# Geometry diagnostic numerical measurements

`core.geometry_diagnostics.projection` and `metrics` are pure Python measurement
modules. They do not infer which input is wrong or certify unseen surfaces.

## Projection authority and finite cells

Projection reuses `CameraDeclaration.transform`, which delegates to
`core.projection_math.compile_projection`, and `project_normalized_point`.
The native centre convention is `2 * i / (size - 1) - 1`, with a singleton axis
at zero. Storage is X-fastest, then Y, then Z. These conventions come from
`native/src/visual_hull_common.cpp`, `visual_hull_projection.h`, and
`visual_hull_apply.cpp`. Mask origin is bottom left. Native nearest sampling
rejects outside UVs and uses `int(u * (width - 1) + 0.5)` for valid coordinates.
The Python authority uses double precision; the C++ engine uses float. Boundary
ties can differ at floating point precision and are not a calibration proof.

A centre represents the Voronoi cell halfway to adjacent native centres, clipped
to the normalized `[-1, 1]` cube. A singleton axis spans the complete interval.
This explicit diagnostic reconstruction convention differs from treating the
occupied centres as sparse points, and from the final mesh surface envelope.
Contiguous occupied X cells merge into cuboids without changing their union.
The eight cuboid corners project to a convex polygon. Scanline clipping marks
raster cells with positive overlap with that polygon; it does not fill an
elevated polygon's rectangular bounding box. Disconnected runs stay separate.
The result is a conservative finite-cell silhouette, not a hidden-surface test.

For an exact antipodal declaration `a2 = a1 + 180 (mod 360), e2 = -e1`,
the shared transform gives `x1_2 = -x1_1`, `y1_2 = -y1_1`, and
`sin_el_2 = -sin_el_1`. Therefore `z2_2 = z2_1`, extents agree, and
the pre-flip UV relation is `(u2, v2) = (1-u1, v1)`. Including declared Flip X,
the raster needs horizontal mirroring exactly when the two flags are equal.
This permits a direct silhouette compatibility measurement independently of
voxel resolution, with explicit raster quantization uncertainty. Merely
opposite viewing directions are insufficient: at the poles, declared azimuth
still specifies raster roll. This relation does not identify which image is true.

`projection_tolerance_pixels` measures a bound on the projected half-cell
displacement, plus half a raster diagonal. This numerical uncertainty must be
recorded by the caller. It does not permit a pass for an unresolvable component.

## Measurements and region visibility

`compare_masks` requires identical explicit raster grids, at most 256 pixels
per axis. Native reconstruction can consume larger original masks; the caller
must separately record any metric-grid resampling and preserve source-grid
component checks. These functions never resize silently.

The comparison records intersection, union-derived IoU, precision, recall,
missing and extraneous masks, and residual component boxes. Empty/empty overlap
is one. Precision is zero when actual is empty and expected is nonempty; recall
is one when expected is empty. An empty/nonempty contour distance is undefined
(`None`), rather than a misleading zero.

Contours are four-neighbour foreground boundaries. Symmetric mean and maximum
distances use exact Euclidean distances between raster boundary sample centres,
computed with a linear-time separable squared-distance transform. They are not
continuous curve distances. Residual connected components use four connectivity
and normalized boxes covering their raster cells. Raw residuals remain visible
even when they lie within the declared tolerance.

Each expected connected component and each explicitly bounded important region
has its own recall and count of missing pixels beyond tolerance. The default
region recall threshold is 0.95 and is an explicit function parameter. Regions
with insufficient foreground, extent, or no bounds remain `unknown`, even when
their coarse samples match perfectly. Below-threshold deficits wholly inside
the numerical tolerance also remain `unknown`. Component truncation and total
residual counts are explicit; callers must not treat omitted checks as passes.

Raster, volume, work, output-region, deadline and cooperative cancellation bounds
prevent unbounded rasterization or all-pairs contour work. Exceeding a bound
raises an exception; no partial image is returned as a successful measurement.

Focused validation is `python -m unittest tests.test_geometry_diagnostic_projection`.
Set `MESHVENN_TEST_NATIVE_DLL` to a read-only existing DLL to additionally compare
all voxel centres in representative cardinal, oblique, elevated, flipped and
rectangular-mask cases with the real native sampler. Independent analytic box
and polygon-square SAT cases verify finite-cell coverage; brute-force small
rasters verify the Euclidean distance transform.
