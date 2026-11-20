"""
OSOBA 4 – silnik reguł.

Zadanie: dla jednego zdarzenia sprawdzić wszystkie reguły i zwrócić dopasowania.
- warunki: rule.condition = {"and": [...]} albo {"or": [...]}, każdy warunek {"field", "op", "value"}
  pola z kropkami ("payload.notional", "labels.service") czytamy z zagnieżdżonego JSON-a
  operatory: eq neq gt gte lt lte in contains wildcard (lista w frontend/src/rules/ruleTypes.ts)
- szablony: "Rejected {{payload.currency}}" -> "Rejected EUR"
- dedup_key: rule.id + (wartość pola rule.group_by, jeśli jest)
- kroki runbooka: services/runbook_parser.py, z podstawionymi wartościami ze zdarzenia
"""
from __future__ import annotations

from models import Event, Rule
from services.contracts import Match


def evaluate(event: Event, rules: list[Rule]) -> list[Match]:
    # TODO (Osoba 4): prawdziwe dopasowanie. Na razie nic nie pasuje.
    return []
