"""
Universal Event & Log Sources Router (/api/sources, /api/ingest/{key}, /api/events).

Supports:
  - Declarative connector specs (Webhook, Polled REST API, SSE Stream, Tailed Log File,
    Apache Kafka, RabbitMQ, and Custom Specs)
  - Config-as-Code YAML/JSON Import & Export
  - Live Dry-Run Parser + Schema Discovery + Rule Matching (without writing to DB)
  - Universal Simulation endpoint for every source kind
  - Live Connection Tester
  - Optional Admin-only enforcement via REQUIRE_ADMIN_FOR_SOURCES flag
"""
import hashlib
import hmac
import json
import re
import secrets
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

from database import get_db
from models import Event, Source, User
from routers.deps import get_current_admin_user, get_optional_current_user
from services.connectors import (
    CONNECTOR_REGISTRY,
    dry_run_against_rules,
    extract_fields,
    generate_simulated_event,
    ingest_manager,
    ingest_records,
    list_connector_specs,
    list_simulator_presets,
    mask_source_config,
    merge_secret_fields,
    parse_raw_payload,
    validate_source_config,
)

# Flip to True when you want to restrict source create/edit/delete to Administrators only.
REQUIRE_ADMIN_FOR_SOURCES = False


def require_source_manager(
    user: Optional[User] = Depends(get_optional_current_user),
) -> Optional[User]:
    """
    Centralized permission gate for source management endpoints.
    Currently open to all users; set REQUIRE_ADMIN_FOR_SOURCES = True to enforce admin-only.
    """
    if REQUIRE_ADMIN_FOR_SOURCES:
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


router = APIRouter(prefix="/api", tags=["Sources & Ingest"])


# --- Request Schemas (Python 3.9 compatible) ---

class SourceCreatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    team: str = Field("All", min_length=1, max_length=100)
    kind: str = Field("webhook", max_length=32)
    key: Optional[str] = Field(None, max_length=64)
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    sample_event: Optional[Any] = None


