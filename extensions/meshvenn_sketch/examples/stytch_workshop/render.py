"""Render the actual exported modules, fitted together on their editable native rig."""
import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

parser=argparse.ArgumentParser()
parser.add_argument('--pack',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=args.pack.resolve()
bpy.ops.wm.open_mainfile(filepath=str(folder/'source.blend'),use_scripts=False)
scene=bpy.context.scene;source=bpy.data.objects['MeshvennScan'];rig=source.find_armature()
for obj in scene.objects:
    if 'meshvenn_workshop_module' in obj:obj.hide_render=True
manifest=json.loads((folder/'pack.json').read_text());modules={};rigs=[rig]
for definition in manifest['modules']:
    before=set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(folder/definition['skinned']['file']),disable_bone_shape=True)
    meshes=[o for o in set(scene.objects)-before if o.type=='MESH']
    assert len(meshes)==1
    modules[meshes[0]]=definition;rigs.append(meshes[0].find_armature())
regions={'body-core':'Doll_body_core','left-arm':'Doll_left_arm','right-arm':'Doll_right_arm','left-leg':'Doll_left_leg','right-leg':'Doll_right_leg'}
for obj in list(scene.objects):
    if obj.type in {'LIGHT','CAMERA'}:bpy.data.objects.remove(obj,do_unlink=True)
source.hide_render=True
world=bpy.data.worlds.new('Workshop studio');world.use_nodes=True
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.15,.18,.22,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35;scene.world=world
camera_data=bpy.data.cameras.new('Module preview');camera=bpy.data.objects.new('Module preview',camera_data)
scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO';camera_data.ortho_scale=2.75
for name,location,power,size in (('Key',(-3,-4,5),320,4),('Fill',(4,-1,3),160,3),('Rim',(1,4,4),420,3)):
    data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
    obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=location
    obj.rotation_euler=(Vector((0,0,1.1))-obj.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,.1))
floor=bpy.context.object;floor.name='Preview floor'
material=bpy.data.materials.new('Studio floor');material.diffuse_color=(.065,.085,.10,1);floor.data.materials.append(material)
scene.render.engine='CYCLES';scene.cycles.samples=48;scene.cycles.use_denoising=True
scene.render.resolution_x=800;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.view_settings.view_transform='AgX';scene.view_settings.exposure=-.1
output=folder/'previews';output.mkdir(exist_ok=True)


def loadout(category):
    selected=[]
    for obj,module in modules.items():
        show=category=='complete' or module['category']==category
        obj.hide_render=not show
        if show:selected.append(module)
    replacements={m['replaces_region'] for m in selected if m['replaces_region']}
    for region,name in regions.items():bpy.data.objects[name].hide_render=region in replacements


def render(name,category,back=False):
    loadout(category);camera.location=(2.7,6 if back else -6,3.0)
    camera.rotation_euler=(Vector((0,0,1.18))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(output/(name+'.png'));bpy.ops.render.render(write_still=True)


render('equipment','equipment');render('replacements','replacement');render('accessories','accessory')
render('accessories-back','accessory',back=True);render('complete','complete')
for current in rigs:
    for name,angle in (('forearm.L',.95),('forearm.R',-.7),('thigh.R',-.45),('shin.R',1.15)):
        bone=current.pose.bones[name];bone.rotation_mode='XYZ';bone.rotation_euler.x=angle
bpy.context.view_layer.update();render('articulated','complete')
print('WORKSHOP RENDER PASS: six native-rig loadout views, including articulated replacements.')
