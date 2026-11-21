"""
OSOBA 4 – wykonywanie kroków runbooka w alercie (kartka 2.6).

  "Steps can be actions… Risky actions need a human to approve them first, from the UI or by replying."
  "Record what was done and by whom, and close the alert when the problem goes away."

Rodzaje kroków (services/runbook_parser.step_kind):
  auto            aplikacja robi sama
  approve         aplikacja robi po zatwierdzeniu (przycisk Approve albo SMS "YES kod")
  manual          człowiek robi sam i klika "Mark done"
  approve_manual  zgoda, potem człowiek robi sam i klika "Mark done"

Jak to idzie (advance_alert):
  krok po kroku; krok auto (albo zatwierdzony) aplikacja wykonuje OD RAZU na symulatorze (services/simulator.py),
  zapisuje wynik i idzie dalej; zatrzymuje się na pierwszym kroku, który czeka na człowieka.
  Krok z warunkiem ("if retry fails twice") wykona się tylko, gdy warunek jest spełniony – inaczej "skipped".
  Nieudany krok dostaje status "failed" (procedura idzie dalej); człowiek może kliknąć Retry albo Mark done.

Kiedy ruszamy: po zapisaniu nowego alertu (pipeline), po Approve / Mark done (routers/alerts.py), po Retry.

Wiele kopii serwera (SKALOWANIE.md): wszystko dzieje się pod blokadą wiersza alertu (Postgres: SELECT … FOR UPDATE,
SQLite/laptop: blokada procesu). Krok wykonujemy tylko, gdy jeszcze nie ma statusu – dwie kopie albo dwa
kliknięcia naraz nie wykonają go dwa razy.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from contextlib import contextmanager, nullcontext
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Alert, CustomAction, Event, Person, Runbook, Team
from services import live
from services import simulator as sim
from services.delivery import enqueue_deliveries
from services.people_service import plan_recipients
from services.rules_engine import render_template
from services.runbook_parser import (ACTIONS, FAIL_WORDS, OK_WORDS, condition_checkable, parse_runbook_full,
                                     step_kind)

log = logging.getLogger("runbook_runner")

IS_POSTGRES = engine.dialect.name == "postgresql"
ALLOW_REAL_HTTP = os.getenv("RUNBOOK_ALLOW_REAL_HTTP", "0") == "1"  # domyślnie tylko symulator (bezpieczeństwo)

FINISHED = {"succeeded", "failed", "skipped"}
_local_lock = threading.RLock()


# ---------------------------------------------------------------- blokada alertu

def alert_guard():
    """Blokada procesu dla SQLite (laptop, jedna kopia). Na Postgresie wystarcza blokada wiersza."""
    return nullcontext() if IS_POSTGRES else _local_lock


def lock_alert(db: Session, alert_id: int) -> Alert | None:
    """Świeży alert z bazy; na Postgresie zablokowany do końca transakcji (SELECT … FOR UPDATE)."""
    q = db.query(Alert).filter(Alert.id == alert_id).populate_existing()
    if IS_POSTGRES:
        q = q.with_for_update()
    return q.first()


@contextmanager
def locked_alert(db: Session, alert_id: int):
    """with locked_alert(db, id) as alert: … zmiany … db.commit()  – commit MUSI być w środku."""
    with alert_guard():
        yield lock_alert(db, alert_id)


# ---------------------------------------------------------------- pomocnicze

def _now() -> str:
    return datetime.utcnow().isoformat()


def _set(alert: Alert, i: int, **fields: Any) -> None:
    steps = [dict(s) for s in (alert.steps or [])]
    steps[i].update(fields)
    alert.steps = steps                      # NOWA lista – inaczej baza nie zauważy zmiany w JSON


def _hist(alert: Alert, who: str, what: str) -> None:
    alert.history = (alert.history or []) + [{"at": _now(), "who": who, "what": what}]


def is_finished(step: dict[str, Any]) -> bool:
    return bool(step.get("done")) or step.get("status") in FINISHED


def _outcome(step: dict[str, Any]) -> str | None:
    """succeeded / failed z punktu widzenia warunków; krok zrobiony ręcznie liczy się jako udany."""
    if step.get("done"):
        return "succeeded"
    return step.get("status") if step.get("status") in ("succeeded", "failed") else None


_TOPIC = (("retry", "retry_workflow"), ("restart", "restart_service"), ("health", "http_get"),
          ("check", "http_get"), ("ticket", "open_ticket"), ("webhook", "webhook"), ("escalat", "escalate"))


def evaluate_condition(condition: str, steps: list[dict[str, Any]], index: int) -> bool | None:
    """True / False z wyniku wcześniejszego kroku ("if retry fails twice"); None, gdy aplikacja nie wie."""
    done_before = [s for s in steps[:index] if _outcome(s)]
    if not done_before or not condition_checkable(condition):
        return None
    c = condition.lower()
    topic = next((a for word, a in _TOPIC if word in c), None)
    prev = next((s for s in reversed(done_before) if topic and s.get("action") == topic), done_before[-1])
    if FAIL_WORDS.search(condition):
        return _outcome(prev) == "failed"
    return _outcome(prev) == "succeeded" if OK_WORDS.search(condition) else None


# ---------------------------------------------------------------- wykonanie jednej akcji

# ---------------------------------------------------------------- własne akcje zespołu (dodawane w UI)

def custom_actions(db: Session) -> dict[str, dict[str, Any]]:
    """{"clear_cache": {"label": "Clear cache", "risky": True}} – do parsera runbooków."""
    return {a.key: {"label": a.label, "risky": bool(a.risky)} for a in db.query(CustomAction).all()}


def run_custom_action(db: Session, step: dict[str, Any], alert: Alert) -> tuple[bool, str]:
    """Akcja zespołu = POST na jej adres, z wartościami ze zdarzenia ({{service}}). Adres bierzemy z bazy przy
    wykonaniu, więc zmiana w UI działa od razu dla wszystkich runbooków. Domyślnie przez symulator."""
    key = step.get("action")
    action = db.query(CustomAction).filter(CustomAction.key == key).first()
    if action is None:
        return False, f"Unknown action {key!r} – add it in Runbooks → Actions the app can run"
    event = db.get(Event, alert.last_event_id) if alert.last_event_id else None
    data = {**((event.payload if event and isinstance(event.payload, dict) else {}) or {}), **(step.get("params") or {})}
    url = render_template(action.url, data) or action.url
    if "{{" in url:
        return False, f"{action.label}: can't fill {url} – the event has no such field"
    body = {"action": key, "alert_id": alert.id, "alert": alert.title, "step": step.get("text")}
    if ALLOW_REAL_HTTP:
        import httpx
        r = httpx.post(url, json=body, timeout=5, follow_redirects=False)
        return r.status_code < 400, f"{action.label}: POST {url} -> {r.status_code}"
    sim.webhook(db, url, body, alert.id)
    return True, f"{action.label}: POST {url} (simulated)"


def execute_step(db: Session, step: dict[str, Any], alert: Alert) -> tuple[bool, str]:
    """Wykonuje akcję kroku na symulatorze. Zwraca (udało się?, opis dla człowieka).
    Nowa akcja bez kodu: Runbooks → Actions (run_custom_action); wbudowana: runbook_parser.ACTIONS + gałąź tutaj."""
    action = step.get("action")
    p = step.get("params") or {}
    aid = alert.id
    if step.get("custom") or (action and action not in ACTIONS):
        try:
            return run_custom_action(db, step, alert)
        except Exception as exc:  # noqa: BLE001
            log.exception("runbook: custom action %s failed", action)
            return False, f"Error while running {action}: {exc}"
    try:
        if action == "http_get":
            url = p.get("url")
            service = sim.resolve_service(url) or sim.resolve_service(p.get("service"))
            if service:
                return sim.health(db, service, aid)
            if url and ALLOW_REAL_HTTP:
                import httpx
                r = httpx.get(url, timeout=5, follow_redirects=False)
                return r.status_code < 400, f"GET {url} -> {r.status_code}"
            return False, f"{url or 'target'} is not a simulated service (real HTTP calls are switched off)"
        if action == "retry_workflow":
            service = sim.resolve_service(p.get("service")) or "settlement"
            return sim.retry_workflow(db, str(p.get("workflowId") or "unknown"), service,
                                      int(p.get("attempts") or 2), aid)
        if action == "restart_service":
            service = sim.resolve_service(p.get("service"))
            if not service:
                return False, f"Unknown service {p.get('service')!r} – restart it yourself"
            return sim.restart(db, service, aid)
        if action == "webhook":
            return sim.webhook(db, str(p.get("url") or "webhook"), p, aid)
        if action == "open_ticket":
            return sim.open_ticket(db, str(p.get("summary") or step.get("text") or alert.title), aid)
        if action == "escalate":
            return escalate_to_team(db, alert, str(p.get("team") or p.get("target") or alert.team))
        if action == "wait":
            return True, f"Waited {p.get('seconds', 0)}s (simulated)"
        return False, f"Unknown action {action!r}"
    except Exception as exc:  # noqa: BLE001 – zepsuta akcja nie może wywrócić alertu
        log.exception("runbook: action %s failed", action)
        return False, f"Error while running {action}: {exc}"


# ---------------------------------------------------------------- eskalacja do innego zespołu

_FILLER = re.compile(r"\b(the|team|on-?call|person|people|engineers?)\b|[^\w\s-]", re.I)


def _norm(name: str) -> str:
    return " ".join(_FILLER.sub(" ", name.lower().replace("-", " ")).split())


def resolve_team(db: Session, target: str) -> str | None:
    """'the Settlements on-call' / 'pricing on-call person' / 'counterparty-support' -> nazwa zespołu z bazy."""
    names = {t.name for t in db.query(Team.name).all()} | {p.team for p in db.query(Person.team).distinct() if p.team}
    wanted = _norm(target)
    if not wanted:
        return None
    for name in names:                                      # najpierw dokładnie ("counterparty-support")
        if name.lower() == target.strip().lower() or _norm(name) == wanted:
            return name
    for name in sorted(names, key=len, reverse=True):       # potem nazwa zespołu jako słowo w tekście ("pricing")
        if _norm(name) and re.search(rf"\b{re.escape(_norm(name))}\b", wanted):
            return name
    return None


def escalate_to_team(db: Session, alert: Alert, target: str) -> tuple[bool, str]:
    """Powiadamia ludzi z innego zespołu tym samym torem co nowy alert: preferencje i godziny (Osoba 2),
    wysyłka z ponawianiem przez Outbox (Osoba 3). "…on-call" = tylko osoby na dyżurze, jeśli są."""
    team = resolve_team(db, target)
    if team is None:
        return False, f"No team called “{target}” – add it (and its people) in Admin / People"
    planned = plan_recipients(db, team, alert.severity or "critical", ["phone", "sms", "email"])
    recipients = [pr.recipient for pr in planned if pr.recipient.to]
    if re.search(r"on-?call", target, re.I):
        on_call = {p.id for p in db.query(Person).filter(Person.team == team, Person.on_call.is_(True))}
        recipients = [r for r in recipients if r.person_id in on_call] or recipients
    if not recipients:
        return False, f"Nobody in team {team} has a phone or e-mail – add them in People"
    enqueue_deliveries(db, alert, recipients)
    sim.escalate(db, team, alert.id)                         # wpis w dzienniku symulatora (panel na stronie)
    who = ", ".join(f"{r.name} ({r.channel})" for r in recipients)
    return True, f"Escalated to {team}: {who}"[:500]


def _run(db: Session, alert: Alert, i: int, who: str = "system") -> None:
    ok, message = execute_step(db, alert.steps[i], alert)
    _set(alert, i, status="succeeded" if ok else "failed", result=message, finished_at=_now(), executed_by=who)
    _hist(alert, who, f"{'✅' if ok else '❌'} step {i + 1} ({alert.steps[i].get('action')}): {message}")


# ---------------------------------------------------------------- serce: co dalej z alertem

def _advance(db: Session, alert: Alert) -> bool:
    """Idzie po krokach: wykonuje kroki aplikacji, zatrzymuje się na człowieku. Wołać pod blokadą alertu."""
    if alert.status == "resolved":
        return False
    changed = False
    for i in range(len(alert.steps or [])):
        step = alert.steps[i]
        if is_finished(step):
            continue
        condition = step.get("condition")
        if condition and evaluate_condition(condition, alert.steps, i) is False:
            _set(alert, i, status="skipped", result=f"Skipped – condition not met: {condition}")
            _hist(alert, "system", f"skipped step {i + 1} (condition not met: {condition})")
            changed = True
            continue

        kind = step_kind(step)
        approved = bool(step.get("approved_by"))
        if kind == "manual" or (kind == "approve_manual" and approved):
            if step.get("status") != "waiting":
                _set(alert, i, status="waiting", result="Do this yourself, then mark it done")
                changed = True
            return changed
        if kind in ("approve", "approve_manual") and not approved:
            if step.get("status") != "waiting_approval":
                cant_check = condition and not condition_checkable(condition)
                note = f"The app can't check “{condition}” – approve if it is true" if cant_check else "Waiting for approval"
                _set(alert, i, status="waiting_approval", result=note)
                _hist(alert, "system", f"step {i + 1} waits for approval: {step.get('text', '')}")
                changed = True
            return changed

        _run(db, alert, i)                              # auto albo zatwierdzony -> aplikacja robi od razu
        changed = True

    if alert.steps and not any(h.get("what") == "runbook finished" for h in (alert.history or [])):
        _hist(alert, "system", "runbook finished")
        changed = True
    return changed


def advance_alert(alert_id: int) -> None:
    """Pcha runbook alertu do przodu (własna sesja i commit). Bezpieczne do wołania wiele razy."""
    db = SessionLocal()
    try:
        with locked_alert(db, alert_id) as alert:
            if alert is not None and _advance(db, alert):
                live.publish(alert)                      # przed commit – patrz services/live.py
            db.commit()
    except Exception:  # noqa: BLE001 – runbook nie może wywrócić przyjmowania zdarzeń / kliknięć
        db.rollback()
        log.exception("runbook: advance failed for alert %s", alert_id)
    finally:
        db.close()


def start_after_commit(db: Session, alert_id: int) -> None:
    """Pipeline woła to dla NOWEGO alertu; kroki ruszą dopiero, gdy zapis alertu się uda (po commit)."""
    db.info.setdefault("runbook_new_alerts", set()).add(alert_id)
    if db.info.get("runbook_hooked"):
        return
    db.info["runbook_hooked"] = True

    def _after_commit(session: Session) -> None:
        for aid in sorted(session.info.pop("runbook_new_alerts", set())):
            advance_alert(aid)

    sa_event.listen(db, "after_commit", _after_commit)
    sa_event.listen(db, "after_soft_rollback", lambda s, _tx: s.info.pop("runbook_new_alerts", None))


# ---------------------------------------------------------------- Retry

def retry_step(db: Session, alert_id: int, index: int, user: Any) -> Alert:
    """Ponawia nieudany krok. Krok ze zgodą może ponowić tylko lead / admin – ponowienie to też zgoda."""
    with alert_guard():
        alert = lock_alert(db, alert_id)
        if alert is None:
            raise HTTPException(404, "Alert not found")
        if alert.status == "resolved":
            raise HTTPException(409, "Alert is already resolved")
        if not 0 <= index < len(alert.steps or []):
            raise HTTPException(404, "No such step")
        step = alert.steps[index]
        if step.get("status") != "failed" or step.get("done"):
            raise HTTPException(409, "Only a failed step can be retried")
        if step.get("approval") == "required":
            from routers.alerts import _check_approve_permission  # ta sama zasada co Approve (Osoba 1)
            _check_approve_permission(db, alert, user)
        who = getattr(user, "uname", None) or "anonymous"
        _set(alert, index, run_no=int(step.get("run_no") or 1) + 1)
        _run(db, alert, index, who)
        _advance(db, alert)
        live.publish(alert)
        db.commit()
    db.refresh(alert)
    return alert


# ---------------------------------------------------------------- "problem minął" -> zamknij alert

RECOVERY_WORDS = {"resolved", "ok", "recovered", "closed", "cleared", "normal", "healthy", "up"}


def is_recovery(payload: Any) -> bool:
    """Zdarzenie mówi, że problem minął: {"status": "resolved"} (Alertmanager z kartki), state: ok itp."""
    if not isinstance(payload, dict):
        return False
    return any(str(payload.get(k, "")).strip().lower() in RECOVERY_WORDS for k in ("status", "state"))


def resolve_recovered(db: Session, dedup_key: str, rule_id: str) -> int | None:
    """Zamyka otwarty alert o tym kluczu (bez commit – robi go pipeline). Zwraca id albo None."""
    alert = (db.query(Alert).filter(Alert.dedup_key == dedup_key, Alert.status != "resolved")
             .order_by(Alert.id.desc()).first())
    if alert is None:
        return None
    alert.status = "resolved"
    _hist(alert, "system", f"resolved – the problem went away (recovery event for rule {rule_id})")
    live.publish(alert)
    return alert.id


# ---------------------------------------------------------------- start serwera

def upgrade_runbook_steps(db: Session) -> int:
    """Runbooki zapisane przed runnerem nie mają warunków ani rodzajów kroków – parsujemy je ponownie."""
    n = 0
    custom = custom_actions(db)
    for rb in db.query(Runbook).all():
        if rb.steps and all("condition" in s for s in rb.steps):
            continue
        try:
            rb.steps = parse_runbook_full(rb.raw, rb.format or "auto", custom).steps
            n += 1
        except ValueError:
            log.warning("runbook %s could not be re-parsed", rb.id)
    if n:
        db.commit()
    return n
