from pathlib import Path

# =========================================================
# Configuration
# =========================================================

DEFAULT_PACKAGE_ROOT = (
    Path("dist")
    / "blender_projection_tool"
)


REQUIRED_PACKAGE_FILES = (
    "__init__.py",
    "blender_manifest.toml",
    "properties/__init__.py",
    "properties/base_groups.py",
    "properties/constants.py",
    "properties/defaults.py",
    "properties/groups.py",
    "properties/pipeline.py",
    "properties/registration.py",
    "properties/settings.py",
    "properties/stage_mapping.py",
    "operators/__init__.py",
    "operators/constants.py",
    "operators/pipeline.py",
    "operators/presets.py",
    "operators/projection_edit.py",
    "operators/projection_load.py",
    "operators/projections.py",
    "operators/registration.py",
    "operators/runtime_execution.py",
    "operators/runtime_state.py",
    "operators/runtime.py",
    "operators/selection.py",
    "operators/turntable_import.py",
    "ui/__init__.py",
    "ui/actions.py",
    "ui/advanced.py",
    "ui/diagnostics.py",
    "ui/drawer_geometry_material.py",
    "ui/drawer_input.py",
    "ui/drawer_selection.py",
    "ui/drawers.py",
    "ui/helpers.py",
    "ui/panel.py",
    "ui/projection_list.py",
    "ui/registration.py",
    "ui/stage_cards.py",
    "version.py",
    "translations.py",

    # Core pipeline
    "core/__init__.py",
    "core/pipeline_contracts/__init__.py",
    "core/pipeline_contracts/context.py",
    "core/pipeline_contracts/identifiers.py",
    "core/pipeline_contracts/implementations.py",
    "core/pipeline_contracts/plan.py",
    "core/pipeline_contracts/results.py",
    "core/pipeline_contracts/stages.py",
    "core/pipeline_registry/__init__.py",
    "core/pipeline_registry/helpers.py",
    "core/pipeline_registry/models.py",
    "core/pipeline_registry/registry.py",
    "core/pipeline_runner/__init__.py",
    "core/pipeline_runner/models.py",
    "core/pipeline_runner/results.py",
    "core/pipeline_runner/runner.py",
    "core/geometry_contracts/__init__.py",
    "core/geometry_contracts/projection.py",
    "core/geometry_contracts/surface.py",
    "core/geometry_contracts/validation.py",
    "core/canonical_rig.py",
    "core/rig_contracts.py",

    # Input / projection
    "core/image_mask.py",
    "core/projection_math/__init__.py",
    "core/projection_math/coordinates.py",
    "core/projection_math/models.py",
    "core/projection_math/projection.py",
    "core/projection_math/vectors.py",

    # Native geometry
    "core/native_loader.py",
    "core/native_bridge/__init__.py",
    "core/native_bridge/abi.py",
    "core/native_bridge/conversion.py",
    "core/native_bridge/errors.py",
    "core/native_bridge/models.py",
    "core/native_bridge/runtime.py",
    "core/native_mesh_builder.py",
    "core/native_scan.py",

    # SDF geometry
    "core/sdf/__init__.py",
    "core/sdf/build.py",
    "core/sdf/constants.py",
    "core/sdf/distance_transform.py",
    "core/sdf/fusion.py",
    "core/sdf/mask.py",
    "core/sdf/projection.py",
    "core/sdf/utils.py",
    "core/sdf/volume.py",
    "core/sdf_surface/__init__.py",
    "core/sdf_surface/cells.py",
    "core/sdf_surface/faces.py",
    "core/sdf_surface/models.py",
    "core/sdf_surface/normals.py",
    "core/sdf_surface/numeric.py",
    "core/sdf_surface/surface_nets.py",

    # Material
    "core/material_blend/__init__.py",
    "core/material_blend/domain.py",
    "core/material_blend/blending.py",
    "core/material_visibility/__init__.py",
    "core/material_visibility/domain.py",
    "core/material_visibility/blender_backend.py",
    "core/material_visibility/tester.py",
    "core/projected_material/__init__.py",
    "core/projected_material/constants.py",
    "core/projected_material/image_buffer.py",
    "core/projected_material/models.py",
    "core/projected_material/sampling.py",
    "core/projected_material/blending.py",
    "core/projected_material/blender_material.py",
    "core/projected_material/application.py",
    "core/uv_bake/__init__.py",
    "core/uv_bake/api.py",
    "core/uv_bake/constants.py",
    "core/uv_bake/geometry.py",
    "core/uv_bake/models.py",
    "core/uv_bake/padding.py",
    "core/uv_bake/primitives.py",
    "core/uv_bake/rasterizer.py",
    "core/uv_bake/texture.py",

    # Implementations
    "implementations/__init__.py",
    "implementations/catalog.py",
    "implementations/registration.py",
    "implementations/projection_images/__init__.py",
    "implementations/projection_images/context.py",
    "implementations/projection_images/implementation.py",
    "implementations/projection_images/models.py",
    "implementations/projection_images/preparation.py",
    "implementations/native_visual_hull/__init__.py",
    "implementations/native_visual_hull/availability.py",
    "implementations/native_visual_hull/blender_output.py",
    "implementations/native_visual_hull/config.py",
    "implementations/native_visual_hull/constants.py",
    "implementations/native_visual_hull/execution.py",
    "implementations/native_visual_hull/implementation.py",
    "implementations/native_visual_hull/output.py",
    "implementations/sdf_reconstruction/__init__.py",
    "implementations/sdf_reconstruction/availability.py",
    "implementations/sdf_reconstruction/blender_mesh.py",
    "implementations/sdf_reconstruction/config.py",
    "implementations/sdf_reconstruction/diagnostics.py",
    "implementations/sdf_reconstruction/execution.py",
    "implementations/sdf_reconstruction/implementation.py",
    "implementations/sdf_reconstruction/metadata.py",
    "implementations/sdf_reconstruction/output.py",
    "implementations/sdf_reconstruction/resolution.py",
    "implementations/sdf_reconstruction/ui_settings.py",
    "implementations/projected_color/__init__.py",
    "implementations/projected_color/configuration.py",
    "implementations/projected_color/geometry.py",
    "implementations/projected_color/metadata.py",
    "implementations/projected_color/implementation.py",
    "implementations/uv_bake/__init__.py",
    "implementations/uv_bake/assets.py",
    "implementations/uv_bake/config.py",
    "implementations/uv_bake/constants.py",
    "implementations/uv_bake/diagnostics.py",
    "implementations/uv_bake/execution.py",
    "implementations/uv_bake/geometry.py",
    "implementations/uv_bake/implementation.py",
    "implementations/uv_bake/metadata.py",
    "implementations/uv_bake/sampler.py",
    "implementations/uv_bake/settings.py",
    "implementations/uv_bake/triangles.py",
    "implementations/uv_bake/ui.py",
    "implementations/canonical_rig/__init__.py",
    "implementations/canonical_rig/binding.py",
    "implementations/canonical_rig/implementation.py",

    # Native binaries
    "native/bin/libbpt_core.so",
    "native/bin/bpt_core.dll",
)


