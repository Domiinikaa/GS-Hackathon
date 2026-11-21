#!/usr/bin/env python3
"""
CLI & library helpers for seeding sample (mock) data on demand.

Usage:
    python seed.py
    python seed.py --with-people
    python seed.py --only teams sources
"""
from __future__ import annotations

import argparse
import sys
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()

from models import Person, Rule, Runbook, Source, Team  # noqa: E402

SEED_CHOICES = ("teams", "sources", "rules", "runbooks", "people")

DEFAULT_TEAMS = [
    ("Settlements", "Order settlement workflows and counterparty operations"),
    ("Pricing", "Pricing engine services and market data latency"),
    ("Rates", "Rates trading desk and trade gateway monitoring"),
    ("Payments", "Payments API reliability and regional failover"),
    ("Management", "Executive leadership and platform administration"),
]


def seed_teams(db: Session) -> int:
    existing = {name.lower() for (name,) in db.query(Team.name).all() if name}
    added = 0
    for name, description in DEFAULT_TEAMS:
        if name.lower() in existing:
            continue
        db.add(Team(name=name, description=description))
        existing.add(name.lower())
        added += 1
    return added


def _mock_sources() -> list[Source]:
    return [
        Source(
            key="demo",
            name="demo-webhook",
            team="All",
            kind="webhook",
            enabled=True,
            status="active",
            config={"auth_mode": "none", "parser": "auto", "sim_preset": "workflow_failure"},
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
            key="payments-webhook",
            name="payments-webhook",
            team="Payments",
            kind="webhook",
            enabled=True,
            status="active",
            config={"auth_mode": "none", "parser": "auto", "sim_preset": "metric_breach"},
            sample_event={
                "alertname": "HighErrorRate",
                "labels": {"service": "payments-api", "region": "eu-west", "severity": "critical"},
                "annotations": {"summary": "Error rate 12% over the last 5 minutes"},
                "startsAt": "2026-11-21T00:13:00Z",
                "status": "firing",
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
    ]


def seed_sources(db: Session) -> int:  # Osoba 3
    existing_keys = {key for (key,) in db.query(Source.key).all()}
    added = 0
    for src in _mock_sources():
        if src.key in existing_keys:
            continue
        db.add(src)
        existing_keys.add(src.key)
        added += 1
    return added


def _mock_rules() -> list[Rule]:
    return [
        Rule(
            id="settlements-prod",
            name="Settlement workflow failed in prod",
            team="Settlements",
            condition={
                "and": [
                    {"field": "type", "op": "eq", "value": "WORKFLOW_FAILED"},
                    {"field": "workflowName", "op": "eq", "value": "order-settlement"},
                    {"field": "environment", "op": "eq", "value": "prod"},
                ]
            },
            channels=["phone", "sms", "ui"],
            title="Workflow {{workflowName}} failed at step {{step}}",
            body="{{error.message}}",
            severity="critical",
            color="red",
        ),
        Rule(
            id="pricing-warnings",
            name="Pricing engine warnings",
            team="Pricing",
            condition={
                "and": [
                    {"field": "service", "op": "wildcard", "value": "pricing-engine-*"},
                    {"field": "level", "op": "in", "value": ["WARN", "ERROR", "FATAL"]},
                ]
            },
            channels=["ui"],
            title="Pricing warnings for {{instrument}}",
            severity="warning",
            color="amber",
        ),
        Rule(
            id="rates-big-rejections",
            name="Large rejected trades (rates desk)",
            team="Rates",
            condition={
                "and": [
                    {"field": "meta.schema", "op": "wildcard", "value": "trade.rejected.*"},
                    {"field": "payload.desk", "op": "eq", "value": "rates"},
                    {"field": "payload.notional", "op": "gt", "value": 10000000},
                ]
            },
            channels=["email", "ui"],
            title="Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}",
            severity="warning",
            color="amber",
        ),
        Rule(
            id="anna-payments-critical",
            name="Critical payments-api alerts",
            team="Anna",
            condition={
                "and": [
                    {"field": "labels.service", "op": "eq", "value": "payments-api"},
                    {"field": "labels.severity", "op": "eq", "value": "critical"},
                ]
            },
            channels=["sms"],
            title="{{alertname}} on {{labels.service}}",
            body="{{annotations.summary}}",
            severity="critical",
            color="red",
        ),
    ]


def seed_rules(db: Session) -> int:  # Osoba 2 – 4 reguły z Appendix A
    existing_ids = {rid for (rid,) in db.query(Rule.id).all()}
    added = 0
    for rule in _mock_rules():
        if rule.id in existing_ids:
            continue
        db.add(rule)
        existing_ids.add(rule.id)
        added += 1
    return added


MOCK_MEMBERS = [
    dict(
        name="Anna",
        team="Payments",
        email="anna@example.com",
        phone="+48 600 000 001",
        channel_prefs={"critical": ["sms"], "warning": ["email"], "info": ["ui"]},
        quiet_hours={"sms": {"from": "08:00", "to": "20:00", "else": "email"}},
    ),
    dict(
        name="Tom",
        team="Settlements",
        email="tom@example.com",
        phone="+48 600 000 002",
        on_call=True,
        channel_prefs={"critical": ["phone", "sms"], "warning": ["email"], "info": ["ui"]},
    ),
    dict(
        name="Kasia",
        team="Rates",
        email="kasia@example.com",
        channel_prefs={"critical": ["email"], "warning": ["email"], "info": ["ui"]},
    ),
]

TEAM_LEADS = [  # one lead per team that has example rules; leads approve risky runbook steps
    dict(name="Ewa", team="Settlements", email="ewa@example.com", phone="+48 600 000 012"),
    dict(name="Marek", team="Pricing", email="marek@example.com", phone="+48 600 000 011"),
    dict(name="Piotr", team="Rates", email="piotr@example.com", phone="+48 600 000 013"),
    dict(name="Zofia", team="Payments", email="zofia@example.com", phone="+48 600 000 014"),
]


def _seed_members(db: Session) -> int:
    members = [Person(**member) for member in MOCK_MEMBERS]
    db.add_all(members)
    return len(members)


def seed_team_leads(db: Session) -> int:  # Osoba 2 – runs once, also on databases created before roles existed
    if db.query(Person).filter(Person.role == "lead").count() > 0:
        return 0
    leads = [
        Person(role="lead", channel_prefs={"critical": ["sms"], "warning": ["email"], "info": ["ui"]}, **lead)
        for lead in TEAM_LEADS
    ]
    db.add_all(leads)
    return len(leads)


def seed_people(db: Session, *, merge: bool = False) -> int:  # Osoba 2
    if not merge:
        added = 0
        if db.query(Person).count() == 0:
            added += _seed_members(db)
        added += seed_team_leads(db)
        return added

    existing_emails = {
        email.strip().lower()
        for (email,) in db.query(Person.email).all()
        if email
    }
    added = 0
    for member in MOCK_MEMBERS:
        email_key = member["email"].strip().lower()
        if email_key in existing_emails:
            continue
        db.add(Person(**member))
        existing_emails.add(email_key)
        added += 1
    for lead in TEAM_LEADS:
        email_key = lead["email"].strip().lower()
        if email_key in existing_emails:
            continue
        db.add(
            Person(
                role="lead",
                channel_prefs={"critical": ["sms"], "warning": ["email"], "info": ["ui"]},
                **lead,
            )
        )
        existing_emails.add(email_key)
        added += 1
    return added


SETTLEMENT_RUNBOOK = """\
runbook: settlement-timeout
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

PAYMENTS_RUNBOOK = """\
# HighErrorRate on payments-api
1. Open the payments dashboard and check if errors are in one region only.
2. If one region: fail traffic over to the other region (needs approval from the team lead).
3. If all regions: check the last deployment and roll it back.
4. Post an update in the #payments-incidents channel every 15 minutes.
"""

PRICING_RUNBOOK = (
    "When pricing latency goes over a second, it's usually the cache. Restart the pricing-engine "
    "instance named in the alert, wait 2 minutes, and if latency is still high, call the pricing "
    "on-call person."
)


def seed_runbooks(db: Session) -> int:  # Osoba 4
    from services.runbook_parser import parse_runbook_full

    by_name = {rb.name: rb for rb in db.query(Runbook).all()}
    specs = (
        ("settlement-timeout", SETTLEMENT_RUNBOOK, "yaml"),
        ("payments-high-error-rate", PAYMENTS_RUNBOOK, "markdown"),
        ("pricing-warnings", PRICING_RUNBOOK, "text"),
    )
    added = 0
    for name, raw, fmt in specs:
        if name in by_name:
            continue
        res = parse_runbook_full(raw, fmt)
        rb = Runbook(
            name=name,
            format=res.format,
            raw=raw,
            steps=res.steps,
            matches=res.matches,
        )
        db.add(rb)
        by_name[name] = rb
        added += 1

    db.flush()  # nadaje id
    for rule_id, rb_name in (
        ("settlements-prod", "settlement-timeout"),
        ("anna-payments-critical", "payments-high-error-rate"),
        ("pricing-warnings", "pricing-warnings"),
    ):
        rule = db.get(Rule, rule_id)
        rb = by_name.get(rb_name)
        if rule is not None and rb is not None and rule.runbook_id is None:
            rule.runbook_id = rb.id
    return added


def seed_all(db: Session, *, include_people: bool = False) -> dict[str, int]:
    counts = {
        "teams": seed_teams(db),
        "sources": seed_sources(db),
        "rules": seed_rules(db),
        "people": seed_people(db, merge=True) if include_people else 0,
    }
    db.flush()
    counts["runbooks"] = seed_runbooks(db)
    db.commit()
    return {
        "teams": counts["teams"],
        "sources": counts["sources"],
        "rules": counts["rules"],
        "runbooks": counts["runbooks"],
        "people": counts["people"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed sample (mock) teams, sources, rules, runbooks, and optionally people into the database."
    )
    parser.add_argument(
        "--with-people",
        action="store_true",
        help="Also seed sample people (3 members + 4 team leads).",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=SEED_CHOICES,
        help="Seed only selected mock datasets.",
    )
    args = parser.parse_args(argv)

    if args.only:
        selected = list(dict.fromkeys(args.only))
        if args.with_people and "people" not in selected:
            selected.append("people")
    else:
        selected = ["teams", "sources", "rules", "runbooks"]
        if args.with_people:
            selected.append("people")

    from database import Base, SessionLocal, engine, startup_lock
    from services.alert_service import ensure_open_dedup_index
    from services.connectors.ingest_manager import ensure_sources_columns
    from services.delivery import ensure_delivery_columns
    from services.people_service import ensure_people_role_column

    with startup_lock():
        Base.metadata.create_all(bind=engine)
        ensure_sources_columns(engine)
        ensure_delivery_columns(engine)
        ensure_open_dedup_index(engine)
        ensure_people_role_column(engine)

        db = SessionLocal()
        try:
            added: dict[str, int] = {}
            if "teams" in selected:
                added["teams"] = seed_teams(db)
            if "sources" in selected:
                added["sources"] = seed_sources(db)
            if "rules" in selected:
                added["rules"] = seed_rules(db)
            if "people" in selected:
                added["people"] = seed_people(db, merge=True)
            db.flush()
            if "runbooks" in selected:
                added["runbooks"] = seed_runbooks(db)
            db.commit()

            model_map = {
                "teams": Team,
                "sources": Source,
                "rules": Rule,
                "runbooks": Runbook,
                "people": Person,
            }
            totals = {name: db.query(model_map[name]).count() for name in selected}
        finally:
            db.close()

    print("[SEED] Mock data summary:")
    for name in selected:
        print(f"  - {name}: +{added[name]} added ({totals[name]} total)")
    if sum(added.values()) == 0:
        print("[SEED] All selected mock records already exist; nothing changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
