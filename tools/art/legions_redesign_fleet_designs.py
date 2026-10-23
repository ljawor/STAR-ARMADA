"""Original Automated Legions fleet, authored offline as closed CPU meshes.

Independent normalized axes preserve each catalogue envelope, not naval proportions.
X is beam, Y is up and +Z is forward. No Blender, runtime or export ownership.
"""
import math

KINDS = ('fighter', 'bomber', 'corvette', 'frigate', 'cruiser', 'battleship',
         'supercapital', 'constructor', 'colonizer', 'convoy')


class _Design:
    def __init__(self, g, frame):
        self.g = g
        self.center = frame['center']
        self.half = tuple(s * .4995 for s in frame['span'])

    def mesh(self, name, role, verts, faces):
        self.g.mesh(name, role,
                    [tuple(self.center[i] + p[i] * self.half[i] for i in range(3))
                     for p in verts], faces)

    def prism(self, name, role, polygon, bottom, top, bevel=True):
        """A chamfered carapace with real side walls, not a surface decal."""
        cx = sum(p[0] for p in polygon) / len(polygon)
        cz = sum(p[1] for p in polygon) / len(polygon)
        cut = min((top - bottom) * .18, .035)
        rings = ((bottom, .90), (bottom+cut, 1), (top-cut, 1), (top, .90)) if bevel else ((bottom, 1), (top, 1))
        verts = [(cx+(x-cx)*s, y, cz+(z-cz)*s) for y, s in rings for x, z in polygon]
        n = len(polygon)
        faces = [tuple(reversed(range(n))), tuple(range(len(verts)-n, len(verts)))]
        faces += [(k*n+j, k*n+(j+1)%n, (k+1)*n+(j+1)%n, (k+1)*n+j)
                  for k in range(len(rings)-1) for j in range(n)]
        self.mesh(name, role, verts, faces)

    @staticmethod
    def outline(x, z, w, length):
        a, b = w/2, length/2
        c = min(a*.28, b*.28)
        return [(x-a+c,z-b), (x+a-c,z-b), (x+a,z-b+c), (x+a,z+b-c),
                (x+a-c,z+b), (x-a+c,z+b), (x-a,z+b-c), (x-a,z-b+c)]

    def block(self, name, role, x, z, w, length, bottom, top):
        self.prism(name, role, self.outline(x,z,w,length), bottom, top)

    def box(self, name, role, pos, size):
        x,y,z=pos; w,h,length=size
        self.prism(name,role,[(x-w/2,z-length/2),(x+w/2,z-length/2),
                             (x+w/2,z+length/2),(x-w/2,z+length/2)],y-h/2,y+h/2,False)

    def beam(self, name, role, a, b, width):
        delta=[b[i]-a[i] for i in range(3)]
        mag=math.sqrt(sum(t*t for t in delta)); v=[t/mag for t in delta]
        ref=(0,1,0) if abs(v[1]) < .9 else (1,0,0)
        u=[v[1]*ref[2]-v[2]*ref[1],v[2]*ref[0]-v[0]*ref[2],v[0]*ref[1]-v[1]*ref[0]]
        mag=math.sqrt(sum(t*t for t in u)); u=[t/mag for t in u]
        t=[v[1]*u[2]-v[2]*u[1],v[2]*u[0]-v[0]*u[2],v[0]*u[1]-v[1]*u[0]]
        verts=[tuple(p[i]+width*(su*u[i]+st*t[i])/2 for i in range(3))
               for p in (a,b) for su,st in ((-1,-1),(1,-1),(1,1),(-1,1))]
        self.mesh(name,role,verts,[(3,2,1,0),(4,5,6,7),(0,1,5,4),
                                  (1,2,6,5),(2,3,7,6),(3,0,4,7)])

    def tube(self, name, role, center, stations, axis='z', n=12):
        """Closed annular solid: never an opaque cylinder masquerading as a bore."""
        verts=[]
        for axial, outer, inner in stations:
            for radius in (outer,inner):
                for j in range(n):
                    u=radius*math.cos(j*2*math.pi/n); v=radius*math.sin(j*2*math.pi/n)
                    p=(u,v,axial) if axis == 'z' else (u,axial,v)
                    verts.append(tuple(center[i]+p[i] for i in range(3)))
        faces=[]
        for k in range(len(stations)-1):
            for wall in (0,1):
                a=k*2*n+wall*n; b=(k+1)*2*n+wall*n
                faces += [(a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n)]
        for k in (0,len(stations)-1):
            a=k*2*n
            faces += [(a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n) for j in range(n)]
        self.mesh(name,role,verts,faces)

    def disc(self, name, role, center, radius, depth, axis='z', n=12):
        verts=[]
        for a in (-depth/2,depth/2):
            for j in range(n):
                u=radius*math.cos(j*2*math.pi/n); v=radius*math.sin(j*2*math.pi/n)
                p=(u,v,a) if axis=='z' else (u,a,v)
                verts.append(tuple(center[i]+p[i] for i in range(3)))
        self.mesh(name,role,verts,[tuple(reversed(range(n))),tuple(range(n,2*n))]+
                  [(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)])

    def well(self, name, x, z, w, length, deck, rise=.16):
        """Broad raised armor with a genuinely sunken machinery pocket."""
        poly=self.outline(x,z,w,length); n=len(poly)
        rings=((deck-.025, .91), (deck+.02,1), (deck+rise, .90),
               (deck+rise, .63), (deck+rise*.38, .63))
        verts=[(x+(px-x)*s,y,z+(pz-z)*s) for y,s in rings for px,pz in poly]
        faces=[tuple(reversed(range(n))),tuple(range(4*n,5*n))]
        faces += [(k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j)
                  for k in range(4) for j in range(n)]
        self.mesh(name+' raised carapace','base',verts,faces)
        floor=deck+rise*.38
        self.box(name+' recessed machinery floor','dark',(x,floor+.005,z),(w*.43,.012,length*.48))
        for j in range(4):
            self.box(name+' radiator vane '+str(j),'trim',
                     (x,floor+rise*.15,z+(j-1.5)*length*.105),(w*.40,rise*.32,length*.035))
        self.box(name+' broad identity enamel','accent',
                 (x,deck+rise+.002,z-length*.38),(w*.42,.012,length*.095))
        for s in (-1,1):
            self.box(name+' hinge '+str(s),'trim',
                     (x+s*w*.42,deck+rise*.45,z),(w*.055,rise*.5,length*.42))


