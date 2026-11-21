"""
OSOBA 4 – wykonywanie kroków runbooka w alercie.

Rodzaje kroków (services/runbook_parser.step_kind):
  manual          człowiek robi sam i klika "Mark done"
  auto            aplikacja robi sama
  approve         aplikacja robi po zatwierdzeniu (UI albo SMS "YES …")
  approve_manual  zgoda, potem człowiek robi sam i klika "Mark done"

Kolejność: krok po kroku. Kroki auto lecą same, aż do pierwszego kroku, który czeka na człowieka.

Zatwierdzanie: można zatwierdzić kilka kroków naraz (approve_until), najwyżej do pierwszego kroku manual.
Zatwierdza lead zespołu albo admin (ta sama zasada co przycisk Approve Osoby 1).

Zły wynik ≠ błąd:
  - zły wynik (serwis nie odpowiada, retry nie przeszedł) nie zatrzymuje procedury, gdy krok tylko sprawdzał
    (akcja "check") albo gdy któryś następny krok ma warunek, który ten wynik obsługuje ("if retry fails twice")
  - w przeciwnym razie, i przy błędzie technicznym (wyjątek, nieznany serwis), krok dostaje status "error":
    procedura stoi, zebrane zgody na dalsze kroki są kasowane, człowiek wybiera Ponów albo Przerwij procedurę

Statusy kroku: None (jeszcze nie doszliśmy) | queued | running | waiting (człowiek robi) |
               waiting_approval | succeeded | failed (zły wynik, idziemy dalej) | skipped (warunek niespełniony) |
               error (procedura stoi) | cancelled (procedura przerwana)

Wiele kopii serwera (SKALOWANIE.md):
  - stan kroków jest w alercie w bazie; zmiany robimy pod blokadą wiersza (Postgres: SELECT … FOR UPDATE,
    SQLite/laptop: blokada procesu) – dwie zmiany naraz się nie nadpiszą
  - krok do wykonania trafia do kolejki step_jobs z unikalną trójką (alert, krok, podejście) -> najwyżej raz
  - worker działa na KAŻDEJ kopii, ale zadanie bierze jedna: warunkowy UPDATE 'queued' -> 'running'
  - sama akcja (np. restart) wykonuje się POZA blokadą; wynik zapisujemy znowu pod blokadą
  - zadanie wzięte przez kopię, która padła, wraca do kolejki po STALE_AFTER
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import event as sa_event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Alert, Runbook, StepJob
from services import live
from services import simulator as sim
from services.runbook_parser import (ACTIONS, FAIL_WORDS, OK_WORDS, condition_checkable, parse_runbook_full,
                                     step_kind)

log = logging.getLogger("runbook_runner")

IS_POSTGRES = engine.dialect.name == "postgresql"
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
POLL_SECONDS = float(os.getenv("RUNBOOK_POLL_SECONDS", "1"))
SWEEP_SECONDS = float(os.getenv("RUNBOOK_SWEEP_SECONDS", "15"))
STALE_AFTER = timedelta(minutes=float(os.getenv("RUNBOOK_STALE_MINUTES", "10")))
WAIT_SCALE = float(os.getenv("RUNBOOK_WAIT_SCALE", "1"))          # np. 0.05 na demo: "wait 2 min" = 6 s
ALLOW_REAL_HTTP = os.getenv("RUNBOOK_ALLOW_REAL_HTTP", "0") == "1"  # domyślnie tylko symulator (bezpieczeństwo)

FINISHED = {"succeeded", "failed", "skipped", "cancelled"}
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

def _now() -> datetime:
    return datetime.utcnow()


def _set(alert: Alert, i: int, **fields: Any) -> None:
    steps = [dict(s) for s in (alert.steps or [])]
    for k, v in fields.items():
        if v is None:
            steps[i].pop(k, None)
        else:
            steps[i][k] = v
    alert.steps = steps                      # NOWA lista – inaczej baza nie zauważy zmiany w JSON


def _hist(alert: Alert, who: str, what: str) -> None:
    alert.history = (alert.history or []) + [{"at": _now().isoformat(), "who": who, "what": what}]


def _who(user: Any) -> str:
    return getattr(user, "uname", None) or "anonymous"


def is_finished(step: dict[str, Any]) -> bool:
    return bool(step.get("done")) or step.get("status") in FINISHED


def is_aborted(alert: Alert) -> bool:
    return any(s.get("status") == "cancelled" for s in (alert.steps or []))


def current_index(alert: Alert) -> int | None:
    """Pierwszy niezakończony krok (tam jest teraz procedura)."""
    return next((i for i, s in enumerate(alert.steps or []) if not is_finished(s)), None)


def _outcome(step: dict[str, Any]) -> str | None:
    """succeeded / failed z punktu widzenia warunków; krok zrobiony ręcznie liczy się jako udany."""
    if step.get("status") in ("succeeded", "failed"):
        return step["status"]
    if step.get("done"):
        return "succeeded"
    return None


_TOPIC = (("retry", "retry_workflow"), ("re-run", "retry_workflow"), ("rerun", "retry_workflow"),
          ("restart", "restart_service"), ("health", "http_get"), ("check", "http_get"),
          ("ticket", "open_ticket"), ("webhook", "webhook"), ("escalat", "escalate"))


def _topic(condition: str) -> str | None:
    c = condition.lower()
    return next((a for word, a in _TOPIC if word in c), None)


def evaluate_condition(condition: str, steps: list[dict[str, Any]], index: int) -> bool | None:
    """True / False, gdy da się ocenić z wyników wcześniejszych kroków; None, gdy aplikacja nie wie."""
    done_before = [s for s in steps[:index] if _outcome(s)]
    if not done_before or not condition_checkable(condition):
        return None
    topic = _topic(condition)
    prev = next((s for s in reversed(done_before) if topic and s.get("action") == topic), done_before[-1])
    if FAIL_WORDS.search(condition):
        return _outcome(prev) == "failed"
    if OK_WORDS.search(condition):
        return _outcome(prev) == "succeeded"
    return None


def handled_by_later_condition(steps: list[dict[str, Any]], index: int) -> bool:
    """Czy zły wynik kroku `index` obsługuje warunek któregoś następnego kroku ("if retry fails twice")."""
    action = steps[index].get("action")
    for j in range(index + 1, len(steps)):
        cond = steps[j].get("condition")
        if not cond or is_finished(steps[j]) or not condition_checkable(cond):
            continue
        topic = _topic(cond)
        if topic == action or (topic is None and j == index + 1):
            return True
    return False


def _enqueue(db: Session, alert_id: int, index: int, run_no: int, run_after: datetime) -> bool:
    """Dodaje krok do kolejki. False, gdy już tam był (unikalna trójka) – nic nie wykona się 2 razy."""
    try:
        with db.begin_nested():
            db.add(StepJob(alert_id=alert_id, step_index=index, run_no=run_no, run_after=run_after))
            db.flush()
        return True
    except IntegrityError:
        return False


# ---------------------------------------------------------------- serce: co dalej z alertem

def _advance(db: Session, alert: Alert) -> bool:
    """Idzie po krokach i ustawia następny ruch. Wołać pod locked_alert. Zwraca True, gdy coś zmienił."""
    if alert.status == "resolved" or is_aborted(alert):
        return False
    changed = False
    i = 0
    while i < len(alert.steps or []):
        step = alert.steps[i]
        if is_finished(step):
            i += 1
            continue
        status = step.get("status")
        if status in ("queued", "running", "error"):
            return changed                                   # krok w trakcie albo procedura stoi po błędzie

        condition = step.get("condition")
        verdict = evaluate_condition(condition, alert.steps, i) if condition else True
        if verdict is False:
            _set(alert, i, status="skipped", result=f"Skipped – condition not met: {condition}",
                 finished_at=_now().isoformat())
            _hist(alert, "system", f"skipped step {i + 1} (condition not met: {condition})")
            changed = True
            i += 1
            continue

        kind = step_kind(step)
        if verdict is None and condition and kind == "auto":
            # aplikacja nie umie sprawdzić warunku -> człowiek potwierdza, że jest spełniony
            _set(alert, i, approval="required")
            kind = "approve"

        if kind == "manual":
            if status != "waiting":
                note = f"Do this yourself if: {condition}" if condition else "Do this yourself, then mark it done"
                _set(alert, i, status="waiting", result=note)
                changed = True
            return changed

        if kind == "approve_manual":
            target = "waiting" if step.get("approved_by") else "waiting_approval"
            if status != target:
                note = ("Approved – do it yourself, then mark it done" if step.get("approved_by")
                        else "Needs approval before anyone does it")
                _set(alert, i, status=target, result=note)
                changed = True
            return changed

        if kind == "approve" and not step.get("approved_by"):
            if status != "waiting_approval":
                note = (f"The app can't check “{condition}” – approve if it is true"
                        if condition and not condition_checkable(condition) else "Waiting for approval")
                _set(alert, i, status="waiting_approval", result=note)
                _hist(alert, "system", f"step {i + 1} waits for approval: {step.get('text', '')}")
                changed = True
            return changed

        # auto albo zatwierdzony -> do kolejki
        run_after = _now()
        note = "Queued"
        if step.get("action") == "wait":
            seconds = float((step.get("params") or {}).get("seconds") or 0) * WAIT_SCALE
            run_after += timedelta(seconds=seconds)
            note = f"Waiting until {run_after.strftime('%H:%M:%S')} UTC"
        if _enqueue(db, alert.id, i, int(step.get("run_no") or 1), run_after):
            _set(alert, i, status="queued", result=note, queued_at=_now().isoformat())
            changed = True
        return changed

    if (alert.steps and all(is_finished(s) for s in alert.steps)
            and not any(h.get("what") == "runbook finished" for h in (alert.history or []))):
        _hist(alert, "system", "runbook finished")
        changed = True
    return changed


def advance_alert(alert_id: int) -> None:
    """Pcha runbook alertu do przodu (własna sesja i commit). Bezpieczne do wołania wiele razy."""
    db = SessionLocal()
    try:
        with locked_alert(db, alert_id) as alert:
            if alert is not None and _advance(db, alert):
                live.publish(alert)                          # przed commit – patrz services/live.py
            db.commit()
    except Exception:  # noqa: BLE001 – runbook nie może wywrócić przyjmowania zdarzeń / kliknięć
        db.rollback()
        log.exception("runbook: advance failed for alert %s", alert_id)
    finally:
        db.close()


def on_alerts_saved(alert_ids: list[int]) -> None:
    for alert_id in dict.fromkeys(alert_ids):
        advance_alert(alert_id)


def start_after_commit(db: Session, alert_id: int) -> None:
    """Pipeline woła to dla NOWEGO alertu; kroki ruszą dopiero, gdy zapis alertu się uda (po commit)."""
    pending: set = db.info.setdefault("runbook_new_alerts", set())
    pending.add(alert_id)
    if db.info.get("runbook_hooked"):
        return
    db.info["runbook_hooked"] = True

    def _after_commit(session: Session) -> None:
        ids = list(session.info.pop("runbook_new_alerts", set()))
        if ids:
            on_alerts_saved(ids)

    def _after_rollback(session: Session) -> None:
        session.info.pop("runbook_new_alerts", None)

    sa_event.listen(db, "after_commit", _after_commit)
    sa_event.listen(db, "after_soft_rollback", lambda s, _tx: _after_rollback(s))


# ---------------------------------------------------------------- decyzje człowieka

def _check_approver(db: Session, alert: Alert, user: Any) -> None:
    from routers.alerts import _check_approve_permission  # ta sama zasada co przycisk Approve (Osoba 1)
    _check_approve_permission(db, alert, user)


def _approvable_until(alert: Alert, index: int) -> list[int]:
    """Kroki do zatwierdzenia od obecnego do `index` włącznie; HTTPException, gdy zakres przekracza manual."""
    steps = alert.steps or []
    if not 0 <= index < len(steps):
        raise HTTPException(404, "No such step")
    cur = current_index(alert)
    if cur is None or index < cur:
        raise HTTPException(409, "This step is already finished")
    to_approve = []
    for j in range(cur, index + 1):
        st = steps[j]
        if is_finished(st):
            continue
        if st.get("status") == "error":
            raise HTTPException(409, f"Step {j + 1} failed – retry it or abort the runbook first")
        kind = step_kind(st)
        if kind == "manual":
            raise HTTPException(409, f"Step {j + 1} is done by a person – you can approve only up to it")
        if kind == "approve_manual" and j < index and not st.get("done"):
            raise HTTPException(409, f"Step {j + 1} is done by a person after approval – "
                                     f"you can approve only up to it")
        if st.get("approval") == "required" and not st.get("approved_by"):
            to_approve.append(j)
    if not to_approve:
        raise HTTPException(409, "Nothing to approve up to this step")
    return to_approve


def approval_limit(alert: Alert) -> int | None:
    """Ostatni krok, który można zatwierdzić jednym ruchem ("YES ALL"): tuż przed pierwszym manual."""
    cur = current_index(alert)
    if cur is None:
        return None
    limit = None
    for j in range(cur, len(alert.steps or [])):
        st = alert.steps[j]
        if is_finished(st):
            continue
        if st.get("status") == "error":
            break
        kind = step_kind(st)
        if kind == "manual":
            break
        limit = j
        if kind == "approve_manual":
            break
    return limit


def _live_alert(db: Session, alert_id: int) -> Alert:
    alert = lock_alert(db, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    if alert.status == "resolved":
        raise HTTPException(409, "Alert is already resolved")
    if is_aborted(alert):
        raise HTTPException(409, "The runbook was aborted")
    return alert


def approve_until(db: Session, alert_id: int, index: int, user: Any, via: str = "") -> Alert:
    """Zatwierdza wszystkie kroki od obecnego do `index` (najwyżej do pierwszego manual)."""
    with alert_guard():
        alert = _live_alert(db, alert_id)
        to_approve = _approvable_until(alert, index)
        _check_approver(db, alert, user)
        who, now = _who(user), _now().isoformat()
        for j in to_approve:
            _set(alert, j, approved_by=who, approved_at=now)
        nums = [str(j + 1) for j in to_approve]
        label = f"step {nums[0]}" if len(nums) == 1 else f"steps {', '.join(nums)}"
        _hist(alert, who, f"approved {label}" + (f" ({via})" if via else ""))
        _advance(db, alert)
        live.publish(alert)
        db.commit()
    db.refresh(alert)
    return alert


def retry_step(db: Session, alert_id: int, index: int, user: Any) -> Alert:
    """"Ponów" po błędzie. Krok ze zgodą może ponowić tylko lead / admin – ponowienie to też zgoda."""
    with alert_guard():
        alert = _live_alert(db, alert_id)
        steps = alert.steps or []
        if not 0 <= index < len(steps):
            raise HTTPException(404, "No such step")
        step = steps[index]
        if step.get("status") != "error" or step.get("done"):
            raise HTTPException(409, "Only a failed step that stopped the runbook can be retried")
        who = _who(user)
        fields: dict[str, Any] = {"status": None, "result": None, "finished_at": None,
                                  "run_no": int(step.get("run_no") or 1) + 1}
        if step.get("approval") == "required":
            _check_approver(db, alert, user)
            fields.update(approved_by=who, approved_at=_now().isoformat())
        _set(alert, index, **fields)
        _hist(alert, who, f"retried step {index + 1}: {step.get('text', '')}")
        _advance(db, alert)
        live.publish(alert)
        db.commit()
    db.refresh(alert)
    return alert


def abort_runbook(db: Session, alert_id: int, user: Any) -> Alert:
    """"Przerwij procedurę": pozostałe kroki anulowane, alert zostaje otwarty (ludzie działają dalej sami)."""
    with alert_guard():
        alert = _live_alert(db, alert_id)
        left = [i for i, s in enumerate(alert.steps or []) if not is_finished(s) and s.get("status") != "running"]
        if not left:
            raise HTTPException(409, "There is nothing left to abort")
        for i in left:
            s = alert.steps[i]
            note = f"{s.get('result')} – runbook aborted" if s.get("status") == "error" else "Cancelled – runbook aborted"
            _set(alert, i, status="cancelled", result=note)
        # krok "running" dokończy się sam; zadania jeszcze w kolejce zamykamy
        db.query(StepJob).filter(StepJob.alert_id == alert_id, StepJob.status == "queued") \
            .update({"status": "finished"}, synchronize_session=False)
        _hist(alert, _who(user), "aborted the runbook")
        live.publish(alert)
        db.commit()
    db.refresh(alert)
    return alert


def _on_error(alert: Alert, index: int, message: str) -> None:
    """Krok zatrzymał procedurę: kasujemy zgody na dalsze kroki – sytuacja jest inna, pytamy od nowa."""
    cleared = []
    for j in range(index + 1, len(alert.steps or [])):
        st = alert.steps[j]
        if st.get("approved_by") and not is_finished(st):
            _set(alert, j, approved_by=None, approved_at=None,
                 status=None if st.get("status") == "waiting" else st.get("status"))
            cleared.append(str(j + 1))
    note = f" – approvals for steps {', '.join(cleared)} cleared, approve again" if cleared else ""
    _hist(alert, "system", f"⛔ step {index + 1} stopped the runbook: {message}{note}")


# ---------------------------------------------------------------- wykonanie jednej akcji

def execute_step(db: Session, step: dict[str, Any], alert: Alert) -> tuple[str, str]:
    """Wykonuje akcję kroku na symulatorze. Zwraca (ok | bad | error, opis dla człowieka).

    ok    – udało się
    bad   – akcja zadziałała, ale wynik jest zły (serwis nie odpowiada, retry nie przeszedł)
    error – nie dało się wykonać (wyjątek, nieznany serwis / akcja)
    """
    action = step.get("action")
    p = step.get("params") or {}
    aid = alert.id

    def done(result: tuple[bool, str]) -> tuple[str, str]:
        return ("ok" if result[0] else "bad"), result[1]

    try:
        if action == "http_get":
            url = p.get("url")
            service = sim.resolve_service(url) or sim.resolve_service(p.get("service"))
            if service:
                return done(sim.health(db, service, aid))
            if url and ALLOW_REAL_HTTP:
                import httpx
                r = httpx.get(url, timeout=5, follow_redirects=False)
                return ("ok" if r.status_code < 400 else "bad"), f"GET {url} -> {r.status_code}"
            return "error", f"{url or 'target'} is not a simulated service (real HTTP calls are switched off)"
        if action == "retry_workflow":
            service = sim.resolve_service(p.get("service")) or "settlement"
            return done(sim.retry_workflow(db, str(p.get("workflowId") or "unknown"), service,
                                           int(p.get("attempts") or 2), aid))
        if action == "restart_service":
            service = sim.resolve_service(p.get("service"))
            if not service:
                return "error", f"Unknown service {p.get('service')!r} – restart it yourself"
            return done(sim.restart(db, service, aid))
        if action == "webhook":
            return done(sim.webhook(db, str(p.get("url") or "webhook"), p, aid))
        if action == "open_ticket":
            return done(sim.open_ticket(db, str(p.get("summary") or step.get("text") or alert.title), aid))
        if action == "escalate":
            return done(sim.escalate(db, str(p.get("team") or p.get("target") or alert.team), aid))
        if action == "wait":
            return "ok", f"Waited {p.get('seconds', 0)}s"
        return "error", f"Unknown action {action!r}"
    except Exception as exc:  # noqa: BLE001
        log.exception("runbook: action %s failed", action)
        return "error", f"Error while running {action}: {exc}"


def run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(StepJob, job_id)
        if job is None:
            return
        idx = job.step_index

        # 1) oznacz krok jako "running" (pod blokadą)
        with locked_alert(db, job.alert_id) as alert:
            step = (alert.steps or [])[idx] if alert and idx < len(alert.steps or []) else None
            if (alert is None or step is None or alert.status == "resolved" or is_finished(step)
                    or step.get("status") != "queued" or int(step.get("run_no") or 1) != job.run_no):
                job.status = "finished"
                db.commit()
                return
            _set(alert, idx, status="running", started_at=_now().isoformat())
            live.publish(alert)
            db.commit()
            step = dict(alert.steps[idx])

        # 2) wykonaj akcję (POZA blokadą – restart może chwilę trwać)
        outcome, message = execute_step(db, step, alert)
        db.commit()

        # 3) zapisz wynik i idź dalej (pod blokadą)
        with locked_alert(db, job.alert_id) as alert:
            current = alert.steps[idx]
            if not current.get("done") and current.get("status") == "running":
                if outcome == "ok":
                    status = "succeeded"
                elif outcome == "bad" and (ACTIONS.get(step.get("action"), {}).get("check")
                                           or handled_by_later_condition(alert.steps, idx)):
                    status = "failed"                        # zły wynik, ale procedura wie, co dalej
                else:
                    status = "error"
                _set(alert, idx, status=status, result=message,
                     finished_at=_now().isoformat(), executed_by="system")
                icon = {"succeeded": "✅", "failed": "❌", "error": "⛔"}[status]
                _hist(alert, "system", f"{icon} step {idx + 1} ({step.get('action')}): {message}")
                if status == "error":
                    _on_error(alert, idx, message)
            db.query(StepJob).filter(StepJob.id == job_id).update({"status": "finished"})
            _advance(db, alert)
            live.publish(alert)
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("runbook: job %s failed", job_id)
    finally:
        db.close()


# ---------------------------------------------------------------- kolejka i worker

def claim_job(db: Session) -> int | None:
    """Bierze jedno zadanie gotowe do wykonania. Dwie kopie nigdy nie wezmą tego samego (warunkowy UPDATE)."""
    now = _now()
    db.query(StepJob).filter(StepJob.status == "running", StepJob.claimed_at < now - STALE_AFTER) \
        .update({"status": "queued", "claimed_by": None}, synchronize_session=False)
    db.commit()
    ids = [r.id for r in db.query(StepJob.id)
           .filter(StepJob.status == "queued", StepJob.run_after <= now)
           .order_by(StepJob.id).limit(10)]
    for job_id in ids:
        taken = db.query(StepJob).filter(StepJob.id == job_id, StepJob.status == "queued") \
            .update({"status": "running", "claimed_at": now, "claimed_by": WORKER_ID}, synchronize_session=False)
        db.commit()
        if taken == 1:
            return job_id
    return None


def run_pending_once() -> bool:
    db = SessionLocal()
    try:
        job_id = claim_job(db)
    finally:
        db.close()
    if job_id is None:
        return False
    run_job(job_id)
    return True


def run_until_idle(max_jobs: int = 100) -> int:
    """Do testów i ręcznego odpalenia: wykonuje gotowe zadania, aż kolejka będzie pusta."""
    n = 0
    while n < max_jobs and run_pending_once():
        n += 1
    return n


def sweep() -> int:
    """Siatka bezpieczeństwa: nowe alerty, których kroki nie ruszyły (np. kopia padła tuż po zapisie)."""
    db = SessionLocal()
    try:
        rows = (db.query(Alert.id, Alert.steps).filter(Alert.status != "resolved")
                .order_by(Alert.id.desc()).limit(200).all())
    finally:
        db.close()
    started = 0
    for alert_id, steps in rows:
        steps = steps or []
        if not steps or "condition" not in steps[0]:          # stare alerty (sprzed runnera) zostawiamy
            continue
        cur = next((s for s in steps if not is_finished(s)), None)
        if cur is not None and cur.get("status") is None:
            advance_alert(alert_id)
            started += 1
    return started


def upgrade_runbook_steps(db: Session) -> int:
    """Runbooki zapisane przed runnerem nie mają warunków ani rodzajów kroków – parsujemy je ponownie."""
    n = 0
    for rb in db.query(Runbook).all():
        if rb.steps and all("condition" in s for s in rb.steps):
            continue
        try:
            rb.steps = parse_runbook_full(rb.raw, rb.format or "auto").steps
            n += 1
        except ValueError:
            log.warning("runbook %s could not be re-parsed", rb.id)
    if n:
        db.commit()
    return n


_stop = threading.Event()
_worker: threading.Thread | None = None


def _loop() -> None:
    log.info("runbook worker %s started", WORKER_ID)
    last_sweep = 0.0
    while not _stop.is_set():
        try:
            busy = run_pending_once()
            if time.monotonic() - last_sweep > SWEEP_SECONDS:
                last_sweep = time.monotonic()
                sweep()
        except Exception:  # noqa: BLE001
            log.exception("runbook worker loop error")
            busy = False
        if not busy:
            _stop.wait(POLL_SECONDS)


def start_worker() -> None:
    """Startuje worker w tle (jeden na kopię serwera). RUNBOOK_WORKER=0 wyłącza."""
    global _worker
    if os.getenv("RUNBOOK_WORKER", "1") == "0" or (_worker and _worker.is_alive()):
        return
    _stop.clear()
    _worker = threading.Thread(target=_loop, name="runbook-worker", daemon=True)
    _worker.start()


def stop_worker() -> None:
    _stop.set()
