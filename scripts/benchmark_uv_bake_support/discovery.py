from __future__ import annotations

from .shared import Path

def discover_sheets(
    example_dir: Path,
    names: list[str],
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

    results = []

    for name in names:
        stem = (
            Path(
                name
            )
            .stem
        )

        path = (
            sheets_dir
            / f"{stem}.png"
        )

        if not path.is_file():
            raise FileNotFoundError(
                (
                    "Missing benchmark sheet: "
                    f"{path}"
                )
            )

        results.append(
            path
        )

    return results
