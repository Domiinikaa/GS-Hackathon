"""Tests for team leads: migration of older databases and seeding."""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from database import Base
from models import Person
from seed import TEAM_LEADS, seed_people
from services.people_service import ensure_people_role_column, team_leads


def test_role_column_added_to_old_database():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:  # "people" table as it looked before roles existed
        conn.execute(text("CREATE TABLE people (id INTEGER PRIMARY KEY, name VARCHAR(100), team VARCHAR(100), "
                          "email VARCHAR(200), phone VARCHAR(50), on_call BOOLEAN, channel_prefs JSON, quiet_hours JSON)"))
        conn.execute(text("INSERT INTO people (name, team) VALUES ('Old', 'IT')"))
    assert ensure_people_role_column(engine) is True
    assert "role" in [c["name"] for c in inspect(engine).get_columns("people")]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT role FROM people")).scalar() == "member"
    assert ensure_people_role_column(engine) is False  # second run does nothing


def test_fresh_database_is_left_to_create_all():
    assert ensure_people_role_column(create_engine("sqlite://")) is False


def test_seed_adds_members_and_leads_once():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_people(db)
    db.commit()
    assert db.query(Person).filter(Person.role == "member").count() == 3
    assert [p.name for p in team_leads(db, "IT")] == ["Marek"]

    db.query(Person).filter(Person.role == "lead").delete()  # someone removes all leads on purpose...
    db.commit()
    db.add(Person(name="New lead", team="IT", role="lead"))
    db.commit()
    seed_people(db)  # ...and adds their own: the seed must not bring the old leads back
    db.commit()
    assert {p.name for p in db.query(Person).filter(Person.role == "lead")} == {"New lead"}
    assert len(TEAM_LEADS) == 3
