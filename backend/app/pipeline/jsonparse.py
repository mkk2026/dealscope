"""Tolerant JSON extraction from model replies.

Models wrap output in ```json fences, prose, or trailing commentary. These pull
the first well-formed array/object out of the noise. Return None on failure —
callers decide the fallback.
"""

import json
import re


def _strip_fences(text: str) -> str:
    return re.sub(r"```(?:json)?", "", text or "")


def extract_json_array(text: str) -> list | None:
    cleaned = _strip_fences(text)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


def extract_json_object(text: str) -> dict | None:
    cleaned = _strip_fences(text)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
