"""
Testy API Osoby 4 na ŚWIEŻEJ, tymczasowej bazie SQLite (app.db nie jest ruszane).

    python tests/test_api.py

Sprawdza: dane startowe, runbooki (CRUD, podgląd, podpinanie, błędy), /api/engine/test
oraz pełną drogę zdarzenia /api/ingest -> baza -> silnik reguł -> przekazanie do Osoby 1.
"""
import os
import sys
import tempfile

# baza testowa MUSI być ustawiona przed importem aplikacji
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402  (tworzy tabele i wgrywa dane startowe do bazy testowej)
import services.pipeline as pipeline  # noqa: E402

client = TestClient(main.app)

SETTLEMENT = {"type": "WORKFLOW_FAILED", "workflowName": "order-settlement", "environment": "prod",
              "workflowId": "WF-1", "step": "book-cash", "error": {"code": "TIMEOUT", "message": "Timed out"}}
TRADE = {"meta": {"schema": "trade.rejected.v2"},
         "payload": {"desk": "rates", "notional": 25000000, "currency": "EUR", "reason": "LIMIT_BREACH"}}
PRICING = {"service": "pricing-engine-eu", "level": "WARN", "instrument": "EURUSD"}
PAYMENTS = {"alertname": "HighErrorRate", "labels": {"service": "payments-api", "severity": "critical"},
            "annotations": {"summary": "5xx > 5%"}}


def ok(resp, status=200):
    assert resp.status_code == status, f"{resp.status_code} != {status}: {resp.text}"
    return resp.json()


def rules_by_id():
    return {r["id"]: r for r in ok(client.get("/api/rules"))}


def engine(event, **extra):
    return ok(client.post("/api/engine/test", json={"event": event, **extra}))


# ---------------------------------------------------------------- dane startowe

def test_seed_runbooks_attached_to_rules():
    runbooks = {rb["name"]: rb for rb in ok(client.get("/api/runbooks"))}
    assert set(runbooks) == {"settlement-timeout", "payments-high-error-rate", "pricing-warnings"}
    rules = rules_by_id()
    assert rules["settlements-prod"]["runbook_id"] == runbooks["settlement-timeout"]["id"]
    assert rules["anna-payments-critical"]["runbook_id"] == runbooks["payments-high-error-rate"]["id"]
    assert rules["pricing-warnings"]["runbook_id"] == runbooks["pricing-warnings"]["id"]
    assert runbooks["settlement-timeout"]["steps"][0]["action"] == "http_get"
    assert runbooks["settlement-timeout"]["steps"][2]["approval"] == "required"
    assert runbooks["payments-high-error-rate"]["steps"][1]["approval"] == "required"
    # Osoba 4: z wolnego tekstu rozpoznajemy akcje (restart, wait, eskalacja); ryzykowne czekają na zgodę
    pricing = runbooks["pricing-warnings"]["steps"]
    assert [s["action"] for s in pricing] == [None, "restart_service", "wait", "escalate"]
    assert [s["approval"] for s in pricing] == ["none", "required", "none", "required"]


def test_restart_does_not_duplicate_seed():
    from database import SessionLocal
    from seed import seed_all
    db = SessionLocal()
    try:
        seed_all(db)  # drugi start serwera
    finally:
        db.close()
    assert len(ok(client.get("/api/runbooks"))) == 3


# ---------------------------------------------------------------- podgląd parsowania

def test_parse_preview_formats():
    r = ok(client.post("/api/runbooks/parse", json={"raw": "1. A\n2. B"}))
    assert r["format"] == "markdown" and [s["text"] for s in r["steps"]] == ["A", "B"]
    r = ok(client.post("/api/runbooks/parse", json={"raw": "Check logs\nsteps:\n- A", "format": "auto"}))
    assert r["format"] == "text" and len(r["steps"]) == 2          # zepsuty YAML w auto -> tekst
    r = ok(client.post("/api/runbooks/parse", json={"raw": "   "}))
    assert r["steps"] == []


def test_parse_preview_explicit_bad_yaml_is_readable_422():
    detail = ok(client.post("/api/runbooks/parse", json={"raw": "a\nsteps:\n- x", "format": "yaml"}), 422)["detail"]
    assert "not valid YAML" in detail and "line" in detail


# ---------------------------------------------------------------- CRUD runbooków

