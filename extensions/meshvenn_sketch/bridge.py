"""Read public Blender projections/mesh metadata; never import the engine."""
from dataclasses import asdict
import json
import math

import bpy
from mathutils import Vector

from .geometry import ViewFrame

RECIPE='mvsketch_recipe'
SIGNATURE='mvsketch_mesh_signature'
SOURCE_REF='mvsketch_source'
IMAGE_REF='mvsketch_image'


def source_mesh(settings):
    source=settings.source
    if (source is None or source.type!='MESH' or source.library or source.data.library
            or source.name not in bpy.context.scene.objects
            or not all(math.isfinite(v) for row in source.matrix_world for v in row)
            or source.matrix_world.determinant()<=1e-10):
        raise ValueError('Choose a local source mesh with a positive, nonsingular world transform.')
    return source


def rig_for(source):
    rigs={m.object for m in source.modifiers if m.type=='ARMATURE' and (m.show_viewport or m.show_render) and m.object is not None}
    if len(rigs)>1:raise ValueError('The source has multiple active rigs; choose an unambiguous source.')
    return next(iter(rigs),None)


def native_frame(source):
    keys=('meshvenn_projection_width','meshvenn_projection_depth','meshvenn_projection_height',
          'meshvenn_projection_voxel_size','meshvenn_projection_center_xy','meshvenn_projection_convention')
    if not all(k in source for k in keys):raise ValueError('This source has no saved Meshvenn projection frame. Use explicit source-bounds calibration instead.')
    w,d,h,voxel,centred,convention=(source[k] for k in keys)
    if convention!='surface-envelope-v1' or type(centred) is not bool:
        raise ValueError('Unsupported saved projection convention.')
    if any(type(v) is not int or v<=0 for v in (w,d,h)) or type(voxel) not in (int,float) or not math.isfinite(voxel) or voxel<=0:
        raise ValueError('Invalid saved projection dimensions.')
    size=(w*voxel,d*voxel,h*voxel)
    return (-size[0]/2,-size[1]/2,0.) if centred else (0.,0.,0.),size


def bounds_frame(source):
    points=[tuple(v.co) for v in source.data.vertices]
    if not points:raise ValueError('The source mesh is empty.')
    minimum=tuple(min(p[i] for p in points) for i in range(3))
    size=tuple(max(p[i] for p in points)-minimum[i] for i in range(3))
    ViewFrame(minimum,size)
    return minimum,size


def calibrate(settings,*,meshvenn=False):
    source=source_mesh(settings)
    if meshvenn:
        engine=getattr(bpy.context.scene,'bpt_settings',None)
        views=getattr(engine,'projections',())
        index=getattr(engine,'active_projection_index',-1)
        if not 0<=index<len(views):raise ValueError('Select a Meshvenn reference view first.')
        view=views[index]
        if view.image is None:raise ValueError('The selected Meshvenn view has no image.')
        minimum,size=native_frame(source)
        frame=ViewFrame(minimum,size,math.degrees(view.azimuth),math.degrees(view.elevation),bool(view.flip_x),
                        float(view.alignment_offset_u),float(view.alignment_offset_v),float(view.alignment_scale))
        image,label=view.image,'Meshvenn: '+view.name
    else:
        image=settings.image
        if image is None:raise ValueError('Choose a reference image before calibrating.')
        minimum,size=bounds_frame(source)
        frame=ViewFrame(minimum,size,math.degrees(settings.azimuth),math.degrees(settings.elevation),bool(settings.flip_x))
        label='Source bounds — image must frame those bounds'
    if image.source in {'TILED','SEQUENCE','MOVIE','VIEWER'} or min(image.size)<=0:
        raise ValueError('Use one loaded, ordinary reference image.')
    settings.image=image;settings.azimuth=math.radians(frame.azimuth);settings.elevation=math.radians(frame.elevation);settings.flip_x=frame.flip_x
    settings.calibrated_source=source;settings.calibrated_image=image
    settings.frame_json=json.dumps({'schema_version':1,'frame':asdict(frame),'image_size':list(image.size),
                                    'kind':'meshvenn' if meshvenn else 'bounds'},allow_nan=False)
    settings.calibration_label=label
    settings.contour.clear()
    return frame


def draft_frame(settings):
    source=source_mesh(settings)
    if settings.calibrated_source is not source or settings.calibrated_image is not settings.image or not settings.frame_json:
        raise ValueError('Calibrate this source and reference view before drawing.')
    state=json.loads(settings.frame_json)
    if state.get('schema_version')!=1 or list(settings.image.size)!=state['image_size']:
        raise ValueError('Reference dimensions changed; calibrate the view again.')
    frame=ViewFrame(**state['frame'])
    minimum,size=native_frame(source) if state['kind']=='meshvenn' else bounds_frame(source)
    if tuple(minimum)!=tuple(frame.minimum) or tuple(size)!=tuple(frame.size):
        raise ValueError('Source calibration changed; calibrate the view again.')
    if (abs(math.degrees(settings.azimuth)-frame.azimuth)>1e-6 or abs(math.degrees(settings.elevation)-frame.elevation)>1e-6
            or bool(settings.flip_x)!=frame.flip_x):raise ValueError('View angles changed; calibrate before drawing.')
    return frame


def depth_anchor(source,rig,bone,frame):
    if rig is None:return tuple(o+s/2 for o,s in zip(frame.minimum,frame.size))
    selected=rig.data.bones.get(bone)
    if selected is None or not selected.use_deform:raise ValueError('Choose an existing deform bone explicitly.')
    return tuple(source.matrix_world.inverted() @ rig.matrix_world @ selected.head_local)


def read_recipe(obj):
    if obj is None or obj.type!='MESH' or obj.library or obj.data.library or RECIPE not in obj:
        raise ValueError('Select an editable piece created by Meshvenn Sketch.')
    recipe=json.loads(obj[RECIPE])
    required={'schema_version','points','frame','anchor','thickness','depth','edge','source_name','image_name','binding_bone','calibration'}
    if not isinstance(recipe,dict) or set(recipe)!=required or type(recipe['schema_version']) is not int or recipe['schema_version']!=1:
        raise ValueError('Unsupported piece recipe.')
    ViewFrame(**recipe['frame'])
    return recipe
