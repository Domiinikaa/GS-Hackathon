"""
Automated tests for SMS, email (SMTP), and phone alerting channels, Outbox retries,
inbound SMS/phone replies, end-to-end ingest pipeline, and background worker lifecycle.

Uses an isolated temporary file-based SQLite DB (app.db is never touched).
"""
from __future__ import annotations

import email
import email.policy
import os
import re
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from typing import Any

# Configure isolated temporary SQLite database before importing app modules
_tmp_dir = tempfile.mkdtemp(prefix="gs_channels_test_")
if "database" not in sys.modules:
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp_dir, 'test_channels.db')}"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Alert, ChannelSetting, Delivery, GatewayMessage  # noqa: E402
from services.channels.messages import build_message  # noqa: E402
from services.delivery import MAX_ATTEMPTS, process_due  # noqa: E402

# czysta baza z danymi startowymi przed testami tego pliku – patrz tests/conftest.py
SEED = {"include_people": True}


# ---------------------------------------------------------------- helpers

class CapturingSMTPServer:
    """Minimal in-process TCP SMTP server on 127.0.0.1 for testing real smtplib.SMTP."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self._sock.settimeout(0.2)
        self.port: int = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="test-smtp-server", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(15.0)
            conn.sendall(b"220 localhost TestSMTP\r\n")
            buf = b""
            mail_from = ""
            rcpt_to: list[str] = []
            in_data = False
            data_lines: list[bytes] = []

            while not self._stop.is_set():
                while b"\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                line, buf = buf.split(b"\r\n", 1)

                if in_data:
                    if line == b".":
                        in_data = False
                        raw_bytes = b"\r\n".join(
                            l[1:] if l.startswith(b"..") else l for l in data_lines
                        )
                        parsed = email.message_from_bytes(raw_bytes, policy=email.policy.default)
                        with self._lock:
                            self.messages.append({
                                "mail_from": mail_from,
                                "rcpt_to": list(rcpt_to),
                                "raw": raw_bytes.decode("utf-8", errors="replace"),
                                "parsed": parsed,
                            })
                        data_lines = []
                        conn.sendall(b"250 OK\r\n")
                    else:
                        data_lines.append(line)
                    continue

                cmd_text = line.decode("utf-8", errors="replace")
                upper = cmd_text.upper()
                if upper.startswith("EHLO"):
                    conn.sendall(b"250-localhost\r\n250 SIZE 10485760\r\n")
                elif upper.startswith("HELO"):
                    conn.sendall(b"250 localhost\r\n")
                elif upper.startswith("MAIL FROM:"):
                    mail_from = cmd_text[10:].strip()
                    conn.sendall(b"250 OK\r\n")
                elif upper.startswith("RCPT TO:"):
                    rcpt_to.append(cmd_text[8:].strip())
                    conn.sendall(b"250 OK\r\n")
                elif upper == "DATA":
                    in_data = True
                    data_lines = []
                    conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                elif upper == "QUIT":
                    conn.sendall(b"221 Bye\r\n")
                    return
                elif upper == "NOOP":
                    conn.sendall(b"250 OK\r\n")
                elif upper == "RSET":
                    mail_from = ""
                    rcpt_to = []
                    conn.sendall(b"250 OK\r\n")
                else:
                    conn.sendall(b"500 Unknown command\r\n")

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)


@pytest.fixture()
def smtp_server():
    srv = CapturingSMTPServer()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture()
def client():
    # Non-context-manager TestClient keeps lifespan off for deterministic manual process_due() tests
    return TestClient(main.app)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_outage_flags():
    yield
    session = SessionLocal()
    try:
        session.query(ChannelSetting).delete()
        session.commit()
    finally:
        session.close()


def _closed_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _extract_bodies(parsed_msg: email.message.EmailMessage) -> tuple[str, str]:
    plain = ""
    html_part = ""
    if parsed_msg.is_multipart():
        for part in parsed_msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                plain = part.get_content()
            elif ctype == "text/html":
                html_part = part.get_content()
    else:
        plain = parsed_msg.get_content()
    return plain, html_part


# ---------------------------------------------------------------- 1. Message formatting

def test_build_messages_formats():
    alert = Alert(
        id=42,
        rule_id="r-1",
        team="Payments",
        dedup_key="k-42",
        title="HighErrorRate <script>alert(1)</script>",
        body="Rate > 12% & rising",
        severity="critical",
        color="red",
        status="open",
        count=3,
        steps=[
            {"text": "Check <logs> first", "approval": "none"},
            {"text": "Failover region", "approval": "required"},
        ],
    )

    em = build_message(alert, "email", "anna@example.com", name="Anna")
    assert em.subject == "[CRITICAL] HighErrorRate <script>alert(1)</script> (×3)"
    assert "Hi Anna," in em.body
    assert "1. Check <logs> first" in em.body
    assert "2. Failover region  (needs approval)" in em.body
    assert "/#alerts/42" in em.body
    assert em.html is not None
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in em.html
    assert "Rate &gt; 12% &amp; rising" in em.html
    assert "Failover region  (needs approval)" in em.html
    assert "/#alerts/42" in em.html

    sms_approval = build_message(alert, "sms", "+48 600 000 001", reply_code="4821")
    assert sms_approval.body.startswith("[CRIT] ")
    assert "/#alerts/42" in sms_approval.body
    assert "Reply ACK 4821 / YES 4821=approve" in sms_approval.body
    assert len(sms_approval.body) <= 160

    no_approval_alert = Alert(
        id=43,
        rule_id="r-2",
        team="IT",
        dedup_key="k-43",
        title="X" * 200,
        body=None,
        severity="warning",
        color="amber",
        status="open",
        count=1,
        steps=[{"text": "Simple step", "approval": "none"}],
    )
    sms_plain = build_message(no_approval_alert, "sms", "+48 600 000 001", reply_code="9912")
    assert sms_plain.body.startswith("[WARN] ")
    assert "Reply ACK 9912" in sms_plain.body
    assert "YES 9912" not in sms_plain.body
    assert "…" in sms_plain.body
    assert len(sms_plain.body) <= 160

    phone_msg = build_message(alert, "phone", "+48 600 000 002")
    assert "critical alert for team Payments" in phone_msg.body
    assert alert.title in phone_msg.body
    assert "Press 1 to acknowledge" in phone_msg.body


# ---------------------------------------------------------------- 2. Channels & outage API

def test_channels_endpoint_and_outage_validation(client):
    resp = client.get("/api/channels")
    assert resp.status_code == 200
    assert resp.json() == [
        {"channel": "email", "down": False},
        {"channel": "sms", "down": False},
        {"channel": "phone", "down": False},
    ]

    for ch in ("sms", "phone"):
        r_down = client.put(f"/api/channels/{ch}/outage", json={"down": True})
        assert r_down.status_code == 200
        assert r_down.json() == {"channel": ch, "down": True}
        state = {c["channel"]: c["down"] for c in client.get("/api/channels").json()}
        assert state[ch] is True

        r_up = client.put(f"/api/channels/{ch}/outage", json={"down": False})
        assert r_up.status_code == 200
        assert r_up.json() == {"channel": ch, "down": False}

    r_email = client.put("/api/channels/email/outage", json={"down": True})
    assert r_email.status_code == 400


# ---------------------------------------------------------------- 3. Email SMTP success

def test_email_smtp_delivery_success(client, db, smtp_server, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(smtp_server.port))
    monkeypatch.setenv("SMTP_STARTTLS", "0")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("MAIL_FROM", "GS Alerting <alerts@test.local>")

    alert = client.post("/api/alerts/test", json={"dedup_key": "smtp-ok-1"}).json()
    d = client.post(
        "/api/deliveries/test",
        json={"channel": "email", "to": "kasia@example.com", "name": "Kasia", "alert_id": alert["id"]},
    ).json()
    assert d["status"] == "pending"

    tried = process_due(db)
    assert tried >= 1

    refreshed = next(x for x in client.get(f"/api/deliveries?alert_id={alert['id']}").json() if x["id"] == d["id"])
    assert refreshed["status"] == "sent"
    assert refreshed["attempts"] == 1
    assert refreshed["sent_at"] is not None
    assert refreshed["last_error"] is None

    assert len(smtp_server.messages) == 1
    msg = smtp_server.messages[0]["parsed"]
    assert msg["To"] == "kasia@example.com"
    assert msg["From"] == "GS Alerting <alerts@test.local>"
    assert "[CRITICAL] HighErrorRate on payments-api" in msg["Subject"]

    plain, html_part = _extract_bodies(msg)
    assert "Hi Kasia," in plain
    assert f"/#alerts/{alert['id']}" in plain
    assert "Fail traffic over to the other region" in plain
    assert f"/#alerts/{alert['id']}" in html_part
    assert "HighErrorRate on payments-api" in html_part


# ---------------------------------------------------------------- 4. SMTP failure, backoff & dead-letter

def test_email_smtp_failure_backoff_and_dead_letter(client, db, monkeypatch):
    closed_port = _closed_local_port()
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(closed_port))
    monkeypatch.setenv("SMTP_STARTTLS", "0")

    alert = client.post("/api/alerts/test", json={"dedup_key": "smtp-fail-1"}).json()
    d = client.post(
        "/api/deliveries/test",
        json={"channel": "email", "to": "fail@example.com", "name": "Fail", "alert_id": alert["id"]},
    ).json()
    did = d["id"]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        row = db.get(Delivery, did, populate_existing=True)
        row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

        before = datetime.utcnow()
        process_due(db)

        row = db.get(Delivery, did, populate_existing=True)
        assert row.attempts == attempt
        assert row.last_error is not None and "SMTP" in row.last_error
        if attempt < MAX_ATTEMPTS:
            assert row.status == "failed"
            assert row.next_attempt_at is not None
            delta = (row.next_attempt_at - before).total_seconds()
            expected = 2 ** attempt
            assert expected - 2 <= delta <= expected + 5
        else:
            assert row.status == "dead"
            assert row.next_attempt_at is None


# ---------------------------------------------------------------- 5. SMS & phone fake gateway + outage recovery

def test_sms_and_phone_fake_gateway_and_outage_recovery(client, db):
    alert = client.post("/api/alerts/test", json={"dedup_key": "gw-outage-1"}).json()

    # Enable outages on both SMS and phone
    assert client.put("/api/channels/sms/outage", json={"down": True}).status_code == 200
    assert client.put("/api/channels/phone/outage", json={"down": True}).status_code == 200

    sms_d = client.post(
        "/api/deliveries/test",
        json={"channel": "sms", "to": "+48 600 111 222", "name": "TestSms", "alert_id": alert["id"]},
    ).json()
    phone_d = client.post(
        "/api/deliveries/test",
        json={"channel": "phone", "to": "+48 600 111 333", "name": "TestPhone", "alert_id": alert["id"]},
    ).json()

    process_due(db)

    for did, ch in ((sms_d["id"], "sms"), (phone_d["id"], "phone")):
        row = db.get(Delivery, did, populate_existing=True)
        assert row.status == "failed"
        assert row.attempts == 1
        assert f"fake {ch} gateway is down" in (row.last_error or "")

    # Restore channels and make deliveries immediately due
    assert client.put("/api/channels/sms/outage", json={"down": False}).status_code == 200
    assert client.put("/api/channels/phone/outage", json={"down": False}).status_code == 200
    for did in (sms_d["id"], phone_d["id"]):
        row = db.get(Delivery, did, populate_existing=True)
        row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    process_due(db)

    for did in (sms_d["id"], phone_d["id"]):
        row = db.get(Delivery, did, populate_existing=True)
        assert row.status == "sent"
        assert row.attempts == 2
        assert row.last_error is None

    phones = {p["number"]: p["name"] for p in client.get("/api/channels/phones").json()}
    assert phones["+48 600 111 222"] == "TestSms"
    assert phones["+48 600 111 333"] == "TestPhone"

    sms_thread = client.get("/api/channels/messages", params={"number": "+48 600 111 222"}).json()
    assert any(m["direction"] == "out" and m["channel"] == "sms" and m["delivery_id"] == sms_d["id"] for m in sms_thread)

    phone_thread = client.get("/api/channels/messages", params={"number": "+48 600 111 333"}).json()
    assert any(
        m["direction"] == "out"
        and m["channel"] == "phone"
        and m["delivery_id"] == phone_d["id"]
        and "Press 1 to acknowledge" in m["body"]
        for m in phone_thread
    )


# ---------------------------------------------------------------- 6. Inbound SMS commands & security

def test_sms_inbound_ack_approve_resolve_and_security(client, db):
    alert = client.post("/api/alerts/test", json={"dedup_key": "sms-inbound-1"}).json()
    aid = alert["id"]
    d = client.post(
        "/api/deliveries/test",
        json={"channel": "sms", "to": "+48 600 000 001", "name": "Anna", "alert_id": aid},
    ).json()
    process_due(db)

    row = db.get(Delivery, d["id"], populate_existing=True)
    assert row.status == "sent"
    code = row.reply_code
    assert code and re.fullmatch(r"\d{4}", code)

    # Wrong phone number trying to use a valid code
    r_wrong = client.post("/api/channels/sms/inbound", json={"from": "+48 999 999 999", "text": f"ACK {code}"}).json()
    assert r_wrong["ok"] is False
    assert "not valid for this number" in r_wrong["reply"]
    assert client.get(f"/api/alerts/{aid}").json()["status"] == "open"

    # Invalid syntax
    r_bad = client.post("/api/channels/sms/inbound", json={"from": "+48 600 000 001", "text": "HELLO"}).json()
    assert r_bad["ok"] is False
    assert "not understood" in r_bad["reply"]
    msgs = client.get("/api/channels/messages", params={"number": "+48 600 000 001"}).json()
    assert any(m["direction"] == "in" and m["body"] == "HELLO" for m in msgs)
    assert any(m["direction"] == "out" and "not understood" in m["body"] for m in msgs)

    # ACK from matching number formatted differently (without spaces)
    r_ack = client.post("/api/channels/sms/inbound", json={"from": "+48600000001", "text": f"ack {code}"}).json()
    assert r_ack["ok"] is True
    assert r_ack["alert_id"] == aid
    a_after_ack = client.get(f"/api/alerts/{aid}").json()
    assert a_after_ack["status"] == "acknowledged"
    assert any(h["who"] == "Anna (SMS)" and h["what"] == "acknowledged" for h in a_after_ack["history"])

    # Second ACK rejected gracefully (409 -> ok=False)
    r_ack2 = client.post("/api/channels/sms/inbound", json={"from": "+48 600 000 001", "text": f"ACK {code}"}).json()
    assert r_ack2["ok"] is False

    # YES approves step index 1 (which has approval == "required")
    r_yes = client.post("/api/channels/sms/inbound", json={"from": "+48 600 000 001", "text": f"YES {code}"}).json()
    assert r_yes["ok"] is True
    assert "step 2 approved" in r_yes["reply"]
    a_after_yes = client.get(f"/api/alerts/{aid}").json()
    assert a_after_yes["steps"][1]["approved_by"] == "Anna (SMS)"
    assert any(h["who"] == "Anna (SMS)" and "approved step 2" in h["what"] for h in a_after_yes["history"])

    # Second YES -> no step waiting for approval
    r_yes2 = client.post("/api/channels/sms/inbound", json={"from": "+48 600 000 001", "text": f"YES {code}"}).json()
    assert r_yes2["ok"] is False
    assert "no step waiting for approval" in r_yes2["reply"]

    # RESOLVE
    r_res = client.post("/api/channels/sms/inbound", json={"from": "+48 600 000 001", "text": f"RESOLVE {code}"}).json()
    assert r_res["ok"] is True
    a_after_res = client.get(f"/api/alerts/{aid}").json()
    assert a_after_res["status"] == "resolved"
    assert any(h["who"] == "Anna (SMS)" and h["what"] == "resolved" for h in a_after_res["history"])


# ---------------------------------------------------------------- 7. Inbound phone keypress

def test_phone_inbound_keypress(client, db):
    # No recent call to an unknown number
    r_none = client.post("/api/channels/phone/inbound", json={"from": "+48 777 000 999", "digit": "1"}).json()
    assert r_none["ok"] is False
    assert "No recent call" in r_none["reply"]

    alert = client.post("/api/alerts/test", json={"dedup_key": "phone-inbound-1"}).json()
    aid = alert["id"]
    client.post(
        "/api/deliveries/test",
        json={"channel": "phone", "to": "+48 600 000 002", "name": "Tom", "alert_id": aid},
    )
    process_due(db)

    # Unsupported digit
    r_bad = client.post("/api/channels/phone/inbound", json={"from": "+48 600 000 002", "digit": "2"}).json()
    assert r_bad["ok"] is False
    assert "Only 1" in r_bad["reply"]
    assert client.get(f"/api/alerts/{aid}").json()["status"] == "open"

    # Press 1 -> acknowledge
    r_ok = client.post("/api/channels/phone/inbound", json={"from": "+48600000002", "digit": "1"}).json()
    assert r_ok["ok"] is True
    assert r_ok["alert_id"] == aid
    a_after = client.get(f"/api/alerts/{aid}").json()
    assert a_after["status"] == "acknowledged"
    assert any(h["who"] == "Tom (phone)" and h["what"] == "acknowledged" for h in a_after["history"])

    msgs = client.get("/api/channels/messages", params={"number": "+48 600 000 002"}).json()
    assert any(m["channel"] == "phone" and m["direction"] == "in" and m["body"] == "pressed 1" for m in msgs)
    assert any(
        m["channel"] == "phone" and m["direction"] == "out" and f"alert {aid} acknowledged" in m["body"]
        for m in msgs
    )


# ---------------------------------------------------------------- 8. E2E ingest pipeline + dedup anti-flood

def test_e2e_ingest_pipeline_dedup_and_channels(client, db, smtp_server, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(smtp_server.port))
    monkeypatch.setenv("SMTP_STARTTLS", "0")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    settlement_payload = {
        "type": "WORKFLOW_FAILED",
        "workflowName": "order-settlement",
        "environment": "prod",
        "workflowId": "WF-E2E-99",
        "step": "book-cash",
        "error": {"code": "TIMEOUT", "message": "Timed out"},
    }

    r1 = client.post("/api/ingest/trade-gateway", json=settlement_payload)
    assert r1.status_code == 200
    [s_alert_id] = r1.json()["alerts"]

    # Seeded Business team: Tom (on_call=True -> phone + sms) and Ewa (lead -> sms). UI is skipped in deliveries.
    s_deliveries = client.get(f"/api/deliveries?alert_id={s_alert_id}").json()
    assert sorted((d["recipient_name"], d["channel"]) for d in s_deliveries) == [
        ("Ewa", "sms"),
        ("Tom", "phone"),
        ("Tom", "sms"),
    ]

    process_due(db)
    s_deliveries_after = client.get(f"/api/deliveries?alert_id={s_alert_id}").json()
    assert all(d["status"] == "sent" for d in s_deliveries_after)

    # Duplicate event: count increments, NO new deliveries created (anti-flood)
    r2 = client.post("/api/ingest/trade-gateway", json=settlement_payload)
    assert r2.status_code == 200
    assert r2.json()["alerts"] == [s_alert_id]
    assert client.get(f"/api/alerts/{s_alert_id}").json()["count"] == 2
    assert len(client.get(f"/api/deliveries?alert_id={s_alert_id}").json()) == 3

    # Ingest trade rejection -> Finance team -> Kasia + Piotr via email
    trade_payload = {
        "meta": {"schema": "trade.rejected.v2"},
        "payload": {"desk": "rates", "notional": 25000000, "currency": "EUR", "reason": "LIMIT_BREACH"},
    }
    rt = client.post("/api/ingest/trade-gateway", json=trade_payload)
    assert rt.status_code == 200
    [t_alert_id] = rt.json()["alerts"]

    t_deliveries = client.get(f"/api/deliveries?alert_id={t_alert_id}").json()
    assert sorted((d["recipient_name"], d["channel"]) for d in t_deliveries) == [
        ("Kasia", "email"),
        ("Piotr", "email"),
    ]

    process_due(db)
    t_deliveries_after = client.get(f"/api/deliveries?alert_id={t_alert_id}").json()
    assert all(d["status"] == "sent" for d in t_deliveries_after)
    assert sorted(m["parsed"]["To"] for m in smtp_server.messages) == ["kasia@example.com", "piotr@example.com"]


# ---------------------------------------------------------------- 9. Lifespan background worker

def test_lifespan_starts_delivery_worker_automatically():
    with TestClient(main.app) as live_client:
        worker_threads = [t for t in threading.enumerate() if t.name == "delivery-worker" and t.is_alive()]
        assert len(worker_threads) == 1
        assert worker_threads[0].daemon is True

        alert = live_client.post("/api/alerts/test", json={"dedup_key": "worker-auto-1"}).json()
        d = live_client.post(
            "/api/deliveries/test",
            json={"channel": "sms", "to": "+48 600 555 000", "name": "WorkerTest", "alert_id": alert["id"]},
        ).json()

        deadline = time.time() + 4.0
        status = d["status"]
        while time.time() < deadline:
            rows = live_client.get(f"/api/deliveries?alert_id={alert['id']}").json()
            match = next((r for r in rows if r["id"] == d["id"]), None)
            if match and match["status"] == "sent":
                status = match["status"]
                break
            time.sleep(0.2)

        assert status == "sent"
