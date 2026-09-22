from __future__ import annotations

import unittest
from pathlib import Path

import core.sdf as sdf
import core.sdf_surface as sdf_surface


class SDFArchitectureTests(unittest.TestCase):
    def test_core_sdf_packages_do_not_import_blender(self) -> None:
        core = Path(__file__).parents[1] / "core"
        sources = sorted((core / "sdf").glob("*.py"))
        surface = core / "sdf_surface"
        sources.extend(sorted(surface.glob("*.py")) if surface.is_dir() else [surface.with_suffix(".py")])
        for source in sources:
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("import bpy", text, source)
            self.assertNotIn("from bpy", text, source)

    def test_sdf_facade_exposes_legacy_public_api(self) -> None:
        expected = {
            "DEFAULT_ISO_LEVEL", "DEFAULT_REFERENCE_MAX_VOXELS", "DEFAULT_SMOOTHNESS",
            "DEFAULT_SURFACE_OFFSET", "DEFAULT_SYMMETRY_X", "SDFBuildConfig",
            "SDFBuildProgress", "SDFBuildResult", "SDFBuildStats", "SDFProjection",
            "SDFVolume", "SIGN_EPSILON", "SignedDistanceMask", "build_sdf_from_views",
            "build_sdf_projections", "build_sdf_volume", "build_signed_distance_mask",
            "cubic_sdf_config", "fuse_signed_distances", "sample_fused_sdf", "smooth_max",
        }
        self.assertEqual(expected, set(sdf.__all__))
        for name in expected:
            self.assertTrue(hasattr(sdf, name), name)

    def test_sdf_surface_facade_exposes_legacy_public_api(self) -> None:
        expected = {
            "CUBE_CORNERS", "CUBE_EDGES", "DEFAULT_GENERATE_NORMALS",
            "DEFAULT_GRADIENT_STEP_SCALE", "EPSILON", "SDFSurfaceConfig",
            "SDFSurfaceMesh", "SDFSurfaceResult", "SDFSurfaceStats",
            "SDFSurfaceVertex", "estimate_sdf_normal", "extract_surface_nets",
        }
        self.assertEqual(expected, set(sdf_surface.__all__))
        for name in expected:
            self.assertTrue(hasattr(sdf_surface, name), name)
