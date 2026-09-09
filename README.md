# Blender Projection Tool

Generate a 3D blockout mesh from multiple calibrated silhouette projections directly inside Blender.

Designed for character blockouts, mascots, plush characters, figurines, turntable reconstruction and local silhouette-based object scanning.

## Compatibility

- Blender 5.2+
- Primary target: Blender 5.2.1
- Local-first
- No external Python dependency required for the current V1

## Concept

Projection Tool reconstructs a 3D visual hull by intersecting silhouettes captured from several known camera angles.

Minimal setup:

```text
Front 0°
+
Side 90°
```

Better turntable scan:

```text
0°
45°
90°
135°
180°
225°
270°
315°
```

Each projection stores an image, azimuth, elevation, optional horizontal flip and enabled/disabled state.

## Pipeline

```text
Reference images
      ↓
Alpha silhouettes
      ↓
Projection calibration
      ↓
Visual Hull
      ↓
Voxel Volume
      ↓
Surface Mesh
      ↓
Blender Voxel Remesh
      ↓
Smoothing
      ↓
3D Blockout
```

## Features

- Arbitrary number of projection views
- Configurable azimuth and elevation
- 4 / 8 / 16-view turntable presets
- Transparent PNG silhouette support
- Configurable alpha threshold
- Configurable voxel resolution
- Optional X symmetry
- Automatic empty-volume cropping
- Exposed-surface-only mesh generation
- Shared vertex reuse
- Automatic height normalization
- Blender voxel remesh cleanup
- Smoothing
- Pure-Python reconstruction core
- Unit tests outside Blender
- GitHub Actions CI
- Automatic installable ZIP generation
- Automatic build versioning
- Extension version displayed in Blender UI

# Installation

Open the repository on GitHub:

```text
Actions
→ CI
→ latest successful run
→ Artifacts
```

Download the generated artifact. It contains a ZIP similar to:

```text
blender_projection_tool-0.1.42.zip
```

Do not extract the extension ZIP.

In Blender 5.2.1:

```text
Edit
→ Preferences
→ Extensions
→ Install from Disk
```

Select the ZIP and enable the extension if required.

# Open Projection Tool

```text
3D Viewport
→ N
→ Projection Tool
```

The sidebar displays the installed version:

```text
Projection Tool
v0.1.42
```

# Preparing images

For best results, every image should:

- show the same object
- use the same pose
- use the same scale
- have the object centered consistently
- use minimal perspective distortion
- have a transparent background
- preserve the same vertical ground and head references

Recommended PNG structure:

```text
RGBA

object:
alpha = 1.0

background:
alpha = 0.0
```

Projection Tool currently creates the mask from alpha:

```python
occupied = alpha >= threshold
```

Default threshold:

```text
0.10
```

# Turntable workflow

For 8 images:

```text
360° / 8 = 45°
```

Recommended naming:

```text
000.png
045.png
090.png
135.png
180.png
225.png
270.png
315.png
```

Workflow:

1. choose the 8-view preset
2. assign each image
3. verify each azimuth
4. generate at 64 or 96 voxels
5. fix alignment
6. increase to 128 only once the result is coherent

# Resolution

| Resolution | Use |
|---:|---|
| 32 | Debug |
| 64 | Fast preview |
| 96 | Default |
| 128 | Good quality |
| 192 | High quality |
| 256 | Experimental |

Examples:

```text
64³  =    262,144 voxels
128³ =  2,097,152 voxels
256³ = 16,777,216 voxels
```

# 3/4 views

3/4 images are supported by the generic projection model.

Example:

```text
Front          0°
Front-right   45°
Right         90°
Back-right   135°
Back         180°
```

They help constrain heads, shoulders, bellies, feet, backpacks, curved objects and asymmetric silhouettes.

# Elevation

Example:

```text
azimuth   = 45°
elevation = 30°
```

For a simple horizontal turntable:

```text
elevation = 0°
```

# Limitations

Visual hull reconstruction cannot recover geometry that never changes the observed silhouette.

Examples:

- deep concavities
- hidden holes
- internal cavities
- texture-based depth
- complex overlapping internal geometry

Projection Tool is multi-view silhouette reconstruction, not full photogrammetry.

# Recommended production workflow

```text
1. Capture / generate references
2. Remove backgrounds
3. Create projection entries
4. Set angles
5. Generate at 64 voxels
6. Correct alignment
7. Generate at 96 voxels
8. Add 3/4 views
9. Generate at 128 voxels
10. Voxel remesh
11. Sculpt corrections
12. Retopology
13. UV unwrap
14. Rig
15. Shape keys
16. Texturing
```

# Project structure

```text
blender_projection_tool/
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── core/
│   ├── __init__.py
│   ├── masks.py
│   ├── visual_hull.py
│   ├── mesh_builder.py
│   └── cleanup.py
│
├── tests/
│   └── test_visual_hull.py
│
├── blender_manifest.toml
├── __init__.py
├── version.py
├── properties.py
├── operators.py
├── ui.py
├── README.md
├── LICENSE
└── .gitignore
```

# Development

```bash
git clone https://github.com/Slimtrat/blender_projection_tool.git
cd blender_projection_tool
python -m unittest discover -s tests -p "test_*.py" -v
```

# CI

Pipeline:

```text
Tests
  ↓
Structure validation
  ↓
Calculate build version
  ↓
Patch packaged manifest
  ↓
Build installable ZIP
  ↓
Upload GitHub artifact
```

# Automatic versioning

The repository manifest keeps the version family, for example:

```toml
version = "0.1.0"
```

During CI packaging, the patch number is replaced by the GitHub Actions run number.

Example:

```text
repository version: 0.1.0
GitHub run number: 42
packaged version: 0.1.42
```

This means every CI ZIP gets a unique increasing version without committing version bumps back to the repository.

Example artifacts:

```text
blender_projection_tool-0.1.41.zip
blender_projection_tool-0.1.42.zip
blender_projection_tool-0.1.43.zip
```

The Blender sidebar reads the installed manifest and displays the packaged version.

# Roadmap

- Folder-based turntable importer
- Automatic angle assignment from filenames
- Drag-and-drop multi-image import
- Automatic silhouette extraction
- Luminance-based masking
- Automatic subject centering
- Projection overlay/debug view
- Voxel preview before mesh creation
- Generation progress reporting
- Faster reconstruction
- Optional NumPy acceleration
- Camera calibration
- Perspective camera support
- Automatic camera pose estimation
- Photogrammetry hybrid mode
- Automatic retopology helpers
- Automatic T-pose helpers
- Per-body-part reconstruction
- Module attachment points
- Texture projection from source images

# License

GPL-3.0-or-later.
