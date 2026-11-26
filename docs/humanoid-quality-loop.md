# Automatic humanoid deformation loop

The optional **Meshvenn Humanoid Quality** extension decorates the existing `canonical-biped-v2` rig implementation. After a new rig is fitted, it snapshots its mesh and armature into a separate worker, measures exported/reimported GLBs and regenerates arm weights until the frozen profile passes or the budget stops the run. The engine contains no imports or quality-loop policy from this extension. The same independent package exposes a CLI and a trusted host-port interface for agents and other consumers.

## Recognition and measurements

This profile recognizes a static native eighteen-joint hierarchy with bilateral weighted head/limb support. It requires one mesh and one armature, no animation, constraints or shape keys, and a rest-pose residual within `2e-5`. Recognition is structural; arbitrary humanoid recognition is not claimed. Oversized sources and unsupported native frames require attention rather than an inferred correction.

Both elbows are tested at 45° and 90°, both shoulders at 45° and 70°, using linear blend skinning on the reimported GLB. Regions are frozen from the baseline before any regeneration. The rigid-link regions exclude a collar sized from the source's measured thickness in the tested flexion plane. The profile checks proximal/distal link motion, protected torso/head/leg/opposite-limb motion, retained collar radius, retained triangle area and inverted area at the elbow. Narrow blending can improve rigidity while folding the interior surface; that candidate must fail.

Source positions, oriented triangles, UVs and native rest frames are preserved. Coincident glTF seam splits can change the vertex count without changing the surface, so correspondence validates rest positions, oriented face multiplicity and consistent skin at coincident seams. Texture bytes and material descriptors must remain identical. Surface/topology observations and saved appearance diagnostics are also recorded automatically; observations do not certify morphology, texture identity, watertightness or artistic quality.

Thresholds live in `meshvenn_humanoid.models.LIMITS`, not in the generator. They are fingerprinted before the first attempt, alongside the measurement policy, regeneration policy and budgets. No candidate can pass through a missing, nonfinite or unknown measurement.

## Targeted regeneration

The local recipe projects each point onto its existing upper-arm/forearm/hand chain and uses bounded, normalized, four-influence weights. It removes distant child influence from the proximal arm while retaining axial attachment mass at the torso. Two narrow transitions are evaluated first; a thickness-adapted transition is tried when necessary. An elbow collar that overlaps adjacent joints cannot be repaired by widening it further. Blender bone heat is a final independent recipe; a solver failure is recorded as a failure.

Every recipe starts from the immutable source, not the previous candidate. The controller retains the best preserved candidate but selects it only when every profile check passes. It never changes the thresholds to accommodate a result. Unresolved or unknown results stop the pipeline and retain their reports. More severe geometry/topology defects require a separate measured regeneration policy; this arm-skinning profile does not invent a mesh repair.

The worker's `session.json` records detection, the baseline, each recipe and its measurements, immutable asset hashes, elapsed time, failures and the final selection. An OS lock prevents simultaneous writers. Default limits are four attempts, 180 seconds and two consecutive attempts without improvement. The extension uses a shorter configurable time budget. Cancellation, stale source hashes, policy changes, tampering and failed preservation checks prevent promotion. Resume preserves elapsed time; it does not reset the budget. No source file is replaced. A passing GLB is retained byte for byte on subsequent runs. Object snapshots pack disposable copies of generated/edited texture buffers and resolve external paths, then restore the live material nodes; unsaved bake pixels must survive the worker transfer without changing the active images.

## Installation and use

See the independent [package README](../packages/meshvenn_humanoid/README.md) and [extension instructions](../extensions/meshvenn_humanoid_auto/README.md). The extension transfers passing weights transactionally to the same scene objects, preserving the active scene and file. Disable it to restore the original pipeline. Host code can instead supply `HumanoidLoop` with its own detection/regeneration/evaluation/verification port. Executable paths, code and providers are trusted host configuration.

The [generated eight-view fixture](../example/v2/generated/StytchDummy8Views/README.md) pins an intentionally defective GLB, the ImageGen inputs and their provenance. CI builds the standalone wheel and installable ZIP, checks the controller on Linux and Windows, performs real Blender regeneration, rejects the inverted collar recipes, verifies the passing result is unchanged on a second run, skips Avocado and exercises automatic extension integration before downstream export. It publishes actual GLB pose renders and reports as artifacts.

Passing this profile means the listed deformation and transport checks passed. Overall character quality and Stytch consumer acceptance remain explicitly unknown. The verified flexion range ends at 90°; harder folds, twist, animation, contact and authored module contracts need their own evidence.
