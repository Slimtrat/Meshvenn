"""Blender authoring operations owned solely by the Sketch extension."""
import bpy
from bpy.props import BoolProperty,EnumProperty,StringProperty
from bpy_extras.io_utils import ExportHelper,ImportHelper

from .authoring import create_piece,load_piece,update_dimensions
from .bridge import calibrate,read_recipe,rig_for,source_mesh
from .exporting import export_piece


class _Operation:
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        try:self.run(context,context.scene.mvsketch)
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class MVSK_OT_UseSource(_Operation,bpy.types.Operator):
    bl_idname='mvsketch.use_source';bl_label='Use Selected Source Mesh'
    def run(self,context,settings):
        obj=context.active_object
        if obj is None or obj.type!='MESH':raise ValueError('Select the character source mesh.')
        settings.source=obj
        rig=rig_for(obj)
        if rig and rig.data.bones.active and rig.data.bones.active.use_deform:settings.bone=rig.data.bones.active.name


class MVSK_OT_Calibrate(_Operation,bpy.types.Operator):
    bl_idname='mvsketch.calibrate';bl_label='Calibrate Reference View'
    from_meshvenn: BoolProperty(default=False)
    def run(self,context,settings):calibrate(settings,meshvenn=self.from_meshvenn)


class MVSK_OT_LoadImage(bpy.types.Operator,ImportHelper):
    bl_idname='mvsketch.load_image';bl_label='Load Reference Image'
    filter_glob: StringProperty(default='*.png;*.jpg;*.jpeg;*.webp;*.tif;*.tiff;*.bmp',options={'HIDDEN'})
    def execute(self,context):
        try:
            image=bpy.data.images.load(self.filepath,check_existing=True)
            context.scene.mvsketch.image=image
            if context.area and context.area.type=='IMAGE_EDITOR':context.space_data.image=image
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class MVSK_OT_OpenView(bpy.types.Operator):
    bl_idname='mvsketch.open_view';bl_label='Open Drawing View'
    bl_description='Open the reference beside the 3D view; changes only the current workspace layout'
    def execute(self,context):
        image=context.scene.mvsketch.image
        if image is None:self.report({'ERROR'},'Choose a reference image first.');return {'CANCELLED'}
        area=next((a for a in context.screen.areas if a.type=='IMAGE_EDITOR'),None)
        if area is None:
            if context.area.type!='VIEW_3D':self.report({'ERROR'},'Open this action from a 3D View.');return {'CANCELLED'}
            before={a.as_pointer() for a in context.screen.areas}
            bpy.ops.screen.area_split(direction='VERTICAL',factor=.5)
            created=[a for a in context.screen.areas if a.as_pointer() not in before]
            if not created:self.report({'ERROR'},'Could not open an Image Editor.');return {'CANCELLED'}
            area=created[0];area.type='IMAGE_EDITOR'
        area.spaces.active.image=image;area.spaces.active.ui_mode='VIEW'
        area.spaces.active.show_region_ui=True
        region=next((r for r in area.regions if r.type=='WINDOW'),None)
        if region:
            with context.temp_override(area=area,region=region):bpy.ops.image.view_all(fit_view=True)
        area.tag_redraw()
        return {'FINISHED'}


class MVSK_OT_Create(_Operation,bpy.types.Operator):
    bl_idname='mvsketch.create_piece';bl_label='Create 3D Piece'
    bl_description='Extrude the calibrated outline and optionally bind every vertex to the chosen bone'
    def run(self,context,settings):
        obj=create_piece(context,settings)
        self.report({'INFO'},f'Created {obj.name}; source and rig unchanged.')


class MVSK_OT_LoadPiece(_Operation,bpy.types.Operator):
    bl_idname='mvsketch.edit_piece';bl_label='Edit Selected Sketch Piece'
    def run(self,context,settings):load_piece(settings,context.active_object)


class MVSK_OT_Dimensions(_Operation,bpy.types.Operator):
    bl_idname='mvsketch.update_dimensions';bl_label='Apply Piece Dimensions'
    bl_description='Update depth/thickness without replacing painted weights; refuse manually edited topology or UVs'
    def run(self,context,settings):update_dimensions(settings.piece,settings)


class MVSK_OT_WeightPaint(_Operation,bpy.types.Operator):
    bl_idname='mvsketch.weight_paint';bl_label='Paint Skin Weights'
    target: EnumProperty(items=(('PIECE','Piece','Paint the selected Sketch piece'),('SOURCE','Source','Paint the character source explicitly')),default='PIECE')
    def run(self,context,settings):
        obj=settings.piece if self.target=='PIECE' else source_mesh(settings)
        if obj is None or obj.type!='MESH' or obj.library or obj.data.library or obj.data.users!=1:
            raise ValueError('Choose a local single-user mesh for weight painting.')
        if self.target=='PIECE':read_recipe(obj)
        rig=rig_for(obj)
        if rig is None or settings.bone not in rig.data.bones or not rig.data.bones[settings.bone].use_deform:
            raise ValueError('Choose a deform bone on this mesh rig before painting.')
        if context.mode!='OBJECT':raise ValueError('Return to Object mode before switching the paint target.')
        if context.view_layer.objects.get(obj.name) is not obj:raise ValueError('Target is excluded from this view layer.')
        selected,active,hidden=tuple(context.selected_objects),context.view_layer.objects.active,obj.hide_get()
        group=obj.vertex_groups.get(settings.bone);created=group is None;index=obj.vertex_groups.active_index
        previews=[(item,item.hide_get(),item.hide_render) for item in context.scene.objects
                  if self.target=='SOURCE' and item.get('meshvenn_source_mesh')==obj.name]
        try:
            for item in context.selected_objects:item.select_set(False)
            obj.hide_set(False);obj.select_set(True);context.view_layer.objects.active=obj
            for item,_,_ in previews:item.hide_set(True);item.hide_render=True
            group=group or obj.vertex_groups.new(name=settings.bone);obj.vertex_groups.active_index=group.index
            if bpy.ops.object.mode_set(mode='WEIGHT_PAINT')!={'FINISHED'}:raise ValueError('Could not enter Weight Paint mode.')
        except BaseException:
            if created and group is not None:obj.vertex_groups.remove(group)
            obj.vertex_groups.active_index=index;obj.hide_set(hidden)
            for item,hide,render in previews:item.hide_set(hide);item.hide_render=render
            for item in context.selected_objects:item.select_set(False)
            for item in selected:item.select_set(True)
            context.view_layer.objects.active=active
            raise


class MVSK_OT_Export(bpy.types.Operator,ExportHelper):
    bl_idname='mvsketch.export_piece';bl_label='Export Piece GLB'
    filename_ext='.glb'
    filter_glob: StringProperty(default='*.glb',options={'HIDDEN'})
    overwrite: BoolProperty(name='Replace Existing File',default=False)
    def execute(self,context):
        try:export_piece(context,context.scene.mvsketch.piece,self.filepath,overwrite=self.overwrite)
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'Exported the piece only, with its rig binding and no clips.')
        return {'FINISHED'}


CLASSES=(MVSK_OT_UseSource,MVSK_OT_Calibrate,MVSK_OT_LoadImage,MVSK_OT_OpenView,MVSK_OT_Create,
         MVSK_OT_LoadPiece,MVSK_OT_Dimensions,MVSK_OT_WeightPaint,MVSK_OT_Export)
