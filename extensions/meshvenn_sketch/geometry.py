"""Consumer of the documented surface-envelope-v1 coordinates, not engine code."""
from dataclasses import dataclass
import math

from .polygon import triangulate


def dot(a,b):return sum(x*y for x,y in zip(a,b))


@dataclass(frozen=True)
class ViewFrame:
    minimum: tuple
    size: tuple
    azimuth: float = 0.
    elevation: float = 0.
    flip_x: bool = False
    offset_u: float = 0.
    offset_v: float = 0.
    scale: float = 1.

    def __post_init__(self):
        if (len(self.minimum)!=3 or len(self.size)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in (*self.minimum,*self.size,self.azimuth,self.elevation,self.offset_u,self.offset_v,self.scale))
                or min(self.size)<=0 or not -90<=self.elevation<=90 or not .25<=self.scale<=4
                or type(self.flip_x) is not bool or max(abs(self.offset_u),abs(self.offset_v))>.5):
            raise ValueError('Invalid calibrated projection frame.')
        object.__setattr__(self,'minimum',tuple(self.minimum))
        object.__setattr__(self,'size',tuple(self.size))

    def axes(self):
        az,el=math.radians(self.azimuth),math.radians(self.elevation)
        ca,sa,ce,se=math.cos(az),math.sin(az),math.cos(el),math.sin(el)
        return (ca,sa,0.),(sa*se,-ca*se,ce),(sa*ce,-ca*ce,-se)

    def extents(self):
        az,el=math.radians(self.azimuth),math.radians(self.elevation)
        horizontal=max(abs(math.cos(az))+abs(math.sin(az)),1e-9)
        return horizontal,max(horizontal*abs(math.sin(el))+abs(math.cos(el)),1e-9)

    def normalized(self,p):return tuple(2*(v-o)/s-1 for v,o,s in zip(p,self.minimum,self.size))

    def ray(self):
        back=self.axes()[2];d=tuple(s*b/2 for s,b in zip(self.size,back));length=math.sqrt(dot(d,d))
        return tuple(v/length for v in d)

    def project(self,p):
        right,up,_=self.axes();h,v=self.extents();n=self.normalized(p)
        u=.5+dot(n,right)/(2*h);y=.5+dot(n,up)/(2*v)
        if self.flip_x:u=1-u
        return ((u-.5-self.offset_u)/self.scale+.5,(y-.5-self.offset_v)/self.scale+.5)

    def unproject(self,uv,anchor):
        if len(uv)!=2 or len(anchor)!=3 or any(not math.isfinite(v) for v in (*uv,*anchor)):
            raise ValueError('Invalid outline or depth anchor.')
        u=.5+(uv[0]-.5)*self.scale+self.offset_u
        v=.5+(uv[1]-.5)*self.scale+self.offset_v
        if self.flip_x:u=1-u
        right,up,back=self.axes();h,w=self.extents()
        depth=dot(self.normalized(anchor),back)
        n=tuple(r*(2*u-1)*h+y*(2*v-1)*w+b*depth for r,y,b in zip(right,up,back))
        return tuple(o+s*(v+1)/2 for o,s,v in zip(self.minimum,self.size,n))


def extrude(points,frame,anchor,thickness,offset=0.):
    """Closed manifold with outward caps; depth follows the calibrated pixel ray."""
    if (type(thickness) not in (int,float) or not math.isfinite(thickness) or thickness<=0
            or type(offset) not in (int,float) or not math.isfinite(offset)):
        raise ValueError('Choose a positive finite thickness and finite depth offset.')
    points,triangles=triangulate(points);n=len(points);direction=frame.ray()
    plane=[frame.unproject(p,anchor) for p in points]
    vertices=tuple(tuple(p[i]+direction[i]*(offset+sign*thickness/2) for i in range(3))
                   for sign in (1,-1) for p in plane)
    front=tuple(tuple(reversed(t)) if frame.flip_x else t for t in triangles)
    faces=list(front)+[tuple(n+i for i in reversed(t)) for t in front]
    order=list(reversed(range(n))) if frame.flip_x else list(range(n))
    faces.extend((i,i+n,j+n,j) for i,j in zip(order,order[1:]+order[:1]))
    # Cap UVs remain the drawn image UVs; side loops are a separate strip.
    uvs=[tuple(points[i%n] for i in face) for face in faces[:2*len(front)]]
    lengths=[math.dist(plane[i],plane[j]) for i,j in zip(order,order[1:]+order[:1])]
    perimeter=sum(lengths);travel=0.
    for length in lengths:
        a,b=travel/perimeter,(travel+length)/perimeter
        uvs.append(((a,1.),(a,0.),(b,0.),(b,1.)));travel+=length
    return points,vertices,tuple(faces),tuple(uvs)
