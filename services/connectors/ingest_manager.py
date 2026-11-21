"""
Background Ingestion Worker Manager & Unified Ingest Pipeline.

Manages live asyncio workers for pull/stream/simulated sources:
  - polled_api (real httpx polling OR built-in simulation)
  - sse        (real httpx SSE streaming OR built-in simulation)
  - logfile    (real file tailing, optionally appending simulated log lines to disk)
  - kafka      (real aiokafka if available & simulate=False, otherwise built-in simulation)
  - rabbitmq   (real aio_pika if available & simulate=False, otherwise built-in simulation)
  - custom     (built-in simulation when simulate=True)

Supports hot-reloading whenever sources are created, updated, toggled, or deleted.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Event, Source
from services.connectors.parser import get_by_path, parse_raw_payload
from services.connectors.simulator import generate_simulated_event
from services.pipeline import process_event


def ingest_records(db: Session, source: Source, raw_payload: Any) -> dict[str, Any]:
    """
    Universal ingestion entrypoint used by HTTP /api/ingest/{key}, background
    pull/stream workers, and the manual Simulate button.
    """
    records = parse_raw_payload(raw_payload, source.config)
    if not records:
        return {"accepted": 0, "alerts": [], "parsed": []}

    alert_ids: list[int] = []
    for item in records:
        event = Event(source_id=source.id, payload=item)
        db.add(event)
        db.flush()
        alert_ids += process_event(db, event)

    now = datetime.utcnow()
    source.events_count = (source.events_count or 0) + len(records)
    source.last_event_at = now
    source.last_error = None
    if source.sample_event is None and records:
        source.sample_event = records[0]

    cfg = source.config or {}
    if source.enabled:
        source.status = "simulating" if cfg.get("simulate") else "active"

    db.commit()
    return {"accepted": len(records), "alerts": alert_ids, "parsed": records}


def _record_source_error(source_id: int, error_msg: str) -> None:
    db = SessionLocal()
    try:
        src = db.query(Source).filter(Source.id == source_id).first()
        if src:
            src.status = "error"
            src.last_error = error_msg[:500]
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


class IngestManager:
    """Manages lifecycle of background source ingestion tasks."""

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._running = False

    def is_worker_running(self, source_id: int) -> bool:
        task = self._tasks.get(source_id)
        return task is not None and not task.done()

    def active_worker_ids(self) -> list[int]:
        return [sid for sid, t in self._tasks.items() if not t.done()]

    async def start(self) -> None:
        """Start background workers for all enabled pull/stream/simulated sources."""
        self._running = True
        db = SessionLocal()
        try:
            sources = db.query(Source).filter(Source.enabled.is_(True)).all()
            for src in sources:
                await self.sync_source(src)
        finally:
            db.close()

    async def stop(self) -> None:
        """Gracefully cancel all running background workers."""
        self._running = False
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def stop_source(self, source_id: int) -> None:
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

        coro = self._dispatch_worker(source_id, kind, config)
        if coro is not None:
            self._tasks[source_id] = asyncio.create_task(coro, name=f"source-{source_id}-{kind}")

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
        seen_ids: set[str] = set()

        if not url:
            _record_source_error(source_id, "Polled REST API requires a valid 'url' or Simulation Mode enabled.")
            return

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
                        for item in items:
                            if cursor_field and isinstance(item, dict):
                                cid = get_by_path(item, cursor_field)
                                if cid is not None:
                                    cid_str = str(cid)
                                    if cid_str in seen_ids:
                                        continue
                                    seen_ids.add(cid_str)
                                    if len(seen_ids) > 5000:
                                        seen_ids.clear()
                            new_items.append(item)

                        if new_items:
                            # Cap initial backfill burst to 25 items per poll
                            await asyncio.to_thread(_ingest_in_fresh_session, source_id, new_items[:25])
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

        offset = 0
        if path.exists() and not from_beginning:
            offset = path.stat().st_size

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
                        if size < offset:
                            offset = 0  # file rotated/truncated
                        if size > offset:
                            with path.open("r", encoding="utf-8", errors="replace") as fh:
                                fh.seek(offset)
                                chunk = fh.read()
                                offset = fh.tell()
                            lines = [ln for ln in chunk.splitlines() if ln.strip()]
                            if lines:
                                await asyncio.to_thread(_ingest_in_fresh_session, source_id, lines)
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
