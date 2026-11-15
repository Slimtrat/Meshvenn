"""Actually execute upstream diagnostics on unchanged authored sources."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from core.diagnostic_contracts import (ArtifactReference, CameraDeclaration, CanonicalReference,
                                     EngineVersion, Region, ViewRevision, ViewSetRevision)
from core.diagnostics_preflight import (AlignmentAnchor, PreflightPolicy, RasterInput, ViewInput,
                                      analyze_preflight)
from scripts.appearance_diagnostic_corpus.authoring import sha256
from .integrity import checked


class NativeLibraryRequired(RuntimeError):
    pass


class LowConfidenceAnalyzer:
    """Local unqualified semantic adapter specimen, never a real model."""
    def __init__(self):
        self.calls = 0

    def metadata(self):
        from core.appearance_diagnostics.semantics import SemanticAnalyzerMetadata
        return SemanticAnalyzerMetadata(EngineVersion("corpus.low_confidence_adapter","1"),
                                        EngineVersion("corpus.unqualified_semantic_fixture","1"))

    def analyze(self, request, *, timeout_seconds, cancel=None):
        from core.appearance_diagnostics.semantics import SemanticClaim, SemanticResponse
        self.calls += 1
        claims = tuple(SemanticClaim(f"low-{index}-{kind}",pair.pair_id,kind,"changed",
            pair.target,pair.reference,"Local contract specimen, not measured semantic fidelity.",
            "Limited evidence and confidence; no real provider qualification.",support="limited",confidence=.2)
            for index,pair in enumerate(request.pairs) for kind in request.kinds)
        return SemanticResponse(request.dependency_fingerprint,self.metadata().model,claims)


def source_snapshot(view_set, inputs):
    return {"view_set":view_set.to_dict(),"buffers":{
        key:{role:{"source_sha256":raster.source_sha256,"decoded_sha256":raster.decoded_sha256}
             for role,raster in (("image",item.image),("mask",item.mask)) if raster is not None}
        for key,item in inputs.items()}}


def _d2(root, case):
    recipe = case["source"]["recipe"]
    proof_data = (root/"authoring-proof.json").read_bytes()
    proof = ArtifactReference("original-D5-authoring",sha256(proof_data),"application/json","authoring-proof.json")
    camera = CameraDeclaration("orthographic",0.,0.,False,True,proof)
    inputs,views = {},[]
    for key in ("target","reference"):
        image = RasterInput.from_path(root/f"assets/{recipe}/{key}-image.png")
        mask = RasterInput.from_path(root/f"assets/{recipe}/{key}-mask.png")
        inputs[key] = ViewInput(image,mask)
        views.append(ViewRevision(key,1,image.content_reference(),mask.content_reference(),camera,
                                  role="reference" if key=="reference" else "observation",origin="rendered"))
    canonical = CanonicalReference("original-D5-design",1,views[1].image,True,("reference",),proof)
    view_set = ViewSetRevision("D5-"+recipe,1,tuple(views),canonical)
    required = ((0.,0.),(90.,0.)) if recipe=="missing_side" else ((0.,0.),)
    result = analyze_preflight(view_set,inputs,
        anchors=(AlignmentAnchor("target","reference",proof.sha256),),
        policy=PreflightPolicy(required_cameras=required))
    paths = {key:{role:root/f"assets/{recipe}/{key}-{role}.png" for role in ("image","mask")}
             for key in inputs}
    return {"view_set":view_set,"inputs":inputs,"reports":(result.report,),"upstream_result":result,
            "upstream_kind":"actual_D2","asset_paths":paths,"annotation":None,"semantic_mock_calls":0}


def _d4(root, case):
    from core.appearance_diagnostics import (AppearancePolicy, AppearanceRegionAnchor,
                                             AppearanceViewSettings, analyze_appearance)
    from core.geometry_diagnostics.models import MaskArtifact
    from core.image_mask import BinaryMask
    from scripts.appearance_diagnostic_corpus.integrity import load_manifest
    from scripts.appearance_diagnostic_corpus.runner import inputs_for_case
    repo = Path(__file__).resolve().parents[2]
    parent_root = repo/"tests/fixtures/diagnostics/appearance-v1"
    parent,_ = load_manifest(parent_root)
    source = case["source"]
    original = next(c for c in parent["cases"] if c["case_id"]==source["parent_case_id"])
    variant = next(v for v in original["variants"] if v["raster_resolution"]==source["raster_resolution"])
    view_set,inputs,surface,settings,regions,anchors,upstream,mesh_data = inputs_for_case(parent_root,original,variant,"canonical")
    paths = {key:{"image":checked(parent_root,asset["path"])} for key,asset in variant["views"].items()}
    if source.get("origin"):
        view_set = replace(view_set,views=tuple(replace(v,origin=source["origin"]) if v.view_id=="target" else v
                                              for v in view_set.views))
    if source.get("additional_reference"):
        extra_source = source["additional_reference"]
        extra = next(c for c in parent["cases"] if c["case_id"]==extra_source["parent_case_id"])
        extra_variant = next(v for v in extra["variants"] if v["raster_resolution"]==32)
        asset = extra_variant["views"][extra_source["view_id"]]
        image = RasterInput.from_path(checked(parent_root,asset["path"]))
        proof = ArtifactReference("original-reference-union",sha256((root/"authoring-proof.json").read_bytes()),
                                  "application/json","authoring-proof.json")
        camera = asset["camera"]
        declaration = CameraDeclaration("orthographic",camera["azimuth_degrees"],camera["elevation_degrees"],
                                        camera["flip_x"],True,proof)
        reference = ViewRevision("reference_extra",1,image.content_reference(),None,declaration,
                                 role="reference",origin="rendered")
        canonical = replace(view_set.canonical_reference,view_ids=("reference","reference_extra"),validation_evidence=proof)
        view_set = replace(view_set,views=view_set.views+(reference,),canonical_reference=canonical,
                           input_order=view_set.input_order+(reference.view_id,))
        inputs[reference.view_id] = ViewInput(image)
        settings[reference.view_id] = AppearanceViewSettings.from_dict(asset["appearance_settings"])
        paths[reference.view_id] = {"image":checked(parent_root,asset["path"])}
    if case["author_intent"].get("allow_targeted_edit"):
        # Evaluate the author's original target-space ROI explicitly as well as
        # the parent's canonical ROI. No bounds are copied from a residual.
        target_region = Region("target",original["expected"]["region_label"],
                               tuple(variant["views"]["target"]["region_projected_bounds"]))
        bound = original["surface_region"]
        proof = ArtifactReference("explicit-original-region",original["source"]["sha256"],"application/json")
        triangles = tuple(i for i,label in enumerate(mesh_data["triangle_labels"]) if label==bound["surface_label"])
        regions = regions+(target_region,)
        anchors = anchors+(AppearanceRegionAnchor(target_region,(bound["x"][0],bound["y"],bound["z"][0]),
            (bound["x"][1],bound["y"],bound["z"][1]),proof,triangles),)
    analyzer = LowConfidenceAnalyzer() if source.get("semantic_mock") else None
    result = analyze_appearance(view_set,inputs,surface=surface,view_settings=settings,regions=regions,
        region_anchors=anchors,upstream_reports=upstream,policy=AppearancePolicy(sampling_size=32,max_seconds=20.),
        vision_analyzer=analyzer)
    annotation = None
    if case["author_intent"].get("allow_targeted_edit"):
        target_asset = variant["views"]["target"]
        truth = RasterInput.from_path(checked(parent_root,target_asset["truth_region_mask"]["path"]))
        values = bytes(int(truth.rgba[index]>=.5) for index in range(3,len(truth.rgba),4))
        annotation = {
            "region":Region("target",original["expected"]["region_label"],tuple(target_asset["region_projected_bounds"])),
            "mask":MaskArtifact.from_mask(BinaryMask(truth.width,truth.height,values)),
            "provenance":ArtifactReference("explicit-authored-original-region",original["source"]["sha256"],
                                            "application/json","original-authoring-source.json"),
        }
    # Independent D2 and D4 reports share the exact source dependency snapshot.
    # Report order is varied later, without reinterpreting or flattening either.
    preflight = analyze_preflight(view_set,inputs,
        anchors=(AlignmentAnchor("target","reference",original["source"]["sha256"]),),
        policy=PreflightPolicy(required_cameras=((0.,0.),)))
    return {"view_set":view_set,"inputs":inputs,"reports":(preflight.report,result.report),"upstream_result":result,
            "upstream_kind":"actual_D4","asset_paths":paths,"annotation":annotation,
            "semantic_mock_calls":analyzer.calls if analyzer else 0,
            "original_authoring_path":checked(parent_root,original["source"]["path"])}


def _d3(root, case, native_library, python_executable):
    from core.geometry_diagnostics import GeometryPolicy, NativeGeometryBackend, analyze_geometry
    from scripts.geometry_diagnostic_corpus.runner import inputs_for_case, load_manifest
    repo = Path(__file__).resolve().parents[2]
    parent_root = repo/"tests/fixtures/diagnostics/geometry-v1"
    parent,_ = load_manifest(parent_root)
    original = next(c for c in parent["cases"] if c["case_id"]==case["source"]["parent_case_id"])
    variant = original["variants"][0]
    view_set,inputs,regions = inputs_for_case(parent_root,original,variant,"canonical")
    library = root/"assets/invalid-native.bin" if case["source"]["kind"]=="actual_native_failure" else native_library
    if library is None:
        raise NativeLibraryRequired("An explicit real native library is required for this D3 case")
    library = Path(library).resolve()
    if not library.is_file():
        raise NativeLibraryRequired("The explicitly supplied native library is unavailable")
    result = analyze_geometry(view_set,inputs,regions=regions,
        policy=GeometryPolicy(resolution=32,reprojection_size=64,max_seconds=20.),
        backend=NativeGeometryBackend(library_path=library,python_executable=python_executable))
    paths = {}
    for view in variant["views"]:
        paths[view["view_id"]] = {role:checked(parent_root,record["path"])
                                 for role,record in view["assets"].items() if role in ("image","mask")}
        if original["canonical"]:
            paths["ref_"+view["view_id"]] = {"image":checked(parent_root,view["assets"]["reference"]["path"])}
    return {"view_set":view_set,"inputs":inputs,"reports":(result.report,),"upstream_result":result,
            "upstream_kind":case["source"]["kind"],"asset_paths":paths,"annotation":None,"semantic_mock_calls":0,
            "native_library_sha256":sha256(library.read_bytes()),"native_library_name":library.name}


def execute_source(root, case, *, native_library=None, python_executable=None):
    kind = case["source"]["kind"]
    if kind=="actual_D2":
        context = _d2(root,case)
    elif kind=="actual_D4":
        context = _d4(root,case)
    else:
        context = _d3(root,case,native_library,python_executable)
    context["original_snapshot"] = source_snapshot(context["view_set"],context["inputs"])
    return context