class SourceUpdatePayload(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    team: Optional[str] = Field(None, min_length=1, max_length=100)
    kind: Optional[str] = Field(None, max_length=32)
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    sample_event: Optional[Any] = None


class SourceImportPayload(BaseModel):
    spec: str = Field(..., min_length=2, description="Raw YAML or JSON source specification")


class DryRunPayload(BaseModel):
    kind: str = "webhook"
    config: Dict[str, Any] = Field(default_factory=dict)
    raw_sample: Any


class SimulatePayload(BaseModel):
    count: int = Field(1, ge=1, le=50)
    preset: Optional[str] = None
    custom_payload: Optional[Any] = None


# --- Helpers ---

def _slugify_key(name: str, db: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "source"
    base = base[:48]
    candidate = base
    while db.query(Source).filter(Source.key == candidate).first() is not None:
        candidate = f"{base}-{secrets.token_hex(3)}"
    return candidate


def _serialize_source(src: Source) -> Dict[str, Any]:
    return {
        "id": src.id,
        "key": src.key,
        "ingest_url": f"/api/ingest/{src.key}",
        "name": src.name,
        "team": src.team,
        "kind": src.kind,
        "config": mask_source_config(src.kind, src.config),
        "sample_event": src.sample_event,
        "detected_fields": extract_fields(src.sample_event) if isinstance(src.sample_event, dict) else [],
        "enabled": bool(src.enabled) if src.enabled is not None else True,
        "status": src.status or ("active" if src.enabled else "paused"),
        "last_error": src.last_error,
        "last_event_at": src.last_event_at.isoformat() if src.last_event_at else None,
        "events_count": src.events_count or 0,
        "worker_running": ingest_manager.is_worker_running(src.id),
        "created_at": src.created_at.isoformat() if src.created_at else None,
    }


def _normalize_sample_event(sample: Any, config: Dict[str, Any]) -> Any:
    """If sample_event is a raw string (e.g. log line or JSON string), parse it cleanly."""
    if sample is None or sample == "":
        return None
    if isinstance(sample, dict):
        return sample
    try:
        parsed = parse_raw_payload(sample, config)
        return parsed[0] if parsed else None
    except Exception:
        return {"raw": str(sample)}


def _verify_webhook_auth(source: Source, request: Request, raw_body: bytes) -> None:
    cfg = source.config or {}
    auth_mode = str(cfg.get("auth_mode") or "none").lower()
    secret = str(cfg.get("auth_secret") or "")
    if auth_mode == "none" or not secret:
        return

    if auth_mode == "bearer":
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or not hmac.compare_digest(auth_header[7:].strip(), secret):
            raise HTTPException(status_code=401, detail="Invalid or missing Bearer token for this source.")
    elif auth_mode == "api_key":
        header_name = str(cfg.get("auth_header") or "X-API-Key")
        provided = request.headers.get(header_name, "")
        if not hmac.compare_digest(provided.strip(), secret):
            raise HTTPException(status_code=401, detail=f"Invalid or missing API key in header '{header_name}'.")
    elif auth_mode == "hmac_sha256":
        header_name = str(cfg.get("auth_header") or "X-Hub-Signature-256")
        provided = request.headers.get(header_name, "").strip()
        if provided.startswith("sha256="):
            provided = provided[7:]
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail=f"Invalid HMAC-SHA256 signature in '{header_name}'.")


# --- Metadata & Registry ---

@router.get("/sources/types")
def get_source_types():
    """Return all registered connector types, their config schemas, and simulator presets."""
    return {
        "types": list_connector_specs(),
        "presets": list_simulator_presets(),
        "yaml_supported": yaml is not None,
        "require_admin": REQUIRE_ADMIN_FOR_SOURCES,
    }


# --- Dry-Run (Idea 3: Unseen Schema Playground + Rule Matching) ---

@router.post("/sources/dry-run")
def dry_run_source(payload: DryRunPayload, db: Session = Depends(get_db)):
    """
    Parse & transform an arbitrary sample event (JSON, NDJSON, regex log, key=value),
    discover dot-notation fields, and preview which active rules match — without saving anything.
    """
    try:
        parsed_records = parse_raw_payload(payload.raw_sample, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    fields = extract_fields(parsed_records[0]) if parsed_records else []
    matched_rules = dry_run_against_rules(db, parsed_records)

    return {
        "parsed_count": len(parsed_records),
        "parsed_records": parsed_records[:5],
        "detected_fields": fields,
        "matched_rules": matched_rules,
    }


# --- Config-as-Code Import (Idea 1) ---

@router.post("/sources/import")
async def import_source_spec(
    payload: SourceImportPayload,
    db: Session = Depends(get_db),
    _user: Optional[User] = Depends(require_source_manager),
):
    """Create a source directly from a YAML or JSON specification."""
    raw = payload.spec.strip()
    data: Any = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        if yaml is not None:
            try:
                data = yaml.safe_load(raw)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Invalid YAML/JSON specification: {exc}")
        else:
            raise HTTPException(status_code=422, detail="Invalid JSON specification (PyYAML not installed).")

    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Specification root must be a YAML/JSON object.")

    create_payload = SourceCreatePayload(
        name=str(data.get("name") or "").strip(),
        team=str(data.get("team") or "All").strip(),
        kind=str(data.get("kind") or "webhook").strip(),
        key=data.get("key"),
        enabled=bool(data.get("enabled", True)),
        config=data.get("config") if isinstance(data.get("config"), dict) else {},
        sample_event=data.get("sample_event"),
    )
    return await create_source(create_payload, db=db, _user=_user)


# --- CRUD ---

@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    sources = db.query(Source).order_by(Source.id.desc()).all()
    return [_serialize_source(s) for s in sources]


@router.post("/sources")
async def create_source(
    payload: SourceCreatePayload,
    db: Session = Depends(get_db),
    _user: Optional[User] = Depends(require_source_manager),
):
    errors = validate_source_config(payload.kind, payload.config)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    if payload.key and payload.key.strip():
        clean_key = re.sub(r"[^a-zA-Z0-9._-]+", "-", payload.key.strip()).strip("-")
        if not clean_key:
            raise HTTPException(status_code=422, detail="Invalid source key.")
        if db.query(Source).filter(Source.key == clean_key).first() is not None:
            raise HTTPException(status_code=409, detail=f"Source key '{clean_key}' already exists.")
    else:
        clean_key = _slugify_key(payload.name, db)

    initial_status = "paused"
    if payload.enabled:
        initial_status = "simulating" if payload.config.get("simulate") else "active"

    src = Source(
        key=clean_key,
        name=payload.name.strip(),
        team=payload.team.strip() or "All",
        kind=payload.kind,
        config=payload.config or {},
        sample_event=_normalize_sample_event(payload.sample_event, payload.config or {}),
        enabled=payload.enabled,
        status=initial_status,
        events_count=0,
    )
    db.add(src)
    db.commit()
    db.refresh(src)

    await ingest_manager.sync_source(src)
    return _serialize_source(src)


@router.put("/sources/{source_id}")
async def update_source(
    source_id: int,
    payload: SourceUpdatePayload,
    db: Session = Depends(get_db),
    _user: Optional[User] = Depends(require_source_manager),
):
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")

    next_kind = payload.kind or src.kind
    next_config = (
        merge_secret_fields(next_kind, src.config, payload.config)
        if payload.config is not None
        else (src.config or {})
    )

    errors = validate_source_config(next_kind, next_config)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    if payload.name is not None:
        src.name = payload.name.strip()
    if payload.team is not None:
        src.team = payload.team.strip() or "All"
    src.kind = next_kind
    src.config = next_config
    if payload.sample_event is not None:
        src.sample_event = _normalize_sample_event(payload.sample_event, next_config)
    if payload.enabled is not None:
        src.enabled = payload.enabled

    src.last_error = None
    if not src.enabled:
        src.status = "paused"
    else:
        src.status = "simulating" if next_config.get("simulate") else "active"

    db.commit()
    db.refresh(src)

    await ingest_manager.sync_source(src)
    return _serialize_source(src)


@router.patch("/sources/{source_id}/toggle")
async def toggle_source(
    source_id: int,
    db: Session = Depends(get_db),
    _user: Optional[User] = Depends(require_source_manager),
):
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")

    src.enabled = not bool(src.enabled)
    src.last_error = None
    if not src.enabled:
        src.status = "paused"
    else:
        src.status = "simulating" if (src.config or {}).get("simulate") else "active"

    db.commit()
    db.refresh(src)

    await ingest_manager.sync_source(src)
    return _serialize_source(src)


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
    _user: Optional[User] = Depends(require_source_manager),
):
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")

    await ingest_manager.stop_source(src.id)
    # Detach existing events so history is preserved without FK errors
    db.query(Event).filter(Event.source_id == src.id).update({Event.source_id: None})
    db.delete(src)
    db.commit()
    return {"deleted": True, "id": source_id}


# --- Export Config-as-Code (Idea 1) ---

@router.get("/sources/{source_id}/export")
def export_source_spec(
    source_id: int,
    format: str = Query("yaml", pattern="^(yaml|json)$"),
    db: Session = Depends(get_db),
):
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")

    spec_obj = {
        "name": src.name,
        "key": src.key,
        "team": src.team,
        "kind": src.kind,
        "enabled": bool(src.enabled),
        "config": mask_source_config(src.kind, src.config),
        "sample_event": src.sample_event,
    }

    if format == "yaml" and yaml is not None:
        content = yaml.safe_dump(spec_obj, sort_keys=False, allow_unicode=True)
    else:
        content = json.dumps(spec_obj, indent=2)

    return {"format": format, "filename": f"{src.key}.{format}", "content": content}


@router.get("/sources/{source_id}/fields")
def get_source_fields(source_id: int, db: Session = Depends(get_db)):
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")
    fields = extract_fields(src.sample_event) if isinstance(src.sample_event, dict) else []
    return {"source_id": src.id, "key": src.key, "fields": fields}


# --- Universal Simulation Endpoint (Works for EVERY source kind) ---

@router.post("/sources/{source_id}/simulate")
def simulate_source_events(
    source_id: int,
    payload: SimulatePayload = Body(default_factory=SimulatePayload),
    db: Session = Depends(get_db),
):
    """
    Simulate 1..50 realistic events for ANY source type (Webhook, Polled API, SSE,
    Log File, Kafka, RabbitMQ, Custom) and send them through the live pipeline.
    """
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")

    cfg = src.config or {}
    preset = payload.preset or str(cfg.get("sim_preset") or "workflow_failure")

    total_accepted = 0
    all_alerts: List[int] = []
    last_parsed: List[Dict[str, Any]] = []

    for _ in range(payload.count):
        if payload.custom_payload is not None and payload.custom_payload != "":
            raw_ev = payload.custom_payload
        else:
            raw_ev = generate_simulated_event(preset, src.kind, cfg)

        # For logfile sources, also append to the configured file on disk for realism
        # and advance the tailer offset so the background worker does not double-ingest it.
        if src.kind == "logfile" and cfg.get("file_path"):
            try:
                p = Path(str(cfg["file_path"]))
                p.parent.mkdir(parents=True, exist_ok=True)
                line = raw_ev if isinstance(raw_ev, str) else json.dumps(raw_ev)
                with p.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                ingest_manager.advance_logfile_offset(src.id, p.stat().st_size)
            except Exception:
                pass

        res = ingest_records(db, src, raw_ev)
        total_accepted += res["accepted"]
        all_alerts.extend(res["alerts"])
        last_parsed = res["parsed"]

    return {
        "source_id": src.id,
        "kind": src.kind,
        "simulated_count": total_accepted,
        "alerts": all_alerts,
        "last_parsed": last_parsed[0] if last_parsed else None,
    }


# --- Live Connection Tester ---

@router.post("/sources/{source_id}/test-connection")
async def test_source_connection(source_id: int, db: Session = Depends(get_db)):
    """Probe connectivity for any configured source without mutating state."""
    src = db.query(Source).filter(Source.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Source not found.")

    cfg = src.config or {}
    if cfg.get("simulate"):
        return {
            "ok": True,
            "mode": "simulation",
            "message": f"Simulation Mode is active for '{src.kind}'. Ready to emit synthetic events.",
        }

    if src.kind == "webhook" or src.kind == "custom":
        return {
            "ok": True,
            "mode": "push",
            "message": f"Push endpoint /api/ingest/{src.key} is active and accepting POST requests.",
        }

    if src.kind in ("polled_api", "sse"):
        url = str(cfg.get("url") or "").strip()
        if not url:
            return {"ok": False, "mode": src.kind, "message": "No URL configured."}
        headers = cfg.get("headers_json") if isinstance(cfg.get("headers_json"), dict) else {}
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                if src.kind == "sse":
                    async with client.stream("GET", url, headers=headers) as resp:
                        return {
                            "ok": resp.status_code < 400,
                            "mode": "sse",
                            "message": f"SSE endpoint responded with HTTP {resp.status_code} ({resp.headers.get('content-type', 'unknown')}).",
                        }
                resp = await client.request(str(cfg.get("method") or "GET").upper(), url, headers=headers)
                return {
                    "ok": resp.status_code < 400,
                    "mode": "polled_api",
                    "message": f"HTTP {resp.status_code} — received {len(resp.content)} bytes.",
                }
        except Exception as exc:
            return {"ok": False, "mode": src.kind, "message": f"Connection failed: {exc}"}

    if src.kind == "logfile":
        fp = str(cfg.get("file_path") or "").strip()
        if not fp:
            return {"ok": False, "mode": "logfile", "message": "No file_path configured."}
        p = Path(fp)
        if p.exists():
            return {
                "ok": True,
                "mode": "logfile",
                "message": f"File exists ({p.stat().st_size} bytes) and is readable.",
            }
        return {
            "ok": False,
            "mode": "logfile",
            "message": f"File '{fp}' does not exist yet. Enable Simulation Mode or create the file.",
        }

    if src.kind == "kafka":
        servers = str(cfg.get("bootstrap_servers") or "localhost:9092").split(",")[0].strip()
        host, _, port_str = servers.partition(":")
        port = int(port_str) if port_str.isdigit() else 9092
        try:
            with socket.create_connection((host, port), timeout=3.0):
                return {"ok": True, "mode": "kafka", "message": f"TCP connection to Kafka broker {host}:{port} succeeded."}
        except Exception as exc:
            return {
                "ok": False,
                "mode": "kafka",
                "message": f"Cannot reach Kafka broker {host}:{port} ({exc}). Tip: enable Simulation Mode to test without Kafka.",
            }

    if src.kind == "rabbitmq":
        amqp_url = str(cfg.get("amqp_url") or "amqp://guest:guest@localhost:5672/")
        parsed = urlparse(amqp_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5672
        try:
            with socket.create_connection((host, port), timeout=3.0):
                return {"ok": True, "mode": "rabbitmq", "message": f"TCP connection to RabbitMQ {host}:{port} succeeded."}
        except Exception as exc:
            return {
                "ok": False,
                "mode": "rabbitmq",
                "message": f"Cannot reach RabbitMQ {host}:{port} ({exc}). Tip: enable Simulation Mode to test without RabbitMQ.",
            }

    return {"ok": True, "mode": src.kind, "message": "Source specification is valid."}


# --- Events Inspector & Universal Push Ingest ---

@router.get("/events")
def list_events(
    limit: int = Query(50, ge=1, le=200),
    source_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if source_id is not None:
        q = q.filter(Event.source_id == source_id)
    events = q.order_by(Event.id.desc()).limit(limit).all()

    sources_map = {s.id: {"name": s.name, "key": s.key, "kind": s.kind, "team": s.team} for s in db.query(Source).all()}
    return [
        {
            "id": e.id,
            "source_id": e.source_id,
            "source": sources_map.get(e.source_id) if e.source_id else None,
            "payload": e.payload,
            "received_at": e.received_at.isoformat() if e.received_at else None,
        }
        for e in events
    ]


@router.post("/ingest/{source_key}")
async def ingest(
    source_key: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Universal push ingestion endpoint.
    Accepts any JSON object, JSON array, NDJSON, or plain-text log lines.
    """
    source = db.query(Source).filter(Source.key == source_key).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Unknown source '{source_key}'")
    if not source.enabled:
        raise HTTPException(status_code=403, detail=f"Source '{source_key}' is currently paused.")

    raw_bytes = await request.body()
    _verify_webhook_auth(source, request, raw_bytes)

    content_type = request.headers.get("content-type", "").lower()
    raw_input: Any
    if "application/json" in content_type:
        try:
            raw_input = json.loads(raw_bytes.decode("utf-8"))
        except Exception:
            raw_input = raw_bytes.decode("utf-8", errors="replace")
    else:
        raw_input = raw_bytes.decode("utf-8", errors="replace")

    try:
        result = ingest_records(db, source, raw_input)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {"accepted": result["accepted"], "alerts": result["alerts"]}
