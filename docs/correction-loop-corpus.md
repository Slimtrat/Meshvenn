# Frozen correction loop corpus

`correction-loop-v1` freezes 18 D6/#83 expectations before any loop-machine
evaluation. It qualifies finite orchestration, persistence and rollback
contracts using local simulated providers/evaluators. Simulated promotion does
not qualify a real provider, semantic model, physical geometry or delivered GLB.

The frozen manifest SHA-256 is
`31992c7a2cce346569ba72308d09247a588189e41d30c55dc7d9a4a7c823fb50`.

The original assets are a 32-pixel asymmetric analytic image, an accepted
reference, independently authored candidates, source metadata and two original
single-triangle GLBs. The user photograph is an explicit analytic provenance
stand-in, not a real photograph. Canonical authority is mathematical author
intent; no human approval is invented. Inputs from frozen D4 and D5 corpora stay
unchanged. No external artwork, provider SDK, network or paid call is used.

Positive controls require promotion only after full reevaluation. Negative
controls cover a higher mean with a missing named part, identity failure,
required unknown, exact photo/source/GLB rollback, attempts/time/cost/stagnation
budgets, provider errors, late replies, cancellation, pending-crash recovery,
provider unavailability, provisional-mesh authority, receipt audit and evaluator
failure after a provider receipt. A logical test clock checks deadline policy;
logical time is never reported as measured wall-clock performance.

One separate scenario executes real D2 and D4 on the original frozen local
colour defect and an authored corrected candidate. Its visible numerical
comparison improves, while identity remains required and unknown. The candidate
must therefore remain unpromoted. This provides actual diagnostic integration
evidence without pretending that a mock certifies identity or asset acceptance.

The manifest and asset hashes are immutable. Calibration and heldout scenarios
are separate; later fixes retain exposed failures as regression history rather
than relabeling them. Runtime journals, receipts, raw evaluations and candidates
will stay under `tmp` and CI artifacts; no large generated runtime output is
committed. Initial D7 and full #84 remain open.

## Run offline

Use Python 3.11 or later. The repository's `lib` folder supplies the standalone
engine when testing a checkout; no provider SDK, paid credential, renderer or
native DLL is needed:

```console
python scripts/qualify_correction_loops.py --verify-only
python scripts/qualify_correction_loops.py --output tmp/correction-loop-qualification
```

For unit tests, add `lib` to `PYTHONPATH` and run:

```console
python -m unittest discover -s tests -p 'test_*loop*.py' -v
```

The matrix has 18 scenarios. `--case` selects an explicitly partial run.
The clock is a deterministic host test clock starting at zero, never reset on
restart. Logical deadline advances test policy; wall-clock elapsed time is
recorded separately. Simulated USD quotes/usage test accounting, not real fees.

Each run gets a fresh directory under `runs/`; no earlier journal or failed
qualification is overwritten. `qualification.json` records assertions, actual
state-derived promotion/rejection facts, source/Python hashes and wall timings.
Individual directories retain start payloads, final states, actual immutable
LoopStore history, receipts, observed port calls and full evaluations. The real
D2/D4 scenario also retains the strict appearance result and numerical region
counts. Runtime outputs are kept under `tmp` and uploaded by CI, not committed.

The test ports are injected through the trusted host constructor. They return
the real SDK-free DTOs from `meshvenn_engine.core.correction_loop`; they never
configure a callback through serialized model arguments. Provider metadata,
model, parameters, actual declared usage and exact request fingerprints survive
in the real journal. A returned receipt must be durably retained for every
completed dispatch to count as exercising its scenario. A different technical
failure before receipt handling cannot pass a cost or service control.

Crash recovery deliberately raises an uncaught local `BaseException` after
dispatch reservation, creates a fresh runtime/store object, reads the actual
disk journal and resumes it. This tests the orchestration boundary; separate
LoopStore tests cover OS-process locks and durability. The uncertain request
must not be submitted again, and unknown usage must remain unknown. No claim
of exactly-once external paid execution is made.

The invariant checks hash the original photo stand-in, original source and GLB
both in the fixtures and through the actual artifact store. Rejected candidates
stay separate and the accepted snapshot retains its exact original hash.
Positive conditional promotion requires a globally evaluated candidate, all
required checks, preserved outside pixels, camera and lineage, and measurable
improvement. A higher average never overrides a named failed part or required
unknown/identity check. Canonical references are compared across stored states,
provider requests and evaluator results; provisional candidate meshes cannot
become authority merely because they were reconstructed or generated.

The Linux/Python 3.11 and Windows/Python 3.13 workflow replays the actual runtime
and store and uploads evidence even on failure. Windows long-path storage is
tested by the store suite; descriptive case names do not determine transaction
path depth. Neither simulated success nor a prepared D5 request certifies a real
provider, actual semantic fidelity, hidden geometry, exported production quality
or D7/#84 acceptance.
