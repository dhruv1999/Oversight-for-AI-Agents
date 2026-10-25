from __future__ import annotations

import json
from typing import Any


def get(obj: Any, *names: str, default: Any = None) -> Any:
    """First present value among several attribute or key names (frameworks differ in spelling)."""
    for n in names:
        if isinstance(obj, dict):
            if obj.get(n) is not None:
                return obj[n]
        elif getattr(obj, n, None) is not None:
            return getattr(obj, n)
    return default


def as_args(value: Any) -> dict[str, Any]:
    """Tool arguments as a dict, whether they arrive as a dict or a JSON string."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {"input": value}
        return parsed if isinstance(parsed, dict) else {"input": parsed}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {"input": value}


def as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json()
    try:
        return json.dumps(value)
    except TypeError:
        return str(value)
