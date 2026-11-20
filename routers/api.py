from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Item
from schemas import ItemCreate, ItemResponse
from services.logic import process_calculations
from services.external import fetch_external_data

router = APIRouter(prefix="/api", tags=["API"])


@router.get("/items", response_model=List[ItemResponse])
def get_items(db: Session = Depends(get_db)):
    return db.query(Item).all()


@router.post("/items", response_model=ItemResponse)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    db_item = Item(**payload.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    items = db.query(Item).all()
    stats = process_calculations(items)
    external = await fetch_external_data()
    return {"stats": stats, "external": external}
