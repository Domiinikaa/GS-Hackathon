"""
OSOBA 4 – silnik reguł.

Dla jednego zdarzenia sprawdza wszystkie reguły i zwraca dopasowania (Match).

- warunki: rule.condition = {"and": [...]} albo {"or": [...]}, każdy warunek {"field", "op", "value"}.
  Grupy można zagnieżdżać: {"and": [{"field": ...}, {"or": [...]}]}.
- pola z kropkami ("payload.notional", "labels.service", "items.0.id") czytamy z zagnieżdżonego JSON-a.
- operatory: eq neq gt gte lt lte in contains wildcard (te same co frontend/src/rules/ruleTypes.ts).
- szablony: "Rejected {{payload.currency}}" -> "Rejected EUR". Brak pola -> placeholder zostaje widoczny.
- dedup_key: rule.id [| wartość pola group_by] [| numer okna czasowego, jeśli group_window_s].
  Ten sam klucz = ten sam alert (Osoba 1 robi count += 1), więc "jeden alert na instrument co 5 min"
  wychodzi sam z siebie: po 5 minutach zmienia się numer okna, więc powstaje nowy alert.
- kroki runbooka: z rule.runbook_id albo z runbooka, którego `matches` pasuje do zdarzenia;
  wartości ze zdarzenia są podstawione (services/runbook_parser.fill_steps).

Wszystko poza `evaluate` to czyste funkcje bez bazy, łatwe do testowania w czystym Pythonie.
"""
from __future__ import annotations

import fnmatch
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, object_session

from models import Event, Rule, Runbook
from services.contracts import Match
from services.runbook_parser import fill_steps, normalize_matches

log = logging.getLogger(__name__)

_MISSING = object()
_PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


# ---------------------------------------------------------------- odczyt pól

def get_field(data: Any, path: str) -> Any:
    """'payload.notional' -> data["payload"]["notional"]. Zwraca _MISSING, jeśli pola nie ma.

    Najpierw próbuje całego klucza (np. dosłowne "meta.schema"), potem schodzi po kropkach.
    Liczby w ścieżce indeksują listy: "items.0.id".
    """
    if not path:
        return _MISSING
    if isinstance(data, dict) and path in data:
        return data[path]
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return _MISSING
            cur = cur[part]
        elif isinstance(cur, list) and part.lstrip("-").isdigit():
            idx = int(part)
            if not -len(cur) <= idx < len(cur):
                return _MISSING
            cur = cur[idx]
        else:
            return _MISSING
    return cur


# ---------------------------------------------------------------- operatory

_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")  # 1,000,000 albo 1,234.5


def _to_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace("_", "").replace(" ", "")
        if _THOUSANDS.match(s):
            s = s.replace(",", "")        # separator tysięcy: 10,000,000
        elif s.count(",") == 1 and "." not in s:
            s = s.replace(",", ".")       # polski przecinek dziesiętny: 1,5
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _equals(actual: Any, expected: Any) -> bool:
    # true/false porównujemy tylko z true/false (albo tekstem "true"/"false"), nigdy z 1/0
    if isinstance(actual, bool) or isinstance(expected, bool):
        return str(actual).lower() == str(expected).lower()
    if actual == expected:
        return True
    a, e = _to_number(actual), _to_number(expected)
    return a is not None and e is not None and a == e


