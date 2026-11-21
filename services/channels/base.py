"""
Wspólny kształt każdego kanału (mail, SMS, telefon…).

Kanał to mała klasa z jedną metodą send(). Nie wie nic o alertach, regułach ani bazie –
dostaje gotową wiadomość (Message) i ma ją doręczyć. Jeśli się nie uda, rzuca ChannelError,
a "listonosz" (services/delivery.py) spróbuje ponownie później.

Nowy dostawca (np. prawdziwe Twilio zamiast udawanej bramki) = nowa klasa w tym folderze
+ wpis w registry.py. Reszta aplikacji się nie zmienia.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Message:
    to: str                    # adres e-mail albo numer telefonu
    subject: str               # temat (mail); dla SMS/telefonu ignorowany
    body: str                  # treść zwykłym tekstem
    html: str | None = None    # opcjonalnie ładna wersja HTML (mail)


class ChannelError(Exception):
    """Doręczenie się nie udało (np. bramka nie odpowiada). Wysyłka zostanie ponowiona."""


class Channel:
    name: str = "base"

    def send(self, message: Message) -> None:
        raise NotImplementedError
