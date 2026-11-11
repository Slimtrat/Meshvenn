"""Chamber doorway and hollow loot chest, metre-scale and animation-ready."""
import math
from .geometry import box, empty, merge_children, prism, ring, stud


def arch(t, halfwidth, spring, rise):
    # Pointed arch: tangent rises steeply from jamb, with a deliberate apex.
    return (-halfwidth * (1-t)**1.12, spring + rise * math.sin(t * math.pi/2))


def door(materials):
    stone, timber, bronze = (materials[key] for key in ('ChamberStone', 'DarkTimber', 'AgedBronze'))
    root = empty('ChamberDoorV1')
    frame = empty('DoorFrame', root)
    # The bottom threshold and jamb footprint explicitly pin the exterior bounds.
    box('Threshold', (0, .10, .035), (1.3, .2, .07), frame, stone, .012)
    for side in (-1, 1):
        for i in range(4):
            box('JambBlock', (side*.51, .106, .08 + .121 + i*.245), (.26, .188, .239), frame,
                stone, .014, seed=50 + i + side, chip=.06)
        box('JambFoot', (side*.51, .10, .105), (.28, .20, .07), frame, bronze, .008)
        box('Impost', (side*.51, .10, 1.055), (.28, .20, .055), frame, bronze, .007)
        for i in range(6):
            ta, tb = i/6 + .004, (i+1)/6 - .004
            ia, ib = arch(ta, .375, 1.02, .38), arch(tb, .375, 1.02, .38)
            oa, ob = arch(ta, .65, 1.07, .73), arch(tb, .65, 1.07, .73)
            polygon = [(side*x, z) for x, z in (ia, oa, ob, ib)]
            prism('ArchVoussoir', polygon, .012, .20, frame, stone, .009, seed=70+i+side)
            ma, mb = arch(ta, .399, 1.02, .425), arch(tb, .399, 1.02, .425)
            prism('ArchInlay', [(side*x, z) for x, z in (ia, ma, mb, ib)], 0, .021, frame, bronze, .002)
    prism('CrownKeystone', [(-.065,1.61),(-.083,1.745),(0,1.80),(.083,1.745),(.065,1.61)],
          .003, .2, frame, stone, 0)
    hinge = empty('DoorHinge', root, (-.362, .112, .075))
    leaf = empty('DoorLeaf', hinge)
    # Eight independent boards follow the pointed silhouette.
    for i in range(8):
        a, b = -.361+i*.09025+.002, -.361+(i+1)*.09025-.002
        def top(x):
            t = 1 - (abs(x)/.375)**(1/1.12)
            return 1.02 + .38*math.sin(max(0,t)*math.pi/2) - .012
        prism('DoorBoard', [(a,.078),(b,.078),(b,top(b)),(a,top(a))], .071,.145,leaf,timber,.006,seed=90+i)
    for z in (.245, .90):
        box('LeafCrossRail',(0,.057,z),(.713,.037,.045),leaf,bronze,.005)
        for x in (-.29,.29):
            stud('RailRivet',(x,.033,z),.012,.01,leaf,bronze)
    for side in (-1,1):
        box('LeafStile',(side*.338,.052,.60),(.028,.035,1.04),leaf,bronze,.005)
    for z in (.22,.88):
        stud('HingePin',(-.358,.102,z),.018,.06,leaf,bronze,axis='X')
    box('HandlePlate',(.222,.047,.637),(.067,.023,.145),leaf,bronze,.009)
    stud('HandleBoss',(.222,.027,.66),.022,.022,leaf,bronze)
    ring('DoorPull',(.222,.009,.605),.038,.009,leaf,bronze)
    empty('RouteSignalSocket',frame,(0,-.012,1.565))
    merge_children(frame)
    merge_children(leaf)
    return root, hinge, 'door', math.pi/2


