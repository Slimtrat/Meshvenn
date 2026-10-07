"""Fail-closed presentation of evidence from one exact GLB V2 workflow run."""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path

from scripts.glb_v2_character_support import assert_refinement_quality, assert_detail_surface_quality
from scripts.v2_preview_appearance import appearance_caption, verify_appearance

MARKER = "<!-- bpt-visual-preview -->"
IMAGE_NAMES = ("source.png", "rest.png", "pose.png", "hidden.png", "sockets_rest.png", "sockets_pose.png")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Preview JSON exceeds its memory budget.")
    value = json.loads(path.read_text("utf-8"), object_pairs_hook=_unique_fields,
                       parse_constant=lambda value: (_ for _ in ()).throw(
        ValueError(f"Non-finite JSON value: {value}")))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path.name}.")
    return value


def validate_revision(sha: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Preview requires a full source commit SHA.")
    return sha


def number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Invalid {name} measurement.")
    return float(value)


def unit_measure(value, name: str) -> float:
    result = number(value, name)
    if not 0 <= result <= 1:
        raise ValueError(f"Out-of-range {name} measurement.")
    return result


def verified_evidence(directory: Path, sha: str, run_id: str, attempt: str) -> dict:
    """Reject old, incomplete, altered, or another run's presentation bundle."""
    validate_revision(sha)
    report = read_json(directory / "preview.json")
    if (report.get("schema_version") != 1 or report.get("source_sha") != sha
            or report.get("run_id") != str(run_id) or report.get("run_attempt") != str(attempt)
            or report.get("rendered_from_final_glb") is not True):
        raise ValueError("Preview evidence does not belong to this exact source/run/attempt.")
    files = report.get("images")
    if not isinstance(files, dict) or set(files) != set(IMAGE_NAMES):
        raise ValueError("Preview is missing a required rendered state.")
    for name, expected in files.items():
        path = directory / name
        if (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)
                or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024 or digest(path) != expected):
            raise ValueError(f"Missing or altered preview image: {name}.")
        header = path.read_bytes()[:33]
        if (len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[8:16] != b"\x00\x00\x00\rIHDR"
                or any(not 128 <= size <= 1024 for size in struct.unpack(">II", header[16:24]))):
            raise ValueError(f"Invalid preview image: {name}.")
    modular = report["modular"]
    verify_appearance(modular)
    for value in (modular.get("sha256"), modular.get("editable_source_sha256"), report.get("source_reference_sha256")):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid preview artifact hash.")
    if modular["roundtrip"].get("passed") is not True:
        raise ValueError("Modular fidelity did not pass.")
    if modular.get("native_joint_count") != 18 or modular.get("animation_count") != 43:
        raise ValueError("Preview lost the native rig or the fixture's clips.")
    if modular["surface_refinement"].get("algorithm") != "contour-taubin-v2":
        raise ValueError("Preview is not the current Organic pipeline.")
    if (modular.get("resolution") != 64 or "uv-bake-v2" not in modular.get("pipeline", [])
            or modular["material"].get("texture_size") != 512
            or len(modular["contract"]["spec"]["regions"]) != 5
            or len(modular["contract"]["spec"]["sockets"]) != 8):
        raise ValueError("The preview does not describe the qualified modular UV Bake fixture.")
    coverage = modular["partition_authoring"]["surface_coverage"]
    if any(type(coverage[key]) is not int or coverage[key] != 0 for key in (
            "unowned_source_polygons", "duplicated_source_polygons", "extra_cap_polygons")):
        raise ValueError("Modular coverage lost, duplicated, or added source faces.")
    fidelity = modular["roundtrip"]
    tolerance = number(fidelity["position_tolerance"], "position tolerance")
    if not 0 < tolerance <= .001:
        raise ValueError("Modular position tolerance exceeds its declared metric budget.")
    for key, maximum in (("max_rest_error", tolerance), ("max_compound_deformation_error", tolerance),
                         ("max_hide_independence_error", tolerance), ("max_socket_compound_error", 2e-4),
                         ("max_inverse_bind_error", 2e-4), ("max_joint_rest_error", 2e-4),
                         ("max_raw_normal_error", 2e-6), ("max_raw_uv_error", 2e-4),
                         ("max_raw_color_error", 2e-6), ("max_weight_error", 2e-4)):
        if not 0 <= number(fidelity[key], key) <= maximum:
            raise ValueError(f"Modular fidelity exceeded the {key} budget.")
    for key in ("clip_name", "hidden_region_id"):
        text = report["pose"][key]
        if not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", text):
            raise ValueError("Unsafe preview caption.")
    if report["pose"]["hidden_region_id"] not in {item["id"] for item in modular["contract"]["spec"]["regions"]}:
        raise ValueError("The hidden preview region does not belong to this GLB.")
    if not math.isfinite(number(report["pose"]["frame"], "animation frame")):
        raise ValueError("Invalid animation frame.")
    if modular.get("source_rig_isolation") != {
            "mesh_count": 1, "armature_count": 0, "animation_count": 0, "vertex_group_count": 0}:
        raise ValueError("The reconstruction reference retained source rig data.")
    if (number(report["pose"]["maximum_deformation_m"], "pose deformation") <= .001
            or number(report["pose"]["maximum_socket_motion_m"], "socket motion") <= .001):
        raise ValueError("The imported preview animation did not visibly deform the character/sockets.")
    reports = report.get("reconstruction", [])
    if {item.get("source_asset") for item in reports} != {"quaternius_human", "quaternius_ual1"} or len(reports) != 2:
        raise ValueError("Missing independent humanoid reconstruction benchmarks.")
    for item in reports:
        if item.get("resolution") != 128 or item.get("surface_refinement") != "organic":
            raise ValueError("The reconstruction score does not use the qualified Organic settings.")
        assert_refinement_quality(item["refinement"], min_roughness_reduction=.2, min_contour_reduction=.5)
        assert_detail_surface_quality(item["surface_3d"], minimum_fscore=.88)
        silhouette = item["silhouette"]
        if (unit_measure(silhouette["mean_iou"], "IoU") < .88
                or silhouette["valid_input_views"] != silhouette["total_views"]
                or silhouette["total_views"] != 10
                or len(silhouette["per_view_iou"]) != 10
                or min(unit_measure(value, "view IoU") for value in silhouette["per_view_iou"].values()) < .8
                or unit_measure(item["surface_3d"]["surface_fscore"], "surface F-score") < .97
                or unit_measure(item["surface_3d"]["max_extent_error"], "extent error") > .08
                or unit_measure(item["landmarks"]["mean_error_in_heights"], "mean joint error") > .04
                or unit_measure(item["landmarks"]["max_error_in_heights"], "maximum joint error") > .09
                or type(item["connectivity"]["component_count"]) is not int
                or item["connectivity"]["component_count"] != 1
                or unit_measure(item["skin_weights"]["weighted_fraction"], "skin coverage") != 1):
            raise ValueError("The displayed reconstruction benchmark did not meet its geometry/rig gates.")
    return report


