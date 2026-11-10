"""Own-mesh creation and dimensions; reference mesh, rig and pixels stay intact."""
from dataclasses import asdict
import hashlib
import json

import bpy

from .bridge import IMAGE_REF,RECIPE,SIGNATURE,SOURCE_REF,depth_anchor,draft_frame,read_recipe,rig_for,source_mesh
from .geometry import ViewFrame,extrude


def mesh_signature(mesh):
    state=([tuple(v.co) for v in mesh.vertices],[tuple(p.vertices) for p in mesh.polygons],
           [[tuple(p.uv) for p in layer.data] for layer in mesh.uv_layers])
    return hashlib.sha256(json.dumps(state,allow_nan=False).encode()).hexdigest()


def _geometry(recipe):
    frame=ViewFrame(**recipe['frame'])
    return extrude(recipe['points'],frame,recipe['anchor'],recipe['thickness']*frame.size[2],recipe['depth']*frame.size[2])


def _collection(context):
    scene=context.scene
    for collection in scene.collection.children:
        if collection.get('mvsketch_owned_collection')==1:
            layer=context.view_layer.layer_collection.children.get(collection.name)
            if collection.hide_viewport or layer is None or layer.exclude or layer.hide_viewport:
                raise ValueError('Unhide the Meshvenn Sketch collection in this view layer before creating a piece.')
            return collection,False
    collection=bpy.data.collections.new('Meshvenn Sketch')
    collection['mvsketch_owned_collection']=1
    scene.collection.children.link(collection)
    return collection,True


