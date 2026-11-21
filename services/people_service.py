"""Decides who gets an alert and on which channel."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Iterable

from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from models import Alert, Person, User
from services.contracts import Recipient

PERSONAL_CHANNELS = ("phone", "sms", "email")
# Where to go when a channel is unavailable (missing address etc.)
FALLBACK = {"phone": "sms", "sms": "email", "email": None}


@dataclass
class PlannedRecipient:
    """Recipient + the reason for the decision (shown in the UI preview: "Anna → email, outside SMS hours")."""
    recipient: Recipient
    reason: str


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def in_window(now: time, start: str, end: str) -> bool:
    """Whether `now` is inside the window [start, end). Supports windows across midnight."""
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
    """Returns (final channel or None, notes) after applying on-call, quiet hours and missing addresses."""
    notes: list[str] = []
    seen: set[str] = set()
    current: str | None = channel
    while current and current not in seen:
        seen.add(current)
        if current == "ui":
            return "ui", notes
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
    """Core logic: who, on which channel, and why. Used by the pipeline and by the UI preview."""
    now_t = (now or datetime.now()).time()
    rule_channels = list(dict.fromkeys(rule_channels or []))
    out: list[PlannedRecipient] = []

    if "ui" in rule_channels:
        out.append(PlannedRecipient(
            Recipient(person_id=None, name=f"team:{target}", channel="ui", to=None),
            "live feed for the whole team",
        ))

    personal_rule = [c for c in rule_channels if c in PERSONAL_CHANNELS]
    if not personal_rule:
        return out

    seen: set[tuple[int, str]] = set()
    for person in _audience(db, target):
        prefs = (person.channel_prefs or {}).get(severity)
        if prefs:
            matched_any = [c for c in rule_channels if c in prefs]
            wanted = [c for c in personal_rule if c in prefs]
            base_reason = f"prefers {', '.join(prefs)} for {severity}"
            if not matched_any:
                wanted = personal_rule
                base_reason += "; using rule channels"
        else:
            wanted = personal_rule
            base_reason = f"no preference for {severity}; using rule channels"

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


def ensure_people_role_column(engine) -> bool:
    """Adds people.role to databases created before the column existed (SQLite and Postgres).
    Returns True when the column was added."""
    insp = inspect(engine)
    if "people" not in insp.get_table_names():
        return False  # fresh database: create_all() makes the table with the column
    if any(col["name"] == "role" for col in insp.get_columns("people")):
        return False
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE people ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'"))
    return True


def team_leads(db: Session, team: str) -> list[Person]:
    """Leads of a team: they approve risky runbook steps for alerts of that team."""
    return db.query(Person).filter(Person.team == team, Person.role == "lead").order_by(Person.name).all()


def ensure_person_for_user(
    db: Session,
    *,
    name: str,
    team: str | None,
    email: str,
    phone: str | None = None,
    role: str = "member",
) -> Person | None:
    """Ensure a Person roster entry exists for a User so they appear in People & alert routing."""
    clean_team = (team or "").strip()
    if not clean_team:
        return None
    clean_email = email.strip().lower()
    existing = db.query(Person).filter(func.lower(Person.email) == clean_email).first()
    if existing is not None:
        if role == "lead" and existing.role != "lead":
            existing.role = "lead"
        return existing
    person = Person(
        name=name.strip(),
        team=clean_team,
        email=clean_email,
        phone=(phone or "").strip() or None,
        on_call=False,
        role=role,
        channel_prefs={"critical": ["email"], "warning": ["email"], "info": ["ui"]},
        quiet_hours={},
    )
    db.add(person)
    return person


def _find_person_for_user(db: Session, user: User) -> Person | None:
    if user.email:
        by_email = db.query(Person).filter(func.lower(Person.email) == user.email.lower()).first()
        if by_email is not None:
            return by_email
    if user.uname:
        return db.query(Person).filter(func.lower(Person.name) == user.uname.lower()).first()
    return None


def sync_person_role_for_user(db: Session, user: User) -> Person | None:
    """Keep Person.role ('lead' | 'member') in sync with User.is_admin."""
    target_role = "lead" if user.is_admin else "member"
    person = _find_person_for_user(db, user)
    if person is not None:
        person.role = target_role
        return person
    team = (user.dzial or "").strip()
    if not team and user.is_admin:
        team = "Management"
        user.dzial = team
    if not team:
        return None
    return ensure_person_for_user(
        db,
        name=user.uname,
        team=team,
        email=user.email,
        phone=user.nrtel,
        role=target_role,
    )


def sync_user_admin_for_person(db: Session, person: Person) -> User | None:
    """Keep User.is_admin in sync when a Person's role ('lead' | 'member') changes."""
    user = None
    if person.email:
        user = db.query(User).filter(func.lower(User.email) == person.email.strip().lower()).first()
    if user is None and person.name:
        user = db.query(User).filter(func.lower(User.uname) == person.name.strip().lower()).first()
    if user is not None:
        user.is_admin = person.role == "lead"
    return user


def migrate_admins_to_leads(db: Session) -> int:
    """Idempotent startup migration: every User with is_admin=True is synced to Person.role='lead'."""
    admins = db.query(User).filter(User.is_admin == True).all()  # noqa: E712
    updated = 0
    for admin in admins:
        person = _find_person_for_user(db, admin)
        if person is not None:
            if person.role != "lead":
                person.role = "lead"
                updated += 1
        else:
            synced = sync_person_role_for_user(db, admin)
            if synced is not None:
                updated += 1
    if updated:
        db.commit()
    return updated


def recipients_for(db: Session, alert: Alert, rule_channels: list[str]) -> list[Recipient]:
    return [p.recipient for p in plan_recipients(db, alert.team, alert.severity, rule_channels)]
