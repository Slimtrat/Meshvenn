"""Original workshop designs, fitted to the public doll's actual joint heads."""
import math
from mathutils import Vector
from geometry import Model

PALETTE=(('Workshop enamel',(.075,.28,.29,1),.2,.48),
         ('Aged brass',(.46,.285,.105,1),.65,.4),
         ('Dark rubber',(.035,.045,.05,1),.05,.8),
         ('Woven canvas',(.38,.255,.14,1),0.,.9))


def designs(joints,frame):
    result=[]
    def add(id,label,category,bone,owner,model,replace=None,socket=None):
        result.append(dict(id=id,label=label,category=category,parent_joint=bone,owner_region=owner,
                           replaces_region=replace,socket_id=socket,model=model))
    head=Model()
    head.silhouette([(-13,61),(-13,66),(-10,71),(10,71),(13,66),(13,61),
                     (10,61),(10,65),(8,68),(-8,68),(-10,65),(-10,61)],-1.5,21,'head',0,frame)
    for side in (-1,1):
        head.ellipsoid((side*12,-1.5,63),(1.8,5.,3.3),'head',1)
        head.ring((side*12,-6.3,63),(0,1,0),1.1,.3,'head',2)
    add('workshop-headguard','Workshop headguard','equipment','head','body-core',head,socket='attach-head')
    for side,suffix,region in ((1,'L','left-arm'),(-1,'R','right-arm')):
        shoulder=Vector(joints['upper_arm.'+suffix]);elbow=Vector(joints['forearm.'+suffix]);wrist=Vector(joints['hand.'+suffix])
        guard=Model();x,z=shoulder.x,shoulder.z
        guard.silhouette([(x-3.5,z+1),(x-4.5,z+3.5),(x-2.3,z+5.4),(x+2.3,z+5.4),(x+4.5,z+3.5),(x+3.5,z+1)],shoulder.y,7.,'upper_arm.'+suffix,0,frame)
        guard.ring(shoulder+(elbow-shoulder)*.18,elbow-shoulder,2.9,.32,'upper_arm.'+suffix,1)
        add('shoulder-shell-'+suffix.lower(),'Shoulder shell '+suffix,'equipment','upper_arm.'+suffix,region,guard)
        arm=Model();upper='upper_arm.'+suffix;lower='forearm.'+suffix;hand='hand.'+suffix
        arm.capsule(shoulder,elbow,1.85,upper,0)
        arm.ellipsoid(elbow,(2.05,2.05,2.05),lower,2)
        arm.capsule(elbow,wrist,1.7,lower,0)
        for t in (.2,.8):arm.ring(elbow+(wrist-elbow)*t,wrist-elbow,1.7,.25,lower,1)
        direction=(wrist-elbow).normalized();palm=wrist+direction*2.1
        arm.ellipsoid(palm,(2.5,2.05,1.8),hand,1)
        for i in (-1,0,1):
            a=palm+Vector((side*1.,i*1.65,.3));b=a+Vector((side*2.6,i*.4,0));c=b+Vector((side*.7,-i*.45,-1.1))
            arm.sweep((a,b,c),(.58,.5,.32),hand,2)
        add('grip-arm-'+suffix.lower(),'Articulated grip arm '+suffix,'replacement',upper,region,arm,replace=region)
    for suffix,region in (('L','left-leg'),('R','right-leg')):
        upper='thigh.'+suffix;lower='shin.'+suffix;foot='foot.'+suffix
        hip,knee,ankle=(Vector(joints[b]) for b in (upper,lower,foot));leg=Model()
        leg.capsule(hip,knee,2.3,upper,0)
        leg.ellipsoid(knee,(2.35,2.35,2.35),lower,2)
        axis=ankle-knee;leg.capsule(knee,ankle,.85,lower,2)
        guide=Vector((0,1,0));u=axis.normalized().cross(guide).normalized();v=axis.normalized().cross(u)
        coil=[]
        for i in range(65):
            t=i/64;angle=t*math.pi*8
            coil.append(knee+axis*(.12+.76*t)+u*(1.8*math.cos(angle))+v*(1.8*math.sin(angle)))
        leg.sweep(coil,[.32]*len(coil),lower,1,sides=6)
        for t in (.1,.9):leg.ring(knee+axis*t,axis,1.8,.4,lower,0)
        leg.ellipsoid((ankle.x,-7.4,6.4),(3.25,7.65,2.45),foot,0)
        leg.ellipsoid(ankle+Vector((0,-1.,-2.3)),(2.2,2.8,3.7),foot,2)
        leg.ellipsoid((ankle.x,-9.3,4.5),(3.2,5.7,.55),foot,2)
        add('spring-leg-'+suffix.lower(),'Articulated spring leg '+suffix,'replacement',upper,region,leg,replace=region)
    horns=Model()
    for side in (-1,1):
        path=[(side*x,y,z) for x,y,z in ((6,0,69),(9,.5,73),(12,1,78),(11,0,82),(7,-1,84))]
        horns.sweep(path,[1.9,1.6,1.1,.6,.08],'head',1,sides=16)
        horns.ring(path[0],Vector(path[1])-Vector(path[0]),1.9,.3,'head',2)
    add('curled-horns','Curled brass horns','accessory','head','body-core',horns,socket='attach-head')
    wings=Model()
    contour=((3,47),(8,57),(18,65),(26,61),(28,52),(23,54),(20,48),(16,51),(12,45),(8,48))
    for side in (-1,1):
        wings.silhouette([(side*x,z) for x,z in contour],8.5,.85,'chest',3,frame)
        for x,z in ((18,65),(26,61),(28,52),(20,48),(12,45)):
            wings.sweep(((side*3,8.1,47),(side*(x*.55+1.5),8.1,(z+47)/2+1),(side*x,8.1,z)),(.3,.26,.12),'chest',1,sides=6)
    add('tatter-wings','Canvas glider wings','accessory','chest','body-core',wings,socket='attach-wing')
    bag=Model();bag.ellipsoid((0,12,36),(7,5,8),'spine',3)
    bag.silhouette([(-6,38),(-6,43),(-3.5,45),(3.5,45),(6,43),(6,38)],16,1.5,'spine',0,frame)
    for x in (-3.2,3.2):
        bag.capsule((x,16.5,33),(x,16.5,40),.5,'spine',2)
        bag.ring((x,17,36.5),(0,1,0),.8,.23,'spine',1)
    bag.sweep(((-2,12,44),(-2,12,47),(2,12,47),(2,12,44)),(.45,.45,.45,.45),'spine',2)
    add('field-backpack','Field backpack','accessory','spine','body-core',bag,socket='attach-backpack')
    return result
