"""Artist workflow in a separate Image Editor / 3D View sidebar."""
import bpy
from .bridge import RECIPE,rig_for


def draw_controls(layout,context):
    settings=context.scene.mvsketch
    source=layout.box();source.label(text='1. Source and reference',icon='IMAGE_DATA')
    source.prop(settings,'source');source.operator('mvsketch.use_source',icon='EYEDROPPER')
    source.prop(settings,'image');source.operator('mvsketch.load_image',icon='FILE_IMAGE')
    engine=getattr(context.scene,'bpt_settings',None)
    if engine is not None:
        row=source.row();row.enabled=bool(getattr(engine,'projections',()))
        op=row.operator('mvsketch.calibrate',text='Use Active Meshvenn Projection',icon='CAMERA_DATA');op.from_meshvenn=True
    manual=source.column(align=True)
    manual.label(text='Manual: image must fit source bounds')
    row=manual.row(align=True);row.prop(settings,'azimuth');row.prop(settings,'elevation')
    manual.prop(settings,'flip_x')
    op=manual.operator('mvsketch.calibrate',text='Calibrate Image to Source Bounds');op.from_meshvenn=False
    if settings.frame_json:source.label(text=settings.calibration_label,icon='CHECKMARK')
    if context.area.type=='VIEW_3D':source.operator('mvsketch.open_view',icon='WINDOW')
    draft=layout.box();draft.label(text='2. Draw and create',icon='GREASEPENCIL')
    if context.area.type=='IMAGE_EDITOR':draft.operator('mvsketch.draw_outline',icon='GREASEPENCIL')
    else:draft.label(text='Open Drawing View, then trace in its sidebar')
    draft.label(text=f'{len(settings.contour)} saved contour corners')
    draft.prop(settings,'name');draft.prop(settings,'color')
    draft.prop(settings,'thickness');draft.prop(settings,'depth');draft.prop(settings,'edge')
    draft.label(text='One view: depth is an artist setting',icon='INFO')
    draft.prop(settings,'bind_to_rig')
    try:rig=rig_for(settings.source) if settings.source else None
    except ValueError:rig=None
    if rig:draft.prop_search(settings,'bone',rig.data,'bones')
    elif settings.bind_to_rig:draft.label(text='Source has no rig; disable binding',icon='ERROR')
    create=draft.row();create.enabled=len(settings.contour)>=3
    create.operator('mvsketch.create_piece',icon='MESH_DATA')
    piece=layout.box();piece.label(text='3. Edit and export',icon='MOD_ARMATURE')
    piece.operator('mvsketch.edit_piece',icon='EYEDROPPER')
    if settings.piece:
        piece.label(text=settings.piece.name)
        piece.operator('mvsketch.update_dimensions',icon='MOD_SOLIDIFY')
        row=piece.row();row.operator('mvsketch.weight_paint',text='Paint Piece Weights',icon='WPAINT_HLT').target='PIECE'
        piece.operator('mvsketch.export_piece',icon='EXPORT')
    if settings.source:
        piece.operator('mvsketch.weight_paint',text='Paint Source Weights',icon='WPAINT_HLT').target='SOURCE'
    piece.label(text='Weight painting uses Blender’s native brushes')
    piece.label(text='Return to Object mode to create or export')


class MVSK_PT_Image(bpy.types.Panel):
    bl_label='Sketch Modules';bl_idname='MVSK_PT_image';bl_space_type='IMAGE_EDITOR';bl_region_type='UI';bl_category='Meshvenn Sketch'
    def draw(self,context):draw_controls(self.layout,context)


class MVSK_PT_View(bpy.types.Panel):
    bl_label='Sketch Modules';bl_idname='MVSK_PT_view';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Meshvenn Sketch'
    def draw(self,context):draw_controls(self.layout,context)


CLASSES=(MVSK_PT_Image,MVSK_PT_View)
