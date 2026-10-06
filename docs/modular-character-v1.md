# Modular character contract V1

Meshvenn can optionally export independently renderable skinned regions and
author-declared sockets. This is geometry and attachment authority, **not** a
damage model, equipment system, capability decision, or replacement armature.
The default whole-body GLB route is unchanged.

## Exporting

In Blender's EXPORT settings, enable **Modular Character** and select an authoring
JSON. Headless callers can provide `PipelineContext.metadata["export_modular_spec"]`
as a `ModularCharacterSpec` or its JSON dictionary; alternatively use
`export_modular_manifest_path`. An enabled mode without a valid manifest fails.
Every modular export runs fidelity validation before atomic publication, even if
the ordinary "Verify Export by Reimport" option is disabled.

The authoring document declares:

- `contract: "meshvenn.modular-character"`, `version: 1`, native `rig_id` and
  integer `rig_version` (the fixture retains `canonical-biped-v2`, eighteen joints).
- `coordinates`: right-handed glTF Y-up, +Z-forward, meters, and actual upstream
  height-normalization provenance. The exporter rejects contradictory or unknown
  provenance rather than assuming a height or reconstructing a coordinate frame.
- `regions`: arbitrary stable IDs, semantic roles, and unique exported node names.
  Five regions are illustrated; five is not a limit of the contract.
- `ownership`: exactly one declared region ID for **each original polygon**, in
  mesh polygon order, for every source object. `ownership_source_sha256` hashes the
  ordered local positions and topology so edits invalidate stale face assignments.
- `seams`: `open-shared-vertices`, empty `authoring_changes` and `caps`. V1 copies
  entire existing faces and duplicates shared vertices at intentional open seams;
  it does not cut, cap, weld, remesh, move vertices, or repair skinning.
- `sockets`: stable ID, unique role, owning region, exact native parent-bone name,
  translation, quaternion `[x,y,z,w]`, scale, `frame: "gltf-joint-local"` and
  `units: "meters"`. Transforms are authored values, not inferred equipment offsets.
- Derived `capabilities` describe actual regions/sockets and explicitly declared
  missing roles. Duplicate, ambiguous, dangling, or unsupported declarations fail.

V1 refuses shape keys, active non-armature modifiers, loose vertices, more than
four influences, and a region spanning multiple source-object frames. These are
explicit unsupported inputs, not silent loss of geometry or attributes.

## Reading the GLB

The GLB contains an object at `asset.extras.meshvenn_modular_character`:

```json
{
  "spec": { "contract": "meshvenn.modular-character", "version": 1 },
  "bindings": {
    "region_nodes": { "left-arm": 3 },
    "skin": 0,
    "joint_nodes": { "hand.L": 20 },
    "sockets": {
      "attach-left-arm": { "parent_joint_node": 20, "owner_region_node": 3 }
    }
  }
}
```

This is an abbreviated structural example; use the complete embedded document,
not these illustrative indices. References are resolved against the **same GLB**.
Region nodes also expose `meshvenn_region_id` and `meshvenn_region_role` extras.
Every region targets one shared skin, with the original joint names and binds.

Hide a region's mesh node, never delete its bones. Other regions still require the
same skeleton. A socket's world matrix is `joint_world * socket_local_TRS`, including
all inherited scale; the local TRS is not in Blender's display-bone basis. It is
relative to the exported glTF joint. Hide equipment by its declared owning region
if your presentation policy requires it; Meshvenn does not make that gameplay choice.
Metadata-only sockets add **no** skin joints.

## Reproducible generated fixture

Run from the repository root with Blender 5.2.1 and the built native engine:

```sh
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/benchmark_modular_character.py -- \
  --resolution 64 --output tmp/modular-character
```

The script isolates the CC0 UAL1 source at rest, renders ten calibrated views, and
runs the actual INPUT → native Geometry → UV Bake V2 → canonical V2 Rig → all
43 retargeted Motion clips → modular EXPORT path. No source rig or weights are
passed into reconstruction. The fixture's authoring planes are explicit,
fixture-specific T-pose design choices documented in `partition-authoring.json`;
they are **not** a generic classifier and never inspect dominant bone weights.

Outputs include `character.glb`, packed editable `source.blend`, `authoring.json`,
and a hash-linked `manifest.json` with resolved references and validation evidence.
The source keeps the authoritative whole-body mesh hidden, independently editable
derived preview parts visible, and the authoring JSON as a Blender Text datablock.
Edit the authoritative source and regenerate ownership/hashes before export;
preview copies are not a second surface authority. Fresh staging copies are
temporary and do not overwrite or rename the existing preview objects.

The committed fixture is in `example/v2/modular/UAL1/`. It is a pipeline/fidelity
fixture, not a certification of material coverage, triangle budget, mobile quality,
realistic anatomy, sealed wound caps, or any game-engine runtime.

## Validation and consumer boundary

Upstream gates check exact face ownership, shared native skeleton, original corner
attributes and materials, normalized skin influences, inverse binds, rest surface,
compound deformation, independent regional visibility, socket transforms, and
rollback without publishing invalid artifacts. Machine-readable evidence states
the actual tolerance and sampling scope; it is not a Godot acceptance result.

Smooth seam normals need special handling: Blender's custom-normal encoding changes
with each region's loop fan. The exporter transports the original source corner
normals through a temporary float-vector attribute, restores those exact values in
the GLB's `NORMAL` accessor, then removes the transport attribute. Raw GLB normals
are checked separately from Blender's reimported normal representation; the UV
budget is not increased to hide normal quantization.

Stytch/Godot should independently gate import of region IDs, shared skin/joints,
runtime deformation, hiding each limb, and bone-local socket/equipment visibility.
Do not repartition, reconstruct seams, repair weights, guess attachments, or replace
the native eighteen-joint rig with a twenty-joint reference rig in the consumer.
The consumer owns its adapter and gameplay policy, not Meshvenn geometry authority.
