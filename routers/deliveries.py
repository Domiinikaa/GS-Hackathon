"""
Wysyłka alertów (kanały) i Outbox: co, komu i jakim kanałem wysłaliśmy, z ponawianiem.

  /api/deliveries…        Outbox (lista wysyłek) + testowa wysyłka
  /api/channels…          kanały: stan, przełącznik awarii, udawany telefon, odpowiedzi z telefonu
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Alert, ChannelSetting, Delivery, GatewayMessage
from services.channels import available_channels
from services.contracts import Recipient
from services.delivery import enqueue_deliveries
from services.replies import digits, handle_phone_keypress, handle_sms

router = APIRouter(tags=["Channels & Outbox"])


# ---------------------------------------------------------------- Outbox
@router.get("/api/deliveries")
def list_deliveries(status: Optional[str] = None, alert_id: Optional[int] = None, limit: int = 100,
                    db: Session = Depends(get_db)):
    q = db.query(Delivery)
    if status:
        q = q.filter(Delivery.status == status)
    if alert_id:
        q = q.filter(Delivery.alert_id == alert_id)
    return q.order_by(Delivery.id.desc()).limit(limit).all()


class TestDeliveryRequest(BaseModel):
    """Udawany odbiorca – do testów, zanim recipients_for (Osoba 2) jest w main."""
    channel: str = "email"            # email | sms | phone
    to: str = "kasia@example.com"     # dla sms/phone: numer, np. +48 600 000 001
    name: str = "Kasia"
    alert_id: Optional[int] = None    # brak = najnowszy alert


@router.post("/api/deliveries/test")
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


# ---------------------------------------------------------------- kanały: stan i awaria do demo
@router.get("/api/channels")
def channels(db: Session = Depends(get_db)):
    """Skonfigurowane kanały i czy któryś ma włączoną (udawaną) awarię."""
    down = {s.channel: s.down for s in db.query(ChannelSetting).all()}
    return [{"channel": c, "down": bool(down.get(c, False))} for c in available_channels()]


class OutageRequest(BaseModel):
    down: bool


@router.put("/api/channels/{channel}/outage")
def set_outage(channel: str, req: OutageRequest, db: Session = Depends(get_db)):
    """Demo: "SMS gateway down" – wysyłki tym kanałem się nie udają i są ponawiane, aż awaria minie."""
    if channel not in ("sms", "phone"):
        raise HTTPException(400, "Outage can be simulated for sms and phone (e-mail: stop Mailpit)")
    setting = db.get(ChannelSetting, channel) or ChannelSetting(channel=channel)
    setting.down = req.down
    db.add(setting)
    db.commit()
    return {"channel": channel, "down": setting.down}


# ---------------------------------------------------------------- udawany telefon
@router.get("/api/channels/phones")
def phones(db: Session = Depends(get_db)):
    """Numery, na które coś poszło (SMS/połączenie) – lista "telefonów" w widoku fałszywego telefonu."""
    rows = (db.query(Delivery.to, func.max(Delivery.recipient_name), func.max(Delivery.id))
            .filter(Delivery.channel.in_(["sms", "phone"]))
            .group_by(Delivery.to).order_by(func.max(Delivery.id).desc()).all())
    return [{"number": number, "name": name} for number, name, _ in rows]


@router.get("/api/channels/messages")
def phone_messages(number: str, db: Session = Depends(get_db)):
    """Rozmowa z jednym numerem: SMS-y i połączenia w obie strony, od najstarszych."""
    wanted = digits(number)
    rows = db.query(GatewayMessage).order_by(GatewayMessage.id.desc()).limit(500).all()
    return [m for m in reversed(rows) if digits(m.number) == wanted]


class SmsInbound(BaseModel):
    """Tak wyglądałby webhook od bramki SMS (np. Twilio), gdy człowiek odpisze."""
    from_number: str = Field(..., alias="from", examples=["+48 600 000 001"])
    text: str = Field(..., examples=["ACK 4821"])

    model_config = {"populate_by_name": True}


@router.post("/api/channels/sms/inbound")
def sms_inbound(msg: SmsInbound, db: Session = Depends(get_db)):
    result = handle_sms(db, msg.from_number, msg.text)
    return {"ok": result.ok, "reply": result.message, "alert_id": result.alert_id}


class PhoneInbound(BaseModel):
    from_number: str = Field(..., alias="from", examples=["+48 600 000 002"])
    digit: str = Field("1", examples=["1"])

    model_config = {"populate_by_name": True}


@router.post("/api/channels/phone/inbound")
def phone_inbound(msg: PhoneInbound, db: Session = Depends(get_db)):
    result = handle_phone_keypress(db, msg.from_number, msg.digit)
    return {"ok": result.ok, "reply": result.message, "alert_id": result.alert_id}
