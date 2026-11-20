"""
Testy Osoby 4: silnik reguł + parser runbooków. Bez serwera i bez bazy.

    python tests/test_engine.py        (albo: pytest tests/)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Event, Rule  # noqa: E402
from services.rules_engine import check_group, evaluate, get_field, render_template, _MISSING  # noqa: E402
from services.runbook_parser import detect_format, fill_steps, parse_runbook  # noqa: E402

# te same reguły co seed.py
RULES = [
    Rule(id="settlements-prod", name="Settlement", team="Settlements", enabled=True,
         condition={"and": [{"field": "type", "op": "eq", "value": "WORKFLOW_FAILED"},
                            {"field": "workflowName", "op": "eq", "value": "order-settlement"},
                            {"field": "environment", "op": "eq", "value": "prod"}]},
         channels=["phone", "sms", "ui"], title="Workflow {{workflowName}} failed at step {{step}}",
         body="{{error.message}}", severity="critical", color="red"),
    Rule(id="pricing-warnings", name="Pricing", team="Pricing", enabled=True,
         condition={"and": [{"field": "service", "op": "wildcard", "value": "pricing-engine-*"},
                            {"field": "level", "op": "in", "value": ["WARN", "ERROR", "FATAL"]}]},
         channels=["ui"], title="Pricing warnings for {{instrument}}", severity="warning", color="amber",
         group_by="instrument", group_window_s=300),
    Rule(id="rates-big-rejections", name="Rates", team="Rates", enabled=True,
         condition={"and": [{"field": "meta.schema", "op": "wildcard", "value": "trade.rejected.*"},
                            {"field": "payload.desk", "op": "eq", "value": "rates"},
                            {"field": "payload.notional", "op": "gt", "value": 10000000}]},
         channels=["email", "ui"], title="Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}",
         severity="warning", color="amber"),
    Rule(id="anna-payments-critical", name="Payments", team="Payments", enabled=True,
         condition={"and": [{"field": "labels.service", "op": "eq", "value": "payments-api"},
                            {"field": "labels.severity", "op": "eq", "value": "critical"}]},
         channels=["sms"], title="{{alertname}} on {{labels.service}}", body="{{annotations.summary}}",
         severity="critical", color="red"),
]

T0 = datetime(2026, 11, 20, 12, 0, 0)


def ev(payload, at=T0, id=1):
    return Event(id=id, payload=payload, received_at=at)


def matched_ids(payload, at=T0):
    return [m.rule_id for m in evaluate(ev(payload, at), RULES)]


# ---------------------------------------------------------------- silnik

def test_trade_rejection_matches_and_renders():
    e = {"meta": {"schema": "trade.rejected.v2", "producer": "trade-gateway"},
         "payload": {"tradeId": "T-998877", "desk": "rates", "notional": 25000000, "currency": "EUR",
                     "reason": "LIMIT_BREACH"}}
    [m] = evaluate(ev(e), RULES)
    assert m.rule_id == "rates-big-rejections"
    assert m.title == "Rejected EUR 25000000 — LIMIT_BREACH"
    assert m.dedup_key == "rates-big-rejections"
    assert m.channels == ["email", "ui"] and m.team == "Rates" and m.event_id == 1


def test_small_trade_and_other_desk_do_not_match():
    base = {"meta": {"schema": "trade.rejected.v2"}, "payload": {"desk": "rates", "notional": 5_000_000}}
    assert matched_ids(base) == []
    base["payload"] = {"desk": "fx", "notional": 50_000_000}
    assert matched_ids(base) == []


def test_settlement_workflow():
    e = {"type": "WORKFLOW_FAILED", "workflowName": "order-settlement", "environment": "prod",
         "workflowId": "WF-123", "step": "book-cash", "error": {"code": "TIMEOUT", "message": "Timed out after 30s"}}
    [m] = evaluate(ev(e), RULES)
    assert m.title == "Workflow order-settlement failed at step book-cash"
    assert m.body == "Timed out after 30s" and m.severity == "critical"
    e["environment"] = "uat"
    assert matched_ids(e) == []


def test_pricing_grouping_per_instrument_and_window():
    def key(instrument, at):
        e = {"service": "pricing-engine-eu", "level": "WARN", "instrument": instrument}
        return evaluate(ev(e, at), RULES)[0].dedup_key

    k1 = key("EURUSD", T0)
    assert k1.startswith("pricing-warnings|EURUSD|w")
    assert key("EURUSD", T0.replace(minute=2)) == k1          # to samo okno 5 min -> ten sam alert
    assert key("GBPUSD", T0) != k1                            # inny instrument -> inny alert
    assert key("EURUSD", T0.replace(minute=7)) != k1          # nowe okno -> nowy alert


def test_pricing_level_filter_and_wildcard():
    assert matched_ids({"service": "pricing-engine-us", "level": "INFO", "instrument": "X"}) == []
    assert matched_ids({"service": "risk-engine", "level": "ERROR", "instrument": "X"}) == []


def test_alertmanager_payload():
    e = {"alertname": "HighErrorRate", "labels": {"service": "payments-api", "severity": "critical"},
         "annotations": {"summary": "5xx > 5%"}}
    [m] = evaluate(ev(e), RULES)
    assert m.title == "HighErrorRate on payments-api" and m.body == "5xx > 5%"


def test_disabled_rule_is_skipped():
    r = Rule(id="x", name="x", team="t", enabled=False, condition={"and": []}, title="t")
    assert evaluate(ev({}), [r]) == []


def test_operators():
    d = {"a": 5, "s": "Hello World", "tags": ["x", "y"], "n": "1500", "b": True, "items": [{"id": 7}]}
    ok = lambda op, field, value: check_group(d, {"and": [{"field": field, "op": op, "value": value}]})  # noqa
    assert ok("eq", "a", "5") and ok("eq", "b", "true") and ok("eq", "items.0.id", 7)
    assert ok("neq", "a", 6) and ok("neq", "missing", 1)
    assert ok("gt", "n", 1000) and ok("gte", "a", 5) and ok("lt", "a", "10") and ok("lte", "a", 5)
    assert not ok("gt", "s", 1)                                # tekst nie jest liczbą
    assert ok("in", "a", "1, 5, 9") and not ok("in", "a", [1, 2])
    assert ok("contains", "s", "world") and ok("contains", "tags", "y")
    assert ok("wildcard", "s", "Hello*") and not ok("wildcard", "s", "hello*")
    assert not ok("eq", "missing", None)


def test_or_and_nested_groups():
    d = {"level": "ERROR", "env": "prod"}
    assert check_group(d, {"or": [{"field": "level", "op": "eq", "value": "WARN"},
                                  {"field": "level", "op": "eq", "value": "ERROR"}]})
    assert check_group(d, {"and": [{"field": "env", "op": "eq", "value": "prod"},
                                   {"or": [{"field": "level", "op": "eq", "value": "FATAL"},
                                           {"field": "level", "op": "eq", "value": "ERROR"}]}]})
    assert check_group(d, {"and": []}) and check_group(d, None)


def test_templates_and_fields():
    d = {"meta.schema": "literal-dot-key", "x": {"y": 1.0}}
    assert get_field(d, "meta.schema") == "literal-dot-key"
    assert get_field(d, "x.z") is _MISSING
    assert render_template("v={{x.y}} m={{ nope }}", d) == "v=1 m={{ nope }}"


def test_broken_rule_does_not_crash():
    r = Rule(id="bad", name="bad", team="t", enabled=True, condition={"and": "not-a-list"}, title="t")
    assert evaluate(ev({"a": 1}), [r] + RULES[:1]) == []


# ---------------------------------------------------------------- runbooki (zwykła lista kroków)

YAML = """
runbook:
  name: settlement-timeout
  steps:
    - Check settlement service health
    - text: Retry workflow {{workflowId}} from step {{step}}
    - name: Call the on-call
