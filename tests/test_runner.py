"""
Testy Osoby 4: wykonywanie kroków runbooka (manual / auto / approve) na symulatorze.
ŚWIEŻA, tymczasowa baza SQLite; worker w tle wyłączony – kroki odpalamy ręcznie (run_until_idle).

    python tests/test_runner.py

Sprawdza scenariusze z kartki (Appendix B) oraz pułapki z SKALOWANIE.md:
równoległe kliknięcia Approve i kilka workerów naraz -> każdy krok wykonany DOKŁADNIE raz.
"""
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'runner.db')}"
os.environ["RUNBOOK_WORKER"] = "0"
os.environ["RUNBOOK_WAIT_SCALE"] = "0"          # "Wait 2 minutes" od razu (poza testem czekania)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import SimCall, StepJob  # noqa: E402
from services import runbook_runner  # noqa: E402

client = TestClient(main.app)

APPENDIX_YAML = """runbook: settlement-timeout
matches:
  type: WORKFLOW_FAILED
  "error.code": TIMEOUT
steps:
  - check: "Is counterparty-service healthy?"
    action: http_get
    url: "http://counterparty-service/health"
  - action: retry_workflow
    workflowId: "{{workflowId}}"
    approval: none
  - if: "retry fails twice"
    action: escalate
    team: counterparty-support
    approval: required
"""

EVENT = {"type": "WORKFLOW_FAILED", "workflowName": "order-settlement", "environment": "prod",
         "workflowId": "WF-1", "step": "book-cash", "error": {"code": "TIMEOUT", "message": "Timed out"}}


def ok(resp, status=200):
    assert resp.status_code == status, f"{resp.status_code} != {status}: {resp.text}"
    return resp.json()


def use_runbook(raw):
    """Podpina świeży runbook pod regułę settlements-prod i zamyka otwarte alerty tej reguły."""
    for a in ok(client.get("/api/alerts?status=open")) + ok(client.get("/api/alerts?status=acknowledged")):
        ok(client.post(f"/api/alerts/{a['id']}/resolve"))
    rb = ok(client.post("/api/runbooks", json={"name": f"rb-{abs(hash(raw)) % 10**6}", "raw": raw}))
    ok(client.post(f"/api/runbooks/{rb['id']}/attach/settlements-prod"))


def set_sim(name, **kw):
    ok(client.put(f"/api/sim/services/{name}", json=kw))


def fire(event=EVENT):
    return ok(client.post("/api/ingest/demo", json=event))["alerts"][0]


def alert(aid):
    return ok(client.get(f"/api/alerts/{aid}"))


def statuses(aid):
    return [s.get("status") for s in alert(aid)["steps"]]


def sim_calls(action, alert_id):
    db = SessionLocal()
    try:
        return db.query(SimCall).filter(SimCall.action == action, SimCall.alert_id == alert_id).count()
    finally:
        db.close()


def reset_sim():
    for name in ("counterparty-service", "settlement", "pricing-engine", "payments-api"):
        set_sim(name, healthy=True, workflows_ok=True)


# ---------------------------------------------------------------- scenariusze z kartki

def test_broken_service_runs_auto_steps_then_waits_for_approval():
    reset_sim()
    use_runbook(APPENDIX_YAML)
    set_sim("counterparty-service", healthy=False)
    aid = fire()
    assert statuses(aid) == ["queued", None, None]            # nic nie dzieje się w samym przyjęciu zdarzenia
    runbook_runner.run_until_idle()
    steps = alert(aid)["steps"]
    assert [s["status"] for s in steps] == ["failed", "failed", "waiting_approval"]
    assert "not responding" in steps[0]["result"] and "2/2" in steps[1]["result"]
    assert sim_calls("escalate", aid) == 0                      # bez zgody nic się nie wykonało

    ok(client.post(f"/api/alerts/{aid}/steps/2/approve"))
    runbook_runner.run_until_idle()
    a = alert(aid)
    assert [s["status"] for s in a["steps"]] == ["failed", "failed", "succeeded"]
    assert a["steps"][2]["result"] == "Escalated to counterparty-support"
    assert a["history"][-1]["what"] == "runbook finished"
    assert sim_calls("escalate", aid) == 1


