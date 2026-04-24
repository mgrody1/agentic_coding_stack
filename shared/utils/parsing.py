"""Helpers for robust model content parsing."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_model_json_content(content: Any) -> dict[str, Any]:
    """Parse model content that may be dict, JSON string, or fenced JSON."""
    if isinstance(content, dict):
        return content

    if not isinstance(content, str):
        return {}

    stripped = content.strip()
    if not stripped:
        return {}

    direct = _try_json_load(stripped)
    if isinstance(direct, dict):
        return direct

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        fenced = _try_json_load(fence_match.group(1).strip())
        if isinstance(fenced, dict):
            return fenced

    return {}


def _try_json_load(payload: str) -> Any:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None
