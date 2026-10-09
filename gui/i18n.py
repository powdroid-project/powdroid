"""Minimal translation helper backed by gui/languages/<code>.json."""

import json
from pathlib import Path

LANGUAGES_DIR = Path(__file__).resolve().parent / "languages"
_fallback = {}
_strings = {}


def _load(code):
    try:
        return json.loads((LANGUAGES_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_language(code):
    global _strings, _fallback
    _fallback = _load("en")
    _strings = _load(code) if code != "en" else _fallback


def _lookup(table, key):
    value = table
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value if isinstance(value, str) else None


def t(key, **kwargs):
    """Translate a dotted key, falling back to English, then to the key itself."""
    if not _fallback:
        set_language("en")
    text = _lookup(_strings, key) or _lookup(_fallback, key) or key
    return text.format(**kwargs) if kwargs else text
