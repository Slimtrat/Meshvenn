"""Matched source/LOD PBR and silhouette renders using directly skinned normals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender import source
from scripts.author_stytch_cloth import api
from scripts.cloth_lod import write_json
from scripts.cloth_replay_math import AXES, lbs

POLICY = {
    "min_silhouette_iou": 0.98,
    "max_interior_linear_rgb_rmse": 0.04,
    "resolution": 512,
    "samples": 32,
    "scope": "Four matched producer views; finite silhouette/material fidelity, not anatomical, pixel-identical consumer or human visual acceptance",
}


def rendered_pixels(path):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        values = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(values)
        return values.reshape(image.size[1], image.size[0], 4)
    finally:
        bpy.data.images.remove(image)


def render_asset(path, output):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path), disable_bone_shape=True)
    material = next(
        o.data.materials[0] for o in bpy.context.scene.objects if o.type == "MESH"
    )
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    reader = api("implementations.glb_export.modular_gltf")
    document, binary = reader.read_glb(path)
    names = [document["nodes"][i]["name"] for i in document["skins"][0]["joints"]]
    frames = source.glb_frames(path)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = POLICY["samples"]
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = POLICY["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("Matched neutral world")
    scene.world.color = (0.04, 0.04, 0.04)
    for location, energy, size in (
        ((-3, -4, 5), 350, 3),
        ((3, -2, 3), 90, 3),
        ((0, 3, 4), 260, 2),
    ):
        data = bpy.data.lights.new("Matched area", "AREA")
        data.energy, data.size = energy, size
        light = bpy.data.objects.new("Matched area", data)
        scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (
            (Vector((0, 0, 1)) - light.location).to_track_quat("-Z", "Y").to_euler()
        )
    data = bpy.data.cameras.new("Matched camera")
    camera = bpy.data.objects.new("Matched camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    data.type = "ORTHO"
    result = {}
    for label, location, target, scale in (
        ("front", (0.5, -4, 1.12), (0, 0, 0.98), 2.15),
        ("back", (-0.5, 4, 1.12), (0, 0, 0.98), 2.15),
        ("side", (4, -0.5, 1.12), (0, 0, 0.98), 2.15),
        ("elbow90", (0.447, -4, 1.36), (0.447, 0, 1.30), 0.90),
    ):
        palette = np.tile(np.identity(4), (18, 1, 1))
        if label == "elbow90":
            pivot = Vector(frames["forearm.L"][i][3] for i in range(3))
            delta = (
                Matrix.Translation(pivot)
                @ Matrix.Rotation(np.pi / 2, 4, Vector((0, 0, -1)))
                @ Matrix.Translation(-pivot)
            )
            for name in ("forearm.L", "hand.L"):
                palette[names.index(name)] = np.array(delta)
        objects = []
        for item in document["meshes"]:
            for primitive in item["primitives"]:
                attributes = {
                    k: np.array(reader.read_accessor(document, binary, v))
                    for k, v in primitive["attributes"].items()
                }
                triangles = np.array(
                    reader.read_accessor(document, binary, primitive["indices"])
                ).reshape(-1, 3)
                points, normals = lbs(
                    palette,
                    attributes["POSITION"],
                    attributes["NORMAL"],
                    attributes["JOINTS_0"].astype(int),
                    attributes["WEIGHTS_0"],
                )
                points = (AXES[:3, :3].T @ points.T).T
                normals = (AXES[:3, :3].T @ normals.T).T
                mesh = bpy.data.meshes.new("Exact GLB render")
                mesh.from_pydata(points.tolist(), [], triangles.tolist())
                mesh.update()
                uv = mesh.uv_layers.new(name="UVMap")
                for loop in mesh.loops:
                    value = attributes["TEXCOORD_0"][loop.vertex_index]
                    uv.data[loop.index].uv = (value[0], 1 - value[1])
                for face in mesh.polygons:
                    face.use_smooth = True
                mesh.normals_split_custom_set_from_vertices(normals.tolist())
                mesh.materials.append(material)
                obj = bpy.data.objects.new("Exact GLB render", mesh)
                scene.collection.objects.link(obj)
                objects.append(obj)
        camera.location = location
        camera.rotation_euler = (
            (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        )
        data.ortho_scale = scale
        frame = output / (label + ".png")
        scene.render.filepath = str(frame)
        bpy.ops.render.render(write_still=True)
        result[label] = rendered_pixels(frame)
        for obj in objects:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("reference", "candidate", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args(
        argv if argv is not None else sys.argv[sys.argv.index("--") + 1 :]
    )
    output = args.output.resolve()
    output.mkdir(exist_ok=False, parents=True)
    write_json(output / "budget.json", POLICY)
    results = []
    for name in ("reference", "candidate"):
        folder = output / name
        folder.mkdir()
        results.append(render_asset(getattr(args, name).resolve(strict=True), folder))
    report = {
        "policy": POLICY,
        "reference_sha256": source.digest(args.reference),
        "candidate_sha256": source.digest(args.candidate),
        "views": [],
        "passed": False,
        "skin_normals": "Direct blended basis, not recomputed posed geometric normals",
        "private_consumer_images_used": False,
        "visual_acceptance": False,
    }
    for label in results[0]:
        a, b = results[0][label], results[1][label]
        left, right = a[:, :, 3] > 0.5, b[:, :, 3] > 0.5
        iou = float(np.sum(left & right) / np.sum(left | right))
        interior = (a[:, :, 3] > 0.99) & (b[:, :, 3] > 0.99)
        for axis in (0, 1):
            interior &= np.roll(left & right, 1, axis) & np.roll(left & right, -1, axis)
        rmse = float(
            np.sqrt(np.mean((a[:, :, :3][interior] - b[:, :, :3][interior]) ** 2))
        )
        passed = (
            iou >= POLICY["min_silhouette_iou"]
            and rmse <= POLICY["max_interior_linear_rgb_rmse"]
        )
        report["views"].append(
            {
                "view": label,
                "silhouette_iou": iou,
                "interior_linear_rgb_rmse": rmse,
                "passed": passed,
            }
        )
    report["passed"] = all(r["passed"] for r in report["views"])
    write_json(output / "renders.json", report)
    if not report["passed"]:
        raise ValueError(
            "Matched cloth LOD render fidelity failed; views/measurements retained"
        )


if __name__ == "__main__":
    main()
