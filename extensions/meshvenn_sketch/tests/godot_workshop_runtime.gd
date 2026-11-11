extends SceneTree
const Adapter = preload("res://godot_module_adapter.gd")
func _initialize():call_deferred("check")
func require(condition: bool, message: String) -> bool:
    if condition:return true
    printerr("WORKSHOP RUNTIME FAIL: ",message);quit(1);return false
func check():
    if not require(not FileAccess.file_exists("res://reference.glb"),"Reference GLB leaked into runtime PCK"):return
    var payload = JSON.parse_string(FileAccess.get_file_as_string("res://pack.json"))
    if not require(payload is Dictionary,"Missing runtime manifest"):return
    var pack: Dictionary = payload
    var arguments: PackedStringArray = OS.get_cmdline_user_args()
    if arguments.has("--negative-cache"):pack["modules"][0]["runtime_scene"]["sha256"]="0".repeat(64)
    var reference = load("res://reference.glb")
    if not require(reference is PackedScene,"Reference imported scene is unavailable"):return
    var avatar: Node3D = reference.instantiate()
    root.add_child(avatar)
    if not require(Adapter._skeletons(avatar).size()==1,"Reference native skeleton is unavailable"):return
    var skeleton: Skeleton3D = Adapter._skeletons(avatar)[0]
    var rests: Array = []
    for i in skeleton.get_bone_count():rests.append(skeleton.get_bone_rest(i))
    var count: int = 0;var installed: Array = []
    for definition in pack["modules"]:
        if not require(not FileAccess.file_exists("res://"+definition["skinned"]["file"]),"Module GLB leaked into runtime PCK"):return
        var result: Dictionary = Adapter.mount_skinned(avatar,skeleton,"res://",pack,definition["id"],pack["target"]["character_sha256"])
        if not require(result["ok"],str(result.get("error"))):return
        if not require(Adapter._meshes(result["node"])[0].get_node(Adapter._meshes(result["node"])[0].skeleton)==skeleton,"Wrong runtime skeleton"):return
        installed.append(result);count+=1
    if not require(count==10 and Adapter._skeletons(avatar).size()==1,"Runtime module/rig count changed"):return
    for mask in 16:
        var presence: Dictionary = {"body-core":true,"left-arm":bool(mask&1),"right-arm":bool(mask&2),"left-leg":bool(mask&4),"right-leg":bool(mask&8)}
        for module in installed:
            if not require(Adapter.apply_presence(module,presence)["ok"],"Runtime presence rejected"):return
            if not require(module["node"].visible==presence[module["definition"]["owner_region"]],"Runtime ownership changed"):return
    for i in skeleton.get_bone_count():
        if not require(skeleton.get_bone_rest(i)==rests[i],"Runtime native rest changed"):return
    print("WORKSHOP SOURCE-FREE PCK PASS: ten modules on one existing skeleton, zero source GLBs available.")
    if not arguments.is_empty():
        var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
        report["source_free_pck"]=true;report["source_glbs_available"]=false;report["runtime_modules"]=count
        report["runtime_owner_presence_checks"]=160;report["runtime_native_rests_preserved"]=true
        var file := FileAccess.open(arguments[0],FileAccess.WRITE)
        file.store_string(JSON.stringify(report,"  ")+"\n");file.close()
    avatar.free();quit(0)
