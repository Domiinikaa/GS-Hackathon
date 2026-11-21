"""OSOBA 4 – runbooki (CRUD + podgląd parsowania) i test silnika reguł na sucho."""
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import CustomAction, Event, Rule, Runbook
from routers.deps import get_optional_current_user
from services import runbook_runner
from services import simulator as sim
from services.rules_engine import evaluate
from services.runbook_parser import ACTIONS, KINDS, ParseResult, normalize_matches, parse_runbook_full, set_kind

router = APIRouter(prefix="/api", tags=["Runbooks & engine (Osoba 4)"])


# ---------------------------------------------------------------- schematy

class ParseRequest(BaseModel):
    raw: str
    format: str = "auto"  # auto | yaml | json | html | markdown | text | link


def _clean_name(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("Name cannot be empty")
    return v


class RunbookIn(BaseModel):
    name: str
    raw: str
    format: str = "auto"
    matches: Optional[Dict[str, Any]] = None  # grupa warunków jak w regułach – automatyczne podpinanie
    kinds: Optional[List[Optional[str]]] = None  # rodzaj każdego kroku (jak w RunbookPatch)

    _name = field_validator("name")(_clean_name)


class RunbookPatch(BaseModel):
    name: Optional[str] = None
    raw: Optional[str] = None
    format: Optional[str] = None
    matches: Optional[Dict[str, Any]] = None
    kinds: Optional[List[Optional[str]]] = None   # rodzaj każdego kroku z UI: manual | auto | approve | approve_manual | null (auto-wykryj)

    _name = field_validator("name")(_clean_name)


class EngineTestRequest(BaseModel):
    event: Any                                # dowolny JSON zdarzenia
    rule_ids: Optional[List[str]] = None      # tylko te reguły z bazy (domyślnie: wszystkie włączone)
    rule: Optional[Dict[str, Any]] = None     # albo reguła z formularza, jeszcze niezapisana


def _parse_or_422(raw: str, fmt: str, db: Session) -> ParseResult:
    """Format, kroki, ostrzeżenia, nazwa, matches. Błąd tylko przy ręcznie wybranym, niepoprawnym YAML / JSON.
    Rozpoznaje też własne akcje zespołu (Runbooks → Actions)."""
    try:
        return parse_runbook_full(raw, fmt, runbook_runner.custom_actions(db))
    except ValueError as e:
        raise HTTPException(422, str(e))


def _get_or_404(db: Session, runbook_id: int) -> Runbook:
    rb = db.get(Runbook, runbook_id)
    if rb is None:
        raise HTTPException(404, f"Runbook {runbook_id} not found")
    return rb


def _apply_kinds(steps: List[dict], kinds: List[Optional[str]]) -> List[dict]:
    if len(kinds) != len(steps):
        raise HTTPException(422, f"Expected {len(steps)} kinds, one per step")
    out = []
    for i, (step, kind) in enumerate(zip(steps, kinds)):
        if kind is not None and kind not in KINDS:
            raise HTTPException(422, f"Step {i + 1}: kind must be one of {', '.join(KINDS)}")
        try:
            out.append(set_kind(step, kind))
        except ValueError as e:
            raise HTTPException(422, f"Step {i + 1}: {e}")
    return out


def _keep_kinds(old: List[dict], new: List[dict]) -> List[dict]:
    """Po edycji treści zostawiamy ręcznie wybrane rodzaje kroków, których tekst się nie zmienił."""
    chosen = {s.get("text"): s.get("kind") for s in old if s.get("kind")}
    out = []
    for step in new:
        kind = chosen.get(step.get("text"))
        try:
            out.append(set_kind(step, kind) if kind else step)
        except ValueError:
            out.append(step)
    return out


# ---------------------------------------------------------------- runbooki

@router.get("/runbooks")
def list_runbooks(db: Session = Depends(get_db)):
    return db.query(Runbook).order_by(Runbook.id).all()


@router.post("/runbooks/parse")
def preview_parse(req: ParseRequest, db: Session = Depends(get_db)):
    """UI wkleja tekst i od razu widzi kroki, ostrzeżenia oraz (z YAML / JSON) nazwę i matches."""
    r = _parse_or_422(req.raw, req.format, db)
    return {"format": r.format, "steps": r.steps, "warnings": r.warnings, "name": r.name, "matches": r.matches}


@router.get("/runbooks/{runbook_id}")
def get_runbook(runbook_id: int, db: Session = Depends(get_db)):
    rb = _get_or_404(db, runbook_id)
    rules = db.query(Rule).filter(Rule.runbook_id == runbook_id).all()
    return {**{c.name: getattr(rb, c.name) for c in Runbook.__table__.columns},
            "rules": [{"id": r.id, "name": r.name} for r in rules]}


@router.post("/runbooks")
def create_runbook(payload: RunbookIn, db: Session = Depends(get_db)):
    r = _parse_or_422(payload.raw, payload.format, db)
    # matches podane wprost wygrywają; inaczej bierzemy je z treści runbooka (YAML: "matches:")
    matches = normalize_matches(payload.matches) if payload.matches else r.matches
    steps = _apply_kinds(r.steps, payload.kinds) if payload.kinds is not None else r.steps
    rb = Runbook(name=payload.name, format=r.format, raw=payload.raw, steps=steps, matches=matches)
    db.add(rb)
    db.commit()
    db.refresh(rb)
    return rb


@router.put("/runbooks/{runbook_id}")
def update_runbook(runbook_id: int, payload: RunbookPatch, db: Session = Depends(get_db)):
    rb = _get_or_404(db, runbook_id)
    if payload.name is not None:
        rb.name = payload.name
    if payload.raw is not None or payload.format is not None:
        raw = payload.raw if payload.raw is not None else rb.raw
        r = _parse_or_422(raw, payload.format or rb.format, db)
        rb.format, rb.steps, rb.raw = r.format, _keep_kinds(rb.steps or [], r.steps), raw
        if r.format in ("yaml", "json"):
            rb.matches = r.matches              # treść runbooka mówi, do czego pasuje (albo już nie)
    if payload.matches is not None:
        rb.matches = normalize_matches(payload.matches)  # {} = wyłącz automatyczne podpinanie
    if payload.kinds is not None:
        rb.steps = _apply_kinds(rb.steps or [], payload.kinds)
    db.commit()
    db.refresh(rb)
    return rb


@router.delete("/runbooks/{runbook_id}")
def delete_runbook(runbook_id: int, db: Session = Depends(get_db)):
    rb = _get_or_404(db, runbook_id)
    db.query(Rule).filter(Rule.runbook_id == runbook_id).update({Rule.runbook_id: None})
    db.delete(rb)
    db.commit()
    return {"deleted": runbook_id}


@router.post("/runbooks/{runbook_id}/attach/{rule_id}")
def attach_to_rule(runbook_id: int, rule_id: str, db: Session = Depends(get_db)):
    """Podpina runbook do reguły (rule.runbook_id). Gotowe do użycia z ekranu Runbooks."""
    _get_or_404(db, runbook_id)
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule {rule_id} not found")
    rule.runbook_id = runbook_id
    db.commit()
    return {"rule_id": rule_id, "runbook_id": runbook_id}


@router.delete("/runbooks/{runbook_id}/attach/{rule_id}")
def detach_from_rule(runbook_id: int, rule_id: str, db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if rule is None or rule.runbook_id != runbook_id:
        raise HTTPException(404, "This runbook is not attached to that rule")
    rule.runbook_id = None
    db.commit()
    return {"rule_id": rule_id, "runbook_id": None}


# ---------------------------------------------------------------- test silnika

@router.post("/engine/test")
def engine_test(req: EngineTestRequest, db: Session = Depends(get_db)):
    """Uruchamia silnik reguł na zdarzeniu BEZ zapisu: które reguły pasują, jaki tytuł, jakie kroki."""
    if req.rule is not None:
        fields = {c.name for c in Rule.__table__.columns}
        rule = Rule(**{k: v for k, v in req.rule.items() if k in fields})
        rule.id = rule.id or "draft"
        rule.enabled = True
        rules = [rule]
    else:
        q = db.query(Rule)
        q = q.filter(Rule.id.in_(req.rule_ids)) if req.rule_ids else q.filter(Rule.enabled.is_(True))
        rules = q.all()

    event = Event(id=0, payload=req.event, received_at=datetime.utcnow())  # nie dodajemy do sesji
    matches = evaluate(event, rules, db=db)
    matched = {m.rule_id for m in matches}
    return {
        "checked": [r.id for r in rules],
        "matched": [asdict(m) for m in matches],
        "not_matched": [r.id for r in rules if r.id not in matched],
    }


# ---------------------------------------------------------------- kroki runbooka w alercie (wykonywanie)
# Approve i Mark done są u Osoby 1 (routers/alerts.py); tutaj Retry nieudanego kroku.

# ---------------------------------------------------------------- akcje: wbudowane + własne zespołu
# "Adding a new runbook or a new kind of action should be as easy as adding a rule" (kartka 2.6):
# zespół dodaje akcję w UI (nazwa + adres + czy wymaga zgody), runbooki jej używają, zero zmian w kodzie.

class CustomActionIn(BaseModel):
    label: str                                 # "Clear cache"
    url: str                                   # "https://{{service}}/cache/clear"
    risky: bool = True
    description: Optional[str] = None

    @field_validator("label")
    @classmethod
    def _label(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2 or len(v) > 100:
            raise ValueError("Name must be 2–100 characters")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^https?://\S+$", v):
            raise ValueError("Address must start with http:// or https://, e.g. https://{{service}}/cache/clear")
        return v


def _action_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:64]


def _action_out(a: CustomAction) -> Dict[str, Any]:
    return {"id": a.id, "key": a.key, "label": a.label, "url": a.url, "risky": bool(a.risky),
            "description": a.description}


def _reparse_runbooks(db: Session) -> None:
    """Po dodaniu / usunięciu akcji zapisane runbooki od razu ją rozpoznają (ręczne rodzaje kroków zostają)."""
    custom = runbook_runner.custom_actions(db)
    for rb in db.query(Runbook).all():
        try:
            rb.steps = _keep_kinds(rb.steps or [], parse_runbook_full(rb.raw, rb.format or "auto", custom).steps)
        except ValueError:
            continue


@router.get("/actions")
def list_actions(db: Session = Depends(get_db)):
    """Akcje, które aplikacja umie wykonać: wbudowane (kod) i własne zespołów (dodane w UI)."""
    builtin = [{"key": k, "label": v["label"], "risky": v["risky"]} for k, v in ACTIONS.items()]
    return {"builtin": builtin, "custom": [_action_out(a) for a in db.query(CustomAction).order_by(CustomAction.label)],
            "kinds": list(KINDS)}


@router.post("/actions", status_code=201)
def create_action(payload: CustomActionIn, db: Session = Depends(get_db)):
    key = _action_key(payload.label)
    if not key or key in ACTIONS:
        raise HTTPException(409, f"“{payload.label}” is a built-in action – pick another name")
    if db.query(CustomAction).filter(CustomAction.key == key).first():
        raise HTTPException(409, f"An action called “{payload.label}” already exists")
    action = CustomAction(key=key, label=payload.label, url=payload.url, risky=payload.risky,
                          description=payload.description)
    db.add(action)
    db.flush()
    _reparse_runbooks(db)
    db.commit()
    db.refresh(action)
    return _action_out(action)


@router.put("/actions/{action_id}")
def update_action(action_id: int, payload: CustomActionIn, db: Session = Depends(get_db)):
    action = db.get(CustomAction, action_id)
    if action is None:
        raise HTTPException(404, "Action not found")
    action.url, action.risky, action.description = payload.url, payload.risky, payload.description
    action.label = payload.label                      # nowa nazwa w tekście – klucz w YAML-u zostaje
    db.flush()
    _reparse_runbooks(db)                             # nazwa albo "risky" mogły się zmienić
    db.commit()
    db.refresh(action)
    return _action_out(action)


@router.delete("/actions/{action_id}")
def delete_action(action_id: int, db: Session = Depends(get_db)):
    action = db.get(CustomAction, action_id)
    if action is None:
        raise HTTPException(404, "Action not found")
    db.delete(action)
    db.flush()
    _reparse_runbooks(db)
    db.commit()
    return {"deleted": action_id}


@router.post("/alerts/{alert_id}/steps/{step_index}/retry")
def retry_step(alert_id: int, step_index: int, db: Session = Depends(get_db),
               user=Depends(get_optional_current_user)):
    """Ponów nieudany krok. Krok ze zgodą może ponowić tylko lead / admin."""
    return runbook_runner.retry_step(db, alert_id, step_index, user)


# ---------------------------------------------------------------- symulator systemów docelowych

class SimServicePatch(BaseModel):
    healthy: Optional[bool] = None
    workflows_ok: Optional[bool] = None


def _sim_out(svc) -> dict:
    now = datetime.utcnow()
    return {"name": svc.name, "healthy": bool(svc.healthy), "workflows_ok": bool(svc.workflows_ok),
            "restarting": bool(svc.restarting_until and now < svc.restarting_until),
            "restarting_until": svc.restarting_until}


@router.get("/sim/services")
def sim_services(db: Session = Depends(get_db)):
    services = sim.list_services(db)
    db.commit()
    return [_sim_out(s) for s in services]


@router.put("/sim/services/{name}")
def sim_set_service(name: str, payload: SimServicePatch, db: Session = Depends(get_db)):
    if name not in sim.DEFAULT_SERVICES:
        raise HTTPException(404, f"Unknown simulated service {name!r}")
    svc = sim.set_service(db, name, healthy=payload.healthy, workflows_ok=payload.workflows_ok)
    db.commit()
    return _sim_out(svc)


@router.get("/sim/calls")
def sim_calls(limit: int = 50, db: Session = Depends(get_db)):
    return sim.recent_calls(db, min(max(limit, 1), 200))
