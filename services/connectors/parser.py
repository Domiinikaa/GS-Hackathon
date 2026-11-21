"""
Universal schema-less payload parser, envelope unwrapper, field alias mapper,
and recursive schema/field discovery engine.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


DEFAULT_LOG_REGEX = (
    r"^(?P<timestamp>\S+)\s+"
    r"(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\s+"
    r"service=(?P<service>\S+)\s+"
    r"(?:instrument=(?P<instrument>\S+)\s+)?"
    r"(?:latency_ms=(?P<latency_ms>\d+(?:\.\d+)?)\s+)?"
    r"(?:message=(?P<message>.+))?$"
)


def _cast_scalar(value: str) -> Any:
    """Convert numeric/boolean string captures into native Python types."""
    if value is None:
        return None
    s = value.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1]
    lower = s.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in ("null", "none"):
        return None
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _parse_kv_line(line: str) -> dict[str, Any]:
    """Parse key=value pairs (supports quoted values)."""
    result: dict[str, Any] = {}
    pattern = re.compile(r'([A-Za-z0-9_.-]+)=(".*?"|\'.*?\'|\S+)')
    for match in pattern.finditer(line):
        result[match.group(1)] = _cast_scalar(match.group(2))
    if not result:
        return {"raw": line}
    return result


def _parse_single_line(line: str, parser_mode: str, regex_pattern: Optional[str]) -> dict[str, Any]:
    stripped = line.strip()
    if not stripped:
        return {}

    if parser_mode in ("auto", "json", "ndjson"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except json.JSONDecodeError:
            if parser_mode == "json":
                raise ValueError(f"Invalid JSON payload: {stripped[:120]}")

    if parser_mode in ("regex", "auto") and regex_pattern:
        m = re.search(regex_pattern, stripped)
        if m:
            gd = m.groupdict()
            if gd:
                return {k: _cast_scalar(v) for k, v in gd.items() if v is not None}
            return {"groups": [_cast_scalar(g) for g in m.groups()], "raw": stripped}

    if parser_mode in ("key_value", "auto"):
        kv = _parse_kv_line(stripped)
        if kv and kv != {"raw": stripped}:
            # Also try to capture leading timestamp + log level if present
            prefix_match = re.match(
                r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\S*)\s+(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b",
                stripped,
            )
            if prefix_match:
                kv.setdefault("timestamp", prefix_match.group("timestamp"))
                kv.setdefault("level", prefix_match.group("level"))
            return kv

    return {"raw": stripped}


def get_by_path(data: Any, path: str) -> Any:
    """Resolve a dot-separated path inside nested dicts (e.g. 'payload.notional')."""
    if not path:
        return data
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    """Set a value at a dot-separated path inside a dict."""
    parts = [p for p in path.split(".") if p]
    if not parts:
        return
    cur = data
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def apply_transforms(record: dict[str, Any], config: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    Apply optional Idea 5 transforms:
      - `root_path`: unwrap a nested envelope (e.g. 'payload' or 'data.event')
      - `field_aliases`: copy/map fields from source dot-paths to target names
    """
    if not isinstance(record, dict):
        record = {"value": record}
    cfg = config or {}
    out = dict(record)

    root_path = str(cfg.get("root_path") or "").strip()
    if root_path:
        unwrapped = get_by_path(out, root_path)
        if isinstance(unwrapped, dict):
            # Keep original envelope under _envelope for traceability
            envelope_meta = {k: v for k, v in out.items() if k != root_path.split(".")[0]}
            out = dict(unwrapped)
            if envelope_meta:
                out["_envelope"] = envelope_meta

    aliases = cfg.get("field_aliases")
    if isinstance(aliases, dict):
        for src_path, target_path in aliases.items():
            src_str = str(src_path).strip()
            dst_str = str(target_path).strip()
            if not src_str or not dst_str:
                continue
            val = get_by_path(out, src_str)
            if val is not None:
                set_by_path(out, dst_str, val)

    return out


def parse_raw_payload(raw_input: Any, config: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """
    Universally parse incoming data (dict, list, JSON string, NDJSON, regex log,
    key=value log) into a list of normalized event dicts with transforms applied.
    """
    cfg = config or {}
    parser_mode = str(cfg.get("parser") or "auto").lower()
    regex_pattern = cfg.get("regex_pattern") or (DEFAULT_LOG_REGEX if parser_mode == "regex" else None)

    records: list[dict[str, Any]] = []

    if isinstance(raw_input, dict):
        records = [raw_input]
    elif isinstance(raw_input, list):
        for item in raw_input:
            if isinstance(item, dict):
                records.append(item)
            elif isinstance(item, str):
                parsed = _parse_single_line(item, parser_mode, regex_pattern)
                if parsed:
                    records.append(parsed)
            else:
                records.append({"value": item})
    elif isinstance(raw_input, (bytes, bytearray)):
        raw_text = raw_input.decode("utf-8", errors="replace")
        return parse_raw_payload(raw_text, cfg)
    elif isinstance(raw_input, str):
        text = raw_input.strip()
        if not text:
            return []

        # First attempt whole-string JSON (handles pretty-printed JSON objects or arrays)
        if parser_mode in ("auto", "json"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    records = [parsed]
                elif isinstance(parsed, list):
                    records = [x if isinstance(x, dict) else {"value": x} for x in parsed]
                else:
                    records = [{"value": parsed}]
            except json.JSONDecodeError:
                if parser_mode == "json":
                    raise ValueError("Invalid JSON input. Switch parser to 'auto', 'ndjson', 'regex', or 'key_value' for non-JSON logs.")

        if not records:
            for line in text.splitlines():
                if not line.strip():
                    continue
                parsed_line = _parse_single_line(line, parser_mode, regex_pattern)
                if parsed_line:
                    records.append(parsed_line)
    else:
        records = [{"value": raw_input}]

    return [apply_transforms(rec, cfg) for rec in records]


def _value_type_name(val: Any) -> str:
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, list):
        return "array"
    if isinstance(val, dict):
        return "object"
    return "string"


def extract_fields(sample: Any, prefix: str = "") -> list[dict[str, Any]]:
    """
    Recursively discover dot-notation field paths, types, and example values
    from any arbitrary JSON event schema.
    """
    fields: list[dict[str, Any]] = []
    if not isinstance(sample, dict):
        return fields

    for key, val in sample.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(val, dict) and val:
            fields.extend(extract_fields(val, path))
        else:
            fields.append({
                "path": path,
                "type": _value_type_name(val),
                "example": val,
            })
    return fields
