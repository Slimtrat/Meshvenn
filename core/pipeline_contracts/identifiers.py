from __future__ import annotations

import re

IMPLEMENTATION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_implementation_id(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("Implementation id cannot be empty.")
    if not IMPLEMENTATION_ID_PATTERN.fullmatch(normalized):
        raise ValueError("Implementation id must contain only lowercase letters, digits, '.', '_' or '-'.")
    return normalized
