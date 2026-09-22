"""Run with Blender --background --python tests/blender_material_comparison_render_smoke.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import bpy

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.render_material_comparison import build_comparison_matrix


def _tile(path: Path, color: tuple[float, float, float, float]) -> None:
    image = bpy.data.images.new(
        name=path.stem,
        width=2,
        height=2,
        alpha=True,
    )
    try:
        image.pixels.foreach_set(list(color) * 4)
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="meshvenn-material-render-") as root:
        output = Path(root)
        red = output / "red.png"
        blue = output / "blue.png"
        matrix = output / "matrix.png"
        _tile(red, (1.0, 0.0, 0.0, 1.0))
        _tile(blue, (0.0, 0.0, 1.0, 1.0))

        layout = build_comparison_matrix(
            {("L2", "red"): red, ("L2", "blue"): blue},
            profiles=["L2"],
            implementations=["red", "blue"],
            output_path=matrix,
            gutter=1,
        )
        assert matrix.is_file()
        assert layout["width"] == 5
        assert layout["height"] == 2
        assert [cell["present"] for cell in layout["cells"]] == [True, True]

        image = bpy.data.images.load(str(matrix), check_existing=False)
        try:
            image.update()
            assert tuple(image.size) == (5, 2)
            assert image.pixels[0] > 0.9
            assert image.pixels[(4 * 4) + 2] > 0.9
        finally:
            bpy.data.images.remove(image)

    print("material comparison render smoke OK")


if __name__ == "__main__":
    main()
