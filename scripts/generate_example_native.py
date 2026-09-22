from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Preserve the public imports used by other scripts.
from scripts.generate_example_native_support.shared import (
    BLEND_MODE,
    BinaryMask,
    CELL_SPECS,
    COLOR_ATTRIBUTE_NAME,
    ExtractedView,
    MATERIAL_MODE,
    Matrix,
    NativeProjection,
    NativeScanner,
    Path,
    ProjectedMaterialView,
    REPO_ROOT,
    RunLogger,
    VISIBILITY_MODE,
    apply_projected_material,
    argparse,
    array,
    bpy,
    create_blender_mesh_from_native,
    dataclass,
    hashlib,
    json,
    pixel_bbox,
    shade_smooth_native_object,
    sys,
)
from scripts.generate_example_native_support.cli import (
    parse_args,
)
from scripts.generate_example_native_support.image_components import (
    _largest_component,
    _copy_cell_pixels,
    _foreground_from_rgba,
    _apply_component_alpha,
    _mask_from_component,
)
from scripts.generate_example_native_support.extraction import (
    sha256_file,
    _save_extracted_png,
    extract_cell,
    extract_sheet,
)
from scripts.generate_example_native_support.projection import (
    prepare_projections,
    prepare_material_views,
    material_views_for_snapshot,
    material_visibility_manifest,
    material_blend_manifest,
    material_stats_manifest,
)
from scripts.generate_example_native_support.scene import (
    clear_scene,
    scale_object_to_height,
    _select_only,
    export_object,
)
from scripts.generate_example_native_support.entrypoint import (
    main,
)
from scripts.generate_example_native_support.pipeline import (
    process_sheet,
)

if __name__ == "__main__":
    main()
