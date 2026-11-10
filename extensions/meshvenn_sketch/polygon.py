"""Validated simple outlines and concave cap triangulation, without Blender."""
import math

EPS = 1e-10
MAX_POINTS = 512


def cross(a,b,c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _on(a,b,p):
    return abs(cross(a,b,p))<=EPS and all(min(a[i],b[i])-EPS<=p[i]<=max(a[i],b[i])+EPS for i in (0,1))


def _intersects(a,b,c,d):
    x,y,z,w=cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
    return (x*y<0 and z*w<0) or _on(a,b,c) or _on(a,b,d) or _on(c,d,a) or _on(c,d,b)


def outline(points):
    """Return a CCW simple polygon; refuse holes, crossings and degenerate input."""
    if not 3<=len(points)<=4096:raise ValueError('Draw one closed outline with at least three points.')
    clean=[]
    for p in points:
        if len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p):
            raise ValueError('Outline coordinates must be finite image UVs.')
        p=tuple(p)
        if not clean or math.dist(clean[-1],p)>1e-8:clean.append(p)
    if len(clean)>1 and math.dist(clean[0],clean[-1])<=1e-8:clean.pop()
    changed=True
    while changed and len(clean)>3:
        changed=False
        for i in range(len(clean)):
            if _on(clean[i-1],clean[(i+1)%len(clean)],clean[i]):
                clean.pop(i);changed=True;break
    if not 3<=len(clean)<=MAX_POINTS:
        raise ValueError('Outline is empty or too complex; use at most 512 contour corners.')
    n=len(clean)
    for i in range(n):
        for j in range(i+1,n):
            if j in {i,(i+1)%n} or i==(j+1)%n:continue
            if _intersects(clean[i],clean[(i+1)%n],clean[j],clean[(j+1)%n]):
                raise ValueError('The outline crosses or touches itself. Redraw a single outer contour.')
    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(clean,clean[1:]+clean[:1]))/2
    if abs(area)<=EPS:raise ValueError('The outline has no usable area.')
    return tuple(clean if area>0 else reversed(clean))


def triangulate(points):
    points=outline(points);remaining=list(range(len(points)));triangles=[]
    while len(remaining)>3:
        for k,b in enumerate(remaining):
            a,c=remaining[k-1],remaining[(k+1)%len(remaining)]
            if cross(points[a],points[b],points[c])<=EPS:continue
            if any(all(cross(points[x],points[y],points[p])>=-EPS for x,y in ((a,b),(b,c),(c,a)))
                   for p in remaining if p not in {a,b,c}):continue
            triangles.append((a,b,c));remaining.pop(k);break
        else:raise ValueError('Cannot triangulate this contour. Remove near-overlapping corners.')
    triangles.append(tuple(remaining))
    return points,tuple(triangles)


def simplify(points, image_size, tolerance=.8):
    """Closed RDP in image pixels; its tolerance never grows to hide complexity."""
    points=tuple(tuple(p) for p in points)
    if len(points)<4:return points
    width,height=image_size
    if width<=0 or height<=0 or not 0<tolerance<=4:raise ValueError('Invalid image simplification scale.')
    pixel=[(p[0]*width,p[1]*height) for p in points]
    if math.dist(pixel[0],pixel[-1])<tolerance:pixel.pop();points=points[:-1]
    if len(pixel)<4:return points
    split=max(range(1,len(pixel)),key=lambda i:math.dist(pixel[0],pixel[i]))
    def chain(indices):
        keep={indices[0],indices[-1]};pending=[(0,len(indices)-1)]
        while pending:
            left,right=pending.pop()
            if right-left<2:continue
            a,b=pixel[indices[left]],pixel[indices[right]]
            dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
            def distance(k):
                p=pixel[indices[k]]
                t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0
                return math.dist(p,(a[0]+t*dx,a[1]+t*dy))
            far=max(range(left+1,right),key=distance)
            if distance(far)>tolerance:
                keep.add(indices[far]);pending.extend(((left,far),(far,right)))
        return [i for i in indices if i in keep]
    order=chain(list(range(split+1)))[:-1]+chain(list(range(split,len(pixel)))+[0])[:-1]
    return tuple(points[i] for i in order)
