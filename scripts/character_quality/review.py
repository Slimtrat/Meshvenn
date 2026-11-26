"""Human review prompts bound to exact exported assets; no automatic verdict."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
import re


QUESTIONS=(
    ("head_boxy","La tête paraît-elle trop carrée ?"),
    ("bust_coherent","Le buste paraît-il cohérent ?"),
    ("extremities_preserved","Les mains et les pieds sont-ils conservés ?"),
)


def review_template(render_manifest:dict)->dict:
    assets=render_manifest["assets"]
    sources=[a for a in assets if a["role"]=="source"]
    if len(sources)!=1:raise ValueError("Human review needs exactly one source")
    binding={"request_sha256":render_manifest["request_sha256"],
             "assets":[{"asset_id":a["asset_id"],"role":a["role"],"glb_sha256":a["glb"]["sha256"],
                        "mesh_sha256":a["mesh"]["sha256"]} for a in assets]}
    digest=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return {"schema_version":1,"kind":"human_character_review","binding_sha256":digest,
            "binding":binding,"reviewer":None,"reviewed_at":None,"status":"unknown",
            "self_attestation":False,"experience_3d":None,
            "quality_certification":"unknown","questions":[{"id":i,"label":q,"choices":["yes","no","unknown"]} for i,q in QUESTIONS],
            "reviews":[{"asset_id":a["asset_id"],"answers":{i:"unknown" for i,_ in QUESTIONS},"comment":""}
                       for a in assets if a["role"]=="candidate"]}


def validate_review(record:dict,render_manifest:dict)->dict:
    """Validate recorded human provenance, never turn answers into certification."""
    expected=review_template(render_manifest)
    if record.get("binding_sha256")!=expected["binding_sha256"] or record.get("binding")!=expected["binding"]:
        raise ValueError("Review is bound to different GLBs or render request")
    if record.get("schema_version")!=1 or record.get("kind")!="human_character_review":raise ValueError("Unsupported review")
    rows=record.get("reviews")
    if not isinstance(rows,list) or [r.get("asset_id") for r in rows]!=[r["asset_id"] for r in expected["reviews"]]:
        raise ValueError("Review candidate set changed")
    for row in rows:
        answers=row.get("answers")
        if not isinstance(answers,dict) or set(answers)!={i for i,_ in QUESTIONS} or any(type(v) is not str or v not in ("yes","no","unknown") for v in answers.values()):
            raise ValueError("Invalid human answers")
        if not isinstance(row.get("comment"),str) or len(row["comment"])>10000:raise ValueError("Invalid comment")
    reviewer=record.get("reviewer");date=record.get("reviewed_at")
    attestation=record.get("self_attestation",False);experience=record.get("experience_3d")
    if type(attestation) is not bool:raise ValueError("Self-attestation must be explicit true or false")
    if experience not in (None,"beginner","occasional","experienced"):raise ValueError("Invalid 3D experience")
    if date is not None:
        if type(date) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",date):
            raise ValueError("Review date must be an ISO timestamp with timezone")
        try:
            parsed=datetime.fromisoformat(date.replace("Z","+00:00"))
            if parsed.utcoffset() is None:raise ValueError("Missing timezone")
        except ValueError as exc:raise ValueError("Invalid ISO review date") from exc
    observed=attestation and experience is not None and isinstance(reviewer,str) and bool(reviewer.strip()) and date is not None
    return {"schema_version":1,"status":"recorded" if observed else "unknown","human_provenance_present":observed,
            "provenance_basis":"self_attested_unverified" if observed else "unknown",
            "self_attestation":attestation,"experience_3d":experience,
            "binding_sha256":expected["binding_sha256"],"quality_certification":"unknown","reviews":rows}
