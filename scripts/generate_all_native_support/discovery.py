from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------
# Discovery
# ---------------------------------------------------------

def discover_examples(
    examples_root: Path,
    requested_example: str,
) -> list[Path]:
    examples_root = (
        examples_root.resolve()
    )

    if not examples_root.exists():
        raise FileNotFoundError(
            (
                "Examples root does not exist: "
                f"{examples_root}"
            )
        )

    if requested_example != "all":
        example_dir = (
            examples_root
            / requested_example
        ).resolve()

        try:
            example_dir.relative_to(
                examples_root
            )

        except ValueError as exc:
            raise ValueError(
                (
                    "Requested example must be "
                    "inside the examples root."
                )
            ) from exc

        _validate_example_dir(
            example_dir
        )

        return [
            example_dir
        ]

    result = [
        sheets_dir.parent
        for sheets_dir
        in examples_root.rglob(
            "sheets"
        )
        if (
            sheets_dir.is_dir()
            and any(
                sheets_dir.glob(
                    "sheet*.png"
                )
            )
        )
    ]

    return sorted(
        result
    )


def _validate_example_dir(
    example_dir: Path,
) -> None:
    if not example_dir.exists():
        raise FileNotFoundError(
            (
                "Example does not exist: "
                f"{example_dir}"
            )
        )

    sheets_dir = (
        example_dir
        / "sheets"
    )

    if not sheets_dir.exists():
        raise FileNotFoundError(
            (
                "Missing sheets directory: "
                f"{sheets_dir}"
            )
        )

    if not any(
        sheets_dir.glob(
            "sheet*.png"
        )
    ):
        raise RuntimeError(
            (
                "No sheet*.png found in "
                f"{sheets_dir}"
            )
        )


def discover_sheets(
    example_dirs: list[Path],
) -> list[
    tuple[
        Path,
        Path,
    ]
]:
    sheets: list[
        tuple[
            Path,
            Path,
        ]
    ] = []

    for example_dir in example_dirs:
        for sheet_path in sorted(
            (
                example_dir
                / "sheets"
            ).glob(
                "sheet*.png"
            )
        ):
            sheets.append(
                (
                    example_dir,
                    sheet_path,
                )
            )

    return sheets


def filter_from_sheet(
    sheets: list[
        tuple[
            Path,
            Path,
        ]
    ],
    *,
    examples_root: Path,
    start_sheet: str,
) -> list[
    tuple[
        Path,
        Path,
    ]
]:
    if not start_sheet:
        return sheets

    normalized = (
        start_sheet
        .replace(
            "\\",
            "/",
        )
        .strip()
    )

    matches: list[int] = []

    for index, (
        _example_dir,
        sheet_path,
    ) in enumerate(
        sheets
    ):
        relative = (
            sheet_path
            .relative_to(
                examples_root
            )
            .as_posix()
        )

        if (
            relative == normalized
            or sheet_path.name
            == normalized
        ):
            matches.append(
                index
            )

    if not matches:
        available = "\n".join(
            (
                "  - "
                + sheet_path
                .relative_to(
                    examples_root
                )
                .as_posix()
            )
            for _, sheet_path
            in sheets
        )

        raise ValueError(
            (
                f'Could not find start sheet '
                f'"{start_sheet}".\n'
                f"Available sheets:\n"
                f"{available}"
            )
        )

    if len(matches) > 1:
        ambiguous = "\n".join(
            (
                "  - "
                + sheets[index][1]
                .relative_to(
                    examples_root
                )
                .as_posix()
            )
            for index in matches
        )

        raise ValueError(
            (
                f'Sheet "{start_sheet}" '
                "is ambiguous.\n"
                "Use a path relative to example/:\n"
                f"{ambiguous}"
            )
        )

    return sheets[
        matches[0]:
    ]
