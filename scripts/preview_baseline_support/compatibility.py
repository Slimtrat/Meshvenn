from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import BaselineConfig, CompatibilityResult, DEFAULT_OUTPUTS, SCHEMA_VERSION
from .manifest import sha256_file

def check_compatibility(
    manifest: dict[str, Any],
    *,
    sheet_name: str,
    source_path: Path,
    profile: str,
    expected_config: BaselineConfig,
) -> CompatibilityResult:
    expected_config.validate()

    if (
        manifest.get(
            "schema_version"
        )
        != SCHEMA_VERSION
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                "schema-version-mismatch"
            ),
        )

    configuration = (
        manifest.get(
            "configuration"
        )
    )

    if not isinstance(
        configuration,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                "missing-configuration"
            ),
        )

    expected = (
        expected_config.to_dict()
    )

    for (
        key,
        expected_value,
    ) in expected.items():
        actual_value = (
            configuration.get(
                key
            )
        )

        if (
            actual_value
            != expected_value
        ):
            return CompatibilityResult(
                compatible=False,
                reason=(
                    "configuration-mismatch:"
                    f"{key}:"
                    f"{actual_value}"
                    "!="
                    f"{expected_value}"
                ),
            )

    profiles = (
        manifest.get(
            "profiles"
        )
    )

    if (
        not isinstance(
            profiles,
            list,
        )
        or profile
        not in profiles
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                f"profile-missing:{profile}"
            ),
        )

    sheets = (
        manifest.get(
            "sheets"
        )
    )

    if not isinstance(
        sheets,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason="missing-sheets",
        )

    sheet = sheets.get(
        sheet_name
    )

    if not isinstance(
        sheet,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                f"sheet-missing:{sheet_name}"
            ),
        )

    if not source_path.is_file():
        return CompatibilityResult(
            compatible=False,
            reason=(
                "source-sheet-missing:"
                f"{source_path}"
            ),
        )

    expected_source_hash = (
        sheet.get(
            "source_sha256"
        )
    )

    current_source_hash = (
        sha256_file(
            source_path
        )
    )

    if (
        expected_source_hash
        != current_source_hash
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                "source-hash-mismatch"
            ),
        )

    outputs = (
        manifest.get(
            "outputs"
        )
    )

    if not isinstance(
        outputs,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason="missing-outputs",
        )

    for (
        output_name,
        expected_filename,
    ) in DEFAULT_OUTPUTS.items():
        if (
            outputs.get(
                output_name
            )
            != expected_filename
        ):
            return CompatibilityResult(
                compatible=False,
                reason=(
                    "output-layout-mismatch:"
                    f"{output_name}"
                ),
            )

    return CompatibilityResult(
        compatible=True,
        reason="compatible",
    )


# ---------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------
