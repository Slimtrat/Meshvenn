"""Transactional, non-destructive face partition for modular character export.

Partitions are open at shared seams: existing faces are assigned exactly once;
no cap, remesh, weld, or anatomical inference is performed.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

import bpy
from mathutils import Vector


REGION_ID_KEY = "meshvenn_region_id"
REGION_ROLE_KEY = "meshvenn_region_role"
SOURCE_MESH_KEY = "meshvenn_source_mesh"
SEAM_POLICY_KEY = "meshvenn_seam_policy"
SEAM_POLICY = "shared-open-seams-no-caps"
NORMAL_ATTRIBUTE = "_meshvenn_normal_gltf"
NORMAL_SEMANTIC = NORMAL_ATTRIBUTE.upper()
COLOR_ATTRIBUTE_PREFIX = "_meshvenn_color_"
COLOR_SEMANTIC_PREFIX = COLOR_ATTRIBUTE_PREFIX.upper()


def _preflight(plan, spec):
    from ...core.modular_character import mesh_surface_sha256

    if plan.rig is None or plan.rig.implementation_id != "canonical-biped-v2":
        raise ValueError("Modular V1 requires the Canonical Biped V2 rig.")
    sources = {obj.name: obj for obj in plan.mesh_objects}
    if len(sources) != len(plan.mesh_objects) or set(spec.ownership) != set(sources):
        raise ValueError("Modular ownership must cover exactly the export source meshes.")
    regions = {region.id: region for region in spec.regions}
    if not regions or len(regions) != len(spec.regions):
        raise ValueError("Modular regions must have unique, non-empty IDs.")
    if len({region.node_name for region in spec.regions}) != len(regions):
        raise ValueError("Modular region node names must be unique.")
    buckets = {region_id: [] for region_id in regions}
    fingerprints = {}
    for source in plan.mesh_objects:
        if source.type != "MESH" or source.mode != "OBJECT":
            raise ValueError("Modular partition requires Object-mode source meshes.")
        if source.data.shape_keys is not None:
            raise ValueError("Modular V1 does not support shape keys; source is unchanged.")
        if any(attribute.name == NORMAL_ATTRIBUTE or attribute.name.startswith(COLOR_ATTRIBUTE_PREFIX)
               for attribute in source.data.attributes):
            raise ValueError("Modular source collides with the reserved normal transport attribute.")
        surface_hash = mesh_surface_sha256(
            [tuple(vertex.co) for vertex in source.data.vertices],
            [tuple(face.vertices) for face in source.data.polygons],
        )
        fingerprints[source.name] = surface_hash
        if spec.ownership_source_sha256.get(source.name) != surface_hash:
            raise ValueError(f"Modular ownership is stale for source {source.name!r}.")
        active = [modifier for modifier in source.modifiers
                  if modifier.show_viewport or modifier.show_render]
        if any(modifier.type != "ARMATURE" for modifier in active):
            raise ValueError("Modular V1 does not support active non-armature modifiers.")
        if plan.armature_object is None or len(active) != 1 or active[0].object is not plan.armature_object:
            raise ValueError("Each modular source must have one binding to the common armature.")
        if active[0].use_deform_preserve_volume or active[0].use_bone_envelopes:
            raise ValueError("Modular GLB requires linear vertex-group armature deformation.")
        if not active[0].use_vertex_groups or active[0].vertex_group or active[0].use_multi_modifier:
            raise ValueError("Modular GLB does not support armature masks or disabled vertex-group skinning.")
        owners = spec.ownership[source.name]
        if len(owners) != len(source.data.polygons):
            raise ValueError(f"Modular ownership face count differs for {source.name!r}.")
        used_vertices = set()
        for face, owner in zip(source.data.polygons, owners):
            if owner not in buckets:
                raise ValueError(f"Unknown modular face owner {owner!r}.")
            buckets[owner].append((source, face.index))
            used_vertices.update(face.vertices)
        if len(used_vertices) != len(source.data.vertices):
            raise ValueError("Modular V1 cannot silently discard loose source vertices.")
        bone_groups = {group.index for group in source.vertex_groups
                       if group.name in plan.armature_object.data.bones}
        if any(sum(group.group in bone_groups and group.weight > 1.0e-7
                   for group in vertex.groups) > 4 for vertex in source.data.vertices):
            raise ValueError("Modular V1 supports at most four skin influences per vertex.")
    spec.validate_against(
        {source.name: len(source.data.polygons) for source in plan.mesh_objects},
        tuple(plan.armature_object.data.bones.keys()), plan.rig.implementation_id,
        mesh_surface_hashes=fingerprints, rig_version=2,
    )
    for region in spec.regions:
        members = buckets[region.id]
        if not members:
            raise ValueError(f"Modular region {region.id!r} contains no source faces.")
        if len({source.as_pointer() for source, _ in members}) != 1:
            raise ValueError("A modular V1 region cannot combine different source-object frames.")
        reserved = {plan.armature_object.name, *plan.armature_object.data.bones.keys(),
                    *(obj.name for obj in plan.auxiliary_objects)}
        if region.node_name in reserved:
            raise ValueError(f"Modular node name collides with the rig/hierarchy: {region.node_name!r}.")
        existing = bpy.data.objects.get(region.node_name)
        if existing is not None and not (
                existing.type == "MESH" and existing is not members[0][0]
                and existing.get(REGION_ID_KEY) == region.id
                and existing.get(REGION_ROLE_KEY) == region.role
                and existing.get(SOURCE_MESH_KEY) == members[0][0].name
                and existing.get(SEAM_POLICY_KEY) == SEAM_POLICY):
            raise ValueError(f"Modular node name already exists outside this derived preview: {region.node_name!r}.")
    return buckets


def _copy_attribute(source, target, source_indices):
    # Standard mesh attributes expose one of these RNA value properties. Fail
    # closed rather than silently dropping an unknown user corner/point layer.
    if not source.data:
        return
    field = next((name for name in ("value", "vector", "color", "matrix")
                  if hasattr(source.data[0], name)), None)
    if field is None:
        raise ValueError(f"Unsupported modular mesh attribute: {source.name!r}.")
    for item, index in zip(target.data, source_indices):
        if index is None:
            # New diagonals only tessellate an existing authored face; they
            # have no original edge attributes and retain Blender's defaults.
            continue
        value = getattr(source.data[index], field)
        setattr(item, field, tuple(value) if hasattr(value, "__len__") else value)


def _partition(source, region, face_indices):
    mesh = source.data
    faces = [mesh.polygons[index] for index in face_indices]
    mesh.calc_loop_triangles()
    selected_faces = set(face_indices)
    triangles = [triangle for triangle in mesh.loop_triangles if triangle.polygon_index in selected_faces]
    vertex_indices = sorted({index for face in faces for index in face.vertices})
    remap = {original: new for new, original in enumerate(vertex_indices)}
    loop_indices = [index for triangle in triangles for index in triangle.loops]
    original_faces = [triangle.polygon_index for triangle in triangles]
    normals = [tuple(mesh.corner_normals[index].vector) for index in loop_indices]
    target = bpy.data.meshes.new(f"{region.node_name}.Mesh")
    obj = None
    try:
        target.from_pydata([tuple(mesh.vertices[index].co) for index in vertex_indices], [],
                           [[remap[index] for index in triangle.vertices] for triangle in triangles])
        for material in mesh.materials:
            target.materials.append(material)
        for output, face_index in zip(target.polygons, original_faces):
            original = mesh.polygons[face_index]
            output.material_index = original.material_index
            output.use_smooth = original.use_smooth
        source_edges = {tuple(sorted(edge.vertices)): edge.index for edge in mesh.edges}
        edge_indices = [source_edges.get(tuple(sorted(vertex_indices[index] for index in edge.vertices)))
                        for edge in target.edges]
        domains = {"POINT": vertex_indices, "EDGE": edge_indices,
                   "FACE": original_faces, "CORNER": loop_indices}
        # Topology is built above; Blender owns these structural attributes.
        structural = {"position", ".corner_vert", ".corner_edge", ".edge_verts"}
        for attribute in mesh.attributes:
            if attribute.name in structural or attribute.name.startswith(".select_"):
                continue
            if attribute.domain not in domains:
                raise ValueError(f"Unsupported modular attribute domain {attribute.domain!r}.")
            output = target.attributes.get(attribute.name)
            if output is None:
                output = target.attributes.new(attribute.name, attribute.data_type, attribute.domain)
            if output.data_type != attribute.data_type or output.domain != attribute.domain:
                raise ValueError(f"Modular attribute type changed: {attribute.name!r}.")
            _copy_attribute(attribute, output, domains[attribute.domain])
        # Creating UV/color through generic attributes keeps all corner data,
        # including seams. Restore active/render choices separately.
        if mesh.uv_layers:
            target.uv_layers.active_index = mesh.uv_layers.active_index
            for output, original in zip(target.uv_layers, mesh.uv_layers):
                output.active_render = original.active_render
        if mesh.color_attributes:
            target.color_attributes.active_color_index = mesh.color_attributes.active_color_index
            target.color_attributes.render_color_index = mesh.color_attributes.render_color_index
        target.normals_split_custom_set(normals)
        # Blender encodes custom normals relative to a vertex fan. Cutting that
        # fan and re-encoding can introduce visible seam differences. Carry the
        # authoritative source normals independently as float32 glTF vectors;
        # the temporary GLB later uses this accessor as its standard NORMAL.
        source_normal_matrix = source.matrix_world.to_3x3().inverted().transposed()
        transport = target.attributes.new(NORMAL_ATTRIBUTE, "FLOAT_VECTOR", "CORNER")
        for output, original in zip(transport.data, normals):
            normal = (source_normal_matrix @ Vector(original)).normalized()
            output.vector = (normal.x, normal.z, -normal.y)
        colors = list(mesh.color_attributes)
        if colors and mesh.color_attributes.render_color_index >= 0:
            render_color = colors.pop(mesh.color_attributes.render_color_index)
            colors.insert(0, render_color)
        for index, layer in enumerate(colors):
            # Blender's exporter may whiten non-active color channels when
            # several layers exist. Carry every authoritative layer separately
            # as linear float4 and publish it as the corresponding COLOR_n.
            color_transport = target.attributes.new(f"{COLOR_ATTRIBUTE_PREFIX}{index}", "FLOAT_COLOR", "CORNER")
            for output, loop in zip(color_transport.data, loop_indices):
                original = loop if layer.domain == "CORNER" else mesh.loops[loop].vertex_index
                output.color = layer.data[original].color
        target.update()
        obj = source.copy()
        obj.name = region.node_name
        obj.data = target
        # source.copy retains modifier configuration, parents and object
        # animation. Group names belong to mesh data in recent Blender versions;
        # rebuild them explicitly before copying the vertex influences.
        obj.vertex_groups.clear()
        for original in source.vertex_groups:
            group = obj.vertex_groups.new(name=original.name)
            group.lock_weight = original.lock_weight
        for index, original in enumerate(vertex_indices):
            for influence in mesh.vertices[original].groups:
                obj.vertex_groups[influence.group].add([index], influence.weight, "REPLACE")
        obj[REGION_ID_KEY] = region.id
        obj[REGION_ROLE_KEY] = region.role
        obj[SOURCE_MESH_KEY] = source.name
        obj[SEAM_POLICY_KEY] = SEAM_POLICY
        bpy.context.collection.objects.link(obj)
        obj.matrix_world = source.matrix_world.copy()
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if target.users == 0:
            bpy.data.meshes.remove(target)
        raise


@contextmanager
def prepare_modular_meshes(plan, spec):
    """Yield a plan containing region copies and release them even on failure."""
    buckets = _preflight(plan, spec)
    created = []
    try:
        for region in spec.regions:
            members = buckets[region.id]
            created.append(_partition(members[0][0], region, [index for _, index in members]))
        bpy.context.view_layer.update()
        yield replace(plan, mesh_objects=tuple(created), mesh_object=created[0])
    finally:
        for obj in reversed(created):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data.users == 0:
                bpy.data.meshes.remove(data)
        bpy.context.view_layer.update()


__all__ = ("prepare_modular_meshes", "REGION_ID_KEY", "REGION_ROLE_KEY", "SOURCE_MESH_KEY",
           "SEAM_POLICY_KEY", "SEAM_POLICY", "NORMAL_ATTRIBUTE", "NORMAL_SEMANTIC",
           "COLOR_ATTRIBUTE_PREFIX", "COLOR_SEMANTIC_PREFIX")
