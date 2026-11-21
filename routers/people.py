"""People API."""
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Delivery, Person, Team, User
from routers.deps import get_current_admin_user, get_current_user
from services.people_service import plan_recipients

router = APIRouter(prefix="/api/people", tags=["People"])

Channel = Literal["email", "sms", "phone", "ui"]
Severity = Literal["info", "warning", "critical"]
Role = Literal["member", "lead"]
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def team_name(db: Session, name: str) -> Optional[str]:
    """Teams are managed in Admin & Teams. Returns the exact team name, or None."""
    team = db.query(Team).filter(func.lower(Team.name) == name.strip().lower()).first()
    return team.name if team else None


def _require_team(db: Session, name: str) -> str:
    found = team_name(db, name)
    if found is None:
        raise HTTPException(422, f"Team '{name}' does not exist. Pick a team managed in Admin & Teams.")
    return found


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
    role: Role = "member"  # "lead" approves risky runbook steps for the team
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
        "on_call": bool(p.on_call), "role": p.role or "member",
        "channel_prefs": p.channel_prefs or {}, "quiet_hours": p.quiet_hours or {},
    }


def _get_or_404(db: Session, person_id: int) -> Person:
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(404, f"Person {person_id} not found")
    return person


@router.get("")
def list_people(team: Optional[str] = None, role: Optional[Role] = None, db: Session = Depends(get_db)):
    """Optional filters, e.g. ?team=IT&role=lead returns the IT team leads."""
    q = db.query(Person)
    if team:
        q = q.filter(Person.team == team)
    if role:
        q = q.filter(Person.role == role)
    return [to_dict(p) for p in q.order_by(Person.team, Person.name).all()]


@router.get("/teams")
def list_teams(db: Session = Depends(get_db)):
    """Teams (managed in Admin & Teams) and people a rule can target."""
    return {
        "teams": [t.name for t in db.query(Team).order_by(Team.name).all()],
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


def _is_own_profile(user: User, person: Person) -> bool:
    """A registered account is linked to its Person by e-mail (see routers/auth.py register)."""
    return bool(person.email) and person.email.strip().lower() == (user.email or "").strip().lower()


@router.post("", status_code=201)
def create_person(payload: PersonIn, db: Session = Depends(get_db), _admin: User = Depends(get_current_admin_user)):
    """Admins only – everyone else appears in People by registering."""
    data = payload.to_columns()
    data["team"] = _require_team(db, data["team"])
    person = Person(**data)
    db.add(person)
    db.commit()
    db.refresh(person)
    return to_dict(person)


@router.put("/{person_id}")
def update_person(person_id: int, payload: PersonIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """Admins edit anyone. A regular user edits only their own profile and cannot change role or e-mail."""
    person = _get_or_404(db, person_id)
    if not user.is_admin and not _is_own_profile(user, person):
        raise HTTPException(403, "You can only edit your own profile.")
    data = payload.to_columns()
    data["team"] = _require_team(db, data["team"])
    if not user.is_admin:
        data["role"] = person.role or "member"   # nobody makes themselves a team lead
        data["email"] = person.email             # e-mail links the profile to the login account
    for key, value in data.items():
        setattr(person, key, value)
    db.commit()
    db.refresh(person)
    return to_dict(person)


@router.delete("/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db), _admin: User = Depends(get_current_admin_user)):
    person = _get_or_404(db, person_id)
    # Keep delivery history, just unlink it from the deleted person
    db.query(Delivery).filter(Delivery.person_id == person_id).update({Delivery.person_id: None})
    db.delete(person)
    db.commit()
    return {"deleted": True}
