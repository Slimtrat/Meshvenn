"""Frozen analytic shape controls; never a universal aesthetic qualification."""
import hashlib
import json
import math
from pathlib import Path
import unittest

from scripts.character_quality.metrics import MetricPolicy, mesh_quality
from scripts.character_quality.profile import ComparisonProfile, compare_quality, REQUIRED_GATES

FIXTURE=Path(__file__).parent/'fixtures/character-quality/analytic-v1.json'
FROZEN_SHA256='3d123f31e1c83173f803b03d1ed3f2afb5fbc3329683a38538c81589bbc55a04'


def fixture():
    data=json.loads(FIXTURE.read_bytes())
    assert hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()==FROZEN_SHA256
    return data


def subdivide(vertices,triangles):
    vertices=list(map(tuple,vertices));midpoints={};result=[]
    def midpoint(a,b):
        key=tuple(sorted((a,b)))
        if key not in midpoints:
            midpoints[key]=len(vertices);vertices.append(tuple((x+y)/2 for x,y in zip(vertices[a],vertices[b])))
        return midpoints[key]
    for a,b,c in triangles:
        ab,bc,ca=midpoint(a,b),midpoint(b,c),midpoint(c,a)
        result.extend(((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)))
    return vertices,result


def ellipsoid(recipe):
    a,b,c=recipe['axes'];m,n=recipe['longitudes'],recipe['latitude_intervals']
    vertices=[(0.,0.,c)]
    for i in range(1,n):
        phi=math.pi*i/n
        vertices.extend((a*math.sin(phi)*math.cos(2*math.pi*j/m),b*math.sin(phi)*math.sin(2*math.pi*j/m),c*math.cos(phi)) for j in range(m))
    bottom=len(vertices);vertices.append((0.,0.,-c));triangles=[]
    for j in range(m):triangles.append((0,1+j,1+(j+1)%m))
    for i in range(n-2):
        first,second=1+i*m,1+(i+1)*m
        for j in range(m):
            following=(j+1)%m
            triangles.extend(((first+j,second+j,second+following),(first+j,second+following,first+following)))
    last=1+(n-2)*m
    for j in range(m):triangles.append((last+j,bottom,last+(j+1)%m))
    return vertices,triangles


def rotate(point):
    # Fixed non-cardinal Rodrigues rotation, declared before observations.
    axis=(1/math.sqrt(14),2/math.sqrt(14),3/math.sqrt(14));angle=.713
    c,s=math.cos(angle),math.sin(angle);dot=sum(a*b for a,b in zip(axis,point))
    cross=(axis[1]*point[2]-axis[2]*point[1],axis[2]*point[0]-axis[0]*point[2],axis[0]*point[1]-axis[1]*point[0])
    return tuple(c*p+s*q+(1-c)*dot*a for p,q,a in zip(point,cross,axis))


def gates(**changes):
    # Contract-only independent evidence records, not claimed measured F-scores.
    result={name:dict(status='pass',evidence_sha256='a'*64) for name in REQUIRED_GATES}
    for name,status in changes.items():result[name]['status']=status
    return result


