"""Accessible offline comparison of the exact rendered and downloadable GLBs."""
from __future__ import annotations

import html
import json
from pathlib import Path,PurePosixPath

from .render import _sha
from .review import review_template


def _validate_package(manifest):
    root=Path(manifest["output_root"]).resolve()
    if manifest.get("status")!="completed":raise ValueError("Rendering is incomplete")
    assets=manifest["assets"]
    if len({a["asset_id"] for a in assets})!=len(assets):raise ValueError("Duplicate assets")
    source=next(a for a in assets if a["role"]=="source")
    source_frames={(f["mode"],f["crop"],f["angle"]):f for f in source["frames"]}
    for asset in assets:
        if asset["reload"].get("verified") is not True or asset["reload"].get("source_glb_sha256")!=asset["glb"]["sha256"]:
            raise ValueError("GLB reload is not bound to the downloadable file")
        for record in [asset["glb"],asset["mesh"],*asset["frames"]]:
            relative=record["path"]
            if type(relative) is not str or "\\" in relative or ":" in relative or PurePosixPath(relative).is_absolute() or any(p in ("",".","..") for p in relative.split("/")):
                raise ValueError("Unsafe package path")
            path=root/relative
            if not path.resolve().is_relative_to(root) or _sha(path)!=record["sha256"]:raise ValueError("Package file changed")
        keys=[(f["mode"],f["crop"],f["angle"]) for f in asset["frames"]]
        if len(keys)!=len(set(keys)) or set(keys)!=set(source_frames):raise ValueError("Synchronized frames are missing or duplicated")
        for frame in asset["frames"]:
            key=(frame["mode"],frame["crop"],frame["angle"])
            if key not in source_frames or frame["camera"]!=source_frames[key]["camera"]:
                raise ValueError("Comparison cameras differ; per-asset fit is forbidden")


