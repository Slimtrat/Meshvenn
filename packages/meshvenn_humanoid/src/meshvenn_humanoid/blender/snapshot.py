"""Portable object snapshots without mutating the source's image buffers."""

from array import array
import bpy


def write_snapshot(path, mesh, objects):
    seen = set()
    slots = []

    def visit(tree):
        if tree is None or tree in seen:
            return
        seen.add(tree)
        for node in tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                slots.append((node, node.image))
            elif node.type == "GROUP":
                visit(node.node_tree)

    for material in mesh.data.materials:
        if material is not None:
            visit(material.node_tree)
    copies = {}
    try:
        for node, image in slots:
            if image.source not in ("FILE", "GENERATED"):
                raise ValueError("Snapshot requires static file or generated textures")
            if image.packed_file is not None and not image.is_dirty:
                continue
            if image not in copies:
                # Image.copy() alone does not retain edited/generated pixels.
                copied = image.copy()
                copies[image] = copied
                pixels = array("f", [0.0]) * len(image.pixels)
                image.pixels.foreach_get(pixels)
                copied.pixels.foreach_set(pixels)
                copied.pack()
            node.image = copies[image]
        bpy.data.libraries.write(
            str(path), objects, path_remap="ABSOLUTE", compress=True
        )
    finally:
        for node, image in slots:
            node.image = image
        for image in copies.values():
            bpy.data.images.remove(image)
