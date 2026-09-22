from __future__ import annotations

from .shared import BLEND_MODE, MATERIAL_MODE, RunLogger, VISIBILITY_MODE
from .cli import parse_args
from .pipeline import process_sheet

def main() -> None:
    args = parse_args()

    example_dir = (
        args
        .example_dir
        .resolve()
    )

    output_dir = (
        args
        .output_dir
        .resolve()
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

    sheets = sorted(
        sheets_dir.glob(
            "sheet*.png"
        )
    )

    if not sheets:
        raise RuntimeError(
            (
                "No sheet*.png found in "
                f"{sheets_dir}"
            )
        )

    generated_root = (
        output_dir
        / "generated"
    )

    generated_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = RunLogger(
        jsonl_path=(
            generated_root
            / "native_run.jsonl"
            if args.json_log
            else None
        )
    )

    logger.divider(
        "NATIVE C++ EXAMPLE GENERATION"
    )

    logger.info(
        "Mesh mode",
        value=(
            args.mesh_mode
        ),
    )

    logger.info(
        "Material mode",
        value=(
            MATERIAL_MODE
        ),
    )

    logger.info(
        "Material visibility",
        value=(
            VISIBILITY_MODE
        ),
    )

    logger.info(
        "Material blend",
        value=(
            BLEND_MODE
        ),
    )

    for index, sheet_path in enumerate(
        sheets,
        start=1,
    ):
        logger.progress(
            index,
            len(
                sheets
            ),
            sheet_path.name,
        )

        process_sheet(
            sheet_path,
            generated_root,
            args,
            logger=(
                logger.child()
            ),
        )

    logger.success(
        "native generation finished",
        elapsed=(
            logger.total_elapsed()
        ),
    )
