"""Render actual baseline/selected GLBs with identical cameras and lighting."""

import argparse, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender.source import digest, load
from meshvenn_humanoid.blender.probes import rotated_bone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    args.session = args.session.resolve()
    args.output = args.output.resolve()
    state = json.loads((args.session / "session.json").read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    if state["status"] != "checks_passed":
        raise ValueError("No passing result to compare")
    renders = []
    for label, asset in (
        ("baseline", state["baseline"]["asset"]),
        ("selected", state["selected"]),
    ):
        path = (args.session / asset["id"] / "character.glb").resolve()
        if digest(path) != asset["sha256"]:
            raise ValueError("Comparison asset changed")
        mesh, rig = load(path)
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 24
        scene.cycles.use_denoising = True
        scene.render.resolution_x = scene.render.resolution_y = 640
        scene.render.resolution_percentage = 100
        scene.world = bpy.data.worlds.new("World")
        scene.world.color = (0.1, 0.1, 0.1)
        scene.view_settings.view_transform = "Standard"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        for name, pos in (("key", (3, -4, 5)), ("fill", (-3, -2, 3))):
            light = bpy.data.lights.new(name, "AREA")
            light.energy = 350
            light.size = 3
            obj = bpy.data.objects.new(name, light)
            scene.collection.objects.link(obj)
            obj.location = pos
        data = bpy.data.cameras.new("Camera")
        camera = bpy.data.objects.new("Camera", data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        data.type = "ORTHO"
        elbow = rig.matrix_world @ rig.data.bones["forearm.L"].head_local
        for angle in (45, 90):
            with rotated_bone(rig, "forearm.L", angle, (0, 1, 0), world_space=True):
                for azimuth in (0, 45):
                    target = elbow + Vector((-0.04, 0, -0.14))
                    data.ortho_scale = 0.85
                    camera.location = target + Vector(
                        (
                            4 * math.sin(math.radians(azimuth)),
                            -4 * math.cos(math.radians(azimuth)),
                            0,
                        )
                    )
                    camera.rotation_euler = (
                        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
                    )
                    name = f"{label}-elbow-{angle}-view-{azimuth}.png"
                    scene.render.filepath = str(args.output / name)
                    bpy.ops.render.render(write_still=True)
                    renders.append(
                        dict(path=name, asset=asset, degrees=angle, azimuth=azimuth)
                    )
    (args.output / "renders.json").write_text(
        json.dumps(
            dict(
                scope="Exact GLB reload, linear blend skinning; no render-only corrections",
                renders=renders,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
