"""
OSOBA 1 – tworzenie i aktualizacja alertów (deduplikacja).

Ten sam dedup_key i alert nie jest resolved -> count += 1, last_seen = teraz.
W przeciwnym razie nowy alert. Potem powiadomienie live feed (services/live.py).

Wszystko w JEDNYM poleceniu do bazy ("wstaw albo zwiększ licznik", INSERT ... ON CONFLICT DO UPDATE),
żeby kilka kopii serwera naraz nie tworzyło duplikatów ani nie gubiło zliczeń.
Wymaga częściowego unikalnego indeksu uq_alerts_open_dedup (models.Alert.__table_args__).
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from models import Alert
from services import live
from services.contracts import Match

log = logging.getLogger("alerts")

OPEN_DEDUP_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_open_dedup "
    "ON alerts (dedup_key) WHERE status != 'resolved'"
)


def ensure_open_dedup_index(engine) -> bool:
    """
    Zakłada indeks w istniejących bazach (create_all dodaje go tylko do nowych tabel).
    Wołane raz przy starcie serwera. Gdy w bazie są już duplikaty, indeksu nie da się założyć –
    serwer działa dalej, a upsert_alert przechodzi na wolniejszą, nieatomową ścieżkę.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(OPEN_DEDUP_INDEX_SQL))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("alerts: could not create uq_alerts_open_dedup (duplicate open alerts?): %s", exc)
        return False


def _insert_for(db: Session):
    """INSERT z obsługą ON CONFLICT – osobny dla każdej bazy, ale z tym samym API."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        return None
    return insert


def upsert_alert(db: Session, match: Match) -> Alert | None:
    now = datetime.utcnow()
    new_row = dict(
        rule_id=match.rule_id,
        team=match.team,
        dedup_key=match.dedup_key,
        title=match.title,
        body=match.body,
        severity=match.severity,
        color=match.color,
        status="open",
        count=1,
        last_event_id=match.event_id,
        steps=match.steps,
        history=[{"at": now.isoformat(), "who": "system", "what": "created"}],
        first_seen=now,
        last_seen=now,
    )

    alert_id = _atomic_upsert(db, new_row, match, now)
    if alert_id is None:
        alert_id = _fallback_upsert(db, new_row, match, now)

    # populate_existing: jeśli ten alert jest już w pamięci sesji, nadpisz go świeżymi danymi z bazy
    alert = db.get(Alert, alert_id, populate_existing=True)

    # Powiadom przeglądarki na żywo (przed commit – patrz services/live.py)
    live.publish(alert)
    return alert


def _atomic_upsert(db: Session, new_row: dict, match: Match, now: datetime) -> int | None:
    """
    Jedno polecenie: wstaw nowy alert, a jeśli istnieje już nierozwiązany z tym dedup_key –
    zwiększ mu licznik W BAZIE (count = alerts.count + 1, nie w Pythonie).
    Zwraca id alertu albo None, gdy baza tego nie obsługuje (brak indeksu / inna baza).
    """
    insert = _insert_for(db)
    if insert is None:
        return None
    stmt = (
        insert(Alert)
        .values(**new_row)
        .on_conflict_do_update(
            index_elements=[Alert.dedup_key],
            index_where=Alert.status != "resolved",
            set_={"count": Alert.count + 1, "last_seen": now, "last_event_id": match.event_id},
        )
        .returning(Alert.id)
    )
    try:
        with db.begin_nested():  # savepoint: błąd nie psuje reszty transakcji
            return db.execute(stmt).scalar_one()
    except DBAPIError as exc:
        log.warning("alerts: atomic upsert unavailable, using fallback: %s", exc.orig)
        return None


def _fallback_upsert(db: Session, new_row: dict, match: Match, now: datetime) -> int:
    """Stara ścieżka "sprawdź, potem zapisz" – tylko gdy indeksu nie da się założyć. Nieodporna na wyścigi."""
    alert = (
        db.query(Alert)
        .filter(Alert.dedup_key == match.dedup_key, Alert.status != "resolved")
        .first()
    )
    if alert:
        alert.count = Alert.count + 1  # nawet tutaj liczymy w bazie, nie w Pythonie
        alert.last_seen = now
        alert.last_event_id = match.event_id
    else:
        alert = Alert(**new_row)
        db.add(alert)
    db.flush()
    return alert.id