class FrozenGeometryTests(unittest.TestCase):
    def setUp(self):
        self.data=fixture();self.cube=self.data['cube'];self.profile=ComparisonProfile(**self.data['profile'])

    def measure(self,vertices,triangles,**kwargs):
        return mesh_quality(vertices,triangles,frame_id=self.data['frame_id'],**kwargs)

    def test_cube_has_known_area_volume_planes_normal_moments_and_turning(self):
        expected=self.cube['expected']
        result=self.measure(self.cube['vertices'],self.cube['triangles'],sections=[dict(section_id='middle',normal=[0,0,1],offset=0)])
        self.assertEqual(result['status'],'measured')
        for name in ('surface_area','enclosed_volume','largest_planar_patch_fraction','normal_moment4','normal_moment8'):
            self.assertAlmostEqual(result[name],expected[name],places=12,msg=name)
        self.assertAlmostEqual(result['sections'][0]['turning_concentration'],expected['central_section_turning_concentration'],places=12)
        comparison=compare_quality(result,result,preservation_gates=gates(),profile=self.profile)
        self.assertEqual(comparison['shape_status'],'pass')
        self.assertEqual(comparison['verification_status'],'unknown')

    def test_area_weighting_is_invariant_to_planar_subdivision_for_cube_and_ellipsoid(self):
        for name,(vertices,triangles) in (('cube',(self.cube['vertices'],self.cube['triangles'])),('ellipsoid',ellipsoid(self.data['ellipsoid']))):
            with self.subTest(name=name):
                first=self.measure(vertices,triangles,sections=[dict(section_id='middle',normal=[0,0,1],offset=0)])
                second=self.measure(*subdivide(vertices,triangles),sections=[dict(section_id='middle',normal=[0,0,1],offset=0)])
                for field in ('surface_area','enclosed_volume','largest_planar_patch_fraction','normal_moment4','normal_moment8'):
                    self.assertAlmostEqual(first[field],second[field],places=10,msg=field)
                self.assertAlmostEqual(first['sections'][0]['turning_concentration'],second['sections'][0]['turning_concentration'],places=10)
                self.assertEqual(compare_quality(first,second,profile=self.profile)['shape_status'],'pass')

    def test_rigid_rotation_preserves_surface_moments_patches_and_jointly_rotated_section(self):
        first=self.measure(self.cube['vertices'],self.cube['triangles'],sections=[dict(section_id='middle',normal=[0,0,1],offset=0)])
        second=self.measure([rotate(p) for p in self.cube['vertices']],self.cube['triangles'],sections=[dict(section_id='middle',normal=rotate((0,0,1)),offset=0)])
        for field in ('surface_area','enclosed_volume','largest_planar_patch_fraction','normal_moment4','normal_moment8'):
            self.assertAlmostEqual(first[field],second[field],places=11,msg=field)
        self.assertAlmostEqual(first['sections'][0]['turning_concentration'],second['sections'][0]['turning_concentration'],places=11)

    def test_multinomial_moments_match_independent_pairwise_surface_integral(self):
        vertices,triangles=ellipsoid(dict(axes=[.7,.5,.9],longitudes=6,latitude_intervals=4))
        normals=[]
        for a,b,c in triangles:
            p,q,r=vertices[a],vertices[b],vertices[c]
            u=tuple(q[i]-p[i] for i in range(3));v=tuple(r[i]-p[i] for i in range(3))
            cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            length=math.sqrt(sum(x*x for x in cross));normals.append((length/2,tuple(x/length for x in cross)))
        area=sum(a for a,_ in normals);result=self.measure(vertices,triangles)
        for degree in (4,8):
            oracle=sum(a*b*sum(x*y for x,y in zip(n,m))**degree for a,n in normals for b,m in normals)/(area*area)
            self.assertAlmostEqual(result['normal_moment'+str(degree)],oracle,places=12)

    def test_source_region_clipping_preserves_area_and_shape_under_retessellation(self):
        regions=[dict(region_id='side',bounds=[[-.3,-1.1,-.7],[1.1,1.1,.7]],evidence_sha256='c'*64,validated=True)]
        first=self.measure(self.cube['vertices'],self.cube['triangles'],regions=regions)
        second=self.measure(*subdivide(self.cube['vertices'],self.cube['triangles']),regions=regions)
        for field in ('surface_area','largest_planar_patch_fraction','normal_moment4','normal_moment8'):
            self.assertAlmostEqual(first['regions'][0][field],second['regions'][0][field],places=11)
        self.assertIsNone(first['regions'][0]['enclosed_volume'])
        self.assertEqual(compare_quality(first,second,profile=self.profile)['regions'][0]['shape_status'],'pass')

    def test_exaggerated_cubification_alerts_relative_to_ellipsoid_but_not_source_cube(self):
        vertices,triangles=ellipsoid(self.data['ellipsoid']);axes=self.data['ellipsoid']['axes']
        section=[dict(section_id='middle',normal=[0,0,1],offset=0)]
        reference=self.measure(vertices,triangles,sections=section)
        candidate=self.measure([[a*x for a,x in zip(axes,p)] for p in self.cube['vertices']],self.cube['triangles'],sections=section)
        result=compare_quality(reference,candidate,profile=self.profile)
        self.assertEqual(result['shape_status'],'fail')
        self.assertEqual(result['signals']['largest_planar_patch_fraction']['status'],'fail')
        self.assertEqual(result['signals']['normal_moment8']['status'],'fail')
        self.assertEqual(result['signals']['section_turning']['status'],'fail')
        self.assertEqual(compare_quality(candidate,candidate,profile=self.profile)['shape_status'],'pass')

    def test_local_authority_and_named_missing_hand_are_not_hidden_in_global_mean(self):
        body=[tuple(p) for p in self.cube['vertices']];hand=[(1.5+.1*p[0],.1*p[1],.1*p[2]) for p in body]
        triangles=self.cube['triangles'];joined=triangles+[[i+8 for i in tri] for tri in triangles]
        regions=[dict(region_id='hand',bounds=[[1.3,-.2,-.2],[1.7,.2,.2]],evidence_sha256='b'*64,validated=True)]
        reference=self.measure(body+hand,joined,regions=regions);candidate=self.measure(body,triangles,regions=regions)
        result=compare_quality(reference,candidate,preservation_gates=gates(),profile=self.profile)
        self.assertEqual(result['global_shape_status'],'pass')
        self.assertEqual(result['shape_status'],'unknown')
        self.assertEqual(result['regions'][0]['surface_presence_status'],'fail')
        self.assertEqual(result['preservation_status'],'fail')
        self.assertEqual(result['overall_status'],'fail')
        self.assertEqual(candidate['regions'][0]['surface_area'],0.)

    def test_volume_and_shortening_are_not_fitted_away_or_accepted_from_roundness(self):
        reference=self.measure(self.cube['vertices'],self.cube['triangles'])
        shrunk=self.measure([[.5*x for x in p] for p in self.cube['vertices']],self.cube['triangles'])
        result=compare_quality(reference,shrunk,preservation_gates=gates(surface_fscore='fail'),profile=self.profile)
        self.assertEqual(result['shape_status'],'pass')
        self.assertEqual(result['size_observations']['enclosed_volume_ratio'],.125)
        self.assertEqual(result['preservation_status'],'fail')
        self.assertEqual(result['overall_status'],'fail')
        self.assertEqual(compare_quality(reference,shrunk)['preservation_status'],'unknown')

    def test_unverified_regions_open_sections_and_budget_remain_explicit_unknown(self):
        regions=[dict(region_id='unverified',bounds=[[-1,-1,-1],[1,1,1]],evidence_sha256='a'*64,validated=False)]
        result=self.measure(self.cube['vertices'],self.cube['triangles'],regions=regions,
            sections=[dict(section_id='face',normal=[0,0,1],offset=1)])
        self.assertEqual(result['regions'][0]['status'],'unknown')
        self.assertEqual(result['sections'][0]['status'],'unknown')
        limited=self.measure(self.cube['vertices'],self.cube['triangles'],policy=MetricPolicy(max_work=1))
        self.assertEqual(limited['status'],'unknown');self.assertEqual(limited['reason'],'metric_work_budget')
        self.assertLessEqual(limited['work_units'],1)
        cancelled=self.measure(self.cube['vertices'],self.cube['triangles'],cancel=lambda:True)
        self.assertEqual(cancelled['reason'],'metric_cancelled')
        json.dumps([result,limited,cancelled],allow_nan=False)

    def test_frame_mismatch_or_unresolved_independent_gate_does_not_acquire_acceptance(self):
        first=self.measure(self.cube['vertices'],self.cube['triangles'])
        second=mesh_quality(self.cube['vertices'],self.cube['triangles'],frame_id='different-frame')
        result=compare_quality(first,second,preservation_gates=gates())
        self.assertEqual(result['shape_status'],'unknown');self.assertEqual(result['preservation_status'],'unknown')
        self.assertEqual(compare_quality(first,first,preservation_gates=gates(important_parts='unknown'))['preservation_status'],'unknown')

    def test_unresolved_solid_volume_or_unsubstantiated_failure_cannot_turn_into_preservation_pass(self):
        closed=self.measure(self.cube['vertices'],self.cube['triangles'])
        opened=self.measure(self.cube['vertices'],self.cube['triangles'][:-1])
        self.assertIsNone(opened['enclosed_volume'])
        result=compare_quality(closed,opened,preservation_gates=gates())
        self.assertEqual(result['volume_observability_status'],'unknown')
        self.assertEqual(result['preservation_status'],'unknown')
        evidence=gates();evidence['important_parts']={'status':'fail','evidence_sha256':None}
        self.assertEqual(compare_quality(closed,closed,preservation_gates=evidence)['preservation_status'],'fail')
        with self.assertRaises(ValueError):MetricPolicy(max_triangles=200001)

    def test_malformed_inputs_and_missing_geometry_are_not_silently_measured(self):
        for vertices,triangles in (([[float('nan'),0,0]],[]),([[0,0,0]],[[0,1,2]]),([[0,0,0]],[[True,0,0]])):
            with self.assertRaises(ValueError):self.measure(vertices,triangles)
        empty=self.measure([],[])
        self.assertEqual(empty['status'],'unknown');self.assertEqual(empty['reason'],'empty_surface')
        self.assertIsNone(empty['enclosed_volume']);json.dumps(empty,allow_nan=False)


if __name__=='__main__':unittest.main()
