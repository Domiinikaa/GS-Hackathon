"""
Wszystkie tabele w bazie. Każda tabela ma właściciela (patrz TEAM.md).
Edytuj TYLKO swoją klasę. Zmiana pola, z którego korzysta ktoś inny = najpierw powiedz zespołowi.

SQLite nie robi migracji: po zmianie pól usuń plik app.db i uruchom backend ponownie.
JSON działa i w SQLite, i w Postgresie.
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from database import Base


# ---------------------------------------------------------------- Osoba 3: wejście
class Source(Base):
    """Program, który wysyła do nas zdarzenia (np. trade-gateway)."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)   # część adresu: /api/ingest/{key}
    name = Column(String(100), nullable=False)             # "trade-gateway"
    team = Column(String(100), nullable=False)             # "Rates"
    kind = Column(String(20), default="webhook")           # webhook | kafka | rabbitmq | logfile
    config = Column(JSON, default=dict)                    # np. {"host": ..., "queue": ...} dla brokerów
    sample_event = Column(JSON, nullable=True)             # wklejony przykład -> podpowiedzi pól w edytorze reguł
    created_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    """Surowe zdarzenie dokładnie tak, jak przyszło. Nie zakładamy żadnego formatu."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True)
    payload = Column(JSON, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------- Osoba 2: reguły i ludzie
class Rule(Base):
    """Kształt pól = frontend/src/rules/ruleTypes.ts (Rule)."""
    __tablename__ = "rules"

    id = Column(String(64), primary_key=True)              # "rates-big-rejections"
    name = Column(String(200), nullable=False)
    team = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True)
    condition = Column(JSON, nullable=False)               # {"and": [{"field","op","value"}, ...]} albo {"or": [...]}
    channels = Column(JSON, default=list)                  # ["email", "ui"]
    title = Column(String(300), nullable=False)            # szablon: "Rejected {{payload.currency}}"
    body = Column(Text, nullable=True)
    severity = Column(String(20), default="warning")       # info | warning | critical
    color = Column(String(20), default="amber")
    group_by = Column(String(200), nullable=True)          # np. "instrument"
    group_window_s = Column(Integer, nullable=True)        # np. 300
    runbook_id = Column(Integer, ForeignKey("runbooks.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Person(Base):
    """Człowiek i jego preferencje kanałów."""
    __tablename__ = "people"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)             # "Anna"
    team = Column(String(100), nullable=False)             # "Payments"
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    on_call = Column(Boolean, default=False)
    # Który kanał przy jakiej ważności, np. {"critical": ["phone","sms"], "warning": ["email"], "info": ["ui"]}
    channel_prefs = Column(JSON, default=dict)
    # Godziny pracy, np. {"sms": {"from": "08:00", "to": "20:00", "else": "email"}}
    quiet_hours = Column(JSON, default=dict)


# ---------------------------------------------------------------- Osoba 4: runbooki
class Runbook(Base):
    __tablename__ = "runbooks"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)             # "settlement-timeout"
    format = Column(String(20), default="text")            # yaml | markdown | text | link
    raw = Column(Text, nullable=False)                     # dokładnie to, co wkleił człowiek
    steps = Column(JSON, default=list)                     # po parsowaniu: [{"text","action","params","approval"}]
    matches = Column(JSON, nullable=True)                  # opcjonalnie: do jakich zdarzeń pasuje sam z siebie


# ---------------------------------------------------------------- Osoba 1: alerty
class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    rule_id = Column(String(64), ForeignKey("rules.id"), nullable=False)
    team = Column(String(100), nullable=False)
    dedup_key = Column(String(300), index=True, nullable=False)  # te same błędy -> ten sam alert
    title = Column(String(300), nullable=False)
    body = Column(Text, nullable=True)
    severity = Column(String(20), default="warning")
    color = Column(String(20), default="amber")
    status = Column(String(20), default="open")            # open | acknowledged | resolved
    count = Column(Integer, default=1)                     # licznik deduplikacji
    last_event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    steps = Column(JSON, default=list)                     # kroki runbooka z podstawionymi wartościami
    history = Column(JSON, default=list)                   # [{"at","who","what"}] – kto co zrobił
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------- Osoba 3: wysyłka
class Delivery(Base):
    """Jedna wysyłka jednego alertu jednej osobie jednym kanałem (Outbox)."""
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    channel = Column(String(20), nullable=False)           # email | sms | phone | ui
    to = Column(String(200), nullable=True)                # adres / numer
    status = Column(String(20), default="pending")         # pending | sent | failed
    attempts = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
