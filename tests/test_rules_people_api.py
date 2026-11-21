"""Tests for the rules and people API."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from database import Base, get_db
from routers import people, rules
from models import Team
from seed import seed_people, seed_rules

TEAMS = sorted(["Management", "Payments", "Pricing", "Rates", "Settlements"])


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add_all([Team(name=n) for n in TEAMS])
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
    {"channels": ["pigeon"]},
    {"title": "   "},
])
def test_rule_validation(client, bad):
    assert client.post("/api/rules", json={**NEW_RULE, **bad}).status_code == 422


def test_nested_and_or_allowed(client):
    cond = {"or": [
        {"and": [{"field": "a", "op": "eq", "value": 1}, {"not": {"field": "b", "op": "eq", "value": 2}}]},
        {"field": "c", "op": "neq", "value": 3},
    ]}
    res = client.post("/api/rules", json={**NEW_RULE, "condition": cond})
    assert res.status_code == 201, res.text
    assert res.json()["condition"] == cond


@pytest.mark.parametrize("cond", [
    {"not": {"field": "a", "op": "eq", "value": 1}},          # top level must be and / or
    {"and": [{"or": []}]},                                    # empty nested group
    {"and": [{"not": {"xor": []}}]},                          # unknown node inside not
    {"and": [{"and": [{"and": [{"and": [{"and": [{"and": [{"field": "a", "op": "eq", "value": 1}]}]}]}]}]}]},
])
def test_bad_nested_conditions_rejected(client, cond):
    assert client.post("/api/rules", json={**NEW_RULE, "condition": cond}).status_code == 422


NEW_PERSON = {
    "name": "Ola", "team": "Rates", "email": "ola@example.com", "phone": "+48 600 000 009",
    "on_call": True,
    "channel_prefs": {"critical": ["phone", "sms"], "warning": ["email"], "info": ["ui"]},
    "quiet_hours": {"sms": {"from": "08:00", "to": "20:00", "else": "email"}},
}


def test_people_crud(client):
    assert len(client.get("/api/people").json()) == 7  # 3 members + 4 team leads from the seed
    created = client.post("/api/people", json=NEW_PERSON)
    assert created.status_code == 201, created.text
    person = created.json()
    assert person["quiet_hours"]["sms"] == {"from": "08:00", "to": "20:00", "else": "email"}

    assert len(client.get("/api/people", params={"team": "Rates"}).json()) == 3  # Kasia, Piotr, Ola
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
    assert teams["teams"] == TEAMS
    assert "Anna" in teams["people"]

    night = client.post("/api/people/preview", json={
        "team": "Anna", "severity": "critical", "channels": ["sms"], "at": "2026-11-20T23:00:00"}).json()
    assert [(r["name"], r["channel"]) for r in night] == [("team:Anna", "ui"), ("Anna", "email")]
    assert "08:00" in night[1]["reason"]


def test_field_hints_shape(client):
    from database import get_db
    from models import Source
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Source(key="t", name="t", team="Rates", sample_event={
        "payload": {"desk": "rates", "notional": 25000000, "ok": True, "tags": ["a"], "extra": {}}, "note": None}))
    db.commit()
    fields = {f["path"]: f for f in client.get("/api/rules/fields").json()}
    assert fields["payload.desk"] == {"path": "payload.desk", "type": "string", "example": "rates", "count": 1}
    assert fields["payload.notional"]["type"] == "number"
    assert fields["payload.ok"]["type"] == "boolean"
    assert fields["payload.tags"]["type"] == "array"
    assert fields["payload.extra"]["type"] == "object"
    assert fields["note"]["type"] == "null"


def test_team_must_be_a_department(client):
    assert client.post("/api/people", json={**NEW_PERSON, "team": "UnknownTeam"}).status_code == 422
    # case-insensitive, stored with the department's exact name
    assert client.post("/api/people", json={**NEW_PERSON, "team": "rates"}).json()["team"] == "Rates"


def test_rule_target_is_team_or_person(client):
    assert client.post("/api/rules", json={**NEW_RULE, "team": "UnknownTeam"}).status_code == 422
    assert client.post("/api/rules", json={**NEW_RULE, "team": "settlements"}).json()["team"] == "Settlements"
    assert client.post("/api/rules", json={**NEW_RULE, "name": "Personal", "team": "Anna"}).json()["team"] == "Anna"


def test_role_defaults_to_member_and_lead_filter(client):
    member = client.post("/api/people", json=NEW_PERSON).json()
    assert member["role"] == "member"
    lead = client.post("/api/people", json={**NEW_PERSON, "name": "Lead Rates", "role": "lead"}).json()
    assert lead["role"] == "lead"
    leads = client.get("/api/people", params={"team": "Rates", "role": "lead"}).json()
    assert {p["name"] for p in leads} == {"Piotr", "Lead Rates"}  # Piotr comes from the seed
    assert client.post("/api/people", json={**NEW_PERSON, "role": "boss"}).status_code == 422
