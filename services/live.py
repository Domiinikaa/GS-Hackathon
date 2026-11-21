"""
Live feed alertów (Server-Sent Events: serwer sam wypycha zmiany do przeglądarek).

Dwa tryby, wybierane automatycznie po adresie bazy (DATABASE_URL):

  in-memory        (SQLite, laptop)   publish() od razu wrzuca alert do skrzynek przeglądarek
                                      podłączonych do TEGO serwera. Działa tylko z jedną kopią serwera.

  postgres-notify  (Postgres, prod)   publish() wysyła do bazy NOTIFY alerts '<id>'. Każda kopia serwera
                                      ma wątek, który słucha (LISTEN alerts), wczytuje alert z bazy
                                      i wrzuca go do skrzynek SWOICH przeglądarek. Działa na wielu kopiach,
                                      bo Postgres rozgłasza ogłoszenie do wszystkich.
                                      Postgres wysyła NOTIFY dopiero po commit – nie pokażemy alertu,
                                      którego zapis się nie udał.

Każda otwarta przeglądarka = jedna skrzynka (asyncio.Queue) + pętla zdarzeń, w której ta skrzynka żyje.
"""
from __future__ import annotations

import asyncio
import json
import logging
import select
import threading
import time

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import object_session

from database import DATABASE_URL, SessionLocal
from models import Alert

log = logging.getLogger("live")

CHANNEL = "alerts"
USE_POSTGRES = DATABASE_URL.startswith("postgresql")

_listeners: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
_lock = threading.Lock()          # listę zmieniają różne wątki – pilnujemy kolejki
_listener_thread: threading.Thread | None = None


def mode() -> str:
    return "postgres-notify" if USE_POSTGRES else "in-memory"


# ---------------------------------------------------------------- przeglądarki: zapis / wypis
def subscribe() -> asyncio.Queue:
    """Przeglądarka się podłącza: dostaje własną skrzynkę."""
    _ensure_listener()
    queue: asyncio.Queue = asyncio.Queue()
    with _lock:
        _listeners.append((asyncio.get_running_loop(), queue))
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    """Przeglądarka się rozłączyła (zamknięta karta): usuwamy jej skrzynkę."""
    with _lock:
        _listeners[:] = [(loop, q) for loop, q in _listeners if q is not queue]


# ---------------------------------------------------------------- nadawanie
def publish(alert: Alert) -> None:
    """
    Ogłoś, że alert się zmienił. Wołać PRZED db.commit() – w trybie Postgres
    ogłoszenie jest częścią transakcji i wychodzi dopiero razem z zapisem.
    """
    if USE_POSTGRES:
        session = object_session(alert)
        if session is not None:
            session.execute(text("SELECT pg_notify(:channel, :payload)"),
                            {"channel": CHANNEL, "payload": str(alert.id)})
    else:
        _broadcast(_serialize(alert))


def _serialize(alert: Alert) -> str:
    """Alert -> tekst JSON (wszystkie kolumny; daty jako tekst)."""
    data = {c.name: getattr(alert, c.name) for c in Alert.__table__.columns}
    return json.dumps(jsonable_encoder(data))


def _broadcast(message: str) -> None:
    """Wrzuć wiadomość do skrzynek wszystkich przeglądarek tego serwera."""
    with _lock:
        targets = list(_listeners)
    for loop, queue in targets:
        try:
            # skrzynka żyje w innym wątku – prosimy jej pętlę, żeby sama ją wrzuciła
            loop.call_soon_threadsafe(queue.put_nowait, message)
        except RuntimeError:
            pass  # pętla już zamknięta (przeglądarka właśnie się rozłączyła)


# ---------------------------------------------------------------- tryb Postgres: nasłuch w tle
def _ensure_listener() -> None:
    """Uruchom wątek LISTEN raz na serwer, przy pierwszej podłączonej przeglądarce."""
    global _listener_thread
    if not USE_POSTGRES:
        return
    with _lock:
        if _listener_thread is None or not _listener_thread.is_alive():
            _listener_thread = threading.Thread(target=_listen_forever, name="alerts-listen", daemon=True)
            _listener_thread.start()


def _listen_forever() -> None:
    import psycopg2
    import psycopg2.extensions

    dsn = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://", 1)
    while True:  # po zerwaniu połączenia z bazą – łączymy się ponownie
        try:
            conn = psycopg2.connect(dsn)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            conn.cursor().execute(f"LISTEN {CHANNEL};")
            log.info("live: listening on Postgres channel '%s'", CHANNEL)
            while True:
                # czekaj max 5 s na ogłoszenie, potem sprawdź znowu (pozwala wykryć zerwane połączenie)
                if select.select([conn], [], [], 5) == ([], [], []):
                    continue
                conn.poll()
                while conn.notifies:
                    _on_notify(conn.notifies.pop(0).payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("live: Postgres listener error (%s), reconnecting in 2 s", exc)
            time.sleep(2)


def _on_notify(payload: str) -> None:
    """Ogłoszenie 'alert <id> się zmienił' – wczytaj świeżą wersję i roześlij."""
    db = SessionLocal()
    try:
        alert = db.get(Alert, int(payload))
        if alert is not None:
            _broadcast(_serialize(alert))
    finally:
        db.close()