def _drive(d, name, x, y, r=.17, front=-.35):
    # The machinery cap ends at -.79; every emitter vertex is aft of -.91.
    d.block(name+' opaque machinery', 'base',x,(front-.79)/2,r*2.2,front+.79,y-r,y+r)
    d.tube(name+' open annular aperture','dark',(x,y,0),
           [(-1,r,r*.70),(-.96,r*1.08,r*.75),(-.79,r*.94,r*.70)])
    d.tube(name+' rolled rim','trim',(x,y,0),[(-.999,r*1.01,r*.70),(-.979,r*1.045,r*.70)])
    d.disc(name+' visible emitter','cool',(x,y,-.936),r*.76,.014)
    for k in range(4):
        z=-.70+(front+.70)*(k+.3)/4
        d.box(name+' heat sink '+str(k),'dark',(x,y+r+.014,z),(r*1.5,.034,.027))


def _sensor(d, name, x, z, deck, top, scale=.22):
    """Distributed robot eyes; no habitable bridge or window rows."""
    d.block(name+' processor root','dark',x,z,scale*2,scale*1.7,deck-.035,top-.13)
    for i,(dx,dz,r) in enumerate(((0,0,scale*.57),(-scale*.64,scale*.18,scale*.30),
                                  (scale*.64,scale*.18,scale*.30))):
        t=top if i==0 else top-.055
        d.tube(name+' eye socket '+str(i),'trim',(x+dx,0,z+dz),
               [(top-.15,r,r*.66),(t,r,r*.70)],axis='y')
        d.disc(name+' optic '+str(i),'lit',(x+dx,t-.035,z+dz),r*.73,.018,axis='y')


def _fighter(d):
    # Swept scythes are two joined blades per side, with an open aft crescent.
    d.block('autonomous thorax','base',0,-.02,.54,1.20,-.65,.34)
    d.block('ventral targeting keel','dark',0,.08,.27,.65,-1,-.48)
    for s in (-1,1):
        d.prism('scythe root '+str(s),'trim',[(s*.16,-.42),(s*.77,-.65),
                  (s*.93,-.29),(s*.58,.12),(s*.20,.30)],-.19,.09)
        d.prism('forward scythe blade '+str(s),'base',[(s*.58,-.21),(s*1.,-.12),
                  (s*.86,.59),(s*.57,1.),(s*.69,.20)],-.11,.24)
        d.well('wing actuator '+str(s),s*.61,-.25,.34,.36,.09,.16)
        d.well('blade armor '+str(s),s*.79,.25,.23,.38,.24,.13)
        _drive(d,'impulse '+str(s),s*.24,-.35,.15,-.33)
        d.beam('exposed wing tendon '+str(s),'dark',(s*.24,.20,-.19),(s*.66,.20,-.37),.065)
    _sensor(d,'flight consensus',0,.14,.32,1.,.23)
    d.well('thoracic armor',0,-.35,.38,.26,.34,.15)
    d.block('split target proboscis','base',0,.69,.18,.42,-.16,.18)
    d.box('ventral target aperture','lit',(0,-.78,.409),(.16,.16,.025))


