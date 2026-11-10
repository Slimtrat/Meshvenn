"""Selected-piece GLB publication; no body, clips or implicit source edits."""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile

import bpy

from .bridge import read_recipe,rig_for


def _digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_skin(obj,rig):
    names={g.index:g.name for g in obj.vertex_groups}
    deform={b.name for b in rig.data.bones if b.use_deform}
    for vertex in obj.data.vertices:
        weights=[(names[g.group],float(g.weight)) for g in vertex.groups if g.weight>0]
        if (not weights or len(weights)>4 or any(n not in deform for n,_ in weights)
                or abs(sum(w for _,w in weights)-1)>1e-5):
            raise ValueError('Normalize every vertex to at most four deform-bone weights before export.')


def _validate_glb(path,obj,rig):
    data=path.read_bytes()
    if len(data)<20 or struct.unpack_from('<4sII',data)!=(b'glTF',2,len(data)):
        raise ValueError('Exporter did not produce a complete GLB 2.0 file.')
    length,kind=struct.unpack_from('<II',data,12)
    if kind!=0x4E4F534A:raise ValueError('GLB has no JSON header.')
    doc=json.loads(data[20:20+length])
    if len(doc.get('meshes',[]))!=1 or doc.get('animations'):
        raise ValueError('Piece export must contain exactly one mesh and no animation clips.')
    if rig:
        skins=doc.get('skins',[])
        if len(skins)!=1:raise ValueError('Piece lost its skin binding.')
        names=[doc['nodes'][i]['name'] for i in skins[0]['joints']]
        if len(names)!=len(rig.data.bones) or set(names)!=set(rig.data.bones.keys()):
            raise ValueError('Piece export changed the rig bone names or joint count.')
    elif doc.get('skins'):raise ValueError('Unexpected skin on an unbound piece.')
    return doc


def export_piece(context,obj,filepath,*,overwrite=False):
    read_recipe(obj)
    if context.mode!='OBJECT' or obj.mode!='OBJECT':raise ValueError('Export the piece in Object mode.')
    if obj.data.shape_keys:raise ValueError('This static-piece export does not discard shape keys; use Blender export for morph assets.')
    if not obj.data.vertices or any(not math.isfinite(v) for p in obj.data.vertices for v in p.co):
        raise ValueError('Piece geometry must be nonempty and finite.')
    rig=rig_for(obj)
    if any(m.type=='ARMATURE' and m.object is None for m in obj.modifiers):raise ValueError('Piece rig is missing; restore its Armature binding first.')
    if rig:_validate_skin(obj,rig)
    destination=Path(bpy.path.abspath(filepath)).resolve()
    if destination.suffix.lower()!='.glb' or not destination.parent.is_dir():
        raise ValueError('Choose a .glb file in an existing directory.')
    if destination.exists() and not overwrite:raise FileExistsError('File exists; explicitly enable Replace Existing File.')
    previous=_digest(destination) if destination.exists() else None
    selected=tuple(context.selected_objects);active=context.view_layer.objects.active
    frame=context.scene.frame_current;subframe=context.scene.frame_subframe
    bases={b.name:b.matrix_basis.copy() for b in rig.pose.bones} if rig else {}
    pose_position=rig.data.pose_position if rig else None
    staged=None
    try:
        for item in selected:item.select_set(False)
        obj.select_set(True)
        if rig:rig.select_set(True)
        context.view_layer.objects.active=obj
        with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='.meshvenn-sketch-',suffix='.glb',delete=False) as stream:
            staged=Path(stream.name)
        result=bpy.ops.export_scene.gltf(filepath=str(staged),export_format='GLB',use_selection=True,
            export_animations=False,export_apply=True,export_def_bones=False,
            export_rest_position_armature=True,export_current_frame=True,export_extras=False,
            export_yup=True,export_skins=True)
        if result!={'FINISHED'}:raise ValueError('Blender GLB export was cancelled.')
        _validate_glb(staged,obj,rig)
        if (destination.exists() and _digest(destination)!=previous) or (previous is not None and not destination.exists()):
            raise ValueError('Destination changed during export; no file was replaced.')
        if overwrite:os.replace(staged,destination)
        else:os.link(staged,destination)
        return destination
    finally:
        if staged is not None and staged.exists():staged.unlink()
        if context.scene.frame_current!=frame or context.scene.frame_subframe!=subframe:context.scene.frame_set(frame,subframe=subframe)
        if rig:
            for bone in rig.pose.bones:bone.matrix_basis=bases[bone.name]
            rig.data.pose_position=pose_position
            context.view_layer.update()
        for item in context.selected_objects:item.select_set(False)
        for item in selected:
            if context.view_layer.objects.get(item.name) is item:item.select_set(True)
        if active is not None and context.view_layer.objects.get(active.name) is active:context.view_layer.objects.active=active
