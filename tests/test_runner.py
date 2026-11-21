"""
Testy Osoby 4: wykonywanie kroków runbooka (auto / approve / manual) na symulatorze i zamykanie alertu,
gdy problem minął (kartka 2.6). ŚWIEŻA, tymczasowa baza SQLite.

    python tests/test_runner.py

Kroki aplikacji wykonują się od razu (przy zapisie alertu, po Approve / Mark done / Retry), więc testy
sprawdzają stan alertu zaraz po wywołaniu API. Na koniec: 20 kliknięć Approve naraz -> akcja dokładnie raz.
"""
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'runner.db')}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import SimCall  # noqa: E402
from seed import seed_all  # noqa: E402

with SessionLocal() as _db:
    seed_all(_db)

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


def use_runbook(raw, rule="settlements-prod"):
    """Podpina świeży runbook pod regułę i zamyka otwarte alerty, żeby każdy test zaczynał od nowego alertu."""
    for a in ok(client.get("/api/alerts?status=open")) + ok(client.get("/api/alerts?status=acknowledged")):
        ok(client.post(f"/api/alerts/{a['id']}/resolve"))
    rb = ok(client.post("/api/runbooks", json={"name": f"rb-{abs(hash(raw)) % 10**6}", "raw": raw}))
    ok(client.post(f"/api/runbooks/{rb['id']}/attach/{rule}"))


def set_sim(name, **kw):
    ok(client.put(f"/api/sim/services/{name}", json=kw))


def reset_sim():
    for name in ("counterparty-service", "settlement", "pricing-engine", "payments-api"):
        set_sim(name, healthy=True, workflows_ok=True)


def fire(event=EVENT, source="demo"):
    return ok(client.post(f"/api/ingest/{source}", json=event))["alerts"][0]


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


# ---------------------------------------------------------------- runbook z kartki (Appendix B)

def test_healthy_service_runs_everything_and_skips_escalation():
    reset_sim()
    use_runbook(APPENDIX_YAML)
    aid = fire()
    a = alert(aid)
    assert [s["status"] for s in a["steps"]] == ["succeeded", "succeeded", "skipped"]
    assert "condition not met" in a["steps"][2]["result"]
    assert a["history"][-1]["what"] == "runbook finished"
    assert sim_calls("escalate", aid) == 0


def test_broken_service_waits_for_approval_then_escalates():
    reset_sim()
    use_runbook(APPENDIX_YAML)
    set_sim("counterparty-service", healthy=False)
    aid = fire()
    steps = alert(aid)["steps"]
    assert [s["status"] for s in steps] == ["failed", "failed", "waiting_approval"]
    assert "not responding" in steps[0]["result"] and "2/2" in steps[1]["result"]
    assert sim_calls("escalate", aid) == 0                      # ryzykowny krok: bez zgody nic się nie dzieje

    a = ok(client.post(f"/api/alerts/{aid}/steps/2/approve"))   # zgoda z UI -> aplikacja od razu wykonuje
    assert [s["status"] for s in a["steps"]] == ["failed", "failed", "succeeded"]
    assert a["steps"][2]["result"] == "Escalated to counterparty-support"
    assert any(h["who"] == "anonymous" and h["what"].startswith("approved step 3") for h in a["history"])
    assert sim_calls("escalate", aid) == 1


def test_duplicate_event_does_not_run_steps_again():
    reset_sim()
    use_runbook(APPENDIX_YAML)
    aid = fire()
    before = (sim_calls("http_get", aid), sim_calls("retry_workflow", aid))
    assert fire() == aid                                        # ten sam alert, licznik ×2
    assert alert(aid)["count"] == 2
    assert (sim_calls("http_get", aid), sim_calls("retry_workflow", aid)) == before


# ---------------------------------------------------------------- manual / approve / warunki

def test_manual_step_blocks_until_marked_done():
    reset_sim()
    use_runbook("1. Open the payments dashboard\n2. Open a JIRA ticket with error {{error.code}}")
    aid = fire()
    assert statuses(aid) == ["waiting", None]                   # stop na kroku ręcznym
    a = ok(client.post(f"/api/alerts/{aid}/steps/0/done"))
    assert a["steps"][0]["done"] and a["steps"][1]["status"] == "succeeded"
    assert a["steps"][1]["result"].startswith("Ticket SIM-")


def test_approve_then_manual():
    reset_sim()
    use_runbook("1. Fail traffic over to the other region (needs approval from the team lead)")
    aid = fire()
    assert statuses(aid) == ["waiting_approval"]
    ok(client.post(f"/api/alerts/{aid}/steps/0/done"), 409)     # najpierw zgoda (zasada Osoby 1)
    ok(client.post(f"/api/alerts/{aid}/steps/0/approve"))
    assert statuses(aid) == ["waiting"]                         # zgoda jest, robi człowiek
    assert ok(client.post(f"/api/alerts/{aid}/steps/0/done"))["steps"][0]["done"]