def _bomber(d):
    d.block('bombing consensus bus','dark',0,-.12,.58,1.02,-.52,.38)
    d.block('hanging ordnance magazine','base',0,.08,.38,.66,-1,-.36)
    for s in (-1,1):
        x=s*.58; tag=str(s)
        d.beam('pod load bearing yoke '+tag,'trim',(0,-.10,-.24),(x,-.10,-.24),.26)
        d.block('armored weapon pod '+tag,'base',x,.04,.80,1.34,-.56,.34)
        for j,z in enumerate((-.35,.18)):
            d.well('pod blast lid '+tag+' '+str(j),x,z,.62,.44,.34,.19)
        d.tube('bomb accelerator muzzle '+tag,'trim',(x,-.10,0),
               [(.66,.24,.14),(.91,.24,.16),(1.,.20,.16)])
        d.disc('bomb accelerator breech '+tag,'lit',(x,-.10,.80),.17,.024)
        _drive(d,'heavy ion '+tag,x,-.12,.22,-.32)
        d.box('pod side recess '+tag,'dark',(x+s*.405,-.03,.06),(.018,.35,.65))
        for j in range(5):
            d.box('pod vertical radiator '+tag+' '+str(j),'trim',
                  (x+s*.405,-.03,-.19+j*.12),(.025,.29,.035))
    _sensor(d,'bomb targeting consensus',0,-.08,.36,1.,.22)
    d.well('bombing bus service armor',0,-.43,.35,.23,.38,.15)


def _corvette(d):
    d.block('drone thorax','base',0,-.37,1.35,.79,-.53,.28)
    d.block('drone ventral processor','dark',0,-.18,.40,.62,-1,-.38)
    for s in (-1,1):
        tag=str(s)
        d.prism('lateral recoil shoulder '+tag,'trim',[(s*.32,-.64),(s*.79,-.67),
                 (s*1.,-.36),(s*.73,-.12),(s*.32,-.20)],-.31,.14)
        d.prism('split jaw '+tag,'base',[(s*.22,-.18),(s*.76,-.21),
                 (s*.86,.61),(s*.50,1.),(s*.24,.63)],-.35,.20)
        d.well('jaw root armor '+tag,s*.50,.02,.42,.35,.20,.19)
        d.well('jaw blade armor '+tag,s*.56,.49,.34,.34,.20,.16)
        d.box('inner jaw track '+tag,'dark',(s*.255,-.05,.39),(.05,.30,.60))
        for j in range(4):
            d.box('inner jaw tooth '+tag+' '+str(j),'trim',
                  (s*.23,-.02,.18+j*.13),(.075,.13,.045))
        _drive(d,'drone drive '+tag,s*.43,-.29,.19,-.35)
        _sensor(d,'jaw consensus '+tag,s*.52,.28,.20,.59,.115)
    _sensor(d,'thorax consensus',0,-.40,.28,1.,.23)
    d.well('aft carapace',0,-.64,.43,.27,.28,.16)


def _flank(d, name, side, x, z, y, length=.40, height=.32):
    """Exposed side cooling bank with its own attached frame and solid fins."""
    d.box(name+' thermal bed','dark',(side*x,y,z),(.065,height,length))
    for j in range(6):
        d.box(name+' deep radiator '+str(j),'trim',
              (side*(x+.022),y,z+(j-2.5)*length*.14),(.07,height*.85,length*.052))
    for sign in (-1,1):
        d.box(name+' bolted frame '+str(sign),'base',
              (side*(x+.018),y+sign*height*.48,z),(.08,height*.08,length*1.03))


