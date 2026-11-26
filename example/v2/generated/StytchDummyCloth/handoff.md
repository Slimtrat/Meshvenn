# Stytch handoff: immutable visual candidate

- Asset ID: `stytch-dummy-cloth-v1`.
- File: `character.glb`, 8,455,284 bytes.
- SHA-256: `c5d79f03057fe84264a1fa9231bc31e71f42c971324ae0a08009c339b760b65d`.
- Repository-declared licence: GPL-3.0-or-later for this new project asset, using Meshvenn's existing `LICENSE`. This is not an automatic output licence inherited from the generator. No separate human asset-specific grant or Stytch GPL-family exception is recorded. Input sheets and the local `.blend` are not covered by a newly asserted blanket grant here. Stytch's owner review remains pending. Generated image inputs and dataset hashes are linked by `provenance.json`.
- Engine/rig pass: #101, merged as `8eba14a4a3857acb4b4c929c91e8304e38119ad9`. Cloth extension: `meshvenn_cloth` 0.1.0.
- One mesh, one skin, eighteen named native joints, 39,804 triangles, no animations. Three embedded 2048² PNGs: base color, tangent normal, packed metallic/roughness. glTF export uses its standard Y-up frame; consumers must apply their normalization explicitly.
- The exact GLB passes the static native humanoid shoulder/elbow profile, selecting its baseline byte for byte, with no regeneration. The generated source's global artistic quality and consumer acceptance are not certified.

## Consumer boundary

This is a **preview/qualification candidate**, not an admitted modular Stytch skin. It has no `modular-character-v1` five-region partition, no eight socket contract and no #100 collision proxies. It also exceeds Stytch's declared 18,000-triangle budget. Do not derive these contracts by splitting the file, use all positive skin influences as ownership, substitute old pose matrices, change weights/rigs in the consumer or relax its import guards.

Keep the existing 0.1.182/0.1.200/0.1.206 library entries immutable. A source-authored modular delivery with sockets, a qualified source LOD and replay of consumer poses/contact is the next producer task. Masses, joints, collision solver and gameplay decisions remain consumer-owned. A subsequent producer delivery must have a new asset identity and SHA; this file is not a mutable `latest` alias.
