"""API tests for rules and people, on a separate in-memory database."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from database import Base, get_db
from routers import people, rules
from seed import seed_people, seed_rules


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        seed_rules(db)
        seed_people(db)
        db.commit()

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(rules.router)
    app.include_router(people.router)
    app.dependency_overrides[get_db] = override
    return TestClient(app)


NEW_RULE = {
    "name": "Big EUR rejections",
    "team": "Rates",
    "condition": {"or": [{"field": "payload.currency", "op": "eq", "value": "EUR"},
                         {"field": "payload.reason", "op": "in", "value": "LIMIT_BREACH, TIMEOUT"}]},
    "channels": ["email", "ui", "email"],
    "title": "Rejected {{payload.currency}}",
    "severity": "warning",
    "color": "amber",
}


def test_rules_crud(client):
    assert len(client.get("/api/rules").json()) == 4

    created = client.post("/api/rules", json=NEW_RULE)
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["id"] == "big-eur-rejections"
    assert rule["channels"] == ["email", "ui"]
    assert rule["condition"]["or"][1]["value"] == ["LIMIT_BREACH", "TIMEOUT"]

    # same name -> unique id
    assert client.post("/api/rules", json=NEW_RULE).json()["id"] == "big-eur-rejections-2"

    updated = client.put(f"/api/rules/{rule['id']}", json={**NEW_RULE, "severity": "critical"})
    assert updated.json()["severity"] == "critical"

    assert client.patch(f"/api/rules/{rule['id']}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/api/rules/{rule['id']}").json() == {"deleted": True}
    assert client.get(f"/api/rules/{rule['id']}").status_code == 404


@pytest.mark.parametrize("bad", [
    {"condition": {"xor": []}},
    {"condition": {"and": []}},
    {"condition": {"and": [{"field": "x", "op": "gt", "value": "abc"}]}},
    {"condition": {"and": [{"field": "x", "op": "like", "value": "a"}]}},
    {"channels": []},
    {"channels": ["pigeon"]},
    {"title": "   "},
])
def test_rule_validation(client, bad):
    assert client.post("/api/rules", json={**NEW_RULE, **bad}).status_code == 422


def test_nested_groups_allowed(client):
    cond = {"and": [{"field": "a", "op": "eq", "value": 1},
                    {"or": [{"field": "b", "op": "eq", "value": 2}, {"field": "c", "op": "eq", "value": 3}]}]}
    assert client.post("/api/rules", json={**NEW_RULE, "condition": cond}).status_code == 201


NEW_PERSON = {
    "name": "Ola", "team": "Rates", "email": "ola@example.com", "phone": "+48 600 000 009",
    "on_call": True,
    "channel_prefs": {"critical": ["phone", "sms"], "warning": ["email"], "info": ["ui"]},
    "quiet_hours": {"sms": {"from": "08:00", "to": "20:00", "else": "email"}},
}


def test_people_crud(client):
    assert len(client.get("/api/people").json()) == 3
    created = client.post("/api/people", json=NEW_PERSON)
    assert created.status_code == 201, created.text
    person = created.json()
    assert person["quiet_hours"]["sms"] == {"from": "08:00", "to": "20:00", "else": "email"}

    assert len(client.get("/api/people", params={"team": "Rates"}).json()) == 2
    updated = client.put(f"/api/people/{person['id']}", json={**NEW_PERSON, "on_call": False})
    assert updated.json()["on_call"] is False
    assert client.delete(f"/api/people/{person['id']}").json() == {"deleted": True}


@pytest.mark.parametrize("bad", [
    {"phone": ""},                                             # SMS selected, no phone
    {"email": "not-an-email"},
    {"quiet_hours": {"sms": {"from": "8am", "to": "20:00"}}},
    {"channel_prefs": {"urgent": ["sms"]}},
])
def test_person_validation(client, bad):
    assert client.post("/api/people", json={**NEW_PERSON, **bad}).status_code == 422


def test_teams_and_preview(client):
    teams = client.get("/api/people/teams").json()
    assert {"Payments", "Rates", "Settlements", "Pricing"} <= set(teams["teams"])
    assert "Anna" in teams["people"]

    night = client.post("/api/people/preview", json={
        "team": "Payments", "severity": "critical", "channels": ["sms"], "at": "2026-11-20T23:00:00"}).json()
    assert [(r["name"], r["channel"]) for r in night] == [("Anna", "email")]
    assert "08:00" in night[0]["reason"]


def test_field_hints(client):
    assert client.get("/api/rules/fields").status_code == 200
