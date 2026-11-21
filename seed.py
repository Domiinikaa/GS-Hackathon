"""
Dane startowe, żeby każdy mógł testować swój kawałek od razu (bez czekania na UI innych).
Wrzucane tylko do pustych tabel. Każdy dopisuje swoje w swojej funkcji.
"""
from sqlalchemy.orm import Session

from models import Person, Rule, Runbook, Source


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
        Rule(id="settlements-prod", name="Settlement workflow failed in prod", team="Business",
             condition={"and": [{"field": "type", "op": "eq", "value": "WORKFLOW_FAILED"},
                                {"field": "workflowName", "op": "eq", "value": "order-settlement"},
                                {"field": "environment", "op": "eq", "value": "prod"}]},
             channels=["phone", "sms", "ui"], title="Workflow {{workflowName}} failed at step {{step}}",
             body="{{error.message}}", severity="critical", color="red"),
        Rule(id="pricing-warnings", name="Pricing engine warnings", team="IT",
             condition={"and": [{"field": "service", "op": "wildcard", "value": "pricing-engine-*"},
                                {"field": "level", "op": "in", "value": ["WARN", "ERROR", "FATAL"]}]},
             channels=["ui"], title="Pricing warnings for {{instrument}}", severity="warning", color="amber",
             group_by="instrument", group_window_s=300),
        Rule(id="rates-big-rejections", name="Large rejected trades (rates desk)", team="Finance",
             condition={"and": [{"field": "meta.schema", "op": "wildcard", "value": "trade.rejected.*"},
                                {"field": "payload.desk", "op": "eq", "value": "rates"},
                                {"field": "payload.notional", "op": "gt", "value": 10000000}]},
             channels=["email", "ui"],
             title="Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}",
             severity="warning", color="amber"),
        Rule(id="anna-payments-critical", name="Critical payments-api alerts", team="Anna",
             condition={"and": [{"field": "labels.service", "op": "eq", "value": "payments-api"},
                                {"field": "labels.severity", "op": "eq", "value": "critical"}]},
             channels=["sms"], title="{{alertname}} on {{labels.service}}", body="{{annotations.summary}}",
             severity="critical", color="red"),
    ])


def seed_people(db: Session) -> None:  # Osoba 2
    if db.query(Person).count() > 0:
        return
    db.add_all([
        Person(name="Anna", team="IT", email="anna@example.com", phone="+48 600 000 001",
               channel_prefs={"critical": ["sms"], "warning": ["email"], "info": ["ui"]},
               quiet_hours={"sms": {"from": "08:00", "to": "20:00", "else": "email"}}),
        Person(name="Tom", team="Business", email="tom@example.com", phone="+48 600 000 002", on_call=True,
               channel_prefs={"critical": ["phone", "sms"], "warning": ["email"], "info": ["ui"]}),
        Person(name="Kasia", team="Finance", email="kasia@example.com",
               channel_prefs={"critical": ["email"], "warning": ["email"], "info": ["ui"]}),
    ])


SETTLEMENT_RUNBOOK = """\
# Settlement workflow failed
1. Check settlement service health at https://settlement.internal/health
2. Retry workflow {{workflowId}} from step {{step}}
3. If the retry fails, call the Settlements on-call
4. Open a JIRA ticket with error {{error.code}}
"""

PRICING_RUNBOOK = """\
# Pricing engine warnings
1. Check the pricing dashboard for {{instrument}}
2. Restart {{service}} if warnings keep coming for more than 5 minutes
3. Tell the Pricing lead
"""


def seed_runbooks(db: Session) -> None:  # Osoba 4
    if db.query(Runbook).count() > 0:
        return
    from services.runbook_parser import parse_runbook
    settlement = Runbook(name="settlement-timeout", format="markdown", raw=SETTLEMENT_RUNBOOK,
                         steps=parse_runbook(SETTLEMENT_RUNBOOK, "markdown"))
    pricing = Runbook(name="pricing-warnings", format="markdown", raw=PRICING_RUNBOOK,
                      steps=parse_runbook(PRICING_RUNBOOK, "markdown"))
    db.add_all([settlement, pricing])
    db.flush()  # nadaje id
    for rule_id, rb in (("settlements-prod", settlement), ("pricing-warnings", pricing)):
        rule = db.get(Rule, rule_id)
        if rule is not None and rule.runbook_id is None:
            rule.runbook_id = rb.id


def seed_all(db: Session) -> None:
    seed_sources(db)
    seed_rules(db)
    seed_people(db)
    db.flush()
    seed_runbooks(db)
    db.commit()
