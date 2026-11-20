"""OSOBA 4 – runbooki: CRUD + podgląd parsowania."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Runbook
from services.runbook_parser import parse_runbook

router = APIRouter(prefix="/api/runbooks", tags=["Runbooks (Osoba 4)"])


class ParseRequest(BaseModel):
    raw: str
    format: str = "text"  # yaml | markdown | text | link


@router.get("")
def list_runbooks(db: Session = Depends(get_db)):
    return db.query(Runbook).all()


@router.post("/parse")
def preview_parse(req: ParseRequest):
    """UI wkleja tekst i od razu widzi, jakie kroki z niego wyszły."""
    return {"steps": parse_runbook(req.raw, req.format)}


@router.post("")
def create_runbook(payload: dict, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 4)")
