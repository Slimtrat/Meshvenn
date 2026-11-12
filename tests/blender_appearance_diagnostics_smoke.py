"""Exercise D4 from an extracted extension without modifying the Blender scene."""
from __future__ import annotations

import argparse
import importlib
from pathlib import Path
import sys

import bpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root",type=Path,required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    package_root = args.package_root.resolve()
    sys.path.insert(0,str(package_root.parent))
    package = importlib.import_module(package_root.name)
    assert Path(package.__file__).resolve().parent == package_root
    contracts = importlib.import_module(package.__name__+".core.diagnostic_contracts")
    rasters = importlib.import_module(package.__name__+".core.diagnostics_preflight")
    appearance = importlib.import_module(package.__name__+".core.appearance_diagnostics")
    package.register()
    try:
        before = tuple(bpy.context.scene.objects)
        size = 32
        def raster(changed):
            pixels = tuple(c for y in range(size) for x in range(size) for c in (
                ((.8,.1,.2,1.) if changed and 12<=x<20 and 12<=y<20 else (.2,.5,.4,1.))
                if 4<=x<28 and 4<=y<28 else (0.,0.,0.,0.)))
            return rasters.RasterInput.from_pixels(size,size,pixels)
        inputs = {name:rasters.ViewInput(raster(name=="target")) for name in ("target","reference")}
        proof = contracts.ArtifactReference("analytic-paint-proof","a"*64,"application/json")
        views = tuple(contracts.ViewRevision(name,1,data.image.content_reference(),None,
            contracts.CameraDeclaration("orthographic",0.,0.,False,True,proof),
            role="observation" if name=="target" else "reference") for name,data in inputs.items())
        revision = contracts.ViewSetRevision("packaged-d4-analytic",1,views,
            contracts.CanonicalReference("accepted",1,views[1].image,True,("reference",),proof))
        surface = appearance.SurfaceMesh(((-.8,0.,-.8),(.8,0.,-.8),(.8,0.,.8),(-.8,0.,.8)),
                                         ((0,1,2),(0,2,3)),proof)
        result = appearance.analyze_appearance(revision,inputs,surface=surface,
            view_settings={name:appearance.AppearanceViewSettings("scene-linear","albedo",1.,True,proof) for name in inputs})
        assert result.report.verification_status == "fail",result.report.to_json()
        assert result.identity_status == "unknown"
        assert appearance.AppearanceResult.from_json(result.to_json()) == result
        assert tuple(bpy.context.scene.objects) == before
        print("PACKAGED_APPEARANCE_DIAGNOSTICS_PASS: visible paint defect, unknown identity, strict replay, no scene mutation")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
