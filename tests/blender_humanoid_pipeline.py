"""Actual engine-registry integration: automatic loop before export."""

import argparse, importlib, sys
from pathlib import Path
from types import SimpleNamespace
import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]


def module(name):
    return importlib.import_module(ROOT.name + "." + name)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--extension-root", type=Path)
    p.add_argument("--site-packages", type=Path)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=False)
    if a.site_packages:
        sys.path.insert(0, str(a.site_packages.resolve()))
    else:
        sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
    from meshvenn_humanoid.integration import Binding
    from meshvenn_humanoid.blender.supervisor import SubprocessSupervisor
    from meshvenn_humanoid.blender.probes import evaluated_positions

    importlib.import_module(ROOT.name).register()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(a.source.resolve()), disable_bone_shape=True)
    mesh = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    old_rig = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
    points = evaluated_positions(mesh)
    mesh.parent = None
    for modifier in list(mesh.modifiers):
        mesh.modifiers.remove(modifier)
    mesh.vertex_groups.clear()
    mesh.matrix_world = Matrix.Identity(4)
    for vertex, point in zip(mesh.data.vertices, points):
        vertex.co = point
    mesh.data.update()
    bpy.data.objects.remove(old_rig, do_unlink=True)
    geometry_api = module("core.geometry_contracts")
    papi = module("core.pipeline_contracts")
    geometry = geometry_api.GeometrySurfaceOutput(
        mesh,
        SimpleNamespace(),
        geometry_api.GeometryProjectionSpace(1, 1, 1),
        "static-test-source",
    )
    context = papi.PipelineContext(scene=bpy.context.scene)
    context.set_output(papi.PipelineStage.GEOMETRY, geometry)
    registry = module("core.pipeline_registry").PIPELINE_REGISTRY
    original = registry.require("canonical-biped-v2")
    extension = None
    if a.extension_root:
        a.extension_root = a.extension_root.resolve()
        sys.path.insert(0, str(a.extension_root.parent))
        extension = importlib.import_module(a.extension_root.name)
        extension.register()
        assert bpy.context.scene.meshvenn_humanoid.enabled
        bpy.context.scene.meshvenn_humanoid.workspace = str(a.output / "loop")
        supervisor = extension.registration.supervisor
    else:
        supervisor = SubprocessSupervisor(ROOT, a.output / "loop", max_seconds=60)

    def check_scene(ctx, rig):
        objects = set(bpy.data.objects)
        scenes = set(bpy.data.scenes)
        file = bpy.data.filepath
        counts = {
            name: len(getattr(bpy.data, name))
            for name in ("meshes", "armatures", "materials", "images")
        }
        result = supervisor(ctx, rig)
        assert (
            set(bpy.data.objects) == objects
            and set(bpy.data.scenes) == scenes
            and bpy.data.filepath == file
        )
        assert counts == {name: len(getattr(bpy.data, name)) for name in counts}
        return result

    if extension:
        binding = extension.registration._binding
        assert binding is not None
        binding.wrapper.supervisor = check_scene
    else:
        binding = Binding(registry, check_scene)
    try:
        result = registry.require("canonical-biped-v2").execute(context)
        assert result.success, result.message
        assert result.metadata["humanoid_quality"]["status"] == "checks_passed"
        assert result.payload.blender_object is mesh
        assert [tuple(v.co) for v in mesh.data.vertices] == list(points)
        context.set_output(papi.PipelineStage.RIG, result.payload)
        context.metadata.update(
            export_output_path=str(a.output / "automatic.glb"),
            export_overwrite_existing=False,
            export_validate_roundtrip=True,
        )
        exported = (
            module("implementations.glb_export")
            .GLBExportImplementation()
            .execute(context)
        )
        assert exported.success, exported.message
        assert exported.metadata["roundtrip"]["passed"]
    finally:
        if extension:
            extension.unregister()
        else:
            binding.close()
    assert registry.require("canonical-biped-v2") is original
    if extension:
        assert not hasattr(bpy.types.Scene, "meshvenn_humanoid")
    print(
        "HUMANOID_PIPELINE_AUTOMATIC: scene preserved, loop passed, downstream export passed"
    )


if __name__ == "__main__":
    main()
