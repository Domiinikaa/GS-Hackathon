"""OSOBA 3 – Outbox: co i komu wysłaliśmy, symulacja awarii kanału i ponawianie."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Alert, Delivery, Person
from services.delivery import (
    CHANNEL_PROVIDERS,
    MAX_ATTEMPTS,
    format_delivery_message,
    list_channel_statuses,
    process_pending_deliveries,
    set_channel_outage,
)

router = APIRouter(prefix="/api/deliveries", tags=["Outbox (Osoba 3)"])


class OutageToggleIn(BaseModel):
    down: bool
    error_message: Optional[str] = None


def _serialize_delivery(
    d: Delivery,
    alerts_by_id: Dict[int, Alert],
    people_by_id: Dict[int, Person],
) -> Dict[str, Any]:
    alert = alerts_by_id.get(d.alert_id)
    person = people_by_id.get(d.person_id) if d.person_id is not None else None
    attempts = d.attempts or 0
    if person is not None:
        person_name: Optional[str] = person.name
    elif d.channel == "ui" and alert is not None:
        person_name = f"Team feed ({alert.team})"
    else:
        person_name = None

    return {
        "id": d.id,
        "alert_id": d.alert_id,
        "person_id": d.person_id,
        "channel": d.channel,
        "to": d.to,
        "status": d.status,
        "attempts": attempts,
        "max_attempts": MAX_ATTEMPTS,
        "exhausted": bool(d.status == "failed" and attempts >= MAX_ATTEMPTS),
        "last_error": d.last_error,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
        "person_name": person_name,
        "alert_title": alert.title if alert else None,
        "alert_severity": alert.severity if alert else None,
        "alert_color": alert.color if alert else None,
        "alert_team": alert.team if alert else None,
        "alert_link": f"/#alerts/{d.alert_id}",
        "message_preview": format_delivery_message(alert, d.channel) if alert else None,
    }


def _serialize_many(db: Session, rows: List[Delivery]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    alert_ids = {d.alert_id for d in rows if d.alert_id is not None}
    person_ids = {d.person_id for d in rows if d.person_id is not None}
    alerts_by_id = (
        {a.id: a for a in db.query(Alert).filter(Alert.id.in_(alert_ids)).all()}
        if alert_ids
        else {}
    )
    people_by_id = (
        {p.id: p for p in db.query(Person).filter(Person.id.in_(person_ids)).all()}
        if person_ids
        else {}
    )
    return [_serialize_delivery(d, alerts_by_id, people_by_id) for d in rows]


@router.get("")
def list_deliveries(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    alert_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Delivery)
    if status:
        q = q.filter(Delivery.status == status)
    if channel:
        q = q.filter(Delivery.channel == channel)
    if alert_id is not None:
        q = q.filter(Delivery.alert_id == alert_id)
    rows = q.order_by(Delivery.id.desc()).limit(limit).all()
    return _serialize_many(db, rows)


@router.get("/stats")
def delivery_stats(db: Session = Depends(get_db)):
    grouped = dict(
        db.query(Delivery.status, func.count(Delivery.id))
        .group_by(Delivery.status)
        .all()
    )
    sent = int(grouped.get("sent", 0))
    pending = int(grouped.get("pending", 0))
    failed = int(grouped.get("failed", 0))
    exhausted = int(
        db.query(func.count(Delivery.id))
        .filter(Delivery.status == "failed", Delivery.attempts >= MAX_ATTEMPTS)
        .scalar()
        or 0
    )
    return {
        "total": sent + pending + failed,
        "sent": sent,
        "pending": pending,
        "failed": failed,
        "exhausted": exhausted,
        "channels": list_channel_statuses(db),
    }


@router.get("/channels")
def get_channel_statuses(db: Session = Depends(get_db)):
    return list_channel_statuses(db)


@router.post("/channels/{channel}/outage")
def toggle_channel_outage(
    channel: str,
    payload: OutageToggleIn,
    db: Session = Depends(get_db),
):
    if channel not in CHANNEL_PROVIDERS:
        raise HTTPException(404, f"Unknown channel '{channel}'")
    state = set_channel_outage(db, channel, payload.down, payload.error_message)
    if not payload.down:
        db.query(Delivery).filter(
            Delivery.channel == channel,
            Delivery.status == "failed",
            Delivery.attempts < MAX_ATTEMPTS,
        ).update({Delivery.next_retry_at: None}, synchronize_session=False)
        db.commit()
        flushed = process_pending_deliveries(db, batch_size=100, ignore_backoff=True)
        return {**state, "flushed": flushed}
    return state


@router.post("/retry-failed")
def retry_all_failed(db: Session = Depends(get_db)):
    reset_count = (
        db.query(Delivery)
        .filter(Delivery.status == "failed")
        .update(
            {
                Delivery.status: "pending",
                Delivery.attempts: 0,
                Delivery.last_error: None,
                Delivery.next_retry_at: None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    result = process_pending_deliveries(db, batch_size=100, ignore_backoff=True)
    return {"reset": int(reset_count), **result}


@router.post("/process")
def process_deliveries_now(db: Session = Depends(get_db)):
    return process_pending_deliveries(db, ignore_backoff=True)


@router.post("/{delivery_id}/retry")
def retry_single_delivery(delivery_id: int, db: Session = Depends(get_db)):
    delivery = db.get(Delivery, delivery_id)
    if delivery is None:
        raise HTTPException(404, f"Delivery {delivery_id} not found")
    delivery.status = "pending"
    delivery.attempts = 0
    delivery.last_error = None
    delivery.next_retry_at = None
    db.commit()
    process_pending_deliveries(db, ignore_backoff=True)
    db.refresh(delivery)
    return _serialize_many(db, [delivery])[0]
