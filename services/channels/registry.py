"""
Spis kanałów: nazwa kanału → klasa, która go obsługuje.

Wybór dostawcy przez zmienną środowiskową, np. EMAIL_PROVIDER=smtp, SMS_PROVIDER=fake.
Dodanie dostawcy = jedna linijka w PROVIDERS (np. "twilio": TwilioSms).
Kanał, którego tu nie ma (np. jeszcze niezrobiony "sms"), jest pomijany – jego wysyłki
czekają w Outboxie jako "pending" i wyjdą, gdy kanał zostanie dodany.
"""
from __future__ import annotations

import os

from services.channels.base import Channel
from services.channels.email_smtp import SmtpEmail

# kanał → {nazwa dostawcy: klasa}
PROVIDERS: dict[str, dict[str, type[Channel]]] = {
    "email": {"smtp": SmtpEmail},
    # "sms":   {"fake": FakeSms, "twilio": TwilioSms},      ← następny krok
    # "phone": {"fake": FakePhone, "twilio": TwilioVoice},
}

DEFAULT_PROVIDER = {"email": "smtp", "sms": "fake", "phone": "fake"}


def get_channel(name: str) -> Channel | None:
    """Zwraca obiekt kanału albo None, jeśli kanału / dostawcy nie ma."""
    providers = PROVIDERS.get(name)
    if not providers:
        return None
    provider = os.getenv(f"{name.upper()}_PROVIDER", DEFAULT_PROVIDER.get(name, ""))
    cls = providers.get(provider)
    return cls() if cls else None


def available_channels() -> list[str]:
    return [name for name in PROVIDERS if get_channel(name) is not None]
