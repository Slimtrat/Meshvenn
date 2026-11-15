"""Bounded content handling for the trusted loop runtime adapter."""
from __future__ import annotations

import base64
import hashlib
import json

from .core.diagnostic_contracts.codec import canonical_json,require_sha256
from .core.diagnostics_preflight import RasterInput
from .core.correction_loop import ProviderReceipt,GlobalEvaluation

MAX_PAYLOAD=64*1024*1024


def fields(value,allowed,required=()):
    if type(value) is not dict or set(value)-set(allowed) or not set(required)<=set(value):
        raise ValueError("Unexpected or missing loop payload fields.")


def payload_artifacts(store,value):
    if type(value) is not dict or len(value)>128:raise ValueError("Artifact bundle exceeds its bound.")
    total=0
    for sha,encoded in value.items():
        require_sha256(sha)
        if type(encoded) is not str or len(encoded)>MAX_PAYLOAD*4//3+4:raise ValueError("Oversized artifact encoding.")
        raw=base64.b64decode(encoded,validate=True)
        total+=len(raw)
        if total>MAX_PAYLOAD:raise ValueError("Artifact bundle exceeds 64MiB.")
        store.put_artifact(raw,sha)


def port_artifacts(store,values):
    if type(values) not in (tuple,list) or len(values)>128:raise ValueError("Invalid port artifact bundle.")
    total=0
    for sha,data in values:
        if type(data) is not bytes:raise ValueError("Port artifacts must be immutable bytes.")
        total+=len(data)
        if total>MAX_PAYLOAD:raise ValueError("Port artifact bundle exceeds 64MiB.")
        store.put_artifact(data,sha)


def verify_snapshot(store,snapshot):
    for sha in snapshot.artifact_hashes:
        if not store.has_artifact(sha):raise ValueError("Snapshot artifact is unavailable: "+sha)


def check_image(store,reference,*,dimensions=None):
    data=store.read_artifact(reference.sha256)
    image=RasterInput.from_png_bytes(data)
    if image.error:raise ValueError("Candidate is not a supported finite PNG: "+image.error)
    if dimensions and (image.width,image.height)!=dimensions:raise ValueError("Candidate changed its original image dimensions.")
    return image


def protected_pixels(store,request,candidate,policy):
    original=request.prepared.prompt.original
    target=next((v for v in candidate.view_set.views if v.view_id==original.view_id),None)
    if target is None or target.image is None:return False
    before=RasterInput.from_png_bytes(store.read_artifact(original.image.sha256))
    after=RasterInput.from_png_bytes(store.read_artifact(target.image.sha256))
    if before.error or after.error:return None
    if (before.width,before.height)!=(after.width,after.height):return False
    region=request.plan.target.bounds
    annotation=request.prepared.prompt.annotation
    mask=annotation.mask if annotation else None
    l,b,r,t=region
    for y in range(before.height):
        v=y/(before.height-1) if before.height>1 else .5
        for x in range(before.width):
            u=x/(before.width-1) if before.width>1 else .5
            editable=l<=u<=r and b<=v<=t
            if editable and mask is not None:
                mx,my=int(u*(mask.width-1)+.5),int(v*(mask.height-1)+.5)
                editable=bool(mask.values[my*mask.width+mx])
            if not editable:
                offset=(y*before.width+x)*4
                if any(abs(a-b)>policy.outside_pixel_tolerance for a,b in zip(before.rgba[offset:offset+4],after.rgba[offset:offset+4])):return False
    return True


def inbox_id(request_id,kind="receipt"):
    return kind+"_"+hashlib.sha256(request_id.encode()).hexdigest()[:40]


def inbox_append(store,request_id,kind,item):
    key=inbox_id(request_id,kind)
    from .loop_store import LoopStoreError
    try:store.create(key,{"items":[]})
    except LoopStoreError as exc:
        if exc.code!="session_exists":raise
    def append(document):
        items=document["items"]
        if item not in items:
            if len(items)>=64:raise ValueError("Inbox receipt bound exceeded.")
            items.append(item)
        return document
    store.update(key,append)


def inbox_load(store,request_id,kind):
    from .loop_store import LoopStoreError
    try:return store.load(inbox_id(request_id,kind))["items"]
    except LoopStoreError as exc:
        if exc.code=="session_not_found":return []
        raise
