"""Preparation tasks identify the actual immutable input requiring repair."""
from dataclasses import replace
import unittest

from core.correction_plans import plan_corrections,prepare_correction
from core.diagnostics_preflight import RasterInput,ViewInput,PreflightPolicy,analyze_preflight
from tests.test_appearance_engine import fixture


class PreparationTargetTests(unittest.TestCase):
    def test_actual_cropped_source_has_an_explicit_preparation_target(self):
        revision,inputs,_=fixture()
        image=inputs["target"].image
        pixels=tuple(c for y in range(image.height) for x in range(image.width) for c in (
            image.rgba[(y*image.width+x+4)*4:(y*image.width+x+4)*4+4] if x+4<image.width else (0.,0.,0.,0.)))
        cropped=RasterInput.from_pixels(image.width,image.height,pixels)
        revision=replace(revision,revision=2,views=tuple(replace(v,image=cropped.content_reference()) if v.view_id=="target" else v for v in revision.views))
        reports=(analyze_preflight(revision,{**inputs,"target":ViewInput(cropped)},
            policy=PreflightPolicy(required_cameras=((0.,0.),))).report,)
        result=plan_corrections(revision,reports)
        task=next(p for p in result.plans if p.action_kind=="prepare_alignment")
        self.assertEqual("target",task.target.view_id)
        self.assertIsNone(task.target.bounds)  # No invented cut-off feature rectangle.
        self.assertEqual(cropped.source_sha256,task.prompt.original.image.sha256)
        self.assertEqual("needs_input",task.readiness)
        self.assertFalse(any(p.action_kind=="edit_region" for p in result.plans))
        with self.assertRaises(ValueError):
            prepare_correction(task,revision,reports)


if __name__=="__main__":
    unittest.main()
