from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


# =========================================================
# Discovery
# =========================================================

def discover_sheets(
    example_dir: Path,
    requested: list[str] | None,
) -> list[Path]:
    sheets_dir = (
        example_dir
        / "sheets"
    )

    if not sheets_dir.is_dir():
        raise FileNotFoundError(
            (
                "Missing sheets directory: "
                f"{sheets_dir}"
            )
        )

    available = sorted(
        sheets_dir.glob(
            "sheet*.png"
        )
    )

    if not available:
        raise RuntimeError(
            (
                "No sheet*.png found in "
                f"{sheets_dir}"
            )
        )

    if not requested:
        return available

    wanted = {
        (
            Path(name).stem
            .strip()
            .lower()
        )
        for name
        in requested
        if str(name).strip()
    }

    selected = [
        path
        for path
        in available
        if (
            path.stem.lower()
            in wanted
        )
    ]

    discovered_names = {
        path.stem.lower()
        for path
        in selected
    }

    missing = sorted(
        wanted
        - discovered_names
    )

    if missing:
        raise ValueError(
            (
                "Requested sheets not found: "
                + ", ".join(
                    missing
                )
            )
        )

    return selected


# =========================================================
# JSON
# =========================================================

def json_safe(
    value: Any,
) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        Path,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): json_safe(
                item
            )
            for (
                key,
                item,
            )
            in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            json_safe(
                item
            )
            for item
            in value
        ]

    return str(
        value
    )


def write_json(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            json_safe(
                value
            ),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