def _frigate(d):
    d.block('fork structural spine','dark',0,-.14,.44,1.40,-.56,.13)
    d.block('fork ventral inverter','base',0,-.25,.28,.67,-1,-.43)
    for s in (-1,1):
        tag=str(s)
        d.prism('fork swept shoulder '+tag,'base',[(s*.10,-.73),(s*.73,-.76),
                 (s*1.,-.43),(s*.66,-.15),(s*.15,-.24)],-.43,.20)
        d.beam('fork tension root '+tag,'trim',(s*.10,-.13,-.36),(s*.58,-.13,.45),.14)
        d.prism('fork forward tine '+tag,'dark',[(s*.35,-.37),(s*.72,-.40),
                 (s*.73,.76),(s*.48,1.),(s*.35,.60)],-.32,.12)
        for j,z in enumerate((-.29,.06,.41,.75)):
            x=s*(.53 if j<3 else .52)
            d.block('fork segment '+tag+' '+str(j),'base',x,z,.40,.30,-.35,.27)
            d.well('fork segmented carapace '+tag+' '+str(j),x,z,.34,.25,.27,.18)
        _flank(d,'fork flank '+tag,s,.70,.28,-.08,.55,.28)
        _drive(d,'fork impulse '+tag,s*.43,-.30,.21,-.30)
    for j,z in enumerate((-.48,-.08)):
        _sensor(d,'fork processor '+str(j),0,z,.13,1. if j==0 else .71,.20)
    d.well('rear hinge armor',0,-.60,.34,.28,.13,.18)


def _cruiser(d):
    # A chain of overlapping spinal vertebrae, not a single slab hull.
    d.block('continuous machine tendon','dark',0,-.02,.36,1.78,-.53,.18)
    d.block('cruiser hanging reactor','dark',0,-.34,.34,.74,-1,-.39)
    for j,z in enumerate((-.60,-.21,.18,.57)):
        width=(1.56,2.,1.73,1.25)[j]
        top=(.25,.35,.29,.19)[j]
        d.block('distributed vertebra '+str(j),'base',0,z,width-.12,.35,-.42,top)
        for s in (-1,1):
            tag=str(j)+' '+str(s); x=s*width*.29
            d.well('spinal armor '+tag,x,z,width*.36,.29,top,.20)
            _flank(d,'spinal radiator '+tag,s,width/2-.06,z,-.10,.26,.30)
        _sensor(d,'spinal consensus '+str(j),0,z,top,1. if j==1 else .73,.16)
    for s in (-1,1):
        _drive(d,'distributed drive '+str(s),s*.44,-.30,.20,-.38)
        d.prism('split machine proboscis '+str(s),'trim',[(s*.10,.55),(s*.45,.58),
                 (s*.34,.90),(s*.18,1.)],-.24,.15)
        d.well('forward accelerator armor '+str(s),s*.22,.71,.23,.29,.15,.13)


def _turret(d, name, x, z, deck, scale=1.):
    # A long mount penetrates the pocket floor below its raised armor surround.
    d.block(name+' rooted gun plinth','dark',x,z,.30*scale,.31*scale,deck-.20,deck+.09*scale)
    d.tube(name+' traversal collar','trim',(x,0,z),
           [(deck+.055*scale,.135*scale,.082*scale),
            (deck+.17*scale,.135*scale,.082*scale)],axis='y')
    d.block(name+' robotic receiver','base',x,z,.22*scale,.26*scale,deck+.08*scale,deck+.23*scale)
    for s in (-1,1):
        d.tube(name+' open accelerator '+str(s),'dark',(x+s*.057*scale,deck+.18*scale,z),
               [(.05*scale,.042*scale,.024*scale),(.38*scale,.042*scale,.026*scale)],n=8)
        d.disc(name+' firing core '+str(s),'lit',
               (x+s*.057*scale,deck+.18*scale,z+.29*scale),.029*scale,.012*scale,n=8)
    d.box(name+' armor tab','accent',(x,deck+.234*scale,z),(.15*scale,.012*scale,.10*scale))