def test_healthy_service_skips_escalation():
    reset_sim()
    use_runbook(APPENDIX_YAML)
    aid = fire()
    runbook_runner.run_until_idle()
    steps = alert(aid)["steps"]
    assert [s["status"] for s in steps] == ["succeeded", "succeeded", "skipped"]
    assert "condition not met" in steps[2]["result"]
    assert sim_calls("escalate", aid) == 0


def test_duplicate_event_does_not_run_steps_again():
    reset_sim()
    use_runbook(APPENDIX_YAML)
    aid = fire()
    runbook_runner.run_until_idle()
    before = (sim_calls("http_get", aid), sim_calls("retry_workflow", aid))
    assert fire() == aid                                        # ten sam alert, licznik ×2
    assert runbook_runner.run_until_idle() == 0
    assert alert(aid)["count"] == 2
    assert (sim_calls("http_get", aid), sim_calls("retry_workflow", aid)) == before


def test_manual_step_blocks_until_marked_done():
    reset_sim()
    use_runbook("1. Open the payments dashboard\n2. Open a JIRA ticket with error {{error.code}}")
    aid = fire()
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["waiting", None]                   # stop na kroku ręcznym
    ok(client.post(f"/api/alerts/{aid}/steps/0/done"))
    runbook_runner.run_until_idle()
    steps = alert(aid)["steps"]
    assert steps[0]["done"] and steps[1]["status"] == "succeeded"
    assert steps[1]["result"].startswith("Ticket SIM-")


def test_approve_then_manual():
    reset_sim()
    use_runbook("1. Fail traffic over to the other region (needs approval from the team lead)")
    aid = fire()
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["waiting_approval"]
    ok(client.post(f"/api/alerts/{aid}/steps/0/done"), 409)     # najpierw zgoda (zasada Osoby 1)
    ok(client.post(f"/api/alerts/{aid}/steps/0/approve"))
    assert statuses(aid) == ["waiting"]                         # zgoda jest, robi człowiek
    ok(client.post(f"/api/alerts/{aid}/steps/0/done"))
    assert alert(aid)["steps"][0]["done"]


def test_condition_the_app_cannot_check_needs_a_person():
    reset_sim()
    use_runbook("1. Wait 2 minutes\n2. If latency is still high, open a JIRA ticket")
    aid = fire()
    runbook_runner.run_until_idle()
    steps = alert(aid)["steps"]
    assert steps[0]["status"] == "succeeded"
    assert steps[1]["status"] == "waiting_approval" and "can't check" in steps[1]["result"]
    ok(client.post(f"/api/alerts/{aid}/steps/1/approve"))
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["succeeded", "succeeded"]


def test_failed_app_step_can_be_marked_done_by_a_person():
    reset_sim()
    use_runbook("1. Check health at http://counterparty-service/health\n2. Open a JIRA ticket")
    set_sim("counterparty-service", healthy=False)
    aid = fire()
    runbook_runner.run_until_idle()
    assert statuses(aid)[0] == "failed"
    ok(client.post(f"/api/alerts/{aid}/steps/0/done"))          # "zrobiłem to sam"
    assert alert(aid)["steps"][0]["done"]


def test_restart_brings_service_back():
    reset_sim()
    set_sim("pricing-engine", healthy=False)
    use_runbook("1. Restart pricing-engine [auto]")
    aid = fire()
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["succeeded"]
    sims = {s["name"]: s for s in ok(client.get("/api/sim/services"))}
    assert sims["pricing-engine"]["restarting"]                 # chwilę nie odpowiada, potem wraca zdrowy


def test_resolved_alert_stops_runbook():
    reset_sim()
    use_runbook("1. Retry workflow WF-1\n2. Open a JIRA ticket")
    aid = fire()
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["waiting_approval", None]
    ok(client.post(f"/api/alerts/{aid}/resolve"))
    ok(client.post(f"/api/alerts/{aid}/steps/0/approve"), 409)
    assert runbook_runner.run_until_idle() == 0


def test_wait_step_is_not_run_before_its_time():
    reset_sim()
    old = runbook_runner.WAIT_SCALE
    runbook_runner.WAIT_SCALE = 1.0
    try:
        use_runbook("1. Wait 10 minutes\n2. Open a JIRA ticket")
        aid = fire()
        assert runbook_runner.run_until_idle() == 0             # za wcześnie
        step = alert(aid)["steps"][0]
        assert step["status"] == "queued" and step["result"].startswith("Waiting until")
    finally:
        runbook_runner.WAIT_SCALE = old


