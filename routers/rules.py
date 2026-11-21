"""Rules API."""
import re
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from database import get_db
from models import Alert, Event, Person, Rule, Source
from routers.people import team_name

router = APIRouter(prefix="/api/rules", tags=["Rules"])

Operator = Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "contains", "wildcard"]
Channel = Literal["email", "sms", "phone", "ui"]
Severity = Literal["info", "warning", "critical"]
Color = Literal["red", "amber", "blue", "green", "slate"]


class ConditionIn(BaseModel):
    field: str = Field(..., min_length=1, max_length=200)
    op: Operator
    value: Union[float, int, str, List[Union[str, float, int]]]

    @model_validator(mode="after")
    def check_value(self):
        if self.op == "in" and not isinstance(self.value, list):
            self.value = [v.strip() for v in str(self.value).split(",") if v.strip()]
        if self.op in ("gt", "gte", "lt", "lte") and not isinstance(self.value, (int, float)):
            try:
                self.value = float(self.value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                raise ValueError(f"'{self.field}': operator {self.op} needs a number")
        return self


MAX_DEPTH = 5


def _validate_node(node: Any, depth: int) -> Dict[str, Any]:
    """A condition node: {"and": [...]}, {"or": [...]}, {"not": ...} or a leaf {"field", "op", "value"}."""
    if depth > MAX_DEPTH:
        raise ValueError(f"conditions can be nested at most {MAX_DEPTH} levels deep")
    if isinstance(node, dict) and len(node) == 1 and next(iter(node)) in ("and", "or"):
        mode, items = next(iter(node.items()))
        if not isinstance(items, list) or not items:
            raise ValueError(f'"{mode}" needs at least one condition')
        return {mode: [_validate_node(item, depth + 1) for item in items]}
    if isinstance(node, dict) and len(node) == 1 and "not" in node:
        return {"not": _validate_node(node["not"], depth + 1)}
    if isinstance(node, dict) and "field" in node:
        return ConditionIn.model_validate(node).model_dump()
    raise ValueError('each condition must be {"and": [...]}, {"or": [...]}, {"not": ...} or {"field", "op", "value"}')


def _validate_group(group: Any) -> Dict[str, Any]:
    """Top level is always an "and" / "or" group; nested and / or groups are allowed inside."""
    if not isinstance(group, dict) or len(group) != 1 or next(iter(group)) not in ("and", "or"):
        raise ValueError('condition must look like {"and": [...]} or {"or": [...]}')
    return _validate_node(group, 0)


class RuleIn(BaseModel):
    id: Optional[str] = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    team: str = Field(..., min_length=1, max_length=100)
    enabled: bool = True
    condition: Dict[str, Any]
    channels: List[Channel] = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=300)
    body: Optional[str] = None
    severity: Severity = "warning"
    color: Color = "amber"
    group_by: Optional[str] = Field(None, max_length=200)
    group_window_s: Optional[int] = Field(None, ge=1, le=86400)
    runbook_id: Optional[int] = None

    @field_validator("condition")
    @classmethod
    def check_condition(cls, v):
        return _validate_group(v)

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, v):
        return list(dict.fromkeys(v))

    @field_validator("name", "team", "title")
    @classmethod
    def strip(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


class RulePatch(BaseModel):
    """Partial change, e.g. {"enabled": false}."""
    enabled: Optional[bool] = None


def to_dict(rule: Rule) -> Dict[str, Any]:
    return {
        "id": rule.id, "name": rule.name, "team": rule.team, "enabled": rule.enabled,
        "condition": rule.condition, "channels": rule.channels or [], "title": rule.title,
        "body": rule.body, "severity": rule.severity, "color": rule.color,
        "group_by": rule.group_by, "group_window_s": rule.group_window_s,
        "runbook_id": rule.runbook_id,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:56] or "rule"


def _unique_id(db: Session, base: str) -> str:
    candidate, n = base, 2
    while db.get(Rule, candidate) is not None:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def _get_or_404(db: Session, rule_id: str) -> Rule:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule '{rule_id}' not found")
    return rule


@router.get("")
def list_rules(team: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Rule)
    if team:
        q = q.filter(Rule.team == team)
    return [to_dict(r) for r in q.order_by(Rule.team, Rule.name).all()]


def _type_name(value: Any) -> str:
    """Same type names as the sources API (services/connectors/parser.py)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _flatten(obj: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = {} if out is None else out
    if isinstance(obj, dict) and (obj or not prefix):
        for k, v in obj.items():
            _flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif prefix:
        out.setdefault(prefix, obj)
    return out


@router.get("/fields")
def field_hints(limit: int = 200, db: Session = Depends(get_db)):
    """Field suggestions for the rule editor, from source samples and recent events.
    Same shape as GET /api/sources/{id}/fields: {"path", "type", "example"} (+ "count")."""
    seen: Dict[str, Dict[str, Any]] = {}
    payloads = [s.sample_event for s in db.query(Source).all() if s.sample_event]
    payloads += [e.payload for e in db.query(Event).order_by(Event.id.desc()).limit(limit).all()]
    for payload in payloads:
        for path, value in _flatten(payload).items():
            entry = seen.setdefault(path, {"path": path, "type": _type_name(value), "example": value, "count": 0})
            entry["count"] += 1
    return sorted(seen.values(), key=lambda e: (-e["count"], e["path"]))


@router.get("/{rule_id}")
def get_rule(rule_id: str, db: Session = Depends(get_db)):
    return to_dict(_get_or_404(db, rule_id))


def _require_target(db: Session, name: str) -> str:
    """A rule goes to a team (department from Admin & Invites) or to one person by name."""
    team = team_name(db, name)
    if team:
        return team
    person = db.query(Person).filter(Person.name == name.strip()).first()
    if person:
        return person.name
    raise HTTPException(422, f"'{name}' is neither a team (Admin & Invites department) nor a person on the People page.")


@router.post("", status_code=201)
def create_rule(payload: RuleIn, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["team"] = _require_target(db, data["team"])
    wanted = _slug(data.pop("id") or data["name"])
    rule = Rule(id=_unique_id(db, wanted), **data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return to_dict(rule)


@router.put("/{rule_id}")
def update_rule(rule_id: str, payload: RuleIn, db: Session = Depends(get_db)):
    rule = _get_or_404(db, rule_id)
    data = payload.model_dump()
    data.pop("id", None)  # the id never changes because alerts reference it
    data["team"] = _require_target(db, data["team"])
    for key, value in data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return to_dict(rule)


@router.patch("/{rule_id}")
def patch_rule(rule_id: str, payload: RulePatch, db: Session = Depends(get_db)):
    rule = _get_or_404(db, rule_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return to_dict(rule)


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    rule = _get_or_404(db, rule_id)
    if db.query(Alert).filter(Alert.rule_id == rule_id).first() is not None:
        # Alerts reference the rule (foreign key), so disable it instead of deleting
        rule.enabled = False
        db.commit()
        return {"deleted": False, "disabled": True, "detail": "Rule has alerts, so it was disabled instead"}
    db.delete(rule)
    db.commit()
    return {"deleted": True}
