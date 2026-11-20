"""OSOBA 3 – źródła zdarzeń i wejście /api/ingest/{key}."""
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Event, Source
from services.pipeline import process_event

router = APIRouter(prefix="/api", tags=["Sources & ingest (Osoba 3)"])


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    return db.query(Source).all()


@router.post("/sources")
def create_source(payload: dict, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 3): wygenerować key, zapisać, zwrócić adres /api/ingest/{key}")


@router.get("/events")
def list_events(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Event).order_by(Event.id.desc()).limit(limit).all()


@router.post("/ingest/{source_key}")
def ingest(source_key: str, payload: Any = Body(...), db: Session = Depends(get_db)):
    """Przyjmuje DOWOLNY JSON (obiekt albo listę obiektów). Działa już teraz."""
    source = db.query(Source).filter(Source.key == source_key).first()
    if not source:
        raise HTTPException(404, f"Unknown source '{source_key}'")
    items = payload if isinstance(payload, list) else [payload]
    alert_ids: list[int] = []
    for item in items:
        event = Event(source_id=source.id, payload=item)
        db.add(event)
        db.flush()  # nadaje event.id
        alert_ids += process_event(db, event)
    db.commit()
    return {"accepted": len(items), "alerts": alert_ids}
