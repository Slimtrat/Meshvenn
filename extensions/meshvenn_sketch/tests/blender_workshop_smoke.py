"""Gate the delivered module GLBs against editable source and native pose palettes."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix,Vector
from mathutils.kdtree import KDTree

HERE=Path(__file__).resolve().parents[1]/'examples/stytch_workshop'
sys.path.insert(0,str(HERE))
import author
import glb

parser=argparse.ArgumentParser()
parser.add_argument('--pack',type=Path,required=True)
parser.add_argument('--compare-pack',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=args.pack.resolve()
pack=json.loads((folder/'pack.json').read_text())
assert pack['contract']=='meshvenn.sketch.module-pack' and pack['version']==1
assert Counter(m['category'] for m in pack['modules'])=={'equipment':3,'replacement':4,'accessory':3}
assert len({m['id'] for m in pack['modules']})==10
bpy.ops.wm.open_mainfile(filepath=str(folder/'source.blend'),use_scripts=False)
source=bpy.data.objects['MeshvennScan'];rig=source.find_armature()
assert author.source_snapshot(source,rig)==pack['target']['source_snapshot_sha256']
models={json.loads(o['meshvenn_workshop_module'])['id']:o for o in bpy.context.scene.objects if 'meshvenn_workshop_module' in o}
convert=Matrix.Rotation(-math.pi/2,4,'X')


def evaluated(obj):
    bpy.context.view_layer.update()
    evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
    try:return [convert @ evaluated.matrix_world @ v.co for v in mesh.vertices]
    finally:evaluated.to_mesh_clear()


def distance(first,second):
    tree=KDTree(len(second))
    for i,p in enumerate(second):tree.insert(p,i)
    tree.balance()
    return max(tree.find(p)[2] for p in first)


def raw_points(doc,binary,posed=False):
    mesh_index=next(i for i,n in enumerate(doc['nodes']) if 'mesh' in n)
    matrix=glb.worlds(doc)[mesh_index];points=[]
    skinned=bool(doc.get('skins'));world=glb.worlds(doc)
    names=[doc['nodes'][i]['name'] for i in doc['skins'][0]['joints']] if skinned else None
    inverse=[Matrix([v[i:i+4] for i in range(0,16,4)]).transposed() for v in glb.values(doc,binary,doc['skins'][0]['inverseBindMatrices'])] if skinned else None
    for primitive in doc['meshes'][doc['nodes'][mesh_index]['mesh']]['primitives']:
        attr=primitive['attributes'];positions=glb.values(doc,binary,attr['POSITION'])
        if not skinned:points.extend(matrix @ Vector(p) for p in positions);continue
        weights=glb.values(doc,binary,attr['WEIGHTS_0']);joints=glb.values(doc,binary,attr['JOINTS_0'])
        for point,indices,row in zip(positions,joints,weights):
            p=Vector((0,0,0))
            for index,weight in zip(indices,row):
                if weight:
                    joint_world=convert @ rig.matrix_world @ rig.pose.bones[names[index]].matrix if posed else world[doc['skins'][0]['joints'][index]]
                    p+=((joint_world @ inverse[index]) @ Vector(point))*weight
            points.append(p)
    return points


reports=[]
for definition in pack['modules']:
    obj=models[definition['id']];record=definition['skinned'];path=folder/record['file']
    assert path.is_relative_to(folder) and glb.digest(path)==record['sha256']
    doc,binary=glb.read(path);glb.check_rig(doc,binary,pack['target']['joint_profile'])
    assert len(doc['meshes'])==len(doc['skins'])==1 and not doc.get('animations')
    assert doc['asset']['extras']['meshvenn_module_asset']['id']==definition['id']
    edges=Counter(tuple(sorted((a,b))) for f in obj.data.polygons for a,b in zip(tuple(f.vertices),tuple(f.vertices)[1:]+tuple(f.vertices)[:1]))
    assert set(edges.values())=={2},definition['id']+' is not closed'
    assert len(obj.data.uv_layers)==1 and all(math.isfinite(v) for loop in obj.data.uv_layers[0].data for v in loop.uv)
    allowed=set(record['deform_bones']);assert allowed<=set(rig.data.bones.keys())
    for vertex in obj.data.vertices:
        weights=[g for g in vertex.groups if g.weight>0]
        assert 1<=len(weights)<=4 and abs(sum(g.weight for g in weights)-1)<1e-5
        assert all(obj.vertex_groups[g.group].name in allowed for g in weights)
    triangles=sum(len(glb.values(doc,binary,p['indices']))//3 for p in doc['meshes'][0]['primitives'])
    assert triangles<=6000
    expected=evaluated(obj);actual=raw_points(doc,binary)
    error=max(distance(actual,expected),distance(expected,actual));assert error<1e-5,(definition['id'],error)
    if args.compare_pack:
        other=json.loads((args.compare_pack/'pack.json').read_text())
        baseline=next(m for m in other['modules'] if m['id']==definition['id'])
        assert all(baseline[key]==definition[key] for key in ('label','category','parent_joint','owner_region','replaces_region','socket_id'))
        old_doc,old_binary=glb.read(args.compare_pack/baseline['skinned']['file'])
        previous=raw_points(old_doc,old_binary)
        assert max(distance(actual,previous),distance(previous,actual))<1e-5,'Regenerated design differs from committed assets'
    probes=0
    for name in allowed:
        bone=rig.pose.bones[name];bone.rotation_mode='XYZ'
        for angle in (-90,-45,45,90):
            bone.rotation_euler.x=math.radians(angle)
            expected=evaluated(obj);actual=raw_points(doc,binary,posed=True)
            pose_error=max(distance(actual,expected),distance(expected,actual))
            assert pose_error<1e-5,(definition['id'],name,angle,pose_error)
            error=max(error,pose_error);probes+=1
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()
    if 'attachment' in definition:
        record=definition['attachment'];static=folder/record['file']
        assert glb.digest(static)==record['sha256']
        sd,sb=glb.read(static);assert not sd.get('skins') and len(sd['nodes'])==len(sd['meshes'])==1
        mount=Matrix(record['binding']['rest_mount_world'])
        points=[mount @ p for p in raw_points(sd,sb)]
        static_error=max(distance(points,raw_points(doc,binary)),distance(raw_points(doc,binary),points))
        assert static_error<1e-5,(definition['id'],static_error)
        error=max(error,static_error)
    before=set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path),disable_bone_shape=True)
    added=set(bpy.context.scene.objects)-before;meshes=[o for o in added if o.type=='MESH']
    assert len(meshes)==1 and len(meshes[0].find_armature().data.bones)==18
    imported=evaluated(meshes[0]);expected=evaluated(obj)
    import_error=max(distance(imported,expected),distance(expected,imported));assert import_error<1e-5
    for item in added:bpy.data.objects.remove(item,do_unlink=True)
    reports.append({'id':definition['id'],'triangles':triangles,'primitives':len(doc['meshes'][0]['primitives']),
                    'pose_probes':probes,'max_source_raw_error_m':error,'reimport_error_m':import_error})
assert sum(r['triangles'] for r in reports)<25000
assert author.source_snapshot(source,rig)==pack['target']['source_snapshot_sha256']
(folder/'validation.json').write_text(json.dumps({'schema_version':1,'modules':reports,'total_triangles':sum(r['triangles'] for r in reports),
    'target_character_sha256':pack['target']['character_sha256'],'source_preserved':True},indent=2)+'\n',encoding='utf-8')
print('WORKSHOP BLENDER PASS:',len(reports),'modules,',sum(r['pose_probes'] for r in reports),'native pose probes, closed geometry, raw/reimport fidelity and six exact mount-local attachments.')
