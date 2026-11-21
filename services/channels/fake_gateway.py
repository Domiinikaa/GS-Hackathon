"""
Udawana bramka SMS i telefoniczna (kartka 2.3: "a fake SMS/phone gateway that logs or shows deliveries").

"Wysłanie" = zapis w tabeli gateway_messages. Widok "fałszywego telefonu" na stronie Outbox pokazuje
te wiadomości jak w komunikatorze i pozwala na nie odpowiedzieć (services/replies.py).

Prawdziwy dostawca, np. Twilio, to osobna klasa obok – ok. 20 linijek:
    POST https://api.twilio.com/2010-04-01/Accounts/<SID>/Messages.json  (From, To, Body + klucz API)
i SMS_PROVIDER=twilio w ustawieniach. Odpowiedzi Twilio wysyła webhookiem na /api/channels/sms/inbound.
"""
from __future__ import annotations

from database import SessionLocal
from models import ChannelSetting, GatewayMessage
from services.channels.base import Channel, ChannelError, Message


def is_down(channel: str) -> bool:
    db = SessionLocal()
    try:
        setting = db.get(ChannelSetting, channel)
        return bool(setting and setting.down)
    finally:
        db.close()


def record(channel: str, direction: str, number: str, body: str, delivery_id: int | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(GatewayMessage(channel=channel, direction=direction, number=number, body=body, delivery_id=delivery_id))
        db.commit()
    finally:
        db.close()


class _FakeGateway(Channel):
    def send(self, message: Message) -> None:
        if is_down(self.name):
            raise ChannelError(f"fake {self.name} gateway is down (simulated outage)")
        record(self.name, "out", message.to, message.body, message.delivery_id)


class FakeSms(_FakeGateway):
    name = "sms"


class FakePhone(_FakeGateway):
    """Połączenie głosowe: treść to tekst, który syntezator mowy przeczytałby przez telefon."""
    name = "phone"
