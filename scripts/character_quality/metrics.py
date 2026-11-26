"""Area-weighted geometry observations in a declared common frame.

No material/shading roughness, per-mesh fitting or aesthetic certificate is
inferred. Section planes and named regions are supplied from source authority.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import time

ALGORITHM = 'character-surface-observations-v1'


@dataclass(frozen=True)
class MetricPolicy:
    max_vertices: int = 200000
    max_triangles: int = 200000
    max_regions: int = 16
    max_sections: int = 32
    max_work: int = 40000000
    max_seconds: float = 30.
    position_tolerance: float = 1e-8
    normal_tolerance: float = 1e-7

    def __post_init__(self):
        for name,maximum in (('max_vertices',200000),('max_triangles',200000),('max_regions',16),('max_sections',32),('max_work',40000000)):
            value=getattr(self,name)
            if type(value) is not int or not 1<=value<=maximum: raise ValueError('Invalid metric work bound: '+name)
        for name in ('max_seconds','position_tolerance','normal_tolerance'):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0: raise ValueError('Invalid metric tolerance/deadline.')
        if self.max_seconds>120 or self.position_tolerance>1e-3 or self.normal_tolerance>1e-3:
            raise ValueError('Metric policy exceeds the bounded numerical profile.')


class _Budget:
    def __init__(self,policy,cancel):
        self.policy,self.cancel,self.work=policy,cancel,0
        self.started=time.perf_counter();self.deadline=self.started+policy.max_seconds
    def check(self,work=1):
        if self.work+work>self.policy.max_work: raise TimeoutError('metric_work_budget')
        if time.perf_counter()>=self.deadline: raise TimeoutError('metric_time_budget')
        if self.cancel is not None and self.cancel(): raise InterruptedError('metric_cancelled')
        self.work+=work


def _dot(a,b): return math.fsum(x*y for x,y in zip(a,b))
def _sub(a,b): return tuple(x-y for x,y in zip(a,b))
def _cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _length(a): return math.sqrt(_dot(a,a))
def _point(value):
    if not isinstance(value,(list,tuple)) or len(value)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e6 for x in value):
        raise ValueError('Vertices/directions require three finite bounded coordinates.')
    return tuple(float(x) for x in value)
def _digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def _address(value): return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def _key(point,tolerance): return tuple(round(c/tolerance) for c in point)


def _faces(vertices,triangles,policy,budget):
    faces=[]; degenerates=0
    for index,tri in enumerate(triangles):
        if index%256==0: budget.check(256)
        points=tuple(vertices[i] for i in tri)
        cross=_cross(_sub(points[1],points[0]),_sub(points[2],points[0])); twice=_length(cross)
        if twice<=policy.position_tolerance**2:
            degenerates+=1; continue
        faces.append((points,twice*.5,tuple(x/twice for x in cross)))
    return faces,degenerates


def _moments(faces,area,budget):
    result={}
    for degree in (4,8):
        terms=[(a,b,degree-a-b,math.factorial(degree)//(math.factorial(a)*math.factorial(b)*math.factorial(degree-a-b)))
               for a in range(degree+1) for b in range(degree-a+1)]
        sums=[0.]*len(terms)
        for index,(_,weight,normal) in enumerate(faces):
            if index%128==0: budget.check(128*len(terms))
            powers=[[1.]+[c**n for n in range(1,degree+1)] for c in normal]
            for j,(a,b,c,_) in enumerate(terms): sums[j]+=weight*powers[0][a]*powers[1][b]*powers[2][c]
        result['normal_moment'+str(degree)]=math.fsum(coefficient*(value/area)**2 for value,(*_,coefficient) in zip(sums,terms))
    return result


def _surface(faces,policy,budget):
    if not faces:
        return dict(status='unknown',reason='empty_surface',surface_area=0.,enclosed_volume=None,component_count=0,
                    largest_planar_patch_fraction=None,normal_moment4=None,normal_moment8=None,components=[])
    area=math.fsum(face[1] for face in faces); edges=defaultdict(list); parent=list(range(len(faces))); patches=list(parent)
    def find(group,i):
        while group[i]!=i: group[i]=group[group[i]];i=group[i]
        return i
    def join(group,a,b):
        a,b=find(group,a),find(group,b)
        if a!=b: group[max(a,b)]=min(a,b)
    for i,(points,_,normal) in enumerate(faces):
        if i%256==0: budget.check(256)
        keys=[_key(p,policy.position_tolerance) for p in points]
        for a,b in zip(keys,keys[1:]+keys[:1]): edges[tuple(sorted((a,b)))].append((i,a<b))
    boundary=nonmanifold=orientation=0
    for index,incident in enumerate(edges.values()):
        if index%256==0: budget.check(256)
        if len(incident)==1: boundary+=1
        elif len(incident)!=2: nonmanifold+=1
        if len(incident)!=2: continue
        (a,forward),(b,other)=incident;join(parent,a,b)
        if forward==other: orientation+=1
        points,_,normal=faces[a]; other_points,_,other_normal=faces[b]
        if _length(_cross(normal,other_normal))<=policy.normal_tolerance and all(
                abs(_dot(normal,_sub(p,points[0])))<=policy.position_tolerance for p in other_points): join(patches,a,b)
    components=defaultdict(list); planes=defaultdict(list)
    for i in range(len(faces)):
        components[find(parent,i)].append(i);planes[find(patches,i)].append(i)
    planar=[]; unresolved=0
    for indices in planes.values():
        total=math.fsum(faces[i][1] for i in indices);basis=faces[indices[0]][2]
        normal=tuple(math.fsum(faces[i][1]*faces[i][2][k]*(1 if _dot(faces[i][2],basis)>=0 else -1) for i in indices) for k in range(3))
        length=_length(normal);normal=tuple(c/length for c in normal)
        anchor=tuple(math.fsum(faces[i][1]*math.fsum(p[k] for p in faces[i][0])/3 for i in indices)/total for k in range(3))
        # Do not let a chain of tiny local turns claim an entire curved surface.
        valid=all(_length(_cross(normal,faces[i][2]))<=2*policy.normal_tolerance and all(
            abs(_dot(normal,_sub(p,anchor)))<=2*policy.position_tolerance for p in faces[i][0]) for i in indices)
        if valid: planar.append(math.fsum(faces[i][1] for i in indices))
        else: unresolved+=len(indices)
    details=[]
    edge_issues=defaultdict(lambda:[0,0,0])
    for incident in edges.values():
        for component in {find(parent,i) for i,_ in incident}:
            edge_issues[component][0]+=len(incident)==1
            edge_issues[component][1]+=len(incident)>2
            edge_issues[component][2]+=len(incident)==2 and incident[0][1]==incident[1][1]
    volume=0.;volume_known=True
    for number,(component,indices) in enumerate(sorted(components.items())):
        points=[p for i in indices for p in faces[i][0]]
        closed=not any(edge_issues[component]);component_volume=None
        if closed:
            anchor=points[0]
            component_volume=abs(math.fsum(_dot(_sub(a,anchor),_cross(_sub(b,anchor),_sub(c,anchor)))/6
                for i in indices for a,b,c in (faces[i][0],)))
            volume+=component_volume
        else: volume_known=False
        details.append(dict(component_id=number,surface_area=math.fsum(faces[i][1] for i in indices),enclosed_volume=component_volume,
            closed_oriented=closed,bounds=[[min(p[k] for p in points) for k in range(3)],[max(p[k] for p in points) for k in range(3)]]))
    result=dict(status='measured',surface_area=area,enclosed_volume=volume if volume_known else None,component_count=len(details),
        components=details,boundary_edges=boundary,nonmanifold_edges=nonmanifold,inconsistent_orientation_edges=orientation,
        largest_planar_patch_fraction=max(planar)/area if planar and not unresolved else None,
        planar_patch_count=len(planar),largest_planar_patch_fractions=[p/area for p in sorted(planar,reverse=True)[:16]],
        planarity_status='unknown' if unresolved else 'measured',unresolved_planarity_triangles=unresolved)
    result.update(_moments(faces,area,budget));return result


def _section(faces,section,policy,budget):
    if type(section) is not dict or set(section)-{'section_id','normal','offset'} or not {'section_id','normal','offset'}<=section.keys():
        raise ValueError('A section declares section_id, normal and offset in the shared frame.')
    name=section['section_id']; normal=_point(section['normal']);length=_length(normal)
    if type(name) is not str or not name or length<1e-12 or type(section['offset']) not in (int,float) or not math.isfinite(section['offset']):
        raise ValueError('Invalid declared section plane.')
    normal=tuple(c/length for c in normal); offset=section['offset']/length; nodes={};segments=set();coplanar=0
    def node(point):
        key=_key(point,policy.position_tolerance)
        if key not in nodes: nodes[key]=point
        return key
    for index,(points,_,_) in enumerate(faces):
        if index%256==0: budget.check(256)
        distances=[_dot(normal,p)-offset for p in points]
        if all(abs(d)<=policy.position_tolerance for d in distances): coplanar+=1;continue
        hits=[]
        for i,j in ((0,1),(1,2),(2,0)):
            a,b=distances[i],distances[j]
            if abs(a)<=policy.position_tolerance: hits.append(points[i])
            if a*b<0 and abs(a)>policy.position_tolerance and abs(b)>policy.position_tolerance:
                t=a/(a-b);hits.append(tuple(x+t*(y-x) for x,y in zip(points[i],points[j])))
        keys=list(dict.fromkeys(node(p) for p in hits))
        if len(keys)==2 and keys[0]!=keys[1]:segments.add(tuple(sorted(keys)))
    base=dict(section_id=name,normal=list(normal),offset=offset,segment_count=len(segments),coplanar_triangles=coplanar)
    graph=defaultdict(set)
    for a,b in segments:graph[a].add(b);graph[b].add(a)
    if coplanar or not segments or any(len(neighbours)!=2 for neighbours in graph.values()):
        return dict(base,status='unknown',reason='coplanar_surface_at_plane' if coplanar else 'open_or_branched_section' if segments else 'no_surface_intersection',loops=[])
    remaining=set(graph);loops=[]
    while remaining:
        budget.check();start=min(remaining);current=start;previous=None;ordered=[]
        while True:
            ordered.append(current);remaining.discard(current)
            following=min(graph[current]-({previous} if previous is not None else set()))
            previous,current=current,following
            if current==start:break
            if len(ordered)>len(graph):return dict(base,status='unknown',reason='unclosed_section_walk',loops=[])
        turns=[];perimeter=0.
        for i,key in enumerate(ordered):
            a=_sub(nodes[key],nodes[ordered[i-1]]);b=_sub(nodes[ordered[(i+1)%len(ordered)]],nodes[key]);la,lb=_length(a),_length(b)
            if la<=policy.position_tolerance or lb<=policy.position_tolerance:continue
            perimeter+=lb;angle=math.acos(max(-1.,min(1.,_dot(a,b)/(la*lb))))
            turns.append(0. if angle<=policy.normal_tolerance else angle)
        total=math.fsum(turns)
        if total<=policy.normal_tolerance:return dict(base,status='unknown',reason='unresolved_section_turns',loops=[])
        loops.append(dict(perimeter=perimeter,turning_concentration=math.fsum(t*t for t in turns)/(total*total),
            total_absolute_turn_radians=total,maximum_turn_radians=max(turns),vertex_count=len(ordered)))
        if len(loops)>128:return dict(base,status='unknown',reason='section_component_budget',loops=[])
    total_length=math.fsum(loop['perimeter'] for loop in loops)
    return dict(base,status='measured',loop_count=len(loops),perimeter=total_length,loops=loops,
        turning_concentration=math.fsum(loop['perimeter']*loop['turning_concentration'] for loop in loops)/total_length)


def _region(faces,region,policy,budget):
    allowed={'region_id','bounds','evidence_sha256','validated','origin','axes'}
    if type(region) is not dict or set(region)-allowed or not {'region_id','bounds','evidence_sha256','validated'}<=region.keys():
        raise ValueError('Named regions require bounded geometry and explicit source authority.')
    if type(region['region_id']) is not str or not region['region_id']:raise ValueError('Region ID is required.')
    if region['validated'] is not True or not _address(region['evidence_sha256']):
        return dict(region_id=region['region_id'],status='unknown',reason='region_authority_unverified',surface_area=None,sections=[])
    bounds=region['bounds']
    if not isinstance(bounds,(list,tuple)) or len(bounds)!=2:raise ValueError('Region bounds require minimum/maximum triples.')
    low,high=map(_point,bounds)
    if any(a>=b for a,b in zip(low,high)):raise ValueError('Region bounds must have positive extent.')
    origin=_point(region.get('origin',(0.,0.,0.)));axes=tuple(_point(a) for a in region.get('axes',((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))))
    if len(axes)!=3 or any(abs(_dot(a,b)-(1. if i==j else 0.))>1e-8 for i,a in enumerate(axes) for j,b in enumerate(axes)):
        raise ValueError('Region axes must be an explicitly orthonormal frame.')
    selected=[]
    for index,(points,_,normal) in enumerate(faces):
        if index%256==0:budget.check(256)
        polygon=list(points)
        for axis,a,b in zip(axes,low,high):
            for sign,bound in ((1.,b),(-1.,-a)):
                clipped=[]
                for i,current in enumerate(polygon):
                    previous=polygon[i-1];dc=sign*_dot(axis,_sub(current,origin))-bound;dp=sign*_dot(axis,_sub(previous,origin))-bound
                    if (dc<=0)!=(dp<=0):
                        t=dp/(dp-dc);clipped.append(tuple(x+t*(y-x) for x,y in zip(previous,current)))
                    if dc<=0:clipped.append(current)
                polygon=clipped
                if not polygon:break
            if not polygon:break
        for i in range(1,len(polygon)-1):
            triangle=(polygon[0],polygon[i],polygon[i+1]);area=.5*_length(_cross(_sub(triangle[1],triangle[0]),_sub(triangle[2],triangle[0])))
            if area>policy.position_tolerance**2:selected.append((triangle,area,normal))
        if len(selected)>policy.max_triangles:raise TimeoutError('region_triangle_budget')
    result=_surface(selected,policy,budget)
    mid=tuple((a+b)/2 for a,b in zip(low,high));centre=tuple(origin[k]+math.fsum(mid[i]*axes[i][k] for i in range(3)) for k in range(3))
    result.update(region_id=region['region_id'],authority_sha256=region['evidence_sha256'],bounds=[list(low),list(high)],
        origin=list(origin),axes=[list(a) for a in axes],selection='Exact triangle clipping to source-declared region; no synthetic caps.',
        sections=[_section(selected,dict(section_id=region['region_id']+'.axis'+str(i),normal=axis,offset=_dot(axis,centre)),policy,budget) for i,axis in enumerate(axes)])
    # Clipping generally opens surfaces; this is not a regional solid-volume claim.
    result['enclosed_volume']=None
    return result


def mesh_quality(vertices, triangles, *, frame_id, units='native_normalized', regions=(), sections=(),
                 policy=None, source_glb_sha256=None, cancel=None):
    """Return finite JSON observations; malformed inputs raise, insufficient data stays unknown."""
    policy=policy or MetricPolicy();budget=_Budget(policy,cancel)
    if type(frame_id) is not str or not frame_id or type(units) is not str or not units:raise ValueError('Explicit common frame and units are required.')
    if source_glb_sha256 is not None and not _address(source_glb_sha256):raise ValueError('Invalid source GLB SHA-256.')
    if len(vertices)>policy.max_vertices or len(triangles)>policy.max_triangles:raise ValueError('Mesh exceeds the bounded diagnostic profile.')
    if len(regions)>policy.max_regions or len(sections)+3*len(regions)>policy.max_sections:raise ValueError('Region/section count exceeds profile.')
    points=tuple(_point(p) for p in vertices);indices=[]
    for triangle in triangles:
        if not isinstance(triangle,(list,tuple)) or len(triangle)!=3 or any(type(i) is not int or not 0<=i<len(points) for i in triangle):
            raise ValueError('Triangles require three valid integer vertex indices.')
        indices.append(tuple(triangle))
    if len({r['region_id'] for r in regions})!=len(regions) or len({s['section_id'] for s in sections})!=len(sections):raise ValueError('Region/section IDs must be unique.')
    result=dict(schema_version=1,algorithm=ALGORITHM,frame_id=frame_id,units=units,
        source_glb_sha256=source_glb_sha256,mesh_sha256=_digest(dict(vertices=points,triangles=indices)),policy=asdict(policy),
        vertex_count=len(points),triangle_count=len(indices),verification_status='unknown',regions=[],sections=[],
        definitions=dict(surface_area='Sum of triangle areas in declared units squared.',
            enclosed_volume='Sum of absolute per-closed-oriented-component signed volume; null when unresolved.',
            planar_patches='Connected coincident-plane surface area; collinear/flat subdivision does not add patches.',
            normal_moments='Area-weighted E[(n dot n_prime)^k], k=4/8; exact 15/45 multinomial contractions, no normal bin axes.',
            section_turning='Perimeter-weighted loop sum(abs(turn)^2)/sum(abs(turn))^2; collinear inserted vertices contribute zero.',
            source_frame='No independent fit, scale normalization, registration or aesthetic inference.'))
    try:
        budget.check();faces,degenerates=_faces(points,indices,policy,budget)
        result.update(_surface(faces,policy,budget));result['degenerate_triangles']=degenerates
        result['bounds']=[[min(p[k] for p in points) for k in range(3)],[max(p[k] for p in points) for k in range(3)]] if points else None
        result['sections']=[_section(faces,s,policy,budget) for s in sections]
        for region in regions:result['regions'].append(_region(faces,region,policy,budget))
        if degenerates:result['coverage_status']='unknown';result['coverage_reason']='Degenerate source triangles were excluded explicitly.'
        else:result['coverage_status']='measured' if faces else 'unknown'
    except (TimeoutError,InterruptedError) as exc:
        result.update(status='unknown',coverage_status='unknown',reason=str(exc))
    result.update(work_units=budget.work,work_definition='Conservative reserved face/multinomial/section work units; not CPU instructions.',elapsed_seconds=time.perf_counter()-budget.started)
    json.dumps(result,allow_nan=False)
    return result