# ---------------------------------------------------------------- wiele kopii serwera naraz (SKALOWANIE.md)

def test_parallel_approvals_execute_the_step_exactly_once():
    reset_sim()
    use_runbook("1. Escalate to the payments on-call")
    aid = fire()
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["waiting_approval"]

    barrier = threading.Barrier(20)

    def click(_):
        barrier.wait()                                          # 20 kliknięć w tej samej chwili
        return client.post(f"/api/alerts/{aid}/steps/0/approve").status_code

    with ThreadPoolExecutor(20) as pool:
        codes = list(pool.map(click, range(20)))
    assert codes.count(200) == 1 and codes.count(409) == 19     # jedno zatwierdzenie, reszta "already approved"

    with ThreadPoolExecutor(8) as pool:                         # 8 "kopii" workera naraz
        list(pool.map(lambda _: runbook_runner.run_until_idle(), range(8)))
    assert sim_calls("escalate", aid) == 1
    approvals = [h for h in alert(aid)["history"] if h["what"].startswith("approved step")]
    assert len(approvals) == 1


def test_parallel_workers_take_each_job_once():
    reset_sim()
    rb = ok(client.post("/api/runbooks", json={
        "name": "parallel", "raw": "1. Open a JIRA ticket\n2. Check health at http://payments-api/health\n"
                                   "3. Open a JIRA ticket again"}))
    ok(client.post(f"/api/runbooks/{rb['id']}/attach/pricing-warnings"))
    # reguła pricing-warnings grupuje po instrumencie -> 5 instrumentów = 5 osobnych alertów, 15 zadań
    ids = [ok(client.post("/api/ingest/demo", json={"service": "pricing-engine-eu", "level": "WARN",
                                                    "instrument": f"PAIR{n}"}))["alerts"][0] for n in range(5)]
    assert len(set(ids)) == 5
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(lambda _: runbook_runner.run_until_idle(), range(6)))
    for aid in ids:                                             # każdy krok każdego alertu dokładnie raz
        assert statuses(aid) == ["succeeded", "succeeded", "succeeded"]
        assert sim_calls("open_ticket", aid) == 2 and sim_calls("http_get", aid) == 1
    db = SessionLocal()
    try:
        jobs = db.query(StepJob).filter(StepJob.alert_id.in_(ids)).all()
        assert len(jobs) == 15 and all(j.status == "finished" for j in jobs)
    finally:
        db.close()


# ---------------------------------------------------------------- zatwierdzanie kilku kroków naraz

PREFIX_RUNBOOK = ("1. Retry workflow WF-1\n2. Restart pricing-engine\n3. Open the payments dashboard\n"
                  "4. Escalate to the payments on-call")


def test_approve_until_runs_the_whole_prefix():
    reset_sim()
    use_runbook(PREFIX_RUNBOOK)
    aid = fire()
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["waiting_approval", None, None, None]
    a = ok(client.post(f"/api/alerts/{aid}/steps/1/approve-until"))      # kroki 1 i 2 jednym kliknięciem
    assert [bool(s.get("approved_by")) for s in a["steps"]] == [True, True, False, False]
    assert a["history"][-2]["what"] == "approved steps 1, 2" or a["history"][-1]["what"] == "approved steps 1, 2"
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["succeeded", "succeeded", "waiting", None]   # stop na kroku manual


def test_approve_until_cannot_go_past_a_manual_step():
    reset_sim()
    use_runbook(PREFIX_RUNBOOK)
    aid = fire()
    runbook_runner.run_until_idle()
    r = ok(client.post(f"/api/alerts/{aid}/steps/3/approve-until"), 409)
    assert "step 3" in r["detail"].lower()
    assert not any(s.get("approved_by") for s in alert(aid)["steps"])     # nic nie zatwierdzone


def test_approve_until_can_end_on_approve_then_manual():
    reset_sim()
    use_runbook("1. Retry workflow WF-1\n2. Fail traffic over to the other region (needs approval)\n"
                "3. Escalate to the payments on-call")
    aid = fire()
    runbook_runner.run_until_idle()
    ok(client.post(f"/api/alerts/{aid}/steps/2/approve-until"), 409)     # za krok "zgoda + ręcznie" nie wolno
    ok(client.post(f"/api/alerts/{aid}/steps/1/approve-until"))
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["succeeded", "waiting", None]                # zgoda jest, człowiek robi krok 2


