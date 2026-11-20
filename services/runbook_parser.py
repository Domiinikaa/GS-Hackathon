"""
OSOBA 4 – zamiana runbooka (YAML / Markdown / wolny tekst) na listę kroków.

Krok: {"text": "Restart pricing-engine", "action": "restart_service" | "retry_workflow" | "http_get" |
       "escalate" | "webhook" | "open_ticket" | None, "params": {...}, "approval": "none" | "required"}
Przykłady wejścia: kartka zadania, Appendix B.
"""
from __future__ import annotations

from typing import Any


def parse_runbook(raw: str, fmt: str) -> list[dict[str, Any]]:
    # TODO (Osoba 4): yaml -> steps, markdown -> lista numerowana, text -> zdania (ew. LLM)
    return [{"text": line.strip(), "action": None, "params": {}, "approval": "none"}
            for line in raw.splitlines() if line.strip()]


def fill_steps(steps: list[dict[str, Any]], event_payload: dict) -> list[dict[str, Any]]:
    # TODO (Osoba 4): podstawić {{workflowId}} itd. wartościami ze zdarzenia
    return steps