"""

MARKDOWN = """# Pricing
1. Check the pricing dashboard for {{instrument}}
2. **Restart** pricing-engine if warnings persist
- [ ] Tell the Pricing lead
"""


def texts(steps):
    return [s["text"] for s in steps]


def test_steps_are_plain_info():
    for steps in (parse_runbook(YAML, "yaml"), parse_runbook(MARKDOWN, "markdown")):
        assert all(s["action"] is None and s["approval"] == "none" and s["params"] == {} for s in steps)


def test_yaml_runbook():
    assert texts(parse_runbook(YAML, "yaml")) == [
        "Check settlement service health", "Retry workflow {{workflowId}} from step {{step}}", "Call the on-call"]
    assert detect_format(YAML) == "yaml"


def test_markdown_runbook():
    assert texts(parse_runbook(MARKDOWN, "markdown")) == [
        "Check the pricing dashboard for {{instrument}}", "Restart pricing-engine if warnings persist",
        "Tell the Pricing lead"]
    assert detect_format(MARKDOWN) == "markdown"


def test_free_text_runbook():
    steps = parse_runbook("Check logs in Kibana. Then retry the workflow; open a JIRA ticket", "auto")
    assert texts(steps) == ["Check logs in Kibana", "Retry the workflow", "Open a JIRA ticket"]
    assert texts(parse_runbook("https://wiki.example.com/rb/1", "auto")) == ["Open runbook https://wiki.example.com/rb/1"]


def test_bad_yaml_raises():
    try:
        parse_runbook("steps: [unclosed", "yaml")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_fill_steps():
    steps = parse_runbook(YAML, "yaml")
    filled = fill_steps(steps, {"workflowId": "WF-1", "step": "book-cash"})
    assert filled[1]["text"] == "Retry workflow WF-1 from step book-cash" and filled[1]["done"] is False
    assert steps[1]["text"].startswith("Retry workflow {{")  # oryginał nietknięty


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
