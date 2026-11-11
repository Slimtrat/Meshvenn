extends SceneTree
## Run in the fresh prepared project after compile_runtime.gd. Original assets are read-only.
const Adapter = preload("res://godot_module_adapter.gd")

var _base_pack: Dictionary
var _definition: Dictionary
var _avatar: Node3D
var _skeleton: Skeleton3D
var _fixture_root: String
var _raw_path: String
var _cache_path: String
var _raw_backup: PackedByteArray
var _cache_backup: PackedByteArray
var _native_before: Array
var _children_before: int
var _cases: int = 0

func _initialize():call_deferred("_run")

func _write(path: String, bytes: PackedByteArray) -> bool:
    var file := FileAccess.open(path,FileAccess.WRITE)
    if file==null:return false
    file.store_buffer(bytes);file.close();return true

func _restore() -> bool:
    var success: bool = true
    if not _raw_path.is_empty():success=_write(_raw_path,_raw_backup) and success
    if not _cache_path.is_empty():success=_write(_cache_path,_cache_backup) and success
    return success

func _remove_fixture() -> bool:
    if not _fixture_root.begins_with("res://_workshop_cache_probe_"):return false
    if not _raw_path.begins_with(_fixture_root+"/") or not _cache_path.begins_with(_fixture_root+"/"):return false
    for path in [_raw_path,_cache_path]:
        if DirAccess.remove_absolute(path)!=OK:return false
    for path in [_raw_path.get_base_dir(),_cache_path.get_base_dir(),_fixture_root]:
        if DirAccess.remove_absolute(path)!=OK:return false
    return true

func _fatal(message: String) -> bool:
    _restore()
    if is_instance_valid(_avatar):_avatar.free()
    printerr("WORKSHOP CACHE FAIL: ",message)
    quit(1)
    return false

func _require(condition: bool, message: String) -> bool:
    if not condition:return _fatal(message)
    return true

func _snapshot() -> Array:
    var values: Array = []
    for i in _skeleton.get_bone_count():
        values.append([_skeleton.get_bone_name(i),_skeleton.get_bone_parent(i),
            _skeleton.get_bone_rest(i),_skeleton.get_bone_pose_position(i),
            _skeleton.get_bone_pose_rotation(i),_skeleton.get_bone_pose_scale(i)])
    for mesh in Adapter._meshes(_skeleton):
        values.append([mesh.get_instance_id(),mesh.transform,mesh.skin.get_instance_id()])
        var binds: Array = []
        for i in mesh.skin.get_bind_count():binds.append([mesh.skin.get_bind_name(i),mesh.skin.get_bind_bone(i),mesh.skin.get_bind_pose(i)])
        values.append(binds)
        for i in mesh.mesh.get_surface_count():
            var material: Material = mesh.get_active_material(i)
            values.append(material.get_instance_id() if material!=null else 0)
            if material is BaseMaterial3D:
                values.append([material.albedo_color,material.metallic,material.roughness,
                    material.albedo_texture.get_instance_id() if material.albedo_texture!=null else 0])
    return values

func _record() -> Dictionary:
    return _definition.duplicate(true)

func _mount(record: Dictionary) -> Dictionary:
    var manifest: Dictionary = _base_pack.duplicate(true)
    manifest["modules"]=[record]
    return Adapter.mount_skinned(_avatar,_skeleton,_fixture_root,manifest,record["id"],manifest["target"]["character_sha256"])

func _unchanged() -> bool:
    return _require(_avatar.get_child_count()==_children_before and _snapshot()==_native_before,
        "Rejected installation changed the native actor or leaked staging nodes")

func _reject(record: Dictionary, label: String) -> bool:
    var result: Dictionary = _mount(record)
    if result.get("ok",false):
        if is_instance_valid(result.get("node")):result["node"].free()
        return _fatal("Accepted "+label)
    if not _require(not str(result.get("error","")).is_empty(),"Missing rejection reason for "+label):return false
    if not _unchanged():return false
    if not _require(_restore(),"Could not restore isolated cache fixture"):return false
    _cases+=1
    return true

func _own_children(node: Node, owner: Node):
    for child in node.get_children():
        child.owner=owner;_own_children(child,owner)

func _variant(change: Callable) -> bool:
    var resource: Resource = ResourceLoader.load(_cache_path,"PackedScene",ResourceLoader.CACHE_MODE_IGNORE)
    if not _require(resource is PackedScene,"Could not load isolated valid cache"):return false
    var instance: Node3D = (resource as PackedScene).instantiate()
    instance.scene_file_path="";_own_children(instance,instance);change.call(instance)
    var scene := PackedScene.new()
    var packed: int = scene.pack(instance)
    if packed!=OK:
        instance.free();return _fatal("Could not construct cache mutation")
    var saved: int = ResourceSaver.save(scene,_cache_path,ResourceSaver.FLAG_BUNDLE_RESOURCES|ResourceSaver.FLAG_COMPRESS)
    instance.free()
    return _require(saved==OK,"Could not save cache mutation")

