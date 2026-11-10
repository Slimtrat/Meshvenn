"""Author/re-export the original ten-piece workshop pack without engine imports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent
ROOT=next((p for p in HERE.parents if (p/'extensions/meshvenn_sketch').is_dir() and (p/'example/v2').is_dir()),None)
sys.path.insert(0,str(HERE))
if ROOT:sys.path.insert(0,str(ROOT/'extensions'))
import glb
from designs import PALETTE,designs

TARGET=ROOT/'example/v2/modular/StytchDollDistalChains' if ROOT else None


def source_snapshot(source,rig):
    value=([tuple(v.co) for v in source.data.vertices],[[tuple((g.group,g.weight)) for g in v.groups] for v in source.data.vertices],
           [list(row) for row in source.matrix_world],[(b.name,b.parent.name if b.parent else None,[list(row) for row in b.matrix_local]) for b in rig.data.bones])
    return hashlib.sha256(json.dumps(value,allow_nan=False).encode()).hexdigest()


def materials():
    result=[]
    for name,color,metal,roughness in PALETTE:
        mat=bpy.data.materials.new(name);mat.use_nodes=True;mat.diffuse_color=color
        node=mat.node_tree.nodes.get('Principled BSDF')
        node.inputs['Base Color'].default_value=color;node.inputs['Metallic'].default_value=metal;node.inputs['Roughness'].default_value=roughness
        result.append(mat)
    return result


def create(module,source,rig,palette,collection):
    model=module.pop('model');mesh=bpy.data.meshes.new(module['id']+'.Mesh')
    mesh.from_pydata(model.vertices,[],model.faces);mesh.update()
    for mat in palette:mesh.materials.append(mat)
    uv=mesh.uv_layers.new(name='Module UV')
    for polygon,material,face_uv in zip(mesh.polygons,model.materials,model.uvs):
        polygon.material_index=material;polygon.use_smooth=True
        for loop,point in zip(polygon.loop_indices,face_uv):uv.data[loop].uv=point
    obj=bpy.data.objects.new(module['id'],mesh);collection.objects.link(obj)
    obj.parent=source.parent;obj.matrix_world=source.matrix_world.copy()
    for name in sorted(set(model.bones)):
        obj.vertex_groups.new(name=name).add([i for i,bone in enumerate(model.bones) if bone==name],1.,'REPLACE')
    obj.modifiers.new('Original native skin','ARMATURE').object=rig
    obj['meshvenn_workshop_module']=json.dumps(module,sort_keys=True)
    return obj


def export_module(obj,rig,destination):
    if obj.type!='MESH' or obj.data.shape_keys or not obj.data.vertices:
        raise ValueError('Module must be a nonempty mesh without shape keys')
    if any(m.type!='ARMATURE' for m in obj.modifiers):
        raise ValueError('Apply non-armature modifiers before library re-export')
    names={g.index:g.name for g in obj.vertex_groups}
    for vertex in obj.data.vertices:
        weights=[(names[g.group],g.weight) for g in vertex.groups if g.weight>0]
        if (not weights or len(weights)>4 or any(n not in rig.data.bones or not rig.data.bones[n].use_deform or not math.isfinite(w) for n,w in weights)
                or abs(sum(w for _,w in weights)-1)>1e-5):
            raise ValueError('Normalize at most four existing deform-bone weights on every module vertex')
    for item in bpy.context.selected_objects:item.select_set(False)
    obj.hide_set(False);obj.hide_render=False;obj.select_set(True);rig.hide_set(False);rig.select_set(True)
    bpy.context.view_layer.objects.active=obj
    result=bpy.ops.export_scene.gltf(filepath=str(destination),export_format='GLB',use_selection=True,
        export_animations=False,export_apply=False,export_def_bones=False,export_rest_position_armature=True,
        export_current_frame=True,export_extras=False,export_yup=True,export_skins=True)
    if result!={'FINISHED'}:raise RuntimeError('Module export cancelled')


def run(output,from_blend=None):
    if output.exists():raise FileExistsError('Choose a fresh pack output directory')
    previous=json.loads((from_blend.parent/'pack.json').read_text()) if from_blend else None
    if previous:
        target=previous['target'];profile=target['joint_profile'];spec=target
    else:
        if TARGET is None:raise ValueError('Fresh generation needs the source checkout; portable re-export uses --from-blend')
        reference,binary=glb.read(TARGET/'character.glb');profile=glb.joint_profile(reference,binary)
        spec=json.loads((TARGET/'authoring.json').read_text())
        target={'character_sha256':glb.digest(TARGET/'character.glb'),'source_sha256':glb.digest(TARGET/'source.blend'),
                'coordinates':spec['coordinates'],'sockets':spec['sockets'],'joint_profile':profile}
    bpy.ops.wm.open_mainfile(filepath=str(from_blend or TARGET/'source.blend'),use_scripts=False)
    source=bpy.data.objects['MeshvennScan'];rig=source.find_armature()
    source_before=source_snapshot(source,rig)
    if previous and source_before!=previous['target']['source_snapshot_sha256']:raise ValueError('Native body, weights, transforms or rest joints changed')
    target['source_snapshot_sha256']=source_before
    if from_blend:
        objects=[o for o in bpy.context.scene.objects if 'meshvenn_workshop_module' in o]
        modules=[json.loads(o['meshvenn_workshop_module']) for o in objects]
    else:
        from meshvenn_sketch.bridge import native_frame
        from meshvenn_sketch.geometry import ViewFrame
        frame=ViewFrame(*native_frame(source))
        joints={b.name:tuple(source.matrix_world.inverted() @ rig.matrix_world @ b.head_local) for b in rig.data.bones}
        modules=designs(joints,frame);palette=materials()
        collection=bpy.data.collections.new('Stytch Workshop Modules');bpy.context.scene.collection.children.link(collection)
        objects=[create(module,source,rig,palette,collection) for module in modules]
    if len(objects)!=10 or len({m['id'] for m in modules})!=10:raise ValueError('Workshop pack requires ten unique modules')
    sockets={s['id']:s for s in spec['sockets']}
    output.mkdir(parents=True);(output/'skinned').mkdir();(output/'attachments').mkdir()
    manifest={'contract':'meshvenn.sketch.module-pack','version':1,'pack_id':'stytch-workshop-v1',
              'target':target,'modules':[]}
    for obj,module in zip(objects,modules):
        path=output/'skinned'/f"{module['id']}.glb";export_module(obj,rig,path)
        doc,data=glb.read(path);glb.check_rig(doc,data,profile)
        if len(doc['meshes'])!=1 or len(doc['skins'])!=1 or doc.get('animations'):raise ValueError('Invalid module-only export')
        metadata={**module,'contract':'meshvenn.sketch.module-asset','version':1,'target_character_sha256':manifest['target']['character_sha256']}
        glb.module_metadata(path,metadata)
        record={**module,'skinned':{'file':path.relative_to(output).as_posix(),'sha256':glb.digest(path),
            'binding':'reuse-native-skin-by-name','deform_bones':list(obj.vertex_groups.keys())}}
        if module['category']!='replacement':
            static=output/'attachments'/f"{module['id']}.glb"
            mount=glb.attachment(path,static,module,sockets.get(module['socket_id']))
            glb.module_metadata(static,{**metadata,'binding':mount})
            record['attachment']={'file':static.relative_to(output).as_posix(),'sha256':glb.digest(static),'binding':mount}
        manifest['modules'].append(record)
        obj.hide_set(True);obj.hide_render=True
    after=source_snapshot(source,rig)
    if after!=source_before:raise ValueError('Reference source was changed')
    (output/'pack.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    # Open the editable file on the complete loadout, with only replaced body regions hidden.
    for obj in objects:obj.hide_set(False);obj.hide_render=False
    replaced={m['replaces_region'] for m in modules if m['replaces_region']}
    for region,name in (('left-arm','Doll_left_arm'),('right-arm','Doll_right_arm'),('left-leg','Doll_left_leg'),('right-leg','Doll_right_leg')):
        bpy.data.objects[name].hide_set(region in replaced);bpy.data.objects[name].hide_render=region in replaced
    bpy.context.scene['meshvenn_workshop_pack']='pack.json'
    for item in bpy.context.selected_objects:item.select_set(False)
    bpy.context.view_layer.objects.active=None
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'source.blend'))
    print('WORKSHOP AUTHOR PASS:',len(modules),'modules; original 18-joint rest/bind profile retained.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--from-blend',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);run(args.output.resolve(),args.from_blend)
