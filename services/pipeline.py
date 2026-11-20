"""
Droga jednego zdarzenia przez system. Plik wspólny – nie zmieniaj bez ustalenia z zespołem.

    zdarzenie (Osoba 3: /api/ingest)
      -> evaluate(event, rules)          -> list[Match]      services/rules_engine.py   (Osoba 4)
      -> upsert_alert(db, match)         -> Alert            services/alert_service.py  (Osoba 1)
      -> recipients_for(db, alert)       -> list[Recipient]  services/people_service.py (Osoba 2)
      -> enqueue_deliveries(db, alert, recipients) -> list[Delivery]  services/delivery.py (Osoba 3)

Dopóki ktoś nie napisze swojej funkcji, jego stub zwraca pustą listę / None i reszta działa dalej.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Event, Rule
from services.alert_service import upsert_alert
from services.delivery import enqueue_deliveries
from services.people_service import recipients_for
from services.rules_engine import evaluate


def process_event(db: Session, event: Event) -> list[int]:
    """Zwraca id alertów, które to zdarzenie utworzyło lub zaktualizowało."""
    rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()
    alert_ids: list[int] = []
    for match in evaluate(event, rules):
        alert = upsert_alert(db, match)
        if alert is None:
            continue
        alert_ids.append(alert.id)
        recipients = recipients_for(db, alert, match.channels)
        enqueue_deliveries(db, alert, recipients)
    db.commit()
    return alert_ids