def curved_lid(name, x1, x2, y_radius, z_radius, base_z, parent, mat, thickness=.018):
    """Closed shell with its inner surface visible in the open pose."""
    import bpy
    from .geometry import finish
    count = 12
    vertices=[]
    for radius_y,radius_z in ((y_radius,z_radius),(y_radius-thickness,z_radius-thickness)):
        for x in (x1,x2):
            vertices.extend((x,-radius_y*math.cos(math.pi*i/count),base_z+radius_z*math.sin(math.pi*i/count)) for i in range(count+1))
    row=count+1
    faces=[]
    for i in range(count):
        faces += [(i,i+1,row+i+1,row+i), (2*row+i,3*row+i,3*row+i+1,2*row+i+1),
                  (i,2*row+i,2*row+i+1,i+1),(row+i,row+i+1,3*row+i+1,3*row+i)]
    faces += [(0,row,3*row,2*row),(count,2*row+count,3*row+count,row+count)]
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    import bmesh
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    return finish(obj,parent,mat,.002)


def chest(materials):
    stone, timber, bronze = (materials[key] for key in ('ChamberStone', 'DarkTimber', 'AgedBronze'))
    root=empty('ChamberLootCacheV1');body=empty('ChestBody',root)
    # Five real walls leave a visible hollow cavity, no black solid masquerading as one.
    box('Bottom',(0,0,.046),(.804,.416,.052),body,timber,.008)
    for side in (-1,1):
        for i in range(3):
            box('StonePanel',(side*.395,0,.115+i*.077),(.035,.405,.074),body,stone,.005,seed=100+i+side)
            box('FrontBackPanel',(0,side*.197,.115+i*.077),(.775,.035,.074),body,stone,.006,seed=110+i+side)
        for y in (-.18,.18):
            box('CornerFoot',(side*.385,y,.034),(.08,.08,.068),body,bronze,.009)
            box('CornerGuard',(side*.396,y,.19),(.045,.056,.245),body,bronze,.006)
        box('UpperRimFrontBack',(0,side*.207,.324),(.834,.026,.031),body,bronze,.004)
        box('UpperRimSide',(side*.408,0,.324),(.025,.413,.031),body,bronze,.004)
    for x in (-.29,.29):
        box('BodyBand',(x,-.214,.199),(.036,.009,.225),body,bronze,.003)
        for z in (.12,.285):
            stud('BodyRivet',(x,-.214,z),.012,.01,body,bronze)
    # Upper lid extents: X .85, Y .44, Z .52; rear hinge is not at object centre.
    hinge=empty('LidHinge',root,(0,.212,.335));lid=empty('ChestLid',hinge)
    curved_lid('VaultedLid',-.415,.415,.212,.177,.343,lid,stone)
    for x in (-.407,-.278,.278,.407):
        curved_lid('BronzeLidBand',x-.014,x+.014,.22,.185,.335,lid,bronze,.012)
    # End-cap semicircle closes each end of the lid while the underside remains hollow.
    import bpy
    from .geometry import finish
    for side in (-1,1):
        vertices=[(side*.414,-.206,.343),(side*.414,.206,.343)]
        vertices += [(side*.414,-.206*math.cos(math.pi*i/12),.343+.17*math.sin(math.pi*i/12)) for i in range(11,0,-1)]
        mesh=bpy.data.meshes.new('LidEnd');mesh.from_pydata(vertices,[],[tuple(range(len(vertices)))]);mesh.update()
        obj=bpy.data.objects.new('LidEnd',mesh);bpy.context.collection.objects.link(obj)
        solid=obj.modifiers.new('End thickness','SOLIDIFY');solid.thickness=.01
        bpy.context.view_layer.objects.active=obj;bpy.ops.object.modifier_apply(modifier=solid.name)
        finish(obj,lid,stone,.002)
    for side in (-1,1):
        box('LidLip',(0,side*.211,.344),(.85,.018,.025),lid,bronze,.004)
    prism('Escutcheon',[(-.046,.22),(-.068,.29),(-.058,.385),(0,.405),(.058,.385),(.068,.29),(.046,.22)],
          -.219,-.201,lid,bronze,.003)
    prism('LockInset',[(0,.264),(-.022,.292),(0,.324),(.022,.292)],-.220,-.218,lid,timber,0)
    stud('LockRivet', (0,-.217,.365),.014,.005,lid,bronze)
    for x in (-.27,.27):
        box('RearHinge',(x,.204,.32),(.075,.028,.075),body,bronze,.005)
    empty('LootSpawnSocket',root,(0,0,.66))
    merge_children(body);merge_children(lid)
    return root,hinge,'chest',math.radians(-105)
