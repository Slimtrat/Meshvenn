"""Read unambiguous JSON authoring data; duplicate keys are never last-wins."""

from __future__ import annotations

import json


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Ambiguous modular JSON: duplicate key {key!r}.")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"Non-finite JSON constant is not supported: {value}.")


def strict_json_loads(value):
    return json.loads(value, object_pairs_hook=_object, parse_constant=_constant)
