"""Standalone extension authoring, rig response, rollback and portable GLB."""
import argparse
from dataclasses import asdict
import importlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser()
parser.add_argument('--package-root',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
sys.path.insert(0,str(args.package_root.resolve().parent))
extension=importlib.import_module(args.package_root.name)
extension.register()
from meshvenn_sketch import authoring,bridge,exporting


def source_state(obj,rig,image):
    return ([tuple(v.co) for v in obj.data.vertices],[(g.name,g.index) for g in obj.vertex_groups],
            [[(g.group,g.weight) for g in v.groups] for v in obj.data.vertices],
            {b.name:([tuple(r) for r in b.matrix_local],b.parent.name if b.parent else None) for b in rig.data.bones},
            {b.name:[tuple(r) for r in b.matrix_basis] for b in rig.pose.bones},tuple(image.pixels))


def refused(call):
    try:call()
    except (ValueError,FileExistsError):return
    raise AssertionError('Unsafe operation was accepted')


def evaluated_positions(obj):
    bpy.context.view_layer.update()
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
    try:return [tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices]
    finally:evaluated.to_mesh_clear()


try:
    assert not hasattr(bpy.context.scene,'bpt_settings'),'Engine must not be installed for this test'
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.object.armature_add()
    rig=bpy.context.object;rig.name='SketchTestRig'
    rig.data.bones[0].name='upper'
    bpy.ops.object.mode_set(mode='EDIT')
    child=rig.data.edit_bones.new('lower');child.head=(0,0,1);child.tail=(0,0,2);child.parent=rig.data.edit_bones['upper']
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add(size=2)
    source=bpy.context.object;source.name='UntouchedCharacter'
    source.parent=rig
    source.vertex_groups.new(name='upper').add(list(range(len(source.data.vertices))),1.,'REPLACE')
    source.modifiers.new('Existing Skin','ARMATURE').object=rig
    rig.location=(1.2,-.3,.6);rig.rotation_euler.z=.2;rig.scale=(.25,.25,.25)
    source.rotation_euler.y=.1;source.scale=(.9,1.1,.95)
    bpy.context.view_layer.update()
    image=bpy.data.images.new('UntouchedReference',width=128,height=128)
    settings=bpy.context.scene.mvsketch;settings.source=source;settings.image=image
    settings.bone='lower';settings.name='Shoulder Piece'
    # Optional bridge consumes public data only; the engine is never imported.
    metadata={'width':2,'depth':2,'height':2,'voxel_size':1.,'center_xy':True,'convention':'surface-envelope-v1'}
    for key,value in metadata.items():source['meshvenn_projection_'+key]=value
    assert bridge.native_frame(source)==((-1.,-1.,0.),(2.,2.,2.))
    view=SimpleNamespace(image=image,name='Public side view',azimuth=.8,elevation=.2,flip_x=True,
                         alignment_offset_u=.1,alignment_offset_v=-.05,alignment_scale=1.2)
    engine=SimpleNamespace(projections=[view],active_projection_index=0)
    scene=SimpleNamespace(objects=bpy.context.scene.objects,bpt_settings=engine)
    with patch.object(bridge,'bpy',SimpleNamespace(context=SimpleNamespace(scene=scene))):
        frame=bridge.calibrate(settings,meshvenn=True)
        assert frame.flip_x and abs(frame.offset_u-.1)<1e-9
        assert bridge.draft_frame(settings)==frame
    assert (view.azimuth,view.elevation,view.flip_x,view.alignment_offset_u)==(.8,.2,True,.1)
    settings.azimuth=0.;settings.elevation=0.;settings.flip_x=False
    bridge.calibrate(settings)
    for uv in ((.55,.55),(.85,.55),(.85,.8),(.68,.9),(.55,.8)):settings.contour.add().uv=uv
    before=source_state(source,rig,image)
    ids=(set(bpy.data.objects),set(bpy.data.meshes),set(bpy.data.materials))
    with patch.object(authoring.json,'dumps',side_effect=RuntimeError('Injected recipe failure')):
        try:authoring.create_piece(bpy.context,settings)
        except RuntimeError:pass
        else:raise AssertionError('Injection missed')
    assert ids==(set(bpy.data.objects),set(bpy.data.meshes),set(bpy.data.materials))
    assert source_state(source,rig,image)==before
    obj=authoring.create_piece(bpy.context,settings)
    assert source_state(source,rig,image)==before
    assert not any(name.startswith('blender_projection_tool') for name in sys.modules)
    assert rig is bridge.rig_for(obj)
    assert all(len(v.groups)==1 and abs(v.groups[0].weight-1)<1e-7 for v in obj.data.vertices)
    # Check rigid bone deformation before changing dimensions, without bevel.
    obj.modifiers['Sketch Rounded Edges'].show_viewport=False
    rest=[obj.matrix_world @ v.co for v in obj.data.vertices]
    rig.pose.bones['lower'].rotation_mode='XYZ';rig.pose.bones['lower'].rotation_euler.x=.7
    bpy.context.view_layer.update()
    palette=rig.matrix_world @ rig.pose.bones['lower'].matrix @ rig.data.bones['lower'].matrix_local.inverted() @ rig.matrix_world.inverted()
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
    try:assert max((evaluated.matrix_world @ v.co-palette @ p).length for v,p in zip(mesh.vertices,rest))<1e-5
    finally:evaluated.to_mesh_clear()
    rig.pose.bones['lower'].matrix_basis.identity();bpy.context.view_layer.update()
    obj.modifiers['Sketch Rounded Edges'].show_viewport=True
    group=obj.vertex_groups.new(name='upper')
    for i in range(len(obj.data.vertices)):
        obj.vertex_groups['lower'].add((i,),.65,'REPLACE');group.add((i,),.35,'REPLACE')
    weights=[[(g.group,g.weight) for g in v.groups] for v in obj.data.vertices]
    original=obj.data;old_recipe=obj[bridge.RECIPE];old_signature=obj[bridge.SIGNATURE]
    settings.thickness=.07;settings.depth=.03
    with patch.object(authoring.json,'dumps',side_effect=RuntimeError('Injected dimension failure')):
        try:authoring.update_dimensions(obj,settings)
        except RuntimeError:pass
        else:raise AssertionError('Injection missed')
    assert obj.data is original and obj[bridge.RECIPE]==old_recipe and obj[bridge.SIGNATURE]==old_signature
    authoring.update_dimensions(obj,settings)
    assert weights==[[(g.group,g.weight) for g in v.groups] for v in obj.data.vertices]
    assert source_state(source,rig,image)==before
    # Manual geometry must not disappear when parameters are changed.
    co=obj.data.vertices[0].co.copy();obj.data.vertices[0].co.x+=.02
    refused(lambda:authoring.update_dimensions(obj,settings));obj.data.vertices[0].co=co
    authoring.load_piece(settings,obj)
    assert len(settings.contour)==5
    # Native paint targets the piece or the explicitly selected source.
    assert bpy.ops.mvsketch.weight_paint(target='PIECE')=={'FINISHED'}
    assert bpy.context.object is obj and obj.mode=='WEIGHT_PAINT'
    bpy.ops.object.mode_set(mode='OBJECT')
    preview=bpy.data.objects.new('Derived preview',source.data.copy())
    bpy.context.scene.collection.objects.link(preview);preview['meshvenn_source_mesh']=source.name
    assert bpy.ops.mvsketch.weight_paint(target='SOURCE')=={'FINISHED'}
    assert bpy.context.object is source and source.mode=='WEIGHT_PAINT' and preview.hide_get() and preview.hide_render
    bpy.ops.object.mode_set(mode='OBJECT')
    assert source_state(source,rig,image)[:1]==before[:1]
    # Entering paint does not reweight any existing vertex.
    assert source_state(source,rig,image)[2:]==before[2:]
    source.vertex_groups.remove(source.vertex_groups['lower'])  # Empty group explicitly chosen for painting.
    assert source_state(source,rig,image)==before
    bpy.data.objects.remove(preview,do_unlink=True)
    args.output.mkdir(parents=True,exist_ok=True)
    destination=args.output/'piece.glb'
    expected_rest=evaluated_positions(obj)
    rig.pose.bones['lower'].rotation_euler.x=.4;bpy.context.view_layer.update()
    posed=source_state(source,rig,image)
    exporting.export_piece(bpy.context,obj,str(destination))
    assert source_state(source,rig,image)==posed
    selected,active=tuple(bpy.context.selected_objects),bpy.context.view_layer.objects.active
    original_bytes=destination.read_bytes()
    with patch.object(exporting,'_validate_glb',side_effect=ValueError('Injected export failure')):
        refused(lambda:exporting.export_piece(bpy.context,obj,str(destination),overwrite=True))
    assert destination.read_bytes()==original_bytes and not list(args.output.glob('.meshvenn-sketch-*'))
    assert tuple(bpy.context.selected_objects)==selected and bpy.context.view_layer.objects.active is active
    assert source_state(source,rig,image)==posed
    refused(lambda:exporting.export_piece(bpy.context,obj,str(destination)))
    raw=destination.read_bytes();length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length])
    assert len(doc['meshes'])==1 and not doc.get('animations')
    assert 'UntouchedCharacter' not in [n.get('name') for n in doc['nodes']]
    assert {doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']}=={'upper','lower'}
    # The GLB reopens independently, while the source scene is saved separately.
    rig.pose.bones['lower'].matrix_basis.identity();bpy.context.view_layer.update()
    obj.modifiers['Sketch Rounded Edges'].show_viewport=True
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'editable.blend'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(destination),disable_bone_shape=True)
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    assert len(meshes)==1 and len(meshes[0].find_armature().data.bones)==2
    actual_rest=evaluated_positions(meshes[0])
    assert len(actual_rest)>=len(expected_rest)
    assert max(min((Vector(p)-Vector(q)).length for q in actual_rest) for p in expected_rest)<1e-5
    bpy.ops.wm.open_mainfile(filepath=str(args.output/'editable.blend'),use_scripts=False)
    obj=bpy.data.objects['Shoulder Piece'];settings=bpy.context.scene.mvsketch
    authoring.load_piece(settings,obj)
    assert settings.source.name=='UntouchedCharacter' and bridge.read_recipe(obj)['binding_bone']=='lower'
    settings.bind_to_rig=False;settings.name='Static accessory'
    assert bpy.ops.mvsketch.create_piece()=={'FINISHED'}
    assert not settings.piece.vertex_groups and bridge.rig_for(settings.piece) is None
    exporting.export_piece(bpy.context,settings.piece,str(args.output/'static.glb'))
    print('SKETCH EXTENSION PASS: standalone registration, source isolation, rig response, exact rollback, painted-weight preservation, GLB and blend reload.')
finally:extension.unregister()
