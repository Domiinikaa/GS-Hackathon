"""
Dry-Run Rule Evaluation (Idea 3 — Unseen Schema Playground).

Evaluates arbitrary parsed payloads against all active rules in the database
WITHOUT persisting events or creating alerts, using `services.rules_engine`
as the single source of truth.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from models import Event, Rule
from services.rules_engine import _MISSING, check_condition, evaluate as team_evaluate, get_field


def _collect_leaf_checks(payload: Any, node: Any) -> list[dict[str, Any]]:
    """Collect per-condition evaluation previews from a rule's condition tree."""
    if not isinstance(node, dict):
        return []

    if "and" in node and isinstance(node["and"], list):
        collected: list[dict[str, Any]] = []
        for child in node["and"]:
            collected.extend(_collect_leaf_checks(payload, child))
        return collected

    if "or" in node and isinstance(node["or"], list):
        collected = []
        for child in node["or"]:
            collected.extend(_collect_leaf_checks(payload, child))
        return collected

    if "not" in node:
        return _collect_leaf_checks(payload, node["not"])

    if "field" in node:
        field = str(node.get("field") or "")
        op = str(node.get("op") or "eq")
        raw_actual = get_field(payload, field)
        actual = None if raw_actual is _MISSING else raw_actual
        return [{
            "field": field,
            "op": op,
            "expected": node.get("value"),
            "actual": actual,
            "passed": check_condition(payload, node),
        }]

    return []


def dry_run_against_rules(db: Session, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Evaluate the first parsed record against active rules without persisting state.
    Returns matched rule previews with rendered title/body, condition details, and runbook steps.
    """
    if not parsed_records:
        return []

    rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()
    if not rules:
        return []

    sample_record = parsed_records[0]
    fake_event = Event(id=0, source_id=None, payload=sample_record)
    team_matches = team_evaluate(fake_event, rules, db=db)

    rules_by_id = {r.id: r for r in rules}
    matched_previews: list[dict[str, Any]] = []
    for m in team_matches:
        r = rules_by_id.get(m.rule_id)
        cond_results = _collect_leaf_checks(sample_record, r.condition) if r else []
        matched_previews.append({
            "rule_id": m.rule_id,
            "rule_name": r.name if r else m.rule_id,
            "team": m.team,
            "severity": m.severity,
            "color": m.color,
            "channels": m.channels,
            "rendered_title": m.title,
            "rendered_body": m.body or "",
            "conditions": cond_results,
            "steps": m.steps,
        })

    return matched_previews
