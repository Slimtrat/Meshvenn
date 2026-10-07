"""Strict captured native-joint probe data; no consumer/gameplay authority."""
from dataclasses import dataclass
import math
import re

FRAME = "Godot imported native bone-local; before unchanged ancestor normalization/facing"
PARENTS = {"root": None, "pelvis": "root", "spine": "pelvis", "chest": "spine",
           "neck": "chest", "head": "neck",
           **{f"{part}.{side}": parent if "." not in parent else parent.replace(".SIDE", "."+side)
              for side in ("L", "R") for part, parent in (
                  ("upper_arm", "chest"), ("forearm", "upper_arm.SIDE"), ("hand", "forearm.SIDE"),
                  ("thigh", "pelvis"), ("shin", "thigh.SIDE"), ("foot", "shin.SIDE"))}}


def matrix_rows(values):
    """Godot Basis.X/Y/Z columns followed by Origin, NOT four row vectors."""
    if (not isinstance(values, (list, tuple)) or len(values) != 12
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
        raise ValueError("Native probe requires twelve finite numeric transform components.")
    rows = tuple(tuple(float(values[column*3+row]) for column in range(4)) for row in range(3))
    determinant = (rows[0][0]*(rows[1][1]*rows[2][2]-rows[1][2]*rows[2][1])
                   - rows[0][1]*(rows[1][0]*rows[2][2]-rows[1][2]*rows[2][0])
                   + rows[0][2]*(rows[1][0]*rows[2][1]-rows[1][1]*rows[2][0]))
    if not math.isfinite(determinant) or determinant <= 1e-8:
        raise ValueError("Native probe transform is singular or mirrored.")
    return (*rows, (0.0, 0.0, 0.0, 1.0))


@dataclass(frozen=True)
class NativeBoneProbe:
    name: str
    parent: str | None
    rest: tuple
    pose: tuple


@dataclass(frozen=True)
class NativePoseProbe:
    asset_sha256: str
    bones: tuple[NativeBoneProbe, ...]

    @classmethod
    def from_dict(cls, value):
        if (not isinstance(value, dict) or set(value) != {"AssetSha256", "CoordinateFrame", "Bones"}
                or value["CoordinateFrame"] != FRAME or not isinstance(value["AssetSha256"], str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", value["AssetSha256"]) is None
                or not isinstance(value["Bones"], list) or len(value["Bones"]) != 18):
            raise ValueError("Expected a hash-linked eighteen-joint native-local probe.")
        rows = value["Bones"]
        if any(not isinstance(b, dict) or set(b) != {"Name", "Parent", "Rest", "Pose"} for b in rows):
            raise ValueError("Invalid native bone probe fields.")
        names = [b["Name"] for b in rows]
        if any(not isinstance(n, str) for n in names) or len(set(names)) != 18 or set(names) != set(PARENTS):
            raise ValueError("Native probe does not name the exact canonical joints once.")
        bones = []
        for b in rows:
            parent = b["Parent"]
            if type(parent) is not int or not -1 <= parent < len(rows):
                raise ValueError("Invalid native probe parent index.")
            parent_name = names[parent] if parent >= 0 else None
            if parent_name != PARENTS[b["Name"]]:
                raise ValueError("Captured native hierarchy differs from the canonical source.")
            bones.append(NativeBoneProbe(b["Name"], parent_name, matrix_rows(b["Rest"]), matrix_rows(b["Pose"])))
        return cls(value["AssetSha256"].lower(), tuple(bones))

    def ordered(self):
        """Deterministic parent-first order; file/index order is not authoritative."""
        result, remaining = [], {b.name: b for b in self.bones}
        while remaining:
            ready = sorted(n for n,b in remaining.items() if b.parent is None or b.parent not in remaining)
            if not ready:
                raise ValueError("Cyclic native probe hierarchy.")
            result.extend(remaining.pop(n) for n in ready)
        return tuple(result)
