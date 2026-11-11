class_name MeshvennWorkshopModules
extends RefCounted
## Asset adapter only. The caller owns loadouts, region presence and replacement visibility.
## avatar_root is the imported character scene root, including its original normalization.

static func _failure(staging: Node, message: String) -> Dictionary:
    if is_instance_valid(staging):staging.free()
    return {"ok":false,"error":message}

static func _skeletons(node: Node) -> Array:
    var found: Array = []
    if node is Skeleton3D:found.append(node)
    for child in node.get_children():found.append_array(_skeletons(child))
    return found

static func _meshes(node: Node) -> Array:
    var found: Array = []
    if node is MeshInstance3D:found.append(node)
    for child in node.get_children():found.append_array(_meshes(child))
    return found

static func _near(a: Transform3D, b: Transform3D) -> bool:
    return a.origin.distance_to(b.origin)<0.00003 and (a.basis.x-b.basis.x).length()<0.00003 and (a.basis.y-b.basis.y).length()<0.00003 and (a.basis.z-b.basis.z).length()<0.00003

static func mount_skinned(avatar_root: Node3D, skeleton: Skeleton3D, pack_root: String,
        pack: Dictionary, module_id: String, character_sha256: String) -> Dictionary:
    if not is_instance_valid(avatar_root) or not is_instance_valid(skeleton) or not avatar_root.is_ancestor_of(skeleton):
        return _failure(null,"Pass the original imported avatar root and its native skeleton")
    if pack.get("contract")!="meshvenn.sketch.module-pack" or pack.get("version")!=1:
        return _failure(null,"Unsupported module pack")
    if pack.get("target",{}).get("character_sha256")!=character_sha256:
        return _failure(null,"Module pack targets another character")
    var matches: Array = pack.get("modules",[]).filter(func(item):return item.get("id")==module_id)
    if matches.size()!=1:return _failure(null,"Module ID is missing or ambiguous")
    var definition: Dictionary = matches[0]
    for child in avatar_root.get_children():
        if child.get_meta("meshvenn_module_id","")==module_id:
            return _failure(null,"Module is already installed")
        if definition["replaces_region"]!=null and child.get_meta("meshvenn_replaces_region","")==definition["replaces_region"]:
            return _failure(null,"A replacement already owns this region")
    var filename: String = definition.get("skinned",{}).get("file","")
    if not filename.begins_with("skinned/") or ".." in filename or filename.contains("\\"):
        return _failure(null,"Invalid module asset path")
    var path: String = pack_root.path_join(filename)
    if FileAccess.get_sha256(path)!=definition["skinned"]["sha256"]:
        return _failure(null,"Module GLB fingerprint changed")
    var resource = load(path)
    if not resource is PackedScene:return _failure(null,"Module GLB is not an imported PackedScene")
    var staging: Node3D = resource.instantiate()
    staging.visible=false;avatar_root.add_child(staging)
    var candidates: Array = _skeletons(staging)
    var meshes: Array = _meshes(staging)
    if candidates.size()!=1 or meshes.size()!=1:return _failure(staging,"Expected one module mesh and one native skin")
    var original: Skeleton3D = candidates[0]
    if original.get_bone_count()!=skeleton.get_bone_count():return _failure(staging,"Native joint count changed")
    var relative: Transform3D = avatar_root.global_transform.affine_inverse()
    for i in original.get_bone_count():
        var name: String = original.get_bone_name(i)
        var target: int = skeleton.find_bone(name)
        if target<0:return _failure(staging,"Missing native joint: "+name)
        var parent: int = original.get_bone_parent(i)
        var target_parent: int = skeleton.get_bone_parent(target)
        if (parent<0)!=(target_parent<0):return _failure(staging,"Native root changed")
        if parent>=0 and original.get_bone_name(parent)!=skeleton.get_bone_name(target_parent):
            return _failure(staging,"Native joint hierarchy changed")
        if not _near(relative*original.global_transform*original.get_bone_global_rest(i),relative*skeleton.global_transform*skeleton.get_bone_global_rest(target)):
            return _failure(staging,"Native rest or normalization changed: "+name)
    var mesh: MeshInstance3D = meshes[0]
    if mesh.skin==null or mesh.skin.get_bind_count()!=skeleton.get_bone_count():return _failure(staging,"Native bind set changed")
    var body_meshes: Array = _meshes(skeleton).filter(func(item):return item.skin!=null)
    if body_meshes.is_empty():return _failure(staging,"Original native body skin is required")
    var reference: Skin = body_meshes[0].skin
    var reference_by_name: Dictionary = {}
    for i in reference.get_bind_count():reference_by_name[str(reference.get_bind_name(i))]=reference.get_bind_pose(i)
    var rebound: Skin = Skin.new()
    for i in mesh.skin.get_bind_count():
        var name: String = str(mesh.skin.get_bind_name(i))
        if not reference_by_name.has(name) or not _near(mesh.skin.get_bind_pose(i),reference_by_name[name]):
            return _failure(staging,"Native inverse bind changed: "+name)
        rebound.add_named_bind(name,mesh.skin.get_bind_pose(i))
    var container := Node3D.new()
    container.name="MeshvennModule_"+module_id;avatar_root.add_child(container)
    mesh.reparent(container,true);mesh.skin=rebound;mesh.skeleton=mesh.get_path_to(skeleton)
    for surface in mesh.mesh.get_surface_count():
        var material: Material = mesh.get_active_material(surface)
        if material!=null:mesh.set_surface_override_material(surface,material.duplicate())
    mesh.visible=true;staging.free()
    container.set_meta("meshvenn_module_id",module_id)
    container.set_meta("meshvenn_owner_region",definition["owner_region"])
    container.set_meta("meshvenn_replaces_region",definition["replaces_region"])
    return {"ok":true,"node":container,"definition":definition}

static func apply_presence(installed: Dictionary, region_visibility: Dictionary) -> Dictionary:
    if not installed.get("ok",false) or not is_instance_valid(installed.get("node")):
        return {"ok":false,"error":"Module is not installed"}
    var owner: String = installed["definition"]["owner_region"]
    if not region_visibility.has(owner) or typeof(region_visibility[owner])!=TYPE_BOOL:
        return {"ok":false,"error":"An explicit owner-region presence value is required"}
    installed["node"].visible=region_visibility[owner]
    return {"ok":true}
