"""Alliance modular field hardware: pure math, six existing runtime material roles.

Authored components are placed against the actual asymmetric envelope. There is no
post-build stretch, bevel, shader, Blender dependency, or export side effect.
"""
import math

KINDS = ('defense_satellite', 'attack_satellite', 'planet_extractor',
         'planet_trade_hub', 'planet_shield_generator', 'planet_pulsar_cannon')


def build(kind, g, frame):
    """Emit one original faction model using the native geometry facade."""
    if kind not in KINDS:
        raise ValueError('Unsupported Alliance hardware: '+str(kind))
    lo, hi = frame['lo'], frame['hi']
    if len(lo) != 3 or len(hi) != 3 or not all(
            math.isfinite(a) and math.isfinite(b) and b > a for a,b in zip(lo,hi)):
        raise ValueError('Expected finite positive three-axis bounds')
    s = [(b-a)*.998 for a,b in zip(lo,hi)]
    c = [(a+b)/2 for a,b in zip(lo,hi)]
    unit = min(s)

    def point(p):
        return tuple(c[i]+p[i]*s[i] for i in range(3))

    def box(name, role, loc, size):
        g.box(name,role,point(loc),tuple(size[i]*s[i] for i in range(3)))

    def module(name,role,loc,size):
        x,y,z = point(loc)
        w,h,d = (size[i]*s[i] for i in range(3))
        g.loft(name,role,[(z-d/2,w/2,y+h/2,y-h/2),
                                (z+d/2,w/2,y+h/2,y-h/2)],x=x)

    def ring(name,role,loc,r,depth,axis='z',n=12):
        # Uniform physical radius: collars remain circular, not envelope-stretched.
        center = point(loc)
        radius = r*unit
        thick = depth*unit
        verts = []
        for d in (-thick/2,thick/2):
            for rr in (radius,radius*.70):
                for j in range(n):
                    a = 2*math.pi*j/n
                    offset = (rr*math.cos(a),rr*math.sin(a),d) if axis == 'z' else (rr*math.cos(a),d,rr*math.sin(a))
                    verts.append(tuple(center[i]+offset[i] for i in range(3)))
        faces = []
        for j in range(n):
            k = (j+1)%n
            faces.extend(((j,k,2*n+k,2*n+j),(n+j,3*n+j,3*n+k,n+k),
                          (j,n+j,n+k,k),(2*n+j,2*n+k,3*n+k,3*n+j)))
        g.mesh(name,role,verts,faces)

    surface = kind.startswith('planet_')
    if surface:
        box('grounded modular transfer foundation','dark',(0,-.445,0),(1,.11,1))
        for side in (-1,1):
            module(f'{side} foundation armor sill','base',(side*.41,-.355,0),(.18,.12,.94))
    else:
        module('armored central equipment body','base',(0,-.10,-.04),(.38,.56,.62))
        box('underslung equipment keel','dark',(0,-.44,-.04),(.20,.12,.50))
        for side in (-1,1):
            box(f'{side} transverse equipment spar','trim',(side*.29,-.10,-.04),(.42,.13,.15))
            module(f'{side} outer radiator raft','dark',(side*.44,-.10,-.04),(.12,.10,.64))

    # Individually mounted industrial service cassettes and exposed cooler ribs.
    # These are pressure cabinets, not triangle padding or unsupported decals.
    for side in (-1,1):
        x = side*(.41 if surface else .425)
        y = -.275 if surface else -.025
        for j in range(3):
            z = -.26+j*.25
            module(f'{side} service cassette {j}','base',(x,y,z),(.12,.09,.072))
            box(f'{side} cassette access {j}','accent',(x,y+.046,z),(.095,.006,.053))
            box(f'{side} task beacon {j}','lit',(x,y+.051,z+.014),(.045,.006,.013))
            box(f'{side} coolant indicator {j}','cool',(x,y+.051,z-.014),(.045,.006,.009))
            for k in range(2):
                box(f'{side} cooler rib {j}.{k}','trim',(x+side*.06,y-.022+k*.02,z),(.015,.009,.062))

    if kind == 'defense_satellite':
        module('compact shield capacitor body','base',(0,.17,-.06),(.43,.28,.40))
        module('shield crown control','accent',(0,.405,-.06),(.18,.19,.18))
        for side in (-1,1):
            module(f'{side} interceptor gun housing','base',(side*.21,.10,.25),(.15,.25,.36))
            ring(f'{side} interceptor open muzzle','trim',(side*.21,.10,.485),.095,.08)
            ring(f'{side} interceptor bore support','dark',(side*.21,.10,.46),.075,.08*s[2]/unit,n=10)
            ring(f'{side} shield collar','cool',(side*.12,.18,-.265),.12,.045)
        box('aft shield shielded bus','trim',(0,-.02,-.415),(.30,.28,.17))

    elif kind == 'attack_satellite':
        ring('long weapon spine open barrel','dark',(0,.24,0),.108,s[2]/unit)
        module('weapon breech','base',(0,.15,-.22),(.38,.32,.44))
        module('fire control crown','accent',(0,.405,-.24),(.16,.19,.19))
        for j in range(5):
            ring(f'spine barrel acceleration collar {j}','trim' if j%2 else 'cool',
                 (0,.24,-.08+j*.085),.14,.055)
        box('barrel ventral rail','base',(0,.155,.22),(.035,.06,.55))
        box('barrel ventral rail support','trim',(0,.12,.22),(.025,.08,.55))

    elif kind == 'planet_extractor':
        module('ore sorting engine','base',(.19,-.07,-.03),(.30,.58,.70))
        box('ore conveyor transfer bed','trim',(-.10,-.25,.03),(.34,.16,.80))
        box('drill gantry mast','base',(-.16,.02,-.19),(.12,.80,.13))
        module('drill overhead power head','accent',(-.06,.43,-.12),(.36,.14,.28))
        box('drill continuous drive shaft','dark',(-.09,-.035,-.04),(.075,.79,.075))
        for j in range(7):
            ring(f'drill cutter open flight {j}','trim',(-.09,-.32+j*.09,-.04),.13,.055,axis='y')
            box(f'drill flight hub spoke {j}','dark',(-.09,-.32+j*.09,-.04),(.16,.022,.028))
        for j in range(6):
            box(f'ore conveyor roller {j}','accent',(-.20,-.155,-.29+j*.12),(.18,.035,.045))

    elif kind == 'planet_trade_hub':
        module('trade customs warehouse','base',(-.16,-.09,-.16),(.42,.58,.42))
        box('transfer apron exposed deck','trim',(.06,-.355,.25),(.65,.08,.45))
        for x in (-.29,.26):
            box(f'crane mast {x}','base',(x,.045,-.22),(.085,.85,.10))
        box('load crane overhead travel beam','accent',(-.015,.455,-.22),(.68,.09,.14))
        box('crane trolley','trim',(.16,.39,-.22),(.15,.09,.18))
        box('crane suspended rigid hoist','dark',(.16,.18,-.22),(.025,.40,.025))
        module('crane load gripper','accent',(.16,-.035,-.22),(.16,.05,.16))
        for j in range(5):
            module(f'transfer apron cargo pallet {j}','base',(-.20+j*.11,-.265,.31),(.09,.10,.20))
            box(f'apron pallet stripe {j}','accent',(-.20+j*.11,-.211,.31),(.06,.008,.15))
        for j in range(5):
            ring(f'warehouse transfer pipe collar {j}','trim',(-.16,-.04,-.38+j*.08),.11,.045)

    elif kind == 'planet_shield_generator':
        module('energy capacitor bunker','base',(0,-.20,0),(.40,.38,.40))
        for side in (-1,1):
            box(f'{side} connected energy pylon','base',(side*.22,.055,0),(.10,.75,.13))
            module(f'{side} pylon crown','accent',(side*.22,.455,0),(.15,.09,.17))
            box(f'{side} exposed pylon energy strip','cool',(side*.22,.16,.069),(.045,.42,.009))
        box('coil overhead connecting bus','trim',(0,.39,0),(.48,.065,.09))
        box('coil reactor shaft','dark',(0,.01,0),(.12,.70,.12))
        for j in range(7):
            ring(f'connected energy coil {j}','cool' if j%2 else 'trim',(0,.02+j*.055,0),.22,.05,axis='y')
            box(f'coil radial conductive spoke {j}','accent',(0,.02+j*.055,0),(.28,.022,.035))

    else:
        module('pulsar anchored turret pedestal','base',(0,-.18,-.10),(.53,.52,.56))
        module('pulsar turret breech','base',(0,.19,-.14),(.46,.38,.43))
        module('turret armored crown','accent',(0,.455,-.16),(.26,.09,.24))
        box('turret crown structural neck','trim',(0,.35,-.16),(.18,.14,.18))
        ring('pulsar barrel continuous open tube','dark',(0,.19,.19),.12,.62*s[2]/unit)
        for j in range(7):
            ring(f'pulsar barrel open accelerator {j}','trim' if j%2 else 'cool',
                 (0,.19,-.015+j*.077),.16,.055)
        for side in (-1,1):
            box(f'{side} turret recoil rail','trim',(side*.13,.19,.13),(.045,.09,.55))
            module(f'{side} breech recoil cylinder','accent',(side*.24,.14,-.15),(.09,.15,.32))

    # Broad, stepped functional armor replaces redundant perimeter cassettes.
    if not surface:
        for side in (-1,1):
            for j in range(3):
                z = -.235+j*.18
                module(f'{side} segmented pressure armor {j}','trim',(side*.205,.09,z),(.075,.50,.155))
                module(f'{side} stepped shoulder armor {j}','base',(side*.125,.325,z),(.17,.075,.155))
            box(f'{side} broad flank vent recess','dark',(side*.245,.015,-.04),(.018,.15,.43))
            for j in range(4):
                box(f'{side} flank heat exchanger vane {j}','accent',(side*.258,.015,-.205+j*.11),(.026,.13,.045))
        module('targeting module armored hood','trim',(0,.39,-.08),(.13,.15,.16))
        box('targeting module optical face','dark',(0,.40,.004),(.10,.08,.014))
        box('targeting module optical aperture','lit',(0,.40,.012),(.063,.035,.006))
        module('crown stepped pressure lid','trim',(0,.49,-.16 if kind == 'attack_satellite' else -.06),(.14,.02,.13))

    elif kind == 'planet_extractor':
        for side in (-1,1):
            x = .19+side*.15
            for j in range(3):
                module(f'{side} ore sorter pressure armor {j}','trim',(x,-.045,-.255+j*.225),(.055,.37,.19))
                box(f'{side} ore sorting vent recess {j}','dark',(x+side*.03,-.025,-.255+j*.225),(.014,.17,.12))
        for j in range(3):
            z = -.24+j*.22
            module(f'ore hopper rim {j}','trim',(.19,.235,z),(.24,.055,.185))
            box(f'ore hopper exposed material bin {j}','dark',(.19,.264,z),(.16,.015,.12))
        module('exposed compressor pump block','trim',(-.25,-.05,.19),(.14,.23,.26))
        for j in range(3):
            module(f'compressor pump head {j}','accent',(-.25,.08,.105+j*.08),(.11,.08,.06))
        box('compressor delivery manifold','dark',(-.18,-.03,.19),(.13,.06,.22))
        for j in range(4):
            box(f'power head cooling bank {j}','trim',(-.06,.4925,-.21+j*.06),(.25,.015,.025))

    elif kind == 'planet_trade_hub':
        for side in (-1,1):
            for j in range(3):
                module(f'{side} customs stepped armor {j}','trim',(-.16+side*.21,-.06,-.30+j*.14),(.055,.40,.115))
        for j in range(3):
            module(f'warehouse roof pressure panel {j}','accent',(-.16,.215,-.30+j*.14),(.32,.05,.115))
        box('dock loading door recess','dark',(-.16,-.09,.057),(.29,.33,.025))
        for j in range(4):
            box(f'dock loading door shutter {j}','trim',(-.16,-.20+j*.075,.075),(.27,.045,.025))
        for side in (-1,1):
            a, b = (side*.27,.13,-.22), (side*.06,.41,-.22)
            verts = [point((p[0]+sx*.025,p[1]+sy*.02,p[2]+sz*.035))
                     for p in (a,b) for sx,sy,sz in ((-1,-1,-1),(1,1,-1),(1,1,1),(-1,-1,1))]
            g.mesh(f'{side} crane diagonal truss member','trim',verts,
                   [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
        module('crane trolley drive motor','dark',(.16,.405,-.33),(.14,.13,.13))
        ring('crane motor exposed gearbox','trim',(.16,.405,-.405),.095,.04,n=8)
        for j in range(4):
            module(f'crane beam flange {j}','trim',(-.24+j*.15,.475,-.22),(.10,.05,.17))

    elif kind == 'planet_shield_generator':
        for side in (-1,1):
            module(f'{side} shield base conduit casing','trim',(side*.14,-.29,.20),(.13,.18,.37))
            module(f'{side} capacitor armored flank','trim',(side*.20,-.18,-.02),(.07,.24,.32))
            box(f'{side} capacitor vent bank recess','dark',(side*.24,-.18,-.02),(.025,.16,.25))
            for j in range(4):
                box(f'{side} capacitor vent bank blade {j}','accent',(side*.254,-.18,-.12+j*.067),(.025,.14,.027))
            for j in range(3):
                module(f'{side} pylon pressure armor {j}','trim',(side*.22,-.18+j*.20,-.065),(.13,.17,.05))
            module(f'{side} crown stepped lid','trim',(side*.22,.493,0),(.11,.014,.13))
        box('shield base crossfeed conduit','accent',(0,-.225,.34),(.34,.065,.06))
        for j in range(3):
            module(f'shield crossfeed armored coupling {j}','base',(-.12+j*.12,-.225,.34),(.07,.10,.09))

    else:
        for side in (-1,1):
            for j in range(3):
                module(f'{side} breech bolted armor plate {j}','trim',(side*.235,.22,-.30+j*.15),(.065,.24,.125))
                for y in (.14,.30):
                    box(f'{side} breech plate structural fastener {j}.{y}','dark',(side*.272,y,-.30+j*.15),(.018,.032,.055))
            module(f'{side} pedestal stepped armor','trim',(side*.255,-.18,-.10),(.065,.31,.42))
            box(f'{side} pedestal heat exchanger','dark',(side*.29,-.15,-.10),(.02,.18,.28))
        module('pulsar targeting module hood','trim',(.15,.41,-.10),(.12,.13,.20))
        box('pulsar targeting optical face','dark',(.15,.42,.004),(.09,.07,.014))
        box('pulsar targeting optical aperture','lit',(.15,.42,.012),(.055,.035,.006))
        module('pulsar crown stepped plate','trim',(0,.49,-.16),(.21,.02,.19))