func _bad_stamp(key: String, value: String) -> bool:
    if not _variant(func(node):node.set_meta(key,value)):return false
    var record: Dictionary = _record()
    record["runtime_scene"]["sha256"]=FileAccess.get_sha256(_cache_path)
    return _reject(record,"cache with a foreign "+key+" stamp and recomputed SHA")

func _run():
    _base_pack=JSON.parse_string(FileAccess.get_file_as_string("res://pack.json"))
    if not _require(not _base_pack.get("modules",[]).is_empty(),"No module definitions"):return
    _definition=_base_pack["modules"][0].duplicate(true)
    if not _require(_definition.has("runtime_scene"),"compile_runtime.gd must run before this test"):return
    _raw_backup=FileAccess.get_file_as_bytes("res://"+_definition["skinned"]["file"])
    _cache_backup=FileAccess.get_file_as_bytes("res://"+_definition["runtime_scene"]["file"])
    if not _require(not _raw_backup.is_empty() and not _cache_backup.is_empty(),"Raw/compiled fixture missing"):return
    _fixture_root="res://_workshop_cache_probe_"+str(Time.get_ticks_usec())
    _raw_path=_fixture_root.path_join(_definition["skinned"]["file"])
    _cache_path=_fixture_root.path_join(_definition["runtime_scene"]["file"])
    if not _require(DirAccess.make_dir_recursive_absolute(_raw_path.get_base_dir())==OK and DirAccess.make_dir_recursive_absolute(_cache_path.get_base_dir())==OK,"Cannot create isolated fixture directories"):return
    if not _require(_restore(),"Cannot create isolated fixtures"):return
    var reference: Resource = load("res://reference.glb")
    if not _require(reference is PackedScene,"Reference actor could not load"):return
    _avatar=(reference as PackedScene).instantiate();root.add_child(_avatar)
    var skeletons: Array = Adapter._skeletons(_avatar)
    if not _require(skeletons.size()==1,"Reference actor has ambiguous skeletons"):return
    _skeleton=skeletons[0];_native_before=_snapshot();_children_before=_avatar.get_child_count()
    var control: Dictionary = _mount(_record())
    if not _require(control.get("ok",false),"Valid copied cache rejected: "+str(control.get("error"))):return
    control["node"].free()
    if not _unchanged():return

    var record: Dictionary = _record()
    record["runtime_scene"]["sha256"]="0".repeat(64)
    if not _reject(record,"wrong compiled SHA"):return
    if not _require(DirAccess.remove_absolute(_cache_path)==OK,"Cannot remove test cache"):return
    if not _reject(_record(),"missing cache"):return
    if not _require(_write(_cache_path,_cache_backup.slice(0,8)),"Cannot truncate isolated cache"):return
    if not _reject(_record(),"truncated cache"):return
    var raw_changed: PackedByteArray = _raw_backup.duplicate()
    raw_changed[raw_changed.size()-1]=raw_changed[raw_changed.size()-1]^1
    if not _require(_write(_raw_path,raw_changed),"Cannot mutate isolated GLB"):return
    if not _reject(_record(),"changed GLB source"):return
    if not _bad_stamp("meshvenn_module_source_sha256","1".repeat(64)):return
    if not _bad_stamp("meshvenn_target_character_sha256","2".repeat(64)):return
    if not _bad_stamp("meshvenn_module_id","foreign-module"):return

    # Keep a strong reference to the cached valid PackedScene, then replace its file.
    var primed: Resource = ResourceLoader.load(_cache_path,"PackedScene",ResourceLoader.CACHE_MODE_REUSE)
    if not _require(primed is PackedScene,"Cannot prime ResourceLoader cache"):return
    if not _bad_stamp("meshvenn_module_source_sha256","3".repeat(64)):return

    if not _variant(func(node):
        var mesh: MeshInstance3D = Adapter._meshes(node)[0]
        mesh.skin=mesh.skin.duplicate()
        mesh.skin.set_bind_name(1,mesh.skin.get_bind_name(0))
        mesh.skin.set_bind_pose(1,mesh.skin.get_bind_pose(0))
    ):return
    record=_record();record["runtime_scene"]["sha256"]=FileAccess.get_sha256(_cache_path)
    if not _reject(record,"duplicate/missing native bind names"):return
    if not _require(_restore(),"Final fixture restoration failed"):return
    if not _require(FileAccess.get_file_as_bytes(_raw_path)==_raw_backup and FileAccess.get_file_as_bytes(_cache_path)==_cache_backup,"Fixture bytes changed after cleanup"):return
    if not _unchanged():return
    primed=null
    if not _remove_fixture():
        printerr("WORKSHOP CACHE FAIL: Cannot remove owned test fixture")
        _avatar.free();quit(1);return
    _avatar.free()
    print("WORKSHOP CACHE PASS: ",_cases," stale/foreign/tampered cache rejections, restored fixture bytes and unchanged native actor.")
    quit(0)
