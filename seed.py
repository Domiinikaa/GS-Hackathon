"""
Dane startowe, żeby każdy mógł testować swój kawałek od razu (bez czekania na UI innych).
Wrzucane tylko do pustych tabel. Każdy dopisuje swoje w swojej funkcji.
"""
from sqlalchemy.orm import Session

from models import Person, Rule, Source


def seed_sources(db: Session) -> None:  # Osoba 3
    if db.query(Source).count() == 0:
        db.add_all([
            Source(
                key="trade-gateway",
                name="trade-gateway",
                team="Rates",
                kind="webhook",
                enabled=True,
                status="active",
                config={"auth_mode": "none", "parser": "auto", "sim_preset": "trade_rejected"},
                sample_event={
                    "meta": {"schema": "trade.rejected.v2", "producer": "trade-gateway", "ts": 1792833245000},
                    "payload": {"tradeId": "T-998877", "desk": "rates", "notional": 25000000, "currency": "EUR", "reason": "LIMIT_BREACH"},
                },
            ),
            Source(
                key="settlement-kafka",
                name="settlement-kafka",
                team="Settlements",
                kind="kafka",
                enabled=False,
                status="paused",
                config={
                    "bootstrap_servers": "localhost:9092",
                    "topic": "settlement.workflows",
                    "group_id": "gs-alerting-consumer",
                    "simulate": True,
                    "sim_preset": "workflow_failure",
                    "sim_interval_s": 10,
                    "parser": "auto",
                },
                sample_event={
                    "type": "WORKFLOW_FAILED",
                    "workflowId": "WF-20261121-00042",
                    "workflowName": "order-settlement",
                    "step": "validate-counterparty",
                    "severity": "ERROR",
                    "environment": "prod",
                    "error": {"code": "TIMEOUT", "message": "Counterparty service did not respond in 5000 ms"},
                },
            ),
            Source(
                key="pricing-engine-logs",
                name="pricing-engine-logs",
                team="Pricing",
                kind="logfile",
                enabled=False,
                status="paused",
                config={
                    "file_path": "/tmp/gs-pricing-engine.log",
                    "from_beginning": False,
                    "poll_interval_s": 2,
                    "simulate": True,
                    "sim_preset": "pricing_log",
                    "sim_interval_s": 10,
                    "parser": "key_value",
                },
                sample_event={
                    "timestamp": "2026-11-21T00:15:00Z",
                    "level": "WARN",
                    "service": "pricing-engine-eu1",
                    "instrument": "EURUSD",
                    "latency_ms": 1420,
                    "message": "Cache latency exceeded 1000ms threshold",
                },
            ),
        ])


def seed_rules(db: Session) -> None:  # Osoba 2 – te same 4 reguły co frontend/src/rules/mockRules.ts
    if db.query(Rule).count() > 0:
        return
    db.add_all([
        Rule(id="settlements-prod", name="Settlement workflow failed in prod", team="Settlements",
             condition={"and": [{"field": "type", "op": "eq", "value": "WORKFLOW_FAILED"},
                                {"field": "workflowName", "op": "eq", "value": "order-settlement"},
                                {"field": "environment", "op": "eq", "value": "prod"}]},
             channels=["phone", "sms", "ui"], title="Workflow {{workflowName}} failed at step {{step}}",
             body="{{error.message}}", severity="critical", color="red"),
        Rule(id="pricing-warnings", name="Pricing engine warnings", team="Pricing",
             condition={"and": [{"field": "service", "op": "wildcard", "value": "pricing-engine-*"},
                                {"field": "level", "op": "in", "value": ["WARN", "ERROR", "FATAL"]}]},
             channels=["ui"], title="Pricing warnings for {{instrument}}", severity="warning", color="amber",
             group_by="instrument", group_window_s=300),
        Rule(id="rates-big-rejections", name="Large rejected trades (rates desk)", team="Rates",
             condition={"and": [{"field": "meta.schema", "op": "wildcard", "value": "trade.rejected.*"},
                                {"field": "payload.desk", "op": "eq", "value": "rates"},
                                {"field": "payload.notional", "op": "gt", "value": 10000000}]},
             channels=["email", "ui"],
             title="Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}",
             severity="warning", color="amber"),
        Rule(id="anna-payments-critical", name="Critical payments-api alerts", team="Payments",
             condition={"and": [{"field": "labels.service", "op": "eq", "value": "payments-api"},
                                {"field": "labels.severity", "op": "eq", "value": "critical"}]},
             channels=["sms"], title="{{alertname}} on {{labels.service}}", body="{{annotations.summary}}",
             severity="critical", color="red"),
    ])


def seed_people(db: Session) -> None:  # Osoba 2
    if db.query(Person).count() > 0:
        return
    db.add_all([
        Person(name="Anna", team="Payments", email="anna@example.com", phone="+48 600 000 001",
               channel_prefs={"critical": ["sms"], "warning": ["email"], "info": ["ui"]},
               quiet_hours={"sms": {"from": "08:00", "to": "20:00", "else": "email"}}),
        Person(name="Tom", team="Settlements", email="tom@example.com", phone="+48 600 000 002", on_call=True,
               channel_prefs={"critical": ["phone", "sms"], "warning": ["email"], "info": ["ui"]}),
        Person(name="Kasia", team="Rates", email="kasia@example.com",
               channel_prefs={"critical": ["email"], "warning": ["email"], "info": ["ui"]}),
    ])


def seed_all(db: Session) -> None:
    seed_sources(db)
    seed_rules(db)
    seed_people(db)
    db.commit()
