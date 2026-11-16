"""Offline French evidence page: inspect files and record an actual person's review."""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path


def image_cards(pictures):
    figures = []
    for label, path in pictures:
        raw = Path(path).read_bytes()
        if len(raw) > 33_554_432 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("A preview must be a bounded original PNG.")
        encoded = base64.b64encode(raw).decode("ascii")
        figures.append('<figure><img alt="' + html.escape(label, quote=True) +
                       '" src="data:image/png;base64,' + encoded + '"><figcaption>' + html.escape(label) + '</figcaption></figure>')
    return "".join(figures)


def difference_summary(comparison):
    differences = comparison.get("directional_differences") or {}
    outside = differences.get("outside_edit_mask") or {}
    def count(value):
        return "Non calculable" if value is None else html.escape(str(value)) + " pixel(s)"
    def empty(value):
        return "Non calculable" if value is None else "Vide" if value else "Non vide"
    rows = []
    for key, label in (("before_minus_after", "1 − 2 : silhouette disparue"),
                       ("after_minus_before", "2 − 1 : silhouette ajoutée")):
        result = differences.get(key) or {}
        rows.append('<tr><th scope="row">' + label + '</th><td>' + count(result.get("outside_edit_mask_pixels")) +
                    '</td><td>' + empty(result.get("outside_edit_mask_empty")) + '</td></tr>')
    rows.append('<tr><th scope="row">Couleurs ou transparence modifiées</th><td>' + count(outside.get("changed_rgba_pixels")) +
                '</td><td>' + empty(outside.get("rgba_difference_empty")) + '</td></tr>')
    note = ("Les différences ne sont pas calculées : les dimensions des images diffèrent. Aucun redimensionnement automatique n’est appliqué."
            if differences.get("reason") == "image_grid_changed" else
            "Les deux différences de silhouette doivent être vides, et les autres couleurs et valeurs de transparence doivent être identiques. Le contour utilise le fond transparent ; les couleurs restent vérifiées séparément.")
    return ('<section aria-label="Différences hors zone autorisée"><h2>1 − 2 et 2 − 1</h2>'
            '<p>Ces contrôles portent sur les pixels hors du badge à modifier.</p><table><thead><tr><th>Contrôle</th><th>Différence</th><th>Ensemble</th></tr></thead><tbody>' +
            "".join(rows) + '</tbody></table><p>' + note + '</p></section>')


