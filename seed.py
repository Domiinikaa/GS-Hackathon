"""
Dane startowe, żeby każdy mógł testować swój kawałek od razu (bez czekania na UI innych).
Wrzucane tylko do pustych tabel. Każdy dopisuje swoje w swojej funkcji.
"""
from sqlalchemy.orm import Session

from models import Person, Rule, Source


def seed_sources(db: Session) -> None:  # Osoba 3
    if db.query(Source).count() == 0:
        db.add_all([
            Source(key="demo", name="demo-webhook", team="All", kind="webhook"),
            Source(key="trade-gateway", name="trade-gateway", team="Rates", kind="webhook"),
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
