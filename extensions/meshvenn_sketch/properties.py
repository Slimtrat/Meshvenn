"""Scene-owned authoring state, separate from Meshvenn pipeline settings."""
import math
import bpy
from bpy.props import BoolProperty,CollectionProperty,FloatProperty,FloatVectorProperty,PointerProperty,StringProperty


def mesh_only(self,obj):return obj.type=='MESH'


class MVSK_Point(bpy.types.PropertyGroup):
    uv: FloatVectorProperty(size=2)


class MVSK_Settings(bpy.types.PropertyGroup):
    source: PointerProperty(name='Character / Source Mesh',type=bpy.types.Object,poll=mesh_only)
    image: PointerProperty(name='Reference Image',type=bpy.types.Image)
    calibrated_source: PointerProperty(type=bpy.types.Object,options={'HIDDEN'})
    calibrated_image: PointerProperty(type=bpy.types.Image,options={'HIDDEN'})
    frame_json: StringProperty(options={'HIDDEN'})
    calibration_label: StringProperty(options={'HIDDEN'})
    azimuth: FloatProperty(name='View Azimuth',subtype='ANGLE',default=0.)
    elevation: FloatProperty(name='View Elevation',subtype='ANGLE',min=-math.pi/2,max=math.pi/2)
    flip_x: BoolProperty(name='Flip Horizontal')
    bone: StringProperty(name='Bone')
    bind_to_rig: BoolProperty(name='Bind to Bone',default=True)
    name: StringProperty(name='Piece Name',default='Sketch Piece')
    thickness: FloatProperty(name='Thickness / Frame Height',default=.035,min=.0001,max=1.,precision=4)
    depth: FloatProperty(name='Depth Offset / Frame Height',default=0.,min=-2.,max=2.,precision=4)
    edge: FloatProperty(name='Rounded Edge / Frame Height',default=.004,min=0.,max=.1,precision=4)
    color: FloatVectorProperty(name='Piece Color',size=4,subtype='COLOR',default=(.12,.42,.65,1.),min=0.,max=1.)
    contour: CollectionProperty(type=MVSK_Point)
    piece: PointerProperty(name='Edited Piece',type=bpy.types.Object,poll=mesh_only)


CLASSES=(MVSK_Point,MVSK_Settings)
