"""Tests for team leads: seeding and lookup."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from database import Base
from models import Person
from seed import TEAM_LEADS, seed_people
from services.people_service import team_leads


def test_seed_adds_members_and_leads_once():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    seed_people(db)
    db.commit()
    assert db.query(Person).filter(Person.role == "member").count() == 3
    assert [p.name for p in team_leads(db, "Pricing")] == ["Marek"]

    db.query(Person).filter(Person.role == "lead").delete()  # someone removes all leads on purpose...
    db.commit()
    db.add(Person(name="New lead", team="Pricing", role="lead"))
    db.commit()
    seed_people(db)  # ...and adds their own: the seed must not bring the old leads back
    db.commit()
    assert {p.name for p in db.query(Person).filter(Person.role == "lead")} == {"New lead"}
    assert len(TEAM_LEADS) == 4
