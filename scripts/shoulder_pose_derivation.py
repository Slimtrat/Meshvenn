"""Explicit evidence-only pose derivation for an intentionally corrected rest rig.

Never label this as a capture of the new asset. Original matrices and proof stay
immutable; the new parent-local pose is R_new * inverse(R_old) * P_old.
"""
from core.native_pose_capture import multiply
from core.native_pose_probe import FRAME, NativePoseProbe, matrix_rows


def components(matrix):
    if (len(matrix) != 4 or any(len(row) != 4 for row in matrix)
            or tuple(matrix[3]) != (0,0,0,1)):
        raise ValueError("Require a complete affine rest/pose matrix.")
    result = [matrix[r][c] for c in range(4) for r in range(3)]
    matrix_rows(result)  # Existing finite/nonmirrored/nonsingular validation.
    return result


def inverse(matrix):
    components(matrix)
    a,b,c = matrix[0][:3]
    d,e,f = matrix[1][:3]
    g,h,i = matrix[2][:3]
    determinant = a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
    rows = ((e*i-f*h,c*h-b*i,b*f-c*e),
            (f*g-d*i,a*i-c*g,c*d-a*f),
            (d*h-e*g,b*g-a*h,a*e-b*d))
    rotation = [tuple(v/determinant for v in row) for row in rows]
    return (*[(*row,-sum(row[j]*matrix[j][3] for j in range(3))) for row in rotation],(0.,0.,0.,1.))


def document(probe):
    names = [b.name for b in probe.bones]
    return {"AssetSha256":probe.asset_sha256,"CoordinateFrame":FRAME,
            "Bones":[{"Name":b.name,"Parent":names.index(b.parent) if b.parent else -1,
                      "Rest":components(b.rest),"Pose":components(b.pose)} for b in probe.bones]}


def derive_pose(probe, new_rests, candidate_sha256):
    probe = NativePoseProbe.from_dict(document(probe))
    if set(new_rests) != {b.name for b in probe.bones}:
        raise ValueError("New rests must name exactly the same eighteen native joints.")
    result = document(probe)
    result["AssetSha256"] = candidate_sha256
    for row,bone in zip(result["Bones"],probe.bones):
        rest = new_rests[bone.name]
        relative = multiply(inverse(bone.rest),bone.pose)
        row["Rest"] = components(rest)
        row["Pose"] = components(multiply(rest,relative))
    return NativePoseProbe.from_dict(result)
