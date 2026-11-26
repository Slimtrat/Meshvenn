"""Scene-preserving subprocess supervision and transactional weight application."""

from pathlib import Path
import json, os, subprocess, uuid
import bpy
from ..models import Asset, Assessment
from . import source
from .snapshot import write_snapshot


class SubprocessSupervisor:
    def __init__(self, engine_root, workspace, *, max_seconds=60.0, enabled=None):
        self.engine_root = Path(engine_root).resolve()
        self.workspace = Path(workspace).resolve()
        self.max_seconds = max_seconds
        self.enabled = enabled

    def __call__(self, context, rig_output):
        if self.enabled and not self.enabled(context):
            return dict(status="disabled")
        mesh, rig = rig_output.blender_object, rig_output.armature_object
        before = source.snapshot(mesh, rig)
        old = source.weights(mesh)
        folder = self.workspace / uuid.uuid4().hex
        folder.mkdir(parents=True)
        input_path = folder / "input.blend"
        run = folder / "run"
        objects = {mesh, rig}
        for obj in tuple(objects):
            parent = obj.parent
            while parent:
                objects.add(parent)
                parent = parent.parent
        write_snapshot(input_path, mesh, objects)
        worker = Path(__file__).with_name("worker.py")
        command = [
            bpy.app.binary_path,
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            str(worker),
            "--",
            "--engine-root",
            str(self.engine_root),
            "--source",
            str(input_path),
            "--output",
            str(run),
            "--object",
            mesh.name,
            "--max-seconds",
            str(self.max_seconds),
        ]
        with (folder / "worker.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=self.max_seconds + 30,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except subprocess.TimeoutExpired:
                return dict(
                    status="budget_exhausted", report_path=str(folder / "worker.log")
                )
        path = run / "session.json"
        if not path.exists():
            return dict(status="failed", report_path=str(folder / "worker.log"))
        state = json.loads(path.read_text())
        state["report_path"] = str(path)
        if result.returncode or state["status"] != "checks_passed":
            return state
        asset = Asset(**state["selected"])
        assessment = Assessment(
            asset, state["best"]["measurements"], state["best"]["evidence"]
        )
        if not assessment.passed:
            raise ValueError("Worker selection does not pass the frozen profile")
        if source.digest(run / asset.id / "character.glb") != asset.sha256:
            raise ValueError("Selected GLB changed")
        if source.snapshot(mesh, rig) != before or source.weights(mesh) != old:
            raise ValueError("Scene source changed during analysis")
        known = {
            n: set(getattr(bpy.data, n))
            for n in (
                "objects",
                "meshes",
                "armatures",
                "materials",
                "node_groups",
                "images",
            )
        }
        try:
            with bpy.data.libraries.load(str(run / asset.id / "source.blend")) as (
                available,
                loaded,
            ):
                if mesh.name not in available.objects:
                    raise ValueError("Selected source object missing")
                loaded.objects = [mesh.name]
            staged = loaded.objects[0]
            staged_rig = next(
                m.object for m in staged.modifiers if m.type == "ARMATURE"
            )
            staged_snapshot = source.snapshot(staged, staged_rig)
            if staged_snapshot != before:
                raise ValueError(
                    "Selected source changed native geometry, UVs or rest frames"
                )
            rows = source.weights(staged)
            try:
                source.apply_weights(mesh, rows)
            except BaseException:
                source.apply_weights(mesh, old)
                raise
            receipt = json.loads((run / asset.id / "receipt.json").read_text())
            mesh["meshvenn_humanoid_quality"] = json.dumps(
                {
                    k: state[k]
                    for k in (
                        "profile",
                        "status",
                        "selected",
                        "source_sha256",
                        "policy_sha256",
                    )
                }
            )
            mesh["meshvenn_rig_skinning_algorithm"] = receipt["refinement"].get(
                "algorithm",
                mesh.get("meshvenn_rig_skinning_algorithm", "preserved-native-skin"),
            )
        finally:
            for obj in set(bpy.data.objects) - known["objects"]:
                bpy.data.objects.remove(obj, do_unlink=True)
            for name in ("meshes", "armatures", "materials", "node_groups", "images"):
                collection = getattr(bpy.data, name)
                for value in set(collection) - known[name]:
                    value.use_fake_user = False
                    if value.users == 0:
                        collection.remove(value)
        bpy.context.view_layer.update()
        return state
