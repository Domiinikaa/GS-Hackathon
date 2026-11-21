"""Tests for recipient selection."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401  (registers the tables)
from database import Base
from models import Person
from services.people_service import in_window, plan_recipients


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        Person(name="Anna", team="Payments", email="anna@example.com", phone="+48 600 000 001",
               channel_prefs={"critical": ["sms"], "warning": ["email"]},
               quiet_hours={"sms": {"from": "08:00", "to": "20:00", "else": "email"}}),
        Person(name="Tom", team="Settlements", email="tom@example.com", phone="+48 600 000 002", on_call=True,
               channel_prefs={"critical": ["phone", "sms"]}),
        Person(name="Ola", team="Settlements", email="ola@example.com", phone="+48 600 000 003",
               channel_prefs={"critical": ["phone", "sms"]}),
        Person(name="Kasia", team="Rates", email="kasia@example.com",
               channel_prefs={"warning": ["email"]}),
    ])
    session.commit()
    yield session
    session.close()


def simple(planned):
    return sorted((p.recipient.name, p.recipient.channel) for p in planned)


DAY = datetime(2026, 11, 20, 12, 0)
NIGHT = datetime(2026, 11, 20, 23, 30)


def test_anna_sms_during_day(db):
    assert simple(plan_recipients(db, "Payments", "critical", [], DAY)) == [("Anna", "sms"), ("team:Payments", "ui")]


def test_anna_email_at_night(db):
    assert simple(plan_recipients(db, "Payments", "critical", [], NIGHT)) == [("Anna", "email"), ("team:Payments", "ui")]


def test_rule_target_can_be_a_person(db):
    assert simple(plan_recipients(db, "Anna", "critical", [], DAY)) == [("Anna", "sms"), ("team:Anna", "ui")]


def test_team_feed_is_always_included(db):
    # The app feed no longer depends on the rule: even a rule without "ui" reaches it
    got = simple(plan_recipients(db, "Payments", "warning", ["email"], DAY))
    assert ("team:Payments", "ui") in got


def test_phone_only_for_on_call(db):
    got = simple(plan_recipients(db, "Settlements", "critical", ["phone", "sms", "ui"], DAY))
    assert got == [("Ola", "sms"), ("Tom", "phone"), ("Tom", "sms"), ("team:Settlements", "ui")]


def test_person_preferences_decide_channels_not_the_rule(db):
    # Kasia prefers email for warning; what the rule lists does not matter any more
    assert simple(plan_recipients(db, "Rates", "warning", ["ui"], DAY)) == [("Kasia", "email"), ("team:Rates", "ui")]
    assert simple(plan_recipients(db, "Rates", "warning", ["sms"], DAY)) == [("Kasia", "email"), ("team:Rates", "ui")]


def test_no_preference_uses_severity_defaults(db):
    # Kasia has no critical preference -> default phone + sms; not on call and no phone -> email
    assert simple(plan_recipients(db, "Rates", "critical", [], DAY)) == [("Kasia", "email"), ("team:Rates", "ui")]
    # info has no default personal channel -> app feed only
    assert simple(plan_recipients(db, "Rates", "info", [], DAY)) == [("team:Rates", "ui")]


def test_unknown_team_gets_only_ui(db):
    assert simple(plan_recipients(db, "Nobody", "critical", ["sms", "ui"], DAY)) == [("team:Nobody", "ui")]


@pytest.mark.parametrize("now,start,end,expected", [
    ("12:00", "08:00", "20:00", True),
    ("20:00", "08:00", "20:00", False),
    ("23:00", "22:00", "06:00", True),
    ("05:59", "22:00", "06:00", True),
    ("12:00", "22:00", "06:00", False),
])
def test_in_window(now, start, end, expected):
    h, m = map(int, now.split(":"))
    assert in_window(datetime(2026, 1, 1, h, m).time(), start, end) is expected


def test_quiet_hours_fallback_to_ui(db):
    db.add(Person(
        name="Jan", team="Ops", email="jan@example.com",
        channel_prefs={"warning": ["email"]},
        quiet_hours={"email": {"from": "08:00", "to": "20:00", "else": "ui"}},
    ))
    db.commit()
    assert simple(plan_recipients(db, "Ops", "warning", ["email"], NIGHT)) == [("Jan", "ui"), ("team:Ops", "ui")]


def test_info_ui_only_preference_not_overridden_by_rule_email(db):
    db.add(Person(
        name="Elena", team="Core", email="elena@example.com",
        channel_prefs={"info": ["ui"]},
    ))
    db.commit()
    assert simple(plan_recipients(db, "Core", "info", ["email", "ui"], DAY)) == [("team:Core", "ui")]
