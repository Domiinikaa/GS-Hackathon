"""
Odpowiedzi na alert z telefonu (kartka 2.6: "approve … by replying to the alert").

SMS:   "ACK 4821"      → przejmij alert (acknowledge)
       "YES 4821"      → zatwierdź pierwszy krok runbooka, który czeka na zgodę (approve)
       "RESOLVE 4821"  → zamknij alert
Telefon: wciśnięcie "1" w trakcie połączenia → acknowledge.

Bezpieczeństwo – zanim cokolwiek zrobimy, sprawdzamy:
  * kod istnieje i należy do wysyłki, która poszła NA TEN numer (nikt obcy nie zatwierdzi cudzym kodem),
  * alert nie jest rozwiązany,
  * akcję wykonują TE SAME funkcje co przyciski na stronie – te same zasady (np. "najpierw zgoda").
W historii alertu zostaje: "approved by Anna (SMS)".

Każda odpowiedź dostaje SMS zwrotny z wynikiem ("OK – alert 8 acknowledged" / powód odmowy).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Alert, Delivery
from services.channels.fake_gateway import record

COMMANDS = {"ACK": "ack", "OK": "ack", "YES": "approve", "Y": "approve", "APPROVE": "approve",
            "RESOLVE": "resolve", "DONE": "resolve"}


@dataclass
class ReplyActor:
    """Udaje zalogowanego użytkownika dla funkcji z routers/alerts.py (czytają .uname i .person_id)."""
    uname: str
    person_id: int | None = None      # osoba, do której poszedł SMS – zatwierdzać kroki może tylko lead


@dataclass
class ReplyResult:
    ok: bool
    message: str                      # tekst SMS-a zwrotnego
    alert_id: int | None = None


def digits(number: str) -> str:
    return re.sub(r"\D", "", number or "")


def handle_sms(db: Session, from_number: str, text: str) -> ReplyResult:
    record("sms", "in", from_number, text)
    words = (text or "").strip().upper().split()
    if len(words) < 2 or words[0] not in COMMANDS:
        return _answer(from_number, ReplyResult(False, "Sorry, not understood. Reply e.g. ACK 4821 or YES 4821."))
    action, code = COMMANDS[words[0]], words[1]

    delivery = _find_delivery(db, from_number, code=code)
    if not delivery:
        return _answer(from_number, ReplyResult(False, f"Code {code} is not valid for this number."))
    return _answer(from_number, _apply(db, delivery, action, "SMS"))


def handle_phone_keypress(db: Session, from_number: str, digit: str) -> ReplyResult:
    record("phone", "in", from_number, f"pressed {digit}")
    if digit.strip() != "1":
        return ReplyResult(False, "Only 1 (acknowledge) is supported.")
    delivery = _find_delivery(db, from_number, channel="phone")
    if not delivery:
        return ReplyResult(False, "No recent call to this number.")
    result = _apply(db, delivery, "ack", "phone")
    record("phone", "out", from_number, result.message)   # "głos" potwierdza w trakcie połączenia
    return result


def _find_delivery(db: Session, from_number: str, code: str | None = None, channel: str | None = None):
    """Wysyłka, która poszła na ten numer (i ma ten kod / jest najnowszym połączeniem)."""
    q = db.query(Delivery).filter(Delivery.status == "sent")
    q = q.filter(Delivery.reply_code == code) if code else q.filter(Delivery.channel == channel)
    for d in q.order_by(Delivery.id.desc()).limit(50):
        if digits(d.to) == digits(from_number):
            return d
    return None


def _apply(db: Session, delivery: Delivery, action: str, via: str) -> ReplyResult:
    # Import tutaj, nie na górze: routers.alerts importuje services, więc unikamy importu w kółko
    from routers.alerts import _change_status, _update_step

    alert = db.get(Alert, delivery.alert_id)
    if not alert:
        return ReplyResult(False, "Alert no longer exists.")
    actor = ReplyActor(uname=f"{delivery.recipient_name or delivery.to} ({via})", person_id=delivery.person_id)
    try:
        if action == "ack":
            _change_status(db, alert.id, "acknowledged", ["open"], actor)
            return ReplyResult(True, f"OK - alert {alert.id} acknowledged. {alert.title}", alert.id)
        if action == "resolve":
            _change_status(db, alert.id, "resolved", ["open", "acknowledged"], actor)
            return ReplyResult(True, f"OK - alert {alert.id} resolved.", alert.id)
        # approve: pierwszy krok, który wymaga zgody i jej jeszcze nie ma
        step_index = next((i for i, s in enumerate(alert.steps or [])
                           if s.get("approval") == "required" and not s.get("approved_by")), None)
        if step_index is None:
            return ReplyResult(False, f"Alert {alert.id} has no step waiting for approval.", alert.id)
        text = (alert.steps[step_index] or {}).get("text", "")
        _update_step(db, alert.id, step_index, actor, "approve")
        return ReplyResult(True, f"OK - step {step_index + 1} approved: {text}"[:160], alert.id)
    except HTTPException as exc:      # te same odmowy co na stronie (np. alert już rozwiązany)
        db.rollback()
        return ReplyResult(False, f"Alert {alert.id}: {exc.detail}", alert.id)


def _answer(number: str, result: ReplyResult) -> ReplyResult:
    record("sms", "out", number, result.message)
    return result
