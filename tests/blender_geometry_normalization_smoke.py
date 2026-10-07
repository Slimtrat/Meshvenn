"""Normalization compatibility boundary and fail-closed publication preflight."""
import argparse
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import bpy


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=root)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    sys.path.insert(0, str(args.package_root.resolve().parent))
    package = importlib.import_module(args.package_root.name)
    package.register()
    try:
        api = importlib.import_module(f"{package.__name__}.implementations.glb_export.modular_source")
        planning = importlib.import_module(f"{package.__name__}.implementations.glb_export.planning")
        contracts = importlib.import_module(f"{package.__name__}.core.geometry_contracts")
        pipeline = importlib.import_module(f"{package.__name__}.core.pipeline_contracts")
        bpy.ops.wm.open_mainfile(filepath=str(root / "example/v2/modular/StytchDoll/source.blend"), use_scripts=False)
        mesh = bpy.data.objects["MeshvennScan"]
        before = dict(mesh.items())
        context = api.context_from_authored_scene(bpy.context.scene,
            output_path=str(root / "tmp/normalization-preflight-unused.glb"))
        geometry = context.require_output(pipeline.PipelineStage.GEOMETRY)
        rig = context.require_output(pipeline.PipelineStage.RIG)
        normalization = geometry.normalization
        assert normalization.provenance == "historical-native-id-properties"
        assert normalization.scale == mesh["meshvenn_normalization_scale"]
        assert not any(k in geometry.metadata for k in ("normalized_height", "target_height", "normalization_scale"))
        assert dict(mesh.items()) == before  # Conversion is in memory, not a migration write.

        def rejected(call):
            try:
                call()
            except (TypeError, ValueError):
                return
            raise AssertionError("Ambiguous normalization was accepted.")

        # Old metadata/metrics cannot rescue a missing explicit contract.
        stale = SimpleNamespace(normalization=None,
            metadata={"normalized_height": True, "target_height": normalization.target_height},
            metrics={"normalization_scale": normalization.scale})
        rejected(lambda: planning._modular_spec(context, geometry.blender_objects, rig, stale))
        for key in ("bpt_normalize_height", "bpt_target_height", "meshvenn_normalization_scale"):
            saved = mesh[key]
            del mesh[key]
            rejected(lambda: api._normalization(mesh))
            mesh[key] = saved
        # New producers persist the explicit contract; historical claims may
        # corroborate it but cannot override contradictory values.
        explicit = contracts.GeometryNormalization(True, normalization.target_height,
            normalization.scale, "native-visual-hull-object-scale")
        mesh["meshvenn_geometry_normalization"] = json.dumps(explicit.to_dict())
        assert api._normalization(mesh) == explicit
        for key, bad in (("bpt_normalize_height", False), ("bpt_target_height", 9),
                         ("meshvenn_normalization_scale", float("nan"))):
            saved = mesh[key]
            mesh[key] = bad
            rejected(lambda: api._normalization(mesh))
            mesh[key] = saved
        # A modern source needs no fallback properties at all.
        legacy = {k: mesh[k] for k in ("bpt_normalize_height", "bpt_target_height", "meshvenn_normalization_scale")}
        for key in legacy:
            del mesh[key]
        assert api._normalization(mesh) == explicit
        for key, value in legacy.items():
            mesh[key] = value
        del mesh["meshvenn_geometry_normalization"]
        assert dict(mesh.items()) == before
        assert api._normalization(mesh) == normalization
        rejected(lambda: replace(geometry, normalization={"scale": 1}))
        native = importlib.import_module(f"{package.__name__}.implementations.native_visual_hull.output")
        producer = importlib.import_module(f"{package.__name__}.implementations.native_visual_hull.blender_output")
        config_api = importlib.import_module(f"{package.__name__}.implementations.native_visual_hull.config")
        volume = SimpleNamespace(width=64, depth=64, height=64, occupied_count=1)
        surface = SimpleNamespace(vertex_count=7128, polygon_count=7126, index_count=42756)
        views = SimpleNamespace(projection_count=2)
        space = contracts.GeometryProjectionSpace(64, 64, 64, 1., True)
        arguments = dict(blender_object=mesh, volume=volume, native_mesh=surface, source=views,
            resolution=64, symmetry_x=False, thread_count=0, mesh_mode="surface_nets",
            normalized_height=True, target_height=normalization.target_height,
            normalization_scale=normalization.scale, projection_space=space)
        generated = native.NativeVisualHullOutput(**arguments)
        assert generated.normalization == explicit
        assert generated.normalized_height is generated.normalization.normalized_height
        assert generated.target_height == generated.normalization.target_height
        assert generated.normalization_scale == generated.normalization.scale
        rejected(lambda: native.NativeVisualHullOutput(**{**arguments, "normalized_height": 1}))
        rejected(lambda: native.NativeVisualHullOutput(**arguments, metrics={"normalization_scale": 9}))
        clone = mesh.copy()
        try:
            producer._write_geometry_metadata(clone, source=views, volume=volume, native_mesh=surface,
                projection_space=space, config=config_api.NativeVisualHullConfig(
                    64, False, 0, "surface_nets", 1., True, True, normalization.target_height),
                normalization_scale=normalization.scale)
            assert api._normalization(clone) == explicit
            assert "meshvenn_geometry_normalization" in clone
        finally:
            bpy.data.objects.remove(clone)
        print("Normalization PASS: explicit authority, read-only historical conversion, contradictory/missing provenance rejected.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
