extends SceneTree
## Real importer / animation / negative-space acceptance; no gameplay collision created.

var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error(message)

func descendants(node: Node) -> Array[Node]:
	var result: Array[Node] = [node]
	for child in node.get_children():
		result.append_array(descendants(child))
	return result

func bounds(node: Node3D) -> AABB:
	var found := false
	var result := AABB()
	for child in descendants(node):
		if child is MeshInstance3D:
			var box: AABB = child.global_transform * child.get_aabb()
			result = result.merge(box) if found else box
			found = true
	return result

func hits(node: Node3D, start: Vector3, end: Vector3) -> int:
	var count := 0
	for child in descendants(node):
		if not child is MeshInstance3D:
			continue
		for surface in child.mesh.get_surface_count():
			var arrays: Array = child.mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			for i in range(0, indices.size(), 3):
				var a: Vector3 = child.global_transform * vertices[indices[i]]
				var b: Vector3 = child.global_transform * vertices[indices[i+1]]
				var c: Vector3 = child.global_transform * vertices[indices[i+2]]
				if Geometry3D.segment_intersects_triangle(start, end, a, b, c) != null:
					count += 1
	return count

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/pack.json"))
	var evidence: Array = []
	for asset in manifest.assets:
		var path: String = "res://assets/" + asset.file
		check(FileAccess.get_sha256(path) == asset.sha256, "Fingerprint mismatch: " + path)
		var packed: PackedScene = load(path)
		check(packed != null, "Cannot import " + path)
		if packed == null:
			continue
		var instance: Node3D = packed.instantiate()
		root.add_child(instance)
		check(instance.transform.is_equal_approx(Transform3D.IDENTITY), "Root must be identity")
		var nodes := descendants(instance)
		for name in asset.requiredNodes:
			check(instance.find_child(name, true, false) != null, "Missing node " + name)
		var player: AnimationPlayer
		for node in nodes:
			check(not node is Skeleton3D, "Rigid prop contains a skeleton")
			check(not node is CollisionObject3D and not node is CollisionShape3D, "GLB activates gameplay collision")
			check(not node is Light3D, "GLB contains a forced light")
			if node is AnimationPlayer:
				player = node
			if node is MeshInstance3D:
				for i in node.mesh.get_surface_count():
					var material: StandardMaterial3D = node.mesh.surface_get_material(i)
					check(material != null and material.albedo_texture != null, "PBR texture missing")
		check(player != null, "Animations absent")
		if player == null:
			instance.queue_free()
			continue
		for clip in asset.animations:
			check(player.has_animation(clip), "Missing clip " + clip)
			check(absf(player.get_animation(clip).length - .6) < .00001, "Clip must last 0.6 seconds")
			check(player.get_animation(clip).loop_mode == Animation.LOOP_NONE, "Prop clips must not loop")
		player.play(asset.animations[0]);player.seek(.6, true);player.advance(0)
		var box := bounds(instance)
		var expected := Vector3(asset.dimensions[0], asset.dimensions[1], asset.dimensions[2])
		check(box.size.distance_to(expected) < .001, "Native bounds mismatch " + str(box))
		check(absf(box.position.y) < .00001, "Root floor is not zero")
		var hinge: Node3D = instance.find_child(asset.opening.node, true, false)
		var closed := hinge.transform
		var is_door: bool = asset.id == "chamber-door-v1"
		var fixed: Node3D = instance.find_child("DoorFrame" if is_door else "ChestBody", true, false)
		var fixed_before := fixed.global_transform
		var start := Vector3(.03, .60, 1) if is_door else Vector3(.03, 1, .025)
		var end := Vector3(.03, .60, -1) if is_door else Vector3(.03, .1, .025)
		check(hits(instance, start, end) > 0, "Closed prop must obstruct the opening")
		player.play(asset.animations[1]);player.seek(.6, true);player.advance(0)
		check(hinge.transform.origin.distance_to(closed.origin) < .00001, "Hinge translated during rotation")
		var expected_rotation := Basis(Vector3.UP if is_door else Vector3.RIGHT, deg_to_rad(asset.opening.angle_degrees))
		check(hinge.basis.is_equal_approx(expected_rotation), "Opening axis/angle mismatch: " + str(hinge.rotation_degrees))
		check(fixed.global_transform.is_equal_approx(fixed_before), "Opening moved the fixed frame/body")
		check(hits(instance, start, end) == 0, "Open passage/cavity is obstructed")
		if not is_door:
			check(hits(instance, Vector3(.03,.2,.025), Vector3(.03,.02,.025)) > 0, "Chest has no real bottom")
		player.play(asset.animations[0]);player.seek(.6,true);player.advance(0)
		check(hinge.transform.is_equal_approx(closed), "Closed clip fails to restore the hinge")
		evidence.append({"id":asset.id,"sha256":asset.sha256,"bounds":[box.size.x,box.size.y,box.size.z],"clips":asset.animations,"rigid":true,"negative_space":true,"no_gameplay_bodies":true})
		instance.free()
	if not failures.is_empty():
		quit(1)
		return
	var report := FileAccess.open("res://validation.json", FileAccess.WRITE)
	report.store_string(JSON.stringify({"status":"pass","engine":Engine.get_version_info().string,"assets":evidence}, "  ") + "\n")
	print("CHAMBER GODOT PASS: real PBR import, dimensions, hinges, four clips, passage/cavity and no gameplay bodies")
	quit(0)
