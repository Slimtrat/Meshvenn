"""The sticky must not turn stale/missing/failed data into a green product score."""
from __future__ import annotations

import copy
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from scripts.v2_preview_evidence import IMAGE_NAMES, build_comment, digest, read_json, verified_evidence

ROOT = Path(__file__).resolve().parents[1]
SHA = "1" * 40


def png(value):
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 128, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + bytes((value, value, value)) * 128) * 128)) + chunk(b"IEND", b""))


def report(directory):
    manifest = read_json(ROOT / "example/v2/modular/UAL1/manifest.json")
    manifest["material"].update(surface_samples=1000, fallback_samples=100, selected_source_samples=1700)
    names = ("000", "045", "090", "135", "180", "225", "270", "315", "TOP", "BOT")
    # Unit-test data only: the actual Blender/CI fixture must generate its own measured color gates.
    manifest.update(geometry_input_mode="neutral-silhouette", material_input_mode="source-color-projection",
        appearance={"passed": True, "render_mode": "base-color-emission", "projection_convention": "native-normalized",
                    "source_sha256": manifest["source_sha256"], "texture_size": 512, "samples_per_axis": 2,
                    "surface_samples": 1000, "fallback_ratio": .1, "neutral_fallback_ratio": .001,
                    "atlas_storage": "srgb-byte-from-scene-linear", "color_transport": {
                        "passed": True, "tolerance": .004, "source_linear_rgb": [.25, .5, .75],
                        "max_linear_error": .003, "source_projection_linear_rgb": [.25, .5, .75],
                        "baked_shader_linear_rgb": [.25, .5, .75], "reimported_shader_linear_rgb": [.25, .503, .75]},
                    "sampling_diagnostics": {"total_samples": 10000, "candidate_samples": 9000,
                        "source_rejected_samples": 1000, "visible_samples": 7000, "occluded_samples": 2000,
                        "front_facing_samples": 6500, "backface_samples": 500, "grazing_rejected_samples": 50,
                        "primary_samples": 900, "projected_fallback_samples": 99, "neutral_fallback_samples": 1,
                        "selected_samples": 1700},
                    "atlas_signal": {"chromatic_fraction": .95, "white_fraction": .001},
                    "source_view_signals": [{"name": name, "chromatic_fraction": .95} for name in names],
                    "views": [{"name": name, "sha256": "3" * 64, "width": 256, "height": 256,
                               "alpha_occupied_pixels": 1000} for name in names]})
    for index, name in enumerate(IMAGE_NAMES):
        (directory / name).write_bytes(png(index * 30))
    refinement = {"algorithm": "contour-taubin-v2", "topology_preserved": True, "face_orientation_preserved": True,
                  "roughness_before_in_voxels": .1, "roughness_after_in_voxels": .07,
                  "mean_contour_residual_before_in_voxels": .3, "mean_contour_residual_after_in_voxels": .1,
                  "contour_residual_sample_count": 100, "contour_residual_valid_samples_before": 100,
                  "contour_residual_valid_samples_after": 99}
    reconstruction = [{"source_asset": name, "resolution": 128, "surface_refinement": "organic", "refinement": refinement,
        "silhouette": {"mean_iou": .93, "valid_input_views": 10, "total_views": 10,
                       "per_view_iou": {str(index): .9 for index in range(10)}},
        "surface_3d": {"surface_fscore": .99, "max_extent_error": .01},
        "landmarks": {"mean_error_in_heights": .02, "max_error_in_heights": .03},
        "connectivity": {"component_count": 1}, "skin_weights": {"weighted_fraction": 1}}
        for name in ("quaternius_human", "quaternius_ual1")]
    return {"schema_version": 1, "source_sha": SHA, "run_id": "10", "run_attempt": "1",
            "rendered_from_final_glb": True, "source_reference_sha256": "2" * 64,
            "images": {name: digest(directory / name) for name in IMAGE_NAMES}, "modular": manifest,
            "pose": {"clip_name": "Meshvenn_Walk_Loop.001", "frame": 6., "maximum_deformation_m": .5,
                     "maximum_socket_motion_m": .1, "hidden_region_id": "left-arm"}, "reconstruction": reconstruction}


class PreviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.report = report(self.directory)
        self.save()

    def tearDown(self):
        self.temporary.cleanup()

    def save(self):
        (self.directory / "preview.json").write_text(json.dumps(self.report), "utf-8")

    def verify(self):
        return verified_evidence(self.directory, SHA, "10", "1")

    def test_current_provenance_and_read_only_summary(self):
        result = self.verify()
        body = build_comment(sha=SHA, run_url="https://example.test/run", status="success", evidence=result,
                             artifact_url="https://example.test/artifact")
        self.assertIn("Canonical V2", body)
        self.assertIn("UV Bake V2", body)
        self.assertIn("0.9300", body)
        self.assertNotIn("![", body)
        self.assertNotIn("Preuve V2 indisponible", body)
        self.assertIn("Godot/Stytch", body)

    def test_failed_job_never_displays_preexisting_success(self):
        body = build_comment(sha=SHA, run_url="https://example.test/run", status="failure", evidence=self.report,
                             image_root="https://example.test/old")
        self.assertIn("Aucun succès", body)
        self.assertNotIn("![", body)
        self.assertNotIn("PASS", body)

    def test_missing_or_stale_identity(self):
        for key, value in (("source_sha", "0" * 40), ("run_id", "9"), ("run_attempt", "2"),
                           ("rendered_from_final_glb", False)):
            with self.subTest(key=key):
                original = self.report[key]
                self.report[key] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.verify()
                self.report[key] = original

    def test_missing_corrupted_or_giant_png(self):
        target = self.directory / "pose.png"
        for value in (b"not a png", png(23)[:16] + struct.pack(">II", 100000, 128) + png(23)[24:]):
            target.write_bytes(value)
            self.report["images"][target.name] = digest(target)
            self.save()
            with self.assertRaises(ValueError):
                self.verify()
        target.unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_no_boolean_or_nonfinite_fidelity_and_no_markdown_captions(self):
        cases = [lambda data: data["modular"]["roundtrip"].update(max_raw_normal_error=True),
                 lambda data: data["modular"]["roundtrip"].update(max_rest_error=.01),
                 lambda data: data["modular"].update(sha256="`forged`") ,
                 lambda data: data["pose"].update(clip_name="ok\n![forged](x)"),
                 lambda data: data["pose"].update(hidden_region_id="another-region"),
                 lambda data: data["pose"].update(maximum_deformation_m=0)]
        original = copy.deepcopy(self.report)
        for mutate in cases:
            self.report = copy.deepcopy(original)
            mutate(self.report)
            self.save()
            with self.assertRaises(ValueError):
                self.verify()

    def test_reconstruction_gate_is_rechecked_not_taken_on_faith(self):
        self.report["reconstruction"][0]["silhouette"]["mean_iou"] = .6
        self.save()
        with self.assertRaises(ValueError):
            self.verify()
        self.report["reconstruction"][0]["silhouette"]["mean_iou"] = .93
        self.report["reconstruction"][0]["refinement"]["mean_contour_residual_after_in_voxels"] = .29
        self.save()
        with self.assertRaises(AssertionError):
            self.verify()

    def test_color_transport_has_its_own_measured_gates(self):
        for key, value in (("neutral_fallback_ratio", .02), ("render_mode", "neutral"),
                           ("samples_per_axis", 1), ("source_sha256", "4" * 64)):
            original = self.report["modular"]["appearance"][key]
            self.report["modular"]["appearance"][key] = value
            self.save()
            with self.assertRaises(ValueError):
                self.verify()
            self.report["modular"]["appearance"][key] = original
        self.report["modular"]["appearance"]["sampling_diagnostics"]["neutral_fallback_samples"] = 2
        self.save()
        with self.assertRaises(ValueError):
            self.verify()
        self.report["modular"].pop("appearance")
        self.save()
        with self.assertRaises(KeyError):
            self.verify()

    def test_double_gamma_or_unmeasured_linear_codec_is_not_certified(self):
        transport = self.report["modular"]["appearance"]["color_transport"]
        transport["reimported_shader_linear_rgb"] = [.05, .21, .46]
        self.save()
        with self.assertRaises(ValueError):
            self.verify()
        transport["reimported_shader_linear_rgb"] = [.25, .503, .75]
        self.report["modular"]["appearance"]["atlas_storage"] = "linear-in-srgb-byte-image"
        self.save()
        with self.assertRaises(ValueError):
            self.verify()

    def test_duplicate_json_fields_and_nonfinite_values_fail_closed(self):
        for text in ('{"passed":false,"passed":true}', '{"value":NaN}'):
            (self.directory / "preview.json").write_text(text, "utf-8")
            with self.assertRaises(ValueError):
                self.verify()


if __name__ == "__main__":
    unittest.main()