def render_page(output: Path, report: dict, *, pictures=(), downloads=(), review_template=None, difference_pictures=()) -> None:
    """Only verified caller-selected files are embedded; no remote scripts/resources."""
    figures = image_cards(pictures)
    maps = image_cards(difference_pictures)
    map_section = '<details><summary>Voir les différences calculées</summary><div class="grid">' + maps + '</div></details>' if maps else ""
    links = []
    for label, path in downloads:
        path = Path(path)
        raw = path.read_bytes()
        if len(raw) > 67_108_864:
            raise ValueError("Download exceeds the evidence size limit.")
        mime = "model/gltf-binary" if path.suffix == ".glb" else "application/json"
        links.append('<a download="' + html.escape(path.name, quote=True) + '" href="data:' + mime + ';base64,' +
                     base64.b64encode(raw).decode("ascii") + '">' + html.escape(label) + '</a>')
    details = html.escape(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    review = "" if review_template is None else review_form(review_template)
    state = report.get("qualification_status", "unknown")
    explanation = "Des preuves restent à compléter." if state == "unknown" else "Un contrôle a échoué : les détails restent conservés." if state == "fail" else "Les contrôles déclarés sont terminés."
    comparison = report.get("comparison") or {}
    if comparison.get("reason") == "image_grid_changed":
        before, after = comparison["assets"]["before"], comparison["assets"]["after"]
        explanation = (f"L’outil a changé le format : {before['width']} × {before['height']} → "
                       f"{after['width']} × {after['height']}. La correction n’est pas validée.")
    elif comparison.get("outside_pixels_status") == "fail":
        explanation = "L’image a été modifiée en dehors du badge. La correction n’est pas validée."
    document = '''<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>MeshVenn — dossier de qualification</title>
<style>
:root{font:17px/1.55 system-ui,sans-serif;color:#172b35;background:#f4f7fa;color-scheme:light}
body{max-width:1100px;margin:auto;padding:32px 22px}h1{font-size:2rem;line-height:1.2}h2{font-size:1.4rem;margin-top:2rem}
.notice{border-left:5px solid #ae6b00;background:#fff4d9;padding:15px 20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px}
figure{margin:0;padding:12px;background:white;border:1px solid #dce3e8;border-radius:10px}img{width:100%;height:auto;background:repeating-conic-gradient(#f4f4f4 0% 25%,#fff 0% 50%) 50%/24px 24px}figcaption{padding-top:9px}
a,button{color:#124d6b}a{display:inline-block;margin:8px 14px 8px 0}button{font:inherit;background:#153f56;color:white;border:0;padding:12px 18px;border-radius:6px;cursor:pointer}
table{width:100%;table-layout:fixed;border-collapse:collapse;background:white}th,td{padding:10px;text-align:left;border:1px solid #dce3e8;overflow-wrap:anywhere}thead{background:#e8eff4}
label{display:block;font-weight:600;margin-top:17px}input,select,textarea{font:inherit;max-width:100%;padding:8px;border:1px solid #8999a4;border-radius:4px}textarea{width:95%;min-height:65px}fieldset{border:1px solid #b7c4cc;margin:22px 0;padding:16px}legend{font-weight:700}
pre{max-height:540px;overflow:auto;padding:16px;background:white;white-space:pre-wrap;word-break:break-word}small{color:#405766}output{display:block;margin-top:12px}a:focus,button:focus,input:focus,select:focus,textarea:focus{outline:3px solid #cd7b00;outline-offset:3px}
</style>
<main><h1>Test : passer le badge rose au bleu</h1>
<p class="notice">''' + html.escape(explanation) + ''' Une amélioration de couleur ne suffit pas à valider le personnage ni un modèle 3D corrigé.</p>
<p>La première image montre le badge rose à corriger ; la deuxième est le résultat conservé de l’outil. La référence bleue est montrée ensuite. Seul l’intérieur du badge devait changer. Vérifiez aussi le fanion, les membres et la transparence autour du robot.</p>
<section aria-label="Images de comparaison"><div class="grid">''' + figures + '''</div></section>''' + difference_summary(comparison) + map_section + '''
<h2>Fichiers et provenance</h2>
<p>Le GLB de référence provient de la scène originale et a été rechargé pour vérification. Il ne représente pas une reconstruction de l’image corrigée. La livraison d’un GLB corrigé reste à qualifier.</p>''' + "".join(links) + review + '''
<details><summary>Mesures et résultats complets</summary><pre>''' + details + '''</pre></details>
<p><small>Ce dossier fonctionne hors ligne. Aucune réponse n’est envoyée automatiquement. Les fichiers originaux restent inchangés ; la revue humaine est enregistrée séparément.</small></p></main></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def review_form(template: dict) -> str:
    """Template is bound by archive/review validation before human answers exist."""
    payload = json.dumps(template, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return '''<h2>Votre revue</h2><p>Répondez vous-même, après inspection des images et du fichier. « Incertain » est une réponse utile. Ce questionnaire ne valide pas automatiquement l’essai.</p>
<form id="review"><fieldset><legend>Votre expérience</legend>
<label for="reviewer">Nom ou pseudonyme</label><input id="reviewer" maxlength="120" required autocomplete="off">
<label for="experience">Pratique de la 3D</label><select id="experience" required><option value="">Choisir</option><option value="none">Aucune</option><option value="basic">Débutant</option><option value="experienced">Expérimenté</option></select>
<label><input id="human" type="checkbox" required> Je suis une personne et je remplis cette revue moi-même.</label></fieldset>
<fieldset><legend>Ce que vous constatez</legend>
<label for="region">Quelle partie devait être corrigée ?</label><textarea id="region" maxlength="2000" required></textarea>
<label for="region_status">Avez-vous pu identifier cette partie ?</label><select id="region_status"><option value="unknown">Incertain</option><option value="pass">Oui</option><option value="fail">Non</option></select>
<label for="result">La correction vous paraît-elle réussie ?</label><select id="result"><option value="unknown">Incertain</option><option value="pass">Oui</option><option value="fail">Non</option></select>
<label for="preservation">Qu’est-ce qui a changé ailleurs ? Observez notamment le fanion, les mains et les pieds.</label><textarea id="preservation" maxlength="2000" required></textarea>
<label for="preservation_status">Les autres éléments vous paraissent-ils conservés ?</label><select id="preservation_status"><option value="unknown">Incertain</option><option value="pass">Oui</option><option value="fail">Non</option></select>
<label for="download">Avez-vous pu identifier et ouvrir le GLB de référence ? Décrivez ce que vous avez fait.</label><textarea id="download" maxlength="2000" required></textarea>
<label for="download_status">Avez-vous pu ouvrir ce fichier ?</label><select id="download_status"><option value="unknown">Non vérifié</option><option value="pass">Oui</option><option value="fail">Non</option></select>
<label for="limitations">Doutes, défauts ou éléments non vérifiés</label><textarea id="limitations" maxlength="2000" required></textarea>
</fieldset><button type="submit">Enregistrer mes réponses en JSON</button><output id="feedback" aria-live="polite"></output></form>
<script id="review-template" type="application/json">''' + payload + '''</script>
<script>
document.getElementById('review').addEventListener('submit',function(event){
 event.preventDefault();const value=JSON.parse(document.getElementById('review-template').textContent);
 const field=id=>document.getElementById(id).value.trim();
 value.reviewer={kind:'human',name:field('reviewer'),experience:field('experience'),non_3d:field('experience')!=='experienced',attested:true};
 value.review_id+='_'+Date.now();value.state='submitted';
 value.reviewed_at=new Date().toISOString();
 value.tasks=[{task_id:'identify_region',question:'Quelle partie devait être corrigée ?',result:field('region_status'),evidence_refs:value.image_sha256s,notes:field('region')},{task_id:'assess_correction',question:'La correction vous paraît-elle réussie ?',result:field('result'),evidence_refs:value.image_sha256s,notes:'Réponse visuelle déclarée par la personne.'},{task_id:'preserve_parts',question:'Les autres éléments sont-ils conservés ?',result:field('preservation_status'),evidence_refs:value.image_sha256s,notes:field('preservation')},{task_id:'open_reference_glb',question:'Avez-vous pu ouvrir le GLB de référence ?',result:field('download_status'),evidence_refs:value.glb_sha256s,notes:field('download')}];
 value.limitations=[field('limitations')];
 const blob=new Blob([JSON.stringify(value,null,2)+'\\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download='meshvenn-human-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById('feedback').textContent='Réponses enregistrées localement. Elles doivent être importées et vérifiées séparément ; aucune validation globale n’est déclarée.';
});
</script>'''
