"""
Dry-Run Rule Evaluation (Idea 3 — Unseen Schema Playground).

Evaluates arbitrary parsed payloads against all active rules in the database
WITHOUT persisting events or creating alerts. Uses `services.rules_engine.evaluate`
when implemented, and falls back to a built-in condition evaluator if the team's
rules_engine stub is not yet filled in.
"""
from __future__ import annotations

import fnmatch
import re
from typing import Any

from sqlalchemy.orm import Session

from models import Event, Rule
from services.connectors.parser import get_by_path
from services.rules_engine import evaluate as team_evaluate


_TEMPLATE_RE = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


def _render_template(template: str | None, payload: dict[str, Any]) -> str:
    if not template:
        return ""

    def _replace(match: re.Match[str]) -> str:
        path = match.group(1)
        val = get_by_path(payload, path)
        return str(val) if val is not None else f"{{{{{path}}}}}"

    return _TEMPLATE_RE.sub(_replace, template)


def _eval_single_condition(payload: dict[str, Any], cond: dict[str, Any]) -> dict[str, Any]:
    field = str(cond.get("field") or "")
    op = str(cond.get("op") or "eq")
    expected = cond.get("value")
    actual = get_by_path(payload, field)
    passed = False

    try:
        if actual is None:
            passed = False
        elif op == "eq":
            passed = str(actual) == str(expected) if not isinstance(actual, (int, float)) else actual == expected
        elif op == "neq":
            passed = str(actual) != str(expected) if not isinstance(actual, (int, float)) else actual != expected
        elif op == "gt":
            passed = float(actual) > float(expected)
        elif op == "gte":
            passed = float(actual) >= float(expected)
        elif op == "lt":
            passed = float(actual) < float(expected)
        elif op == "lte":
            passed = float(actual) <= float(expected)
        elif op == "in":
            if isinstance(expected, list):
                allowed = [str(x) for x in expected]
            else:
                allowed = [x.strip() for x in str(expected).split(",") if x.strip()]
            passed = str(actual) in allowed
        elif op == "contains":
            passed = str(expected).lower() in str(actual).lower()
        elif op == "wildcard":
            passed = fnmatch.fnmatch(str(actual), str(expected))
    except (ValueError, TypeError):
        passed = False

    return {
        "field": field,
        "op": op,
        "expected": expected,
        "actual": actual,
        "passed": passed,
    }


def _eval_condition_node(payload: dict[str, Any], node: Any) -> tuple[bool, list[dict[str, Any]]]:
    """
    Recursively evaluate a condition tree supporting arbitrarily nested
    'and', 'or', 'not' groups as well as leaf {'field', 'op', 'value'} nodes.
    """
    if not isinstance(node, dict):
        return False, []

    if "and" in node and isinstance(node["and"], list):
        children = node["and"]
        if not children:
            return False, []
        all_passed = True
        collected: list[dict[str, Any]] = []
        for child in children:
            child_ok, child_leaves = _eval_condition_node(payload, child)
            if not child_ok:
                all_passed = False
            collected.extend(child_leaves)
        return all_passed, collected

    if "or" in node and isinstance(node["or"], list):
        children = node["or"]
        if not children:
            return False, []
        any_passed = False
        collected = []
        for child in children:
            child_ok, child_leaves = _eval_condition_node(payload, child)
            if child_ok:
                any_passed = True
            collected.extend(child_leaves)
        return any_passed, collected

    if "not" in node:
        child_ok, child_leaves = _eval_condition_node(payload, node["not"])
        return (not child_ok), child_leaves

    if "field" in node:
        leaf = _eval_single_condition(payload, node)
        return leaf["passed"], [leaf]

    return False, []


def _eval_rule_locally(payload: dict[str, Any], rule: Rule) -> tuple[bool, list[dict[str, Any]]]:
    return _eval_condition_node(payload, rule.condition or {})


def dry_run_against_rules(db: Session, parsed_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Evaluate the first parsed record (or all records up to 5) against active rules.
    Returns matched rule previews with rendered title/body and condition details.
    """
    if not parsed_records:
        return []

    rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()
    if not rules:
        return []

    sample_record = parsed_records[0]
    fake_event = Event(id=0, source_id=None, payload=sample_record)

    matched_previews: list[dict[str, Any]] = []

    # Try team's rules_engine first if implemented
    try:
        team_matches = team_evaluate(fake_event, rules)
    except Exception:
        team_matches = []

    if team_matches:
        rules_by_id = {r.id: r for r in rules}
        for m in team_matches:
            r = rules_by_id.get(m.rule_id)
            _, cond_results = _eval_rule_locally(sample_record, r) if r else (True, [])
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
            })
        return matched_previews

    # Fallback local evaluator so Dry-Run works immediately
    for rule in rules:
        matched, cond_results = _eval_rule_locally(sample_record, rule)
        if matched:
            matched_previews.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "team": rule.team,
                "severity": rule.severity,
                "color": rule.color,
                "channels": rule.channels or [],
                "rendered_title": _render_template(rule.title, sample_record),
                "rendered_body": _render_template(rule.body, sample_record),
                "conditions": cond_results,
            })

    return matched_previews
