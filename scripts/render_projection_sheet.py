from __future__ import annotations

import argparse
import math
import shutil
import sys

from array import array
from pathlib import Path

import bpy

from mathutils import Vector


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.presheet_layout import (
    CELL_SPECS,
    pixel_bbox,
)


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1:
        ]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Render a generated GLB back into "
            "a Projection Tool reference sheet."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Generated GLB to render.",
    )

    parser.add_argument(
        "--template",
        required=True,
        type=Path,
        help=(
            "Original Projection Tool sheet. "
            "Its layout and annotations are preserved."
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Generated Projection Tool PNG.",
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--material-mode",
        choices=(
            "neutral",
            "original",
        ),
        default="neutral",
        help=(
            "neutral replaces materials with a "
            "uniform geometry material; original "
            "keeps GLB materials."
        ),
    )

    parser.add_argument(
        "--framing",
        type=float,
        default=1.15,
        help=(
            "Common orthographic framing multiplier "
            "used for every view."
        ),
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Cleanup
# ---------------------------------------------------------

def clear_scene() -> None:
    for obj in tuple(
        bpy.data.objects
    ):
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )

    for mesh in tuple(
        bpy.data.meshes
    ):
        if mesh.users == 0:
            bpy.data.meshes.remove(
                mesh
            )

    for camera in tuple(
        bpy.data.cameras
    ):
        if camera.users == 0:
            bpy.data.cameras.remove(
                camera
            )

    for light in tuple(
        bpy.data.lights
    ):
        if light.users == 0:
            bpy.data.lights.remove(
                light
            )


# ---------------------------------------------------------
# GLB import
# ---------------------------------------------------------

def import_glb(
    path: Path,
) -> list[
    bpy.types.Object
]:
    path = path.resolve()

    if not path.exists():
        raise FileNotFoundError(
            (
                "Missing GLB: "
                f"{path}"
            )
        )

    before = set(
        bpy.data.objects
    )

    bpy.ops.import_scene.gltf(
        filepath=str(
            path
        )
    )

    imported = [
        obj
        for obj in bpy.data.objects
        if obj not in before
    ]

    meshes = [
        obj
        for obj in imported
        if obj.type == "MESH"
    ]

    if not meshes:
        raise RuntimeError(
            "Imported GLB contains no mesh."
        )

    return meshes


# ---------------------------------------------------------
# Bounds
# ---------------------------------------------------------

def combined_bounds(
    objects: list[
        bpy.types.Object
    ],
) -> tuple[
    Vector,
    Vector,
]:
    min_corner = Vector(
        (
            float("inf"),
            float("inf"),
            float("inf"),
        )
    )

    max_corner = Vector(
        (
            float("-inf"),
            float("-inf"),
            float("-inf"),
        )
    )

    for obj in objects:
        matrix = (
            obj.matrix_world
        )

        for corner in obj.bound_box:
            point = (
                matrix
                @ Vector(
                    corner
                )
            )

            min_corner.x = min(
                min_corner.x,
                point.x,
            )

            min_corner.y = min(
                min_corner.y,
                point.y,
            )

            min_corner.z = min(
                min_corner.z,
                point.z,
            )

            max_corner.x = max(
                max_corner.x,
                point.x,
            )

            max_corner.y = max(
                max_corner.y,
                point.y,
            )

            max_corner.z = max(
                max_corner.z,
                point.z,
            )

    return (
        min_corner,
        max_corner,
    )


def center_objects(
    objects: list[
        bpy.types.Object
    ],
) -> tuple[
    Vector,
    Vector,
]:
    (
        min_corner,
        max_corner,
    ) = combined_bounds(
        objects
    )

    center = (
        min_corner
        + max_corner
    ) * 0.5

    for obj in objects:
        obj.location -= (
            center
        )

    (
        centered_min,
        centered_max,
    ) = combined_bounds(
        objects
    )

    model_size = (
        centered_max
        - centered_min
    )

    return (
        Vector(
            (
                0.0,
                0.0,
                0.0,
            )
        ),
        model_size,
    )


# ---------------------------------------------------------
# Materials
# ---------------------------------------------------------

def apply_neutral_material(
    objects: list[
        bpy.types.Object
    ],
) -> None:
    material = (
        bpy.data.materials.new(
            "BPT_ProjectionNeutral"
        )
    )

    material.diffuse_color = (
        0.58,
        0.61,
        0.66,
        1.0,
    )

    material.roughness = (
        0.72
    )

    material.metallic = (
        0.0
    )

    for obj in objects:
        if obj.type != "MESH":
            continue

        obj.data.materials.clear()

        obj.data.materials.append(
            material
        )


# ---------------------------------------------------------
# Camera
# ---------------------------------------------------------

def create_camera() -> bpy.types.Object:
    camera_data = (
        bpy.data.cameras.new(
            "BPT_ProjectionCamera"
        )
    )

    camera_data.type = (
        "ORTHO"
    )

    camera_data.clip_start = (
        0.001
    )

    camera_data.clip_end = (
        1000.0
    )

    camera = (
        bpy.data.objects.new(
            "BPT_ProjectionCamera",
            camera_data,
        )
    )

    bpy.context.scene.collection.objects.link(
        camera
    )

    bpy.context.scene.camera = (
        camera
    )

    return camera


def look_at(
    obj: bpy.types.Object,
    target: Vector,
) -> None:
    direction = (
        target
        - obj.location
    )

    if direction.length == 0.0:
        return

    obj.rotation_euler = (
        direction
        .to_track_quat(
            "-Z",
            "Y",
        )
        .to_euler()
    )


def place_camera(
    camera: bpy.types.Object,
    *,
    target: Vector,
    model_size: Vector,
    azimuth_degrees: float,
    elevation_degrees: float,
    ortho_scale: float,
) -> None:
    framing_size = max(
        model_size.x,
        model_size.y,
        model_size.z,
        0.01,
    )

    distance = (
        framing_size
        * 4.0
    )

    azimuth = math.radians(
        azimuth_degrees
    )

    elevation = math.radians(
        elevation_degrees
    )

    # TOP and BOT receive explicit rotations.
    #
    # This avoids roll ambiguity when the camera
    # is exactly on the vertical axis and keeps
    # world +Y as the top of the image.

    if elevation_degrees >= 89.999:
        camera.location = (
            0.0,
            0.0,
            distance,
        )

        camera.rotation_euler = (
            0.0,
            0.0,
            0.0,
        )

    elif elevation_degrees <= -89.999:
        camera.location = (
            0.0,
            0.0,
            -distance,
        )

        camera.rotation_euler = (
            0.0,
            math.pi,
            0.0,
        )

    else:
        horizontal_distance = (
            math.cos(
                elevation
            )
            * distance
        )

        camera.location = (
            math.sin(
                azimuth
            )
            * horizontal_distance,
            -math.cos(
                azimuth
            )
            * horizontal_distance,
            math.sin(
                elevation
            )
            * distance,
        )

        look_at(
            camera,
            target,
        )

    camera.data.ortho_scale = (
        ortho_scale
    )


# ---------------------------------------------------------
# Lighting
# ---------------------------------------------------------

def create_area_light(
    *,
    name: str,
    location: tuple[
        float,
        float,
        float,
    ],
    energy: float,
    size: float,
) -> None:
    light_data = (
        bpy.data.lights.new(
            name=name,
            type="AREA",
        )
    )

    light_data.energy = (
        energy
    )

    light_data.shape = (
        "DISK"
    )

    light_data.size = (
        size
    )

    light = (
        bpy.data.objects.new(
            name,
            light_data,
        )
    )

    light.location = (
        location
    )

    bpy.context.scene.collection.objects.link(
        light
    )

    look_at(
        light,
        Vector(
            (
                0.0,
                0.0,
                0.0,
            )
        ),
    )


def setup_lighting(
    model_size: Vector,
) -> None:
    radius = max(
        model_size.x,
        model_size.y,
        model_size.z,
        1.0,
    )

    distance = (
        radius
        * 2.6
    )

    light_size = (
        radius
        * 2.2
    )

    create_area_light(
        name="BPT_Key",
        location=(
            distance,
            -distance,
            distance * 1.4,
        ),
        energy=650.0,
        size=light_size,
    )

    create_area_light(
        name="BPT_Fill",
        location=(
            -distance,
            -distance,
            distance,
        ),
        energy=325.0,
        size=light_size,
    )

    create_area_light(
        name="BPT_Back",
        location=(
            0.0,
            distance,
            distance * 1.2,
        ),
        energy=250.0,
        size=light_size,
    )


# ---------------------------------------------------------
# Render configuration
# ---------------------------------------------------------

def setup_render(
    *,
    samples: int,
) -> None:
    scene = (
        bpy.context.scene
    )

    scene.render.engine = (
        "CYCLES"
    )

    scene.cycles.device = (
        "CPU"
    )

    scene.cycles.samples = max(
        1,
        samples,
    )

    scene.cycles.use_denoising = (
        False
    )

    scene.render.resolution_percentage = (
        100
    )

    scene.render.film_transparent = (
        True
    )

    scene.render.image_settings.file_format = (
        "PNG"
    )

    scene.render.image_settings.color_mode = (
        "RGBA"
    )

    scene.render.image_settings.color_depth = (
        "8"
    )

    scene.render.use_file_extension = (
        True
    )

    # Keep the neutral renders predictable.
    #
    # The transparent film means the world is
    # used for illumination but is not written
    # into the output background.

    world = (
        scene.world
    )

    if world is None:
        world = (
            bpy.data.worlds.new(
                "BPT_ProjectionWorld"
            )
        )

        scene.world = (
            world
        )

    world.use_nodes = (
        True
    )

    if world.node_tree is not None:
        background = (
            world
            .node_tree
            .nodes
            .get(
                "Background"
            )
        )

        if background is not None:
            background.inputs[
                "Color"
            ].default_value = (
                0.18,
                0.18,
                0.18,
                1.0,
            )

            background.inputs[
                "Strength"
            ].default_value = (
                0.45
            )


# ---------------------------------------------------------
# Projection sheet geometry
# ---------------------------------------------------------

def projection_cells(
    width: int,
    height: int,
) -> list[
    tuple[
        str,
        int,
        int,
        float,
        float,
        tuple[
            int,
            int,
            int,
            int,
        ],
    ]
]:
    result = []

    for (
        name,
        column,
        row,
        azimuth,
        elevation,
    ) in CELL_SPECS:
        bbox = pixel_bbox(
            width,
            height,
            column,
            row,
        )

        result.append(
            (
                name,
                column,
                row,
                azimuth,
                elevation,
                bbox,
            )
        )

    return result


def common_ortho_scale(
    model_size: Vector,
    cells: list[
        tuple[
            str,
            int,
            int,
            float,
            float,
            tuple[
                int,
                int,
                int,
                int,
            ],
        ]
    ],
    *,
    framing: float,
) -> float:
    if framing <= 0.0:
        raise ValueError(
            "framing must be greater than zero"
        )

    aspects: list[
        float
    ] = []

    for (
        _name,
        _column,
        _row,
        _azimuth,
        _elevation,
        bbox,
    ) in cells:
        (
            x0,
            y0,
            x1,
            y1,
        ) = bbox

        width = (
            x1
            - x0
        )

        height = (
            y1
            - y0
        )

        if (
            width <= 0
            or height <= 0
        ):
            raise ValueError(
                (
                    "Invalid Projection Tool "
                    f"cell size: {bbox}"
                )
            )

        aspects.append(
            width
            / height
        )

    minimum_aspect = min(
        aspects
    )

    horizontal_diagonal = (
        math.hypot(
            model_size.x,
            model_size.y,
        )
    )

    # Orthographic scale expresses vertical
    # world-space coverage.
    #
    # We use one conservative scale for all
    # cameras. This is intentional: changing the
    # scale from one view to another would make
    # the before/after sheet misleading.

    required_for_horizontal_views = max(
        model_size.z,
        (
            horizontal_diagonal
            / minimum_aspect
        ),
    )

    required_for_vertical_views = max(
        model_size.x,
        model_size.y,
        (
            max(
                model_size.x,
                model_size.y,
            )
            / minimum_aspect
        ),
    )

    return (
        max(
            required_for_horizontal_views,
            required_for_vertical_views,
            0.01,
        )
        * framing
    )


# ---------------------------------------------------------
# Template pixels
# ---------------------------------------------------------

def load_template(
    path: Path,
) -> tuple[
    array,
    int,
    int,
]:
    path = path.resolve()

    if not path.exists():
        raise FileNotFoundError(
            (
                "Missing Projection Tool "
                f"template: {path}"
            )
        )

    image = (
        bpy.data.images.load(
            str(
                path
            ),
            check_existing=False,
        )
    )

    try:
        image.update()

        width = int(
            image.size[0]
        )

        height = int(
            image.size[1]
        )

        if (
            width <= 0
            or height <= 0
        ):
            raise ValueError(
                (
                    "Invalid template size: "
                    f"{width}x{height}"
                )
            )

        pixels = array(
            "f",
            [0.0],
        ) * (
            width
            * height
            * 4
        )

        image.pixels.foreach_get(
            pixels
        )

    finally:
        bpy.data.images.remove(
            image
        )

    return (
        pixels,
        width,
        height,
    )


def clear_cell(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
) -> None:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    for y in range(
        y0,
        y1,
    ):
        for x in range(
            x0,
            x1,
        ):
            index = (
                (
                    y
                    * sheet_width
                    + x
                )
                * 4
            )

            sheet_pixels[
                index
            ] = 1.0

            sheet_pixels[
                index + 1
            ] = 1.0

            sheet_pixels[
                index + 2
            ] = 1.0

            sheet_pixels[
                index + 3
            ] = 1.0


# ---------------------------------------------------------
# Individual render
# ---------------------------------------------------------

def render_view(
    *,
    camera: bpy.types.Object,
    target: Vector,
    model_size: Vector,
    name: str,
    azimuth: float,
    elevation: float,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    ortho_scale: float,
    output_dir: Path,
) -> Path:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    width = (
        x1
        - x0
    )

    height = (
        y1
        - y0
    )

    scene = (
        bpy.context.scene
    )

    scene.render.resolution_x = (
        width
    )

    scene.render.resolution_y = (
        height
    )

    place_camera(
        camera,
        target=target,
        model_size=model_size,
        azimuth_degrees=(
            azimuth
        ),
        elevation_degrees=(
            elevation
        ),
        ortho_scale=(
            ortho_scale
        ),
    )

    output_path = (
        output_dir
        / f"{name}.png"
    )

    scene.render.filepath = str(
        output_path.resolve()
    )

    print(
        (
            f"Rendering projection "
            f"{name} "
            f"({azimuth:.0f}°, "
            f"{elevation:.0f}°)"
        )
    )

    bpy.ops.render.render(
        write_still=True
    )

    if not output_path.exists():
        raise RuntimeError(
            (
                "Render did not produce: "
                f"{output_path}"
            )
        )

    return output_path


# ---------------------------------------------------------
# Compositing
# ---------------------------------------------------------

def composite_render(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    render_path: Path,
) -> None:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    expected_width = (
        x1
        - x0
    )

    expected_height = (
        y1
        - y0
    )

    image = (
        bpy.data.images.load(
            str(
                render_path.resolve()
            ),
            check_existing=False,
        )
    )

    try:
        image.update()

        width = int(
            image.size[0]
        )

        height = int(
            image.size[1]
        )

        if (
            width
            != expected_width
            or height
            != expected_height
        ):
            raise ValueError(
                (
                    "Rendered cell size mismatch. "
                    f"Expected "
                    f"{expected_width}x"
                    f"{expected_height}, "
                    f"got {width}x{height}."
                )
            )

        render_pixels = array(
            "f",
            [0.0],
        ) * (
            width
            * height
            * 4
        )

        image.pixels.foreach_get(
            render_pixels
        )

        premultiplied = (
            image.alpha_mode
            == "PREMUL"
        )

        for local_y in range(
            height
        ):
            for local_x in range(
                width
            ):
                source_index = (
                    (
                        local_y
                        * width
                        + local_x
                    )
                    * 4
                )

                target_index = (
                    (
                        (
                            y0
                            + local_y
                        )
                        * sheet_width
                        + x0
                        + local_x
                    )
                    * 4
                )

                alpha = max(
                    0.0,
                    min(
                        1.0,
                        render_pixels[
                            source_index + 3
                        ],
                    ),
                )

                if premultiplied:
                    red = (
                        render_pixels[
                            source_index
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                    green = (
                        render_pixels[
                            source_index + 1
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                    blue = (
                        render_pixels[
                            source_index + 2
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                else:
                    red = (
                        render_pixels[
                            source_index
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                    green = (
                        render_pixels[
                            source_index + 1
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                    blue = (
                        render_pixels[
                            source_index + 2
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                sheet_pixels[
                    target_index
                ] = max(
                    0.0,
                    min(
                        1.0,
                        red,
                    ),
                )

                sheet_pixels[
                    target_index + 1
                ] = max(
                    0.0,
                    min(
                        1.0,
                        green,
                    ),
                )

                sheet_pixels[
                    target_index + 2
                ] = max(
                    0.0,
                    min(
                        1.0,
                        blue,
                    ),
                )

                sheet_pixels[
                    target_index + 3
                ] = 1.0

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Save
# ---------------------------------------------------------

def save_projection_sheet(
    pixels: array,
    width: int,
    height: int,
    output_path: Path,
) -> None:
    output_path = (
        output_path.resolve()
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = (
        bpy.data.images.new(
            name="BPT_ProjectionSheet",
            width=width,
            height=height,
            alpha=True,
        )
    )

    try:
        image.pixels.foreach_set(
            pixels
        )

        image.filepath_raw = str(
            output_path
        )

        image.file_format = (
            "PNG"
        )

        image.save()

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.samples < 1:
        raise ValueError(
            "samples must be >= 1"
        )

    if args.framing <= 0.0:
        raise ValueError(
            "framing must be > 0"
        )

    input_path = (
        args.input.resolve()
    )

    template_path = (
        args.template.resolve()
    )

    output_path = (
        args.output.resolve()
    )

    stills_dir = (
        output_path.parent
        / (
            output_path.stem
            + "_stills"
        )
    )

    if stills_dir.exists():
        shutil.rmtree(
            stills_dir
        )

    stills_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    clear_scene()

    objects = import_glb(
        input_path
    )

    (
        target,
        model_size,
    ) = center_objects(
        objects
    )

    if (
        args.material_mode
        == "neutral"
    ):
        apply_neutral_material(
            objects
        )

    camera = create_camera()

    setup_lighting(
        model_size
    )

    setup_render(
        samples=(
            args.samples
        )
    )

    (
        sheet_pixels,
        sheet_width,
        sheet_height,
    ) = load_template(
        template_path
    )

    cells = projection_cells(
        sheet_width,
        sheet_height,
    )

    ortho_scale = common_ortho_scale(
        model_size,
        cells,
        framing=(
            args.framing
        ),
    )

    print(
        (
            "Projection sheet size: "
            f"{sheet_width}x"
            f"{sheet_height}"
        )
    )

    print(
        (
            "Common orthographic scale: "
            f"{ortho_scale:.6f}"
        )
    )

    print(
        (
            "Material mode: "
            f"{args.material_mode}"
        )
    )

    for (
        index,
        (
            name,
            _column,
            _row,
            azimuth,
            elevation,
            bbox,
        ),
    ) in enumerate(
        cells,
        start=1,
    ):
        print(
            (
                f"[{index}/"
                f"{len(cells)}] "
                f"{name}"
            )
        )

        clear_cell(
            sheet_pixels,
            sheet_width,
            bbox,
        )

        render_path = render_view(
            camera=camera,
            target=target,
            model_size=model_size,
            name=name,
            azimuth=azimuth,
            elevation=elevation,
            bbox=bbox,
            ortho_scale=(
                ortho_scale
            ),
            output_dir=(
                stills_dir
            ),
        )

        composite_render(
            sheet_pixels,
            sheet_width,
            bbox,
            render_path,
        )

    save_projection_sheet(
        sheet_pixels,
        sheet_width,
        sheet_height,
        output_path,
    )

    if not output_path.exists():
        raise RuntimeError(
            (
                "Projection sheet was "
                "not generated: "
                f"{output_path}"
            )
        )

    if not args.keep_stills:
        shutil.rmtree(
            stills_dir
        )

    print(
        (
            "Projection sheet generated: "
            f"{output_path}"
        )
    )


if __name__ == "__main__":
    main()