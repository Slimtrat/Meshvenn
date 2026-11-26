"""Fixed GLB capture profiles; held-out evaluation angles stay separate."""
LEGACY_CAMERAS = tuple((f"az{a:03d}", a, 0.) for a in range(0, 360, 45)) + (
    ("top", 0., -90.), ("bottom", 0., 90.))
ADDITIONAL_CAMERAS = tuple((f"az{int(a):03d}_5", a, 0.) for a in (22.5+45*k for k in range(8)))
DENSE_CAMERAS = LEGACY_CAMERAS + ADDITIONAL_CAMERAS
DENSE_PROFILE = "native-cube-18-input-v1"
