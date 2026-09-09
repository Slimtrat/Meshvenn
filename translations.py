from __future__ import annotations

import bpy


TRANSLATIONS = {
    "en": {
        "projection_tool": "Projection Tool",
        "projection_views": "Projection Views",
        "turntable_presets": "Turntable Presets",
        "selected_projection": "Selected Projection",
        "generation": "Generation",
        "scale": "Scale",
        "cleanup": "Cleanup",
        "generate_scan": "Generate Scan",
        "workflow": "Workflow",

        "enabled": "Enabled",
        "name": "Name",
        "image": "Image",
        "azimuth": "Azimuth",
        "elevation": "Elevation",
        "flip_x": "Flip X",

        "mode": "Mode",
        "resolution": "Resolution",
        "threshold": "Threshold",
        "symmetry_x": "Symmetry X",

        "normalize_height": "Normalize Height",
        "target_height": "Target Height",

        "auto_remesh": "Auto Remesh",
        "voxel_size": "Voxel Size",
        "smooth": "Smooth",

        "use_transparent": "Use transparent silhouettes.",
        "more_angles": "More angles = tighter visual hull.",
        "start_low": "Start at 64-96 voxels.",

        "front_side_preset": "Front + Side",
        "add_projection": "Add Projection",
        "remove_projection": "Remove Projection",

        "diagnostics": "Diagnostics",
        "active_views": "Active views",
        "missing_images": "Missing images",
    },

    "fr": {
        "projection_tool": "Outil de projection",
        "projection_views": "Vues de projection",
        "turntable_presets": "Préréglages de rotation",
        "selected_projection": "Projection sélectionnée",
        "generation": "Génération",
        "scale": "Échelle",
        "cleanup": "Nettoyage",
        "generate_scan": "Générer le scan",
        "workflow": "Utilisation",

        "enabled": "Activée",
        "name": "Nom",
        "image": "Image",
        "azimuth": "Azimut",
        "elevation": "Élévation",
        "flip_x": "Retourner horizontalement",

        "mode": "Mode",
        "resolution": "Résolution",
        "threshold": "Seuil",
        "symmetry_x": "Symétrie X",

        "normalize_height": "Normaliser la hauteur",
        "target_height": "Hauteur cible",

        "auto_remesh": "Remesh automatique",
        "voxel_size": "Taille des voxels",
        "smooth": "Lissage",

        "use_transparent": "Utilisez des silhouettes sur fond transparent.",
        "more_angles": "Plus de vues = volume plus précis.",
        "start_low": "Commencez à 64-96 voxels.",

        "front_side_preset": "Face + Profil",
        "add_projection": "Ajouter une projection",
        "remove_projection": "Supprimer la projection",

        "diagnostics": "Diagnostic",
        "active_views": "Vues actives",
        "missing_images": "Images manquantes",
    },
}


def get_language() -> str:
    try:
        language = bpy.context.preferences.view.language
    except Exception:
        return "en"

    if language.lower().startswith("fr"):
        return "fr"

    return "en"


def tr(key: str) -> str:
    language = get_language()

    language_table = TRANSLATIONS.get(
        language,
        TRANSLATIONS["en"],
    )

    return language_table.get(
        key,
        TRANSLATIONS["en"].get(key, key),
    )