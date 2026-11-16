"""Verify the frozen authored reference archive; never claim a fresh bpy reload."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import struct

FROZEN_MANIFEST_SHA256="f0d1e6be24740cb4b38ce359613d8bf0f377f1bfae81b393f4e8d1c8ada0145f"
REPO=Path(__file__).resolve().parents[2]


def _read(path,limit):
    try:
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size>limit:
            raise ValueError("Fixture file type or size is invalid.")
        with path.open("rb") as stream:data=stream.read(limit+1)
    except OSError as exc:
        raise ValueError("A fixture file is missing or unreadable.") from exc
    if len(data)>limit:raise ValueError("Fixture file exceeds its byte budget.")
    return data


def verify_fixture(root:Path)->dict:
    """Check pinned bytes, PNG grids, GLB resources and the archived reload binding.

    ``root`` is the provider-v1 fixture directory. Fresh rebuilds on another
    Blender version are separate measurements, not replacements for this pin.
    """
    root=Path(root).resolve()
    raw=_read(root/"manifestfixture.json",1024*1024)
    if hashlib.sha256(raw).hexdigest()!=FROZEN_MANIFEST_SHA256:
        raise ValueError("Frozen provider reference manifest changed; untrusted JSON is not reload proof.")
    manifest=json.loads(raw)
    if not (manifest["schema_version"]==1 and manifest["frozen_before_provider"] is True and
            manifest["provider_calls"]==0 and manifest["human_reviewed"] is False and
            manifest["provider_fidelity_qualified"] is False and manifest["corrected_3d_claim"] is False):
        raise ValueError("The archive's authored/pre-provider scope is invalid.")
    assets=manifest["assets"]
    if not 1<=len(assets)<=64:raise ValueError("Fixture asset count exceeds its bound.")
    contents={};total=0
    for record in assets:
        name=record["path"]
        if type(name) is not str or Path(name).name!=name or name in contents:
            raise ValueError("Fixture assets require unique local basenames.")
        data=_read(root/name,2*1024*1024)
        total+=len(data)
        if total>16*1024*1024:raise ValueError("Fixture exceeds its aggregate byte budget.")
        if len(data)!=record["bytes"] or hashlib.sha256(data).hexdigest()!=record["sha256"]:
            raise ValueError("Fixture artifact differs from its frozen byte fingerprint: "+name)
        contents[name]=data
    author=manifest["authoring_script"]
    if author["path"]!="scripts/build_diagnostic_reference.py" or hashlib.sha256(
            _read(REPO/author["path"],1024*1024)).hexdigest()!=author["sha256"]:
        raise ValueError("The original Blender authoring script changed.")
    for name,data in contents.items():
        if name.endswith(".png"):
            if data[:8]!=b"\x89PNG\r\n\x1a\n" or data[12:16]!=b"IHDR":
                raise ValueError("Pinned raster has no PNG IHDR.")
            width,height,depth,color=struct.unpack_from(">IIBB",data,16)
            expected=1024 if "front" in name or "badge" in name else 512
            if (width,height,depth,color)!=(expected,expected,8,6):
                raise ValueError("Pinned PNG grid or RGBA encoding is inconsistent.")
    glb=contents[manifest["truth"]["glb"]]
    if struct.unpack_from("<4sII",glb)!=(b"glTF",2,len(glb)):
        raise ValueError("Pinned GLB has an invalid complete header.")
    offset=12;chunks=[]
    while offset<len(glb):
        length,kind=struct.unpack_from("<I4s",glb,offset)
        if length%4 or offset+8+length>len(glb):raise ValueError("Pinned GLB chunk bounds are invalid.")
        chunks.append((kind,glb[offset+8:offset+8+length]));offset+=8+length
    if len(chunks)!=2 or [c[0] for c in chunks]!=[b"JSON",b"BIN\0"]:
        raise ValueError("Authored source requires self-contained JSON and BIN chunks.")
    document=json.loads(chunks[0][1])
    if any("uri" in item for item in (*document.get("buffers",[]),*document.get("images",[]))):
        raise ValueError("External GLB resources are not part of this owned fixture.")
    if document.get("images") or document.get("animations") or len(document["buffers"])!=1:
        raise ValueError("This fixture declares untextured, unanimated original geometry.")
    if not 0<=len(chunks[1][1])-document["buffers"][0]["byteLength"]<=3:
        raise ValueError("GLB binary resource length is invalid.")
    proof=json.loads(contents[manifest["truth"]["reload"]])
    source=json.loads(contents[manifest["truth"]["source"]])
    if (proof["source_glb_sha256"]!=hashlib.sha256(glb).hexdigest() or not proof["reloaded_in_empty_scene"] or
            not 0<=proof["maximum_world_position_error"]<=proof["tolerance"]<=2e-6 or
            set(proof["before"])!=set(proof["after"]) or set(proof["before"])!=set(source["expected_parts"])):
        raise ValueError("Archived fresh-scene reload proof is unbound or inconsistent.")
    triangles=sum(document["accessors"][p["indices"]]["count"]//3 for mesh in document["meshes"] for p in mesh["primitives"])
    if triangles!=proof["triangles"] or len(document["meshes"])!=proof["mesh_objects"]:
        raise ValueError("GLB resources do not agree with the archived geometric inventory.")
    pair=manifest["provider_inputs"]
    if not pair["selection_frozen_before_provider"] or not pair["transparent_background"] or (pair["width"],pair["height"])!=(1024,1024):
        raise ValueError("Provider image selection is not explicitly frozen.")
    for key in ("healthy","target","edit_mask","visible_mask"):
        if pair[key] not in contents:raise ValueError("A declared provider input is absent.")
    return dict(schema_version=1,fixture_id=manifest["fixture_id"],manifest_sha256=FROZEN_MANIFEST_SHA256,
        verified_assets=len(assets),verified_bytes=total,source_glb_sha256=proof["source_glb_sha256"],
        resources=dict(meshes=len(document["meshes"]),nodes=len(document["nodes"]),materials=len(document["materials"]),
            triangles=triangles,embedded_buffers=1,external_resources=0),
        archived_reload_verified=True,fresh_reload_performed=False,
        archived_reload_proof_sha256=hashlib.sha256(contents[manifest["truth"]["reload"]]).hexdigest(),manifest=manifest)
