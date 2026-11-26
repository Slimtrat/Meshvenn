# Generated eight-view dummy: defective rig regression fixture

`rig-baseline.glb` deliberately retains the old inverse-distance skinning. Bending an elbow to 90° pulls the proximal arm and deforms the hand. It is the negative input to the automatic humanoid quality loop, not the delivered corrected asset.

`provenance.json` pins its bytes, engine revision, reconstruction settings and generated inputs. `inputs/` contains both original ImageGen sheets, their prompts, fixed crops and the registered eight-view dataset. Diagonal registration uses the documented native camera convention; the requested image cameras are not physically calibrated. There is no known 3D ground truth or Stytch consumer acceptance.

Run `meshvenn-humanoid --blender /trusted/blender --engine-root /trusted/Meshvenn --source example/v2/generated/StytchDummy8Views/rig-baseline.glb --output output/dummy-quality-loop`. A passing run writes `selected.glb`, editable candidate sources and the complete report. `scripts/render_humanoid_quality.py` renders the actual baseline and selected GLBs at identical elbow angles and cameras. No render-only deformation is used.

The CI verifies the source hashes, detects the defective baseline, rejects the narrow collar recipes when they invert faces, selects the thickness-adapted correction and then proves that a second run preserves the passing GLB byte for byte. Surface/texture observations do not establish aesthetic or anatomical certification.
