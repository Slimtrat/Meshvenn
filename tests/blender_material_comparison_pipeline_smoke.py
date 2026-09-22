"""Minimal end-to-end material comparison render without native geometry."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import bpy

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.render_material_comparison import process_sheet


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="meshvenn-material-pipeline-") as root:
        comparison_root = Path(root)
        variant = comparison_root / "sheet1" / "L2" / "projected-color-v1.2"
        variant.mkdir(parents=True)

        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.object
        material = bpy.data.materials.new("SmokeMaterial")
        material.diffuse_color = (0.8, 0.2, 0.1, 1.0)
        material.use_nodes = True
        cube.data.materials.append(material)
        bpy.ops.export_scene.gltf(
            filepath=str(variant / "model.glb"),
            export_format="GLB",
            use_selection=True,
        )
        (variant / "variant.json").write_text(
            json.dumps(
                {
                    "geometry": {
                        "vertices": len(cube.data.vertices),
                        "faces": len(cube.data.polygons),
                        "dimensions": list(cube.dimensions),
                    }
                }
            ),
            encoding="utf-8",
        )

        args = argparse.Namespace(
            views=4,
            size=128,
            samples=1,
            keep_stills=False,
            reuse_renders=False,
            continue_on_error=False,
            gutter=1,
        )
        result = process_sheet(
            comparison_root,
            sheet="sheet1",
            profiles=["L2"],
            implementations=["projected-color-v1.2"],
            args=args,
        )
        assert result["success"]
        assert (comparison_root / "sheet1" / "material_comparison.png").is_file()
        assert (comparison_root / "sheet1" / "render_comparison.json").is_file()
        assert result["matrix"]["cells"][0]["present"]

    print("material comparison pipeline smoke OK")


if __name__ == "__main__":
    main()
