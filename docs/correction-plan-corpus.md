# Frozen correction planning corpus

`correction-plan-v1` freezes 18 independent D5/#82 expectations before evaluating
the correction planner. It checks the decisions and immutable preparation
packages, without executing a provider or qualifying semantic identity.

The frozen manifest SHA-256 is
`c6e20ec65dcfcd00471edc4483db54ce8fcb42e6adce9fe7159baf18658b4567`.
`scripts.correction_plan_corpus.integrity.load_manifest` rejects changed labels,
assets, parent manifests or original authoring definitions. Code fingerprints
for the authoring recipe explicitly normalize LF to keep regeneration portable.

The sources comprise original 64-pixel asymmetric D2 masks/rasters and unchanged
32-pixel sources from the separately frozen `appearance-v1` corpus. D3 controls
use the original `geometry-v1` ambiguity and canonical cases with a real native
library supplied explicitly by the caller. Missing native support leaves those
controls unqualified; no fake backend may supply their quality evidence.

Cases cover a supported local edit with bounded region, accepted references and
explicit D2/D3/D4 postconditions; intentional asymmetry; framing and mask repair;
a useful missing view; a real bounded native-loader failure; unresolved versus
canonical-supported geometry; unsupported masks, multiple references and camera
constraints; stale source, capabilities, report and policy; preservation of
user-origin content; and absent or low-support semantic evidence.

The `user` source is an explicitly declared analytic stand-in for a provenance
contract, not a real photograph. Capability profiles and the low-confidence
semantic port are contract specimens, not measured provider capabilities or
model fidelity. Canonical acceptance is original mathematical author intent;
human review is never invented. The invalid native-library bytes are original
test data and exercise the actual isolated loader failure path.

Every case retains original-source immutability, exact dependency binding,
nonexecution and qualification limits. Unsupported constraints must be rejected
or handled by an explicit alternative, never silently removed. Empty output
cannot satisfy the positive targeted-edit, preparation, useful-view and engine
diagnosis controls. A provider package remains a proposal; D6–D8, initial D7 and
full #84 acceptance remain unknown/open.

Calibration and heldout expectations are separated. Once measured, implementation
fixes may rerun exposed cases, but labels and inputs cannot be changed to obtain
a pass. The runner will retain failed attempts, full raw reports and package
contents under `tmp`; CI will upload actual evidence without committing large
runtime outputs. Two report orders will test deterministic planning. No image,
provider or network call is part of this qualification.

## Offline execution

With Python 3.11 or later, verify authored data and run the actual matrix:

```console
python scripts/qualify_correction_plans.py --verify-only
python -m unittest discover -s tests -p test_correction_plan_corpus.py -v
python scripts/qualify_correction_plans.py --native-library /absolute/path/to/bpt_core.dll --output tmp/correction-plan-qualification
```

The explicit native path can identify the platform's `.dll` or `.so` build.
`--python-executable` controls the trusted isolated native worker interpreter;
neither path becomes a provider prompt argument. A missing library leaves D3
cases unqualified and returns a nonzero status. `--case` selects an explicitly
partial matrix. The loader-failure case always uses the original invalid binary
probe to measure a real bounded worker/loader error, not fake geometry.

Each case executes its actual upstream diagnostics once. Both report-order
invocations use that exact immutable measured snapshot; no upstream quality
result is fabricated. The two orders also reverse input-order provenance,
which is excluded from semantic D1 dependencies. All plan/package content,
original-region bounds and context fingerprints are checked for stability.

Target-space edit annotations come from the independent original authored ROI
and inline support mask. D4 measures that original target ROI explicitly in
addition to the unchanged parent's canonical ROI. Bounds are never copied or
expanded from a residual to make an annotation pass. The source mask is explicit
author intent, not proof of physical segmentation. Multiple accepted references
use a distinct original 45-degree design view, not a duplicate or a target-derived
reference.

For every prepared request the runner tests strict JSON roundtrips and verifies
exact source, report-content, policy and capability bindings. Staleness probes
change one valid dependency after preparing a valid baseline: source revision
and content, capability version, report finding text, or minimum-region policy.
Rejection must occur in `prepare_correction`; fixture construction errors do not
count. Original encoded hashes and decoded buffers are compared before/after.

`qualification.json` records every assertion, raw numerical region/location
evidence, capabilities, policies, actual source/native/Python hashes and timings.
Each new run receives a fresh subdirectory; earlier failures remain intact.
Actual D2/D3/D4 reports, strict upstream results, original PNGs, actual D4 overlays,
full correction plans and prepared packages remain under `tmp`. Runtime outputs
are not committed. The complementary Linux/Python 3.11 and Windows/Python 3.13
workflow builds the real unchanged native core and uploads evidence on failure.

A prepared package has unknown verification status, immutable originals and
derived candidate lineage. It does not include an executed edit, a provider
compliance result, accepted identity or delivered GLB certification. Local
semantic mocks only test insufficient-evidence handling. This corpus establishes
bounded orchestration and preparation contracts, not general model quality.