def write_contact_sheet(render_manifest:dict,output:Path,*,candidate_id:str|None=None)->Path:
    """A coordinated, labelled source/result PNG, with no generated image content."""
    from PIL import Image,ImageDraw,ImageFont
    _validate_package(render_manifest)
    root=Path(render_manifest["output_root"])
    source=next(a for a in render_manifest["assets"] if a["role"]=="source")
    candidates=[a for a in render_manifest["assets"] if a["role"]=="candidate"]
    candidate=next((a for a in candidates if a["asset_id"]==candidate_id),None) if candidate_id else candidates[0] if candidates else None
    if candidate is None:raise ValueError("No candidate for before/after comparison")
    def frame(asset):
        frames=asset["frames"]
        return next((f for f in frames if f["mode"]=="flat" and f["crop"]=="full" and f["angle"]==45),
                    next(f for f in frames if f["mode"]=="flat" and f["crop"]=="full"))
    tiles=[]
    for asset in (source,candidate):
        with Image.open(root/frame(asset)["path"]) as image:tiles.append(image.convert("RGB"))
    if tiles[0].size!=tiles[1].size:raise ValueError("Comparison frames must have the same raster size")
    width,height=tiles[0].size;banner=84;footer=44;gutter=12
    result=Image.new("RGB",(width*2+gutter,height+banner+footer),(17,24,39))
    draw=ImageDraw.Draw(result)
    def font_at(size):
        for name in ("C:/Windows/Fonts/segoeui.ttf","DejaVuSans.ttf"):
            try:return ImageFont.truetype(name,size)
            except OSError:pass
        return ImageFont.load_default(size=size)
    font=font_at(max(15,width//26));small=font_at(max(12,width//38))
    for index,(asset,tile,title) in enumerate(zip((source,candidate),tiles,("AVANT — SOURCE À CONSERVER","APRÈS — RÉSULTAT OBTENU"))):
        x=index*(width+gutter);result.paste(tile,(x,banner))
        draw.text((x+18,12),title,fill="white",font=font)
        draw.text((x+18,45),asset["label"][:66],fill=(187,210,237),font=small)
        draw.text((x+18,banner+height+10),"GLB "+asset["glb"]["sha256"][:16]+"… · forme à facettes",fill=(187,210,237),font=small)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);result.save(output)
    return output


def write_presentation(render_manifest:dict,output:Path)->Path:
    """Write an offline HTML viewer next to render-manifest assets (no CDN)."""
    root=Path(render_manifest["output_root"]).resolve();output=Path(output).resolve()
    if output!=root:raise ValueError("HTML must remain beside its audited render package")
    output.mkdir(parents=True,exist_ok=True)
    assets=render_manifest["assets"]
    if len([a for a in assets if a["role"]=="source"])!=1 or not any(a["role"]=="candidate" for a in assets):
        raise ValueError("Visible comparison needs a source and a candidate")
    _validate_package(render_manifest)
    template=review_template(render_manifest)
    (output/"human-review-template.json").write_text(json.dumps(template,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    data=json.dumps({"manifest":render_manifest,"review":template},ensure_ascii=False,allow_nan=False).replace("<","\\u003c")
    source=next(a for a in assets if a["role"]=="source")
    first=next(a for a in assets if a["role"]=="candidate")
    def initial(asset):
        return next((f["path"] for f in asset["frames"] if f["mode"]=="flat" and f["crop"]=="full" and f["angle"]==45),
                    next(f["path"] for f in asset["frames"] if f["mode"]=="flat" and f["crop"]=="full"))
    page='''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Personnage — comparaison avant / après</title><style>
:root{color-scheme:dark;font:17px/1.5 system-ui;background:#101827;color:#edf3fb}body{max-width:1400px;margin:auto;padding:24px}h1{font-size:2rem;margin-bottom:4px}p{max-width:85ch}.intro{color:#bbd2ed}.tools,fieldset{padding:18px;border:1px solid #62768d;border-radius:10px;margin:18px 0}.tools{display:flex;flex-wrap:wrap;align-items:center;gap:20px}label{display:inline-block}select,button,input,textarea{font:inherit}select,button,textarea,input[type=text]{background:#23364c;color:white;border:1px solid #8caacb;border-radius:5px;padding:8px}button{cursor:pointer}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #e9c86c;outline-offset:4px}input[type=range]{width:240px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.panel{background:#172336;border:1px solid #62768d;border-radius:12px;padding:14px;min-width:0}.panel h2{margin:0;font-size:1.25rem}.panel img{width:100%;display:block;aspect-ratio:1;background:#141b27;object-fit:contain}.caption{min-height:2em;color:#bbd2ed}.sha{font:12px/1.5 monospace;overflow-wrap:anywhere}a{color:#b8d9ff}small{color:#c3cfdc}.question{padding:12px 0}.question strong{display:block}.question label{margin:8px 22px 4px 0}textarea{width:min(96%,700px);min-height:80px}.notice{border-left:4px solid #edc56b;padding:8px 18px}summary{cursor:pointer}@media(max-width:720px){body{padding:14px}.pair{gap:8px}.panel{padding:7px}.panel h2{font-size:1rem}.caption{font-size:14px}.tools{gap:12px}.sha{font-size:10px}}
</style><h1>La forme du personnage, avant / après</h1><p class="intro">À gauche : la source à conserver. À droite : le résultat réellement exporté puis rechargé. Les deux images gardent le même angle, la même échelle et le même cadrage.</p>
<div class="tools"><label>Résultat à comparer <select id="candidate"></select></label><label>Lecture <select id="mode"><option value="flat">Forme — facettes visibles</option><option value="material">Matériaux du GLB</option></select></label><label>Cadrage <select id="crop"><option value="full">Personnage entier</option><option value="head">Gros plan tête</option><option value="bust">Gros plan buste</option></select></label><label>Tourner ensemble <input id="angle" type="range" min="0" step="1" value="1"><output id="anglelabel">45°</output></label><button id="play" type="button">Lancer la rotation</button></div>
<div class="pair"><section class="panel"><h2>AVANT · Source à conserver</h2><div class="caption" id="source-label">SOURCE_LABEL</div><img id="source-image" src="SOURCE_IMAGE" alt="Source : personnage entier, facettes visibles, angle commun"><p id="source-links"></p></section><section class="panel"><h2>APRÈS · Résultat obtenu</h2><div class="caption" id="candidate-label">CANDIDATE_LABEL</div><img id="candidate-image" src="CANDIDATE_IMAGE" alt="Résultat : personnage entier, facettes visibles, même angle que la source"><p id="candidate-links"></p></section></div>
<p class="notice">Le mode « forme » impose des normales plates pour révéler les facettes. Le mode « matériaux » conserve les matériaux et le lissage importés. Les gros plans suivent des zones du cadre source commun ; ils ne constituent pas une segmentation anatomique. Aucun ajustement du cadrage par résultat.</p>
<h2>Votre avis sur ce résultat</h2><p>Aucun avis humain n’a été inventé. Les réponses restent locales dans ce navigateur ; « enregistrer » télécharge votre fiche JSON sans envoi réseau. La qualité générale reste inconnue, y compris après cet avis.</p><label>Votre nom ou identifiant <input type="text" id="reviewer" autocomplete="name"></label><fieldset><legend>Votre pratique de la 3D</legend><label><input type="radio" name="experience_3d" value="beginner"> Débutant ou aucune pratique</label> <label><input type="radio" name="experience_3d" value="occasional"> Pratique occasionnelle</label> <label><input type="radio" name="experience_3d" value="experienced"> Pratique régulière ou professionnelle</label></fieldset><p><label><input type="checkbox" id="attestation"> J’atteste avoir personnellement examiné ces images et renseigné cet avis. Cette déclaration ne vérifie pas mon identité.</label></p><fieldset id="questions"><legend>Ce que vous voyez</legend></fieldset><label>Commentaire<br><textarea id="comment"></textarea></label><p><button id="save" type="button">Enregistrer mon avis sur ce résultat</button> <output id="saved" role="status"></output></p>
<details><summary>Fichiers, provenance et limites</summary><p>Chaque téléchargement GLB reprend exactement les octets importés. Les maillages JSON sont extraits après import, en coordonnées monde Blender. Les références éventuelles restent distinctes des résultats. Cette page ne certifie ni l’identité, ni la topologie, ni la qualité générale d’un personnage.</p><ul><li><a href="render-manifest.json">Manifeste des rendus et empreintes SHA256</a></li><li><a href="human-review-template.json">Fiche de revue encore inconnue</a></li></ul><div id="references"></div></details>
<script id="data" type="application/json">DATA_JSON</script><script>
const data=JSON.parse(document.getElementById('data').textContent),m=data.manifest,review=data.review;
const source=m.assets.find(a=>a.role==='source'),candidates=m.assets.filter(a=>a.role==='candidate'),$=id=>document.getElementById(id);
for(const option of [...$('mode').options])if(!m.modes.includes(option.value))option.remove();
for(const a of candidates){const o=document.createElement('option');o.value=a.asset_id;o.textContent=a.label;$('candidate').append(o)}
for(const q of review.questions){const d=document.createElement('div');d.className='question';const title=document.createElement('strong');title.textContent=q.label;d.append(title);for(const [value,label] of [['yes','Oui'],['no','Non'],['unknown','Je ne peux pas conclure']]){const l=document.createElement('label'),i=document.createElement('input');i.type='radio';i.name=q.id;i.value=value;i.checked=value==='unknown';l.append(i,document.createTextNode(' '+label));d.append(l)}$('questions').append(d)}
$('angle').max=m.angles.length-1;const initial=m.angles.indexOf(45);$('angle').value=initial<0?0:initial;
function chosen(){return candidates.find(a=>a.asset_id===$('candidate').value)}
let editingAssetId=chosen().asset_id;
function captureAnswers(){const row=review.reviews.find(r=>r.asset_id===editingAssetId);for(const q of review.questions)row.answers[q.id]=document.querySelector('input[name="'+q.id+'"]:checked').value;row.comment=$('comment').value;}
function links(id,a){const p=$(id);p.replaceChildren();const l=document.createElement('a');l.href=a.glb.path;l.download=a.asset_id+'.glb';l.textContent='Télécharger ce GLB exact';const sha=document.createElement('div');sha.className='sha';sha.textContent='SHA256 '+a.glb.sha256;p.append(l,sha)}
function update(){const crop=$('crop').value,mode=$('mode').value,angle=crop==='full'?m.angles[Number($('angle').value)]:45;$('angle').disabled=crop!=='full';$('anglelabel').textContent=angle+'°';for(const [key,a] of [['source',source],['candidate',chosen()]]){const f=a.frames.find(f=>f.mode===mode&&f.crop===crop&&f.angle===angle);const img=$(key+'-image');if(f){img.src=f.path;img.alt=a.label+' — '+(mode==='flat'?'facettes visibles':'matériaux')+', '+crop+', '+angle+'°';img.hidden=false}else{img.hidden=true}$(key+'-label').textContent=a.label;links(key+'-links',a)}}
let timer=null;function stop(){if(timer)clearInterval(timer);timer=null;$('play').textContent='Lancer la rotation'}
$('play').onclick=()=>{if(timer){stop();return}$('crop').value='full';timer=setInterval(()=>{$('angle').value=(Number($('angle').value)+1)%m.angles.length;update()},850);$('play').textContent='Arrêter la rotation';update()};
for(const id of ['angle','mode','crop'])$(id).addEventListener('input',()=>{if(id==='crop')stop();update()});
$('candidate').onchange=()=>{captureAnswers();editingAssetId=chosen().asset_id;const row=review.reviews.find(r=>r.asset_id===editingAssetId);for(const q of review.questions)for(const i of document.getElementsByName(q.id))i.checked=i.value===row.answers[q.id];$('comment').value=row.comment;update()};
$('save').onclick=()=>{captureAnswers();const name=$('reviewer').value.trim();if(!name){$('saved').textContent='Indiquez votre nom ou identifiant pour attribuer cet avis.';return}review.reviewer=name;review.reviewed_at=new Date().toISOString();review.self_attestation=$('attestation').checked;const experience=document.querySelector('input[name="experience_3d"]:checked');review.experience_3d=experience?experience.value:null;review.status=review.self_attestation&&review.experience_3d!==null?'recorded':'unknown';review.quality_certification='unknown';const blob=new Blob([JSON.stringify(review,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='avis-personnage.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('saved').textContent='Fiche téléchargée. '+(review.status==='recorded'?'Déclaration personnelle non vérifiée.':'Avis non attesté ou expérience non renseignée : statut inconnu.')+' Aucune certification automatique.'};
for(const a of m.assets.filter(a=>a.role==='reference')){const p=document.createElement('p'),l=document.createElement('a');l.href=a.glb.path;l.textContent='Référence distincte : '+a.label;p.append(l);$('references').append(p)}update();
</script></html>'''
    for token,value in (("SOURCE_LABEL",html.escape(source["label"])),("CANDIDATE_LABEL",html.escape(first["label"])),
                        ("SOURCE_IMAGE",html.escape(initial(source),quote=True)),("CANDIDATE_IMAGE",html.escape(initial(first),quote=True)),("DATA_JSON",data)):
        page=page.replace(token,value)
    path=output/"index.html";path.write_text(page,encoding="utf-8")
    try:write_contact_sheet(render_manifest,output/"before-after.png")
    except ImportError:pass  # HTML and original coordinated PNGs remain usable without optional Pillow.
    return path
