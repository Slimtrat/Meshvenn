import importlib, sys, unittest, math
from pathlib import Path
from types import SimpleNamespace as NS
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from meshvenn_cloth.config import ClothConfig
from meshvenn_cloth.regions import coherent_head_views


@dataclass(frozen=True)
class Mask:
    width: int
    height: int
    values: bytes


@dataclass(frozen=True)
class View:
    name: str
    image: object
    transform: object
    mask: object = None


class PolicyTests(unittest.TestCase):
    def test_import_has_no_engine_or_blender_dependency_and_parameters_are_bounded(
        self,
    ):
        self.assertNotIn("bpy", sys.modules)
        for kw in (
            {"texture_size": 1000},
            {"relief": math.nan},
            {"thread_spacing": 0},
            {"roughness": -0.1},
        ):
            with self.assertRaises(ValueError):
                ClothConfig(**kw)

    def fixture(self):
        group = NS(index=0)
        mesh = NS(
            vertex_groups={"head": group},
            data=NS(
                vertices=[
                    NS(co=NS(z=1.6), groups=[NS(group=0, weight=1.0)])
                    for _ in range(16)
                ]
            ),
        )
        image = NS(
            width=9,
            height=21,
            sample_bilinear_alpha_aware=lambda u, v: (
                (0.05, 0.04, 0.03, 1.0)
                if abs(u - 0.5) < 0.02 and abs(v - 0.9) < 0.02
                else (0.7, 0.6, 0.5, 1.0)
            ),
        )
        views = [
            View(str(a), image, NS(azimuth_degrees=a, elevation_degrees=0))
            for a in (0, 90, 180, 270)
        ]
        return mesh, views, NS(height=128, voxel_size=2 / 128)

    def test_only_side_head_samples_are_excluded_and_original_inputs_are_immutable(
        self,
    ):
        mesh, views, space = self.fixture()
        masked, report = coherent_head_views(mesh, views, space, Mask)
        self.assertIs(masked[0], views[0])
        self.assertIs(masked[2], views[2])
        self.assertIsNone(views[1].mask)
        self.assertEqual(masked[1].mask.values[:144], bytes([1]) * 144)
        self.assertEqual(masked[1].mask.values[18 * 9 + 4], 0)
        self.assertEqual(masked[1].mask.values[18 * 9], 1)
        self.assertEqual(report["allowed_head_views"], ["0", "180"])

    def test_policy_intersects_an_existing_mask_without_filling_rejected_pixels(self):
        mesh, views, space = self.fixture()
        views[1] = View(
            "90", views[1].image, views[1].transform, Mask(9, 21, bytes(189))
        )
        masked, _ = coherent_head_views(mesh, views, space, Mask)
        self.assertEqual(masked[1].mask.values, bytes(189))

    def test_unsupported_head_or_cameras_fail_explicitly(self):
        mesh, views, space = self.fixture()
        views[0].transform.elevation_degrees = 30
        with self.assertRaises(ValueError):
            coherent_head_views(mesh, views, space, Mask)
        mesh.vertex_groups = {}
        with self.assertRaises(ValueError):
            coherent_head_views(mesh, views, space, Mask)
