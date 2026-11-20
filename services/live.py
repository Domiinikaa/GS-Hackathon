"""
OSOBA 1 – live feed alertów (Server-Sent Events, push zamiast odświeżania strony).

Pomysł: lista kolejek asyncio, po jednej na każdą otwartą przeglądarkę.
publish() wrzuca alert do wszystkich, endpoint /api/alerts/stream czyta ze swojej kolejki.
Uwaga: pipeline działa w wątku (zwykłe def), więc publish musi użyć loop.call_soon_threadsafe.
"""


def publish(alert_dict: dict) -> None:
    # TODO (Osoba 1)
    pass
