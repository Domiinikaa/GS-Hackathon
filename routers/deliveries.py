"""OSOBA 3 – Outbox: co i komu wysłaliśmy, z ponawianiem."""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Delivery

router = APIRouter(prefix="/api/deliveries", tags=["Outbox (Osoba 3)"])


@router.get("")
def list_deliveries(status: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(Delivery)
    if status:
        q = q.filter(Delivery.status == status)
    return q.order_by(Delivery.id.desc()).limit(limit).all()
