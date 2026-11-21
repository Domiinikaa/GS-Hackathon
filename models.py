from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Float, JSON, String, Text, text
from sqlalchemy.orm import relationship
from database import Base


# --- Authentication & Administration Models ---

class Department(Base):
    """
    Company departments managed dynamically by the Administrator.
    Administrators can add, edit, and remove departments at any time.
    """
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """
    User entity with role-based attributes and personal data ownership.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    uname = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    nrtel = Column(String(30), nullable=True)
    dzial = Column(String(100), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Personal items owned by this user
    items = relationship("Item", back_populates="owner", cascade="all, delete-orphan")

    # Invite codes created by this administrator
    created_invites = relationship("InviteCode", foreign_keys="InviteCode.created_by_id", back_populates="created_by")
    # Invite code used by this user to register
    used_invite = relationship("InviteCode", foreign_keys="InviteCode.used_by_id", back_populates="used_by", uselist=False)


class InviteCode(Base):
    """
    One-time invite codes generated exclusively by Administrators.
    Required for new user registration. Can grant Administrator privileges.
    """
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, index=True, nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    is_admin_invite = Column(Boolean, default=False, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    used_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_id], back_populates="created_invites")
    used_by = relationship("User", foreign_keys=[used_by_id], back_populates="used_invite")


class Item(Base):
    """
    User panel record / asset position model.
    Scoped to the owner user via user_id.
    """
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(100), nullable=False)
    category = Column(String(50), default="General")
    value = Column(Float, default=0.0)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="items")


# --- Alerting & Incident Response Models (from feature/rules-ui) ---

class Source(Base):
    """Programs and services streaming events to the ingest endpoint."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)   # /api/ingest/{key}
    name = Column(String(100), nullable=False)             # e.g. "trade-gateway"
    team = Column(String(100), nullable=False)             # e.g. "Rates"
    kind = Column(String(20), default="webhook")           # webhook | kafka | rabbitmq | logfile
    config = Column(JSON, default=dict)                    # broker connection options
    sample_event = Column(JSON, nullable=True)             # sample payload for rule hints
    created_at = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    """Raw incoming event exactly as received."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True)
    payload = Column(JSON, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow, index=True)


class Rule(Base):
    """Evaluation rules for event filtering and alerting."""
    __tablename__ = "rules"

    id = Column(String(64), primary_key=True)              # e.g. "rates-big-rejections"
    name = Column(String(200), nullable=False)
    team = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True)
    condition = Column(JSON, nullable=False)               # {"and": [{"field","op","value"}, ...]}
    channels = Column(JSON, default=list)                  # ["email", "ui", "sms"]
    title = Column(String(300), nullable=False)            # template: "Rejected {{payload.currency}}"
    body = Column(Text, nullable=True)
    severity = Column(String(20), default="warning")       # info | warning | critical
    color = Column(String(20), default="amber")
    group_by = Column(String(200), nullable=True)          # e.g. "instrument"
    group_window_s = Column(Integer, nullable=True)        # aggregation window in seconds
    runbook_id = Column(Integer, ForeignKey("runbooks.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Person(Base):
    """Employee notification and escalation preferences."""
    __tablename__ = "people"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)             # "Anna"
    team = Column(String(100), nullable=False)             # "Payments"
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    on_call = Column(Boolean, default=False)
    channel_prefs = Column(JSON, default=dict)             # {"critical": ["phone","sms"], ...}
    quiet_hours = Column(JSON, default=dict)               # {"sms": {"from": "08:00", "to": "20:00"}}
    role = Column(String(20), nullable=False, default="member", server_default="member")  # member | lead (approves risky steps)


class Runbook(Base):
    """Incident remediation runbooks."""
    __tablename__ = "runbooks"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)             # "settlement-timeout"
    format = Column(String(20), default="text")            # yaml | markdown | text | link
    raw = Column(Text, nullable=False)                     # author content
    steps = Column(JSON, default=list)                     # parsed steps
    matches = Column(JSON, nullable=True)                  # automatic event matching criteria


class Alert(Base):
    """Active, acknowledged, or resolved alerts."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    rule_id = Column(String(64), ForeignKey("rules.id"), nullable=False)
    team = Column(String(100), nullable=False)
    dedup_key = Column(String(300), index=True, nullable=False)  # deduplication key
    title = Column(String(300), nullable=False)
    body = Column(Text, nullable=True)
    severity = Column(String(20), default="warning")
    color = Column(String(20), default="amber")
    status = Column(String(20), default="open")            # open | acknowledged | resolved
    count = Column(Integer, default=1)                     # deduplication counter
    last_event_id = Column(Integer, ForeignKey("events.id"), nullable=True)
    steps = Column(JSON, default=list)                     # runbook steps with substituted variables
    history = Column(JSON, default=list)                   # [{"at","who","what"}]
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, index=True)

    # Zasada w bazie: jeden dedup_key = najwyżej jeden NIEROZWIĄZANY alert.
    # Chroni przed duplikatami, gdy kilka kopii serwera dostanie to samo zdarzenie naraz.
    # Dla istniejących baz indeks zakłada services/alert_service.ensure_open_dedup_index().
    __table_args__ = (
        Index("uq_alerts_open_dedup", "dedup_key", unique=True,
              sqlite_where=text("status != 'resolved'"),
              postgresql_where=text("status != 'resolved'")),
    )


class Delivery(Base):
    """Outbox notification delivery records."""
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=True)
    channel = Column(String(20), nullable=False)           # email | sms | phone | ui
    to = Column(String(200), nullable=True)                # address or number
    status = Column(String(20), default="pending")         # pending | sending | sent | failed | dead
    attempts = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    # Treść przygotowana przy zapisie (services/channels/messages.py) – Outbox pokazuje dokładnie to, co poszło
    subject = Column(String(300), nullable=True)
    body = Column(Text, nullable=True)
    html = Column(Text, nullable=True)
    # Kiedy listonosz może (ponownie) spróbować; przy "sending" = do kiedy wysyłka jest zarezerwowana
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    recipient_name = Column(String(100), nullable=True)    # "Anna" – do Outboxa i do historii przy odpowiedzi
    reply_code = Column(String(8), nullable=True, index=True)  # kod w SMS-ie: "odpowiedz ACK 4821"


class GatewayMessage(Base):
    """
    Udawana bramka SMS / telefon: wszystko, co "wyszło" do telefonów i co z nich "przyszło".
    Prawdziwa bramka (np. Twilio) trzymałaby to u siebie – tu pokazujemy to w widoku "fałszywego telefonu".
    """
    __tablename__ = "gateway_messages"

    id = Column(Integer, primary_key=True)
    channel = Column(String(20), nullable=False)           # sms | phone
    direction = Column(String(10), nullable=False)         # out (do człowieka) | in (odpowiedź człowieka)
    number = Column(String(50), nullable=False, index=True)
    body = Column(Text, nullable=False)
    delivery_id = Column(Integer, ForeignKey("deliveries.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ChannelSetting(Base):
    """Przełącznik awarii kanału do demo ("SMS gateway down"). W bazie, więc działa na wszystkich kopiach serwera."""
    __tablename__ = "channel_settings"

    channel = Column(String(20), primary_key=True)         # sms | phone | email
    down = Column(Boolean, default=False, nullable=False)
