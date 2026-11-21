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
from models import Delivery, Person, SimCall, Team  # noqa: E402

# czysta baza z danymi startowymi przed testami tego pliku – patrz tests/conftest.py
SEED = {}

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


def add_person(name, team, phone=None, email=None, role="member", on_call=False, prefs=None):
    """Osoba w bazie (seed nie dodaje już przykładowych osób). Zespół tworzy, jeśli go nie ma."""
    db = SessionLocal()
    try:
        if not db.query(Team).filter(Team.name == team).first():
            db.add(Team(name=team))
        person = db.query(Person).filter(Person.name == name).first()
        if person is None:
            person = Person(name=name, team=team, phone=phone, email=email, role=role, on_call=on_call,
                            channel_prefs=prefs or {}, quiet_hours={})
            db.add(person)
        db.commit()
        return person.id
    finally:
        db.close()


def deliveries(alert_id):
    db = SessionLocal()
    try:
        return sorted((d.recipient_name, d.channel) for d in db.query(Delivery).filter(Delivery.alert_id == alert_id))
    finally:
        db.close()


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
    add_person("Ola", "counterparty-support", phone="+48 600 100 001", on_call=True, prefs={"critical": ["sms"]})
    use_runbook(APPENDIX_YAML)
    set_sim("counterparty-service", healthy=False)
    aid = fire()
    steps = alert(aid)["steps"]
    assert [s["status"] for s in steps] == ["failed", "failed", "waiting_approval"]
    assert "not responding" in steps[0]["result"] and "2/2" in steps[1]["result"]
    assert sim_calls("escalate", aid) == 0                      # ryzykowny krok: bez zgody nic się nie dzieje

    a = ok(client.post(f"/api/alerts/{aid}/steps/2/approve"))   # zgoda z UI -> aplikacja od razu wykonuje
    assert [s["status"] for s in a["steps"]] == ["failed", "failed", "succeeded"]
    assert a["steps"][2]["result"] == "Escalated to counterparty-support: Ola (sms)"
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


# ---------------------------------------------------------------- eskalacja powiadamia ludzi z innego zespołu

def test_escalation_notifies_people_of_the_target_team():
    reset_sim()
    add_person("Iga", "Rates", phone="+48 600 200 001", prefs={"critical": ["sms"]})
    add_person("Jan", "Rates", email="jan@example.com")
    use_runbook("1. Escalate to the Rates team [auto]")
    aid = fire()
    step = alert(aid)["steps"][0]
    assert step["status"] == "succeeded"
    assert step["result"] == "Escalated to Rates: Iga (sms), Jan (email)"
    assert deliveries(aid) == [("Iga", "sms"), ("Jan", "email")]      # przez Outbox, z ponawianiem


def test_escalation_to_on_call_only_pages_people_on_duty():
    reset_sim()
    add_person("Marek", "Pricing", phone="+48 600 300 001", on_call=True, prefs={"critical": ["phone"]})
    add_person("Zosia", "Pricing", phone="+48 600 300 002", prefs={"critical": ["sms"]})
    use_runbook("1. Call the pricing on-call person [auto]")
    aid = fire()
    assert alert(aid)["steps"][0]["result"] == "Escalated to Pricing: Marek (phone)"
    assert deliveries(aid) == [("Marek", "phone")]


def test_escalation_to_unknown_or_empty_team_fails():
    reset_sim()
    use_runbook("1. Escalate to the ghost-busters [auto]\n2. Escalate to the Management team [auto]")
    aid = fire()
    steps = alert(aid)["steps"]
    assert steps[0]["status"] == "failed" and "No team called" in steps[0]["result"]
    assert steps[1]["status"] == "failed" and "Nobody in team Management" in steps[1]["result"]
    assert deliveries(aid) == []


# ---------------------------------------------------------------- zgoda SMS-em tylko od leada

def _sms_to(alert_id, person_id, name, phone, code):
    db = SessionLocal()
    try:
        db.add(Delivery(alert_id=alert_id, person_id=person_id, channel="sms", to=phone, status="sent",
                        reply_code=code, recipient_name=name))
        db.commit()
    finally:
        db.close()


def test_sms_approval_only_from_the_team_lead():
    from services.replies import handle_sms
    reset_sim()
    tom = add_person("Tom", "Settlements", phone="+48 600 400 001", on_call=True)
    ewa = add_person("Ewa", "Settlements", phone="+48 600 400 002", role="lead")
    use_runbook("1. Restart pricing-engine")
    aid = fire()
    assert statuses(aid) == ["waiting_approval"]
    _sms_to(aid, tom, "Tom", "+48 600 400 001", "5101")
    _sms_to(aid, ewa, "Ewa", "+48 600 400 002", "5102")
    db = SessionLocal()
    try:
        refused = handle_sms(db, "+48600400001", "YES 5101")        # dyżurny, ale nie lead
        assert not refused.ok and "Only a team lead" in refused.message and "Ewa" in refused.message
        assert statuses(aid) == ["waiting_approval"] and sim_calls("restart_service", aid) == 0
        approved = handle_sms(db, "+48600400002", "YES 5102")       # lead zespołu
        assert approved.ok and "step 1 approved" in approved.message
    finally:
        db.close()
    a = alert(aid)
    assert a["steps"][0]["status"] == "succeeded" and a["steps"][0]["approved_by"] == "Ewa (SMS)"
    ack = handle_sms(SessionLocal(), "+48600400001", "ACK 5101")    # ACK SMS-em dalej może każdy
    assert ack.ok


