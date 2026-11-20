from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Item
from services.logic import process_calculations
from services.external import fetch_external_data

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home_view(request: Request, db: Session = Depends(get_db)):
    items = db.query(Item).order_by(Item.created_at.desc()).all()
    stats = process_calculations(items)
    external = await fetch_external_data()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "items": items,
            "stats": stats,
            "external": external,
        }
    )


@router.post("/items/add")
async def add_item_form(
    title: str = Form(...),
    category: str = Form("General"),
    value: float = Form(0.0),
    description: str = Form(""),
    db: Session = Depends(get_db)
):
    item = Item(
        title=title,
        category=category,
        value=value,
        description=description
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/items/{item_id}/delete")
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/", status_code=303)
