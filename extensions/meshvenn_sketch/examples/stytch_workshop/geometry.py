"""Small closed, UV-mapped solids for the authored workshop module collection."""
import math
from mathutils import Vector


class Model:
    def __init__(self):
        self.vertices=[];self.faces=[];self.bones=[];self.materials=[];self.uvs=[]

    def add(self,vertices,faces,bone,material,uvs=None):
        start=len(self.vertices)
        self.vertices.extend(tuple(p) for p in vertices);self.bones.extend([bone]*len(vertices))
        self.faces.extend(tuple(start+i for i in face) for face in faces)
        self.materials.extend([material]*len(faces))
        self.uvs.extend(uvs or [tuple((.5+.45*math.cos(2*math.pi*i/len(f)),.5+.45*math.sin(2*math.pi*i/len(f))) for i in range(len(f))) for f in faces])

    def sweep(self,points,radii,bone,material,sides=12):
        points=[Vector(p) for p in points];vertices=[]
        for i,(point,radius) in enumerate(zip(points,radii)):
            tangent=(points[min(i+1,len(points)-1)]-points[max(i-1,0)]).normalized()
            guide=Vector((0,1,0)) if abs(tangent.y)<.9 else Vector((1,0,0))
            u=tangent.cross(guide).normalized();v=tangent.cross(u)
            a,b=(radius,radius) if isinstance(radius,(int,float)) else radius
            vertices.extend(point+u*(a*math.cos(2*math.pi*j/sides))+v*(b*math.sin(2*math.pi*j/sides)) for j in range(sides))
        faces=[tuple(reversed(range(sides)))];uvs=[tuple((.5+.45*math.cos(2*math.pi*j/sides),.5+.45*math.sin(2*math.pi*j/sides)) for j in reversed(range(sides)))]
        for i in range(len(points)-1):
            for j in range(sides):
                k=(j+1)%sides
                faces.append((i*sides+j,i*sides+k,(i+1)*sides+k,(i+1)*sides+j))
                uvs.append(((j/sides,i/(len(points)-1)),((j+1)/sides,i/(len(points)-1)),((j+1)/sides,(i+1)/(len(points)-1)),(j/sides,(i+1)/(len(points)-1))))
        faces.append(tuple(range((len(points)-1)*sides,len(vertices))))
        uvs.append(tuple((.5+.45*math.cos(2*math.pi*j/sides),.5+.45*math.sin(2*math.pi*j/sides)) for j in range(sides)))
        self.add(vertices,faces,bone,material,uvs)

    def capsule(self,a,b,radius,bone,material):
        a,b=Vector(a),Vector(b);d=b-a
        if d.length<radius:raise ValueError('Capsule axis too short')
        points=[a-d.normalized()*radius*.35,a,a+d*.12,a+d*.88,b,b+d.normalized()*radius*.35]
        self.sweep(points,[radius*.35,radius*.85,radius,radius,radius*.85,radius*.35],bone,material)

    def ellipsoid(self,center,scale,bone,material):
        center=Vector(center);vertices=[center+Vector((0,0,-scale[2]))];faces=[];uvs=[]
        sides,rings=16,9
        for i in range(1,rings+1):
            t=-math.pi/2+math.pi*i/(rings+1)
            vertices.extend(center+Vector((scale[0]*math.cos(t)*math.cos(2*math.pi*j/sides),scale[1]*math.cos(t)*math.sin(2*math.pi*j/sides),scale[2]*math.sin(t))) for j in range(sides))
        top=len(vertices);vertices.append(center+Vector((0,0,scale[2])))
        for j in range(sides):
            k=(j+1)%sides;faces.append((0,1+k,1+j));uvs.append(((.5,0),((j+1)/sides,1/(rings+1)),(j/sides,1/(rings+1))))
        for i in range(rings-1):
            for j in range(sides):
                k=(j+1)%sides;faces.append((1+i*sides+j,1+i*sides+k,1+(i+1)*sides+k,1+(i+1)*sides+j))
                uvs.append(((j/sides,(i+1)/(rings+1)),((j+1)/sides,(i+1)/(rings+1)),((j+1)/sides,(i+2)/(rings+1)),(j/sides,(i+2)/(rings+1))))
        for j in range(sides):
            faces.append((top,1+(rings-1)*sides+j,1+(rings-1)*sides+(j+1)%sides))
            uvs.append(((.5,1),(j/sides,rings/(rings+1)),((j+1)/sides,rings/(rings+1))))
        self.add(vertices,faces,bone,material,uvs)

    def ring(self,center,axis,radius,tube,bone,material):
        center,axis=Vector(center),Vector(axis).normalized()
        guide=Vector((0,1,0)) if abs(axis.y)<.9 else Vector((1,0,0))
        u=axis.cross(guide).normalized();v=axis.cross(u);vertices=[];faces=[];uvs=[]
        major,minor=20,6
        for i in range(major):
            radial=u*math.cos(2*math.pi*i/major)+v*math.sin(2*math.pi*i/major)
            vertices.extend(center+radial*(radius+tube*math.cos(2*math.pi*j/minor))+axis*(tube*math.sin(2*math.pi*j/minor)) for j in range(minor))
        for i in range(major):
            for j in range(minor):
                faces.append((i*minor+j,((i+1)%major)*minor+j,((i+1)%major)*minor+(j+1)%minor,i*minor+(j+1)%minor))
                uvs.append(((i/major,j/minor),((i+1)/major,j/minor),((i+1)/major,(j+1)/minor),(i/major,(j+1)/minor)))
        self.add(vertices,faces,bone,material,uvs)

    def silhouette(self,points,depth,thickness,bone,material,frame):
        from meshvenn_sketch.geometry import extrude
        uv=[frame.project((x,depth,z)) for x,z in points]
        _,vertices,faces,uvs=extrude(uv,frame,(0,depth,0),thickness)
        self.add(vertices,faces,bone,material,uvs)
