"""
OSOBA 4 – zamiana runbooka w DOWOLNEJ formie na listę kroków (kartka zadania: Appendix B).

Runbook to (na razie) zwykła instrukcja dla człowieka: lista kroków do przeczytania.
Aplikacja niczego nie wykonuje. Zasada: przy "auto" nigdy błąd i nic nie ginie po cichu –
jeśli czegoś nie użyliśmy, mówimy o tym w ostrzeżeniu (warnings).

Krok: {"text": "Check settlement service health", "action": None, "params": {}, "approval": "none"}
(pola action / params / approval zostają puste, żeby nie zmieniać wspólnego kształtu RunbookStep)

Obsługiwane formy:
- yaml / json: lista kroków pod dowolnym kluczem (steps, procedure, actions, tasks…), także głębiej;
               krok to tekst albo słownik, np. {check, action, url} -> "Check: Is X healthy? (action: http_get; url: …)",
               {if, action, team, approval: required} -> "If retry fails twice: Escalate (team: …) (requires approval)".
               Klucze "runbook"/"name" -> proponowana nazwa, "matches" -> do jakich zdarzeń runbook pasuje.
- html:       skopiowane z wiki / Confluence: <li> = krok, wiersze tabel, akapity
- markdown:   listy ("1.", "1)", "a)", "-", "*", "•", "- [ ]", "Step 1:"), bloki kodu doklejane do kroku, tabele
- text:       zdania / linie; dzieli też ";", "->", "→", "then" oraz ", wait…", ", and if…" (wolny tekst z wiki / czatu)
- link:       jeden krok "Open runbook <url>"
- auto:       zgadujemy format po treści

{{pole}} w treści kroku jest zamieniane na wartość ze zdarzenia (fill_steps).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

# ---------------------------------------------------------------- wynik

@dataclass
class ParseResult:
    format: str
    steps: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    name: str | None = None                 # proponowana nazwa (np. "runbook: settlement-timeout")
    matches: dict[str, Any] | None = None   # do jakich zdarzeń pasuje: {"and": [{"field","op","value"}]}


def _step(text: str) -> dict[str, Any]:
    return {"text": text.strip(), "action": None, "params": {}, "approval": "none"}


def _short(s: str, n: int = 60) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- wzorce

# początek punktu listy: "1." "1)" "a)" "b." "-" "*" "+" "•" "Step 1:" (+ opcjonalny checkbox "[ ]")
_LIST_ITEM = re.compile(
    r"^\s*(?:\d+[.)]|[a-zA-Z][.)](?=\s)|[-*+•▪◦]|step\s*\d+\s*[:.)-])\s*(?:\[[ xX]\]\s+)?(.*\S)\s*$", re.I)

# kropka kończy zdanie, ale nie po skrótach typu "e.g." / "np." (lookbehind musi mieć stałą długość)
_SPLIT_SENTENCES = re.compile(
    r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bnp\.)(?<!\betc\.)(?<!\bvs\.)(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])"
    r"|;\s*|\s*(?:->|=>|→)\s*|\s+(?:then|and then|następnie|potem)\s+", re.I)

# czasowniki, od których zaczyna się kolejna czynność w zdaniu: "Restart X, wait 2 minutes, and call Y"
_VERBS = (
    "restart|wait|call|check|open|post|roll|retry|rerun|escalate|notify|tell|page|contact|verify|ensure|run|"
    "stop|start|scale|clear|flush|fail|switch|disable|enable|rollback|revert|deploy|redeploy|create|raise|"
    "file|update|inform|ask|look|review|confirm|monitor|increase|decrease|drain|kill|purge|reboot|bounce|"
    "sprawdź|zrestartuj|poczekaj|zadzwoń|otwórz|napisz|powiadom|wyłącz|włącz|uruchom|zatrzymaj|eskaluj|zgłoś"
)
_SPLIT_CLAUSES = re.compile(rf",\s*(?:and\s+|then\s+|i\s+|a\s+potem\s+)?(?=(?:if|when|unless|jeśli|jeżeli|gdy|{_VERBS})\b)", re.I)
_CONDITION_START = re.compile(r"^(?:and\s+)?(?:if|when|unless|jeśli|jeżeli|gdy)\b", re.I)

_LEADING_WORDS = re.compile(
    r"^(?:and then|then|next|after that|first(?:ly)?|second(?:ly)?|third(?:ly)?|finally|lastly|and|"
    r"następnie|potem|najpierw|na koniec|w końcu)\s*,?\s+", re.I)

# klucze w YAML / JSON
_LIST_KEYS = ("steps", "procedure", "procedures", "actions", "tasks", "instructions", "checklist",
              "playbook", "runbook", "items", "remediation", "kroki")
_MAIN_KEYS = ("text", "name", "title", "description", "step", "summary", "task", "instruction", "do",
              "opis", "krok")
_LABEL_KEYS = ("check", "verify", "ask", "question", "note", "warning", "sprawdź")   # -> "Check: …"
_COND_KEYS = {"if": "If", "when": "When", "unless": "Unless", "condition": "If", "on": "On", "jeśli": "Jeśli"}
_SKIP_KEYS = {"id", "order", "number", "no", "nr", "index", "seq", "position"}
_PARAM_KEYS = {"params", "parameters", "with", "args", "arguments", "inputs", "input", "vars"}
_APPROVAL_KEYS = {"approval", "requires_approval", "approval_required", "needs_approval", "approve",
                  "manual_approval", "manual", "confirm", "requires_confirmation"}
_SUBSTEP_KEYS = ("steps", "substeps", "sub_steps", "children")
_META_KEYS = {"name", "title", "id", "version", "owner", "team", "author", "description", "summary",
              "updated", "created", "tags", "matches", "match", "rule", "format", "kind", "type"}
_NAME_KEYS = ("runbook", "name", "title", "id")
_MATCH_KEYS = ("matches", "match", "when", "trigger", "applies_to")


def _clean_inline_md(s: str) -> str:
    """**bold**, __bold__, `code`, [tekst](url) -> czytelny tekst."""
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)
    s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip()


# ---------------------------------------------------------------- YAML / JSON (dane strukturalne)

def _humanize(key: str) -> str:
    """retry_workflow / retryWorkflow -> Retry workflow"""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(key)).replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:].lower() if s else s


def _fmt_value(v: Any) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, dict):
        return ", ".join(f"{k}: {_fmt_value(x)}" for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(_fmt_value(x) for x in v)
    return "" if v is None else str(v).strip()


def _is_approval(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("required", "yes", "true", "manual", "y", "1", "always")


def _get(d: dict, keys) -> tuple[Any, Any]:
    """Pierwszy klucz z listy (bez względu na wielkość liter) z niepustą, prostą wartością."""
    lower = {str(k).lower(): k for k in d}
    for k in keys:
        real = lower.get(k)
        if real is not None and d[real] not in (None, "", [], {}) and not isinstance(d[real], (dict, list)):
            return real, d[real]
    return None, None


def _item_to_texts(item: Any) -> list[str]:
    """Jeden element listy kroków -> 1+ tekstów kroków (podkroki idą osobno, po rodzicu)."""
    if item is None:
        return []
    if isinstance(item, list):
        return [t for x in item for t in _item_to_texts(x)]
    if not isinstance(item, dict):
        text = _fmt_value(item)
        return [text] if text else []

    used: set = set()
    main = None
    key, value = _get(item, _MAIN_KEYS)
    if key is not None:
        used.add(key)
        main = _fmt_value(value)
    else:
        key, value = _get(item, _LABEL_KEYS)
        if key is not None:
            used.add(key)
            main = f"{_humanize(key)}: {_fmt_value(value)}"

    prefix = ""
    approval = False
    extras: list[str] = []
    substeps: list[str] = []
    for k, v in item.items():
        kl = str(k).lower()
        if k in used or kl in _SKIP_KEYS or v in (None, "", [], {}):
            continue
        if kl in _COND_KEYS and not isinstance(v, (dict, list)) and not prefix:
            prefix = f"{_COND_KEYS[kl]} {_fmt_value(v)}: "      # if: "retry fails twice" -> "If retry fails twice: "
        elif kl in _APPROVAL_KEYS:
            approval = approval or _is_approval(v)
        elif kl in _SUBSTEP_KEYS and isinstance(v, list):
            substeps += _item_to_texts(v)
        elif kl in _PARAM_KEYS and isinstance(v, dict):
            extras += [f"{pk}: {_fmt_value(pv)}" for pk, pv in v.items()]
        elif kl == "action" and main is None and not isinstance(v, (dict, list)):
            main = _humanize(v)                                  # action: retry_workflow -> "Retry workflow"
        else:
            extras.append(f"{k}: {_fmt_value(v)}")

    if main is None:
        if len(extras) == 1 and not substeps:                    # "- check: settlement health"
            main, extras = extras[0], []
        elif extras:
            main, extras = extras[0], extras[1:]
        elif substeps:
            return substeps
        else:
            return []
    text = prefix + main
    if extras:
        text += f" ({'; '.join(extras)})"
    if approval:
        text += " (requires approval)"
    return [text] + substeps


def _find_step_list(doc: Any, depth: int = 0) -> Any:
    if isinstance(doc, list):
        return doc
    if not isinstance(doc, dict) or depth > 4:
        return None
    lower = {str(k).lower(): k for k in doc}
    for key in _LIST_KEYS:                           # najpierw znane nazwy
        if key in lower:
            found = _find_step_list(doc[lower[key]], depth + 1)
            if found is not None:
                return found
    for k, v in doc.items():                         # potem pierwsza lista gdziekolwiek (poza "matches")
        if str(k).lower() in _MATCH_KEYS:
            continue
        found = _find_step_list(v, depth + 1)
        if found is not None:
            return found
    return None


def normalize_matches(m: Any) -> dict[str, Any] | None:
    """matches z runbooka -> grupa warunków jak w regułach.

    {"type": "WORKFLOW_FAILED", "error.code": "TIMEOUT"} -> {"and": [{"field": "type", "op": "eq", ...}, ...]}
    Gotowa grupa {"and"/"or": [...]} zostaje bez zmian. Lista wartości -> operator "in".
    """
    if not isinstance(m, dict) or not m:
        return None
    if "and" in m or "or" in m:
        return m
    conds = []
    for k, v in m.items():
        if isinstance(v, dict) and "op" in v:
            conds.append({"field": str(k), "op": v["op"], "value": v.get("value")})
        elif isinstance(v, list):
            conds.append({"field": str(k), "op": "in", "value": v})
        elif isinstance(v, str) and "*" in v:
            conds.append({"field": str(k), "op": "wildcard", "value": v})
        else:
            conds.append({"field": str(k), "op": "eq", "value": v})
    return {"and": conds}


def _structured(doc: Any, fmt: str) -> ParseResult:
    result = ParseResult(format=fmt, steps=[])
    if isinstance(doc, dict):
        lower = {str(k).lower(): k for k in doc}
        for k in _NAME_KEYS:
            if k in lower and isinstance(doc[lower[k]], (str, int)) and str(doc[lower[k]]).strip():
                result.name = str(doc[lower[k]]).strip()
                break
        for k in _MATCH_KEYS:
            if k in lower and isinstance(doc[lower[k]], dict):
                result.matches = normalize_matches(doc[lower[k]])
                break

    steps_list = _find_step_list(doc)
    if steps_list is None:
        if isinstance(doc, dict):                    # {step1: "...", step2: "..."} bez listy
            steps_list = [v for k, v in doc.items() if str(k).lower() not in _META_KEYS | set(_MATCH_KEYS)]
        elif doc is not None:
            steps_list = [doc]
        else:
            steps_list = []
    result.steps = [_step(t) for t in _item_to_texts(steps_list) if t.strip()]
    return result


_STRUCT_HINT = "If this is a plain list of steps, choose Auto-detect or Markdown instead."


def _parse_yaml(raw: str) -> ParseResult:
    try:
        import yaml  # pyyaml
    except ImportError as e:  # pragma: no cover
        raise ValueError("PyYAML is not installed (pip install pyyaml)") from e
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (problem around line {mark.line + 1})" if mark is not None else ""
        raise ValueError(f"This is not valid YAML{where}. {_STRUCT_HINT}") from e
    return _structured(doc, "yaml")


def _parse_json(raw: str) -> ParseResult:
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"This is not valid JSON (problem around line {e.lineno}). {_STRUCT_HINT}") from e
    return _structured(doc, "json")


# ---------------------------------------------------------------- HTML (wiki / Confluence)

class _HtmlSteps(HTMLParser):
    """<li> = krok (zagnieżdżone osobno), <tr> = krok z komórek; reszta tekstu -> linie."""
    BLOCK = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "pre"}
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[str] = []      # kroki z <li> / <tr>
        self.loose: list[str] = []      # tekst spoza list i tabel
        self._li: list[list[str]] = []  # stos otwartych <li>
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._buf: list[str] = []
        self._in_heading = False
        self._skip = 0                  # <script>/<style>
        self._header_row = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "li":
            self._li.append([])
        elif tag == "tr":
            self._row = []
            self._header_row = False
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._header_row = self._header_row or tag == "th"
        elif tag in self.BLOCK:
            self._flush()
            self._in_heading = tag in self.HEADINGS

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "li" and self._li:
            text = " ".join("".join(self._li.pop()).split())
            if text:
                self.items.append(text)
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            cells = [c for c in self._row if c]
            if cells and not self._header_row:
                if len(cells) > 1 and re.fullmatch(r"\d+[.)]?", cells[0]):
                    cells = cells[1:]            # kolumna z numerem kroku
                self.items.append(" – ".join(cells))
            self._row = None
        elif tag in self.BLOCK:
            self._flush()
            self._in_heading = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._li:
            self._li[-1].append(data)
        elif not self._in_heading and self._row is None:
            self._buf.append(data)

    def _flush(self):
        text = " ".join("".join(self._buf).split())
        if text:
            self.loose.append(text)
        self._buf = []

    def result(self) -> list[str]:
        self._flush()
        return self.items


def _parse_html(raw: str) -> ParseResult:
    parser = _HtmlSteps()
    parser.feed(raw)
    parser.close()
    items = parser.result()
    if not items:                                  # brak list i tabel -> akapity jak tekst
        result = _parse_text("\n".join(parser.loose))
        result.format = "html"
        return result
    result = ParseResult(format="html", steps=[_step(t) for t in items])
    if parser.loose:
        result.warnings.append(_ignored_warning(parser.loose))
    return result


# ---------------------------------------------------------------- Markdown

def _ignored_warning(lines: list[str]) -> str:
    shown = ", ".join(f'"{_short(l)}"' for l in lines[:3])
    more = f" and {len(lines) - 3} more" if len(lines) > 3 else ""
    what = "This line is" if len(lines) == 1 else f"{len(lines)} lines are"
    return (f"{what} not part of the list, so not used as a step: {shown}{more}. "
            f"Number it like the other steps if it should be one.")


def _parse_markdown(raw: str) -> ParseResult:
    lines = raw.replace("\r\n", "\n").split("\n")
    has_list = any(_LIST_ITEM.match(l) for l in lines)
    has_table = any(re.match(r"^\s*\|.*\|\s*$", l) for l in lines)
    if not has_list and not has_table:             # brak list i tabel -> tekst (bez nagłówków)
        result = _parse_text("\n".join(l for l in lines if not l.lstrip().startswith("#")))
        result.format = "markdown"
        return result

    steps: list[str] = []
    ignored: list[str] = []
    in_code, code, table_header_seen = False, [], False

    def attach_code():
        block = "; ".join(c.strip() for c in code if c.strip())
        if block:
            if steps:
                steps[-1] += f" ({block})"
            else:
                steps.append(block)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if in_code:                            # koniec bloku kodu -> doklej do poprzedniego kroku
                attach_code()
                code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if not stripped or stripped.startswith("#") or re.fullmatch(r"[-*_=]{3,}", stripped):
            continue
        if re.match(r"^\|.*\|$", stripped):        # tabela
            if re.fullmatch(r"\|[\s:|-]+\|", stripped):
                continue                           # |---|---|
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not table_header_seen:
                table_header_seen = True           # pierwszy wiersz = nagłówki
                continue
            cells = [c for c in cells if c]
            if len(cells) > 1 and re.fullmatch(r"\d+[.)]?", cells[0]):
                cells = cells[1:]
            if cells:
                steps.append(_clean_inline_md(" – ".join(cells)))
            continue
        m = _LIST_ITEM.match(line)
        if m:
            steps.append(_clean_inline_md(m.group(1)))
        elif steps and line[:1] in (" ", "\t"):    # wcięta kontynuacja punktu
            steps[-1] += " " + _clean_inline_md(stripped)
        else:
            ignored.append(stripped)               # zwykły akapit między / po listach
    if in_code and code:                           # niezamknięty blok kodu
        attach_code()
    result = ParseResult(format="markdown", steps=[_step(t) for t in steps if t.strip()])
    if ignored:
        result.warnings.append(_ignored_warning(ignored))
    return result


# ---------------------------------------------------------------- zwykły tekst

def _strip_leading_words(part: str) -> str:
    while True:                                    # "Then, finally, ..." -> usuń wszystkie słowa-łączniki
        stripped = _LEADING_WORDS.sub("", part)
        if stripped == part:
            return part
        part = stripped


def _split_clauses(sentence: str) -> list[str]:
    """'Restart X, wait 2 minutes, and if Y, call Z' -> ['Restart X', 'Wait 2 minutes', 'If Y, call Z']."""
    pieces = [p.strip() for p in _SPLIT_CLAUSES.split(sentence) if p and p.strip()]
    merged: list[str] = []
    for p in pieces:
        # "if latency is still high" + "call the on-call" -> jeden krok warunkowy
        if merged and _CONDITION_START.match(merged[-1]) and "," not in merged[-1]:
            merged[-1] = f"{merged[-1]}, {p}"
        else:
            merged.append(p)
    return merged


def _parse_text(raw: str) -> ParseResult:
    steps = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LIST_ITEM.match(line)
        if m:
            line = m.group(1)
        for sentence in _SPLIT_SENTENCES.split(line):
            # "First, check X" -> "check X" zanim podzielimy po przecinkach (inaczej zostałoby samo "First")
            sentence = _strip_leading_words((sentence or "").strip(" ."))
            if not sentence:
                continue
            # zdanie opisowe ("When X, it's usually Y") zostawiamy w całości; czynności dzielimy
            for part in _split_clauses(sentence):
                part = _strip_leading_words(part.strip(" ."))
                if part:
                    steps.append(_step(part[0].upper() + part[1:]))
    return ParseResult(format="text", steps=steps)


# ---------------------------------------------------------------- wykrywanie formatu

def _looks_like_json(s: str) -> bool:
    if not (s[:1] in "{[" and s[-1:] in "}]"):
        return False
    try:
        json.loads(s)
        return True
    except ValueError:
        return False


def detect_format(raw: str) -> str:
    s = raw.strip()
    if re.fullmatch(r"https?://\S+", s):
        return "link"
    if _looks_like_json(s):
        return "json"
    if re.search(r"<\s*(ol|ul|li|p|br|div|table|tr|h[1-6])\b[^>]*>", s, re.I):
        return "html"
    if (re.search(r"^\s*(steps|procedure|actions|tasks|runbook|playbook|matches)\s*:", s, re.M | re.I)
            or re.search(r"^\s*-\s+[\w-]+\s*:(\s|$)", s, re.M)):
        return "yaml"
    if re.search(r"^\s*(#|```|\|.*\||\d+[.)]\s|[a-zA-Z][.)]\s|[-*+•]\s|step\s*\d+\s*[:.)-])", s, re.M | re.I):
        return "markdown"
    return "text"


_PARSERS = {"yaml": _parse_yaml, "json": _parse_json, "html": _parse_html,
            "markdown": _parse_markdown, "md": _parse_markdown, "text": _parse_text}
_FORMAT_NAMES = {"yaml": "YAML", "json": "JSON", "html": "HTML"}


def _placeholder_warnings(steps: list[dict[str, Any]]) -> list[str]:
    out = []
    for i, s in enumerate(steps, 1):
        t = s["text"]
        if t.count("{{") != t.count("}}"):
            out.append(f"Step {i} has an unclosed placeholder. Write it like {{{{payload.tradeId}}}}.")
        else:
            single = re.search(r"(?<!\{)\{([\w.]+)\}(?!\})", t)
            if single:
                out.append(f"Step {i} uses {{{single.group(1)}}} with single braces, so it won't be filled in. "
                           f"Use double braces: {{{{{single.group(1)}}}}}.")
    return out


def parse_runbook_full(raw: str, fmt: str = "auto") -> ParseResult:
    """Główne wejście: format, kroki, ostrzeżenia, proponowana nazwa i matches.

    - format wybrany ręcznie: tylko ten format; niepoprawny YAML / JSON -> ValueError z czytelnym komunikatem
    - "auto": zgadujemy; gdy rozpoznany format zawiedzie albo nic nie da -> każda linia jako krok + ostrzeżenie
    """
    fmt = (fmt or "auto").lower()
    if not raw or not raw.strip():
        return ParseResult(format=fmt, steps=[])
    if fmt == "link" or (fmt == "auto" and detect_format(raw) == "link"):
        return ParseResult(format="link", steps=[_step(f"Open runbook {raw.strip()}")])

    if fmt != "auto":
        result = _PARSERS.get(fmt, _parse_text)(raw)
    else:
        detected = detect_format(raw)
        try:
            result = _PARSERS[detected](raw)
            broken = None
        except ValueError:
            result, broken = ParseResult(format=detected, steps=[]), detected
        if not result.steps:
            # nic nie wyszło: każda linia jako krok (bez samych nagłówków typu "steps:")
            kept = "\n".join(l for l in raw.splitlines()
                             if not re.fullmatch(r"\s*[\w-]+\s*:\s*", l) and not l.lstrip().startswith("#"))
            fallback = _parse_text(kept)
            if broken:
                fallback.warnings.append(
                    f"This looks like {_FORMAT_NAMES.get(broken, broken)} but isn't valid, "
                    f"so each line was used as a step. Check the steps below.")
            result = fallback

    if not result.steps:
        result.warnings.append("No steps found. Write one step per line, or as a numbered list.")
    result.warnings += _placeholder_warnings(result.steps)
    return result


def parse_runbook_with_format(raw: str, fmt: str = "auto") -> tuple[str, list[dict[str, Any]]]:
    r = parse_runbook_full(raw, fmt)
    return r.format, r.steps


def parse_runbook(raw: str, fmt: str = "auto") -> list[dict[str, Any]]:
    """Same kroki. Rzuca ValueError tylko przy ręcznie wybranym, niepoprawnym YAML-u / JSON-ie."""
    return parse_runbook_full(raw, fmt).steps


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
