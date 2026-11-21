"""Tests for admin -> People roster sync and create_admin conflict handling."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from create_admin import create_or_promote_admin
from database import Base
from models import Person, User
from services.people_service import ensure_person_for_user
from services.security import hash_password


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_ensure_person_for_user_creates_and_deduplicates(db):
    assert ensure_person_for_user(db, name="NoTeam", team=None, email="noteam@example.com") is None

    created = ensure_person_for_user(
        db, name="Admin", team="Management", email="Admin@Example.com", phone="+48 600 000 099"
    )
    db.commit()
    assert created is not None
    assert created.team == "Management"
    assert created.email == "admin@example.com"

    again = ensure_person_for_user(
        db, name="Admin", team="Management", email="admin@example.com"
    )
    assert again.id == created.id
    assert db.query(Person).count() == 1


def test_create_or_promote_admin_creates_user_and_person(db):
    user, status = create_or_promote_admin(
        db, uname="boss", email="Boss@Example.com", password="Secret123!", phone="+48 600 111 222"
    )
    assert status == "created"
    assert user.is_admin is True
    assert user.dzial == "Management"

    person = db.query(Person).filter(Person.email == "boss@example.com").first()
    assert person is not None
    assert person.name == "boss"
    assert person.team == "Management"
    assert person.phone == "+48 600 111 222"


def test_create_or_promote_admin_existing_by_uname_or_email(db):
    existing = User(
        uname="jan",
        email="jan@example.com",
        hashed_password=hash_password("pass"),
        dzial=None,
        is_admin=False,
    )
    db.add(existing)
    db.commit()

    # Match by uname even with a different email argument
    user, status = create_or_promote_admin(
        db, uname="jan", email="other@example.com", password="ignored", phone="+48 600 222 333"
    )
    assert status == "promoted"
    assert user.id == existing.id
    assert user.is_admin is True
    assert user.dzial == "Management"
    assert user.nrtel == "+48 600 222 333"

    person = db.query(Person).filter(Person.email == "jan@example.com").first()
    assert person is not None
    assert person.team == "Management"

    # Match by email (case-insensitive) when already admin
    user2, status2 = create_or_promote_admin(
        db, uname="different_uname", email="JAN@EXAMPLE.COM", password="ignored"
    )
    assert status2 == "already_admin"
    assert user2.id == existing.id
    assert db.query(Person).count() == 1


def test_create_or_promote_admin_conflict_between_two_users(db):
    db.add_all([
        User(uname="alice", email="alice@example.com", hashed_password=hash_password("p1"), dzial="Rates"),
        User(uname="bob", email="bob@example.com", hashed_password=hash_password("p2"), dzial="Payments"),
    ])
    db.commit()

    with pytest.raises(ValueError, match="Conflict"):
        create_or_promote_admin(db, uname="alice", email="bob@example.com", password="Secret123!")
