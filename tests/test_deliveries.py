"""
Tests for Notification Delivery, Outbox API, Channel Outages, Retries & Migration (Osoba 3).

    /Users/koperek/Desktop/programy/GS-Hackathon/.venv/bin/python tests/test_deliveries.py
"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'deliveries.db')}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

import main  # noqa: E402
from services.delivery import MAX_ATTEMPTS  # noqa: E402

client = TestClient(main.app)

TRADE_PAYLOAD = {
    "meta": {"schema": "trade.rejected.v2", "producer": "trade-gateway", "ts": 1792833245000},
    "payload": {
        "tradeId": "T-998877",
        "desk": "rates",
        "notional": 25000000,
        "currency": "EUR",
        "reason": "LIMIT_BREACH",
    },
}

PAYMENTS_PAYLOAD = {
    "alertname": "HighErrorRate",
    "labels": {"service": "payments-api", "region": "eu-west", "severity": "critical"},
    "annotations": {"summary": "Error rate 12% over the last 5 minutes"},
    "startsAt": "2026-11-21T00:13:00Z",
    "status": "firing",
}

SETTLEMENT_PAYLOAD = {
    "type": "WORKFLOW_FAILED",
    "workflowId": "WF-20261121-00042",
    "workflowName": "order-settlement",
    "step": "validate-counterparty",
    "severity": "ERROR",
    "environment": "prod",
    "error": {"code": "TIMEOUT", "message": "Counterparty service did not respond in 5000 ms"},
}


def ok(resp, status=200):
    assert resp.status_code == status, f"{resp.status_code} != {status}: {resp.text}"
    return resp.json()


def test_enqueue_deliveries_creates_rows_and_dedup_does_not_spam():
    r = ok(client.post("/api/ingest/trade-gateway", json=[TRADE_PAYLOAD, TRADE_PAYLOAD]))
    assert r["accepted"] == 2
    rates_alert_id = r["alerts"][0]

    rows = ok(client.get(f"/api/deliveries?alert_id={rates_alert_id}"))
    assert len(rows) == 3  # team:Rates (ui) + Kasia (email) + Piotr (email)

    ui_rows = [d for d in rows if d["channel"] == "ui"]
    email_rows = [d for d in rows if d["channel"] == "email"]
    assert len(ui_rows) == 1
    assert ui_rows[0]["person_id"] is None
    assert ui_rows[0]["status"] == "sent"
    assert ui_rows[0]["attempts"] == 1
    assert ui_rows[0]["sent_at"] is not None

    assert len(email_rows) == 2
    assert all(d["status"] == "pending" and d["attempts"] == 0 and d["sent_at"] is None for d in email_rows)

    # Duplicate ingest must NOT create duplicate Delivery rows
    ok(client.post("/api/ingest/trade-gateway", json=TRADE_PAYLOAD))
    rows_after = ok(client.get(f"/api/deliveries?alert_id={rates_alert_id}"))
    assert len(rows_after) == 3

    # Payments webhook & seeded demo webhook
    pay_res = ok(client.post("/api/ingest/payments-webhook", json=PAYMENTS_PAYLOAD))
    pay_rows = ok(client.get(f"/api/deliveries?alert_id={pay_res['alerts'][0]}"))
    assert len(pay_rows) == 1 and pay_rows[0]["person_name"] == "Anna" and pay_rows[0]["status"] == "pending"

    demo_res = ok(client.post("/api/ingest/demo", json=SETTLEMENT_PAYLOAD))
    demo_rows = ok(client.get(f"/api/deliveries?alert_id={demo_res['alerts'][0]}"))
    assert {(d["person_name"], d["channel"], d["status"]) for d in demo_rows} == {
        ("Team feed (Settlements)", "ui", "sent"),
        ("Tom", "phone", "pending"),
        ("Tom", "sms", "pending"),
        ("Ewa", "sms", "pending"),
    }


def test_process_pending_deliveries_and_message_previews():
    res = ok(client.post("/api/deliveries/process"))
    assert res["claimed"] >= 6 and res["failed"] == 0

    all_rows = ok(client.get("/api/deliveries?limit=100"))
    assert all(d["status"] == "sent" and d["sent_at"] is not None and d["last_error"] is None for d in all_rows)

    # Verify email preview includes runbook steps & link; SMS includes short link <= 160 chars
    settlement_alerts = ok(client.get("/api/alerts?team=Settlements&status=open"))
    s_alert_id = settlement_alerts[0]["id"]
    s_rows = ok(client.get(f"/api/deliveries?alert_id={s_alert_id}"))
    sms_row = next(d for d in s_rows if d["channel"] == "sms")
    phone_row = next(d for d in s_rows if d["channel"] == "phone")

    assert f"/#alerts/{s_alert_id}" in sms_row["message_preview"]["body"]
    assert len(sms_row["message_preview"]["body"]) <= 160
    assert "3 runbook steps ready" in phone_row["message_preview"]["script"]

    pay_alerts = ok(client.get("/api/alerts?team=Anna&status=open"))
    p_alert_id = pay_alerts[0]["id"]
    p_rows = ok(client.get(f"/api/deliveries?alert_id={p_alert_id}"))
    p_msg = p_rows[0]["message_preview"]
    assert f"/#alerts/{p_alert_id}" in p_msg["link"]
    if p_rows[0]["channel"] == "email":
        assert "Runbook steps:" in p_msg["body"]
        assert "[APPROVAL REQUIRED]" in p_msg["body"]


def test_simulated_outage_isolation_max_attempts_and_recovery():
    # Resolve existing Settlements alert so we can raise a fresh one
    for a in ok(client.get("/api/alerts?team=Settlements&status=open")):
        ok(client.post(f"/api/alerts/{a['id']}/resolve"))

    # Put SMS channel into simulated outage
    outage = ok(client.post("/api/deliveries/channels/sms/outage", json={
        "down": True,
        "error_message": "Simulated SMS gateway timeout",
    }))
    assert outage["simulated_down"] is True

    res = ok(client.post("/api/ingest/demo", json=SETTLEMENT_PAYLOAD))
    alert_1 = res["alerts"][0]

    # Attempt 1..5 -> phone/ui succeed; SMS fails up to MAX_ATTEMPTS
    proc1 = ok(client.post("/api/deliveries/process"))
    assert proc1["sent"] == 1 and proc1["failed"] == 2  # Tom phone sent; Tom+Ewa sms failed

    rows1 = ok(client.get(f"/api/deliveries?alert_id={alert_1}"))
    assert next(d for d in rows1 if d["channel"] == "phone")["status"] == "sent"
    assert next(d for d in rows1 if d["channel"] == "ui")["status"] == "sent"
    sms_rows_1 = [d for d in rows1 if d["channel"] == "sms"]
    assert all(
        d["status"] == "failed"
        and d["attempts"] == 1
        and d["last_error"] == "Simulated SMS gateway timeout"
        and d["next_retry_at"] is not None
        and d["exhausted"] is False
        for d in sms_rows_1
    )

    for expected_attempt in range(2, MAX_ATTEMPTS + 1):
        ok(client.post("/api/deliveries/process"))
    exhausted_rows = [d for d in ok(client.get(f"/api/deliveries?alert_id={alert_1}")) if d["channel"] == "sms"]
    assert all(d["attempts"] == MAX_ATTEMPTS and d["exhausted"] is True and d["next_retry_at"] is None for d in exhausted_rows)

    # Exhausted rows are no longer claimed automatically
    idle = ok(client.post("/api/deliveries/process"))
    assert idle == {"claimed": 0, "sent": 0, "failed": 0}

    # Trigger another fresh alert while SMS is still down (only 1 failed attempt -> retryable)
    ok(client.post(f"/api/alerts/{alert_1}/resolve"))
    alert_2 = ok(client.post("/api/ingest/demo", json=SETTLEMENT_PAYLOAD))["alerts"][0]
    ok(client.post("/api/deliveries/process"))

    # Restore SMS -> non-exhausted rows (alert_2) flush automatically!
    restored = ok(client.post("/api/deliveries/channels/sms/outage", json={"down": False}))
    assert restored["simulated_down"] is False
    assert restored["flushed"]["sent"] == 2

    rows_2 = ok(client.get(f"/api/deliveries?alert_id={alert_2}"))
    assert all(d["status"] == "sent" for d in rows_2)

    # Rescuing exhausted rows manually: single retry + retry-failed
    single_id = exhausted_rows[0]["id"]
    retried_one = ok(client.post(f"/api/deliveries/{single_id}/retry"))
    assert retried_one["status"] == "sent" and retried_one["attempts"] == 1 and retried_one["exhausted"] is False

    bulk = ok(client.post("/api/deliveries/retry-failed"))
    assert bulk["reset"] == 1 and bulk["sent"] == 1 and bulk["failed"] == 0


def test_deliveries_filters_stats_and_errors():
    stats = ok(client.get("/api/deliveries/stats"))
    assert stats["total"] == stats["sent"] + stats["pending"] + stats["failed"]
    assert stats["failed"] == 0 and stats["pending"] == 0 and stats["sent"] > 0
    assert len(stats["channels"]) == 4

    channels = ok(client.get("/api/deliveries/channels"))
    assert [c["channel"] for c in channels] == ["email", "sms", "phone", "ui"]

    emails = ok(client.get("/api/deliveries?status=sent&channel=email"))
    assert emails and all(d["channel"] == "email" and d["status"] == "sent" for d in emails)

    ok(client.post("/api/deliveries/channels/pigeon/outage", json={"down": True}), 404)
    ok(client.post("/api/deliveries/999999/retry"), 404)


def test_ensure_delivery_columns_migrates_old_table():
    old_engine = create_engine("sqlite://")
    with old_engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE deliveries ("
            "id INTEGER PRIMARY KEY, alert_id INTEGER NOT NULL, person_id INTEGER, "
            "channel VARCHAR(20) NOT NULL, \"to\" VARCHAR(200), status VARCHAR(20), "
            "attempts INTEGER, last_error TEXT, created_at DATETIME, sent_at DATETIME)"
        ))
    main.ensure_delivery_columns(old_engine)
    cols = {c["name"] for c in inspect(old_engine).get_columns("deliveries")}
    assert "next_retry_at" in cols
    main.ensure_delivery_columns(old_engine)  # idempotent second run


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
