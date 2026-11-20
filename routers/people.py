"""OSOBA 2 – ludzie i ich preferencje kanałów: CRUD."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Person

router = APIRouter(prefix="/api/people", tags=["People (Osoba 2)"])


@router.get("")
def list_people(team: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Person)
    if team:
        q = q.filter(Person.team == team)
    return q.all()


@router.post("")
def create_person(payload: dict, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 2)")


@router.put("/{person_id}")
def update_person(person_id: int, payload: dict, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 2)")


@router.delete("/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 2)")
