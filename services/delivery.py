"""
OSOBA 3 – wysyłka: zapis do Outboxa, formatowanie per kanał i worker z ponawianiem.

Kontrakt przekazywany z pipeline'u (`services/pipeline.py`):
- `enqueue_deliveries(db, alert, recipients)` jest wołane RAZ na nowy alert
  (nowy problem, ponowne wystąpienie po Resolve, lub nowe okno czasowe `group_window_s`).
  Powtórzenia zdeduplikowane (`count += 1`) NIE wołają ponownie `enqueue_deliveries`.
- `alert` ma już nadane `alert.id` (link `/#alerts/{alert.id}`), wyrenderowane `title`/`body`,
  `severity`, `color`, `team` oraz `steps` z podstawionymi zmiennymi zdarzenia.
- `recipients` są już rozwiązani z uwzględnieniem `channel_prefs`, `on_call`, `quiet_hours`
  i fallbacków (dla kanału `"ui"` pole `person_id` oraz `to` mają wartość `None`).

Skalowanie poziome (`SKALOWANIE.md`):
- Wiersze `Delivery` oraz flagi awarii kanałów (`ChannelConfig`) leżą w bazie.
- Worker na Postgresie pobiera partię przez `SELECT ... FOR UPDATE SKIP LOCKED`,
  dzięki czemu N replik nie wysyła tego samego powiadomienia wielokrotnie.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Alert, ChannelConfig, Delivery
from services.contracts import Recipient

log = logging.getLogger("delivery")

MAX_ATTEMPTS = 5
POLL_INTERVAL_S = 1.0
BACKOFF_BASE_S = 2
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
CHANNEL_ORDER = ("email", "sms", "phone", "ui")


def backoff_seconds(attempts: int) -> int:
    return min(30, BACKOFF_BASE_S ** max(1, attempts))


class DeliveryError(RuntimeError):
    """Raised when a channel fails to deliver a notification."""


def format_delivery_message(alert: Alert, channel: str) -> dict[str, Any]:
    """Render alert & runbook instructions tailored to the target channel."""
    alert_link = f"{PUBLIC_BASE_URL}/#alerts/{alert.id}"
    sev = (alert.severity or "warning").upper()
    steps = alert.steps or []

    if channel == "email":
        subject = f"[{sev}] {alert.title}"
        lines = [
            f"Team: {alert.team}",
            f"Severity: {sev}",
        ]
        if alert.body:
            lines.append(f"\n{alert.body}")
        if steps:
            lines.append("\nRunbook steps:")
            for idx, step in enumerate(steps, 1):
                text = str(step.get("text") or "").strip()
                action = step.get("action")
                approval = step.get("approval")
                line = f"{idx}. {text}"
                if action:
                    line += f" [action: {action}]"
                if approval == "required":
                    line += " [APPROVAL REQUIRED]"
                lines.append(line)
        lines.append(f"\nOpen alert: {alert_link}")
        return {"subject": subject, "body": "\n".join(lines), "link": alert_link}

    if channel == "sms":
        prefix = f"[{sev}] "
        suffix = f" — {alert_link}"
        max_title = max(10, 160 - len(prefix) - len(suffix))
        title = alert.title or "Alert"
        if len(title) > max_title:
            title = title[: max_title - 1] + "…"
        return {"body": f"{prefix}{title}{suffix}", "link": alert_link}

    if channel == "phone":
        steps_note = (
            f"{len(steps)} runbook step{'s' if len(steps) != 1 else ''} ready in the portal."
            if steps
            else "Open the portal to acknowledge and investigate."
        )
        body_part = f" Details: {alert.body}." if alert.body else ""
        script = f"{sev} alert for {alert.team}: {alert.title}.{body_part} {steps_note}"
        return {"script": script, "link": alert_link}

    return {"body": f"Live feed pushed to {alert.team} ({alert_link})", "link": alert_link}


# ---------------------------------------------------------------- pluggable channel providers

class ChannelProvider:
    """Base notification provider. Swap a subclass in CHANNEL_PROVIDERS for a real gateway."""

    channel: str = ""
    provider_name: str = ""

    def send(self, to: str | None, alert: Alert, message: dict[str, Any]) -> None:
        raise NotImplementedError


class MockEmailProvider(ChannelProvider):
    channel = "email"
    provider_name = "Mock SMTP Gateway"

    def send(self, to: str | None, alert: Alert, message: dict[str, Any]) -> None:
        if not to or not to.strip():
            raise DeliveryError("Missing recipient email address.")
        log.info("[EMAIL -> %s] %s", to, message.get("subject"))


class MockSmsProvider(ChannelProvider):
    channel = "sms"
    provider_name = "Mock SMS Gateway"

    def send(self, to: str | None, alert: Alert, message: dict[str, Any]) -> None:
        if not to or not to.strip():
            raise DeliveryError("Missing recipient phone number for SMS.")
        log.info("[SMS -> %s] %s", to, message.get("body"))


class MockPhoneProvider(ChannelProvider):
    channel = "phone"
    provider_name = "Mock Voice/Phone Gateway"

    def send(self, to: str | None, alert: Alert, message: dict[str, Any]) -> None:
        if not to or not to.strip():
            raise DeliveryError("Missing recipient phone number for voice call.")
        log.info("[PHONE -> %s] %s", to, message.get("script"))


class UiChannelProvider(ChannelProvider):
    channel = "ui"
    provider_name = "Live SSE Feed"

    def send(self, to: str | None, alert: Alert, message: dict[str, Any]) -> None:
        log.debug("[UI -> %s] %s", alert.team, message.get("body"))


CHANNEL_PROVIDERS: dict[str, ChannelProvider] = {}


def register_provider(provider: ChannelProvider) -> None:
    CHANNEL_PROVIDERS[provider.channel] = provider


for _default_provider in (
    MockEmailProvider(),
    MockSmsProvider(),
    MockPhoneProvider(),
    UiChannelProvider(),
):
    register_provider(_default_provider)


# ---------------------------------------------------------------- DB-backed simulated outages

def is_channel_down(db: Session, channel: str) -> tuple[bool, str]:
    cfg = db.get(ChannelConfig, channel)
    if cfg and cfg.simulated_down:
        return True, cfg.error_message or f"Simulated {channel} channel outage"
    return False, ""


def set_channel_outage(
    db: Session,
    channel: str,
    down: bool,
    error_message: str | None = None,
) -> dict[str, Any]:
    cfg = db.get(ChannelConfig, channel)
    now = datetime.utcnow()
    if cfg is None:
        cfg = ChannelConfig(
            channel=channel,
            simulated_down=bool(down),
            error_message=(error_message.strip()[:300] if down and error_message else None),
            updated_at=now,
        )
        db.add(cfg)
    else:
        cfg.simulated_down = bool(down)
        cfg.error_message = error_message.strip()[:300] if down and error_message else None
        cfg.updated_at = now
    db.commit()
    db.refresh(cfg)
    provider = CHANNEL_PROVIDERS.get(channel)
    return {
        "channel": channel,
        "provider": provider.provider_name if provider else channel,
        "simulated_down": bool(cfg.simulated_down),
        "error_message": cfg.error_message if cfg.simulated_down else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


def list_channel_statuses(db: Session) -> list[dict[str, Any]]:
    configs = {cfg.channel: cfg for cfg in db.query(ChannelConfig).all()}
    ordered_channels = list(CHANNEL_ORDER) + [
        ch for ch in CHANNEL_PROVIDERS if ch not in CHANNEL_ORDER
    ]
    out: list[dict[str, Any]] = []
    for ch in ordered_channels:
        provider = CHANNEL_PROVIDERS.get(ch)
        if provider is None:
            continue
        cfg = configs.get(ch)
        out.append({
            "channel": ch,
            "provider": provider.provider_name,
            "simulated_down": bool(cfg.simulated_down) if cfg else False,
            "error_message": cfg.error_message if cfg and cfg.simulated_down else None,
            "updated_at": cfg.updated_at.isoformat() if cfg and cfg.updated_at else None,
        })
    return out


# ---------------------------------------------------------------- enqueue & worker batch processing

def enqueue_deliveries(db: Session, alert: Alert, recipients: list[Recipient]) -> list[Delivery]:
    """
    Persist one Outbox Delivery row per resolved recipient inside the caller's transaction.
    `ui` deliveries are recorded immediately as `sent` since live SSE already pushes them to the UI.
    """
    if not recipients:
        return []

    now = datetime.utcnow()
    rows: list[Delivery] = []
    for r in recipients:
        if r.channel == "ui":
            rows.append(Delivery(
                alert_id=alert.id,
                person_id=r.person_id,
                channel=r.channel,
                to=r.to,
                status="sent",
                attempts=1,
                last_error=None,
                created_at=now,
                sent_at=now,
                next_retry_at=None,
            ))
        else:
            rows.append(Delivery(
                alert_id=alert.id,
                person_id=r.person_id,
                channel=r.channel,
                to=r.to,
                status="pending",
                attempts=0,
                last_error=None,
                created_at=now,
                sent_at=None,
                next_retry_at=None,
            ))

    db.add_all(rows)
    db.flush()
    return rows


def process_pending_deliveries(
    db: Session,
    batch_size: int = 20,
    *,
    ignore_backoff: bool = False,
) -> dict[str, int]:
    """Claim pending/retryable deliveries and attempt sending via each channel provider."""
    now = datetime.utcnow()
    query = db.query(Delivery).filter(
        Delivery.status.in_(("pending", "failed")),
        Delivery.attempts < MAX_ATTEMPTS,
    )
    if not ignore_backoff:
        query = query.filter(
            or_(Delivery.next_retry_at.is_(None), Delivery.next_retry_at <= now)
        )
    query = query.order_by(Delivery.id.asc()).limit(batch_size)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)

    rows = query.all()
    if not rows:
        return {"claimed": 0, "sent": 0, "failed": 0}

    sent = 0
    failed = 0
    for delivery in rows:
        alert = db.get(Alert, delivery.alert_id)
        try:
            if alert is None:
                raise DeliveryError(f"Alert {delivery.alert_id} not found")
            down, reason = is_channel_down(db, delivery.channel)
            if down:
                raise DeliveryError(reason)
            provider = CHANNEL_PROVIDERS.get(delivery.channel)
            if provider is None:
                raise DeliveryError(f"Unsupported delivery channel '{delivery.channel}'")
            message = format_delivery_message(alert, delivery.channel)
            provider.send(delivery.to, alert, message)
            delivery.status = "sent"
            delivery.attempts = (delivery.attempts or 0) + 1
            delivery.sent_at = datetime.utcnow()
            delivery.last_error = None
            delivery.next_retry_at = None
            sent += 1
        except Exception as exc:  # noqa: BLE001
            delivery.status = "failed"
            delivery.attempts = (delivery.attempts or 0) + 1
            delivery.last_error = str(exc)[:500]
            if delivery.attempts < MAX_ATTEMPTS:
                delivery.next_retry_at = datetime.utcnow() + timedelta(
                    seconds=backoff_seconds(delivery.attempts)
                )
            else:
                delivery.next_retry_at = None
            failed += 1

    db.commit()
    return {"claimed": len(rows), "sent": sent, "failed": failed}


def _run_worker_batch() -> dict[str, int]:
    db = SessionLocal()
    try:
        return process_pending_deliveries(db)
    finally:
        db.close()


class DeliveryWorker:
    """Async background loop dispatching Outbox deliveries."""

    def __init__(self) -> None:
        self._task: asyncio.Task[Any] | None = None
        self._running = False

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="outbox-delivery-worker")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        try:
            while self._running:
                try:
                    await asyncio.to_thread(_run_worker_batch)
                except Exception:  # noqa: BLE001
                    log.exception("Outbox delivery worker batch failed")
                await asyncio.sleep(POLL_INTERVAL_S)
        except asyncio.CancelledError:
            raise


delivery_worker = DeliveryWorker()
