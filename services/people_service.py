"""
OSOBA 2 – kto ma dostać alert i jakim kanałem.

Zasady (w tej kolejności):
1. Odbiorcy: rule.team może być nazwą zespołu ("Payments") albo osoby ("Anna").
   Jeśli istnieje osoba o takim imieniu, alert idzie tylko do niej, w przeciwnym razie do całego zespołu.
2. Kanał "ui" to kanał zespołowy (live feed), więc zawsze jest jeden wpis na alert, a nie po jednym na osobę.
3. Kanały osobiste = kanały reguły ∩ channel_prefs[severity] danej osoby.
   Osoba bez preferencji dla tej wagi albo z pustym przecięciem dostaje kanały z reguły (alert nie może zginąć).
4. "phone" tylko do dyżurnego (on_call). Pozostali dostają zamiast tego SMS.
5. quiet_hours: {"sms": {"from": "08:00", "to": "20:00", "else": "email"}} oznacza, że SMS idzie tylko w tym oknie,
   a poza nim kanał zastępczy. Okno przez północ (22:00–06:00) też działa.
6. Brak adresu (SMS bez telefonu, e-mail bez adresu) -> kanał zastępczy, żeby wiadomość dokądś dotarła.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Iterable

from sqlalchemy.orm import Session

from models import Alert, Person
from services.contracts import Recipient

PERSONAL_CHANNELS = ("phone", "sms", "email")
# Dokąd przejść, gdy kanał jest niedostępny (brak adresu itp.)
FALLBACK = {"phone": "sms", "sms": "email", "email": None}


@dataclass
class PlannedRecipient:
    """Recipient + powód decyzji (do podglądu w UI: „Anna → email, bo poza godzinami SMS”)."""
    recipient: Recipient
    reason: str


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def in_window(now: time, start: str, end: str) -> bool:
    """Czy `now` mieści się w oknie [start, end). Obsługuje okna przez północ."""
    a, b = _parse_hhmm(start), _parse_hhmm(end)
    if a == b:
        return True
    if a < b:
        return a <= now < b
    return now >= a or now < b


def _address(person: Person, channel: str) -> str | None:
    if channel in ("sms", "phone"):
        return person.phone or None
    if channel == "email":
        return person.email or None
    return None


def _resolve_channel(person: Person, channel: str, now: time) -> tuple[str | None, list[str]]:
    """Zwraca (ostateczny kanał albo None, notatki), stosując on-call, godziny ciszy i brak adresu."""
    notes: list[str] = []
    seen: set[str] = set()
    current: str | None = channel
    while current and current not in seen:
        seen.add(current)
        if current == "phone" and not person.on_call:
            notes.append("phone only for on-call → sms")
            current = "sms"
            continue
        window = (person.quiet_hours or {}).get(current)
        if window and window.get("from") and window.get("to") and not in_window(now, window["from"], window["to"]):
            alt = window.get("else") or FALLBACK.get(current)
            notes.append(f"{current} only {window['from']}–{window['to']} → {alt or 'skip'}")
            current = alt
            continue
        if _address(person, current) is None:
            alt = FALLBACK.get(current)
            notes.append(f"no address for {current} → {alt or 'skip'}")
            current = alt
            continue
        return current, notes
    return None, notes


def _audience(db: Session, target: str) -> list[Person]:
    people = db.query(Person).filter(Person.name == target).all()
    if people:
        return people
    return db.query(Person).filter(Person.team == target).all()


def plan_recipients(
    db: Session,
    target: str,
    severity: str,
    rule_channels: Iterable[str],
    now: datetime | None = None,
) -> list[PlannedRecipient]:
    """Serce logiki: kto, jakim kanałem i dlaczego. Używane przez pipeline i przez podgląd w UI."""
    now_t = (now or datetime.now()).time()
    rule_channels = list(dict.fromkeys(rule_channels or []))
    out: list[PlannedRecipient] = []

    if "ui" in rule_channels:
        out.append(PlannedRecipient(
            Recipient(person_id=None, name=f"team:{target}", channel="ui", to=None),  # type: ignore[arg-type]
            "live feed for the whole team",
        ))

    personal_rule = [c for c in rule_channels if c in PERSONAL_CHANNELS]
    if not personal_rule:
        return out

    seen: set[tuple[int, str]] = set()
    for person in _audience(db, target):
        prefs = (person.channel_prefs or {}).get(severity)
        wanted = [c for c in personal_rule if c in prefs] if prefs else []
        base_reason = f"prefers {', '.join(prefs)} for {severity}" if prefs else f"no preference for {severity}"
        if not wanted:
            wanted = personal_rule
            base_reason += "; using rule channels"

        for channel in wanted:
            final, notes = _resolve_channel(person, channel, now_t)
            if final is None or (person.id, final) in seen:
                continue
            seen.add((person.id, final))
            out.append(PlannedRecipient(
                Recipient(person_id=person.id, name=person.name, channel=final, to=_address(person, final)),
                "; ".join([base_reason, *notes]),
            ))
    return out


def recipients_for(db: Session, alert: Alert, rule_channels: list[str]) -> list[Recipient]:
    return [p.recipient for p in plan_recipients(db, alert.team, alert.severity, rule_channels)]
