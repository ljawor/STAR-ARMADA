"""Original Automated Legions hardware: rooted industrial robotic architecture.

CPU-authorable closed solids only. X is beam, Y is up, +Z is forward.
Recipes use [-1,1] coordinates mapped to center + .499 * span * coordinate.
No Blender imports, modifiers, runtime classes, or material substitutions.
"""
import math

KINDS = ('defense_satellite', 'attack_satellite', 'planet_extractor', 'planet_trade_hub',
         'planet_shield_generator', 'planet_pulsar_cannon')


class _Machine:
    def __init__(self, g, frame):
        self.g, self.frame, self.serial = g, frame, 0

    def mesh(self, name, role, vertices, faces):
        self.serial += 1
        world = [tuple(self.frame['center'][i]+.499*self.frame['span'][i]*v[i]
                       for i in range(3)) for v in vertices]
        self.g.mesh(f'{name} {self.serial:03}',role,world,faces)

    def block(self, name, role, center, size):
        """Eight-sided pressure casing with broad corner cuts, not a bevel modifier."""
        x,y,z = center
        a,b,c = (s/2 for s in size)
        cut = min(a,b)*.3
        outline = [(-a+cut,-b),(a-cut,-b),(a,-b+cut),(a,b-cut),
                   (a-cut,b),(-a+cut,b),(-a,b-cut),(-a,-b+cut)]
        vv = [(x+u,y+v,z+w) for w in (-c,c) for u,v in outline]
        ff = [tuple(reversed(range(8))),tuple(range(8,16))]
        ff += [(j,(j+1)%8,(j+1)%8+8,j+8) for j in range(8)]
        self.mesh(name,role,vv,ff)

    def tube(self, name, role, center, radius, depth, axis='z', bore=0, n=12):
        """A real through-bore or capped rotational machine component."""
        def point(u,v,w):
            p = {'x':(w,u,v),'y':(v,w,u),'z':(u,v,w)}[axis]
            return tuple(center[i]+p[i] for i in range(3))
        radii = (radius,bore) if bore else (radius,)
        vv = [point(r*math.cos(j*2*math.pi/n),r*math.sin(j*2*math.pi/n),w)
              for w in (-depth/2,depth/2) for r in radii for j in range(n)]
        step = len(radii)*n
        ff = [(j,(j+1)%n,step+(j+1)%n,step+j) for j in range(n)]
        if bore:
            ff += [(n+j,step+n+j,step+n+(j+1)%n,n+(j+1)%n) for j in range(n)]
            ff += [(j,n+j,n+(j+1)%n,(j+1)%n) for j in range(n)]
            ff += [(step+j,step+(j+1)%n,step+n+(j+1)%n,step+n+j) for j in range(n)]
        else:
            ff += [tuple(reversed(range(n))),tuple(range(n,2*n))]
        self.mesh(name,role,vv,ff)

    def panel(self, name, role, center, size):
        """Flat-edged machinery beds/louvres: spend bevels on armor, not strips."""
        vv = [tuple(center[i]+sign[i]*size[i]/2 for i in range(3))
              for sign in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                           (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        self.mesh(name, role, vv, [(3,2,1,0),(4,5,6,7),(0,1,5,4),
                                  (1,2,6,5),(2,3,7,6),(3,0,4,7)])

    def beam(self, name, role, start, end, width, depth):
        """Chamfered articulated structural link, endpoints embedded in bearings."""
        direction = [end[i]-start[i] for i in range(3)]
        length = math.sqrt(sum(v*v for v in direction))
        w = [v/length for v in direction]
        ref = (0,0,1) if abs(w[2]) < .9 else (0,1,0)
        u = [ref[1]*w[2]-ref[2]*w[1],ref[2]*w[0]-ref[0]*w[2],ref[0]*w[1]-ref[1]*w[0]]
        norm = math.sqrt(sum(v*v for v in u)); u = [v/norm for v in u]
        v = [w[1]*u[2]-w[2]*u[1],w[2]*u[0]-w[0]*u[2],w[0]*u[1]-w[1]*u[0]]
        a,b = width/2,depth/2
        cut = min(a,b)*.3
        outline = [(-a+cut,-b),(a-cut,-b),(a,-b+cut),(a,b-cut),
                   (a-cut,b),(-a+cut,b),(-a,b-cut),(-a,-b+cut)]
        vv = [tuple(p[i]+u[i]*x+v[i]*y for i in range(3))
              for p in (start,end) for x,y in outline]
        ff = [tuple(reversed(range(8))),tuple(range(8,16))]
        ff += [(j,(j+1)%8,(j+1)%8+8,j+8) for j in range(8)]
        self.mesh(name,role,vv,ff)

    def plates(self, name, x, y, z, width, length, count=4):
        """Raised overlapping armor tiles over a visible dark pressure bed."""
        self.block(name+' inset','dark',(x,y-.055,z),(width+.04,.14,length+.04))
        for j in range(count):
            self.block(name+' plate bank','base' if j%2 else 'trim',
                       (x,y,z-length/2+length*(j+.5)/count),
                       (width,.12,length/count*.86))

    def fins(self, name, x, y, z, width, length, count=4):
        self.block(name+' coolant manifold','dark',(x,y-.04,z),(width,.14,length))
        for j in range(count):
            self.block(name+' radiator fin','trim',
                       (x,y+.025,z-length/2+length*(j+.5)/count),
                       (width,.16,length/count*.44))
        self.block(name+' exposed coolant','cool',(x,y+.11,z),(width*.7,.035,length*.16))


def _defense(m):
    # A low four-shouldered gun drone, not a dish or human crew compartment.
    m.block('tracking drone pressure core','base',(0,-.24,-.14),(.82,.86,1.12))
    m.block('ventral processor keel','dark',(0,-.82,-.18),(.46,.36,.72))
    m.tube('tracking gimbal','trim',(0,.22,.03),.35,.3,'y',bore=.19)
    m.block('gun cradle','dark',(0,.4,.22),(.74,.26,.84))
    m.block('tracking processor armor','base',(0,.64,-.08),(.54,.54,.52))
    m.block('target slit','lit',(0,.82,.19),(.32,.12,.045))
    for side in (-1,1):
        x = side*.72
        m.beam('shoulder load link','dark',(side*.3,-.25,-.22),(x,-.18,-.22),.35,.34)
        m.block('shoulder armor','base',(x,-.16,-.27),(.56,.7,1.06))
        m.plates('shoulder segmented',x,.22,-.27,.49,.94,3)
        m.panel('interceptor bank mount','dark',(x,-.13,.285),(.48,.54,.13))
        m.block('interceptor bank armor pod','trim',(x,-.15,.35),(.42,.42,.18))
        m.tube('interceptor bank rotary feed','accent',(x,-.15,.445),.16,.16,n=8,bore=.085)
        m.panel('interceptor bank sensor hood','base',(x,.075,.385),(.40,.13,.16))
        m.panel('interceptor bank sensor lens','cool',(x,.075,.475),(.28,.08,.04))
        m.fins('shoulder heat rejection',x,.32,-.25,.23,.85)
        m.block('sensor cheek','accent',(side*.4,.58,-.06),(.26,.27,.48))
        m.tube('interceptor barrel','dark',(side*.22,.4,.65),.13,.7,bore=.075)
        m.tube('interceptor muzzle collar','trim',(side*.22,.4,.9),.165,.14,bore=.08)
        m.tube('vector drive casing','dark',(side*.7,-.18,-.86),.19,.28,bore=.12)
        m.tube('vector drive glow','cool',(side*.7,-.18,-.94),.125,.03)
        m.plates('cradle cheek',side*.34,.48,.1,.24,.65,3)
    m.plates('processor dorsal',0,.94,-.08,.43,.45,4)


def _attack(m):
    # Split flywheel banks flank one exposed accelerator: no drone-turret reuse.
    m.block('recoil spine','dark',(0,-.28,-.02),(.48,.58,1.74))
    m.block('ventral recoil sink','base',(0,-.78,-.35),(.48,.44,.76))
    m.block('lance breech','base',(0,.02,-.51),(.72,.72,.65))
    m.tube('lance accelerator','dark',(0,.15,.38),.21,1.24,bore=.12)
    for z in (-.03,.24,.51,.8):
        m.tube('accelerator field winding','accent',(0,.15,z),.31,.13,bore=.215)
        m.block('winding support shoe','trim',(0,-.19,z),(.36,.22,.18))
    m.block('autonomous fire control','base',(0,.74,-.52),(.48,.52,.4))
    m.block('targeting slit','lit',(0,.81,-.305),(.31,.12,.05))
    for side in (-1,1):
        x = side*.68
        m.beam('capacitor structural yoke','trim',(side*.18,-.16,-.35),(x,.05,-.44),.34,.32)
        m.block('split capacitor','base',(x,.13,-.37),(.64,1.12,.92))
        m.plates('capacitor dorsal',x,.73,-.37,.56,.86,3)
        m.panel('capacitor feed bank mount','dark',(x,.13,.115),(.54,.96,.13))
        for y in (-.20,.13,.46):
            m.block('capacitor forward plate bank','trim',(x,y,.185),(.50,.28,.14))
        for y in (-.18,.44):
            m.tube('capacitor feed bank power cell','accent',(x,y,.28),.18,.23,n=8)
            m.tube('capacitor feed bank terminal','cool',(x,y,.405),.105,.04,n=6)
        m.panel('capacitor feed bank interlock','base',(x,.13,.29),(.40,.17,.19))
        m.fins('capacitor heat exchanger',x,.76,-.35,.25,.85)
        m.tube('vector engine','dark',(x,.12,-.85),.245,.3,bore=.16)
        m.tube('vector engine exhaust','cool',(x,.12,-.985),.165,.03)
        m.block('capacitor charging bus','accent',(side*.38,.22,-.2),(.14,.18,.65))
    m.plates('breech roof',0,.43,-.52,.57,.58,3)


def _extractor(m):
    # Three independently articulated drill heads surround a real ore path.
    m.block('ore processing raft','base',(0,-.84,0),(1.6,.32,1.6))
    for x in (-.78,.78):
        for z in (-.78,.78):
            m.block('load spreading foot','dark',(x,-.86,z),(.44,.28,.44))
    m.block('central robotic process tower','base',(0,.04,-.15),(.66,1.5,.66))
    m.block('compressor head','trim',(0,.76,-.18),(.74,.32,.64))
    m.block('autonomous process eyes','lit',(0,.85,.155),(.42,.12,.04))
    m.plates('compressor armor',0,.94,-.18,.62,.58,4)
    m.panel('process crusher mount','dark',(0,.03,.215),(.56,1.12,.14))
    for x in (-.17,.17):
        m.block('process crusher jaw','trim',(x,.13,.31),(.23,.72,.24))
    m.panel('process crusher sorting sensor','accent',(0,-.33,.335),(.50,.16,.21))
    for side in (-1,1):
        m.plates('raft raised armor',side*.6,-.61,-.17,.47,1.15,5)
        m.fins('compressor cooling',side*.43,.14,-.60,.23,.50)
        m.tube('process crusher drive motor','accent',(side*.37,.25,-.1),.22,.22,'x',n=8)
        m.tube('process crusher motor cover','trim',(side*.49,.25,-.1),.15,.06,'x',n=8)
        m.block('ore collection container','base',(side*.59,-.38,-.48),(.38,.48,.40))
        m.panel('ore collection container lid','trim',(side*.59,-.12,-.48),(.34,.08,.36))
        m.panel('ore collection container lock','accent',(side*.59,-.30,-.265),(.22,.22,.09))
    for x,z in ((-.63,.35),(.63,.35),(0,-.67)):
        shoulder = (x*.53,.44,z*.35)
        elbow = (x,.65,z)
        wrist = (x,.05,z)
        m.tube('robot shoulder','accent',shoulder,.19,.27,'x')
        m.beam('robot upper link','base',shoulder,elbow,.24,.27)
        m.tube('robot elbow bearing','trim',elbow,.17,.3,'x')
        m.beam('robot forearm','dark',elbow,wrist,.23,.24)
        m.tube('drill spindle','dark',(x,-.24,z),.145,.72,'y')
        for y in (-.5,-.27,-.04):
            m.tube('drill cutter crown','trim',(x,y,z),.215,.13,'y',n=8)
        m.block('drill drive housing','accent',(x,.02,z),(.38,.3,.38))
    m.block('sorting conveyor','dark',(0,-.58,.46),(.48,.18,1.08))
    for z in (.12,.34,.56,.78):
        m.block('sorting conveyor flight','trim',(0,-.455,z),(.46,.09,.1))
    for side in (-1,1):
        m.block('ore hopper wall','base',(side*.26,-.29,-.41),(.12,.66,.48))
    m.block('ore hopper rear jaw','accent',(0,-.29,-.66),(.58,.66,.12))
    m.block('ore hopper dark throat','dark',(0,-.57,-.42),(.46,.12,.45))
    m.block('ore optical separator','cool',(0,-.39,.03),(.3,.06,.12))


def _trade(m):
    # Ground routing carousel with two load-bearing pick-and-place robot arches.
    m.block('cargo transfer foundation','dark',(0,-.86,0),(1.64,.28,2))
    m.block('transverse loading apron','base',(0,-.77,0),(2,.3,.68))
    m.tube('routing carousel drive','base',(0,-.55,0),.58,.34,'y')
    m.tube('routing carousel bearing','trim',(0,-.34,0),.56,.16,'y',bore=.34)
    m.tube('routing carousel hub','accent',(0,-.3,0),.31,.2,'y')
    m.block('freight routing sensor','lit',(0,-.185,0),(.3,.045,.3))
    for side in (-1,1):
        x = side*.65
        m.block('handling root column','base',(x,-.04,-.15),(.4,1.48,.42))
        m.panel('handling lift mount','dark',(x,-.04,.10),(.32,1.18,.14))
        m.block('handling lift carriage','trim',(x,-.02,.20),(.34,.48,.22))
        m.tube('handling lift servo','accent',(x,-.02,.33),.17,.15,n=8)
        m.beam('handling lift hydraulic rod','trim',(x,-.57,.19),(x,.49,.19),.10,.11)
        m.block('handling shoulder pressure armor','base',(x,.56,-.15),(.52,.48,.58))
        m.tube('handling elbow','accent',(x,.82,-.12),.18,.42,'x')
        m.beam('handling upper arm','trim',(x,.8,-.12),(side*.29,.51,.45),.21,.26)
        m.tube('handling wrist bearing','dark',(side*.29,.48,.45),.17,.28,'x')
        m.beam('cargo jaw left tine','base',(side*.29-.1,.48,.45),(side*.29-.1,.11,.5),.11,.14)
        m.beam('cargo jaw right tine','base',(side*.29+.1,.48,.45),(side*.29+.1,.11,.5),.11,.14)
        m.block('handling jaw actuator','cool',(side*.29,.49,.45),(.14,.07,.2))
        m.plates('handling shoulder',x,.76,-.15,.43,.52,3)
        m.fins('routing processor',side*.28,-.5,-.72,.35,.45)
        for z in (-.63,.63):
            m.block('freight cassette','base',(x,-.45,z),(.48,.54,.62))
            m.plates('cassette impact shield',x,-.14,z,.42,.56,3)
            m.block('freight cassette latch','accent',(x,-.37,z+side*.31),(.23,.18,.06))
            m.panel('freight cassette handling socket','dark',(x,-.45,z+.305),(.36,.36,.08))
            for dx in (-.11,.11):
                m.panel('freight cassette fork rail','trim',(x+dx,-.45,z+.33),(.09,.31,.06))
        m.block('sorting transfer belt','dark',(0,-.64,side*.7),(.59,.16,.56))
        for z in (.45,.64,.83):
            m.block('routing conveyor roller','trim',(0,-.535,side*z),(.55,.08,.07))
    m.block('routing controller armored core','base',(0,-.27,-.65),(.42,.65,.47))
    m.block('routing controller data slit','cool',(0,.07,-.65),(.24,.035,.29))


def _shield(m):
    # Two thick emitter walls grow out of armored buttresses, never a crown.
    m.block('shield armored plinth','base',(0,-.82,0),(1.62,.36,1.62))
    m.block('reactor pressure vessel','dark',(0,-.1,-.13),(.57,1.14,.72))
    m.tube('reactor flux drum','accent',(0,.23,-.15),.31,.56,'y')
    m.block('reactor interlock indicator','lit',(0,.53,-.15),(.3,.05,.3))
    for side in (-1,1):
        x = side*.61
        m.block('emitter array pressure shell','base',(x,.2,-.04),(.54,1.48,1.08))
        m.plates('emitter roof',x,.94,-.04,.48,.98,3)
        # Both faces of each wall are machinery, not blank extruded slabs.
        # Raised stepped pods split a tall bus duct from a broad vent bank.
        for face in (-1,1):
            wall = x+face*.27
            m.panel('emitter power face mount','dark',(wall+face*.025,.20,-.04),(.09,1.30,.96))
            m.block('emitter power face armor pod','trim',(wall+face*.045,.54,-.26),(.11,.54,.44))
            m.panel('emitter power face pod interlock','accent',(wall+face*.105,.54,-.26),(.03,.32,.26))
            m.panel('emitter power face vent well','dark',(wall+face*.04,-.03,.22),(.08,.92,.40))
            for y in (-.36,-.12,.12,.36):
                m.panel('emitter power face vent louvre','trim',(wall+face*.10,y,.22),(.04,.13,.34))
            m.panel('emitter power face conductor channel','accent',(wall+face*.045,-.14,-.28),(.09,.72,.27))
            m.panel('emitter power face conductor','cool',(wall+face*.105,-.14,-.28),(.025,.58,.075))
            m.block('emitter power face step cover','base',(wall+face*.06,-.42,-.28),(.12,.23,.37))
        for z in (-.8,.8):
            m.block('rooted buttress foot','dark',(side*.8,-.85,z),(.4,.3,.4))
            m.beam('rooted buttress','trim',(side*.79,-.68,z),(x,.42,z*.46),.25,.28)
            m.plates('buttress load shield',side*.74,-.63,z,.35,.35,2)
        for y in (.02,.57):
            m.tube('field winding','accent',(x,y,.55),.205,.13,bore=.125)
            m.tube('emitter array aperture','cool',(x,y,.603),.13,.035)
            m.block('emitter array lower bracket','trim',(x,y-.22,.51),(.45,.12,.19))
        m.block('capacitor bank','dark',(side*.3,-.43,-.55),(.4,.39,.55))
        m.plates('capacitor shell',side*.29,-.18,-.55,.36,.49,3)
        m.fins('shield heat rejection',side*.51,-.31,-.78,.46,.40)
        m.beam('reactor armored bus','accent',(side*.12,-.25,-.1),(x,-.25,-.1),.17,.21)
    m.plates('reactor pressure roof',0,.51,-.17,.47,.6,4)


def _pulsar(m):
    # A squat articulated siege mechanism, broad trunnions and massive breech.
    m.block('siege pedestal','base',(0,-.68,-.1),(1.3,.64,1.55))
    m.tube('azimuth bearing','trim',(0,-.3,-.21),.53,.25,'y')
    m.block('heavy breech','base',(0,.4,-.5),(1.1,.9,1))
    m.block('breech recessed process face','dark',(0,.4,-.995),(.77,.6,.01))
    m.block('breech status register','lit',(0,.53,-.999),(.43,.12,.002))
    m.tube('pulsar barrel','dark',(0,.35,.35),.285,1.3,bore=.18)
    for z in (-.06,.25,.58,.91):
        m.tube('pulsar focusing coil','accent',(0,.35,z),.355,.15,bore=.265)
    m.tube('pulsar throat glow','cool',(0,.35,.9),.185,.04)
    m.plates('breech dorsal',0,.94,-.5,.98,.88,4)
    for side in (-1,1):
        x = side*.64
        m.panel('breech power drive mount','dark',(side*.575,.45,-.53),(.11,.68,.82))
        m.block('breech power drive armor pod','base',(side*.63,.62,-.60),(.22,.40,.62))
        for z in (-.81,-.59,-.37):
            m.panel('breech power drive vent cover','trim',(side*.755,.62,z),(.06,.26,.16))
        m.block('breech power drive channel','accent',(side*.67,.28,-.80),(.20,.34,.19))
        m.panel('breech power drive conductor','cool',(side*.775,.28,-.80),(.03,.24,.09))
        m.block('trunnion armored root','base',(x,-.31,-.25),(.38,.7,.84))
        m.tube('articulated trunnion','trim',(x,.2,-.25),.3,.4,'x',bore=.14)
        m.tube('trunnion drive shaft','dark',(x,.2,-.25),.13,.43,'x')
        m.beam('elevation actuator body','dark',(x,-.4,.18),(x,.21,.03),.21,.23)
        m.beam('elevation actuator piston','trim',(x,-.21,.12),(x,.39,-.04),.11,.12)
        m.tube('recoil piston','trim',(side*.55,.51,.29),.1,.94)
        m.tube('recoil piston seal','accent',(side*.55,.51,.04),.16,.2,bore=.105)
        m.block('recoil piston bridge','base',(side*.42,.47,.64),(.37,.26,.24))
        m.plates('trunnion load armor',x,.05,-.25,.34,.72,4)
        m.fins('breech heat exchanger',side*.89,.07,-.46,.20,.64)
        for z in (-.76,.72):
            m.block('anchored siege foot','dark',(side*.78,-.84,z),(.44,.32,.44))
            m.beam('splayed foundation leg','base',(side*.43,-.65,z*.63),(side*.78,-.74,z),.26,.29)
            m.plates('foundation armored shoe',side*.75,-.61,z,.39,.39,2)


def build(kind,g,frame):
    """Emit one actual hardware binding into the supplied geometry facade."""
    if kind not in KINDS:
        raise ValueError(kind)
    {'defense_satellite':_defense,'attack_satellite':_attack,
     'planet_extractor':_extractor,'planet_trade_hub':_trade,
     'planet_shield_generator':_shield,'planet_pulsar_cannon':_pulsar}[kind](_Machine(g,frame))
