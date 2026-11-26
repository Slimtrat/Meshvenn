# Generated dummy with a portable cloth finish

`character.glb` is the generated eight-view mannequin with the qualified local arm skin, a 2048² projected base-color atlas, a tangent-space woven normal map and a packed metallic/roughness map. All images are embedded; the asset uses standard glTF PBR. The eighteen-joint rig is retained. It does not contain the modular partitions/sockets required for automatic Stytch admission.

The source sheets, prompts and calibrated-convention assumptions remain in `../StytchDummy8Views/inputs/`. They are generated images, not known 3D ground truth. `provenance.json` pins this asset, the input dataset, the original defective rig fixture, the qualified skin input, the material recipe and the exported transport checks. The comparison uses actual GLB reloads with the same lights/cameras.

The recipe retains front/back authority for dark head markings and excludes contradictory dark details from side/diagonal appearance views while retaining their cloth observations. Excluded pixels stay excluded from source coverage. Woven relief and variable roughness are authored surface details, not recovered observations. The normal bake modifies no vertices, UVs, native rest frames or weights. Overall artistic quality and Stytch consumer acceptance are not inferred from export success.

Reproduce from the preserved native-frame `.blend` with the qualified skin:

```sh
blender --background --factory-startup --python-exit-code 1 --python scripts/benchmark_stylized_dummy_quality.py -- --source-blend SOURCE.blend --source-sha256 SHA256 --dataset example/v2/generated/StytchDummy8Views/inputs/dataset-native-frame.json --output output/cloth-replay --cardinal-priority --variants detail --texture-size 2048 --coherent-head --cloth
```

The independent `Meshvenn Cloth` extension can also finish an existing UV-mapped material or add **Cloth UV Bake** to the engine's MATERIAL stage. The base-color bake resolution and the detail-map resolution are separate settings. Neither creates source-image detail that does not exist.
