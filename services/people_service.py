"""
OSOBA 2 – kto ma dostać alert i jakim kanałem.

Zadanie: ludzie z alert.team; dla każdego kanały z reguły skrzyżowane z jego channel_prefs[alert.severity];
uwzględnić quiet_hours (np. SMS tylko 08:00–20:00, inaczej email) i on_call (kanał "phone" tylko do dyżurnego).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Alert
from services.contracts import Recipient


def recipients_for(db: Session, alert: Alert, rule_channels: list[str]) -> list[Recipient]:
    # TODO (Osoba 2): prawdziwe preferencje. Na razie nikt.
    return []
