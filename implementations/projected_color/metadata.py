from __future__ import annotations
import bpy
from ...core.projected_material import MaterialProjectionStats
from .configuration import IMPLEMENTATION_ID, ProjectedColorOutput

def _write_material_metadata(obj: bpy.types.Object, *, output: ProjectedColorOutput) -> None:
    """
    Add generic Meshvenn metadata.

    apply_projected_material() already writes detailed BPT
    material / visibility / blend statistics.
    """
    obj['meshvenn_material_implementation'] = IMPLEMENTATION_ID
    obj['meshvenn_material_version'] = '1.2'
    obj['meshvenn_material_mode'] = output.material_mode
    obj['meshvenn_material_visibility_mode'] = output.visibility_mode
    obj['meshvenn_material_blend_mode'] = output.blend_mode
    obj['meshvenn_material_color_attribute'] = output.color_attribute
    obj['meshvenn_material_geometry_implementation'] = output.geometry.implementation_id
    obj['meshvenn_material_projection_convention'] = output.geometry.projection_space.convention.value

def _stats_metrics(stats: MaterialProjectionStats) -> dict[str, int]:
    """
    Standard metrics exposed to PipelineRunner/UI.

    Keep this explicit rather than serializing the dataclass
    wholesale so the public diagnostics contract is clear.
    """
    return {'vertices': stats.vertex_count, 'loops': stats.loop_count, 'views': stats.view_count, 'projected_vertices': stats.projected_vertices, 'fallback_vertices': stats.fallback_vertices, 'projected_fallback_vertices': stats.projected_fallback_vertices, 'neutral_fallback_vertices': stats.neutral_fallback_vertices, 'candidate_samples': stats.candidate_samples, 'source_rejected_samples': stats.source_rejected_samples, 'visible_samples': stats.visible_samples, 'occluded_samples': stats.occluded_samples, 'front_facing_samples': stats.front_facing_samples, 'backface_samples': stats.backface_samples, 'grazing_rejected_samples': stats.grazing_rejected_samples, 'relative_rejected_samples': stats.relative_rejected_samples, 'top_k_rejected_samples': stats.top_k_rejected_samples, 'selected_samples': stats.selected_samples, 'accepted_samples': stats.accepted_samples, 'rejected_samples': stats.rejected_samples}
