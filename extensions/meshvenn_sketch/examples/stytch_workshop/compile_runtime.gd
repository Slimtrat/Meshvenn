extends SceneTree
## Build immutable, self-contained runtime scenes while the verified source GLBs exist.
func _initialize():call_deferred("build")

func require(condition: bool, message: String) -> bool:
    if condition:return true
    printerr("WORKSHOP COMPILE FAIL: ",message);quit(1);return false

func import_is_current(source: String) -> bool:
    var config := ConfigFile.new()
    if config.load(source+".import")!=OK:return false
    var imported: String = config.get_value("remap","path","")
    var destinations = config.get_value("deps","dest_files",PackedStringArray())
    if imported.is_empty() or destinations.size()!=1 or destinations[0]!=imported or not FileAccess.file_exists(imported):return false
    var sidecar: String = imported.get_basename()+".md5"
    if not FileAccess.file_exists(sidecar):return false
    var hashes: String = FileAccess.get_file_as_string(sidecar)
    var pattern := RegEx.new()
    pattern.compile('source_md5\\s*=\\s*"([0-9a-f]{32})"')
    var found = pattern.search(hashes)
    if found==null or found.get_string(1)!=FileAccess.get_md5(source):return false
    pattern.compile('dest_md5\\s*=\\s*"([0-9a-f]{32})"')
    found=pattern.search(hashes)
    return found!=null and found.get_string(1)==FileAccess.get_md5(imported)

func save_scene(resource: Resource, path: String, stamp: Dictionary) -> bool:
    if not require(resource is PackedScene,"Imported module scene is missing"):return false
    var node: Node3D = resource.instantiate()
    node.scene_file_path=""
    own_children(node,node)
    for key in stamp:node.set_meta(key,stamp[key])
    var compiled := PackedScene.new()
    if not require(compiled.pack(node)==OK,"Could not compile native module scene"):
        node.free();return false
    if not require(ResourceSaver.save(compiled,path,ResourceSaver.FLAG_BUNDLE_RESOURCES|ResourceSaver.FLAG_COMPRESS)==OK,"Could not save native module scene"):
        node.free();return false
    node.free()
    return true

func own_children(node: Node, owner: Node):
    for child in node.get_children():
        child.owner=owner;own_children(child,owner)

func build():
    var arguments: PackedStringArray = OS.get_cmdline_user_args()
    var base: String = arguments[0] if not arguments.is_empty() else "res://"
    var path: String = base.path_join("pack.json")
    var payload = JSON.parse_string(FileAccess.get_file_as_string(path))
    if not require(payload is Dictionary,"Module manifest is missing"):return
    var pack: Dictionary = payload
    DirAccess.make_dir_recursive_absolute(base.path_join("runtime"))
    for definition in pack["modules"]:
        var source: String = base.path_join(definition["skinned"]["file"])
        if not require(FileAccess.get_sha256(source)==definition["skinned"]["sha256"],"Module bytes changed before compilation"):return
        if not import_is_current(source):
            printerr("WORKSHOP COMPILE FAIL: imported scene is stale; run Godot --editor --import first")
            quit(1);return
        var output: String = "runtime/"+definition["id"]+".scn"
        if not save_scene(ResourceLoader.load(source,"PackedScene",ResourceLoader.CACHE_MODE_IGNORE_DEEP),base.path_join(output),{
            "meshvenn_module_source_sha256":definition["skinned"]["sha256"],
            "meshvenn_module_id":definition["id"],"meshvenn_target_character_sha256":pack["target"]["character_sha256"]}):return
        definition["runtime_scene"]={"file":output,"sha256":FileAccess.get_sha256(base.path_join(output)),
            "source_sha256":definition["skinned"]["sha256"],"godot_version":Engine.get_version_info()["string"]}
    var file := FileAccess.open(path,FileAccess.WRITE)
    file.store_string(JSON.stringify(pack,"  ",false,true)+"\n");file.close()
    print("WORKSHOP COMPILE PASS: ten verified native module scenes bundled for source-free runtime.")
    quit(0)
