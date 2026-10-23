"""Nine original Alliance orbital recipes: X beam, Y up, Z longitudinal.

Dimensions are authored against the envelope, never fitted after generation.
Closed chamfered pressure modules, exposed industrial frames and empty working
apertures share the accepted shipyard's naval language, not its geometry.
Only Python math is required; all output goes through the supplied facade.
"""
import math

KINDS = ('command_station', 'mining_station', 'research_station', 'defense_platform',
         'sensor_station', 'trade_station', 'fighter_platform', 'repair_dock', 'energy_relay')


def build(kind, g, frame):
    if kind not in KINDS:
        raise ValueError('Unknown Alliance orbital design: '+str(kind))
    lo, hi = frame['lo'], frame['hi']
    if len(lo) != 3 or len(hi) != 3 or not all(
            math.isfinite(a) and math.isfinite(b) and b > a for a,b in zip(lo,hi)):
        raise ValueError('Expected finite positive three-axis envelope')
    center = [(a+b)/2 for a,b in zip(lo,hi)]
    scale = [(b-a)*.999 for a,b in zip(lo,hi)]

    def point(p):
        return tuple(center[i]+p[i]*scale[i] for i in range(3))

    def box(name, role, p, size):
        g.box(name, role, point(p), tuple(size[i]*scale[i] for i in range(3)))

    def module(name, role, p, size):
        x,y,z = p
        w,h,d = size
        g.loft(name, role, [(center[2]+zz*scale[2], w*scale[0]/2,
                            center[1]+(y+h/2)*scale[1], center[1]+(y-h/2)*scale[1])
                           for zz in (z-d/2,z+d/2)], x=center[0]+x*scale[0])

    def sculpt(name, role, p, size):
        # Broken shoulder / tapered nose, not another constant-section slab.
        x,y,z = p
        w,h,d = size
        sections = ((-.5,.66,.18),(-.29,1,.50),(.24,1,.50),(.5,.76,.30))
        g.loft(name, role, [(center[2]+(z+zz*d)*scale[2], ww*w*scale[0]/2,
                            center[1]+(y+top*h)*scale[1],
                            center[1]+(y-h/2)*scale[1]) for zz,ww,top in sections],
               x=center[0]+x*scale[0])

    def vent(name, p, size):
        # A raised air-handling plenum, recessed dark intake, and broad louvers.
        x,y,z = p
        w,h,d = size
        module(name+' plenum','trim',p,size)
        box(name+' recessed intake','dark',(x,y+h*.48,z),(w*.70,h*.12,d*.72))
        for j in range(3):
            box(f'{name} louver {j}','base',(x,y+h*.56,z+(j-1)*d*.23),
                (w*.73,h*.14,d*.09))

    def annulus(name, role, p, outer, inner, depth, n=24):
        # Genuine Y-up hollow collar. Four walls; no disk across the aperture.
        x,y,z = p
        vv = [point((x+r*math.cos(j*2*math.pi/n), yy,
                     z+r*math.sin(j*2*math.pi/n)))
              for yy in (y-depth/2,y+depth/2) for r in (outer,inner) for j in range(n)]
        ff = []
        for j in range(n):
            k = (j+1)%n
            ff.extend(((j,k,2*n+k,2*n+j),(n+j,3*n+j,3*n+k,n+k),
                       (j,n+j,n+k,k),(2*n+j,2*n+k,3*n+k,3*n+j)))
        g.mesh(name,role,vv,ff)

    def beam(name, role, a, b, width):
        d = [b[i]-a[i] for i in range(3)]
        length = math.sqrt(sum(c*c for c in d))
        d = [c/length for c in d]
        ref = (0,1,0) if abs(d[1]) < .9 else (1,0,0)
        u = [d[1]*ref[2]-d[2]*ref[1],d[2]*ref[0]-d[0]*ref[2],d[0]*ref[1]-d[1]*ref[0]]
        norm = math.sqrt(sum(c*c for c in u))
        u = [c/norm*width/2 for c in u]
        v = [d[1]*u[2]-d[2]*u[1],d[2]*u[0]-d[0]*u[2],d[0]*u[1]-d[1]*u[0]]
        vv = [point(tuple(p[i]+su*u[i]+sv*v[i] for i in range(3)))
              for p in (a,b) for su,sv in ((-1,-1),(1,-1),(1,1),(-1,1))]
        g.mesh(name,role,vv,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])

    def services(name, x, y, z, width=.22, height=.20, length=.90, count=10):
        # Pressure-access panels, shutters and warm occupied service galleries.
        module(name+' pressure hull','base',(x,y,z),(width,height,length))
        for side in (-1,1):
            for j in range(count):
                zz = z+(j-(count-1)/2)*length/count*.91
                xx = x+side*width/2
                box(f'{name} access panel {side}.{j}','trim',(xx,y,zz),(.006,height*.44,length/count*.70))
                box(f'{name} shutter {side}.{j}','dark',(xx+side*.003,y-height*.10,zz),(.004,height*.16,length/count*.52))
                box(f'{name} occupied window {side}.{j}','lit',(xx+side*.003,y+height*.13,zz),(.004,height*.13,length/count*.50))
                box(f'{name} service marking {side}.{j}','accent',(xx+side*.003,y-height*.24,zz),(.004,height*.055,length/count*.43))

    def beacon(name, x, bottom, top, z):
        box(name+' mast','trim',(x,(bottom+top-.018)/2,z),(.025,top-bottom-.018,.025))
        box(name+' navigation light','cool',(x,top-.009,z),(.025,.018,.025))

    if kind == 'command_station':
        services('coalition command keel',0,-.30,0,height=.40,length=1,count=8)
        sculpt('inhabited tier lower','base',(0,.015,0),(.62,.28,.63))
        sculpt('inhabited tier council','trim',(0,.225,0),(.40,.18,.42))
        sculpt('inhabited tier bridge','base',(0,.405,0),(.24,.19,.25))
        box('command bridge roof','accent',(0,.495,0),(.14,.01,.12))
        for side in (-1,1):
            sculpt(f'command habitat wing {side}','base',(side*.34,-.04,0),(.32,.16,.48))
            # Roofs are occupied by meaningful assemblies: segmented walkable
            # armor, service bridges, and two independently vented plant rooms.
            for j,z in enumerate((-.16,0,.16)):
                module(f'command terrace armor lower {side}.{j}','trim',
                       (side*.262,.16,z),(.085,.035,.125))
                module(f'command terrace armor council {side}.{j}','base',
                       (side*.155,.32,z*.57),(.075,.03,.075))
            for end in (-1,1):
                module(f'command terrace armor end {side}.{end}','trim',
                       (side*.155,.15,end*.25),(.17,.04,.095))
                beam(f'command wing load buttress {side}.{end}','dark',
                     (side*.08,-.31,end*.12),(side*.39,-.08,end*.12),.065)
            vent(f'command lower heat exchanger {side}',(side*.16,-.31,0),(.14,.22,.25))
            box(f'command communications array pedestal {side}','dark',
                (side*.435,.145,0),(.04,.16,.06))
            sculpt(f'command communications array housing {side}','trim',
                   (side*.425,.255,0),(.12,.09,.20))
            box(f'command communications array face {side}','cool',
                (side*.425,.302,0),(.08,.012,.12))
            box(f'command communications array divider {side}','accent',
                (side*.425,.311,0),(.018,.015,.12))
            for z in (-.135,.135):
                vent(f'command cooling plant {side}.{z}',(side*.385,.087,z),(.14,.10,.135))
                box(f'command plant feed trunk {side}.{z}','dark',
                    (side*.29,.065,z),(.11,.04,.06))
            module(f'command service bridge {side}','accent',(side*.35,.065,0),(.27,.05,.065))
            for x in (.24,.46):
                box(f'command bridge support {side}.{x}','dark',(side*x,.025,0),(.025,.08,.06))
            # Exposed fore/aft logistics bays: roof + jambs, never a filled cube.
            for end in (-1,1):
                z=end*.365
                module(f'command logistics bay deck {side}.{end}','trim',
                       (side*.15,-.17,z),(.17,.06,.22))
                sculpt(f'command logistics bay canopy {side}.{end}','base',
                       (side*.15,-.015,z),(.18,.055,.22))
                for edge in (-1,1):
                    box(f'command logistics bay jamb {side}.{end}.{edge}','accent',
                        (side*.15+edge*.074,-.09,z),(.022,.12,.20))
                box(f'command logistics bay threshold {side}.{end}','cool',
                    (side*.15,-.135,end*.466),(.12,.012,.018))
                beam(f'command loading bridge {side}.{end}','trim',
                     (side*.15,-.10,end*.28),(side*.15,-.10,end*.20),.035)
            for deck,y,w,length,count in ((0,.04,.31,.27,7),(1,.25,.20,.18,5),(2,.42,.12,.12,4)):
                for j in range(count):
                    z=(j-(count-1)/2)*length/count
                    box(f'inhabited tier window {side}.{deck}.{j}','lit',(side*w,y,z),(.005,.028,length/count*.65))
            box(f'command wing cyan band {side}','cool',(side*.49,-.04,0),(.02,.06,.16))
        # Fore/aft bridge communications housings connect roof to council level.
        for end in (-1,1):
            sculpt(f'command communications trunk {end}','dark',(0,.24,end*.245),(.10,.15,.14))
            module(f'command communications shield {end}','accent',(0,.32,end*.245),(.13,.035,.12))

    elif kind == 'mining_station':
        services('ore processing service hull',0,-.12,0,height=.22,length=1)
        box('ore conveyor transverse bridge','dark',(0,-.15,0),(1,.12,.17))
        for end in (-1,1):
            sculpt(f'ore separator {end}','base',(0,.06,end*.33),(.20,.16,.25))
            vent(f'ore separator exhaust {end}',(0,.165,end*.33),(.15,.065,.16))
            module(f'ore conveyor drive {end}','accent',(0,.01,end*.16),(.15,.10,.12))
            box(f'ore separator output chute {end}','dark',(0,-.03,end*.445),(.13,.07,.09))
        for side in (-1,1):
            sculpt(f'ore crusher armored housing {side}','base',(side*.32,-.18,0),(.28,.32,.36))
            module(f'ore conveyor enclosed transfer {side}','dark',(side*.17,-.04,0),(.18,.09,.12))
            vent(f'ore conveyor drive cooling {side}',(side*.17,.025,0),(.09,.05,.10))
            for j in range(7):
                z=-.14+j*.046
                box(f'ore crusher tooth bank {side}.{j}','trim',(side*.32,-.005,z),(.24,.045,.019))
                box(f'ore conveyor cleat {side}.{j}','accent',(side*.16,-.075,z),(.09,.04,.020))
            module(f'ore collection sump {side}','dark',(side*.32,-.40,0),(.20,.20,.28))
            annulus(f'ore hopper raised rim {side}','trim',(side*.32,.15,0),.175,.13,.10,16)
            for z in (-.16,.16):
                box(f'ore hopper feed support {side}.{z}','base',(side*.32,.04,z),(.06,.22,.055))
            # Open overhead gantry: no sheet across the hopper mouth.
            for z in (-.17,.17):
                box(f'ore handling gantry foot {side}.{z}','base',(side*.32,.29,z),(.055,.22,.05))
            sculpt(f'ore handling hoist rail {side}','accent',(side*.32,.43,0),(.08,.14,.40))
            module(f'ore handling hoist drive {side}','dark',(side*.32,.38,.11),(.11,.08,.10))
            box(f'ore machinery status {side}','cool',(side*.32,.495,0),(.05,.01,.08))

    elif kind == 'research_station':
        services('laboratory central utility trunk',0,-.28,0,height=.44,length=1)
        box('laboratory transfer crossbeam','trim',(0,-.14,0),(1,.10,.12))
        for end in (-1,1):
            sculpt(f'laboratory sample lock {end}','trim',(0,.005,end*.35),(.20,.14,.23))
            module(f'laboratory sample hatch {end}','accent',(0,.08,end*.35),(.12,.035,.13))
        for side in (-1,1):
            for j,z in enumerate((-.30,0,.30)):
                sculpt(f'laboratory pressure vessel {side}.{j}','base',(side*.32,-.10,z),(.25,.25,.22))
                box(f'laboratory view port {side}.{j}','cool',(side*.32,.027,z),(.15,.012,.12))
                box(f'laboratory docking neck {side}.{j}','trim',(side*.18,-.12,z),(.18,.08,.08))
                vent(f'laboratory thermal hood {side}.{j}',(side*.32,.06,z+.025),(.16,.065,.12))
            box(f'research array outrigger {side}','base',(side*.34,.13,0),(.05,.32,.06))
            box(f'research array longitudinal carrier {side}','trim',(side*.34,.27,0),(.035,.05,.64))
            for j in range(5):
                z=-.25+j*.125
                box(f'research array panel {side}.{j}','dark',(side*.34,.285,z),(.27,.035,.11))
                box(f'research array collector {side}.{j}','cool',(side*.34,.306,z),(.23,.008,.08))
        module('laboratory elevated observatory','base',(0,.17,0),(.16,.50,.17))
        beacon('research telescope timing',0,.39,.50,0)
        box('research telescope collar crossmount','base',(0,.38,0),(.28,.03,.035))
        annulus('research telescope open aperture','trim',(0,.38,0),.13,.10,.05)

    elif kind == 'defense_platform':
        services('armored fire control citadel',0,-.12,0,height=.76,length=.44)
        sculpt('fire control armored director','trim',(0,.29,0),(.20,.12,.24))
        box('fire control rangefinder','cool',(0,.354,0),(.14,.012,.065))
        for end in (-1,1):
            vent(f'fire control cooling {end}',(0,-.13,end*.34),(.09,.07,.14))
        for side in (-1,1):
            sculpt(f'gun arm transverse {side}','base',(side*.30,-.13,0),(.40,.20,.16))
            sculpt(f'gun arm longitudinal {side}','base',(0,-.13,side*.31),(.16,.20,.38))
            for axis in ('x','z'):
                p=(side*.37,.04,0) if axis=='x' else (0,.04,side*.37)
                annulus(f'gun arm traverse race {axis}.{side}','dark',
                        (p[0],-.035,p[2]),.12,.085,.05,8)
                sculpt(f'gun arm turret {axis}.{side}','trim',p,(.20,.20,.20))
                module(f'gun arm ammunition {axis}.{side}','accent',
                       (p[0],-.03,p[2]-.085),(.16,.07,.09))
                for lane in (-1,1):
                    x=p[0]+lane*.048
                    box(f'gun arm barrel {axis}.{side}.{lane}','dark',(x,.095,p[2]+.055),(.035,.065,.14))
                    box(f'gun arm muzzle {axis}.{side}.{lane}','accent',(x,.095,p[2]+.115),(.044,.073,.025))
                box(f'gun arm acquisition {axis}.{side}','cool',(p[0],.145,p[2]),(.04,.01,.04))
            for j in range(7):
                box(f'gun arm armor rib {side}.{j}','trim',(side*(.16+j*.045),-.015,0),(.02,.035,.14))
        beacon('fire control director',0,.25,.50,0)
        box('fore aft armored range bridge','dark',(0,-.22,0),(.10,.12,1))

    elif kind == 'sensor_station':
        services('sensor data processing hull',0,-.28,0,height=.44,length=1)
        box('sensor transverse carrier','trim',(0,-.17,0),(1,.13,.12))
        for end in (-1,1):
            sculpt(f'sensor receiver cabinet {end}','trim',(0,.005,end*.32),(.19,.15,.23))
            vent(f'sensor receiver cooling {end}',(0,.105,end*.32),(.14,.065,.15))
        for side in (-1,1):
            module(f'sensor waveguide {side}','accent',(side*.18,-.115,0),(.20,.065,.10))
        for side in (-1,1):
            x=side*.31
            box(f'sensor dish continuous pedestal {side}','base',(x,.025,0),(.065,.39,.065))
            annulus(f'sensor dish reflector rim {side}','trim',(x,.23,0),.185,.15,.055,32)
            # Open ribbed bowl, not a solid sphere; ribs meet center mast and rim.
            for j in range(12):
                angle=j*math.pi/6
                beam(f'sensor dish radial rib {side}.{j}','base',(x,.18,0),
                     (x+.17*math.cos(angle),.23,.17*math.sin(angle)),.012)
            beacon(f'sensor dish feed {side}',x,.18,.50,0)
            annulus(f'sensor dish feed collar {side}','accent',(x,.38,0),.035,.010,.04,16)
        for j in range(8):
            box(f'sensor correlator rack {j}','dark',(0,-.03,-.35+j*.10),(.16,.08,.065))
            box(f'sensor correlator activity {j}','cool',(0,.012,-.35+j*.10),(.09,.008,.035))

    elif kind == 'trade_station':
        services('customs inhabited terminal',0,-.17,0,height=.46,length=1)
        box('transfer gantry cargo crosswalk','base',(0,-.23,0),(1,.22,.16))
        for end in (-1,1):
            sculpt(f'customs inspection lock {end}','trim',(0,.13,end*.31),(.21,.16,.26))
            module(f'customs scanner hood {end}','accent',(0,.22,end*.31),(.16,.05,.15))
            box(f'customs inspection shutter {end}','dark',(0,.10,end*.443),(.12,.07,.012))
        vent('customs terminal life support',(0,.10,0),(.16,.09,.20))
        for side in (-1,1):
            x=side*.38
            box(f'transfer gantry outside rail {side}','trim',(x,-.17,0),(.06,.12,.92))
            module(f'transfer gantry drive {side}','accent',(x,-.065,0),(.12,.09,.14))
            for end in (-1,1):
                sculpt(f'transfer gantry sorting deck {side}.{end}','trim',
                       (side*.24,-.085,end*.24),(.28,.055,.20))
                box(f'transfer gantry cargo roller {side}.{end}','dark',
                    (side*.22,-.05,end*.24),(.16,.018,.13))
                box(f'transfer gantry deck guide {side}.{end}','cool',
                    (side*.22,-.037,end*.24),(.16,.009,.025))
            for j,z in enumerate((-.32,-.105,.105,.32)):
                module(f'transfer gantry bonded container {side}.{j}','base',(x,-.025,z),(.22,.18,.17))
                for k in range(3):
                    box(f'container locking rib {side}.{j}.{k}','accent',(x,.068,z-.055+k*.055),(.22,.014,.012))
                box(f'transfer gantry trolley {side}.{j}','dark',(x,.17,z),(.12,.10,.10))
                box(f'transfer gantry crane column {side}.{j}','trim',(x,.255,z),(.035,.41,.035))
                box(f'transfer gantry hoist beam {side}.{j}','base',(side*.31,.46,z),(.22,.08,.055))
                box(f'transfer gantry load signal {side}.{j}','cool',(side*.31,.495,z),(.04,.01,.035))
        module('customs lower pressure sump','dark',(0,-.445,0),(.16,.11,.32))

    elif kind == 'fighter_platform':
        services('flight operations island',0,-.20,0,height=.60,length=1)
        for side in (-1,1):
            # Side bays are physically empty, with separate roof, floor, and jambs.
            x=side*.32
            box(f'launch bay deck {side}','base',(side*.3025,-.43,0),(.395,.14,.90))
            sculpt(f'launch bay roof {side}','base',(x,.31,0),(.36,.12,.90))
            box(f'launch bay outer jamb {side}','trim',(side*.47,-.03,0),(.06,.62,.90))
            for j,z in enumerate((-.39,-.13,.13,.39)):
                box(f'launch bay roof spar {side}.{j}','trim',(x,.245,z),(.35,.035,.025))
                box(f'launch bay catapult {side}.{j}','dark',(x,-.35,z),(.24,.02,.045))
                box(f'launch bay guide stripe {side}.{j}','cool',(x,-.334,z),(.24,.012,.013))
                box(f'launch bay roof service {side}.{j}','accent',(x,.375,z),(.18,.018,.055))
            for z in (-.445,.445):
                box(f'launch bay doorway light {side}.{z}','lit',(side*.465,.03,z),(.015,.32,.013))
            for end in (-1,1):
                vent(f'launch bay ventilation {side}.{end}',(x,.407,end*.27),(.22,.065,.19))
                sculpt(f'launch bay roof armor {side}.{end}','trim',(x,.378,end*.075),(.30,.035,.12))
                box(f'launch bay duct {side}.{end}','dark',(side*.20,.375,end*.27),(.06,.06,.18))
        module('flight control bridge pedestal','base',(0,.20,0),(.14,.24,.20))
        sculpt('flight control occupied bridge','trim',(0,.40,0),(.16,.20,.24))
        module('flight control roof armor','accent',(0,.48,0),(.13,.04,.14))
        module('flight control access gallery','accent',(0,.12,0),(.12,.04,.80))
        for end in (-1,1):
            sculpt(f'flight control ready room {end}','trim',(0,.16,end*.34),(.18,.12,.19))
            box(f'flight control ready room glazing {end}','lit',(0,.222,end*.34),(.11,.012,.10))

    elif kind == 'repair_dock':
        # The backhouse is behind the working aperture, not inside its void.
        services('repair dock rear workshop',0,-.12,-.41,width=.74,height=.34,length=.18,count=14)
        box('open cradle rear foundation','dark',(0,-.405,-.41),(1,.19,.18))
        for side in (-1,1):
            sculpt(f'repair dock machine shop {side}','trim',(side*.23,.12,-.41),(.24,.17,.18))
            vent(f'repair dock extractor {side}',(side*.23,.235,-.41),(.17,.075,.13))
            box(f'repair dock machine shop support {side}','base',(side*.23,-.005,-.41),(.14,.11,.16))
        for side in (-1,1):
            x=side*.45
            box(f'open cradle longitudinal rail {side}','base',(x,-.35,0),(.10,.16,1))
            box(f'open cradle upper travel rail {side}','trim',(x,.39,0),(.08,.08,1))
            for end in (-1,1):
                sculpt(f'open cradle travel drive {side}.{end}','accent',(x,-.24,end*.37),(.10,.09,.18))
                box(f'open cradle cable tray {side}.{end}','dark',(x,-.255,end*.17),(.075,.03,.25))
            for j,z in enumerate((-.32,-.08,.16,.40)):
                box(f'open cradle upright {side}.{j}','base',(x,.025,z),(.075,.75,.055))
                box(f'open cradle gripper actuator {side}.{j}','accent',(side*.38,-.18,z),(.15,.07,.09))
                box(f'open cradle gripper jaw {side}.{j}','trim',(side*.31,-.10,z),(.045,.20,.065))
                box(f'open cradle crane motor {side}.{j}','dark',(x,.45,z),(.10,.10,.10))
                box(f'open cradle task light {side}.{j}','cool',(side*.396,.32,z),(.025,.025,.04))
                beam(f'open cradle exterior diagonal {side}.{j}','trim',(x,-.30,z-.07),(x,.35,z+.07),.018)
                # Light mounts deliberately bridge from the rail into each light.
                box(f'open cradle light bracket {side}.{j}','trim',(side*.42,.32,z),(.06,.03,.04))
        # No crossbar or filled floor in the forward through-clearance.

    elif kind == 'energy_relay':
        services('power distribution armored manifold',0,-.28,0,height=.44,length=1,count=6)
        box('power stack transverse bus','trim',(0,-.20,0),(1,.15,.14))
        for end in (-1,1):
            sculpt(f'power stack switchgear {end}','base',(0,.04,end*.29),(.20,.22,.25))
            vent(f'power stack switchgear cooling {end}',(0,.175,end*.29),(.15,.065,.16))
            module(f'power stack bus cover {end}','accent',(0,.01,end*.11),(.13,.12,.12))
        for side in (-1,1):
            box(f'power stack longitudinal bus {side}','base',(side*.32,-.25,0),(.10,.12,.82))
            for j,z in enumerate((-.28,0,.28)):
                x=side*.32
                module(f'power stack accumulator {side}.{j}','dark',(x,-.02,z),(.22,.54,.20))
                for k in range(3):
                    y=-.18+k*.20
                    annulus(f'power stack cooling collar {side}.{j}.{k}','trim',(x,y,z),.12,.09,.026,8)
                    box(f'power stack flux indicator {side}.{j}.{k}','cool',(x+.115,y,z),(.015,.026,.035))
                module(f'power stack armored cap {side}.{j}','accent',(x,.29,z),(.23,.12,.21))
                box(f'power stack terminal post {side}.{j}','trim',(x,.415,z),(.045,.17,.045))
                box(f'power stack terminal lamp {side}.{j}','lit',(x,.495,z),(.045,.01,.045))
    return None
