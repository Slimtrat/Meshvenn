extends SceneTree
const Adapter = preload("res://godot_module_adapter.gd")

func _initialize():call_deferred("check")

func require(condition: bool, message: String):
    if not condition:
        printerr("WORKSHOP GODOT FAIL: ",message)
        quit(1)
        assert(false,message)

func check():
    var pack: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://pack.json"))
    var avatar: Node3D = load("res://reference.glb").instantiate()
    root.add_child(avatar)
    var skeleton: Skeleton3D = Adapter._skeletons(avatar)[0]
    var rests: Array = []
    for i in skeleton.get_bone_count():rests.append(skeleton.get_bone_rest(i))
    var installed: Array = []
    for definition in pack["modules"]:
        var result: Dictionary = Adapter.mount_skinned(avatar,skeleton,"res://",pack,definition["id"],pack["target"]["character_sha256"])
        require(result["ok"],str(result.get("error")))
        installed.append(result)
        var meshes: Array = Adapter._meshes(result["node"])
        require(meshes.size()==1,"Unexpected surface count")
        require(meshes[0].get_node(meshes[0].skeleton)==skeleton,"Equipment retained another skeleton")
        require(meshes[0].skin.get_bind_count()==18,"A native bind disappeared")
        var template: Node3D = load("res://"+definition["skinned"]["file"]).instantiate()
        var template_mesh: MeshInstance3D = Adapter._meshes(template)[0]
        require(meshes[0].get_active_material(0)!=template_mesh.get_active_material(0),"Module materials are shared between characters")
        template.free()
    require(Adapter._skeletons(avatar).size()==1,"Duplicate native skeleton survived installation")
    for mask in 16:
        var presence: Dictionary = {"body-core":true,"left-arm":bool(mask&1),"right-arm":bool(mask&2),"left-leg":bool(mask&4),"right-leg":bool(mask&8)}
        for module in installed:
            require(Adapter.apply_presence(module,presence)["ok"],"Presence frame rejected")
            require(module["node"].visible==presence[module["definition"]["owner_region"]],"Absent anatomy resurrected equipment")
    var child_count: int = avatar.get_child_count()
    require(not Adapter.mount_skinned(avatar,skeleton,"res://",pack,pack["modules"][0]["id"],pack["target"]["character_sha256"])["ok"],"Duplicate module accepted")
    require(not Adapter.mount_skinned(avatar,skeleton,"res://",pack,"unknown",pack["target"]["character_sha256"])["ok"],"Unknown module accepted")
    require(not Adapter.mount_skinned(avatar,skeleton,"res://",pack,pack["modules"][0]["id"],"foreign-character")["ok"],"Foreign asset accepted")
    require(avatar.get_child_count()==child_count,"Rejected installation leaked nodes")
    var static_count: int = 0
    for definition in pack["modules"]:
        if not definition.has("attachment"):continue
        var attachment: Node3D = load("res://"+definition["attachment"]["file"]).instantiate()
        require(Adapter._skeletons(attachment).is_empty() and Adapter._meshes(attachment).size()==1,"Static attachment contains a rig or body")
        attachment.free();static_count+=1
    require(static_count==6,"Static attachment variants are incomplete")
    for i in skeleton.get_bone_count():require(skeleton.get_bone_rest(i)==rests[i],"Original native rest changed")
    var forearm: int = skeleton.find_bone("forearm.L")
    skeleton.set_bone_pose_rotation(forearm,Quaternion(Vector3.RIGHT,PI/2))
    skeleton.force_update_all_bone_transforms()
    require(skeleton.get_bone_global_pose(forearm)!=skeleton.get_bone_global_rest(forearm),"Native control did not move")
    for module in installed:module["node"].free()
    require(Adapter._skeletons(avatar).size()==1 and skeleton.get_bone_count()==18,"Uninstall changed the native rig")
    print("WORKSHOP GODOT PASS: ten real GLBs installed on one native skeleton, 160 owner-presence checks, native pose control, exact rests and rejected foreign IDs.")
    var report: Dictionary = {"schema_version":1,"godot_version":Engine.get_version_info()["string"],"target_character_sha256":pack["target"]["character_sha256"],
        "skinned_modules":installed.size(),"static_attachments":static_count,"native_skeletons":1,"owner_presence_checks":160,"native_rests_preserved":true}
    var report_file := FileAccess.open("res://godot-validation.json",FileAccess.WRITE)
    report_file.store_string(JSON.stringify(report,"  ")+"\n");report_file.close()
    avatar.free();quit(0)
