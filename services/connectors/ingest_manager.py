"""
Horizontally Scalable Background Ingestion Worker Manager & Unified Ingest Pipeline.

Compliant with SKALOWANIE.md (N stateless replicas + shared PostgreSQL / local SQLite):
  - Atomic SQL counter updates (`events_count = coalesce(events_count, 0) + N`) to prevent
    lost increments under concurrent ingestion across replicas.
  - PostgreSQL session advisory locks (`pg_try_advisory_lock`) for singleton pull/stream
    workers (`polled_api`, `sse`, `logfile`, and `simulate=True`) so only ONE replica polls
    a given source; automatic failover if the leader replica dies.
  - Real `kafka` (consumer groups) and `rabbitmq` (competing consumers) intentionally run
    WITHOUT advisory locks so partitions/queues distribute across all N replicas.
  - Periodic DB reconciler loop (every 5s) synchronizes worker state across replicas when
    sources are created, edited, toggled, or deleted on another replica.
  - Polled REST API cursor IDs are persisted in `Source.config["_seen_cursors"]` so
    deduplication survives restarts and replica failovers.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from database import DATABASE_URL, SessionLocal, engine
from models import Event, Rule, Source
from services.connectors.parser import get_by_path, parse_raw_payload
from services.connectors.simulator import generate_simulated_event
from services.pipeline import process_event


USE_POSTGRES = DATABASE_URL.startswith("postgresql")
ADVISORY_LOCK_BASE = 700_000
RECONCILE_INTERVAL_S = 5.0
MAX_STORED_CURSORS = 200


def ensure_sources_columns(bind) -> None:
    """Adds new Source columns on existing SQLite or PostgreSQL databases."""
    insp = inspect(bind)
    if "sources" not in insp.get_table_names():
        return
    existing = {col["name"] for col in insp.get_columns("sources")}
    is_pg = bind.dialect.name == "postgresql"
    column_ddls = (
        ("enabled", "ALTER TABLE sources ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE"
         if is_pg else "ALTER TABLE sources ADD COLUMN enabled BOOLEAN DEFAULT 1"),
        ("status", "ALTER TABLE sources ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"
         if is_pg else "ALTER TABLE sources ADD COLUMN status VARCHAR(20) DEFAULT 'active'"),
        ("last_error", "ALTER TABLE sources ADD COLUMN last_error TEXT"),
        ("last_event_at", "ALTER TABLE sources ADD COLUMN last_event_at TIMESTAMP"
         if is_pg else "ALTER TABLE sources ADD COLUMN last_event_at DATETIME"),
        ("events_count", "ALTER TABLE sources ADD COLUMN events_count INTEGER NOT NULL DEFAULT 0"
         if is_pg else "ALTER TABLE sources ADD COLUMN events_count INTEGER DEFAULT 0"),
    )
    missing = [sql for name, sql in column_ddls if name not in existing]
    if not missing:
        return
    with bind.begin() as conn:
        for sql in missing:
            conn.execute(text(sql))


def ingest_records(db: Session, source: Source, raw_payload: Any) -> dict[str, Any]:
    """
    Universal ingestion entrypoint used by HTTP /api/ingest/{key}, background
    pull/stream workers, and the manual Simulate button.
    Uses atomic SQL increment for `events_count` (safe under N concurrent replicas).
    """
    records = parse_raw_payload(raw_payload, source.config)
    if not records:
        return {"accepted": 0, "alerts": [], "parsed": []}

    source_id = source.id
    source_enabled = bool(source.enabled)
    cfg = dict(source.config or {})
    needs_sample = source.sample_event is None
    enabled_rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()

    alert_ids: list[int] = []
    for item in records:
        event = Event(source_id=source_id, payload=item)
        db.add(event)
        db.flush()
        alert_ids += process_event(db, event, rules=enabled_rules, commit=False)

    now = datetime.utcnow()
    next_status = ("simulating" if cfg.get("simulate") else "active") if source_enabled else "paused"

    update_values: dict[Any, Any] = {
        Source.events_count: func.coalesce(Source.events_count, 0) + len(records),
        Source.last_event_at: now,
        Source.last_error: None,
        Source.status: next_status,
    }
    if needs_sample and records:
        update_values[Source.sample_event] = records[0]

    db.query(Source).filter(Source.id == source_id).update(
        update_values,
        synchronize_session=False,
    )
    db.commit()
    return {"accepted": len(records), "alerts": alert_ids, "parsed": records}


def _record_source_error(source_id: int, error_msg: str) -> None:
    db = SessionLocal()
    try:
        db.query(Source).filter(Source.id == source_id).update(
            {
                Source.status: "error",
                Source.last_error: error_msg[:500],
            },
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


def _ingest_in_fresh_session(source_id: int, raw_payload: Any) -> int:
    db = SessionLocal()
    try:
        src = db.query(Source).filter(Source.id == source_id).first()
        if not src or not src.enabled:
            return 0
        res = ingest_records(db, src, raw_payload)
        return res["accepted"]
    finally:
        db.close()


def _load_seen_cursors(source_id: int) -> list[str]:
    db = SessionLocal()
    try:
        src = db.query(Source).filter(Source.id == source_id).first()
        if not src or not isinstance(src.config, dict):
            return []
        raw = src.config.get("_seen_cursors")
        return [str(x) for x in raw] if isinstance(raw, list) else []
    finally:
        db.close()


def _save_seen_cursors(source_id: int, cursors: list[str]) -> None:
    db = SessionLocal()
    try:
        src = db.query(Source).filter(Source.id == source_id).first()
        if not src:
            return
        cfg = dict(src.config or {})
        cfg["_seen_cursors"] = cursors[-MAX_STORED_CURSORS:]
        src.config = cfg
        flag_modified(src, "config")
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


def _config_fingerprint(source: Source) -> str:
    """Hash source worker-relevant settings (ignoring internal _seen_cursors) for reconciler."""
    cfg = {k: v for k, v in (source.config or {}).items() if not str(k).startswith("_")}
    raw = json.dumps({"kind": source.kind, "enabled": bool(source.enabled), "config": cfg}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _needs_singleton_lock(kind: str, config: dict[str, Any]) -> bool:
    """
    Real Kafka (consumer group) & RabbitMQ (competing consumers) scale natively across
    all replicas. Polled APIs, SSE streams, log files, and simulations must run on
    only ONE replica at a time via PostgreSQL advisory locks.
    """
    if bool(config.get("simulate", False)):
        return True
    return kind in ("polled_api", "sse", "logfile", "custom")


class IngestManager:
    """Manages lifecycle of background source ingestion tasks across N replicas."""

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._fingerprints: dict[int, str] = {}
        self._logfile_offsets: dict[int, int] = {}
        self._reconcile_task: asyncio.Task[Any] | None = None
        self._running = False

    def advance_logfile_offset(self, source_id: int, new_offset: int) -> None:
        """Advance tracked file offset after manual simulate writes to a log file."""
        self._logfile_offsets[source_id] = max(self._logfile_offsets.get(source_id, 0), new_offset)

    def is_worker_running(self, source_id: int) -> bool:
        task = self._tasks.get(source_id)
        return task is not None and not task.done()

    def active_worker_ids(self) -> list[int]:
        return [sid for sid, t in self._tasks.items() if not t.done()]

    async def start(self) -> None:
        """Start background workers and the cross-replica DB reconciler."""
        self._running = True
        await self._reconcile_once()
        self._reconcile_task = asyncio.create_task(self._reconcile_loop(), name="ingest-reconciler")

    async def stop(self) -> None:
        """Gracefully cancel the reconciler and all running background workers."""
        self._running = False
        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
        self._reconcile_task = None

        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._fingerprints.clear()
        self._logfile_offsets.clear()

    async def stop_source(self, source_id: int) -> None:
        self._fingerprints.pop(source_id, None)
        self._logfile_offsets.pop(source_id, None)
        task = self._tasks.pop(source_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def _needs_background_worker(self, source: Source) -> bool:
        if not source.enabled:
            return False
        cfg = source.config or {}
        if source.kind in ("polled_api", "sse", "logfile", "kafka", "rabbitmq"):
            return True
        if source.kind == "custom" and bool(cfg.get("simulate", False)):
            return True
        return False

    async def sync_source(self, source: Source) -> None:
        """Hot-reload a single source's background worker after create/update/toggle."""
        await self.stop_source(source.id)
        if not self._running:
            return
        if not self._needs_background_worker(source):
            return

        source_id = source.id
        kind = source.kind
        config = dict(source.config or {})
        fp = _config_fingerprint(source)

        coro = self._dispatch_worker(source_id, kind, config)
        if coro is not None:
            self._fingerprints[source_id] = fp
            self._tasks[source_id] = asyncio.create_task(
                self._run_with_optional_advisory_lock(source_id, kind, config, coro),
                name=f"source-{source_id}-{kind}",
            )

    async def _reconcile_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(RECONCILE_INTERVAL_S)
                await self._reconcile_once()
        except asyncio.CancelledError:
            raise

    async def _reconcile_once(self) -> None:
        """Synchronize local workers with DB state (handles multi-replica edits & failover)."""
        def _fetch_sources() -> list[tuple[int, str, bool, dict[str, Any], str]]:
            db = SessionLocal()
            try:
                rows = db.query(Source).all()
                return [
                    (s.id, s.kind, bool(s.enabled), dict(s.config or {}), _config_fingerprint(s))
                    for s in rows
                ]
            finally:
                db.close()

        try:
            snapshot = await asyncio.to_thread(_fetch_sources)
        except Exception:
            return

        db_ids = {row[0] for row in snapshot}

        # Stop workers for deleted sources
        for running_id in list(self._tasks.keys()):
            if running_id not in db_ids:
                await self.stop_source(running_id)

        # Start, stop, or restart workers whose config/enabled state changed on another replica
        for sid, kind, enabled, cfg, fp in snapshot:
            needs = enabled and (
                kind in ("polled_api", "sse", "logfile", "kafka", "rabbitmq")
                or (kind == "custom" and bool(cfg.get("simulate", False)))
            )
            running = self.is_worker_running(sid)
            prev_fp = self._fingerprints.get(sid)

            if not needs:
                if running or sid in self._tasks:
                    await self.stop_source(sid)
                continue

            if not running or prev_fp != fp:
                await self.stop_source(sid)
                coro = self._dispatch_worker(sid, kind, cfg)
                if coro is not None:
                    self._fingerprints[sid] = fp
                    self._tasks[sid] = asyncio.create_task(
                        self._run_with_optional_advisory_lock(sid, kind, cfg, coro),
                        name=f"source-{sid}-{kind}",
                    )

    async def _run_with_optional_advisory_lock(
        self,
        source_id: int,
        kind: str,
        config: dict[str, Any],
        worker_coro: Any,
    ) -> None:
        """
        On PostgreSQL, hold a session-level advisory lock for singleton workers so only
        one replica executes polling/streaming/simulation for a given source_id.
        If another replica already holds the lock, close the coroutine and exit cleanly;
        the reconciler will retry on failover.
        """
        if not USE_POSTGRES or not _needs_singleton_lock(kind, config):
            await worker_coro
            return

        lock_key = ADVISORY_LOCK_BASE + source_id
        lock_conn = None
        try:
            lock_conn = await asyncio.to_thread(engine.connect)
            acquired = await asyncio.to_thread(
                lambda: bool(lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key}).scalar())
            )
            if not acquired:
                worker_coro.close()
                return
            await worker_coro
        except asyncio.CancelledError:
            raise
        finally:
            if lock_conn is not None:
                try:
                    await asyncio.to_thread(
                        lambda: lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key})
                    )
                except Exception:
                    pass
                try:
                    await asyncio.to_thread(lock_conn.close)
                except Exception:
                    pass

    def _dispatch_worker(self, source_id: int, kind: str, config: dict[str, Any]):
        simulate = bool(config.get("simulate", False))

        if kind == "logfile":
            return self._run_logfile_worker(source_id, config)
        if simulate:
            return self._run_simulation_worker(source_id, kind, config)
        if kind == "polled_api":
            return self._run_polled_api_worker(source_id, config)
        if kind == "sse":
            return self._run_sse_worker(source_id, config)
        if kind == "kafka":
            return self._run_kafka_worker(source_id, config)
        if kind == "rabbitmq":
            return self._run_rabbitmq_worker(source_id, config)
        return None

    async def _run_simulation_worker(self, source_id: int, kind: str, config: dict[str, Any]) -> None:
        interval = max(2.0, float(config.get("sim_interval_s") or 10))
        preset = str(config.get("sim_preset") or "workflow_failure")
        try:
            while True:
                event = generate_simulated_event(preset, kind, config)
                await asyncio.to_thread(_ingest_in_fresh_session, source_id, event)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _record_source_error(source_id, f"Simulation worker error: {exc}")

    async def _run_polled_api_worker(self, source_id: int, config: dict[str, Any]) -> None:
        url = str(config.get("url") or "").strip()
        method = str(config.get("method") or "GET").upper()
        interval = max(3.0, float(config.get("interval_s") or 30))
        timeout = max(2.0, float(config.get("timeout_s") or 10))
        records_path = str(config.get("records_path") or "").strip()
        cursor_field = str(config.get("cursor_field") or "id").strip()
        headers = config.get("headers_json") if isinstance(config.get("headers_json"), dict) else {}

        if not url:
            _record_source_error(source_id, "Polled REST API requires a valid 'url' or Simulation Mode enabled.")
            return

        seen_list = await asyncio.to_thread(_load_seen_cursors, source_id)
        seen_set = set(seen_list)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                while True:
                    try:
                        resp = await client.request(method, url, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        items = get_by_path(data, records_path) if records_path else data
                        if isinstance(items, dict):
                            items = [items]
                        elif not isinstance(items, list):
                            items = [{"value": items}]

                        new_items: list[Any] = []
                        cursors_dirty = False
                        for item in items:
                            if cursor_field and isinstance(item, dict):
                                cid = get_by_path(item, cursor_field)
                                if cid is not None:
                                    cid_str = str(cid)
                                    if cid_str in seen_set:
                                        continue
                                    seen_set.add(cid_str)
                                    seen_list.append(cid_str)
                                    cursors_dirty = True
                            new_items.append(item)

                        if new_items:
                            await asyncio.to_thread(_ingest_in_fresh_session, source_id, new_items[:25])
                        if cursors_dirty:
                            if len(seen_list) > MAX_STORED_CURSORS:
                                seen_list = seen_list[-MAX_STORED_CURSORS:]
                                seen_set = set(seen_list)
                            await asyncio.to_thread(_save_seen_cursors, source_id, seen_list)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        _record_source_error(source_id, f"Poll failed: {exc}")
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise

    async def _run_sse_worker(self, source_id: int, config: dict[str, Any]) -> None:
        url = str(config.get("url") or "").strip()
        headers = dict(config.get("headers_json") if isinstance(config.get("headers_json"), dict) else {})
        headers.setdefault("Accept", "text/event-stream")
        headers.setdefault("User-Agent", "GS-Alerting-Ingest/1.0")
        max_per_min = max(1, int(config.get("max_events_per_min") or 30))

        if not url:
            _record_source_error(source_id, "SSE Stream requires a valid 'url' or Simulation Mode enabled.")
            return

        window_start = time.monotonic()
        window_count = 0

        try:
            while True:
                try:
                    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                        async with client.stream("GET", url, headers=headers) as resp:
                            resp.raise_for_status()
                            async for line in resp.aiter_lines():
                                if not line or not line.startswith("data:"):
                                    continue
                                raw_data = line[5:].strip()
                                if not raw_data:
                                    continue
                                now = time.monotonic()
                                if now - window_start >= 60.0:
                                    window_start = now
                                    window_count = 0
                                if window_count >= max_per_min:
                                    continue
                                window_count += 1
                                await asyncio.to_thread(_ingest_in_fresh_session, source_id, raw_data)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _record_source_error(source_id, f"SSE stream disconnected: {exc}")
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise

    async def _run_logfile_worker(self, source_id: int, config: dict[str, Any]) -> None:
        file_path = str(config.get("file_path") or "/tmp/gs-pricing-engine.log").strip()
        from_beginning = bool(config.get("from_beginning", False))
        poll_interval = max(0.5, float(config.get("poll_interval_s") or 2))
        simulate = bool(config.get("simulate", False))
        sim_preset = str(config.get("sim_preset") or "pricing_log")
        sim_interval = max(2.0, float(config.get("sim_interval_s") or 10))

        path = Path(file_path)
        if simulate:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(exist_ok=True)
            except Exception as exc:
                _record_source_error(source_id, f"Cannot prepare simulated log file '{file_path}': {exc}")
                return

        initial_offset = 0
        if path.exists() and not from_beginning:
            initial_offset = path.stat().st_size
        self._logfile_offsets[source_id] = initial_offset

        last_sim = 0.0

        try:
            while True:
                now = time.monotonic()
                if simulate and (now - last_sim >= sim_interval):
                    last_sim = now
                    ev = generate_simulated_event(sim_preset, "logfile", config)
                    line_to_write = ev if isinstance(ev, str) else json.dumps(ev)
                    try:
                        with path.open("a", encoding="utf-8") as fh:
                            fh.write(line_to_write + "\n")
                    except Exception as exc:
                        _record_source_error(source_id, f"Failed writing simulated log line: {exc}")

                if path.exists():
                    try:
                        size = path.stat().st_size
                        offset = self._logfile_offsets.get(source_id, 0)
                        if size < offset:
                            offset = 0
                            self._logfile_offsets[source_id] = 0
                        if size > offset:
                            with path.open("r", encoding="utf-8", errors="replace") as fh:
                                fh.seek(offset)
                                chunk = fh.read()
                                new_offset = fh.tell()
                            lines = [ln for ln in chunk.splitlines() if ln.strip()]
                            if lines:
                                await asyncio.to_thread(_ingest_in_fresh_session, source_id, lines)
                            self._logfile_offsets[source_id] = max(self._logfile_offsets.get(source_id, 0), new_offset)
                    except Exception as exc:
                        _record_source_error(source_id, f"Error reading log file: {exc}")
                elif not simulate:
                    _record_source_error(source_id, f"Waiting for log file '{file_path}' to exist...")

                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            raise

    async def _run_kafka_worker(self, source_id: int, config: dict[str, Any]) -> None:
        try:
            from aiokafka import AIOKafkaConsumer  # type: ignore
        except ImportError:
            _record_source_error(
                source_id,
                "Real Kafka mode requires 'aiokafka' installed. Enable Simulation Mode to test without a broker.",
            )
            return

        topic = str(config.get("topic") or "trade-events")
        servers = str(config.get("bootstrap_servers") or "localhost:9092")
        group_id = str(config.get("group_id") or "gs-alerting-consumer")
        offset_reset = str(config.get("auto_offset_reset") or "latest")

        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=servers,
            group_id=group_id,
            auto_offset_reset=offset_reset,
        )
        try:
            await consumer.start()
            async for msg in consumer:
                raw = msg.value.decode("utf-8", errors="replace") if msg.value else ""
                if raw:
                    await asyncio.to_thread(_ingest_in_fresh_session, source_id, raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _record_source_error(source_id, f"Kafka consumer error: {exc}")
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass

    async def _run_rabbitmq_worker(self, source_id: int, config: dict[str, Any]) -> None:
        try:
            import aio_pika  # type: ignore
        except ImportError:
            _record_source_error(
                source_id,
                "Real RabbitMQ mode requires 'aio-pika' installed. Enable Simulation Mode to test without a broker.",
            )
            return

        amqp_url = str(config.get("amqp_url") or "amqp://guest:guest@localhost:5672/")
        queue_name = str(config.get("queue") or "workflow.events")

        try:
            connection = await aio_pika.connect_robust(amqp_url)
            async with connection:
                channel = await connection.channel()
                queue = await channel.declare_queue(queue_name, durable=True)
                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        async with message.process():
                            raw = message.body.decode("utf-8", errors="replace")
                            if raw:
                                await asyncio.to_thread(_ingest_in_fresh_session, source_id, raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _record_source_error(source_id, f"RabbitMQ consumer error: {exc}")


ingest_manager = IngestManager()
