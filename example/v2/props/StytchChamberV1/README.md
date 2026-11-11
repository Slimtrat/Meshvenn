# Stytch Chamber props V1

Two authored, rigid 3D props for the Chamber terrain kit. These are editable meshes,
not image billboards or reconstructions of the reference illustrations. The separate
authoring tools live in `scripts/chamber_props`; Meshvenn core/native code is unchanged.

| Asset | Closed dimensions (X/Y/Z metres) | Triangles | Clips |
| --- | --- | --- | --- |
| `chamber-door-v1.glb` | 1.30 / 1.80 / 0.20 | 2,988 | `door_closed`, `door_open` |
| `chamber-loot-cache-v1.glb` | 0.85 / 0.52 / 0.44 | 3,224 | `chest_closed`, `chest_open` |

Each GLB embeds its standard PBR base-color PNGs and uses three opaque materials:
cool painted stone, dark timber and aged bronze. Roughness is 0.76–0.90; metallic
is 0 for stone/timber and 0.35 for bronze. No custom shaders, forced lights, emission,
rigs, skins, morphs or automatic collision bodies. There are two mesh nodes per prop,
with four material surfaces on the door and six on the chest. Separate `.blend` files
pack the images and preserve geometry, UVs and two editable NLA animation tracks.

## Integration contract

glTF/Godot coordinates: +Y up, +Z front, one unit = one metre. Root transforms are
identity, origins are at the bottom centre and closed X bounds are symmetric.
The door sits behind the player plane, Z in [-0.20, 0]; the chest has Z in [-0.22, 0.22].
Bounding boxes in `pack.json` describe visible geometry, excluding empty sockets.

- Door: `DoorFrame` is fixed. `DoorHinge` rotates around its left vertical edge;
  `DoorLeaf` is its child. `door_open` rotates +90° around Y into the background.
  The pointed passage has width 0.75 m, spring height 1.02 m, apex 1.40 m and a
  0.07 m threshold. `RouteSignalSocket` is a frame locator for Host-controlled signals.
- Chest: `ChestBody` is a hollow container with a real bottom. `ChestLid` is a child
  of `LidHinge`, whose X axis runs along the rear rim. `chest_open` rotates -105°
  around X; the curved lid has a real inner surface. `LootSpawnSocket` sits at Y=0.66 m.
- Each clip lasts 0.6 seconds, is non-looping and animates only its hinge. `*_closed`
  explicitly resets the angle to zero; stop/play an open clip to animate opening.
  Host owns interaction, collected/unavailable states, route colours and loot decisions.
- `collision-spec.json` is advisory documentation only. Stytch keeps its existing
  collision authority until actual-game envelope comparisons approve a change.
  Do not auto-generate convex hulls that fill the doorway or chest cavity.

`pack.json` pins the GLB, editable source and texture SHA-256 values. Copy GLBs and
this manifest unchanged into the consumer; import them through Godot normally.
Standalone source PNGs are for editing; runtime GLBs do not depend on their paths.
The art direction follows Stytch's Chamber concept, but no private Stytch source,
reference image or game capture is redistributed. Geometry and deterministic painted
plates are authored in this repository and share its GPL-3.0-or-later licence.

## Fixture scope

These are useful non-skeletal Meshvenn reference cases: thin wall thickness, a pointed
negative space, a hollow curved shell, multiple independent rigid components, UV/PBR
retention, movable pivots and exact real-world scale. Asset acceptance independently
checks exported GLB structure, Blender reimport/closed surfaces, native Godot import,
four clip endpoints, fixed-body invariance and ray probes through closed/open voids.
This certifies asset delivery. It is not yet a score for Meshvenn's pixel-to-3D
reconstruction, hidden volume recovery or Android rendering performance.

## Reproduce

Use fresh output directories. Blender 5.2.1 and Godot 4.7.1 are used by CI.

```sh
blender --background --factory-startup --python-exit-code 1 --python scripts/author_stytch_chamber.py -- --output tmp/chamber-new
blender --background --factory-startup --python-exit-code 1 --python scripts/chamber_props/blender_smoke.py -- --pack tmp/chamber-new
python scripts/run_chamber_godot.py --godot /path/to/godot --pack tmp/chamber-new --output tmp/chamber-godot-new
blender --background --factory-startup --python-exit-code 1 --python scripts/chamber_props/render.py -- --pack tmp/chamber-new
python -m unittest discover -s tests -p test_chamber_props.py -v
python scripts/build_stytch_chamber_pack.py --pack tmp/chamber-new --output dist/stytch-chamber-v1-new.zip
```

The ZIP includes source tools, licence, editable sources, standalone textures, GLBs,
manifests, actual GLB renders and Blender/Godot evidence. Regenerated `.blend` bytes
include Blender metadata and are not a byte-reproducibility promise; delivered files
remain fingerprinted. CI validates both committed and independently regenerated assets.
