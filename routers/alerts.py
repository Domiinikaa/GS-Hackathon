"""OSOBA 1 – alerty: lista, szczegóły, ack/resolve, live feed."""
from typing import Optional
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Alert
from services.alert_service import upsert_alert
from services.contracts import Match

router = APIRouter(prefix="/api/alerts", tags=["Alerts (Osoba 1)"])


@router.get("")
def list_alerts(team: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Alert)
    if team:
        q = q.filter(Alert.team == team)
    if status:
        q = q.filter(Alert.status == status)
    return q.order_by(Alert.last_seen.desc()).limit(200).all()


class TestAlertRequest(BaseModel):
    """Dane udawanej paczki. Wszystko ma wartości domyślne, więc można nic nie wpisywać."""
    dedup_key: str = "test-payments-errors"
    title: str = "HighErrorRate on payments-api"
    body: Optional[str] = "Error rate 12% over the last 5 minutes"
    team: str = "Payments"
    severity: str = "critical"
    color: str = "red"
    rule_id: str = "anna-payments-critical"


@router.post("/test")
def create_test_alert(req: TestAlertRequest, db: Session = Depends(get_db)):
    """TYLKO DO TESTÓW: udaje Osobę 4 i przepuszcza paczkę przez upsert_alert."""
    match = Match(
        rule_id=req.rule_id,
        team=req.team,
        event_id=None,                 # nie ma prawdziwego zdarzenia
        dedup_key=req.dedup_key,
        title=req.title,
        body=req.body,
        severity=req.severity,
        color=req.color,
        channels=["ui"],
        steps=[
            {"text": "Open the payments dashboard and check if errors are in one region",
             "action": None, "params": {}, "approval": "none"},
            {"text": "Fail traffic over to the other region",
             "action": "failover", "params": {"service": "payments-api"}, "approval": "required"},
        ],
    )
    alert = upsert_alert(db, match)
    db.commit()
    db.refresh(alert)  # po commit obiekt jest "pusty" – wczytaj go z bazy, żeby było co zwrócić
    return alert


@router.get("/stream")
async def stream():
    # TODO (Osoba 1): czytać z kolejki w services/live.py i wysyłać "data: {json}\n\n"
    async def gen():
        while True:
            yield ": keepalive\n\n"
            await asyncio.sleep(15)
    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/{alert_id}")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return alert


@router.post("/{alert_id}/ack")
def ack(alert_id: int, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 1): status=acknowledged + wpis do history")


@router.post("/{alert_id}/resolve")
def resolve(alert_id: int, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 1): status=resolved + wpis do history")


@router.post("/{alert_id}/steps/{step_index}/approve")
def approve_step(alert_id: int, step_index: int, db: Session = Depends(get_db)):
    raise HTTPException(501, "TODO (Osoba 1 + 4): zatwierdzenie ryzykownego kroku runbooka")