def _as_list(value: Any) -> list[Any]:
    """UI może wysłać listę albo tekst "WARN, ERROR, FATAL"."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return [value]


def _compare(actual: Any, expected: Any, op: str) -> bool:
    a, e = _to_number(actual), _to_number(expected)
    if a is None or e is None:
        return False
    return {"gt": a > e, "gte": a >= e, "lt": a < e, "lte": a <= e}[op]


def check_condition(data: Any, cond: dict[str, Any]) -> bool:
    """Jeden warunek {"field","op","value"} albo zagnieżdżona grupa {"and"/"or"/"not": ...}."""
    if "not" in cond:
        return not check_condition(data, cond["not"])
    if "and" in cond or "or" in cond:
        return check_group(data, cond)

    op = cond.get("op", "eq")
    expected = cond.get("value")
    actual = get_field(data, cond.get("field", ""))

    if actual is _MISSING:
        return op == "neq"  # pola nie ma -> na pewno "nie równa się"

    if op == "eq":
        return _equals(actual, expected)
    if op == "neq":
        return not _equals(actual, expected)
    if op in ("gt", "gte", "lt", "lte"):
        return _compare(actual, expected, op)
    if op == "in":
        return any(_equals(actual, e) for e in _as_list(expected))
    if op == "contains":
        if isinstance(actual, list):
            return any(_equals(item, expected) for item in actual)
        return str(expected).lower() in str(actual).lower()
    if op == "wildcard":
        return fnmatch.fnmatchcase(str(actual), str(expected))

    log.warning("Unknown operator %r in condition %r", op, cond)
    return False


def check_group(data: Any, group: dict[str, Any] | None) -> bool:
    """{"and": [...]} = wszystkie; {"or": [...]} = co najmniej jeden; {"not": ...} = zaprzeczenie. Pusta/brak = pasuje."""
    if not group:
        return True
    if "not" in group:
        return not check_condition(data, group["not"])
    if "and" in group:
        return all(check_condition(data, c) for c in group["and"] or [])
    if "or" in group:
        items = group["or"] or []
        return not items or any(check_condition(data, c) for c in items)
    if "field" in group:  # pojedynczy warunek bez grupy też akceptujemy
        return check_condition(data, group)
    # prosty zapis z runbooka (Appendix B): {"type": "WORKFLOW_FAILED", "error.code": "TIMEOUT"}
    return check_group(data, normalize_matches(group))


# ---------------------------------------------------------------- szablony

def _format_value(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (dict, list)):
        import json
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def render_template(template: str | None, data: Any) -> str | None:
    """'Rejected {{payload.currency}}' -> 'Rejected EUR'. Nieznane pole zostaje jako {{pole}}."""
    if template is None:
        return None

    def repl(m: re.Match[str]) -> str:
        value = get_field(data, m.group(1))
        return m.group(0) if value is _MISSING or value is None else _format_value(value)

    return _PLACEHOLDER.sub(repl, template)


# ---------------------------------------------------------------- deduplikacja

def build_dedup_key(rule: Rule, data: Any, at: datetime | None = None) -> str:
    parts = [rule.id]
    if rule.group_by:
        value = get_field(data, rule.group_by)
        parts.append("-" if value is _MISSING or value is None else _format_value(value))
    if rule.group_window_s:
        ts = (at or datetime.utcnow()).timestamp()
        parts.append(f"w{int(ts // rule.group_window_s)}")
    return "|".join(parts)


# ---------------------------------------------------------------- runbook

def _runbook_steps(rule: Rule, data: Any, db: Session | None = None) -> list[dict[str, Any]]:
    db = db or object_session(rule)
    if db is None:
        return []
    runbook: Runbook | None = None
    if rule.runbook_id:
        runbook = db.get(Runbook, rule.runbook_id)
    else:
        # runbook może sam powiedzieć, do jakich zdarzeń pasuje (Runbook.matches = grupa warunków)
        for rb in db.query(Runbook).filter(Runbook.matches.isnot(None)).all():
            if rb.matches and check_group(data, rb.matches):
                runbook = rb
                break
    if runbook is None or not runbook.steps:
        return []
    return fill_steps(runbook.steps, data)


# ---------------------------------------------------------------- główna funkcja

def rule_matches(rule: Rule, data: Any) -> bool:
    try:
        return check_group(data, rule.condition)
    except Exception:  # jedna zepsuta reguła nie może zatrzymać całego ingestu
        log.exception("Rule %s failed to evaluate", rule.id)
        return False


def build_match(rule: Rule, data: Any, event_id: int, at: datetime | None = None,
                steps: list[dict[str, Any]] | None = None) -> Match:
    return Match(
        rule_id=rule.id,
        team=rule.team,
        event_id=event_id,
        dedup_key=build_dedup_key(rule, data, at),
        title=render_template(rule.title, data) or rule.name,
        body=render_template(rule.body, data),
        severity=rule.severity or "warning",
        color=rule.color or "amber",
        channels=list(rule.channels or []),
        steps=steps or [],
    )


def evaluate(event: Event, rules: list[Rule], db: Session | None = None) -> list[Match]:
    data = event.payload if event.payload is not None else {}
    at = event.received_at or datetime.utcnow()
    matches: list[Match] = []
    for rule in rules:
        if rule.enabled is False or not rule_matches(rule, data):
            continue
        matches.append(build_match(rule, data, event.id, at, _runbook_steps(rule, data, db=db)))
    return matches
