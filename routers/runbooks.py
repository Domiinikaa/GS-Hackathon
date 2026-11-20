"""OSOBA 4 – runbooki (CRUD + podgląd parsowania) i test silnika reguł na sucho."""
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import Event, Rule, Runbook
from services.rules_engine import evaluate
from services.runbook_parser import parse_runbook_with_format

router = APIRouter(prefix="/api", tags=["Runbooks & engine (Osoba 4)"])


# ---------------------------------------------------------------- schematy

class ParseRequest(BaseModel):
    raw: str
    format: str = "auto"  # auto | yaml | markdown | text | link


def _clean_name(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("Name cannot be empty")
    return v


class RunbookIn(BaseModel):
    name: str
    raw: str
    format: str = "auto"
    matches: Optional[Dict[str, Any]] = None  # grupa warunków jak w regułach – automatyczne podpinanie

    _name = field_validator("name")(_clean_name)


class RunbookPatch(BaseModel):
    name: Optional[str] = None
    raw: Optional[str] = None
    format: Optional[str] = None
    matches: Optional[Dict[str, Any]] = None

    _name = field_validator("name")(_clean_name)


class EngineTestRequest(BaseModel):
    event: Any                                # dowolny JSON zdarzenia
    rule_ids: Optional[List[str]] = None      # tylko te reguły z bazy (domyślnie: wszystkie włączone)
    rule: Optional[Dict[str, Any]] = None     # albo reguła z formularza, jeszcze niezapisana


def _parse_or_422(raw: str, fmt: str) -> tuple:
    """(format, którego naprawdę użyto, kroki). Błąd tylko przy ręcznie wybranym, niepoprawnym YAML-u."""
    try:
        return parse_runbook_with_format(raw, fmt)
    except ValueError as e:
        raise HTTPException(422, str(e))


def _get_or_404(db: Session, runbook_id: int) -> Runbook:
    rb = db.get(Runbook, runbook_id)
    if rb is None:
        raise HTTPException(404, f"Runbook {runbook_id} not found")
    return rb


# ---------------------------------------------------------------- runbooki

@router.get("/runbooks")
def list_runbooks(db: Session = Depends(get_db)):
    return db.query(Runbook).order_by(Runbook.id).all()


@router.post("/runbooks/parse")
def preview_parse(req: ParseRequest):
    """UI wkleja tekst i od razu widzi, jakie kroki z niego wyszły."""
    fmt, steps = _parse_or_422(req.raw, req.format)
    return {"format": fmt, "steps": steps}


@router.get("/runbooks/{runbook_id}")
def get_runbook(runbook_id: int, db: Session = Depends(get_db)):
    rb = _get_or_404(db, runbook_id)
    rules = db.query(Rule).filter(Rule.runbook_id == runbook_id).all()
    return {**{c.name: getattr(rb, c.name) for c in Runbook.__table__.columns},
            "rules": [{"id": r.id, "name": r.name} for r in rules]}


@router.post("/runbooks")
def create_runbook(payload: RunbookIn, db: Session = Depends(get_db)):
    fmt, steps = _parse_or_422(payload.raw, payload.format)
    rb = Runbook(name=payload.name, format=fmt, raw=payload.raw, steps=steps, matches=payload.matches)
    db.add(rb)
    db.commit()
    db.refresh(rb)
    return rb


@router.put("/runbooks/{runbook_id}")
def update_runbook(runbook_id: int, payload: RunbookPatch, db: Session = Depends(get_db)):
    rb = _get_or_404(db, runbook_id)
    if payload.name is not None:
        rb.name = payload.name
    if payload.matches is not None:
        rb.matches = payload.matches or None  # {} = wyłącz automatyczne podpinanie
    if payload.raw is not None or payload.format is not None:
        raw = payload.raw if payload.raw is not None else rb.raw
        rb.format, rb.steps = _parse_or_422(raw, payload.format or rb.format)
        rb.raw = raw
    db.commit()
    db.refresh(rb)
    return rb


@router.delete("/runbooks/{runbook_id}")
def delete_runbook(runbook_id: int, db: Session = Depends(get_db)):
    rb = _get_or_404(db, runbook_id)
    db.query(Rule).filter(Rule.runbook_id == runbook_id).update({Rule.runbook_id: None})
    db.delete(rb)
    db.commit()
    return {"deleted": runbook_id}


@router.post("/runbooks/{runbook_id}/attach/{rule_id}")
def attach_to_rule(runbook_id: int, rule_id: str, db: Session = Depends(get_db)):
    """Podpina runbook do reguły (rule.runbook_id). Gotowe do użycia z ekranu Runbooks."""
    _get_or_404(db, runbook_id)
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(404, f"Rule {rule_id} not found")
    rule.runbook_id = runbook_id
    db.commit()
    return {"rule_id": rule_id, "runbook_id": runbook_id}


@router.delete("/runbooks/{runbook_id}/attach/{rule_id}")
def detach_from_rule(runbook_id: int, rule_id: str, db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if rule is None or rule.runbook_id != runbook_id:
        raise HTTPException(404, "This runbook is not attached to that rule")
    rule.runbook_id = None
    db.commit()
    return {"rule_id": rule_id, "runbook_id": None}


# ---------------------------------------------------------------- test silnika

@router.post("/engine/test")
def engine_test(req: EngineTestRequest, db: Session = Depends(get_db)):
    """Uruchamia silnik reguł na zdarzeniu BEZ zapisu: które reguły pasują, jaki tytuł, jakie kroki."""
    if req.rule is not None:
        fields = {c.name for c in Rule.__table__.columns}
        rule = Rule(**{k: v for k, v in req.rule.items() if k in fields})
        rule.id = rule.id or "draft"
        rule.enabled = True
        rules = [rule]
    else:
        q = db.query(Rule)
        q = q.filter(Rule.id.in_(req.rule_ids)) if req.rule_ids else q.filter(Rule.enabled.is_(True))
        rules = q.all()

    event = Event(id=0, payload=req.event, received_at=datetime.utcnow())  # nie dodajemy do sesji
    matches = evaluate(event, rules)
    matched = {m.rule_id for m in matches}
    return {
        "checked": [r.id for r in rules],
        "matched": [asdict(m) for m in matches],
        "not_matched": [r.id for r in rules if r.id not in matched],
    }
