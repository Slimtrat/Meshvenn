# Multiview diagnostics

The first delivery of [#77](https://github.com/Slimtrat/Meshvenn/issues/77) checks
reference preparation before asking a generator to change an object's design.
The common APIs run locally without Blender, credentials or a paid service.
The existing Blender INPUT implementation can explicitly consume an accepted
alignment while sharing its original pixels, mask and provenance with geometry
and material projection.

- [Versioned contracts](diagnostic-contracts.md): immutable source revisions,
  observations, uncertainty, evidence, required checks and stale-report rejection.
- [Image preparation and alignment](diagnostics-preflight.md): corrupt/unsupported
  inputs, alpha/masks, truncation, coverage, camera assumptions and bounded
  same-camera registration against an independent reference.
- [Offline qualification](diagnostic-corpus.md): a frozen analytic corpus,
  calibration/heldout separation, real reports and overlays, order/resolution
  controls and measured outcomes.

From the repository root:

```sh
python scripts/qualify_diagnostics.py --output tmp/diagnostic-qualification
```

Open `qualification.json` for the measured D1/D2 outcome and each case's
`diagnostic-report.json` and overlays for its evidence. A qualification failure
exits nonzero and retains the failure reports. Unknown downstream checks remain
unknown even when the tested preparation controls pass.

Preparation reports do not certify 3D reconstruction, hidden surfaces, appearance
or animation. Geometry conflict attribution, identity analysis, correction plans,
resumable generation and verified accessible GLB delivery remain the subsequent
issues in the roadmap. The initial corpus contains mathematical synthetic truth;
it does not substitute for human-reviewed generated images or real-provider and
end-to-end product acceptance. The complete qualification issue #84 stays open.

The Stytch character's deformation/stabilization acceptance and production-art
licensing are separate. No Stytch artwork or Chamber prop is used in this corpus.
