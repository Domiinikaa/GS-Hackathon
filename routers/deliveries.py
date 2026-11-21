"""Wysyłka alertów (kanały) i Outbox: co, komu i jakim kanałem wysłaliśmy, z ponawianiem."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import engine, get_db
from models import Alert, Delivery
from services.channels import available_channels
from services.contracts import Recipient
from services.delivery import ensure_delivery_columns, enqueue_deliveries, start_worker


def _on_startup() -> None:
    ensure_delivery_columns(engine)   # nowe kolumny w istniejących bazach
    start_worker()                     # listonosz w tle – po jednym na kopię serwera


router = APIRouter(prefix="/api/deliveries", tags=["Channels & Outbox"], on_startup=[_on_startup])


@router.get("")
def list_deliveries(status: Optional[str] = None, alert_id: Optional[int] = None, limit: int = 100,
                    db: Session = Depends(get_db)):
    q = db.query(Delivery)
    if status:
        q = q.filter(Delivery.status == status)
    if alert_id:
        q = q.filter(Delivery.alert_id == alert_id)
    return q.order_by(Delivery.id.desc()).limit(limit).all()


@router.get("/channels")
def channels():
    """Które kanały są skonfigurowane (mają dostawcę)."""
    return {"available": available_channels()}


class TestDeliveryRequest(BaseModel):
    """Udawany odbiorca – do testów, zanim recipients_for (Osoba 2) jest w main."""
    channel: str = "email"
    to: str = "kasia@example.com"
    name: str = "Kasia"
    alert_id: Optional[int] = None    # brak = najnowszy alert


@router.post("/test")
def create_test_delivery(req: TestDeliveryRequest, db: Session = Depends(get_db)):
    """TYLKO DO TESTÓW: wysyła wskazany alert do udawanego odbiorcy wybranym kanałem."""
    alert = db.get(Alert, req.alert_id) if req.alert_id else db.query(Alert).order_by(Alert.id.desc()).first()
    if not alert:
        raise HTTPException(404, "No alert – create one with POST /api/alerts/test first")
    created = enqueue_deliveries(db, alert, [Recipient(person_id=None, name=req.name, channel=req.channel, to=req.to)])
    db.commit()
    if not created:
        raise HTTPException(400, "Nothing to send (channel 'ui' or empty address)")
    db.refresh(created[0])
    return created[0]
