"""Compatibility entrypoint for the preview-baseline contract suite.

The test classes live in preview_baseline_cases; importing them here preserves
the existing unittest module name and avoids duplicate discovery.
"""
from __future__ import annotations

import unittest

from tests.preview_baseline_cases.config_and_hash import BaselineConfigTests, HashTests
from tests.preview_baseline_cases.manifest import ManifestGenerationTests, ManifestPersistenceTests
from tests.preview_baseline_cases.compatibility import CompatibilityTests
from tests.preview_baseline_cases.cli import CliTests

if __name__ == "__main__":
    unittest.main()
