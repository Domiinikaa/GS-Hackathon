"""People API."""
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from database import get_db
from models import Delivery, Person, Rule
from services.people_service import plan_recipients

router = APIRouter(prefix="/api/people", tags=["People"])

Channel = Literal["email", "sms", "phone", "ui"]
Severity = Literal["info", "warning", "critical"]
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class QuietWindow(BaseModel):
    """The channel is used only from `from` to `to`; outside that window the `else` channel is used."""
    from_: str = Field(..., alias="from")
    to: str
    else_: Optional[Channel] = Field("email", alias="else")

    model_config = {"populate_by_name": True}

    @field_validator("from_", "to")
    @classmethod
    def hhmm(cls, v):
        if not HHMM.match(v):
            raise ValueError("time must be HH:MM, e.g. 08:00")
        return v


class PersonIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    team: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=50)
    on_call: bool = False
    channel_prefs: Dict[Severity, List[Channel]] = Field(default_factory=dict)
    quiet_hours: Dict[Channel, QuietWindow] = Field(default_factory=dict)

    @field_validator("name", "team")
    @classmethod
    def strip(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("email", "phone")
    @classmethod
    def blank_to_none(cls, v):
        return (v or "").strip() or None

    @field_validator("email")
    @classmethod
    def email_shape(cls, v):
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("not a valid e-mail address")
        return v

    @model_validator(mode="after")
    def check_addresses(self):
        used = {c for chans in self.channel_prefs.values() for c in chans}
        if used & {"sms", "phone"} and not self.phone:
            raise ValueError("SMS / phone call is selected, so a phone number is required")
        if "email" in used and not self.email:
            raise ValueError("E-mail is selected, so an e-mail address is required")
        return self

    def to_columns(self) -> Dict[str, Any]:
        data = self.model_dump(by_alias=True)
        data["channel_prefs"] = {k: list(dict.fromkeys(v)) for k, v in data["channel_prefs"].items()}
        return data


def to_dict(p: Person) -> Dict[str, Any]:
    return {
        "id": p.id, "name": p.name, "team": p.team, "email": p.email, "phone": p.phone,
        "on_call": bool(p.on_call), "channel_prefs": p.channel_prefs or {}, "quiet_hours": p.quiet_hours or {},
    }


def _get_or_404(db: Session, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(404, f"Person {person_id} not found")
    return person


@router.get("")
def list_people(team: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Person)
    if team:
        q = q.filter(Person.team == team)
    return [to_dict(p) for p in q.order_by(Person.team, Person.name).all()]


@router.get("/teams")
def list_teams(db: Session = Depends(get_db)):
    """All teams and people a rule can target (suggestions for the "Who gets notified" field)."""
    teams = {t for (t,) in db.query(Person.team).distinct()} | {t for (t,) in db.query(Rule.team).distinct()}
    return {
        "teams": sorted(t for t in teams if t),
        "people": sorted({n for (n,) in db.query(Person.name).distinct()}),
    }


class PreviewIn(BaseModel):
    team: str
    severity: Severity = "warning"
    channels: List[Channel] = Field(default_factory=list)
    at: Optional[datetime] = None  # defaults to now


@router.post("/preview")
def preview_recipients(payload: PreviewIn, db: Session = Depends(get_db)):
    """Who would get an alert from such a rule, and why (nothing is sent)."""
    planned = plan_recipients(db, payload.team.strip(), payload.severity, payload.channels, payload.at)
    return [
        {"person_id": p.recipient.person_id, "name": p.recipient.name, "channel": p.recipient.channel,
         "to": p.recipient.to, "reason": p.reason}
        for p in planned
    ]


@router.get("/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db)):
    return to_dict(_get_or_404(db, person_id))


@router.post("", status_code=201)
def create_person(payload: PersonIn, db: Session = Depends(get_db)):
    person = Person(**payload.to_columns())
    db.add(person)
    db.commit()
    db.refresh(person)
    return to_dict(person)


@router.put("/{person_id}")
def update_person(person_id: int, payload: PersonIn, db: Session = Depends(get_db)):
    person = _get_or_404(db, person_id)
    for key, value in payload.to_columns().items():
        setattr(person, key, value)
    db.commit()
    db.refresh(person)
    return to_dict(person)


@router.delete("/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = _get_or_404(db, person_id)
    # Keep delivery history, just unlink it from the deleted person
    db.query(Delivery).filter(Delivery.person_id == person_id).update({Delivery.person_id: None})
    db.delete(person)
    db.commit()
    return {"deleted": True}
