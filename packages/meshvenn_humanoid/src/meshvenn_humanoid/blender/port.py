"""Trusted Blender host; edits only disposable copies and measures exact exports."""

import importlib, json, math, shutil
from pathlib import Path
from types import SimpleNamespace
import bpy
from meshvenn_humanoid import Asset, Assessment
from meshvenn_humanoid.skinning import Segment, localize_arms
from . import source
from .evaluation import make_regions, measure
from .probes import evaluated_positions
from ..observations import surface_observations
from ..correspondence import match_surface
from mathutils import Vector


class BlenderHumanoidPort:
    def __init__(self, engine_module, source_path, workspace, *, object_name=None):
        self.module = engine_module
        self.input = Path(source_path).resolve()
        self.workspace = Path(workspace).resolve()
        self.name = object_name
        self.regions = None
        self.reference = None
        if self.input.is_relative_to(self.workspace):
            raise ValueError("Keep the immutable source outside loop output")

    def api(self, name):
        return importlib.import_module(self.module + "." + name)

    def source_digest(self):
        return source.digest(self.input)

    def detect(self):
        mesh, rig = source.load(self.input, self.name)
        return source.detect(mesh, rig, self.api("core.native_pose_probe").PARENTS)

    def verify(self, asset):
        if source.digest(self.workspace / asset.id / "character.glb") != asset.sha256:
            raise ValueError("Candidate bytes changed")

    def baseline(self, *, cancel=None):
        return self.regenerate("baseline", "preserve", cancel=cancel)

    def regenerate(self, identifier, recipe, *, cancel=None):
        folder = self.workspace / identifier
        receipt = folder / "receipt.json"
        if receipt.exists():
            data = json.loads(receipt.read_text())
            if (
                data["source_sha256"] != self.source_digest()
                or data["recipe"] != recipe
            ):
                raise ValueError("Stale generation receipt")
            asset = Asset(identifier, data["glb_sha256"])
            self.verify(asset)
            return asset
        if folder.exists():
            raise ValueError("Incomplete candidate retained; do not overwrite it")
        if cancel and cancel():
            raise InterruptedError("Cancelled before regeneration")
        folder.mkdir(parents=True)
        mesh, rig = source.load(self.input, self.name)
        before = source.snapshot(mesh, rig)
        old = source.weights(mesh)
        evidence = {}
        if recipe.startswith("local-") or recipe == "radial-200":
            fraction = {"local-018": 0.18, "local-028": 0.28, "radial-200": 0.18}[
                recipe
            ]
            to_mesh = mesh.matrix_world.inverted() @ rig.matrix_world
            bones = {
                b.name: Segment(
                    tuple(to_mesh @ b.head_local), tuple(to_mesh @ b.tail_local)
                )
                for b in rig.data.bones
            }
            new, evidence = localize_arms(
                [tuple(v.co) for v in mesh.data.vertices],
                old,
                bones,
                blend_fraction=fraction,
                radial_expansion=2.0 if recipe == "radial-200" else 0.0,
                bend_axis=tuple(
                    mesh.matrix_world.to_3x3().inverted() @ Vector((0, 1, 0))
                ),
            )
            source.apply_weights(mesh, new)
        elif recipe == "bone-heat":
            for m in list(mesh.modifiers):
                mesh.modifiers.remove(m)
            mesh.vertex_groups.clear()
            bpy.ops.object.select_all(action="DESELECT")
            mesh.select_set(True)
            rig.select_set(True)
            bpy.context.view_layer.objects.active = rig
            bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)
        elif recipe != "preserve":
            raise ValueError("Unknown humanoid regeneration recipe")
        rows = source.weights(mesh)
        invalid = sum(
            not row
            or len(row) > 4
            or not math.isclose(sum(row.values()), 1.0, abs_tol=1e-5)
            or any(not math.isfinite(v) or v <= 0 for v in row.values())
            for row in rows
        )
        if invalid:
            raise ValueError(f"Candidate has {invalid} invalid skin rows")
        changed = int(before != source.snapshot(mesh, rig))
        if changed:
            raise ValueError("Regeneration changed mesh, UVs or native rest frames")
        if evidence:
            mesh["meshvenn_humanoid_refinement"] = json.dumps(evidence, sort_keys=True)
            mesh["meshvenn_rig_skinning_algorithm"] = evidence["algorithm"]
        p = self.api("core.pipeline_contracts")
        g = self.api("core.geometry_contracts")
        r = self.api("core.rig_contracts")
        calibrated = mesh.get("meshvenn_projection_convention") == "surface-envelope-v1"
        if calibrated:
            space = g.GeometryProjectionSpace(
                mesh["meshvenn_projection_width"],
                mesh["meshvenn_projection_depth"],
                mesh["meshvenn_projection_height"],
                mesh["meshvenn_projection_voxel_size"],
                mesh["meshvenn_projection_center_xy"],
            )
        else:
            # Export consumes world transforms, not projection coordinates.
            # This required contract field has no camera authority; no image
            # projection stage is run or exposed for this GLB-only source.
            space = g.GeometryProjectionSpace(1, 1, 1)
        geometry = g.GeometrySurfaceOutput(
            mesh,
            SimpleNamespace(material_views=None),
            space,
            "humanoid-preserved-surface",
            metadata={
                "projection_frame_status": (
                    "saved-source-frame" if calibrated else "unavailable-export-only"
                )
            },
        )
        context = p.PipelineContext(scene=bpy.context.scene)
        context.set_output(p.PipelineStage.GEOMETRY, geometry)
        context.set_output(
            p.PipelineStage.RIG,
            r.RigOutput(
                geometry,
                mesh,
                rig,
                "canonical-biped-v2",
                {b.name: b.name for b in rig.data.bones},
                "humanoid-quality-loop",
            ),
        )
        path = folder / "character.glb"
        context.metadata.update(
            export_output_path=str(path),
            export_overwrite_existing=False,
            export_validate_roundtrip=True,
        )
        if recipe == "preserve" and self.input.suffix.lower() == ".glb":
            shutil.copyfile(self.input, path)
            roundtrip = dict(
                passed=True,
                scope="Exact byte-preserving GLB baseline, with structural/import checks; no re-export",
            )
        else:
            exported = (
                self.api("implementations.glb_export")
                .GLBExportImplementation()
                .execute(context)
            )
            if not exported.success:
                raise RuntimeError(exported.message)
            roundtrip = exported.metadata["roundtrip"]
        bpy.ops.wm.save_as_mainfile(
            filepath=str(folder / "source.blend"), compress=True
        )
        asset = Asset(identifier, source.digest(path))
        data = dict(
            source_sha256=self.source_digest(),
            recipe=recipe,
            glb_sha256=asset.sha256,
            source_structure_changes=changed,
            invalid_weights=invalid,
            refinement=evidence,
            export_roundtrip=roundtrip,
        )
        receipt.write_text(json.dumps(data, indent=2) + "\n")
        return asset

    def evaluate(self, asset, *, cancel=None):
        self.verify(asset)
        base = self.baseline(cancel=cancel)
        if self.reference is None:
            mesh, rig = source.load(self.workspace / base.id / "character.glb")
            self.reference = evaluated_positions(mesh)
            self.regions = make_regions(mesh, rig, self.reference)
            mesh.data.calc_loop_triangles()
            self.triangles = [tuple(t.vertices) for t in mesh.data.loop_triangles]
            self.frames = source.glb_frames(self.workspace / base.id / "character.glb")
        mesh, rig = source.load(self.workspace / asset.id / "character.glb")
        points = evaluated_positions(mesh)
        mesh.data.calc_loop_triangles()
        mapping = match_surface(
            self.reference,
            points,
            self.triangles,
            [tuple(t.vertices) for t in mesh.data.loop_triangles],
            source.weights(mesh),
        )
        error = max(math.dist(a, points[i]) for a, i in zip(self.reference, mapping))
        matrix_error = source.frame_error(
            self.frames, source.glb_frames(self.workspace / asset.id / "character.glb")
        )
        if self.input.suffix.lower() == ".glb":
            matrix_error = max(
                matrix_error,
                source.frame_error(source.glb_frames(self.input), self.frames),
            )
        values, evidence = measure(
            mesh,
            rig,
            self.regions,
            mapping=mapping,
            triangles=self.triangles,
            cancel=cancel,
        )
        receipt = json.loads((self.workspace / asset.id / "receipt.json").read_text())
        values.update(
            source_structure_changes=receipt["source_structure_changes"],
            invalid_weights=receipt["invalid_weights"],
            export_failures=0.0 if receipt["export_roundtrip"]["passed"] else 1.0,
            rest_position_error=max(error, matrix_error),
            appearance_transport_changes=int(
                source.appearance_signature(self.workspace / base.id / "character.glb")
                != source.appearance_signature(
                    self.workspace / asset.id / "character.glb"
                )
            ),
        )
        mesh.data.calc_loop_triangles()
        evidence["surface"] = surface_observations(
            points, [list(t.vertices) for t in mesh.data.loop_triangles]
        )
        evidence["appearance"] = {
            k: (
                list(mesh[k])
                if not isinstance(mesh[k], (str, int, float, bool))
                else mesh[k]
            )
            for k in mesh.keys()
            if k.startswith("meshvenn_uv_bake")
        }
        evidence["appearance"].update(
            transport=source.appearance_signature(
                self.workspace / asset.id / "character.glb"
            ),
            identity_status="unknown",
            camera_calibration="not established by this rig loop",
        )
        evidence["native_rest_matrix_error"] = matrix_error
        evidence["source_pose_scope"] = (
            "Static native source; global visual quality and consumer acceptance remain unknown"
        )
        result = Assessment(asset, values, evidence)
        (self.workspace / asset.id / "assessment.json").write_text(
            json.dumps(result.to_dict(), indent=2) + "\n"
        )
        self.verify(asset)
        return result
