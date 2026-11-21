from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Item, User
from schemas import ItemCreate, ItemResponse
from services.logic import process_calculations
from services.external import fetch_external_data
from routers.deps import get_current_user, get_optional_current_user

router = APIRouter(prefix="/api", tags=["Private User Panel & API"])


@router.get("/items", response_model=List[ItemResponse])
def get_user_items(
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns items for the current authenticated user:
    - If authenticated: returns ONLY records owned by this user.
    - If unauthenticated (demo/guest): returns global records (user_id is None).
    """
    if current_user:
        return db.query(Item).filter(Item.user_id == current_user.id).order_by(Item.created_at.desc()).all()
    return db.query(Item).filter(Item.user_id.is_(None)).order_by(Item.created_at.desc()).all()


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_user_item(
    payload: ItemCreate,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Creates a new record scoped to the authenticated user's private panel."""
    db_item = Item(
        user_id=current_user.id if current_user else None,
        title=payload.title,
        category=payload.category,
        value=payload.value,
        description=payload.description
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.delete("/items/{item_id}", status_code=status.HTTP_200_OK)
def delete_user_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deletes an item. Users can only delete records they personally own."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")

    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied. You can only modify your own records."
        )

    db.delete(item)
    db.commit()
    return {"message": "Record successfully deleted."}


@router.get("/stats")
async def get_user_stats(
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """Returns analytics for the user's records alongside external market feeds."""
    if current_user:
        items = db.query(Item).filter(Item.user_id == current_user.id).all()
    else:
        items = db.query(Item).filter(Item.user_id.is_(None)).all()

    stats = process_calculations(items)
    external = await fetch_external_data()
    return {
        "stats": stats,
        "external": external,
        "user": {
            "uname": current_user.uname,
            "email": current_user.email,
            "team": current_user.dzial,
            "dzial": current_user.dzial,
        } if current_user else None
    }