def _battleship(d):
    # Broad interlocked bastions and stepped fortress plates, never a wedge.
    d.block('bastion interlocking foundation','dark',0,-.02,1.88,1.38,-.62,.12)
    d.block('bastion axial reactor','base',0,-.18,.47,1.03,-1,.28)
    d.block('bastion raised central casemate','base',0,-.06,.91,1.10,.06,.40)
    for s in (-1,1):
        for j,z in enumerate((-.39,.26)):
            tag=str(s)+' '+str(j)
            d.block('fortress load block '+tag,'base',s*.70,z,.48,.57,-.43,.43)
            d.well('fortress broad armor '+tag,s*.70,z,.51,.47,.43,.24)
            _flank(d,'fortress wall radiator '+tag,s,.94,z,-.02,.45,.43)
            _turret(d,'bastion battery '+tag,s*.70,z,.67,.70)
        d.prism('machine ram '+str(s),'base',[(s*.21,.46),(s*.61,.46),
                 (s*.68,.85),(s*.40,1.),(s*.23,.85)],-.40,.22)
        d.well('ram armor '+str(s),s*.42,.70,.30,.35,.22,.22)
        for j,z in enumerate((-.37,.12)):
            d.well('central fortress panel '+str(s)+' '+str(j),s*.24,z,.36,.37,.40,.24)
        for j,x in enumerate((.23,.66)):
            _drive(d,'bastion drive '+str(s)+' '+str(j),s*x,-.42,.16,-.35)
    _sensor(d,'bastion command consensus',0,-.12,.40,1.,.23)
    for s in (-1,1):
        _sensor(d,'fore consensus '+str(s),s*.40,.58,.22,.72,.13)
        _turret(d,'forward denial '+str(s),s*.25,.20,.64,.70)


def _supercapital(d):
    # Two literal open launch channels at X +/-.33. There is NO floor under them.
    d.block('rear carrier crosshead','dark',0,-.65,1.82,.32,-.62,.24)
    d.block('lance continuous support','dark',0,.08,.28,1.84,-.57,.20)
    d.block('lance reactor keel','base',0,-.38,.24,.58,-1,-.43)
    for s in (-1,1):
        tag=str(s)
        d.block('outer carrier machine hull '+tag,'base',s*.73,.04,.42,1.56,-.48,.30)
        for j,z in enumerate((-.49,-.13,.23,.59)):
            d.well('carrier fortress panel '+tag+' '+str(j),s*.73,z,.44,.30,.30,.25)
            _flank(d,'carrier radiator '+tag+' '+str(j),s,.94,z,-.08,.27,.41)
        # Rails remain entirely on the walls; space between them is physically empty.
        d.box('inner launch rail '+tag,'trim',(s*.50,-.03,.12),(.10,.14,1.25))
        for j,z in enumerate((-.35,.03,.41)):
            d.box('launch guidance light '+tag+' '+str(j),'cool',
                  (s*.455,-.025,z),(.016,.055,.16))
        _drive(d,'carrier outer drive '+tag,s*.72,-.30,.21,-.41)
        _drive(d,'carrier axial drive '+tag,s*.12,-.43,.10,-.39)
        for j,z in enumerate((-.44,.23)):
            _turret(d,'carrier denial '+tag+' '+str(j),s*.73,z,.55,.72)
        _sensor(d,'carrier distributed processor '+tag,s*.73,-.24,.30,.84,.15)
    for j,z in enumerate((-.43,-.13,.17,.47)):
        d.well('lance segmented spine '+str(j),0,z,.24,.25,.20,.22)
    _sensor(d,'lance firing consensus',0,-.42,.42,1.,.13)
    for s in (-1,1):
        d.block('forward lance jaw '+str(s),'trim',s*.071,.73,.085,.54,-.15,.29)
        d.box('lance field coil '+str(s),'accent',(s*.086,.30,.73),(.04,.026,.33))
    d.box('lance recessed firing core','lit',(0,.055,.89),(.045,.22,.025))


def _constructor(d):
    d.block('spider robotic abdomen','base',0,-.14,.76,.85,-.45,.32)
    d.block('spider tool magazine','dark',0,.03,.38,.62,-1,-.30)
    # Six articulated rigs. Feet touch the robot arm, never float as ornaments.
    for s in (-1,1):
        for j,z in enumerate((-.51,-.04,.43)):
            tag=str(s)+' '+str(j); fore=z+.13
            root_z=min(z,.23)
            root=(s*.29,-.02,root_z); knee=(s*.76,-.17,fore)
            toe=(s*.92,-.64,fore+.15)
            d.beam('spider upper rig '+tag,'base',root,knee,.13)
            d.beam('spider hydraulic ram '+tag,'trim',(s*.29,-.16,root_z+.04),
                   (s*.76,-.28,fore+.025),.060)
            d.block('spider knee '+tag,'dark',s*.76,fore,.24,.22,-.31,-.07)
            d.beam('spider lower rig '+tag,'trim',knee,toe,.095)
            d.block('spider gripper '+tag,'base',s*.91,fore+.17,.18,.20,-.77,-.58)
            d.box('spider tool face '+tag,'accent',(s*.91,-.776,fore+.17),(.12,.016,.10))
        _drive(d,'spider positioning drive '+str(s),s*.24,-.26,.15,-.39)
        d.well('spider broad shell '+str(s),s*.19,-.16,.32,.59,.32,.20)
    d.beam('forward assembly tool spine','dark',(0,-.10,.22),(0,-.10,.86),.16)
    for s in (-1,1):
        d.block('assembly mandible '+str(s),'trim',s*.13,.84,.15,.32,-.25,.08)
        d.box('assembly welder '+str(s),'lit',(s*.13,-.06,.996),(.09,.11,.008))
    _sensor(d,'spider tool consensus',0,-.14,.32,1.,.20)