EXPECTED_IMPLEMENTATIONS = (
    "projection-images",
    "native-visual-hull",
    "sdf-reconstruction-v1",
    "projected-color-v1.2",
    "uv-bake-v2",
    "canonical-biped-v1",
)


EXPECTED_PROJECTION_NAMES = (
    "Front",
    "Right",
    "Back",
    "Top",
)


# =========================================================
# Generic GEOMETRY
# =========================================================

EXPECTED_GEOMETRY_CONTRACT = (
    "surface-envelope-v1"
)

FAKE_GEOMETRY_IMPLEMENTATION_ID = (
    "fake-sdf-surface"
)


# =========================================================
# SDF expected defaults
# =========================================================

EXPECTED_SDF_RESOLUTION = 96

EXPECTED_SDF_MINIMUM_RESOLUTION = 16

EXPECTED_SDF_REFERENCE_MAX_RESOLUTION = 160

EXPECTED_SDF_SYMMETRY_X = False

EXPECTED_SDF_SMOOTHNESS = 0.0

EXPECTED_SDF_SURFACE_OFFSET = 0.0

EXPECTED_SDF_ISO_LEVEL = 0.0

EXPECTED_SDF_GRADIENT_STEP_SCALE = 0.5


# =========================================================
# UV Bake expected defaults
# =========================================================

EXPECTED_UV_BAKE_TEXTURE_SIZE = "512"

EXPECTED_UV_BAKE_TEXTURE_SIZE_INT = int(
    EXPECTED_UV_BAKE_TEXTURE_SIZE
)

EXPECTED_UV_BAKE_PADDING_PIXELS = 8

EXPECTED_UV_BAKE_SAMPLES_PER_AXIS = "1"

EXPECTED_UV_BAKE_UV_LAYER_NAME = (
    "MeshvennUV"
)

EXPECTED_UV_BAKE_ISLAND_MARGIN = 0.02

EXPECTED_UV_BAKE_ANGLE_LIMIT_DEGREES = 66.0

EXPECTED_UV_BAKE_REUSE_EXISTING_UV = False

EXPECTED_SMART_PROJECT_MARGIN_PIXELS = 0.5


# =========================================================
# Blender RNA identifiers
# =========================================================

EXPECTED_OPERATOR_RNA_IDS = (
    "BPT_OT_load_projection_image",
    "BPT_OT_import_turntable_images",
    "BPT_OT_add_projection",
    "BPT_OT_remove_projection",
    "BPT_OT_add_turntable_preset",
    "BPT_OT_add_front_side_preset",

    "BPT_OT_set_pipeline_implementation",
    "BPT_OT_reset_pipeline_settings",

    "BPT_OT_run_pipeline",
    "BPT_OT_run_pipeline_stage",

    "BPT_OT_generate_character",
)


EXPECTED_OPERATOR_IDNAMES = (
    "bpt.load_projection_image",
    "bpt.import_turntable_images",
    "bpt.add_projection",
    "bpt.remove_projection",
    "bpt.add_turntable_preset",
    "bpt.add_front_side_preset",

    "bpt.set_pipeline_implementation",
    "bpt.reset_pipeline_settings",

    "bpt.run_pipeline",
    "bpt.run_pipeline_stage",

    "bpt.generate_character",
)


MAIN_PANEL_RNA_ID = (
    "BPT_PT_main_panel"
)

PROJECTION_UI_LIST_RNA_ID = (
    "BPT_UL_ProjectionViews"
)