# ---------------------------------------------------------------- własne akcje zespołu (dodawane w UI, bez kodu)

def _sim_detail(action, alert_id):
    db = SessionLocal()
    try:
        return [c.detail for c in db.query(SimCall).filter(SimCall.action == action, SimCall.alert_id == alert_id)]
    finally:
        db.close()


def test_team_action_added_in_ui_is_used_by_runbooks():
    reset_sim()
    act = ok(client.post("/api/actions", json={"label": "Clear cache", "url": "https://{{workflowName}}.internal/cache/clear",
                                              "risky": False}), 201)
    assert act["key"] == "clear_cache"
    ok(client.post("/api/actions", json={"label": "Clear cache", "url": "https://x"}), 409)      # nazwa zajęta
    ok(client.post("/api/actions", json={"label": "Restart service", "url": "https://x"}), 409)  # wbudowana
    ok(client.post("/api/actions", json={"label": "Bad", "url": "not-a-url"}), 422)
    assert any(a["key"] == "clear_cache" for a in ok(client.get("/api/actions"))["custom"])

    # tekst ("Clear cache on …") i YAML ("action: clear_cache") rozpoznają akcję zespołu
    preview = ok(client.post("/api/runbooks/parse", json={"raw": "1. Clear cache on settlement", "format": "auto"}))
    assert preview["steps"][0]["action"] == "clear_cache" and preview["steps"][0]["custom"]

    use_runbook("steps:\n  - action: clear_cache\n")
    aid = fire()
    step = alert(aid)["steps"][0]
    assert step["status"] == "succeeded"                                  # risky: false -> wykonuje się sama
    assert step["result"] == "Clear cache: POST https://order-settlement.internal/cache/clear (simulated)"
    assert _sim_detail("webhook", aid)[0].startswith("POST https://order-settlement.internal/cache/clear")


def test_risky_team_action_waits_for_approval_and_url_change_applies():
    reset_sim()
    act = ok(client.post("/api/actions", json={"label": "Fail over region", "url": "https://lb.internal/failover"}), 201)
    use_runbook("1. Fail over region to eu-west")
    aid = fire()
    assert statuses(aid) == ["waiting_approval"]                          # domyślnie ryzykowna
    ok(client.put(f"/api/actions/{act['id']}", json={"label": "Fail over region", "url": "https://lb2.internal/failover",
                                                     "risky": True}))
    a = ok(client.post(f"/api/alerts/{aid}/steps/0/approve"))
    assert a["steps"][0]["result"] == "Fail over region: POST https://lb2.internal/failover (simulated)"   # nowy adres


def test_existing_runbook_learns_a_new_action_and_forgets_a_deleted_one():
    rb = ok(client.post("/api/runbooks", json={"name": "learns", "raw": "1. Purge queue orders"}))
    assert rb["steps"][0]["action"] is None                               # jeszcze nieznana -> manual
    act = ok(client.post("/api/actions", json={"label": "Purge queue", "url": "https://mq.internal/purge"}), 201)
    step = ok(client.get(f"/api/runbooks/{rb['id']}"))["steps"][0]
    assert step["action"] == "purge_queue" and step["custom"]
    ok(client.delete(f"/api/actions/{act['id']}"))
    step = ok(client.get(f"/api/runbooks/{rb['id']}"))["steps"][0]
    assert step["action"] is None and not step.get("custom")


# ---------------------------------------------------------------- wiele kliknięć naraz (SKALOWANIE.md)

def test_parallel_approvals_execute_the_step_exactly_once():
    reset_sim()
    use_runbook("1. Restart pricing-engine")
    aid = fire()
    assert statuses(aid) == ["waiting_approval"]

    barrier = threading.Barrier(20)

    def click(_):
        barrier.wait()                                          # 20 kliknięć w tej samej chwili
        return client.post(f"/api/alerts/{aid}/steps/0/approve").status_code

    with ThreadPoolExecutor(20) as pool:
        codes = list(pool.map(click, range(20)))
    assert codes.count(200) == 1 and codes.count(409) == 19     # jedno zatwierdzenie, reszta "already approved"
    assert sim_calls("restart_service", aid) == 1
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