def _percent_reduction(values: dict, before: str, after: str) -> str:
    start, end = number(values[before], before), number(values[after], after)
    if start <= 0 or end < 0:
        raise ValueError("Invalid refinement residual.")
    return f"{100 * (1 - end / start):.1f}%"


def build_comment(*, sha: str, run_url: str, status: str, evidence: dict | None = None,
                  image_root: str | None = None, artifact_url: str | None = None,
                  reason: str | None = None) -> str:
    validate_revision(sha)
    lines = [MARKER, "", "## Meshvenn — pipeline personnage V2", "",
             f"Révision exécutée : `{sha[:12]}` · [Run et contrôles]({run_url})", ""]
    if status != "success" or evidence is None:
        lines += ["**Preuve V2 indisponible pour cette révision. Aucun succès ni ancien rendu n’est substitué.**", "",
                  f"État du job : `{status}`. " + (reason or "Consulter les contrôles du run."), ""]
        if artifact_url:
            lines += [f"[Diagnostics disponibles]({artifact_url}) — ils ne constituent pas un résultat certifié.", ""]
        return "\n".join(lines)
    modular, pose = evidence["modular"], evidence["pose"]
    regions = len(modular["contract"]["spec"]["regions"])
    sockets = len(modular["contract"]["spec"]["sockets"])
    lines += ["`GLB source → 10 vues calibrées → Native Organic → UV Bake V2 → Canonical V2 → Motion → GLB modulaire`", "",
              f"Rendus de preuve : **GLB final réimporté**, résolution {modular['resolution']}, "
              f"{regions} régions, {sockets} sockets, **18 joints natifs / 43 clips**. Aucun rig source transmis à la reconstruction.", ""]
    lines += [appearance_caption(modular["appearance"]), ""]
    if image_root:
        lines += ["| Source isolée | Export texturé · repos | Animation réellement importée |",
              "| :---: | :---: | :---: |",
              f"| ![Source]({image_root}/source.png) | ![Rest]({image_root}/rest.png) | ![Pose]({image_root}/pose.png) |", ""]
    else:
        lines += ["Les six rendus réels sont disponibles dans l’artefact : source isolée, repos texturé, animation, "
                  "région masquée, sockets au repos et animés. Aucune image ancienne n’est substituée.", ""]
    lines += [
              f"Clip : `{pose['clip_name']}` · frame `{pose['frame']:.2f}` · déplacement mesuré "
              f"`{pose['maximum_deformation_m']:.4f} m`.", ""]
    if image_root:
        lines += ["| Région masquée, même pose | Diagnostic X-ray · sockets repos | Diagnostic X-ray · sockets animation |",
              "| :---: | :---: | :---: |",
              f"| ![Hidden region]({image_root}/hidden.png) | ![Rest sockets]({image_root}/sockets_rest.png) | ![Animated sockets]({image_root}/sockets_pose.png) |", ""]
    lines += [
              f"Région masquée : `{pose['hidden_region_id']}`. Les marqueurs orange sont les positions des sockets calculées à partir des TRS du contrat, "
              "dans une vue X-ray à matériau diagnostic séparé. Les vues repos/animation/masquage conservent les matériaux exportés ; "
              "aucun os ni accessoire n’est ajouté à l’export. Le TRS complet est contrôlé séparément.", "",
              "### Contrôles du découpage — ce GLB", "",
              "| Mesure | Résultat |",
              "| :--- | ---: |",
              f"| Couverture des faces | {modular['partition_authoring']['surface_coverage']['unowned_source_polygons']} perdues / "
              f"{modular['partition_authoring']['surface_coverage']['duplicated_source_polygons']} dupliquées |",
              f"| Erreur maximale repos / pose composée | {modular['roundtrip']['max_rest_error']:.3g} / "
              f"{modular['roundtrip']['max_compound_deformation_error']:.3g} m |",
              f"| Masquage indépendant / socket composé | {modular['roundtrip']['max_hide_independence_error']:.3g} / "
              f"{modular['roundtrip']['max_socket_compound_error']:.3g} |",
              "| Fidélité positions, triangles, UV, normales brutes, poids, bind et matériaux | PASS · contrôles séparés |", "",
              "<details>", "<summary>Qualité de reconstruction — benchmarks séparés, résolution 128</summary>", "",
              "Ces deux scores ne sont pas attribués au GLB modulaire de résolution 64 présenté ci-dessus.", "",
              "| Source | IoU silhouette | F-score 3D · 5% | F-score triangles · 1% | Erreur moyenne joints / hauteur | Rugosité réduite | Résidu contour réduit |",
              "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in evidence["reconstruction"]:
        refinement = item["refinement"]
        detail_score = assert_detail_surface_quality(item["surface_3d"], minimum_fscore=.88)
        lines.append(f"| {item['source_asset']} | {item['silhouette']['mean_iou']:.4f} | "
                     f"{item['surface_3d']['surface_fscore']:.4f} | {detail_score:.4f} | {item['landmarks']['mean_error_in_heights']:.4f} | "
                     f"{_percent_reduction(refinement, 'roughness_before_in_voxels', 'roughness_after_in_voxels')} | "
                     f"{_percent_reduction(refinement, 'mean_contour_residual_before_in_voxels', 'mean_contour_residual_after_in_voxels')} |")
    lines += ["", "Gates réels : IoU ≥ 0.88 (chaque vue ≥ 0.80), F-score historique ≥ 0.97, "
              "F-score aux triangles à 1% ≥ 0.88, joints moyens ≤ 0.04 H / "
              "pire ≤ 0.09 H, rugosité réduite ≥ 20%, contour réduit ≥ 50%, surface connectée et skin complet.", "",
              "Les distances utilisent les boîtes englobantes normalisées indépendamment : elles ne certifient ni "
              "l’échelle absolue ni une anatomie réaliste. Normales géométriques et défauts topologiques sont "
              "rapportés séparément, sans prétendre certifier l’absence d’intersections.", "",
              "</details>", ""]
    if artifact_url:
        lines += [f"[Télécharger les preuves V2]({artifact_url}) : `modular_character/character.glb`, "
                  "`source.blend` éditable, `authoring.json`, `manifest.json`, vues et rapports détaillés.", ""]
    lines += [f"SHA-256 du GLB rendu : `{modular['sha256']}`.", "",
              "**Portée** : fidélité Blender/export certifiée ; les contrôles Godot/Stytch, mobile et qualité visuelle "
              "des textures restent distincts. Les seams ouvertes sont intentionnelles ; aucun cap n’est ajouté.", "",
              "Diagnostics L2/L10 legacy : voir le commentaire séparé et replié ; ce n’est pas la pipeline V2.", ""]
    return "\n".join(lines)
