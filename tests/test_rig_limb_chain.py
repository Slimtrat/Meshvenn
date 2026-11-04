"""Authored distal-chain projection, exact protected skin and refusal semantics."""
import copy
from dataclasses import replace
import math
import random
import unittest

from core.rig_limb_chain import CHAINS, refine_distal_limb_weights
from core.rig_owned_skin import _surface_distances
from tests.test_rig_owned_skin import authored_surface


def fixture():
    pts,faces,roles,_,bones,_ = authored_surface()
    keys,members,distances,_ = _surface_distances(pts,faces,roles,1.)
    rows = []
    for key in keys:
        if "body-core" in members[key]: rows.append({"pelvis":1.})
        else:
            role = next(iter(members[key])); a,b,_ = CHAINS[role]
            foreign = "chest" if "arm" in role else "pelvis"
            rows.append({a:.75,b:.24,foreign:.01})
    return pts,faces,roles,rows,bones,keys,members,distances


class DistalChainTests(unittest.TestCase):
    def test_existing_chain_ratios_are_preserved_and_foreign_mass_fades_out(self):
        pts,faces,roles,rows,bones,keys,members,ds = fixture()
        original = copy.deepcopy((pts,faces,roles,rows,bones))
        result,report = refine_distal_limb_weights(pts,faces,roles,rows,bones)
        self.assertEqual((pts,faces,roles,rows,bones),original)
        self.assertGreater(report["changed_vertex_count"],0)
        for key,old,new in zip(keys,rows,result):
            if "body-core" in members[key]: self.assertEqual(new,old); continue
            role = next(iter(members[key])); chain = CHAINS[role]
            self.assertAlmostEqual(new[chain[0]]/new[chain[1]],old[chain[0]]/old[chain[1]])
            self.assertAlmostEqual(sum(new.values()),1.)
            self.assertLessEqual(sum(v>0 for v in new.values()),4)
            if ds[role][key] <= .06: self.assertEqual(new,old)
            if ds[role][key] >= .12: self.assertLessEqual(set(new),set(chain))

    def test_already_chain_only_rows_are_not_renormalized_even_with_float_roundoff(self):
        pts,faces,roles,rows,bones,keys,members,ds = fixture()
        selected = next(i for i,k in enumerate(keys) if members[k]=={"left-leg"} and ds['left-leg'][k]>.18)
        rows[selected] = {"thigh.L":.699999988079071,"shin.L":.30000001192092896,"root":0.}
        result,_ = refine_distal_limb_weights(pts,faces,roles,rows,bones)
        self.assertEqual(result[selected],rows[selected])
        self.assertEqual(list(result[selected]),list(rows[selected]))

    def test_face_order_uv_seams_scale_and_translation_are_invariant(self):
        pts,faces,roles,rows,bones,*_ = fixture()
        expected,_ = refine_distal_limb_weights(pts,faces,roles,rows,bones)
        order=list(range(len(faces)));random.Random(57).shuffle(order)
        actual,_=refine_distal_limb_weights(pts,[faces[i] for i in order],[roles[i] for i in order],rows,bones)
        self.assertEqual(actual,expected)
        split=[pts[i] for f in faces for i in f]; split_rows=[rows[i] for f in faces for i in f]
        split_faces=[tuple(range(4*i,4*i+4)) for i in range(len(faces))]
        actual,_=refine_distal_limb_weights(split,split_faces,roles,split_rows,bones)
        self.assertEqual(actual,[expected[i] for f in faces for i in f])
        for scale in (.01,400.):
            moved=lambda p: tuple(o+scale*v for o,v in zip((3,-2,5),p))
            new_bones=[replace(b,head=moved(b.head),tail=moved(b.tail)) for b in bones]
            actual,_=refine_distal_limb_weights([moved(p) for p in pts],faces,roles,rows,new_bones)
            for a,b in zip(actual,expected):
                self.assertEqual(set(a),set(b))
                for n in a: self.assertAlmostEqual(a[n],b[n],places=9)

    def test_missing_existing_chain_invalid_input_and_noop_are_rejected(self):
        pts,faces,roles,rows,bones,keys,members,ds=fixture()
        selected=next(i for i,k in enumerate(keys) if members[k]=={'left-leg'} and ds['left-leg'][k]>.18)
        for replacement in ({'pelvis':1.},{'pelvis':math.nan},{'root':1.}):
            bad=copy.deepcopy(rows);bad[selected]=replacement
            with self.assertRaises(ValueError): refine_distal_limb_weights(pts,faces,roles,bad,bones)
        pure=[dict(r) if 'body-core' in members[k] else {CHAINS[next(iter(members[k]))][0]:1.} for k,r in zip(keys,rows)]
        with self.assertRaisesRegex(ValueError,'No positive'): refine_distal_limb_weights(pts,faces,roles,pure,bones)
        with self.assertRaises(ValueError): refine_distal_limb_weights(pts,faces,roles,rows,bones,collar_in_heights=True)
        with self.assertRaises(ValueError): refine_distal_limb_weights(pts,faces,['body-core']*len(roles),rows,bones)


if __name__=='__main__': unittest.main()
