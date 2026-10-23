"""Offline, mesh-only Automated Legions orbital machinery designs."""
import math

KINDS = frozenset(('command_station', 'shipyard', 'mining_station', 'research_station',
                   'defense_platform', 'sensor_station', 'trade_station',
                   'fighter_platform', 'repair_dock', 'energy_relay'))


class _Design:
    """Author in machine coordinates; fit the complete assembly, never clip it.

    Each piece is a closed solid with explicit chamfers, not export-time bevels.
    Overlapping collars and socketed beams represent mechanically joined solids.
    Annuli retain both inner walls and an unobstructed axial bore.
    """
    def __init__(self):
        self.parts = []
        self.hosts = {}
        self.attachments = []

    def solid(self, name, role, vertices, faces):
        self.parts.append((f'{name} {len(self.parts):03d}', role, vertices, faces))

    def block(self, name, role, center, size, basis=None, plain=False):
        w, h, d = size
        c = min(w, d)*.19
        polygon = [(-w/2+c,-d/2), (w/2-c,-d/2), (w/2,-d/2+c),
                   (w/2,d/2-c), (w/2-c,d/2), (-w/2+c,d/2),
                   (-w/2,d/2-c), (-w/2,-d/2+c)]
        if plain:
            polygon = [(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]
        # Reallocate redundant bevel bands to broad, functional equipment.
        # Oblique beams keep the original socket and end-cap profile.
        rows = ((-h/2,.84),(-h*.31,1),(h*.31,1),(h/2,.84)) if basis and not plain else ((-h/2,1),(h/2,1))
        vertices = [(x*s,y,z*s) for y,s in rows for x,z in polygon]
        if basis is None:
            vertices = [tuple(center[i]+p[i] for i in range(3)) for p in vertices]
        else:
            vertices = [tuple(center[i]+sum(p[j]*basis[j][i] for j in range(3))
                              for i in range(3)) for p in vertices]
        n = len(polygon)
        last = n*(len(rows)-1)
        faces = [tuple(range(n)), tuple(reversed(range(last,last+n)))]
        for row in range(len(rows)-1):
            for i in range(n):
                j = (i+1)%n
                faces.append((row*n+i,(row+1)*n+i,(row+1)*n+j,row*n+j))
        index = len(self.parts)
        self.solid(name,role,vertices,faces)
        self.hosts[index] = (center,size,basis)
        return index

    def mounted(self, host, name, role, offset, size):
        """Derive socketed equipment from its host frame, never world guesses.

        Offsets and sizes are host-relative. Contact and visible protrusion are
        checked against the actual convex solids, including oblique beams.
        """
        center, span, basis = self.hosts[host]
        axes = basis or ((1,0,0),(0,1,0),(0,0,1))
        local = tuple(offset[i]*span[i] for i in range(3))
        pos = tuple(center[i]+sum(local[j]*axes[j][i] for j in range(3)) for i in range(3))
        child = self.block(name,role,pos,tuple(size[i]*span[i] for i in range(3)),basis,
                           plain=role in ('dark','cool','lit'))
        self.attachments.append((child,host))
        return child

    def beam(self, name, role, a, b, width=.14, depth=None):
        delta = tuple(b[i]-a[i] for i in range(3))
        length = math.sqrt(sum(x*x for x in delta))
        y = tuple(x/length for x in delta)
        ref = (0,0,1) if abs(y[2]) < .9 else (1,0,0)
        def cross(a,b):
            return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
        x = cross(y,ref)
        norm = math.sqrt(sum(t*t for t in x))
        x = tuple(t/norm for t in x)
        z = cross(x,y)
        return self.block(name,role,tuple((a[i]+b[i])/2 for i in range(3)),
                          (width,length,depth or width),(x,y,z))

    def ring(self, name, role, center, outer, inner, depth, axis='y', segments=16):
        vertices = []
        for z,r in ((-depth/2,outer),(-depth/2,inner),(depth/2,outer),(depth/2,inner)):
            for i in range(segments):
                a = 2*math.pi*i/segments
                p = (r*math.cos(a),r*math.sin(a),z)
                if axis == 'y':
                    p = (p[0],p[2],-p[1])
                elif axis == 'x':
                    p = (p[2],p[0],p[1])
                vertices.append(tuple(center[j]+p[j] for j in range(3)))
        faces = []
        n = segments
        for i in range(n):
            j = (i+1)%n
            faces.extend(((i,j,2*n+j,2*n+i), (n+i,3*n+i,3*n+j,n+j),
                          (i,n+i,n+j,j), (2*n+i,2*n+j,3*n+j,3*n+i)))
        self.solid(name,role,vertices,faces)

    def pod(self, name, center, size=(.48,.32,.48)):
        """Six-role process bank with stepped roof and exposed service machinery.

        Armor cheeks stand proud of dark races on both roof and manifold. A
        nested processor/socket/lens stack replaces the broad luminous end-cap;
        power color is limited to a valve and a status aperture. All dimensions
        derive from the load-bearing casing, retaining the original envelope.
        """
        case = self.block(name+' armor bank','base',center,size)
        for side in (-1,1):
            self.mounted(case,name+' segmented armor panel','trim',
                         (side*.255,.54,0),(.24,.24,.66))
        self.mounted(case,name+' recessed service race','dark',(0,.47,0),(.25,.22,.66))
        manifold = self.mounted(case,name+' coolant manifold','trim',(.42,0,0),(.26,.72,.73))
        for side in (-1,1):
            self.mounted(manifold,name+' segmented manifold cheek','base',
                         (.43,side*.27,0),(.28,.26,.75))
        self.mounted(manifold,name+' manifold recessed race','dark',
                     (.45,0,0),(.22,.24,.74))
        self.mounted(manifold,name+' manifold compressor stage','accent',
                     (.46,0,-.25),(.22,.28,.30))
        self.mounted(manifold,name+' localized coolant valve','cool',(.16/.26-.10,0,0),(.20,.38,.45))
        head = self.mounted(case,name+' machine head processor','accent',(0,0,.45),(.58,.65,.29))
        self.mounted(head,name+' machine head recessed socket','dark',(0,0,.38),(.78,.74,.32))
        self.mounted(head,name+' status lens','lit',(0,0,.14/.29),(.22/.58,.18/.65,.06/.29))
        self.mounted(case,name+' socket collar','trim',(0,-.43,0),(.82,.30,.82))
        for side in (-1,1):
            self.mounted(case,name+' stepped cheek armor','base',(side*.32,-.02,.40),(.20,.74,.31))

    def emit(self,g,frame):
        vertices = [v for _,_,vs,_ in self.parts for v in vs]
        low = [min(v[i] for v in vertices) for i in range(3)]
        high = [max(v[i] for v in vertices) for i in range(3)]
        for name,role,vs,fs in self.parts:
            mapped = [tuple(frame['center'][i]+.4995*frame['span'][i]*
                            (2*(v[i]-low[i])/(high[i]-low[i])-1) for i in range(3)) for v in vs]
            g.mesh(name,role,mapped,fs)


def _command(d):
    # Distributed quorum processors: five polygonal cores, not one inhabited tower.
    d.pod('quorum central polygon core',(0,0,0),(.68,.48,.68))
    nodes = ((-.72,.10,-.65),(.72,.10,-.65),(-.72,-.08,.65),(.72,-.08,.65))
    for x,y,z in nodes:
        d.beam('redundant armored data bridge','dark',(0,-.05,0),(x,y-.05,z),.22)
        d.pod('distributed voting core',(x,y,z),(.51,.43,.50))
        roof = d.block('quorum processor roof armor','trim',(x,y+.26,z),(.32,.18,.35))
        for side in (-1,1):
            cartridge = d.mounted(roof,'quorum stepped compute cartridge','base',
                                  (side*.25,.49,0),(.38,.40,.86))
            d.mounted(cartridge,'quorum compute cartridge thermal socket','dark',
                      (0,.45,0),(.65,.28,.72))
    for a,b in ((nodes[0],nodes[1]),(nodes[2],nodes[3]),(nodes[0],nodes[2]),(nodes[1],nodes[3])):
        d.beam('perimeter armored fiber trunk','trim',a,b,.12)
    d.beam('supported vertical decision bus','dark',(0,-.72,0),(0,.73,0),.24)
    d.pod('upper scheduler processor',(0,.66,0),(.43,.32,.46))
    d.pod('lower logistics processor',(0,-.64,0),(.50,.35,.45))
    for s in (-1,1):
        d.block('command heat exchanger armor','base',(s*.27,-.24,0),(.23,.23,.50))
        d.block('command substantial exhaust vent','dark',(s*.31,-.28,.10),(.20,.22,.28))


def _shipyard(d):
    # No floor, roof or vessel in the dock. Two keel rails and three portal cranes.
    for s in (-1,1):
        x=s*.82
        keel = d.block('assembly cradle spine','dark',(x,-.53,0),(.23,.30,2.0))
        for travel in (-.18,.18,.46):
            d.mounted(keel,'keel sectional deck plate','trim',
                      (0,.54,travel),(1.40,.24,.075))
        for z in (-.72,0,.72):
            d.pod('assembly drive machinery',(x,-.48,z),(.44,.36,.47))
            d.block('gantry pedestal armor','trim',(x,-.20,z),(.24,.30,.28))
            column = d.beam('portal load bearing column','base',(x,-.18,z),(x,.75,z),.17)
            gantry = d.mounted(column,'attached service gantry','trim',
                               (0,-.08,.55),(1.8,.55,.75))
            race = d.mounted(gantry,'column service race motor','dark',
                             (0,0,.45),(.72,.72,.32))
            d.mounted(race,'column localized drive monitor','lit',(0,0,.48),(.30,.28,.18))
            d.block('supported crane travel drive','accent',(x,.63,z),(.28,.25,.33))
            d.beam('robot shoulder','trim',(x,.42,z),(s*.48,.42,z+.10),.15)
            d.beam('robot articulated elbow','dark',(s*.48,.42,z+.10),(s*.40,.12,z+.16),.12)
            tool = d.block('robot welder head','base',(s*.40,.10,z+.16),(.16,.20,.18))
            d.mounted(tool,'assembly head socket','dark',(0,0,.48),(.76,.72,.26))
            d.mounted(tool,'assembly head actuator jaw','accent',(.40,.05,0),(.45,.78,.62))
            d.mounted(tool,'robot welding emitter','lit',(0,0,.50),(.42,.35,.25))
    for z in (-.72,0,.72):
        portal = d.beam('overhead portal gantry','base',(-.87,.76,z),(.87,.76,z),.20)
        for travel in (-.32,0,.32):
            d.mounted(portal,'portal sectional deck armor','trim',
                      (-.49,travel,0),(.58,.27,.92))
        for travel in (-.28,.28):
            machine = d.mounted(portal,'portal face machinery','accent',
                                (0,travel,.50),(1.25,.25,.85))
            d.mounted(machine,'portal face recessed motor housing','dark',
                      (0,0,.46),(.68,.76,.28))
            d.mounted(machine,'portal face tool carriage','trim',
                      (-.36,0,.20),(.42,.58,.95))
            d.mounted(machine,'portal face local power socket','cool',
                      (0,0,.53),(.35,.24,.14))
        d.block('overhead cable drive armor','dark',(0,.76,z),(.48,.23,.26))
    d.beam('rear cradle structural bridge','base',(-.86,-.55,-.90),(.86,-.55,-.90),.22)
    d.beam('underframe diagonal brace','trim',(-.82,-.70,-.78),(.82,-.70,.78),.12)
    d.beam('underframe crossed brace','trim',(.82,-.70,-.78),(-.82,-.70,.78),.12)
    d.pod('yard scheduler processor',(0,.76,-.76),(.50,.30,.43))


def _mining(d):
    d.pod('ore distribution manifold',(0,.05,0),(.70,.53,.65))
    for s in (-1,1):
        feed = d.block('crusher feed conveyor armor','dark',(s*.43,-.10,0),(.70,.25,.32))
        for travel in (-.30,0,.30):
            roller = d.mounted(feed,'crusher feed roller housing','trim',
                               (travel,.48,0),(.25,.62,.90))
            d.mounted(roller,'crusher roller recessed drive','dark',
                      (0,.46,0),(.66,.28,.68))
        for z in (-.42,.42):
            d.pod('refinery separator machinery',(s*.68,.07,z),(.46,.47,.47))
            d.beam('refinery fluid manifold','trim',(s*.64,-.08,-.42),(s*.64,-.08,.42),.16)
            d.block('refinery raised exhaust vent','trim',(s*.68,.37,z),(.32,.19,.32))
    d.block('drill transmission housing','base',(0,-.35,0),(.46,.54,.46))
    for y,r in ((-.48,.39),(-.73,.34),(-.96,.28)):
        d.ring('rotary drill bore','trim',(0,y,0),r,r*.55,.25)
    for s in (-1,1):
        d.beam('drill torque reaction arm','dark',(s*.27,-.31,0),(s*.27,-.85,0),.13)
    d.pod('ore intake sorter',(0,.25,.78),(.60,.42,.45))
    d.beam('intake ore conveyor drive','accent',(0,.06,.14),(0,.06,.78),.29)
    d.block('intake mouth armor','base',(0,.44,.78),(.45,.22,.30))


def _research(d):
    chambers = ((-.68,.0,-.42),(.68,.0,-.42),(0,.0,.73))
    d.pod('experiment arbitration processor',(0,-.25,0),(.62,.36,.58))
    for x,y,z in chambers:
        d.beam('isolated laboratory transfer bridge','trim',(0,-.30,0),(x,-.24,z),.20)
        d.pod('test chamber thermal machinery',(x,y,z),(.52,.38,.53))
        d.ring('open test chamber bore','base',(x,.41,z),.30,.19,.38)
        d.ring('test chamber containment coil','trim',(x,.47,z),.32,.28,.11)
        for s in (-1,1):
            d.beam('chamber containment yoke','dark',(x+s*.25,.06,z),(x+s*.25,.61,z),.10)
        valve = d.block('test chamber valve manifold','accent',(x,.28,z-.28),(.32,.22,.20))
        for side in (-1,1):
            actuator = d.mounted(valve,'containment valve actuator','trim',
                                 (side*.25,.48,0),(.34,.65,.85))
            d.mounted(actuator,'containment actuator recessed drive','dark',
                      (0,.45,0),(.65,.28,.66))
    d.beam('supported experiment timing mast','dark',(0,-.22,-.36),(0,.77,-.36),.20)
    d.pod('timing reference processor',(0,.78,-.36),(.39,.29,.36))
    d.pod('sample quarantine processor',(-.28,-.57,.12),(.40,.29,.44))
    d.pod('sample vacuum processor',(.28,-.57,.12),(.40,.29,.44))


def _defense(d):
    d.pod('fortress targeting processor',(0,.02,-.28),(.55,.46,.65))
    d.pod('fortress lower power processor',(0,-.52,-.28),(.50,.35,.56))
    d.block('fortress cross structure armor','dark',(0,-.18,-.22),(1.65,.27,.48))
    for s in (-1,1):
        d.pod('paired gun ammunition processor',(s*.65,.0,-.50),(.48,.48,.68))
        d.pod('paired gun breech armor',(s*.65,.17,.12),(.47,.40,.55))
        carriage = d.block('gun recoil carriage armor','trim',(s*.65,.03,.49),(.48,.25,.43))
        for side in (-1,1):
            servo = d.mounted(carriage,'recoil servo cassette','base',
                              (side*.25,.43,0),(.36,.48,.85))
            d.mounted(servo,'recoil hydraulic recessed race','dark',
                      (0,.45,0),(.65,.28,.72))
        for x in (s*.51,s*.79):
            d.ring('heavy cannon muzzle bore','dark',(x,.20,.85),.12,.066,.68,axis='z')
            d.ring('heavy cannon cooling bore','trim',(x,.20,.66),.15,.122,.18,axis='z')
        d.block('gun side blast armor','base',(s*.96,.18,-.10),(.20,.41,.67))
        d.beam('gun mount load transfer','accent',(s*.65,-.20,-.38),(0,-.46,-.28),.18)
        d.block('ammunition substantial vent','dark',(s*.65,.31,-.51),(.32,.21,.38))


def _sensor(d):
    # Two thick, cellular phased-array leaves on a forked support, no floating dish.
    d.pod('sensor correlation processor',(0,-.70,-.12),(.92,.38,.64))
    d.pod('sensor timing processor',(0,-.30,-.57),(.50,.33,.43))
    for s in (-1,1):
        x=s*.57
        d.beam('array fork structural mast','dark',(x,-.65,-.12),(x,1.0,-.12),.18)
        d.beam('array fork root brace','trim',(0,-.73,-.15),(x,-.25,-.12),.18)
        d.beam('array rear diagonal waveguide','trim',(0,-.30,-.55),(x,.85,-.12),.12)
        for y in (-.10,.37,.84):
            d.pod('phased array receiver processor',(x,y,.02),(.49,.33,.24))
            tile = d.block('phased array radiator tile','trim',(x,y,.19),(.37,.24,.12))
            for row in (-1,1):
                for col in (-1,1):
                    socket = d.mounted(tile,'phased cell socket','dark',
                                       (col*.24,row*.23,.47),(.39,.36,.24))
                    d.mounted(socket,'phased cell emitter','cool',
                              (0,0,.44),(.42,.42,.24))
    d.beam('array top calibration link','accent',(-.57,.97,-.12),(.57,.97,-.12),.10)


def _trade(d):
    d.pod('cargo routing processor',(0,.12,0),(.72,.46,.65))
    d.pod('cargo inspection processor',(0,-.47,0),(.57,.35,.54))
    for x,z in ((-.78,0),(.78,0),(0,-.78),(0,.78)):
        d.beam('cargo routing conveyor armor','dark',(0,-.13,0),(x,-.13,z),.28)
        d.pod('cargo exchange drive',(x,.08,z),(.46,.37,.48))
        d.block('cargo clamp drive armor','trim',(x,.36,z),(.34,.24,.35))
        # Each raised mechanical hoist has feet and a connected lifting head.
        for s in (-1,1):
            d.beam('cargo hoist load column','base',(x+s*.17,.18,z),(x+s*.17,.72,z),.10)
        hoist = d.block('cargo hoist processor drive','accent',(x,.69,z),(.46,.20,.24))
        for side in (-1,1):
            jaw = d.mounted(hoist,'cargo gripper jaw','base',
                            (side*.32,-.48,.15),(.25,.70,.85))
            d.mounted(jaw,'cargo gripper recessed servo','dark',
                      (0,0,.46),(.62,.65,.28))
        d.block('cargo crane luminous scanner','lit',(x,.59,z+.10),(.25,.10,.08))
    d.block('routing switchgear armor','base',(0,.45,0),(.48,.28,.43))
    d.block('routing switchgear raised vent','dark',(0,.60,0),(.34,.14,.30))


def _fighter(d):
    # Four exposed launch rails. Central flight volume has neither deck nor roof.
    d.beam('launch rear structural bridge','dark',(-.95,-.55,-.85),(.95,-.55,-.85),.27)
    for s in (-1,1):
        for x in (s*.49,s*.87):
            backbone = d.block('open launch acceleration rail','base',(x,-.53,.07),(.13,.20,1.86))
            for travel in (-.30,.30):
                cassette = d.mounted(backbone,'launch rail service cassette','trim',
                                     (s*.48,0,travel),(1.30,.65,.14))
                d.mounted(cassette,'launch rail recessed charge socket','dark',
                          (s*.45,0,0),(.28,.68,.65))
            rail = d.block('launch energized conductor','dark',(x,-.41,.07),(.065,.08,1.70))
            for travel in (-.34,0,.34):
                d.mounted(rail,'launch induction contact segment','cool',
                          (0,.45,travel),(.78,.25,.15))
        for z in (-.55,.50):
            d.pod('launch induction drive',(s*.86,-.57,z),(.39,.36,.43))
            d.beam('launch rail support outrigger','trim',(s*.43,-.62,z),(s*.98,-.62,z),.14)
        d.pod('launch recovery processor',(s*.65,-.10,-.84),(.47,.48,.38))
        d.beam('launch fork root brace','dark',(s*.86,-.64,.68),(s*.65,-.28,-.84),.11)
    d.pod('flight sequencing processor',(0,.45,-.84),(.63,.42,.38))
    d.beam('flight processor mounting stalk','trim',(0,-.61,-.84),(0,.46,-.84),.22)
    d.block('flight control substantial roof vent','dark',(0,.74,-.84),(.46,.20,.30))


def _repair(d):
    # U-shaped service dock, open towards +Z and through its center vertically.
    d.block('repair dock rear structural bridge','dark',(0,-.25,-.91),(1.92,.40,.30))
    d.pod('repair scheduler processor',(0,.18,-.91),(.65,.45,.40))
    for s in (-1,1):
        x=s*.82
        d.block('repair dock longitudinal backbone','base',(x,-.36,-.02),(.26,.35,1.90))
        for z in (-.65,.05,.72):
            d.pod('repair machine shop drive',(x,-.30,z),(.43,.45,.43))
            if z == .05:
                continue  # Central machine shops leave four useful tool stations.
            d.beam('repair robot load pedestal','trim',(x,-.18,z),(x,.45,z),.15)
            d.ring('repair robot shoulder bore','dark',(x,.42,z),.18,.09,.20,axis='z')
            d.beam('repair articulated upper arm','base',(x,.43,z),(s*.50,.66,z+.10),.14)
            d.beam('repair articulated tool arm','accent',(s*.50,.66,z+.10),(s*.43,.30,z+.16),.11)
            tool = d.block('repair plasma tool manifold','trim',(s*.43,.28,z+.16),(.14,.23,.18))
            for side in (-1,1):
                d.mounted(tool,'repair plasma tool jaw','accent',
                          (side*.38,0,.15),(.40,.72,.65))
            d.block('repair plasma emitter','lit',(s*.43,.20,z+.20),(.08,.07,.08))
        service = d.block('repair service armor bank','base',(s*1.02,-.23,-.32),(.20,.37,.56))
        for side in (-1,1):
            d.mounted(service,'repair service segmented armor panel','trim',
                      (side*.25,.54,0),(.24,.24,.66))
        d.mounted(service,'repair service recessed service race','dark',(0,.47,0),(.24,.22,.66))
        head = d.mounted(service,'repair service machine head valve','accent',(0,.35,.35),(.70,.45,.35))
        d.mounted(head,'repair service machine head socket','dark',(0,.40,0),(.66,.30,.72))
        d.block('repair service raised vent casing','dark',(s*1.08,-.02,-.32),(.18,.19,.41))


def _energy(d):
    # Hollow induction stack, four lateral power banks, rear conductor ladder.
    for s in (-1,1):
        d.beam('relay conductor load column','dark',(s*.65,-.95,-.10),(s*.65,.95,-.10),.17)
        for y in (-.52,.52):
            d.pod('relay switchgear processor',(s*.72,y,-.35),(.43,.40,.49))
            d.block('relay switchgear armor','base',(s*.76,y+.26,-.35),(.32,.22,.35))
            d.block('relay switchgear raised vent','dark',(s*.76,y+.38,-.35),(.25,.15,.27))
    for y in (-.78,-.26,.26,.78):
        d.ring('induction power coil','accent',(0,y,0),.49,.32,.22)
        d.ring('power coil coolant bore','trim',(0,y,0),.515,.475,.11)
        for s in (-1,1):
            insulator = d.beam('coil radial insulator','trim',(s*.43,y,-.10),(s*.69,y,-.10),.16)
            shoe = d.mounted(insulator,'relay coil transfer shoe','dark',
                             (0,0,.48),(1.0,.70,.60))
            d.mounted(shoe,'relay local transfer contact','cool',
                      (0,0,.45),(.40,.45,.24))
    for s in (-1,1):
        d.beam('rear high voltage conductor','lit',(s*.30,-.92,-.50),(s*.30,.92,-.50),.085)
        d.beam('rear conductor cross support','base',(s*.68,-.65,-.34),(s*.30,-.65,-.50),.13)
        d.beam('rear conductor upper support','base',(s*.68,.65,-.34),(s*.30,.65,-.50),.13)


_BUILDERS = {'command_station': _command, 'shipyard': _shipyard,
             'mining_station': _mining, 'research_station': _research,
             'defense_platform': _defense, 'sensor_station': _sensor,
             'trade_station': _trade, 'fighter_platform': _fighter,
             'repair_dock': _repair, 'energy_relay': _energy}


def build(kind,g,frame):
    """Emit one machine installation using only ``g.mesh``; no Blender imports."""
    if kind not in KINDS:
        raise ValueError(f'Unknown Legions orbital kind: {kind}')
    try:
        if any(len(frame[k]) != 3 for k in ('lo','hi','span','center')):
            raise ValueError('Frame vectors must have three components')
        if not all(math.isfinite(v) for k in ('lo','hi','span','center') for v in frame[k]):
            raise ValueError('Non-finite frame')
        for i in range(3):
            if frame['span'][i] <= 0 or frame['hi'][i] <= frame['lo'][i]:
                raise ValueError('Empty frame')
            if not math.isclose(frame['hi'][i]-frame['lo'][i],frame['span'][i],rel_tol=1e-7):
                raise ValueError('Inconsistent frame span')
            if not math.isclose((frame['hi'][i]+frame['lo'][i])/2,frame['center'][i],abs_tol=1e-7):
                raise ValueError('Inconsistent frame center')
    except (KeyError,TypeError,IndexError) as exc:
        raise ValueError('Frame requires finite lo, hi, span, center vectors') from exc
    design = _Design()
    _BUILDERS[kind](design)
    design.emit(g,frame)