# ---------------------------------------------------------------- błąd: kasowanie zgód, Ponów, Przerwij

def test_error_clears_approvals_and_retry_continues():
    reset_sim()
    set_sim("settlement", workflows_ok=False)
    use_runbook("1. Retry workflow WF-1\n2. Escalate to the payments on-call")
    aid = fire()
    runbook_runner.run_until_idle()
    ok(client.post(f"/api/alerts/{aid}/steps/1/approve-until"))
    runbook_runner.run_until_idle()
    a = alert(aid)
    assert [s.get("status") for s in a["steps"]] == ["error", None]      # retry nie przeszedł i nic tego nie obsługuje
    assert not a["steps"][1].get("approved_by")                          # zgoda na krok 2 skasowana
    assert "approve again" in a["history"][-1]["what"]
    assert sim_calls("escalate", aid) == 0

    ok(client.post(f"/api/alerts/{aid}/steps/1/approve-until"), 409)     # najpierw Ponów albo Przerwij
    set_sim("settlement", workflows_ok=True)
    ok(client.post(f"/api/alerts/{aid}/steps/0/retry"))
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["succeeded", "waiting_approval"]            # krok 2 trzeba zatwierdzić od nowa
    assert sim_calls("retry_workflow", aid) == 3                          # 2 próby + 1 po Ponów


def test_technical_error_stops_and_abort_cancels_the_rest():
    reset_sim()
    use_runbook("1. Restart the mystery-box [auto]\n2. Open a JIRA ticket")
    aid = fire()
    runbook_runner.run_until_idle()
    a = alert(aid)
    assert [s.get("status") for s in a["steps"]] == ["error", None]
    assert "Unknown service" in a["steps"][0]["result"]
    ok(client.post(f"/api/alerts/{aid}/steps/1/retry"), 409)             # ponowić można tylko krok z błędem
    a = ok(client.post(f"/api/alerts/{aid}/runbook/abort"))
    assert [s["status"] for s in a["steps"]] == ["cancelled", "cancelled"]
    assert a["status"] != "resolved" and a["history"][-1]["what"] == "aborted the runbook"
    assert runbook_runner.run_until_idle() == 0
    ok(client.post(f"/api/alerts/{aid}/runbook/abort"), 409)


def test_mark_done_after_error_continues():
    reset_sim()
    use_runbook("1. Restart the mystery-box [auto]\n2. Open a JIRA ticket")
    aid = fire()
    runbook_runner.run_until_idle()
    ok(client.post(f"/api/alerts/{aid}/steps/0/done"))                   # "zrobiłem ręcznie"
    runbook_runner.run_until_idle()
    steps = alert(aid)["steps"]
    assert steps[0]["done"] and steps[1]["status"] == "succeeded"


# ---------------------------------------------------------------- SMS: YES / YES N / YES ALL

def _sms_delivery(aid, code):
    from models import Delivery
    db = SessionLocal()
    try:
        db.add(Delivery(alert_id=aid, channel="sms", to="+48 600 000 001", status="sent",
                        reply_code=code, recipient_name="Lead"))
        db.commit()
    finally:
        db.close()


def _sms(text):
    from services.replies import handle_sms
    db = SessionLocal()
    try:
        return handle_sms(db, "+48600000001", text)
    finally:
        db.close()


def test_sms_yes_variants():
    reset_sim()
    use_runbook("1. Retry workflow WF-1\n2. Restart pricing-engine\n3. Escalate to the payments on-call\n"
                "4. Open the payments dashboard")
    aid = fire()
    runbook_runner.run_until_idle()
    _sms_delivery(aid, "7311")
    r = _sms("YES 7311")
    assert r.ok and r.message.startswith("OK - step 1 approved")
    r = _sms("YES 2 7311")
    assert r.ok and "step 2 approved" in r.message
    assert not alert(aid)["steps"][2].get("approved_by")
    r = _sms("YES 9 7311")
    assert not r.ok                                                       # nie ma kroku 9 / za manualem
    r = _sms("YES ALL 7311")
    assert r.ok and "step 3 approved" in r.message
    runbook_runner.run_until_idle()
    assert statuses(aid) == ["succeeded", "succeeded", "succeeded", "waiting"]
    r = _sms("YES ALL 7311")
    assert not r.ok                                                       # nic już nie czeka na zgodę


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