def _colonizer(d):
    # A foundry barge: independent industrial hearths around a deep reactor trough.
    d.block('foundry load bearing raft','dark',0,-.03,1.87,1.62,-.61,-.18)
    d.block('foundry hanging smelter','base',0,-.15,.58,.98,-1,-.35)
    for s in (-1,1):
        tag=str(s)
        d.block('foundry machinery sill '+tag,'base',s*.65,.03,.58,1.44,-.42,.14)
        for j,z in enumerate((-.43,.04,.51)):
            label=tag+' '+str(j)
            d.block('raised foundry hearth '+label,'base',s*.65,z,.61,.39,.08,.46)
            d.well('foundry broad heat shield '+label,s*.65,z,.53,.33,.46,.22)
            _flank(d,'foundry radiator '+label,s,.94,z,-.08,.33,.33)
        _drive(d,'foundry heavy drive '+tag,s*.57,-.36,.22,-.34)
        d.block('landing tool ram '+tag,'trim',s*.61,.81,.26,.38,-.31,.15)
    d.block('foundry deep processing trench','dark',0,.13,.36,1.12,-.18,-.04)
    for j,z in enumerate((-.34,-.05,.24,.53)):
        d.tube('smelting cell rim '+str(j),'trim',(0,0,z),
               [(-.045,.14,.095),(.17,.14,.095)],axis='y')
        d.disc('visible smelting cell '+str(j),'lit',(0,.045,z),.105,.025,axis='y')
    d.block('foundry automation root','base',0,-.50,.36,.38,-.12,.52)
    _sensor(d,'foundry consensus',0,-.50,.52,1.,.17)
    for s in (-1,1):
        d.beam('foundry supported gantry '+str(s),'trim',
               (s*.40,.14,.04),(s*.40,.72,.04),.085)
    d.beam('foundry overhead manipulator rail','base',(-.44,.72,.04),(.44,.72,.04),.12)
    d.block('foundry attached tool head','accent',0,.04,.18,.20,.54,.73)


def _convoy(d):
    # Connected replaceable transport capsules, each with a visible mechanical neck.
    d.block('convoy armored coupling spine','dark',0,-.01,.31,1.83,-.45,.18)
    d.block('convoy ventral power stack','base',0,-.18,.27,.74,-1,-.33)
    for j,z in enumerate((-.49,.05,.59)):
        for s in (-1,1):
            tag=str(j)+' '+str(s); x=s*(.64 if j<2 else .52)
            d.beam('transport load neck '+tag,'trim',(0,-.08,z),(x,-.08,z),.17)
            d.block('transport pressure capsule '+tag,'base',x,z,.68 if j<2 else .64,.48,-.47,.32)
            d.well('transport access carapace '+tag,x,z,.59,.39,.32,.20)
            d.box('transport side service inset '+tag,'dark',
                  (x+s*(.344 if j<2 else .324),-.04,z),(.014,.28,.29))
            d.box('transport side broad registry '+tag,'accent',
                  (x+s*(.350 if j<2 else .330),-.04,z),(.018,.15,.21))
        d.block('convoy coupling collar '+str(j),'trim',0,z,.39,.16,-.27,.26)
    for s in (-1,1):
        _drive(d,'convoy thrust cluster '+str(s),s*.43,-.29,.18,-.37)
    d.block('convoy sensor nose','base',0,.80,.35,.40,-.17,.37)
    _sensor(d,'convoy route consensus',0,.73,.37,1.,.18)
    d.box('nose scanning aperture','lit',(0,.03,.997),(.20,.12,.004))


_BUILDERS = dict(zip(KINDS, (_fighter,_bomber,_corvette,_frigate,_cruiser,
                           _battleship,_supercapital,_constructor,_colonizer,_convoy)))


def build(kind, g, frame):
    if kind not in _BUILDERS:
        raise ValueError('unknown Legions fleet kind: '+str(kind))
    _BUILDERS[kind](_Design(g,frame))