def test_runbook_crud_and_attach_flow():
    rb = ok(client.post("/api/runbooks", json={"name": "  test-rb  ", "raw": "1. Hello {{payload.reason}}"}))
    rb_id = rb["id"]
    assert rb["name"] == "test-rb" and rb["format"] == "markdown" and rb["steps"][0]["text"] == "Hello {{payload.reason}}"

    # podpięcie do reguły bez runbooka -> alert z tej reguły dostaje kroki z wartościami ze zdarzenia
    ok(client.post(f"/api/runbooks/{rb_id}/attach/rates-big-rejections"))
    assert ok(client.get(f"/api/runbooks/{rb_id}"))["rules"] == [
        {"id": "rates-big-rejections", "name": "Large rejected trades (rates desk)"}]
    [m] = engine(TRADE)["matched"]
    assert [s["text"] for s in m["steps"]] == ["Hello LIMIT_BREACH"]

    # edycja treści -> kroki parsowane od nowa; edycja samej nazwy nie rusza kroków
    rb = ok(client.put(f"/api/runbooks/{rb_id}", json={"raw": "1. Bye\n2. Again"}))
    assert [s["text"] for s in rb["steps"]] == ["Bye", "Again"]
    rb = ok(client.put(f"/api/runbooks/{rb_id}", json={"name": "renamed"}))
    assert rb["name"] == "renamed" and len(rb["steps"]) == 2

    # odpięcie, ponowne podpięcie, usunięcie -> reguła wraca do "bez runbooka"
    ok(client.delete(f"/api/runbooks/{rb_id}/attach/rates-big-rejections"))
    assert rules_by_id()["rates-big-rejections"]["runbook_id"] is None
    ok(client.post(f"/api/runbooks/{rb_id}/attach/rates-big-rejections"))
    ok(client.delete(f"/api/runbooks/{rb_id}"))
    assert rules_by_id()["rates-big-rejections"]["runbook_id"] is None
    ok(client.get(f"/api/runbooks/{rb_id}"), 404)
    assert engine(TRADE)["matched"][0]["steps"] == []


def test_attach_replaces_previous_runbook():
    before = rules_by_id()["pricing-warnings"]["runbook_id"]
    rb = ok(client.post("/api/runbooks", json={"name": "replacement", "raw": "1. New step"}))
    ok(client.post(f"/api/runbooks/{rb['id']}/attach/pricing-warnings"))
    assert rules_by_id()["pricing-warnings"]["runbook_id"] == rb["id"]
    assert ok(client.get(f"/api/runbooks/{before}"))["name"] == "pricing-warnings"   # stary nie usunięty
    ok(client.post(f"/api/runbooks/{before}/attach/pricing-warnings"))              # przywróć
    ok(client.delete(f"/api/runbooks/{rb['id']}"))


def test_runbook_errors():
    ok(client.post("/api/runbooks", json={"name": "   ", "raw": "1. A"}), 422)        # pusta nazwa
    ok(client.post("/api/runbooks", json={"raw": "1. A"}), 422)                        # brak nazwy
    ok(client.post("/api/runbooks", json={"name": "x", "raw": "a\nsteps:\n- b", "format": "yaml"}), 422)
    ok(client.put("/api/runbooks/99999", json={"name": "x"}), 404)
    ok(client.put("/api/runbooks/1", json={"name": ""}), 422)
    ok(client.delete("/api/runbooks/99999"), 404)
    ok(client.post("/api/runbooks/99999/attach/settlements-prod"), 404)
    ok(client.post("/api/runbooks/1/attach/no-such-rule"), 404)
    ok(client.delete("/api/runbooks/1/attach/rates-big-rejections"), 404)             # nie był podpięty


def test_parse_preview_returns_warnings_name_and_matches():
    r = ok(client.post("/api/runbooks/parse", json={"raw": "1. A\n2. B\nzrob cos znowu"}))
    assert [s["text"] for s in r["steps"]] == ["A", "B"] and "zrob cos znowu" in r["warnings"][0]
    r = ok(client.post("/api/runbooks/parse", json={"raw": "runbook: x\nmatches:\n  type: T\nsteps:\n  - A"}))
    assert r["name"] == "x" and r["matches"] == {"and": [{"field": "type", "op": "eq", "value": "T"}]}


def test_appendix_b_yaml_runbook_attaches_itself_by_matches():
    yaml_rb = ("runbook: settlement-timeout-b\nmatches:\n  type: WORKFLOW_FAILED\n  \"error.code\": CIRCUIT_OPEN\n"
               "steps:\n  - action: retry_workflow\n    workflowId: \"{{workflowId}}\"\n")
    rb = ok(client.post("/api/runbooks", json={"name": "settlement-timeout-b", "raw": yaml_rb}))
    assert rb["matches"]["and"][1] == {"field": "error.code", "op": "eq", "value": "CIRCUIT_OPEN"}

    seed_rb = rules_by_id()["settlements-prod"]["runbook_id"]
    ok(client.delete(f"/api/runbooks/{seed_rb}/attach/settlements-prod"))   # reguła bez własnego runbooka
    try:
        # seed runbook's own `matches` auto-attaches for TIMEOUT
        [m_seed] = engine(SETTLEMENT)["matched"]
        assert len(m_seed["steps"]) == 3
        # newly created YAML runbook auto-attaches for CIRCUIT_OPEN
        circuit = {**SETTLEMENT, "error": {"code": "CIRCUIT_OPEN", "message": "x"}}
        [m] = engine(circuit)["matched"]
        assert [s["text"] for s in m["steps"]] == ["Retry workflow (workflowId: WF-1)"]
        other = {**SETTLEMENT, "error": {"code": "DB_DOWN", "message": "x"}}
        assert engine(other)["matched"][0]["steps"] == []                     # matches nie pasuje
    finally:
        ok(client.post(f"/api/runbooks/{seed_rb}/attach/settlements-prod"))
        ok(client.delete(f"/api/runbooks/{rb['id']}"))


