"""
OSOBA 1 – tworzenie i aktualizacja alertów.

Zadanie: jeśli istnieje otwarty alert z tym samym match.dedup_key -> count += 1, last_seen = teraz.
W przeciwnym razie nowy alert. Potem powiadomić live feed (services/live.py).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from models import Alert
from services import live
from services.contracts import Match


def upsert_alert(db: Session, match: Match) -> Alert | None:
    now = datetime.utcnow()

    # 1) Pytanie: czy jest już niezamknięty alert z tym samym odciskiem?
    alert = (
        db.query(Alert)
        .filter(Alert.dedup_key == match.dedup_key)
        .filter(Alert.status != "resolved")
        .first()
    )

    if alert:
        # 2a) TAK → to powtórka. Licznik +1, zapamiętaj kiedy i które zdarzenie.
        alert.count += 1
        alert.last_seen = now
        alert.last_event_id = match.event_id
    else:
        # 2b) NIE → nowy alert, wszystkie dane bierzemy z paczki od Osoby 4.
        alert = Alert(
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
        db.add(alert)

    # 3) Wyślij do bazy, żeby alert dostał numer (id). Zatwierdzi to pipeline (commit).
    db.flush()

    # 4) Powiadom przeglądarki na żywo (przed commit – patrz services/live.py)
    live.publish(alert)
    return alert