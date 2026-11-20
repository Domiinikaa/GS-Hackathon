"""
OSOBA 4 – zamiana runbooka (YAML / Markdown / wolny tekst / link) na listę kroków.

Runbook to (na razie) zwykła instrukcja dla człowieka: lista kroków do przeczytania.
Aplikacja niczego nie wykonuje, więc nie rozpoznajemy akcji ani zatwierdzeń.

Krok: {"text": "Check settlement service health", "action": None, "params": {}, "approval": "none"}
(pola action / params / approval zostają puste, żeby nie zmieniać wspólnego kształtu RunbookStep)

- yaml:     lista kroków albo {"steps": [...]}; krok to tekst albo słownik z polem text/name/title/description
- markdown: pozycje list ("1.", "-", "*", "- [ ]"); nagłówki pomijamy
- text:     każda linia / zdanie = krok ("then", "następnie", ";" też dzielą)
- link:     jeden krok "Open runbook <url>"
- auto:     zgadujemy format po treści

{{pole}} w treści kroku jest zamieniane na wartość ze zdarzenia (fill_steps).
"""
from __future__ import annotations

import re
from typing import Any

_LIST_ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+(?:\[[ xX]\]\s+)?(.*\S)\s*$")
_SPLIT_TEXT = re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])|;\s*|\s+(?:then|and then|następnie|potem)\s+", re.I)
_LEADING_THEN = re.compile(r"^(?:and then|then|następnie|potem)\s+", re.I)


def _step(text: str) -> dict[str, Any]:
    return {"text": text.strip(), "action": None, "params": {}, "approval": "none"}


# ---------------------------------------------------------------- formaty

def _parse_yaml(raw: str) -> list[dict[str, Any]]:
    try:
        import yaml  # pyyaml
    except ImportError as e:  # pragma: no cover
        raise ValueError("PyYAML is not installed (pip install pyyaml)") from e
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e

    if isinstance(doc, dict):
        if isinstance(doc.get("runbook"), dict):  # runbook: {name: ..., steps: [...]}
            doc = doc["runbook"]
        doc = doc.get("steps")
    if doc is None:
        return []
    if not isinstance(doc, list):
        raise ValueError("YAML runbook must be a list of steps or have a 'steps:' list")

    steps = []
    for item in doc:
        if isinstance(item, dict):
            item = next((item[k] for k in ("text", "name", "title", "description", "step") if item.get(k)), "")
        if str(item).strip():
            steps.append(_step(str(item)))
    return steps


def _parse_markdown(raw: str) -> list[dict[str, Any]]:
    items = [m.group(1) for line in raw.splitlines() if (m := _LIST_ITEM.match(line))]
    if not items:  # brak list -> traktuj jak tekst (bez nagłówków)
        return _parse_text("\n".join(l for l in raw.splitlines() if not l.lstrip().startswith("#")))
    cleaned = [re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", i) for i in items]  # **bold**, `code`
    return [_step(t) for t in cleaned]


def _parse_text(raw: str) -> list[dict[str, Any]]:
    steps = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LIST_ITEM.match(line)
        if m:
            line = m.group(1)
        for part in _SPLIT_TEXT.split(line):
            part = _LEADING_THEN.sub("", (part or "").strip(" ."))
            if part:
                steps.append(_step(part[0].upper() + part[1:]))
    return steps


def detect_format(raw: str) -> str:
    s = raw.strip()
    if re.fullmatch(r"https?://\S+", s):
        return "link"
    if re.search(r"^\s*steps\s*:", s, re.M) or re.search(r"^\s*-\s+\w+\s*:", s, re.M):
        return "yaml"
    if re.search(r"^\s*(#|\d+[.)]\s|[-*+]\s)", s, re.M):
        return "markdown"
    return "text"


def parse_runbook(raw: str, fmt: str = "auto") -> list[dict[str, Any]]:
    """Główne wejście. Rzuca ValueError przy niepoprawnym YAML-u."""
    if not raw or not raw.strip():
        return []
    fmt = (fmt or "auto").lower()
    if fmt in ("auto", ""):
        fmt = detect_format(raw)
    if fmt == "yaml":
        return _parse_yaml(raw)
    if fmt in ("markdown", "md"):
        return _parse_markdown(raw)
    if fmt == "link":
        return [_step(f"Open runbook {raw.strip()}")]
    return _parse_text(raw)


# ---------------------------------------------------------------- podstawianie wartości

def fill_steps(steps: list[dict[str, Any]], event_payload: Any) -> list[dict[str, Any]]:
    """Podstawia {{workflowId}} itd. wartościami ze zdarzenia. Nie zmienia oryginału."""
    from services.rules_engine import render_template  # import tutaj, żeby uniknąć importu cyklicznego
    out = []
    for step in steps or []:
        filled = _step(render_template(step.get("text", ""), event_payload) or "")
        filled["done"] = False
        out.append(filled)
    return out
