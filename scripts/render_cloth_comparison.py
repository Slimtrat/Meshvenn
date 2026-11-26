"""Matched cameras and lighting on exact GLB reloads, including an elbow pose."""

import argparse, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender.source import load, digest
from meshvenn_humanoid.blender.probes import evaluated_positions, rotated_bone
from meshvenn_humanoid.correspondence import PointIndex


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("baseline", "cloth", "output"):
        p.add_argument("--" + n, type=Path, required=True)
    p.add_argument("--color", type=Path, help="Optional resolution-only comparison")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    inputs = {
        n: getattr(a, n).resolve(strict=True)
        for n in ("baseline", "color", "cloth")
        if getattr(a, n) is not None
    }
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=False)
    reference = None
    rows = []
    for name, path in inputs.items():
        mesh, rig = load(path)
        points = evaluated_positions(mesh)
        if reference is None:
            reference = points
        else:
            target = PointIndex(points)
            source = PointIndex(reference)
            error = max(
                max(math.dist(p, points[target.nearest(p)[0]]) for p in reference),
                max(math.dist(p, reference[source.nearest(p)[0]]) for p in points),
            )
            if error > 2e-5:
                raise ValueError("Material comparison changed source surface")
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 48
        scene.cycles.use_denoising = True
        scene.render.resolution_x = scene.render.resolution_y = 720
        scene.render.resolution_percentage = 100
        scene.world = bpy.data.worlds.new("World")
        scene.world.color = (0.065, 0.065, 0.065)
        scene.view_settings.view_transform = "Standard"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        for label, position, energy, size in (
            ("key", (-3, -4, 5), 420, 2.5),
            ("fill", (3, -1, 2), 90, 3),
            ("rim", (0, 3, 4), 400, 2),
        ):
            data = bpy.data.lights.new(label, "AREA")
            data.energy = energy
            data.size = size
            light = bpy.data.objects.new(label, data)
            scene.collection.objects.link(light)
            light.location = position
            light.rotation_euler = (
                (Vector((0, 0, 1)) - light.location).to_track_quat("-Z", "Y").to_euler()
            )
        data = bpy.data.cameras.new("Camera")
        camera = bpy.data.objects.new("Camera", data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        data.type = "ORTHO"
        height = max(p[2] for p in points) - min(p[2] for p in points)
        frames = []
        for shot, target, scale, azimuth in (
            ("full", Vector((0, 0, height * 0.5)), height * 1.16, 12),
            (
                "face",
                rig.matrix_world @ rig.data.bones["head"].head_local
                + Vector((0, 0, height * 0.085)),
                height * 0.37,
                12,
            ),
            ("cloth", Vector((height * 0.08, 0, height * 0.57)), height * 0.30, 5),
        ):
            camera.location = target + Vector(
                (
                    4 * math.sin(math.radians(azimuth)),
                    -4 * math.cos(math.radians(azimuth)),
                    0.15,
                )
            )
            camera.rotation_euler = (
                (target - camera.location).to_track_quat("-Z", "Y").to_euler()
            )
            data.ortho_scale = scale
            filename = f"{name}-{shot}.png"
            scene.render.filepath = str(a.output / filename)
            bpy.ops.render.render(write_still=True)
            frames.append(filename)
        with rotated_bone(rig, "forearm.L", 90, (0, 1, 0), world_space=True):
            target = rig.matrix_world @ rig.data.bones["forearm.L"].head_local + Vector(
                (-0.04, 0, -0.14)
            )
            camera.location = target + Vector((0, -4, 0))
            camera.rotation_euler = (
                (target - camera.location).to_track_quat("-Z", "Y").to_euler()
            )
            data.ortho_scale = 0.85
            filename = f"{name}-elbow.png"
            scene.render.filepath = str(a.output / filename)
            bpy.ops.render.render(write_still=True)
            frames.append(filename)
        rows.append(dict(id=name, sha256=digest(path), frames=frames))
    (a.output / "renders.json").write_text(
        json.dumps(
            dict(
                scope="Exact GLB reloads, identical cameras and lights; no image retouching",
                cases=rows,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
