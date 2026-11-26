"""Actual portable PBR maps, repeat application, rollback and registry boundary."""

import argparse, importlib, json, sys, struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy

ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser()
p.add_argument("--package-root", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
a.package_root = a.package_root.resolve()
a.output = a.output.resolve()
a.output.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(a.package_root.parent))
extension = importlib.import_module(a.package_root.name)
extension.register()
from meshvenn_cloth.authoring import apply_cloth
from meshvenn_cloth.config import ClothConfig

assert not hasattr(bpy.context.scene, "bpt_settings")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12)
mesh = bpy.context.object
mesh.name = "Cloth acceptance sphere"
material = bpy.data.materials.new("Baked source")
material.use_nodes = True
shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
base = bpy.data.images.new("Original color", width=4, height=4)
base.pixels[:] = [0.8, 0.65, 0.4, 1.0] * 16
image_node = material.node_tree.nodes.new("ShaderNodeTexImage")
image_node.image = base
material.node_tree.links.new(image_node.outputs["Color"], shader.inputs["Base Color"])
mesh.data.materials.append(material)
positions = [tuple(v.co) for v in mesh.data.vertices]
uv = [tuple(x.uv) for x in mesh.data.uv_layers.active.data]
pixels = tuple(base.pixels[:])
old_engine = bpy.context.scene.render.engine
original_nodes = set(material.node_tree.nodes)
first = apply_cloth(mesh, ClothConfig(texture_size=64))
assert first["base_color"] is base and tuple(base.pixels[:]) == pixels
assert (
    mesh.data.materials[0] is first["material"]
    and set(material.node_tree.nodes) == original_nodes
)
second = apply_cloth(mesh, ClothConfig(texture_size=128))
assert (
    len([n for n in second["material"].node_tree.nodes if n.type == "TEX_IMAGE"]) == 3
)
assert [tuple(v.co) for v in mesh.data.vertices] == positions
assert [tuple(x.uv) for x in mesh.data.uv_layers.active.data] == uv
assert (
    bpy.context.scene.render.engine == old_engine and bpy.context.active_object is mesh
)
before = (mesh.data.materials[0], set(bpy.data.materials), set(bpy.data.images))
with patch(
    "meshvenn_cloth.authoring._run_bake",
    side_effect=RuntimeError("Injected bake failure"),
):
    try:
        apply_cloth(mesh, ClothConfig(texture_size=64))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Failed bake was accepted")
assert before == (mesh.data.materials[0], set(bpy.data.materials), set(bpy.data.images))
assert (
    bpy.context.scene.render.engine == old_engine and bpy.context.active_object is mesh
)
# The standalone extension has not imported the engine. Connect explicitly now.
sys.path.insert(0, str(ROOT.parent))
engine = importlib.import_module(ROOT.name)
engine.register()
extension.registration.connect()
registry = importlib.import_module(
    ROOT.name + ".core.pipeline_registry"
).PIPELINE_REGISTRY
assert registry.require("cloth-uv-bake-v1").descriptor.identifier == "cloth-uv-bake-v1"
assert registry.require("uv-bake-v2") is extension.registration._implementation.original
g = importlib.import_module(ROOT.name + ".core.geometry_contracts")
pipeline = importlib.import_module(ROOT.name + ".core.pipeline_contracts")
view_api = importlib.import_module(ROOT.name + ".core.projected_material")
view = view_api.ProjectedMaterialView.from_blender_image(
    name="front", image=base, azimuth_degrees=0, elevation_degrees=0
)
geometry = g.GeometrySurfaceOutput(
    mesh,
    SimpleNamespace(material_views=(view,)),
    g.GeometryProjectionSpace(2, 2, 2),
    "cloth-smoke-source",
)
context = pipeline.PipelineContext(scene=bpy.context.scene)
context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
context.settings = SimpleNamespace(
    uv_bake_texture_size=64, uv_bake_reuse_existing_uv=True
)
bpy.context.scene.meshvenn_cloth.texture_size = "256"
finished = registry.require("cloth-uv-bake-v1").execute(context)
assert finished.success, finished.message
assert finished.payload.material is mesh.data.materials[0]
assert (
    finished.metadata["cloth"]["detail_authority"]
    == "Authored, not observed source coverage"
)
assert finished.metrics["texture_size"] == 64
assert [tuple(v.co) for v in mesh.data.vertices] == positions and [
    tuple(x.uv) for x in mesh.data.uv_layers.active.data
] == uv
context.metadata.update(
    export_output_path=str(a.output / "cloth.glb"),
    export_overwrite_existing=False,
    export_validate_roundtrip=True,
)
exported = (
    importlib.import_module(ROOT.name + ".implementations.glb_export")
    .GLBExportImplementation()
    .execute(context)
)
assert exported.success, exported.message
data = (a.output / "cloth.glb").read_bytes()
length = struct.unpack_from("<I", data, 12)[0]
document = json.loads(data[20 : 20 + length])
portable = document["materials"][0]
assert (
    "normalTexture" in portable
    and "metallicRoughnessTexture" in portable["pbrMetallicRoughness"]
)
assert len(document["images"]) == 3


def image_for(socket):
    found = set()

    def visit(node):
        if node.type == "TEX_IMAGE":
            found.add(node.image)
            return
        for value in node.inputs:
            for link in value.links:
                visit(link.from_node)

    for link in socket.links:
        visit(link.from_node)
    assert len(found) == 1
    return found.pop()


source_shader = next(
    n for n in mesh.data.materials[0].node_tree.nodes if n.type == "BSDF_PRINCIPLED"
)
expected_maps = {
    name: tuple(image_for(source_shader.inputs[name]).pixels[:])
    for name in ("Normal", "Roughness")
}
known = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(a.output / "cloth.glb"), disable_bone_shape=True)
imported = next(o for o in set(bpy.data.objects) - known if o.type == "MESH")
shader = next(
    n for n in imported.data.materials[0].node_tree.nodes if n.type == "BSDF_PRINCIPLED"
)
for name, expected in expected_maps.items():
    actual = tuple(image_for(shader.inputs[name]).pixels[:])
    assert (
        len(actual) == len(expected)
        and max(abs(x - y) for x, y in zip(actual, expected)) <= 1.0 / 255
    ), (name + " transport changed")
normal = second["normal"]
rough = second["roughness"]
assert (
    normal.colorspace_settings.name == "Non-Color"
    and rough.colorspace_settings.name == "Non-Color"
)
assert (
    max(normal.pixels[::4]) - min(normal.pixels[::4]) > 0.01
), "Normal map lost its woven detail"
assert all(
    abs(v) < 1e-6 for v in rough.pixels[2::4]
), "Metallic B channel must stay zero"
assert 0.6 < max(rough.pixels[1::4]) <= 1.0, "Fabric roughness was not baked"
extension.unregister()
assert (
    registry.get("cloth-uv-bake-v1") is None and registry.get("uv-bake-v2") is not None
)
assert not hasattr(bpy.types.Scene, "meshvenn_cloth")
(a.output / "smoke.json").write_text(
    json.dumps(
        dict(
            portable_maps=3,
            roundtrip=exported.metadata["roundtrip"],
            source_color_preserved=True,
            source_mesh_uv_preserved=True,
            reapply=True,
            rollback=True,
            optional_registry=True,
        ),
        indent=2,
    )
    + "\n"
)
print(
    "CLOTH_SMOKE: portable maps, exact color/UV/mesh, reapply, rollback and registry passed"
)
