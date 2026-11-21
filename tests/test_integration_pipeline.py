"""
End-to-end integration tests for the unified pipeline before handing off to Notifications (Osoba 3).

    /Users/koperek/Desktop/programy/GS-Hackathon/.venv/bin/python tests/test_integration_pipeline.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'integration.db')}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import main  # noqa: E402
import services.pipeline as pipeline  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from models import Alert, User  # noqa: E402
from services.people_service import plan_recipients  # noqa: E402
from services.security import create_access_token, hash_password  # noqa: E402

client = TestClient(main.app)

DELIVERIES_LOG = []
_real_enqueue = pipeline.enqueue_deliveries


def _spy_enqueue(db, alert, recipients):
    DELIVERIES_LOG.append({
        "alert_id": alert.id,
        "rule_id": alert.rule_id,
        "team": alert.team,
        "title": alert.title,
        "body": alert.body,
        "severity": alert.severity,
        "count": alert.count,
        "steps": [dict(s) for s in (alert.steps or [])],
        "recipients": sorted(
            ((r.person_id, r.name, r.channel, r.to) for r in recipients),
            key=lambda item: (-1 if item[0] is None else item[0], item[1], item[2]),
        ),
    })
    return _real_enqueue(db, alert, recipients)


pipeline.enqueue_deliveries = _spy_enqueue


def ok(resp, status=200):
    assert resp.status_code == status, f"{resp.status_code} != {status}: {resp.text}"
    return resp.json()


def _source_by_key(key):
    for s in ok(client.get("/api/sources")):
        if s["key"] == key:
            return s
    raise AssertionError(f"Source {key!r} not found")


def _auth_header(uname, email, is_admin=False):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.uname == uname).first()
        if user is None:
            user = User(
                uname=uname,
                email=email,
                hashed_password=hash_password("Secret123!"),
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        token = create_access_token({"sub": str(user.id), "uname": user.uname})
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def test_startup_created_open_dedup_index_and_seed():
    with engine.connect() as conn:
        idx = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name='uq_alerts_open_dedup'")
        ).scalar()
    assert idx == "uq_alerts_open_dedup"
    teams = ok(client.get("/api/teams"))
    depts = ok(client.get("/api/departments"))
    assert teams == depts
    teams_by_name = {t["name"]: t for t in teams}
    assert set(teams_by_name) == {"Settlements", "Pricing", "Rates", "Payments", "Management"}
    assert teams_by_name["Settlements"]["people_count"] == 2  # Tom + Ewa
    assert teams_by_name["Settlements"]["rules_count"] == 1   # settlements-prod
    assert teams_by_name["Settlements"]["sources_count"] == 1  # settlement-kafka
    assert teams_by_name["Rates"]["people_count"] == 2        # Kasia + Piotr
    assert teams_by_name["Rates"]["rules_count"] == 1         # rates-big-rejections
    assert teams_by_name["Rates"]["sources_count"] == 1       # trade-gateway
    assert teams_by_name["Payments"]["people_count"] == 2     # Anna + Zofia
    assert teams_by_name["Pricing"]["people_count"] == 1      # Marek
    sources = {s["key"] for s in ok(client.get("/api/sources"))}
    assert {"demo", "trade-gateway", "payments-webhook", "settlement-kafka", "pricing-engine-logs"} == sources


def test_settlements_end_to_end_and_antiflood_dedup():
    DELIVERIES_LOG.clear()
    src = _source_by_key("settlement-kafka")
    workflow_ev = {
        "type": "WORKFLOW_FAILED",
        "workflowId": "WF-20261121-00042",
        "workflowName": "order-settlement",
        "step": "validate-counterparty",
        "severity": "ERROR",
        "environment": "prod",
        "error": {"code": "TIMEOUT", "message": "Counterparty service did not respond in 5000 ms"},
    }

    res1 = ok(client.post(f"/api/sources/{src['id']}/simulate", json={
        "count": 1,
        "custom_payload": json.dumps(workflow_ev),
    }))
    assert res1["simulated_count"] == 1
    assert len(DELIVERIES_LOG) == 1

    d = DELIVERIES_LOG[0]
    assert d["rule_id"] == "settlements-prod"
    assert d["team"] == "Settlements"
    assert d["count"] == 1
    assert len(d["steps"]) == 3
    assert [s["action"] for s in d["steps"]] == ["http_get", "retry_workflow", "escalate"]
    assert d["steps"][1]["params"] == {"workflowId": "WF-20261121-00042"}
    assert [s["approval"] for s in d["steps"]] == ["none", "none", "required"]

    recips = {(name, ch) for _, name, ch, _ in d["recipients"]}
    assert recips == {("team:Settlements", "ui"), ("Tom", "phone"), ("Tom", "sms"), ("Ewa", "sms")}

    # 5 more identical events -> still 1 open alert with count=6, NO extra enqueue_deliveries calls!
    res_flood = ok(client.post(f"/api/sources/{src['id']}/simulate", json={
        "count": 5,
        "custom_payload": json.dumps(workflow_ev),
    }))
    assert res_flood["simulated_count"] == 5
    assert len(DELIVERIES_LOG) == 1  # NO flood!

    alert_id = d["alert_id"]
    alert = ok(client.get(f"/api/alerts/{alert_id}"))
    assert alert["count"] == 6 and alert["status"] == "open"
    persisted_deliveries = ok(client.get(f"/api/deliveries?alert_id={alert_id}"))
    assert len(persisted_deliveries) == 3  # Tom (phone + sms) + Ewa (sms); ui is live-feed only
    assert sorted((row["recipient_name"], row["channel"]) for row in persisted_deliveries) == [
        ("Ewa", "sms"),
        ("Tom", "phone"),
        ("Tom", "sms"),
    ]

    # Resolve the alert -> next occurrence creates a NEW alert and notifies once again
    ok(client.post(f"/api/alerts/{alert_id}/resolve"))
    ok(client.post(f"/api/sources/{src['id']}/simulate", json={
        "count": 1,
        "custom_payload": json.dumps(workflow_ev),
    }))
    assert len(DELIVERIES_LOG) == 2
    assert DELIVERIES_LOG[1]["alert_id"] != alert_id
    assert DELIVERIES_LOG[1]["count"] == 1


def test_pricing_logfile_key_value_and_grouping():
    DELIVERIES_LOG.clear()
    src = _source_by_key("pricing-engine-logs")
    # Point logfile path into temp directory so /tmp is untouched
    temp_log = os.path.join(_tmp, "pricing-test.log")
    ok(client.put(f"/api/sources/{src['id']}", json={
        "config": {**src["config"], "file_path": temp_log},
    }))

    line = (
        '2026-11-21T00:15:00Z WARN service=pricing-engine-eu1 '
        'instrument=EURUSD latency_ms=1420 message="Cache latency exceeded 1000ms threshold"'
    )
    ok(client.post(f"/api/sources/{src['id']}/simulate", json={"count": 2, "custom_payload": line}))
    assert len(DELIVERIES_LOG) == 1
    d = DELIVERIES_LOG[0]
    assert d["rule_id"] == "pricing-warnings"
    assert d["title"] == "Pricing warnings for EURUSD"
    # Team feed always; Marek (Pricing lead) has no warning preference -> default email
    assert d["recipients"] == [(None, "team:Pricing", "ui", None), (5, "Marek", "email", "marek@example.com")]
    assert len(d["steps"]) == 4  # Appendix B pricing text splits into 4 steps
    alert = ok(client.get(f"/api/alerts/{d['alert_id']}"))
    assert alert["count"] == 2
    assert alert["dedup_key"] == "pricing-warnings"  # repeats of the same rule share one alert


def test_rates_webhook_ingest():
    DELIVERIES_LOG.clear()
    payload = {
        "meta": {"schema": "trade.rejected.v2", "producer": "trade-gateway", "ts": 1792833245000},
        "payload": {"tradeId": "T-998877", "desk": "rates", "notional": 25000000, "currency": "EUR", "reason": "LIMIT_BREACH"},
    }
    res = ok(client.post("/api/ingest/trade-gateway", json=payload))
    assert res["accepted"] == 1 and len(res["alerts"]) == 1
    assert len(DELIVERIES_LOG) == 1
    d = DELIVERIES_LOG[0]
    assert d["rule_id"] == "rates-big-rejections"
    assert d["title"] == "Rejected EUR 25000000 — LIMIT_BREACH"
    recips = {(name, ch) for _, name, ch, _ in d["recipients"]}
    assert recips == {("team:Rates", "ui"), ("Kasia", "email"), ("Piotr", "email")}


def test_payments_anna_quiet_hours_and_runbook_approval():
    DELIVERIES_LOG.clear()
    payload = {
        "alertname": "HighErrorRate",
        "labels": {"service": "payments-api", "region": "eu-west", "severity": "critical"},
        "annotations": {"summary": "Error rate 12% over the last 5 minutes"},
        "startsAt": "2026-11-21T00:13:00Z",
        "status": "firing",
    }
    res = ok(client.post("/api/ingest/payments-webhook", json=payload))
    assert res["accepted"] == 1 and len(res["alerts"]) == 1
    assert len(DELIVERIES_LOG) == 1
    d = DELIVERIES_LOG[0]
    assert d["rule_id"] == "anna-payments-critical"
    assert d["steps"][1]["approval"] == "required"

    expected_ch = "sms" if 8 <= datetime.now().hour < 20 else "email"
    assert [(name, ch) for _, name, ch, _ in d["recipients"]] == [("team:Anna", "ui"), ("Anna", expected_ch)]

    db = SessionLocal()
    try:
        day_r = plan_recipients(db, "Anna", "critical", ["sms"], datetime(2026, 11, 21, 12, 0))
        night_r = plan_recipients(db, "Anna", "critical", ["sms"], datetime(2026, 11, 21, 23, 0))
        assert [(p.recipient.name, p.recipient.channel) for p in day_r] == [("team:Anna", "ui"), ("Anna", "sms")]
        assert [(p.recipient.name, p.recipient.channel) for p in night_r] == [("team:Anna", "ui"), ("Anna", "email")]
    finally:
        db.close()


def test_step_approval_rbac():
    # Use the latest open Settlements alert created in test_settlements_end_to_end_and_antiflood_dedup
    alerts = ok(client.get("/api/alerts?team=Settlements&status=open"))
    assert alerts
    settlement_alert_id = alerts[0]["id"]

    tom_hdr = _auth_header("tom", "tom@example.com", is_admin=False)
    marek_hdr = _auth_header("marek", "marek@example.com", is_admin=False)
    ewa_hdr = _auth_header("ewa", "ewa@example.com", is_admin=False)
    admin_hdr = _auth_header("sec_admin", "sec_admin@example.com", is_admin=True)
    demo_hdr = _auth_header("demo_tester", "demo_user@example.com", is_admin=False)

    # Regular team member (Tom) -> 403
    ok(client.post(f"/api/alerts/{settlement_alert_id}/steps/2/approve", headers=tom_hdr), 403)
    # Wrong team lead (Marek, lead of Pricing) -> 403
    ok(client.post(f"/api/alerts/{settlement_alert_id}/steps/2/approve", headers=marek_hdr), 403)
    # Mark done before approval -> 409
    ok(client.post(f"/api/alerts/{settlement_alert_id}/steps/2/done", headers=ewa_hdr), 409)
    # Right team lead (Ewa, lead of Settlements) -> 200, then mark done -> 200
    approved = ok(client.post(f"/api/alerts/{settlement_alert_id}/steps/2/approve", headers=ewa_hdr))
    assert approved["steps"][2]["approved_by"] == "ewa"
    done = ok(client.post(f"/api/alerts/{settlement_alert_id}/steps/2/done", headers=tom_hdr))
    assert done["steps"][2]["done"] is True and done["steps"][2]["done_by"] == "tom"

    # Payments alert (routed to "Anna" -> Anna's team is "Payments" -> lead is Zofia, or Admin)
    pay_alerts = ok(client.get("/api/alerts?team=Anna&status=open"))
    assert pay_alerts
    pay_alert_id = pay_alerts[0]["id"]
    ok(client.post(f"/api/alerts/{pay_alert_id}/steps/1/approve", headers=marek_hdr), 403)
    admin_approved = ok(client.post(f"/api/alerts/{pay_alert_id}/steps/1/approve", headers=admin_hdr))
    assert admin_approved["steps"][1]["approved_by"] == "sec_admin"

    # Unlinked demo user fallback on a fresh Settlements alert
    ok(client.post(f"/api/alerts/{settlement_alert_id}/resolve", headers=admin_hdr))
    src = _source_by_key("settlement-kafka")
    ok(client.post(f"/api/sources/{src['id']}/simulate", json={
        "count": 1,
        "custom_payload": json.dumps({
            "type": "WORKFLOW_FAILED",
            "workflowId": "WF-DEMO-2",
            "workflowName": "order-settlement",
            "step": "validate-counterparty",
            "environment": "prod",
            "error": {"code": "TIMEOUT", "message": "Timeout"},
        }),
    }))
    fresh_alerts = ok(client.get("/api/alerts?team=Settlements&status=open"))
    demo_approved = ok(client.post(f"/api/alerts/{fresh_alerts[0]['id']}/steps/2/approve", headers=demo_hdr))
    assert demo_approved["steps"][2]["approved_by"] == "demo_tester"


def test_dry_run_matches_rules_engine_and_rule_edit_keeps_runbook():
    non_matching = {
        "type": "WORKFLOW_FAILED",
        "workflowName": "order-settlement",
        "environment": "uat",
        "error": {"code": "TIMEOUT", "message": "Timeout"},
    }
    dr_none = ok(client.post("/api/sources/dry-run", json={"kind": "webhook", "config": {}, "raw_sample": non_matching}))
    assert dr_none["matched_rules"] == []

    matching = {
        "type": "WORKFLOW_FAILED",
        "workflowId": "WF-DRY-1",
        "workflowName": "order-settlement",
        "step": "book-ledger",
        "environment": "prod",
        "error": {"code": "TIMEOUT", "message": "Timed out"},
    }
    dr_hit = ok(client.post("/api/sources/dry-run", json={"kind": "webhook", "config": {}, "raw_sample": matching}))
    assert len(dr_hit["matched_rules"]) == 1
    m = dr_hit["matched_rules"][0]
    assert m["rule_id"] == "settlements-prod"
    assert m["rendered_title"] == "Workflow order-settlement failed at step book-ledger"
    assert len(m["steps"]) == 3 and m["steps"][1]["params"]["workflowId"] == "WF-DRY-1"

    # Rule PUT preserves runbook_id when passed
    rule = ok(client.get("/api/rules/settlements-prod"))
    orig_rb = rule["runbook_id"]
    assert orig_rb is not None
    updated = ok(client.put("/api/rules/settlements-prod", json={**rule, "name": "Settlement workflow failed in prod (edited)"}))
    assert updated["runbook_id"] == orig_rb


def test_team_rename_cascades_across_entities():
    admin_hdr = _auth_header("team_admin", "team_admin@example.com", is_admin=True)
    team = ok(client.post("/api/admin/teams", json={"name": "TempOps", "description": "Temp"}, headers=admin_hdr), 201)
    person = ok(client.post("/api/people", json={
        "name": "TempUser", "team": "TempOps", "email": "temp@example.com",
        "channel_prefs": {"warning": ["email"]},
    }), 201)
    rule = ok(client.post("/api/rules", json={
        "name": "Temp rule", "team": "TempOps",
        "condition": {"and": [{"field": "temp_flag", "op": "eq", "value": "yes"}]},
        "channels": ["email", "ui"], "title": "Temp alert",
    }), 201)
    src = ok(client.post("/api/sources", json={
        "name": "temp-src", "team": "TempOps", "kind": "webhook", "enabled": True,
    }))
    ok(client.post(f"/api/ingest/{src['key']}", json={"temp_flag": "yes"}))
    alerts_before = ok(client.get("/api/alerts?team=TempOps"))
    assert len(alerts_before) == 1

    ok(client.put(f"/api/admin/teams/{team['id']}", json={"name": "RenamedOps"}, headers=admin_hdr))

    assert ok(client.get(f"/api/people/{person['id']}"))["team"] == "RenamedOps"
    assert ok(client.get(f"/api/rules/{rule['id']}"))["team"] == "RenamedOps"
    assert _source_by_key(src["key"])["team"] == "RenamedOps"
    alerts_after = ok(client.get("/api/alerts?team=RenamedOps"))
    assert len(alerts_after) == 1 and alerts_after[0]["id"] == alerts_before[0]["id"]


def test_unified_teams_auth_sync_source_validation_and_delete_guard():
    admin_hdr = _auth_header("team_admin", "team_admin@example.com", is_admin=True)
    invite = ok(client.post("/api/admin/invites", json={"is_admin": False}, headers=admin_hdr), 201)
    code = invite["code"]

    # Unknown team fails with 422 and does NOT consume the invite code
    ok(client.post("/api/auth/register", json={
        "uname": "synced_user",
        "email": "synced@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "invite_code": code,
        "team": "NonExistent",
    }), 422)

    # Valid registration normalizes case and auto-creates matching Person in People roster
    reg = ok(client.post("/api/auth/register", json={
        "uname": "synced_user",
        "email": "synced@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "invite_code": code,
        "nrtel": "+48 600 999 111",
        "team": "payments",
    }), 201)
    assert reg["user"]["team"] == "Payments" and reg["user"]["dzial"] == "Payments"
    user_hdr = {"Authorization": f"Bearer {reg['access_token']}"}
    pay_people = ok(client.get("/api/people?team=Payments"))
    synced_person = next((p for p in pay_people if p["email"] == "synced@example.com"), None)
    assert synced_person is not None and synced_person["name"] == "synced_user"

    # Updating profile via PUT /api/auth/me updates both user and linked Person
    me_upd = ok(client.put("/api/auth/me", json={"team": "rates"}, headers=user_hdr))
    assert me_upd["team"] == "Rates" and me_upd["dzial"] == "Rates"
    assert ok(client.get(f"/api/people/{synced_person['id']}"))["team"] == "Rates"

    # Sources validate team against unified Teams directory
    ok(client.post("/api/sources", json={"name": "bad-src", "team": "BogusTeam", "kind": "webhook"}), 422)
    norm_src = ok(client.post("/api/sources", json={"name": "norm-src", "team": "rates", "kind": "webhook"}))
    assert norm_src["team"] == "Rates"
    shared_src = ok(client.post("/api/sources", json={"name": "shared-src", "team": "All", "kind": "webhook"}))
    assert shared_src["team"] == "All"

    # Delete guard: team with people/rules returns 409; empty team deletes cleanly with 200
    teams_by_name = {t["name"]: t for t in ok(client.get("/api/teams"))}
    ok(client.delete(f"/api/admin/teams/{teams_by_name['Settlements']['id']}", headers=admin_hdr), 409)
    empty_team = ok(client.post("/api/admin/teams", json={"name": "EmptyTeam"}, headers=admin_hdr), 201)
    ok(client.delete(f"/api/admin/teams/{empty_team['id']}", headers=admin_hdr), 200)


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
