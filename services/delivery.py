"""
OSOBA 3 – wysyłka: zapis do Outboxa i (udawane) kanały z ponawianiem.

Zadanie:
- enqueue_deliveries: jeden wiersz Delivery na odbiorcę, status "pending"
- worker (np. pętla w tle co 1 s): bierze "pending"/"failed" z attempts < 5, wywołuje kanał,
  ustawia "sent" albo "failed" + last_error. Nic nie ginie, bo wszystko leży w tabeli.
- kanały to małe klasy z metodą send(to, alert) – prawdziwy dostawca = podmiana jednej klasy.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Alert, Delivery
from services.contracts import Recipient


def enqueue_deliveries(db: Session, alert: Alert, recipients: list[Recipient]) -> list[Delivery]:
    # TODO (Osoba 3): zapisać Delivery dla każdego odbiorcy
    return []
