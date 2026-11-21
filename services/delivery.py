"""
Wysyłka alertów: zapis do Outboxa + "listonosz" w tle, który doręcza i ponawia.

  enqueue_deliveries()  – jeden wiersz w tabeli deliveries na odbiorcę, status "pending".
                          Treść jest liczona od razu, więc Outbox pokazuje dokładnie to, co wyjdzie.
  process_due()         – bierze wysyłki, których czas nadszedł, i doręcza je przez kanał.
  start_worker()        – pętla w tle (co 1 s) wywołująca process_due().

Nic nie ginie: wszystko leży w tabeli. Gdy kanał nie działa → kolejna próba po 2, 4, 8, 16 s,
po MAX_ATTEMPTS nieudanych → status "dead" (widać w Outboxie z ostatnim błędem).

Wiele kopii serwera: każda ma swojego listonosza, ale wysyłkę "rezerwuje" jedno polecenie
UPDATE ... WHERE status = <stary> – udaje się tylko jednej kopii, więc nic nie wychodzi dwa razy.
Działa tak samo na SQLite i Postgresie.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import or_, text, update
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Alert, Delivery
from services.channels import ChannelError, Message, available_channels, get_channel
from services.channels.messages import build_message
from services.contracts import Recipient

log = logging.getLogger("delivery")

MAX_ATTEMPTS = 5
LEASE = timedelta(seconds=60)     # na tyle wysyłka jest zarezerwowana dla jednej kopii
POLL_SECONDS = 1.0
BATCH = 20

_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


# ---------------------------------------------------------------- zapis do Outboxa
def enqueue_deliveries(db: Session, alert: Alert, recipients: list[Recipient]) -> list[Delivery]:
    """Jeden wiersz na odbiorcę. Kanał "ui" pomijamy – to robi live feed na stronie."""
    now = datetime.utcnow()
    created: list[Delivery] = []
    for r in recipients:
        if r.channel == "ui" or not r.to:
            continue
        msg = build_message(alert, r.channel, r.to, r.name)
        delivery = Delivery(
            alert_id=alert.id, person_id=r.person_id, channel=r.channel, to=r.to,
            status="pending", attempts=0, subject=msg.subject, body=msg.body, html=msg.html,
            next_attempt_at=now, created_at=now,
        )
        db.add(delivery)
        created.append(delivery)
    db.flush()
    return created


# ---------------------------------------------------------------- listonosz
def process_due(db: Session) -> int:
    """Doręcz wszystkie wysyłki, których czas nadszedł. Zwraca liczbę prób."""
    channels = available_channels()
    if not channels:
        return 0
    now = datetime.utcnow()
    due_ids = [row.id for row in (
        db.query(Delivery.id)
        .filter(Delivery.channel.in_(channels))
        .filter(Delivery.status.in_(["pending", "failed", "sending"]))  # "sending" po terminie = kopia padła w trakcie
        .filter(or_(Delivery.next_attempt_at.is_(None), Delivery.next_attempt_at <= now))
        .order_by(Delivery.id)
        .limit(BATCH)
    )]
    tried = 0
    for delivery_id in due_ids:
        if _claim(db, delivery_id, now):
            _deliver(db, delivery_id)
            tried += 1
    return tried


def _claim(db: Session, delivery_id: int, now: datetime) -> bool:
    """Zarezerwuj wysyłkę dla tej kopii. True tylko dla jednej kopii, nawet gdy próbują naraz."""
    result = db.execute(
        update(Delivery)
        .where(Delivery.id == delivery_id)
        .where(Delivery.status.in_(["pending", "failed", "sending"]))
        .where(or_(Delivery.next_attempt_at.is_(None), Delivery.next_attempt_at <= now))
        .values(status="sending", next_attempt_at=now + LEASE)
    )
    db.commit()
    return result.rowcount == 1


def _deliver(db: Session, delivery_id: int) -> None:
    delivery = db.get(Delivery, delivery_id, populate_existing=True)
    channel = get_channel(delivery.channel)
    delivery.attempts = (delivery.attempts or 0) + 1
    try:
        if channel is None:
            raise ChannelError(f"channel '{delivery.channel}' is not configured")
        channel.send(Message(to=delivery.to, subject=delivery.subject or "",
                             body=delivery.body or "", html=delivery.html))
        delivery.status = "sent"
        delivery.sent_at = datetime.utcnow()
        delivery.last_error = None
        delivery.next_attempt_at = None
        log.info("delivery %s sent via %s to %s", delivery.id, delivery.channel, delivery.to)
    except Exception as exc:  # noqa: BLE001 – każdy błąd kanału = ponowienie, nie upadek listonosza
        delivery.last_error = str(exc)[:1000]
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "dead"
            delivery.next_attempt_at = None
            log.warning("delivery %s dead after %s attempts: %s", delivery.id, delivery.attempts, exc)
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = datetime.utcnow() + timedelta(seconds=2 ** delivery.attempts)
            log.info("delivery %s failed (attempt %s), retry in %ss: %s",
                     delivery.id, delivery.attempts, 2 ** delivery.attempts, exc)
    db.commit()


def _loop() -> None:
    while True:
        db = SessionLocal()
        try:
            process_due(db)
        except Exception as exc:  # noqa: BLE001
            log.warning("delivery worker error: %s", exc)
            db.rollback()
        finally:
            db.close()
        time.sleep(POLL_SECONDS)


def start_worker() -> None:
    """Uruchom listonosza raz na kopię serwera (wołane przy starcie aplikacji)."""
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="delivery-worker", daemon=True)
            _worker.start()
            log.info("delivery worker started (channels: %s)", ", ".join(available_channels()) or "none")


# ---------------------------------------------------------------- nowe kolumny w istniejących bazach
NEW_COLUMNS = {
    "subject": "VARCHAR(300)",
    "body": "TEXT",
    "html": "TEXT",
    "next_attempt_at": "TIMESTAMP",
}


def ensure_delivery_columns(engine) -> None:
    """create_all nie dodaje kolumn do istniejących tabel – dopisujemy brakujące przy starcie."""
    for column, sql_type in NEW_COLUMNS.items():
        try:
            with engine.begin() as conn:  # osobna transakcja na każdą kolumnę (Postgres)
                conn.execute(text(f"ALTER TABLE deliveries ADD COLUMN {column} {sql_type}"))
        except Exception:  # noqa: BLE001 – kolumna już jest
            pass
