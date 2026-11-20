"""
"Gniazdka" między osobami. Tę strukturę zmieniamy tylko po ustaleniu z całym zespołem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Match:
    """Wynik silnika reguł (Osoba 4) -> wejście do alertów (Osoba 1)."""
    rule_id: str
    team: str
    event_id: int
    dedup_key: str          # np. "rates-big-rejections|T-998877"; ten sam klucz = ten sam alert (+1 do licznika)
    title: str              # szablon już wypełniony wartościami ze zdarzenia
    body: str | None
    severity: str
    color: str
    channels: list[str]
    steps: list[dict[str, Any]] = field(default_factory=list)  # kroki runbooka z podstawionymi wartościami


@dataclass
class Recipient:
    """Wynik preferencji ludzi (Osoba 2) -> wejście do wysyłki (Osoba 3)."""
    person_id: int
    name: str
    channel: str            # email | sms | phone | ui
    to: str | None          # adres e-mail / numer telefonu; None dla "ui"
