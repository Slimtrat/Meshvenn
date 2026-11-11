# Meshvenn Sketch

The [Stytch Workshop Modules V1](https://github.com/Slimtrat/Meshvenn/tree/main/example/v2/modules/StytchWorkshopV1)
delivery contains ten editable equipment, replacement and accessory designs,
plus a separate Godot adapter tested on the public native doll.

An independent Blender 5.2+ extension for drawing a closed outline on a reference
image, making a rounded 3D accessory, and editing skin weights with Blender's
native brushes. It works with an ordinary mesh and image, with or without the
Meshvenn engine installed.

## Install

Install **meshvenn_sketch-0.1.0.zip** through Blender's **Preferences → Get
Extensions → Install from Disk**, then enable **Meshvenn Sketch**. Its sidebar
tab appears in both the 3D View and the Image Editor. This ZIP is separate from
the Meshvenn reconstruction extension.

Build it from this checkout with Python 3.11+:

```sh
python scripts/build_meshvenn_sketch.py
blender --command extension validate dist/meshvenn_sketch-0.1.0.zip
```

## Draw an accessory

1. Work in the character's **rest pose** and in Object mode. In the **Meshvenn
   Sketch** sidebar, choose the original **Character / Source Mesh**.
2. With Meshvenn installed, select the desired engine reference view, then click
   **Use Active Meshvenn Projection**. This copies the public projection frame,
   image and alignment into the extension's own draft. No engine data changes.
   Alternatively, load an ordinary reference, choose azimuth/elevation and
   **Calibrate Image to Source Bounds**. In manual calibration, the image must
   frame the source's complete local bounding box, without extra margins. Zero
   azimuth looks along the local Y axis; zero elevation is a horizontal view.
3. **Open Drawing View** puts an Image Editor beside the 3D View. In its
   **Meshvenn Sketch** sidebar, click **Draw Piece Outline**, then click corners
   or drag a closed outline over the image. **Enter** accepts; **Esc** cancels; **R** redraws;
   **Backspace** removes a point. Reference pixels stay intact. Draw one simple
   contour per piece; crossing outlines and holes are refused. You can zoom and
   pan between strokes, then redraw the contour at the new scale.
4. Give the piece a name and color. Set **Thickness**, **Depth Offset** and
   **Rounded Edge** as fractions of the source frame's height. A single image
   defines the silhouette; the artist supplies the missing depth. This is an
   extrusion with rounded edges, not inferred anatomy or a hidden back view.
5. Choose an existing **deform bone**, or disable **Bind to Bone** for a static
   accessory. The initial binding assigns every vertex to that bone. Depth is
   centered on the bone's rest head, then shifted by the depth offset along the
   viewing direction. Click **Create 3D Piece**, inspect in 3D and adjust depth.
6. Trace another piece from any other calibrated face as needed. Each piece
   saves its own view, outline and dimensions. Recalibrating starts a fresh draft.

The result is a separate closed mesh in the **Meshvenn Sketch** collection. It
shares the source's transform and references the existing armature. The source
geometry, source weights, rig structure, reference images and reconstruction
settings are unchanged by creation. No bones are generated or renamed.

## Edit geometry and skinning

Select a generated piece and click **Edit Selected Sketch Piece** to restore its
saved draft. Change thickness/depth/roundness, then **Apply Piece Dimensions**.
This retains vertex indices, UVs, vertex groups and painted weights. A manually
edited mesh or UV layout is deliberately protected from procedural replacement;
continue editing it with Blender or create another piece instead. Shared mesh
data and shape keys also prevent procedural dimension updates.

**Paint Piece Weights** selects the piece and chosen deform-bone group and enters
Blender Weight Paint mode. Use native brushes and normalize weights before
exporting (maximum four deform-bone influences per vertex). Return to Object
mode to update dimensions or export. Blender's regular undo applies to contour,
creation, dimensions and weight painting. Save a `.blend` to keep recipes,
reference pointers and editable weights.

**Paint Source Weights** explicitly switches the paint target to the original
character mesh. Painting now changes that mesh's weights. Derived Meshvenn
previews associated with that source are hidden so that the source is visible;
rebuild those previews using their owning workflow after editing the source.
Painting the source does not publish a new Meshvenn character bundle.

## Export

**Export Piece GLB** writes only the generated accessory and its complete
existing bone hierarchy, with skin weights and no animation clips or character
body. Non-armature modifiers such as rounded edges are applied for export;
the editable `.blend` stays intact. Posed rigs export from their rest binding,
and the current pose and selection are restored. Existing files require the
explicit **Replace Existing File** option.

This standard GLB is an authoring asset. It does not add sockets, ownership
regions, module IDs or runtime behavior to Meshvenn/Stytch's modular-character
contract. A consumer can attach or integrate the accessory using its own asset
pipeline. Complete character rebundling remains a separate operation.

## Architecture and verification

Runtime modules live entirely in this directory and import no engine code.
The optional bridge only reads public Blender RNA and the documented
`surface-envelope-v1` mesh metadata. Native reconstruction, core registration,
core operators and core UI do not depend on Sketch. Disabling Sketch removes
its UI/tools while leaving authored meshes, materials and recipes in the file.

The dedicated **Meshvenn Sketch Extension** CI builds and validates its ZIP,
runs projection/triangulation/manifold/boundary tests, and loads the extracted
package in factory-startup Blender without the engine. It exercises rollback,
bone response, painted-weight preservation, GLB export/reimport and `.blend`
reload. CI artifacts contain the installable ZIP and the generated test scene.
