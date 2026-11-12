"""Build the two authored rigid prop fixtures, never importing the Meshvenn engine."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from . import designs, materials


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def animate(hinge, prefix, angle):
    hinge.rotation_mode='XYZ'
    axis=2 if prefix=='door' else 0
    for state in ('closed','open'):
        action=bpy.data.actions.new(prefix+'_'+state)
        hinge.animation_data_create();hinge.animation_data.action=action
        for frame,value in ((1,0),(19,angle if state=='open' else 0)):
            hinge.rotation_euler[axis]=value
            hinge.keyframe_insert(data_path='rotation_euler',frame=frame)
        track=hinge.animation_data.nla_tracks.new();track.name=action.name
        track.strips.new(action.name,1,action)
        hinge.animation_data.action=None
        track.mute=True
    hinge.rotation_euler=(0,0,0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    folder=args.output.resolve()
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'pack.json').exists():raise FileExistsError('Use a fresh output directory')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats=materials.create(folder/'textures')
    assets=[]
    for build,identifier,dimensions,required in (
        (designs.door,'chamber-door-v1',[1.3,1.8,.2],['DoorFrame','DoorHinge','DoorLeaf','RouteSignalSocket']),
        (designs.chest,'chamber-loot-cache-v1',[.85,.52,.44],['ChestBody','LidHinge','ChestLid','LootSpawnSocket']),
    ):
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        root,hinge,prefix,angle=build(mats)
        root['asset_id']=identifier;root['source']='Meshvenn authored rigid prop fixture; no skin'
        animate(hinge,prefix,angle)
        scene=bpy.context.scene;scene.render.fps=30;scene.frame_start=1;scene.frame_end=19;scene.frame_set(1)
        bpy.context.view_layer.update()
        points=[obj.matrix_world@Vector(corner) for obj in scene.objects if obj.type=='MESH' for corner in obj.bound_box]
        minimum=[min(v[i] for v in points) for i in range(3)]
        maximum=[max(v[i] for v in points) for i in range(3)]
        # Convert Blender XYZ to standard glTF XYZ (X,Z,-Y).
        lo=[minimum[0],minimum[2],-maximum[1]];hi=[maximum[0],maximum[2],-minimum[1]]
        actual=[hi[i]-lo[i] for i in range(3)]
        if max(abs(actual[i]-dimensions[i]) for i in range(3))>.006:
            raise ValueError(f'{identifier} unexpected bounds {lo} {hi}: {actual}')
        for obj in scene.objects:
            if obj.type=='MESH':
                obj.data.calc_loop_triangles()
        triangles=sum(len(obj.data.loop_triangles) for obj in scene.objects if obj.type=='MESH')
        if triangles>5000:raise ValueError(f'Triangle budget exceeded: {triangles}')
        bpy.ops.wm.save_as_mainfile(filepath=str(folder/(identifier+'.blend')))
        bpy.ops.object.select_all(action='SELECT')
        for track in hinge.animation_data.nla_tracks:track.mute=False
        bpy.ops.export_scene.gltf(filepath=str(folder/(identifier+'.glb')),export_format='GLB',
            use_selection=True,export_yup=True,export_animations=True,export_animation_mode='NLA_TRACKS',
            export_optimize_animation_keep_anim_object=True,
            export_anim_slide_to_zero=True,
            export_force_sampling=True,export_frame_range=False,export_nla_strips_merged_animation_name='Animation',
            export_extras=True,export_cameras=False,export_lights=False)
        assets.append(dict(id=identifier,file=identifier+'.glb',sha256=fingerprint(folder/(identifier+'.glb')),
            source=dict(file=identifier+'.blend',sha256=fingerprint(folder/(identifier+'.blend'))),
            dimensions=dimensions,bounds=dict(min=lo,max=hi),requiredNodes=required,
            animations=[prefix+'_closed',prefix+'_open'],triangles=triangles,
            opening=dict(node=hinge.name,axis='+Y' if prefix=='door' else '+X',angle_degrees=round(angle*180/3.141592653589793),duration_seconds=.6),
            materials=3,skins=0,collision='collision-spec.json'))
    document=dict(schema_version=1,pack_id='stytch-chamber-v1',coordinates=dict(up='+Y',front='+Z',units='metres'),
        provenance=dict(author='Slimtrat / Meshvenn',method='Authored closed geometry and deterministic painted PBR plates',
            external_image_dependencies=[],reference='Stytch Chamber stone/bronze art direction; reference images are not distributed'),
        assets=assets,textures=[dict(file='textures/'+p.name,sha256=fingerprint(p)) for p in sorted((folder/'textures').glob('*.png'))])
    (folder/'pack.json').write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    collision=dict(schema_version=1,coordinates=document['coordinates'],authority='Advisory only. Stytch retains its existing gameplay collision; no automatic GLB bodies.',
        assets=[dict(id='chamber-door-v1',closed_leaf=dict(type='box',center=[0,.73,-.11],size=[.72,1.32,.075],owner='DoorHinge'),
            passage=dict(width=.75,spring_height=1.02,apex_height=1.4,threshold_height=.07),
            fixed_boxes=[dict(center=[x,.55,-.1],size=[.26,1.04,.20]) for x in (-.51,.51)]),
            dict(id='chamber-loot-cache-v1',body_envelope=dict(type='box',center=[0,.17,0],size=[.85,.34,.44]),
                lid_envelope=dict(type='box',center=[0,.427,0],size=[.85,.185,.44],owner='LidHinge'),
                cavity=dict(min=[-.365,.075,-.17],max=[.365,.30,.17]))])
    (folder/'collision-spec.json').write_text(json.dumps(collision,indent=2)+'\n',encoding='utf-8')
    print('CHAMBER AUTHOR PASS '+json.dumps(assets))
