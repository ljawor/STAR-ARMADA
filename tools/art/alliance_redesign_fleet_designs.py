"""Nine naval/modular Alliance hulls. Pure geometry; no scene or export ownership.

Local design coordinates are an envelope, not a post-export fitting operation:
X beam, Y up, Z forward, each in [-1, 1]. The caller supplies native bounds.
Pressure spines, blunt crossheads and replaceable machinery follow the frigate.
"""
import math

KINDS = ('fighter', 'bomber', 'corvette', 'cruiser', 'battleship',
         'supercapital', 'constructor', 'colonizer', 'convoy')


class _Design:
    def __init__(self, g, frame):
        self.g = g
        self.center = frame['center']
        self.half = [s * .4995 for s in frame['span']]

    def mesh(self, name, role, vertices, faces):
        return self.g.mesh(name, role, [tuple(self.center[i] + p[i]*self.half[i]
                                            for i in range(3)) for p in vertices], faces)

    def box(self, name, role, pos, size):
        vertices = [tuple(pos[i]+s[i]*size[i]/2 for i in range(3))
                    for s in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                              (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        return self.mesh(name, role, vertices,
                         [(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)])

    def loft(self, name, role, stations, x=0):
        vertices = []
        for z,w,t,b in stations:
            c = min((t-b)*.24, w*.3)
            vertices.extend(((x-w+c,t,z),(x+w-c,t,z),(x+w,t-c,z),
                             (x+w,b+c,z),(x+w-c,b,z),(x-w+c,b,z),
                             (x-w,b+c,z),(x-w,t-c,z)))
        faces = [tuple(reversed(range(8))),tuple(range(len(vertices)-8,len(vertices)))]
        faces.extend((k*8+j,k*8+(j+1)%8,(k+1)*8+(j+1)%8,(k+1)*8+j)
                     for k in range(len(stations)-1) for j in range(8))
        return self.mesh(name,role,vertices,faces)

    def ring(self, name, role, x, y, stations, n=12):
        vertices=[]; faces=[]
        for z,outer,inner in stations:
            for r in (outer,inner):
                vertices.extend((x+r*math.cos(j*2*math.pi/n),
                                 y+r*math.sin(j*2*math.pi/n),z) for j in range(n))
        for k in range(len(stations)-1):
            for wall in (0,1):
                a=k*2*n+wall*n; b=(k+1)*2*n+wall*n
                faces.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
        for k in (0,len(stations)-1):
            a=k*2*n
            faces.extend((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n) for j in range(n))
        return self.mesh(name,role,vertices,faces)

    def emitter(self, name, x, y, z, r, n=12):
        vertices=[(x+r*math.cos(j*2*math.pi/n),y+r*math.sin(j*2*math.pi/n),z+d*.004)
                  for d in (-1,1) for j in range(n)]
        faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]
        faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
        self.mesh(name,'cool',vertices,faces)

    def beam(self,name,role,a,b,width):
        delta=[b[i]-a[i] for i in range(3)]
        norm=math.sqrt(sum(d*d for d in delta)); d=[v/norm for v in delta]
        ref=(0,1,0) if abs(d[1])<.9 else (1,0,0)
        u=[d[1]*ref[2]-d[2]*ref[1],d[2]*ref[0]-d[0]*ref[2],d[0]*ref[1]-d[1]*ref[0]]
        norm=math.sqrt(sum(v*v for v in u)); u=[v/norm for v in u]
        v=[d[1]*u[2]-d[2]*u[1],d[2]*u[0]-d[0]*u[2],d[0]*u[1]-d[1]*u[0]]
        vertices=[tuple(p[i]+width*(su*u[i]+sv*v[i])/2 for i in range(3))
                  for p in (a,b) for su,sv in ((-1,-1),(1,-1),(1,1),(-1,1))]
        self.mesh(name,role,vertices,[(3,2,1,0),(4,5,6,7),(0,1,5,4),
                                    (1,2,6,5),(2,3,7,6),(3,0,4,7)])


def _drive(d, x, index, r=.16, y=-.25, forward=-.34):
    """Emitter intersects bore wall, aft of the opaque machinery end cap."""
    tag=str(index)
    length=forward+.79
    d.loft('drive machinery '+tag,'base',[
        (-.79,r,.02,-.53),(-.79+length*.25,r*1.12,.08,-.56),
        (-.79+length*.8,r*1.12,.08,-.56),(forward,r,.02,-.53)],x=x)
    d.ring('open exhaust throat '+tag,'dark',x,y,
           [(-1,r,r*.73),(-.94,r*1.06,r*.76),(-.78,r*.95,r*.72)])
    d.ring('exhaust rolled lip '+tag,'trim',x,y,[(-.998,r*1.01,r*.73),(-.973,r*1.035,r*.73)])
    d.emitter('visible recessed drive emitter '+tag,x,y,-.925,r*.8)
    for j in range(4):
        z=-.79+length*(.3+j*.14)
        d.box('drive radiator '+tag+' '+str(j),'dark',(x,.075,z),(r*1.6,.045,.035))


def _bridge(d, z, width=.26, bottom=.25, top=1.0, name='naval bridge'):
    d.loft(name+' plinth','base',[(z-.14,width*.8,bottom+.12,bottom-.1),
                                 (z-.1,width,bottom+.2,bottom-.1),
                                 (z+.12,width,bottom+.2,bottom-.1)])
    d.loft(name+' crown','base',[(z-.1,width*.66,top-.1,bottom+.1),
                                (z-.06,width*.82,top,bottom+.1),
                                (z+.1,width*.82,top,bottom+.1)])
    for j in range(5):
        x=(j-2)*width*.27
        d.box(name+' window gasket '+str(j),'dark',(x,top-.12,z+.102),(width*.24,.12,.018))
        d.box(name+' glazing '+str(j),'cool',(x,top-.12,z+.114),(width*.18,.075,.01))
    d.box(name+' roof registry','accent',(0,top-.004,z),(width,.008,.065))


def _service(d, rows, x=.21, top=.3, start=-.5, step=.12):
    """Each replaceable armor cassette has a latch and a real raised vent bank."""
    for side in (-1,1):
        for j in range(rows):
            z=start+j*step; xx=side*x; tag=str(side)+' '+str(j)
            d.loft('replaceable armor cassette '+tag,'base',[
                (z-.045,.075,top,top-.1),(z-.035,.09,top+.035,top-.1),
                (z+.035,.09,top+.035,top-.1),(z+.045,.075,top,top-.1)],x=xx)
            d.box('cassette service latch '+tag,'accent',(xx,top+.038,z-.026),(.075,.018,.018))
            for k in range(3):
                d.box('cassette cooling louvre '+tag+' '+str(k),'dark',
                      (xx,top+.04,z-.005+k*.014),(.12,.014,.007))
            d.box('cassette edge keeper '+tag,'trim',(xx+side*.079,top+.018,z),(.014,.035,.065))


def _panel(d, tag, x, z, width, length, deck, rise=.1):
    """Broad chamfered armor, inset maintenance well and attached raised louvres.

    The dark reveal is a substantial exposed border, not a coplanar seam.
    All equipment roots penetrate its host; dimensions are local envelope units.
    """
    d.box(tag+' service trench','dark',(x,deck+.012,z),(width,.04,length))
    d.loft(tag+' broad functional panel','base',[
        (z-length*.46,width*.40,deck+rise*.65,deck),
        (z-length*.35,width*.47,deck+rise,deck),
        (z+length*.35,width*.47,deck+rise,deck),
        (z+length*.46,width*.40,deck+rise*.65,deck)],x=x)
    d.box(tag+' maintenance well','dark',(x,deck+rise+.004,z),
          (width*.62,.018,length*.48))
    for k in range(5):
        d.box(tag+' raised heat exchanger '+str(k),'trim',
              (x,deck+rise+.022,z+(k-2)*length*.075),
              (width*.53,.035,length*.034))
    for side in (-1,1):
        d.box(tag+' armored hinge '+str(side),'trim',
              (x+side*width*.34,deck+rise*.9,z),(.025,.045,length*.55))
    d.box(tag+' identification tab','accent',(x,deck+rise+.009,z+length*.32),
          (width*.48,.018,length*.09))


def _side_equipment(d, tag, side, x, z, top, bottom, length):
    """Deep side-mounted radiator pod with ribs and a visible armored fairing."""
    d.loft(tag+' machinery fairing','trim',[
        (z-length/2,.035,top-.05,bottom+.05),
        (z-length*.34,.065,top,bottom),
        (z+length*.34,.065,top,bottom),
        (z+length/2,.035,top-.05,bottom+.05)],x=side*x)
    d.box(tag+' radiator recess','dark',(side*(x+.063),(top+bottom)/2,z),
          (.015,(top-bottom)*.7,length*.6))
    for k in range(5):
        d.box(tag+' radiator rib '+str(k),'base',
              (side*(x+.075),(top+bottom)/2,z+(k-2)*length*.11),
              (.028,(top-bottom)*.65,length*.035))


def _hull(d, width=.34, top=.3, nose=.3):
    d.loft('continuous naval pressure spine','dark',[
        (-.79,width*.75,top-.08,-.62),(-.6,width,top,-.68),
        (.35,width,top,-.68),(.8,nose,top,-.54),(1,nose*.85,top-.08,-.44)])
    d.loft('deep armored keel','base',[(-.63,.12,-.5,-.84),(-.45,.16,-.5,-1),
                                       (.42,.16,-.5,-1),(.73,.12,-.4,-.7)])


def _fighter(d):
    _hull(d,.22,.28,.14)
    d.box('twinboom load bearing wing','base',(0,-.05,-.14),(2,.22,.26))
    for side in (-1,1):
        d.loft('fighter twinboom '+str(side),'base',[
            (-.78,.15,.08,-.45),(-.6,.18,.18,-.5),(.55,.14,.1,-.36),(.92,.09,.02,-.25)],x=side*.72)
        d.box('boom cannon '+str(side),'dark',(side*.72,-.1,.79),(.08,.08,.38))
        _drive(d,side*.72,side,r=.17)
    _bridge(d,.3,.2,.24,1,'fighter canopy')
    _service(d,3,.18,.29,start=-.49,step=.22)


def _bomber(d):
    _hull(d,.4,.28,.33)
    d.box('heavy weapons load crosshead','base',(0,-.12,-.1),(2,.3,.36))
    for side in (-1,1):
        d.loft('heavy torpedo magazine '+str(side),'base',[
            (-.45,.24,-.05,-.72),(-.3,.27,0,-.8),(.6,.27,0,-.8),(.85,.22,-.08,-.7)],x=side*.65)
        for j in range(3):
            x=side*.65+(j-1)*.12
            d.ring('open torpedo launch tube '+str(side)+' '+str(j),'trim',x,-.38,
                   [(.84,.055,.04),(.9,.055,.04)],n=8)
        _drive(d,side*.56,side,r=.2)
    _bridge(d,.27,.28,.25,1,'bomber armored cockpit')
    _service(d,3,.25,.29,start=-.49,step=.26)


def _corvette(d):
    _hull(d,.3,.28,.38)
    d.box('blockade runner engine transom','base',(0,-.25,-.59),(2,.72,.28))
    for j,x in enumerate((-.76,-.38,0,.38,.76)):
        _drive(d,x,j,r=.155)
    d.loft('runner blunt forward crosshead','base',[(.58,.32,.32,-.4),(.7,.57,.45,-.45),
                                                         (.91,.57,.4,-.4),(1,.42,.28,-.3)])
    _bridge(d,.44,.25,.28,1,'runner pilothouse')
    _service(d,7,.22,.29,start=-.38,step=.12)
    for side in (-1,1):
        d.loft('runner transom raised armor '+str(side),'base',
               [(-.68,.16,.21,.1),(-.64,.21,.27,.1),(-.5,.21,.27,.1),
                (-.46,.16,.21,.1)],x=side*.63)
        d.box('runner transom intake '+str(side),'dark',(side*.63,.275,-.57),(.25,.025,.1))
        d.box('runner transom latch '+str(side),'accent',(side*.63,.29,-.53),(.13,.025,.025))


def _cruiser(d):
    _hull(d,.4,.3,.48)
    for side in (-1,1):
        d.loft('liberty broad shoulder '+str(side),'base',[
            (-.48,.22,.32,-.5),(-.2,.31,.45,-.6),(.55,.31,.45,-.6),(.76,.26,.3,-.48)],x=side*.61)
        d.box('shoulder registry '+str(side),'accent',(side*.65,.451,.28),(.32,.015,.12))
        _drive(d,side*.58,side,r=.2)
    _bridge(d,.2,.29,.3,1,'liberty bridge')
    _service(d,10,.58,.45,start=-.19,step=.08)
    for side in (-1,1):
        for j,z in enumerate((-.08,.22,.5)):
            _panel(d,'liberty shoulder armor '+str(side)+' '+str(j),
                   side*.79,z,.3,.25,.45,.12 if j!=1 else .17)
            _side_equipment(d,'liberty flank '+str(side)+' '+str(j),
                            side,.91,z,.21,-.43,.23)
        _panel(d,'liberty forecastle '+str(side),side*.19,.74,.32,.3,.3,.12)
        d.loft('liberty raised gun platform '+str(side),'trim',
               [(.28,.12,.57,.3),(.34,.16,.68,.3),(.49,.15,.68,.3)],x=side*.34)
        for k in (-1,1):
            d.box('liberty heavy barrel '+str(side)+' '+str(k),'dark',
                  (side*.34+k*.055,.61,.58),(.045,.055,.32))


def _battleship(d):
    _hull(d,.49,.32,.56)
    for side in (-1,1):
        d.loft('command cruiser armor bank '+str(side),'base',[
            (-.64,.22,.4,-.7),(-.5,.25,.5,-.75),(.54,.25,.5,-.75),(.72,.24,.32,-.6)],x=side*.68)
        for j in range(5):
            z=-.37+j*.19
            d.loft('broadside gun casemate '+str(side)+' '+str(j),'trim',
                   [(z-.06,.13,.61,.43),(z-.04,.16,.69,.43),(z+.06,.14,.61,.43)],x=side*.67)
            for dx in (-.065,.065):
                d.box('casemate barrel '+str(side)+' '+str(j)+' '+str(dx),'dark',
                      (side*.67+dx,.57,z+.12),(.045,.045,.22))
        _drive(d,side*.6,side,r=.22)
    _bridge(d,.08,.36,.3,1,'command cruiser bridge')
    _service(d,9,.3,.32,start=-.54,step=.12)
    for side in (-1,1):
        for j,z in enumerate((-.4,-.12,.16,.44)):
            _panel(d,'command outer armor '+str(side)+' '+str(j),
                   side*.87,z,.24,.245,.5,.12+(j%2)*.045)
            _side_equipment(d,'command flank machinery '+str(side)+' '+str(j),
                            side,.91,z,.24,-.56,.23)
            d.loft('command gun platform tier '+str(side)+' '+str(j),'base',
                   [(z-.09,.19,.54,.46),(z-.065,.21,.59,.46),
                    (z+.08,.19,.59,.46)],x=side*.65)
        for j,z in enumerate((.64,.85)):
            _panel(d,'command forward armor '+str(side)+' '+str(j),
                   side*.24,z,.42,.18,.28,.14+j*.025)
        d.box('command longitudinal service alley '+str(side),'dark',
              (side*.47,.505,.02),(.055,.025,.97))
        for j,z in enumerate((-.35,0,.35)):
            d.beam('command armored cross brace '+str(side)+' '+str(j),'trim',
                   (side*.42,.52,z-.07),(side*.54,.55,z+.07),.035)


def _carrier(d):
    _hull(d,.27,.28,.4)
    # Side hangars have roof/floor, inboard pressure wall and end bulkheads.
    # There is deliberately NO exterior side wall, door slab or interior filler.
    for side in (-1,1):
        xx=side*.64
        d.box('empty sidehangar flight deck '+str(side),'base',(xx,-.63,.03),(.72,.16,1.42))
        d.box('empty sidehangar canopy '+str(side),'base',(xx,.32,.03),(.72,.16,1.42))
        for j,z in enumerate((-.68,.74)):
            d.box('hangar end bulkhead '+str(side)+' '+str(j),'dark',(xx,-.15,z),(.72,.96,.08))
        for j in range(7):
            z=-.57+j*.2
            d.box('hangar roof girder '+str(side)+' '+str(j),'trim',(xx,.22,z),(.7,.07,.04))
            d.box('hangar threshold stripe '+str(side)+' '+str(j),'accent',(side*.88,-.544,z),(.18,.012,.06))
            d.box('hangar ceiling lamp '+str(side)+' '+str(j),'lit',(side*.6,.18,z),(.15,.02,.04))
        _drive(d,side*.62,side,r=.22,forward=-.69)
    _bridge(d,-.15,.23,.28,1,'carrier island')
    _service(d,9,.18,.29,start=-.5,step=.14)
    for side in (-1,1):
        # Everything is above the solid canopy; the side aperture stays empty.
        for j,z in enumerate((-.5,-.17,.16,.49)):
            for lane in (0,1):
                _panel(d,'carrier roof armor '+str(side)+' '+str(j)+' '+str(lane),
                       side*(.46+lane*.34),z,.29,.29,.4,
                       .1+(.045 if (j+lane)%3==0 else 0))
        for j,z in enumerate((-.34,.32)):
            tag='carrier gantry '+str(side)+' '+str(j)
            for x in (.35,.93):
                d.box(tag+' foot '+str(x),'dark',(side*x,.48,z),(.06,.18,.08))
            d.beam(tag+' overhead truss','trim',(side*.35,.57,z),(side*.93,.57,z),.045)
            d.beam(tag+' diagonal','base',(side*.35,.42,z),(side*.61,.57,z),.035)
            d.box(tag+' crane trolley','accent',(side*.67,.59,z),(.12,.07,.1))
        d.loft('carrier aft service plant '+str(side),'trim',
               [(-.66,.21,.55,.4),(-.62,.25,.67,.4),(-.57,.24,.67,.4)],x=side*.64)
        for k in range(5):
            d.box('carrier plant radiator '+str(side)+' '+str(k),'dark',
                  (side*.64,.675,-.642+k*.014),(.33,.025,.007))
        for j,z in enumerate((-.48,.02,.52)):
            tag='carrier service alley machinery '+str(side)+' '+str(j)
            d.box(tag+' foundation','dark',(side*.63,.45,z),(.08,.12,.18))
            d.loft(tag+' pump casing','trim',
                   [(z-.07,.055,.6,.45),(z-.045,.075,.65,.45),
                    (z+.055,.075,.65,.45),(z+.08,.05,.59,.45)],x=side*.63)
            for k in (-1,1):
                d.beam(tag+' coolant feed '+str(k),'accent',
                       (side*(.63+k*.08),.5,z-.05),(side*(.63+k*.08),.6,z+.05),.025)
            d.box(tag+' access hatch','base',(side*.63,.655,z),(.08,.025,.06))


def _constructor(d):
    _hull(d,.22,.05,.18)
    d.box('engineering sled load deck','base',(0,-.48,.03),(2,.3,1.6))
    for side in (-1,1):
        x=side*.74
        d.box('crane pedestal '+str(side),'dark',(x,-.12,-.1),(.22,.55,.24))
        d.beam('engineering crane mast '+str(side),'trim',(x,-.15,-.1),(x,.94,-.26),.09)
        d.beam('engineering crane armature '+str(side),'base',(x,.94,-.26),(x,.9,.68),.12)
        d.beam('crane diagonal brace '+str(side),'accent',(x,.15,-.13),(x,.9,.38),.05)
        d.box('crane crown bearing '+str(side),'dark',(x,.94,-.26),(.18,.12,.18))
        d.box('crane hoist '+str(side),'trim',(x,.6,.65),(.045,.64,.045))
        d.box('attached grappler '+str(side),'accent',(x,.28,.65),(.2,.1,.12))
        _drive(d,side*.58,side,r=.19)
    _bridge(d,.61,.2,.04,.66,'engineering wheelhouse')
    _service(d,4,.35,-.3,start=-.46,step=.3)
    for side in (-1,1):
        d.loft('engineering deck winch '+str(side),'trim',
               [(.17,.12,-.15,-.34),(.2,.16,-.08,-.34),(.35,.16,-.08,-.34)],x=side*.46)
        d.box('engineering winch cable bed '+str(side),'dark',(side*.46,-.075,.27),(.2,.025,.08))


def _colonizer(d):
    _hull(d,.26,.2,.22)
    for side in (-1,1):
        d.box('habitat load arm '+str(side),'dark',(side*.5,-.2,0),(.8,.2,1.32))
        for j in range(3):
            z=-.43+j*.45; x=side*.7
            d.loft('colony habitat pressure module '+str(side)+' '+str(j),'base',[
                (z-.2,.23,.7,-.5),(z-.15,.3,.82,-.62),
                (z+.15,.3,.82,-.62),(z+.2,.23,.7,-.5)],x=x)
            for k in range(4):
                d.box('habitat daylight glazing '+str(side)+' '+str(j)+' '+str(k),'cool',
                      (x+(k-1.5)*.1,.823,z),(.07,.012,.19))
            d.box('habitat registry '+str(side)+' '+str(j),'accent',(x,.83,z+.12),(.35,.025,.04))
        _drive(d,side*.52,side,r=.2)
    _bridge(d,.67,.25,.2,1,'colony navigation')
    _service(d,6,.19,.21,start=-.5,step=.18)
    for side in (-1,1):
        for z in (-.43,.02,.47):
            d.box('habitat roof air recycler '+str(side)+' '+str(z),'dark',
                  (side*.7,.84,z-.12),(.32,.055,.08))
            d.box('habitat recycler cap '+str(side)+' '+str(z),'trim',
                  (side*.7,.87,z-.12),(.24,.035,.055))


def _convoy(d):
    _hull(d,.21,.17,.27)
    d.box('cargo backbone cross deck','dark',(0,-.3,-.06),(1.8,.23,1.48))
    for side in (-1,1):
        for j in range(4):
            z=-.57+j*.35; x=side*.66
            d.loft('convoy cargo module '+str(side)+' '+str(j),'base',[
                (z-.15,.28,.55,-.63),(z-.12,.34,.66,-.73),
                (z+.12,.34,.66,-.73),(z+.15,.28,.55,-.63)],x=x)
            for k in (-1,1):
                d.box('container restraint '+str(side)+' '+str(j)+' '+str(k),'trim',
                      (x,.66,z+k*.09),(.58,.035,.025))
            d.box('container registry '+str(side)+' '+str(j),'accent',(x,.67,z),(.3,.025,.08))
        _drive(d,side*.55,side,r=.2)
    _bridge(d,.73,.24,.16,1,'transport pilothouse')
    _service(d,5,.16,.18,start=-.54,step=.21)
    for side in (-1,1):
        for j in range(4):
            z=-.57+j*.35
            d.box('cargo roof access well '+str(side)+' '+str(j),'dark',
                  (side*.66,.68,z),(.43,.045,.14))
            for k in (-1,1):
                d.box('cargo stacking shoe '+str(side)+' '+str(j)+' '+str(k),'base',
                      (side*.66+k*.22,.7,z),(.07,.09,.16))


_BUILDERS = dict(zip(KINDS, (_fighter,_bomber,_corvette,_cruiser,_battleship,
                            _carrier,_constructor,_colonizer,_convoy)))


def build(kind, g, frame):
    """Build exactly one manifest kind into an existing six-role mesh facade."""
    if kind not in _BUILDERS:
        raise ValueError('Unsupported Alliance fleet kind: '+str(kind))
    if len(frame['span']) != 3 or any(s <= 0 for s in frame['span']):
        raise ValueError('Fleet frame requires three positive native spans')
    d=_Design(g,frame)
    _BUILDERS[kind](d)
    # Attached docking status lamps: on the continuous blunt bow cap.
    for side in (-1,1):
        d.box('bow docking status '+str(side),'lit',(side*.07,.06,.999),(.07,.05,.002))