# ---------------------------------------------------------------- test silnika

def test_engine_test_each_sample_hits_its_rule():
    for event, rule_id in ((SETTLEMENT, "settlements-prod"), (TRADE, "rates-big-rejections"),
                           (PRICING, "pricing-warnings"), (PAYMENTS, "anna-payments-critical")):
        r = engine(event)
        assert [m["rule_id"] for m in r["matched"]] == [rule_id], (rule_id, r)
        assert len(r["checked"]) == 4 and rule_id not in r["not_matched"]


def test_engine_test_settlement_details():
    [m] = engine(SETTLEMENT)["matched"]
    assert m["title"] == "Workflow order-settlement failed at step book-cash" and m["body"] == "Timed out"
    assert m["severity"] == "critical" and m["channels"] == ["phone", "sms", "ui"]
    assert m["steps"][0]["action"] == "http_get"
    assert m["steps"][1]["text"] == "Retry workflow (workflowId: WF-1)"
    assert m["steps"][1]["params"] == {"workflowId": "WF-1"}
    assert m["steps"][2]["action"] == "escalate"
    assert m["steps"][2]["approval"] == "required"


def test_engine_test_no_match_and_odd_events():
    assert engine({**SETTLEMENT, "environment": "uat"})["matched"] == []
    for event in ([1, 2], "text", 42, None, {}):
        assert engine(event)["matched"] == []
    ok(client.post("/api/engine/test", json={}), 422)                                 # brak "event"


def test_engine_test_rule_filter_and_draft_rule():
    r = engine(SETTLEMENT, rule_ids=["rates-big-rejections"])
    assert r["checked"] == ["rates-big-rejections"] and r["matched"] == []
    runbooks = {rb["name"]: rb for rb in ok(client.get("/api/runbooks"))}
    draft = {"name": "Draft", "team": "QA", "title": "Got {{type}}",
             "runbook_id": runbooks["settlement-timeout"]["id"],
             "condition": {"or": [{"field": "type", "op": "eq", "value": "WORKFLOW_FAILED"}]}, "unknown": 1}
    [m] = engine(SETTLEMENT, rule=draft)["matched"]
    assert m["rule_id"] == "draft" and m["title"] == "Got WORKFLOW_FAILED"
    assert len(m["steps"]) == 3 and m["steps"][1]["params"]["workflowId"] == "WF-1"


def test_disabled_rule_is_skipped_by_engine():
    from database import SessionLocal
    from models import Rule
    db = SessionLocal()
    try:
        db.get(Rule, "settlements-prod").enabled = False
        db.commit()
        assert engine(SETTLEMENT)["matched"] == []
        db.get(Rule, "settlements-prod").enabled = True
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------- pełna droga przez /api/ingest

def test_ingest_end_to_end_hands_matches_to_person_1():
    captured = []
    real = pipeline.upsert_alert
    pipeline.upsert_alert = lambda db, match: captured.append(match)  # udajemy Osobę 1
    try:
        r = ok(client.post("/api/ingest/trade-gateway", json=[TRADE, TRADE, {"noise": True}]))
        assert r["accepted"] == 3
        ok(client.post("/api/ingest/demo", json=SETTLEMENT))
    finally:
        pipeline.upsert_alert = real

    assert [m.rule_id for m in captured] == ["rates-big-rejections", "rates-big-rejections", "settlements-prod"]
    assert captured[0].dedup_key == captured[1].dedup_key          # ten sam problem -> ten sam alert
    assert captured[0].event_id != captured[1].event_id
    assert captured[2].steps[1]["text"] == "Retry workflow (workflowId: WF-1)"  # runbook z bazy
    assert captured[2].steps[2]["approval"] == "required"
    events = ok(client.get("/api/events?limit=10"))
    assert len(events) >= 4


def test_ingest_unknown_source_404():
    ok(client.post("/api/ingest/nope", json=TRADE), 404)


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
