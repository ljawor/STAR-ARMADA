"""Original Free Systems Alliance escort frigate, explicit geometry only.

X is beam, Y is up, +Z is forward. A blunt command hammerhead, separate
outboard machinery and readable service bays replace the Imperium spear.
The caller owns materials, scene initialization, export and asset activation.
No approved Alliance builder or Blender module is imported here.
"""
import math


def _beam(g, name, role, a, b, width, depth):
    """Rectangular connected service girder between two world-space points."""
    d = [b[i]-a[i] for i in range(3)]
    length = math.sqrt(sum(v*v for v in d))
    d = [v/length for v in d]
    # All authored girders lie in XZ or YZ, never parallel to the X reference.
    u = [0, d[2], -d[1]]
    norm = math.sqrt(sum(v*v for v in u))
    u = [v/norm for v in u]
    v = [d[1]*u[2]-d[2]*u[1],d[2]*u[0]-d[0]*u[2],d[0]*u[1]-d[1]*u[0]]
    verts = [tuple(p[i]+su*width*u[i]/2+sv*depth*v[i]/2 for i in range(3))
             for p in (a,b) for su,sv in ((-1,-1),(1,-1),(1,1),(-1,1))]
    g.mesh(name,role,verts,[(3,2,1,0),(4,5,6,7),(0,1,5,4),
                            (1,2,6,5),(2,3,7,6),(3,0,4,7)])


def _deck_drum(g, name, role, x, y, z, radius, depth, n):
    """Y-axis fastener/bearing; facade disc is reserved for Z-axis exhaust."""
    verts = [(x+radius*math.cos(j*2*math.pi/n),y+d*depth/2,
              z+radius*math.sin(j*2*math.pi/n))
             for d in (-1,1) for j in range(n)]
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    g.mesh(name,role,verts,faces)