def test_condition_the_app_cannot_check_needs_a_person():
    reset_sim()
    use_runbook("1. Wait 2 minutes\n2. If latency is still high, open a JIRA ticket")
    aid = fire()
    steps = alert(aid)["steps"]
    assert steps[0]["status"] == "succeeded"
    assert steps[1]["status"] == "waiting_approval" and "can't check" in steps[1]["result"]
    ok(client.post(f"/api/alerts/{aid}/steps/1/approve"))
    assert statuses(aid) == ["succeeded", "succeeded"]


def test_restart_brings_service_back():
    reset_sim()
    set_sim("pricing-engine", healthy=False)
    use_runbook("1. Restart pricing-engine [auto]")
    aid = fire()
    assert statuses(aid) == ["succeeded"]
    sims = {s["name"]: s for s in ok(client.get("/api/sim/services"))}
    assert sims["pricing-engine"]["restarting"]                 # chwilę nie odpowiada, potem wraca zdrowy


def test_resolved_alert_stops_runbook():
    reset_sim()
    use_runbook("1. Retry workflow WF-1\n2. Open a JIRA ticket")
    aid = fire()
    assert statuses(aid) == ["waiting_approval", None]
    ok(client.post(f"/api/alerts/{aid}/resolve"))
    ok(client.post(f"/api/alerts/{aid}/steps/0/approve"), 409)
    assert sim_calls("retry_workflow", aid) == 0


# ---------------------------------------------------------------- nieudany krok: Retry / Mark done

def test_failed_step_can_be_retried_after_the_fix():
    reset_sim()
    set_sim("settlement", workflows_ok=False)
    use_runbook("1. Retry workflow WF-1 [auto]\n2. Open a JIRA ticket")
    aid = fire()
    assert statuses(aid) == ["failed", "succeeded"]             # nieudany krok nie zatrzymuje procedury
    ok(client.post(f"/api/alerts/{aid}/steps/1/retry"), 409)    # ponowić można tylko nieudany krok
    set_sim("settlement", workflows_ok=True)
    a = ok(client.post(f"/api/alerts/{aid}/steps/0/retry"))
    assert a["steps"][0]["status"] == "succeeded" and a["steps"][0]["run_no"] == 2
    assert any(h["what"].startswith("✅ step 1") and h["who"] == "anonymous" for h in a["history"])


def test_failed_step_can_be_marked_done_by_a_person():
    reset_sim()
    set_sim("counterparty-service", healthy=False)
    use_runbook("1. Check health at http://counterparty-service/health\n2. Open a JIRA ticket")
    aid = fire()
    assert statuses(aid)[0] == "failed"
    assert ok(client.post(f"/api/alerts/{aid}/steps/0/done"))["steps"][0]["done"]   # "zrobiłem to sam"


# ---------------------------------------------------------------- "problem minął" -> alert sam się zamyka

def test_recovery_event_closes_the_alert():
    payments = {"alertname": "HighErrorRate", "labels": {"service": "payments-api", "region": "eu-west",
                                                         "severity": "critical"},
                "annotations": {"summary": "Error rate 12%"}, "status": "firing"}
    aid = fire(payments, source="payments-webhook")
    assert alert(aid)["status"] == "open"
    assert fire({**payments, "status": "resolved"}, source="payments-webhook") == aid
    a = alert(aid)
    assert a["status"] == "resolved"
    assert a["history"][-1]["who"] == "system" and "problem went away" in a["history"][-1]["what"]
    # "resolved" bez otwartego alertu niczego nie tworzy
    assert ok(client.post("/api/ingest/payments-webhook", json={**payments, "status": "resolved"}))["alerts"] == []


# ---------------------------------------------------------------- wiele kliknięć naraz (SKALOWANIE.md)

def test_parallel_approvals_execute_the_step_exactly_once():
    reset_sim()
    use_runbook("1. Escalate to the payments on-call")
    aid = fire()
    assert statuses(aid) == ["waiting_approval"]

    barrier = threading.Barrier(20)

    def click(_):
        barrier.wait()                                          # 20 kliknięć w tej samej chwili
        return client.post(f"/api/alerts/{aid}/steps/0/approve").status_code

    with ThreadPoolExecutor(20) as pool:
        codes = list(pool.map(click, range(20)))
    assert codes.count(200) == 1 and codes.count(409) == 19     # jedno zatwierdzenie, reszta "already approved"
    assert sim_calls("escalate", aid) == 1
    assert len([h for h in alert(aid)["history"] if h["what"].startswith("approved step")]) == 1


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