def create_piece(context,settings):
    if context.mode!='OBJECT':raise ValueError('Create pieces in Object mode.')
    frame=draft_frame(settings);source=source_mesh(settings)
    rig=rig_for(source) if settings.bind_to_rig else None
    if settings.bind_to_rig and rig is None:raise ValueError('Source has no rig. Disable Bind to Bone for an unskinned piece.')
    if rig is not None and (rig.library or rig.data.library):raise ValueError('Use a local editable rig.')
    name=settings.name.strip()
    if not name:raise ValueError('Give this piece a name.')
    recipe={'schema_version':1,'points':[tuple(p.uv) for p in settings.contour],'frame':asdict(frame),
        'anchor':depth_anchor(source,rig,settings.bone,frame),'thickness':float(settings.thickness),
        'depth':float(settings.depth),'edge':float(settings.edge),'source_name':source.name,'image_name':settings.image.name,
        'binding_bone':settings.bone if rig else None,'calibration':json.loads(settings.frame_json)}
    points,vertices,faces,uvs=_geometry(recipe);recipe['points']=points
    mesh=obj=material=collection=None;new_collection=False
    selected,active,old_piece=tuple(context.selected_objects),context.view_layer.objects.active,settings.piece
    try:
        mesh=bpy.data.meshes.new(name+'.Mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
        layer=mesh.uv_layers.new(name='Sketch UV')
        for polygon,face_uv in zip(mesh.polygons,uvs):
            for index,uv in zip(polygon.loop_indices,face_uv):layer.data[index].uv=uv
            polygon.use_smooth=True
        material=bpy.data.materials.new(name+'.Material');material.diffuse_color=tuple(settings.color)
        material.use_nodes=True
        material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=tuple(settings.color)
        material.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.65
        mesh.materials.append(material)
        obj=bpy.data.objects.new(name,mesh)
        obj.parent=source.parent;obj.parent_type=source.parent_type
        if source.parent_type!='OBJECT':raise ValueError('Source bone/vertex parenting requires explicit rest-space authoring.')
        obj.matrix_world=source.matrix_world.copy()
        bevel=obj.modifiers.new('Sketch Rounded Edges','BEVEL')
        bevel.width=settings.edge*frame.size[2];bevel.segments=3;bevel.limit_method='ANGLE';bevel.use_clamp_overlap=True
        bevel.harden_normals=True
        if rig:
            obj.vertex_groups.new(name=settings.bone).add(list(range(len(mesh.vertices))),1.,'REPLACE')
            modifier=obj.modifiers.new('Sketch Skin','ARMATURE');modifier.object=rig
        obj[RECIPE]=json.dumps(recipe,allow_nan=False);obj[SIGNATURE]=mesh_signature(mesh)
        obj[SOURCE_REF]=source;obj[IMAGE_REF]=settings.image
        collection,new_collection=_collection(context);collection.objects.link(obj)
        context.view_layer.update()
        if context.view_layer.objects.get(obj.name) is not obj:raise ValueError('New piece is excluded from the active view layer.')
        for area in context.screen.areas if context.screen else ():
            if area.type=='VIEW_3D' and area.spaces.active.local_view and source.local_view_get(area.spaces.active):
                obj.local_view_set(area.spaces.active,True)
        for item in context.selected_objects:item.select_set(False)
        obj.select_set(True);context.view_layer.objects.active=obj;settings.piece=obj
    except BaseException:
        if obj is not None:bpy.data.objects.remove(obj,do_unlink=True)
        if mesh is not None and mesh.users==0:bpy.data.meshes.remove(mesh)
        if material is not None and material.users==0:bpy.data.materials.remove(material)
        if collection is not None and new_collection and not collection.objects:bpy.data.collections.remove(collection)
        for item in context.selected_objects:item.select_set(False)
        for item in selected:item.select_set(True)
        context.view_layer.objects.active=active;settings.piece=old_piece
        raise
    return obj


def update_dimensions(obj,settings):
    recipe=read_recipe(obj)
    if obj.mode!='OBJECT' or obj.data.users!=1 or obj.data.shape_keys:
        raise ValueError('Use a single-user piece without shape keys, in Object mode.')
    if mesh_signature(obj.data)!=obj.get(SIGNATURE):
        raise ValueError('Geometry/UVs were edited manually. Keep those edits; create another piece or edit dimensions in Blender.')
    recipe.update(thickness=float(settings.thickness),depth=float(settings.depth),edge=float(settings.edge))
    _,vertices,faces,_=_geometry(recipe)
    if len(vertices)!=len(obj.data.vertices) or tuple(tuple(p.vertices) for p in obj.data.polygons)!=faces:
        raise ValueError('Contour changed; create a new piece to preserve existing painted weights.')
    original=obj.data;staged=original.copy();old_recipe,old_signature=obj[RECIPE],obj[SIGNATURE]
    bevel=next((m for m in obj.modifiers if m.name=='Sketch Rounded Edges' and m.type=='BEVEL'),None)
    old_width=bevel.width if bevel else None
    if bevel is None and recipe['edge']>0:
        bpy.data.meshes.remove(staged)
        raise ValueError('Rounded-edge modifier was removed or renamed; restore it before applying procedural roundness.')
    try:
        staged.vertices.foreach_set('co',[value for p in vertices for value in p]);staged.update()
        obj.data=staged;obj[RECIPE]=json.dumps(recipe,allow_nan=False);obj[SIGNATURE]=mesh_signature(staged)
        if bevel:bevel.width=recipe['edge']*ViewFrame(**recipe['frame']).size[2]
    except BaseException:
        obj.data=original;obj[RECIPE]=old_recipe;obj[SIGNATURE]=old_signature
        if bevel:bevel.width=old_width
        if staged.users==0:bpy.data.meshes.remove(staged)
        raise
    if original.users==0:bpy.data.meshes.remove(original)
    return obj


def load_piece(settings,obj):
    recipe=read_recipe(obj);settings.piece=obj
    source,image=obj.get(SOURCE_REF),obj.get(IMAGE_REF)
    settings.source=source;settings.calibrated_source=source
    settings.image=image;settings.calibrated_image=image
    settings.frame_json=json.dumps(recipe['calibration']);settings.calibration_label='Saved piece view'
    frame=ViewFrame(**recipe['frame'])
    import math
    settings.azimuth=math.radians(frame.azimuth);settings.elevation=math.radians(frame.elevation);settings.flip_x=frame.flip_x
    settings.name=obj.name;settings.thickness=recipe['thickness'];settings.depth=recipe['depth'];settings.edge=recipe['edge']
    settings.bone=recipe['binding_bone'] or '';settings.bind_to_rig=recipe['binding_bone'] is not None
    settings.contour.clear()
    for uv in recipe['points']:settings.contour.add().uv=uv
    return obj
