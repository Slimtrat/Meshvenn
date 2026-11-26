"""Human review prompts bound to exact exported assets; no automatic verdict."""
from __future__ import annotations

import hashlib
import json


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
        if not isinstance(answers,dict) or set(answers)!={i for i,_ in QUESTIONS} or set(answers.values())-{"yes","no","unknown"}:
            raise ValueError("Invalid human answers")
        if not isinstance(row.get("comment"),str) or len(row["comment"])>10000:raise ValueError("Invalid comment")
    reviewer=record.get("reviewer");date=record.get("reviewed_at")
    observed=isinstance(reviewer,str) and bool(reviewer.strip()) and isinstance(date,str) and bool(date.strip())
    return {"schema_version":1,"status":"recorded" if observed else "unknown","human_provenance_present":observed,
            "binding_sha256":expected["binding_sha256"],"quality_certification":"unknown","reviews":rows}
