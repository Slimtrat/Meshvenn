"""Independent original triangle scene and linear ray caster for fixture truth.

This module imports neither the diagnostic BVH nor its reprojection helpers.
Geometry is authored in native reconstruction coordinates [-1,1]. Cardinal and
45-degree cameras use independently stated orthographic ray equations.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib


def canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png_rgba(width: int, height: int, rgba: bytes, *, author_tag="") -> bytes:
    if len(rgba) != width * height * 4:
        raise ValueError("PNG RGBA buffer dimensions disagree")
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    rows = b"".join(b"\0" + rgba[y * width * 4:(y + 1) * width * 4] for y in reversed(range(height)))
    tag = chunk(b"tEXt", b"AnalyticAuthoring\0" + author_tag.encode("ascii")) if author_tag else b""
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + tag + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def add_box(mesh, label, minimum, maximum, material):
    x0, y0, z0 = minimum
    x1, y1, z1 = maximum
    faces = (
        ("front", ((x0,y0,z0), (x1,y0,z0), (x1,y0,z1), (x0,y0,z1))),
        ("back", ((x1,y1,z0), (x0,y1,z0), (x0,y1,z1), (x1,y1,z1))),
        ("right", ((x1,y0,z0), (x1,y1,z0), (x1,y1,z1), (x1,y0,z1))),
        ("left", ((x0,y1,z0), (x0,y0,z0), (x0,y0,z1), (x0,y1,z1))),
        ("top", ((x0,y0,z1), (x1,y0,z1), (x1,y1,z1), (x0,y1,z1))),
        ("bottom", ((x0,y1,z0), (x1,y1,z0), (x1,y0,z0), (x0,y0,z0))),
    )
    for face, vertices in faces:
        start = len(mesh["vertices"])
        mesh["vertices"].extend(vertices)
        mesh["uvs"].extend(((0.,0.), (1.,0.), (1.,1.), (0.,1.)))
        mesh["triangles"].extend(((start,start+1,start+2), (start,start+2,start+3)))
        mesh["triangle_labels"].extend((f"{label}_{face}",) * 2)
        mesh["triangle_materials"].extend((material,) * 2)


def scene(*, occluder=False, ambiguous=False):
    mesh = {"schema_version": 1, "coordinate_space": "native-normalized-cube-minus-one-to-one",
            "vertices": [], "triangles": [], "uvs": [], "triangle_labels": [], "triangle_materials": []}
    add_box(mesh, "body", (-.72,-.35,-.65), (.72,.35,.65), "authored_patch")
    if occluder:
        add_box(mesh, "occluder", (-.30,-.90,-.10), (.40,-.65,.45), "occluder_neutral")
    if ambiguous:
        # A second coincident interior face has independent identity/UVs. This
        # is genuinely ambiguous surface correspondence, not an ordinary shared
        # edge between the two triangles of one quad.
        start = len(mesh["vertices"])
        mesh["vertices"].extend(mesh["vertices"][:4])
        mesh["uvs"].extend(((1.,0.), (0.,0.), (0.,1.), (1.,1.)))
        mesh["triangles"].extend(((start,start+1,start+2), (start,start+2,start+3)))
        mesh["triangle_labels"].extend(("coincident_independent_front",) * 2)
        mesh["triangle_materials"].extend(("ambiguous_other_layer",) * 2)
    return mesh


def subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def triangle_hit(origin, direction, a, b, c):
    # Independent textbook Moller-Trumbore, brute force over authored triangles.
    edge1, edge2 = subtract(b, a), subtract(c, a)
    p = cross(direction, edge2)
    determinant = dot(edge1, p)
    if abs(determinant) < 1e-12:
        return None
    inverse = 1. / determinant
    offset = subtract(origin, a)
    u = dot(offset, p) * inverse
    if u < -1e-10 or u > 1 + 1e-10:
        return None
    q = cross(offset, edge1)
    v = dot(direction, q) * inverse
    if v < -1e-10 or u + v > 1 + 1e-10:
        return None
    distance = dot(edge2, q) * inverse
    if distance < 0:
        return None
    return distance, (1-u-v, u, v)


def primary_rays(azimuth: float, size: int):
    angle = math.radians(azimuth)
    ca, sa = math.cos(angle), math.sin(angle)
    right, backward = (ca,sa,0.), (sa,-ca,0.)
    span = abs(ca) + abs(sa)
    for y in range(size):
        vertical = 2*y/(size-1)-1
        for x in range(size):
            horizontal = (2*x/(size-1)-1) * span
            origin = tuple(right[i]*horizontal + (vertical if i == 2 else 0.) + 3*backward[i] for i in range(3))
            yield origin, tuple(-v for v in backward)


def authored_colour(material: str, u: float, v: float, *, variant="base", injection="none", world=(0.,0.,0.)):
    if material == "occluder_neutral":
        return (115, 125, 135)
    if material == "ambiguous_other_layer":
        return (220, 65, 180)
    colour = ((45,95,190) if u < .5 else (200,70,55)) if v < .5 else ((65,170,100) if u < .5 else (205,175,55))
    if .58 <= u <= .86 and .60 <= v <= .90 and int((u-.58)/.28*4) % 2 == 0:
        colour = (28,35,55)
    if variant == "intentional_asymmetry" and .08 <= u <= .24 and .70 <= v <= .94 and v > .70+(u-.08):
        colour = (35,205,205)
    x, _y, z = world
    if injection == "local_colour" and -.58 <= x <= -.22 and -.48 <= z <= -.14:
        colour = (195,45,175)
    if injection == "removed_motif" and .58 <= u <= .86 and .60 <= v <= .90:
        colour = (205,175,55)
    if injection == "occlusion_patch" and .18 <= x <= .38 and .06 <= z <= .34:
        colour = (205,40,170)
    return colour


def scalar_gain(colour, gain):
    def to_linear(value):
        v = value/255
        return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
    def to_srgb(value):
        v = 12.92*value if value <= .0031308 else 1.055*value**(1/2.4)-.055
        return max(0, min(255, int(v*255+.5)))
    return tuple(to_srgb(to_linear(channel)*gain) for channel in colour)


def render(mesh, azimuth: float, size: int, *, variant="base", injection="none", gain=1.):
    pixels, records = bytearray(), []
    for origin, direction in primary_rays(azimuth, size):
        hits = []
        for index, triangle in enumerate(mesh["triangles"]):
            a, b, c = (mesh["vertices"][i] for i in triangle)
            result = triangle_hit(origin, direction, a, b, c)
            if result is not None:
                hits.append((result[0], index, result[1]))
        if not hits:
            pixels.extend((0,0,0,0))
            records.append(None)
            continue
        distance, index, weights = min(hits, key=lambda h: (round(h[0], 10), h[1]))
        triangle = mesh["triangles"][index]
        u, v = (sum(weights[j]*mesh["uvs"][triangle[j]][axis] for j in range(3)) for axis in (0,1))
        world = tuple(origin[i]+distance*direction[i] for i in range(3))
        material = mesh["triangle_materials"][index]
        colour = authored_colour(material, u, v, variant=variant, injection=injection, world=world)
        pixels.extend((*scalar_gain(colour, gain),255))
        records.append({"triangle_index": index, "surface_label": mesh["triangle_labels"][index],
                        "position": world, "uv": (u,v), "closest_distance": distance})
    return bytes(pixels), records
