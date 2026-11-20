"""
OSOBA 1 – tworzenie i aktualizacja alertów.

Zadanie: jeśli istnieje otwarty alert z tym samym match.dedup_key -> count += 1, last_seen = teraz.
W przeciwnym razie nowy alert. Potem powiadomić live feed (services/live.py).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Alert
from services.contracts import Match


def upsert_alert(db: Session, match: Match) -> Alert | None:
    # TODO (Osoba 1): deduplikacja + zapis + live.publish(...)
    return None
