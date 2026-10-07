"""Rest-relative evidence derivation is not unchanged-rest consumer replay."""
import copy
import json
from pathlib import Path
import unittest

from core.native_pose_capture import error, multiply
from core.native_pose_probe import NativePoseProbe
from scripts.shoulder_pose_derivation import derive_pose, inverse

ROOT = Path(__file__).resolve().parents[1]


class ShoulderPoseDerivationTests(unittest.TestCase):
    def setUp(self):
        self.pose = NativePoseProbe.from_dict(json.loads((ROOT / "example/v2/poses/StytchDoll/factory-hall-pose.json").read_text("utf-8")))
        self.rests = {b.name:b.rest for b in self.pose.bones}

    def test_unchanged_rest_identity_and_target_fingerprint(self):
        derived = derive_pose(self.pose,self.rests,"a"*64)
        self.assertEqual(derived.asset_sha256,"a"*64)
        for old,new in zip(self.pose.bones,derived.bones):
            self.assertLess(error(old.pose,new.pose),1e-11)

    def test_changed_rest_preserves_noncommuting_local_delta_not_old_pose(self):
        rests = copy.deepcopy(self.rests)
        old = next(b for b in self.pose.bones if b.name == "upper_arm.L")
        shift = ((0.,-1.,0.,2.),(1.,0.,0.,3.),(0.,0.,1.,-4.),(0.,0.,0.,1.))
        rests[old.name] = multiply(shift,old.rest)
        derived = derive_pose(self.pose,rests,"b"*64)
        new = next(b for b in derived.bones if b.name == old.name)
        self.assertGreater(error(old.pose,new.pose),1.)
        self.assertLess(error(multiply(inverse(old.rest),old.pose),multiply(inverse(new.rest),new.pose)),1e-10)
        self.assertEqual(self.pose.asset_sha256,"76590fd9c335335255f2eb2a4fc0866adf3c5a6a6fad0d4938c9e7550b7dcb57")

    def test_missing_singular_nonfinite_and_nonaffine_rests_fail_closed(self):
        with self.assertRaises(ValueError):
            derive_pose(self.pose,{},"a"*64)
        for row in (((0.,0.,0.,0.),)*3+((0.,0.,0.,1.),),
                    ((float("nan"),0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.)),
                    ((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,1.,1.))):
            rests = dict(self.rests)
            rests["upper_arm.L"] = row
            with self.assertRaises(ValueError):
                derive_pose(self.pose,rests,"a"*64)


if __name__ == "__main__":
    unittest.main()
