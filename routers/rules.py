"""OSOBA 2 – reguły: CRUD. Kształt JSON = frontend/src/rules/ruleTypes.ts (Rule)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Rule

router = APIRouter(prefix="/api/rules", tags=["Rules (Osoba 2)"])


@router.get("")
def list_rules(db: Session = Depends(get_db)):
    return db.query(Rule).all()


@router.post("")
def create_rule(payload: dict, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 2): walidacja (pydantic) + zapis")


@router.put("/{rule_id}")
def update_rule(rule_id: str, payload: dict, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 2)")


@router.delete("/{rule_id}")
def delete_rule(rule_id: str, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 2)")