def build(kind, g, frame):
    """Author one frigate through the unchanged six-role geometry facade.

    Broad structural surfaces, not isolated markers, establish the .998
    envelope. All dimensions are authored inside the manifest; no evaluated
    mesh fitting, bevel modifiers, global flattening or exporter side effects.
    """
    if kind != 'frigate':
        raise ValueError('Alliance representative ship supports only frigate')
    half_beam = frame['span'][0]*.499
    xmid = frame['center'][0]
    if abs(xmid) > 1e-7:
        raise ValueError('Alliance frigate requires the native centered X frame')
    aft = frame['center'][2]-frame['span'][2]*.499
    fore = frame['center'][2]+frame['span'][2]*.499
    keel = frame['center'][1]-frame['span'][1]*.499
    crown = frame['center'][1]+frame['span'][1]*.499

    # Naval pressure hull: a long rectangular backbone, not a pointed wedge.
    g.loft('continuous naval pressure spine','dark',[
        (-67,8,5,-5),(-59,11,8,-7),(-39,12,10,-8),(-12,12,11,-8),
        (14,12,11,-7),(35,11,10,-6),(51,13,10,-5),(60,12,8,-4)])
    g.loft('deep continuous armored keel','base',[
        (-61,5,-4,-7),(-48,7,-5,keel),(-9,7,-5,keel),
        (24,6,-4,-9),(47,5,-3,-7),(57,4,-2,-5)])
    g.loft('forward hammerhead command hull','base',[
        (38,16,10,-4),(44,27,14,-5),(51,half_beam,15,-5),
        (61,half_beam,15,-4),(68,31,13,-3),(fore-.35,26,10,-1)])
    g.loft('hammerhead lower protective chine','trim',[
        (43,23,-2,-4.5),(51,31,-2,-5.5),(63,31,-1,-4.5),(70,26,0,-2.5)])
    # A wide, low bridge grows directly out of the hammerhead's dorsal deck.
    g.loft('command citadel lower stepped plinth','dark',[
        (42,13,16,10),(46,17,19,11),(60,17,19,11),(66,12,16,10)])
    g.loft('command citadel armored shoulders','base',[
        (44,12,18.5,13),(48,15,20.5,13),(60,15,20.5,13),(65,11,18.5,13)])
    g.loft('rounded chamfer command crown','base',[
        (46,9,22,17),(49,11,crown,17),(59,11,crown,17),(64,9,23,17)])
    for j in range(7):
        x=(j-3)*2.05
        g.box('bridge forward recessed glazing gasket %02d'%j,'dark',(x,20.2,64.08),(1.85,2.9,.22))
        g.box('bridge forward blue glazing %02d'%j,'cool',(x,20.25,64.23),(1.5,1.75,.12))
    for side in (-1,1):
        for j in range(4):
            g.box('bridge side glazing %s %02d'%(side,j),'cool',(side*11.04,21.3,50.2+j*2.1),(.16,1.45,1.45))
        g.loft('hammerhead port navigation cheek %s'%side,'accent',[
            (48,2,15.1,13),(51,3,15.55,13),(62,3,15.55,13),(66,2,13.6,12)],x=side*25)
        g.box('hammerhead navigation lamp %s'%side,'lit',(side*27.5,14.6,61.5),(1.4,.7,3))

    # Discrete armor blocks have real bevelled/chamfered profiles and gaps
    # revealing the continuous pressure structure rather than painted seams.
    for j,z in enumerate((-51,-36,-21,-6,9,24,36)):
        for side in (-1,1):
            g.loft('stepped shoulder armor %s %02d'%(side,j),'base',[
                (z-6.5,3.6,11.1,-3),(z-5.4,5.1,13,-4.8),
                (z+4.4,5.1,13,-4.8),(z+6.2,3.6,11.1,-3)],x=side*10)
            g.loft('shoulder armor raised edge %s %02d'%(side,j),'trim',[
                (z-4.8,2.6,13.1,11.5),(z-3.8,3.7,13.7,11.5),
                (z+3.5,3.7,13.7,11.5),(z+4.5,2.6,13.1,11.5)],x=side*10)
            g.box('module latch %s %02d'%(side,j),'accent',(side*14.6,6.7,z),(1.1,3,3.2))
            for offset in (-3.2,3.2):
                _deck_drum(g,'armor captive fastener %s %02d %s'%(side,j,offset),
                           'trim',side*11,13.8,z+offset,.65,.55,n=6)
        g.loft('central deck access module %02d'%j,'base',[
            (z-5.8,4.1,11.1,7),(z-4.7,5.2,12,7),
            (z+4.4,5.2,12,7),(z+5.5,4.1,11.1,7)])
        g.loft('ventral replaceable armor module %02d'%j,'base',[
            (z-5.4,4.5,-6,-8.2),(z-4.4,5.5,-5.5,-9.2),
            (z+4.4,5.5,-5.5,-9.2),(z+5.4,4.5,-6,-8.2)])

    for side in (-1,1):
        x=side*23
        # Permanent crossheads visibly intersect spine and machinery casings.
        for j,z in enumerate((-51,-24,8,30)):
            g.loft('load bearing lateral crosshead %s %02d'%(side,j),'dark',[
                (z-3,13,5,-3),(z-2,14,6,-4),(z+2,14,6,-4),(z+3,13,5,-3)],x=side*17)
            g.box('crosshead upper strap %s %02d'%(side,j),'trim',(side*17,5.7,z),(24,1.5,2.4))
        g.loft('outboard drive armored machinery case %s'%side,'base',[
            (-69,6.2,7,-5),(-65,8.2,10,-7),(-51,9,11,-8),
            (-32,9,11,-8),(-23,7.3,9,-6),(-19,5.3,6,-4)],x=x)
        g.loft('connected lateral mission pod %s'%side,'base',[
            (-2,4.6,6,-4),(2,6.6,9,-5),(12,7.5,10,-5),
            (26,7.5,10,-5),(35,6.5,8,-4),(39,4.5,5,-2)],x=x)
        g.loft('mission pod dorsal stepped armor %s'%side,'trim',[
            (5,4.5,10,7),(8,5.9,11.5,7),(26,5.9,11.5,7),(31,4.5,9.5,6)],x=x)
        g.box('mission pod registry band %s'%side,'accent',(x,10.9,19),(7.5,1.3,7))
        for j,z in enumerate((7,17,27)):
            g.box('mission pod outer recessed hatch %s %02d'%(side,j),'dark',
                  (x+side*7.1,2,z),(1,6,6.5))
            g.box('mission pod hatch brace %s %02d'%(side,j),'trim',
                  (x+side*7.55,2,z),(.7,4.6,1.1))
        # Open waist service gantry, with actual triangular trusses and pipework.
        # Its aft end penetrates the drive pod; forward end penetrates mission pod.
        for y in (-1,7):
            g.box('service frame longitudinal rail %s %s'%(side,y),'trim',
                  (x,y,-10.5),(2.4,1.4,27))
        for j in range(4):
            z=-23+j*7
            g.box('service gantry upright %s %02d'%(side,j),'base',(x,3,z),(2.7,8.7,1.5))
            if j<3:
                _beam(g,'service gantry rising diagonal %s %02d'%(side,j),'trim',
                      (x,-.8,z),(x,7,z+7),1.0,1.5)
                _beam(g,'service gantry falling diagonal %s %02d'%(side,j),'dark',
                      (x,7,z),(x,-.8,z+7),.85,1.35)
        for dx in (-2,2):
            g.box('attached service conduit %s %s'%(side,dx),'accent',
                  (x+dx,2,-10.5),(1.1,1.2,27))
        # Large cooling fins are attached to the pod top, not floating slivers.
        for j in range(8):
            z=-62+j*4.5
            g.loft('machinery heat exchanger fin %s %02d'%(side,j),'dark',[
                (z-.85,5.6,11.4,8),(z-.35,6.4,13,8),(z+.8,5.6,11.4,8)],x=x)
            g.box('heat exchanger edge cap %s %02d'%(side,j),'trim',
                  (x,12.3,z),(9.8,.75,.85))
        # Negative-Z exhaust: every opaque loft ends at -69 or forward.
        # The hollow rings extend aft; emissive faces live inside their bores,
        # in front of the opaque machinery cap along an aft-view sight ray.
        g.ring('hollow open drive nozzle %s'%side,'dark',x,1,[
            (aft,7.1,5.85),(aft+1.2,7.8,6.1),(-76,8,5.7),
            (-72,6.8,5.2),(-68.6,6.4,4.9)],n=24)
        g.ring('nozzle mouth rolled metal rim %s'%side,'trim',x,1,[
            (aft+.08,7.2,5.86),(aft+.85,7.65,6.06)],n=24)
        g.disc('exposed cyan drive emitter %s'%side,'cool',x,1,aft+2.3,5.45,.3,n=24)
        for j,z in enumerate((-75,-72,-69)):
            g.ring('drive casing circumferential rib %s %02d'%(side,j),'base',x,1,[
                (z-.55,7.7,6.9),(z+.55,7.7,6.9)],n=12)
        for j in range(8):
            angle=j*math.pi/4
            xx=x+7.15*math.cos(angle); yy=1+7.15*math.sin(angle)
            g.box('drive casing tension lug %s %02d'%(side,j),'accent',
                  (xx,yy,-73.8),(1,1,3.2))

    # Low, broad escort gun mounts: hull-integrated rather than tower turrets.
    for j,(x,z) in enumerate(((-20,51),(20,51),(-9,-33),(9,-33))):
        y=15.1 if z>0 else 13.1
        _deck_drum(g,'escort gun armored bearing %02d'%j,'dark',x,y,z,3.7,1.8,n=16)
        g.loft('escort gun low armored mantlet %02d'%j,'base',[
            (z-3.1,2.1,y+2.2,y),(z-1.8,3.2,y+3.7,y),
            (z+2.5,2.7,y+3,y),(z+3.1,2,y+1.9,y)],x=x)
        for side in (-1,1):
            g.box('escort twin barrel %02d %s'%(j,side),'dark',
                  (x+side*1.4,y+2,z+4.4),(.9,.9,6.2))
            g.box('escort barrel muzzle %02d %s'%(j,side),'trim',
                  (x+side*1.4,y+2,z+7.3),(1.2,1.2,.9))
        g.box('escort mount fire control optic %02d'%j,'lit',(x,y+3.2,z+2.6),(.9,.8,.45))

    # Broad bow rescue/docking doors and their physical framing.
    for j in range(5):
        x=(j-2)*8
        g.box('bow modular docking door %02d'%j,'dark',(x,4.3,fore-.24),(6,5.4,.24))
        g.box('bow door cross rib %02d'%j,'trim',(x,4.3,fore-.08),(5.4,.9,.16))
        g.box('bow door status light %02d'%j,'lit',(x,6.2,fore-.09),(2.8,.45,.18))
