"""
Symulator systemów docelowych.

W środowisku demo nie ma prawdziwego counterparty-service, silnika procesów ani pricing-engine.
Zamiast nich są tu udawane serwisy, a aplikacja NAPRAWDĘ wykonuje na nich akcje z runbooka:
sprawdza zdrowie, ponawia proces, restartuje, woła webhook, zakłada ticket, eskaluje.

- Stan każdego serwisu jest w bazie (tabela sim_services), nie w pamięci – każda kopia serwera widzi to samo
  (SKALOWANIE.md, pułapka 3.3). Na demo przełączamy go z ekranu ("działa / nie działa").
- Każde wywołanie trafia do dziennika sim_calls – widać, co aplikacja zrobiła w udawanym świecie.
- Podpięcie prawdziwych systemów = podmiana funkcji w tym pliku (ten sam kontrakt: zwróć (ok, opis)).

Reguły udawanego świata (proste, żeby dało się pokazać oba scenariusze):
- health:   OK, gdy serwis jest zdrowy i nie jest w trakcie restartu
- retry:    proces udaje się, gdy settlement ma workflows_ok i counterparty-service jest zdrowy
- restart:  serwis przez RESTART_SECONDS nie odpowiada, potem wraca ZDROWY (restart naprawia)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import SimCall, SimService

DEFAULT_SERVICES = ("counterparty-service", "settlement", "pricing-engine", "payments-api")
RESTART_SECONDS = float(os.getenv("SIM_RESTART_SECONDS", "5"))
WORKFLOW_DEPENDENCY = "counterparty-service"     # proces rozliczeń zależy od tego serwisu


def ensure_services(db: Session) -> None:
    """Dodaje brakujące udawane serwisy. Bezpieczne przy kilku kopiach naraz (konflikt = ktoś już dodał)."""
    existing = {s.name for s in db.query(SimService.name).all()}
    for name in DEFAULT_SERVICES:
        if name in existing:
            continue
        try:
            with db.begin_nested():
                db.add(SimService(name=name))
                db.flush()
        except IntegrityError:
            pass


def list_services(db: Session) -> list[SimService]:
    ensure_services(db)
    return db.query(SimService).order_by(SimService.name).all()


def set_service(db: Session, name: str, healthy: bool | None = None, workflows_ok: bool | None = None) -> SimService:
    ensure_services(db)
    svc = db.get(SimService, name)
    if svc is None:
        svc = SimService(name=name)
        db.add(svc)
    if healthy is not None:
        svc.healthy = healthy
        svc.restarting_until = None
    if workflows_ok is not None:
        svc.workflows_ok = workflows_ok
    _log(db, name, "admin", f"set healthy={svc.healthy}, workflows_ok={svc.workflows_ok}", True)
    db.flush()
    return svc


def resolve_service(target: str | None) -> str | None:
    """'http://counterparty-service/health' / 'settlement.internal' / 'pricing-engine-eu-1' -> nazwa serwisu."""
    if not target:
        return None
    t = str(target).strip().lower()
    host = urlparse(t).hostname if "://" in t else t.split("/")[0]
    host = host or t
    for name in DEFAULT_SERVICES:
        if host == name or host.split(".")[0] == name or host.startswith(name):
            return name
    first = host.split(".")[0]
    for name in DEFAULT_SERVICES:                      # "settlement-service" -> "settlement"
        if first.startswith(name.split("-")[0]) and len(first) >= 4:
            return name
    return None


def _log(db: Session, service: str | None, action: str, detail: str, ok: bool, alert_id: int | None = None) -> None:
    db.add(SimCall(service=service, action=action, detail=detail[:2000], ok=ok, alert_id=alert_id))


def _svc(db: Session, name: str) -> SimService:
    ensure_services(db)
    svc = db.get(SimService, name)
    if svc is None:
        svc = SimService(name=name)
        db.add(svc)
        db.flush()
    return svc


def _is_up(svc: SimService, now: datetime) -> bool:
    if svc.restarting_until and now < svc.restarting_until:
        return False
    if svc.restarting_until and now >= svc.restarting_until:
        svc.restarting_until = None
        svc.healthy = True                               # po restarcie serwis wraca zdrowy
    return bool(svc.healthy)


# ---------------------------------------------------------------- akcje (zwracają (ok, opis))

def health(db: Session, service: str, alert_id: int | None = None) -> tuple[bool, str]:
    now = datetime.utcnow()
    svc = _svc(db, service)
    up = _is_up(svc, now)
    restarting = bool(svc.restarting_until and now < svc.restarting_until)
    msg = f"{service} responded 200 OK" if up else (
        f"{service} is restarting (503)" if restarting else f"{service} is not responding (503)")
    _log(db, service, "http_get", msg, up, alert_id)
    return up, msg


def retry_workflow(db: Session, workflow_id: str, service: str = "settlement", attempts: int = 2,
                   alert_id: int | None = None) -> tuple[bool, str]:
    now = datetime.utcnow()
    engine = _svc(db, service)
    dependency = _svc(db, WORKFLOW_DEPENDENCY)
    tries = []
    for attempt in range(1, max(1, attempts) + 1):
        ok = _is_up(engine, now) and engine.workflows_ok and _is_up(dependency, now)
        tries.append(ok)
        _log(db, service, "retry_workflow",
             f"retry {attempt}/{attempts} of {workflow_id}: {'succeeded' if ok else 'failed'}", ok, alert_id)
        if ok:
            return True, f"Workflow {workflow_id} retried successfully (attempt {attempt}/{attempts})"
    reason = (f"{WORKFLOW_DEPENDENCY} is down" if not _is_up(dependency, now)
              else f"{service} rejected the retry")
    return False, f"Workflow {workflow_id} failed {attempts}/{attempts} retries ({reason})"


def restart(db: Session, service: str, alert_id: int | None = None) -> tuple[bool, str]:
    svc = _svc(db, service)
    svc.restarting_until = datetime.utcnow() + timedelta(seconds=RESTART_SECONDS)
    _log(db, service, "restart_service", f"restart requested; back in {RESTART_SECONDS:g}s", True, alert_id)
    return True, f"{service} is restarting (back in {RESTART_SECONDS:g}s)"


def webhook(db: Session, url: str, payload: dict[str, Any], alert_id: int | None = None) -> tuple[bool, str]:
    _log(db, resolve_service(url), "webhook", f"POST {url} {payload}", True, alert_id)
    return True, f"Webhook called: POST {url}"


def open_ticket(db: Session, summary: str, alert_id: int | None = None) -> tuple[bool, str]:
    call = SimCall(service="ticketing", action="open_ticket", detail=summary[:2000], ok=True, alert_id=alert_id)
    db.add(call)
    db.flush()                                            # id z bazy = numer ticketu, unikalny na wszystkich kopiach
    ticket = f"SIM-{1000 + call.id}"
    call.detail = f"{ticket}: {summary}"[:2000]
    return True, f"Ticket {ticket} opened"


def escalate(db: Session, team: str, alert_id: int | None = None) -> tuple[bool, str]:
    _log(db, "paging", "escalate", f"paged {team}", True, alert_id)
    return True, f"Escalated to {team}"


def recent_calls(db: Session, limit: int = 50) -> list[SimCall]:
    return db.query(SimCall).order_by(SimCall.id.desc()).limit(limit).all()
