"""UNAPPROVED original Imperium support craft; geometry only, no scene side effects.

X beam, Y up, +Z bow. One Hammer represents the unchanged six-member squadron;
one convoy hauler is shared by crew transport/trade bindings owned by the caller.
Runtime supplies all six material roles. No palette, binding or approval changes.
Broad manufactured chamfers are real surfaces, not modifier-dependent detail.
"""
import math


class _Kit:
    """Local mesh kit, fitted as ONE assembly to the caller's world-unit frame.

    Buffering only this build's vertices permits exact class normalization without
    touching scene objects. Elliptical rings follow the same assembly transform.
    No Blender imports: the caller owns normals, materials, export and lifecycle.
    """
    def __init__(self):
        self.parts = []

    def mesh(self, name, role, verts, faces):
        self.parts.append((name, role, list(verts), list(faces)))

    def loft(self, name, role, stations, x=0):
        verts = []
        for z, w, top, bottom in stations:
            c = min((top-bottom)*.22, w*.28)
            verts.extend([(x-w+c,top,z),(x+w-c,top,z),
                          (x+w,top-c,z),(x+w,bottom+c,z),
                          (x+w-c,bottom,z),(x-w+c,bottom,z),
                          (x-w,bottom+c,z),(x-w,top-c,z)])
        faces = [tuple(reversed(range(8))), tuple(range(len(verts)-8,len(verts)))]
        for k in range(len(stations)-1):
            faces.extend((8*k+j,8*k+(j+1)%8,8*(k+1)+(j+1)%8,8*(k+1)+j)
                         for j in range(8))
        self.mesh(name, role, verts, faces)

    def box(self, name, role, loc, size):
        x,y,z = loc
        w,h,d = size
        self.loft(name, role, [(z-d/2,w/2,y+h/2,y-h/2),
                              (z+d/2,w/2,y+h/2,y-h/2)], x)

    def plate(self, name, role, outline, bottom, top):
        n = len(outline)
        verts = [(x,bottom,z) for x,z in outline]+[(x,top,z) for x,z in outline]
        faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
        faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
        self.mesh(name, role, verts, faces)

    def ring(self, name, role, x, y, stations, n=12):
        verts = []
        for z, outer, inner in stations:
            for r in (outer,inner):
                verts.extend((x+r*math.cos(j*2*math.pi/n),
                              y+r*math.sin(j*2*math.pi/n),z) for j in range(n))
        faces = []
        for k in range(len(stations)-1):
            for wall in (0,1):
                a,b = k*2*n+wall*n,(k+1)*2*n+wall*n
                faces.extend((a+j,a+(j+1)%n,b+(j+1)%n,b+j) for j in range(n))
        for k in (0,len(stations)-1):
            a = k*2*n
            faces.extend((a+j,a+n+j,a+n+(j+1)%n,a+(j+1)%n) for j in range(n))
        self.mesh(name, role, verts, faces)

    def disc(self, name, role, x, y, z, radius, depth, n=12):
        verts = [(x+radius*math.cos(j*2*math.pi/n),
                  y+radius*math.sin(j*2*math.pi/n),z+dz*depth/2)
                 for dz in (-1,1) for j in range(n)]
        faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
        faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
        self.mesh(name, role, verts, faces)

    def emit(self, g, frame, kind):
        points = [v for _,_,verts,_ in self.parts for v in verts]
        lo = [min(v[i] for v in points) for i in range(3)]
        hi = [max(v[i] for v in points) for i in range(3)]
        # A little more than .003 protects float32 export rounding at the limit.
        margin = .0032
        scale = [(frame['hi'][i]-frame['lo'][i]-2*margin)/(hi[i]-lo[i])
                 for i in range(3)]
        for number,(name,role,verts,faces) in enumerate(self.parts,1):
            fitted = [tuple(frame['lo'][i]+margin+(v[i]-lo[i])*scale[i]
                            for i in range(3)) for v in verts]
            g.mesh(f'{kind} {number:03d} {name}', role, fitted, faces, bevel=0)


def _drive(k, x, y, cap, end, radius):
    """Closed machinery ends at cap; luminous disk sits aft inside OPEN throat.

    The disk rim enters the inner wall, so it is mechanically connected. A rear
    axial ray to the disk face hits no closed hull/cap or trim crossbar first.
    """
    k.disc('drive capped machinery', 'dark', x,y,cap+1.4,radius*.88,2.8)
    k.ring('hollow angular drive throat', 'dark', x,y,
           [(cap+.15,radius,.64*radius),
            (end+1.8,1.08*radius,.69*radius),
            (end,1.12*radius,.79*radius)])
    k.ring('exposed annular stern lip', 'trim', x,y,
           [(end+.6,1.14*radius,.79*radius),
            (end,1.14*radius,.79*radius)])
    k.disc('recessed connected cyan emitter', 'cool', x,y,
           end+2.05,.75*radius,.18)


def _bomber(k):
    # Talon-family clipped delta, but twin torpedo hulls dominate the silhouette.
    k.loft('continuous armored center keel','dark',
           [(-23,6.3,5.6,-2.4),(-8,7.7,6.4,-3.24),
            (12,4.4,4.8,-1.9),(35,.7,1.3,-.7)])
    k.loft('layered ventral spear','base',
           [(-21,5,-.2,-3),(-5,5.9,.5,-3.1),(21,2.6,2.4,-1),(35,.7,1.2,-.7)])
    for s in (-1,1):
        k.plate('thick broad swept delta','base',
                [(s*5,17),(s*26,-6),(s*31.25,-16),
                 (s*30,-23),(s*20,-24),(s*6,-15)],-.5,2.6)
        k.plate('recessed wing service field','dark',
                [(s*13,7),(s*27,-9),(s*28.8,-18),(s*18,-20),(s*11,-9)],2.4,2.9)
        k.plate('raised large wing armor field','base',
                [(s*17,1),(s*26,-10),(s*27,-17),(s*20,-18),(s*15,-9)],2.65,3.5)
        k.plate('swept bright trailing edge','trim',
                [(s*9,-15),(s*21,-23),(s*29,-22),(s*24,-19),(s*14,-12)],2.45,3.0)
        k.plate('wing ownership slash','accent',
                [(s*20,-3),(s*21,-4),(s*26,-13),(s*25,-14)],3.35,3.58)
        # Large paired armored torpedo fuselages, not six separate craft.
        k.loft('armored torpedo fuselage','base',
               [(-23,4.8,6.7,-1.4),(-14,5.8,7.8,-2.4),
                (4,5.5,7.4,-2.1),(17,3.7,5.2,-1.1),(24,2,3.6,-.5)],s*13)
        k.loft('fuselage layered dorsal armor','trim',
               [(-20,3.3,7.2,5.9),(-11,4,8.25,6.6),
                (3,3.7,7.85,6.4),(16,2.3,5.5,4.3)],s*13)
        k.box('dorsal ownership panel','accent',(s*13,8.2,-9),(4.2,.3,3.4))
        k.loft('lower wing ordnance pylon','dark',
               [(-12,3.7,1,-2.7),(2,3.7,1.1,-3.05),(13,2.8,1,-2.7)],s*22)
        k.loft('lower pylon armored cheek','base',
               [(-11,3.3,.1,-2.9),(3,3.3,.4,-3.1),(14,2.3,.3,-2.5)],s*22)
        # Three broad cluster sockets on each forward bay, visibly recessed.
        k.box('weapon bay armored bulkhead','dark',(s*13,2.5,21.1),(7.3,4.4,2.1))
        for dx in (-2,0,2):
            k.ring('torpedo launch socket rim','trim',s*13+dx,2.3,
                   [(21.6,.92,.65),(22.8,.92,.65)],n=8)
            k.disc('deep dark launch socket','dark',s*13+dx,2.3,21.7,.67,.15,n=8)
        k.box('torpedo bay safety lamp','lit',(s*16.5,4.15,21.7),(.45,.7,.45))
        k.box('aft thermal well','dark',(s*13,7.5,-18),(6.4,1.2,5))
        for z in (-19.5,-18,-16.5):
            k.box('large thermal shingle','trim',(s*13,8.1,z),(5.1,.5,.65))
        _drive(k,s*13,2.3,-23.3,-28.996,4.25)
    k.loft('cockpit armored plinth','trim',
           [(-10,3.9,7.4,4.3),(-2,4.2,8.6,5.1),(9,2.6,6.4,3.6),(15,1.4,4.6,2.9)])
    k.loft('graphite angular canopy','dark',
           [(-8,3,9.8,6.8),(-2,3.3,12.5,7.7),(5,2.6,10.7,6.4),(11,1.2,6.1,4.2)])
    k.loft('canopy armored center brow','base',
           [(-8,.65,10.2,9.3),(-2,.8,13,12),(5,.55,11.1,10.2),(11,.3,6.4,5.6)])
    k.loft('short dorsal stabilizer foundation','base',
           [(-22,2.4,7,4),(-16,2.8,9.5,5.7),(-9,2,9,6)])
    k.loft('broad swept dorsal crest','trim',
           [(-21,.6,9,6),(-16,.85,14,7),(-10,.55,10.5,7.4)])
    k.loft('raised nose shield','base',[(12,3.5,5,2.2),(25,2.1,3.3,.5),(35,.7,1.3,-.1)])
    k.box('nose dark optical socket','dark',(0,2.8,27),(1.5,.45,2))
    k.box('small exposed nose aperture','cool',(0,3.05,27),(.6,.12,1))


def _windows(k, x, y, zs, side):
    for z in zs:
        k.box('habitation dark window recess','dark',(x,y,z),(.48,2.1,2.6))
        k.box('warm occupied glazing','lit',(x+side*.24,y+.1,z),(.16,.85,1.75))


def _colonizer(k):
    # Continuous deep keel: habitat banks and landing decks key into its sides.
    k.loft('continuous colony frigate keel','dark',
           [(-20,9,8,-5),(-11,11,10,-7),(8,10,11,-6),(20,7.5,10,-3),(24.35825,6,8,-1)])
    k.loft('armored ventral landing section','base',
           [(-18,8,-1,-6.6),(-7,10,-.4,-7),(13,8,1,-5.5),(22,5,3,-2.5)])
    k.box('integrated transverse habitat deck','base',(0,8,-1),(37,4,34))
    for s in (-1,1):
        for z in (-11,0,11):
            k.loft('integrated armored habitat module','base',
                   [(z-4.8,7,17,-.5),(z-3,8.1,19,-1),
                    (z+3,8.1,19,-1),(z+4.8,7,17,-.5)],s*11.9)
            k.loft('habitat raised roof shield','trim',
                   [(z-3.8,5.8,19.5,17.9),(z+3.8,5.8,19.5,17.9)],s*11.9)
            k.box('habitat structural end rib','dark',(s*11.9,9,z-4.2),(14.3,16,.9))
            k.box('habitat owner plaque','accent',(s*11.9,19.6,z),(4,.3,1.8))
            _windows(k,s*20.03,12,[z-1.6,z+1.6],s)
            k.box('landing equipment armored door','dark',(s*14.5,-1,z),(6,1.4,5.8))
            k.box('landing door broad lock rib','trim',(s*14.5,-1.7,z),(4.5,.55,1.3))
        k.loft('landing sponson continuous support','base',
               [(-14,3.7,2,-4.8),(11,3.7,2,-4.8)],s*13)
        k.box('landing pad heavy shoe','trim',(s*13,-5.1,8),(8,1.8,7))
        k.box('aft drive armored shoulder','base',(s*8,3.8,-17),(11,12,7))
        _drive(k,s*8,2,-20,-24.6975,4.1)
        k.box('aft maintenance recess','dark',(s*8,10.1,-17),(7,1,4.7))
        for z in (-18.5,-17,-15.5):
            k.box('aft machinery ventilation shingle','trim',(s*8,10.65,z),(6,.5,.7))
    # Raised forecastle is a civilian docking and navigation house, no armament.
    k.loft('docking forecastle foundation','base',
           [(9,8.3,19.4,8),(17,8.3,22,8),(23,6.8,20,7)])
    k.loft('forward colony navigation house','base',
           [(12,6.5,24,18),(18,6.5,25,19),(21,5.7,23.5,18)])
    k.box('bridge forward visor recess','dark',(0,22.2,21.1),(10,2.7,.55))
    for x in (-3.6,-1.2,1.2,3.6):
        k.box('bridge warm navigation glazing','lit',(x,22.3,21.42),(1.6,.85,.18))
    k.box('forecastle broad armored brow','trim',(0,24,20.4),(13,1,3))
    k.box('forecastle docking recess','dark',(0,7,24.15),(8,7,.4))
    k.box('forecastle personnel airlock','trim',(0,7,24.39),(5.4,5,.4))
    k.box('airlock split pressure seam','dark',(0,7,24.62),(.32,4.1,.15))
    k.box('docking task light','lit',(0,10,24.4),(4,.45,.25))
    k.box('utility mast rooted roof base','dark',(0,24.9,15),(3.2,1.4,3))
    k.box('short utility mast','base',(0,25.85,15),(1,1.3,1))
    k.box('mast transverse survey housing','trim',(0,26.2,15),(5,.6,1.6))
    k.box('mast survey aperture','cool',(0,26.15,15.84),(2,.3,.12))
    k.box('central life support spine','base',(0,13,-3),(7,7,20))
    for z in (-10,-4,2):
        k.box('spine service hatch','dark',(0,16.6,z),(4,.4,3.8))
        k.box('spine hatch reinforcing rim','trim',(0,16.9,z),(3,.35,1.1))


def _convoy(k):
    # Two long, large pressure pods form ONE integrated armored personnel hauler.
    # Unlike the colonizer's six short habitat banks, these are continuous tanks.
    k.loft('hauler central load keel','dark',
           [(-20,8,10,-4),(-12,10,12,-6.8),(10,10,12,-6),(22,8,10,-3),(24.35825,6,8,-1)])
    k.loft('continuous underside cargo ramp casing','base',
           [(-17,6.7,0,-6.7),(9,8,1,-6.5),(21,6.5,4,-3.5)])
    k.box('full width pressure pod load deck','base',(0,6,-1),(36,9,34))
    for s in (-1,1):
        k.loft('long occupied pressure pod','base',
               [(-17,5.7,15,-2),(-13,8.8,19,-3),
                (9,8.8,19,-3),(15,6.9,16,-1.7)],s*10.7)
        k.loft('pod broad dorsal armored shell','trim',
               [(-13,6,19.6,17),(8,6,19.6,17),(12,4.5,17.3,15.5)],s*10.7)
        for z in (-10,-2,6):
            k.box('pod transverse containment saddle','dark',(s*10.7,18.5,z),(14,2,1.5))
            k.box('saddle armored keeper','base',(s*10.7,19.55,z),(10,1.2,1.3))
            k.box('outer cargo lock recess','dark',(s*19.4,7,z),(.45,8,5.5))
            k.box('large cargo lock pressure door','base',(s*19.66,7,z),(.35,6.5,4.4))
            k.box('door transverse pressure lock','trim',(s*19.88,7,z),(.3,1.1,4.8))
            k.box('cargo lock owner marker','accent',(s*19.85,9,z),(.15,.8,2.1))
        _windows(k,s*19.43,13.5,[-7,-4,2,5],s)
        k.box('aft load bearing engine shoulder','base',(s*8,4,-17),(10,12,7))
        _drive(k,s*8,2,-20,-24.6975,4.25)
        k.box('drive access service recess','dark',(s*8,10.2,-17),(6,1,5))
        for z in (-18.6,-17,-15.4):
            k.box('broad drive cooling vane','trim',(s*8,10.8,z),(5,.5,.75))
        k.box('bow load bearing dock cheek','base',(s*8,7,18),(5,13,8))
        k.box('dock face approach lamp','lit',(s*7.9,11.2,22.12),(2,.7,.25))
    # A recessed full-height boarding vestibule is carried between the bow cheeks.
    k.loft('integrated boarding dock forecastle','base',
           [(12,8.5,15,0),(20,8.5,15,1),(24.35825,6.5,13,2)])
    k.box('boarding vestibule recess','dark',(0,7.3,24.5),(9.2,8.8,.5))
    k.box('boarding pressure lock','trim',(0,7.3,24.8),(6.8,7.3,.4))
    k.box('boarding double door panel','base',(0,7.3,25.04),(5.5,6.1,.18))
    k.box('boarding center seam','dark',(0,7.3,25.16),(.3,5.7,.12))
    k.box('broad boarding dock threshold','trim',(0,2.7,24),(11,1.4,3))
    k.box('boarding warm lintel lamp','lit',(0,11.3,24.85),(5.8,.65,.3))
    # Raised compact bridge is amidships, not the colonizer's tall bow house.
    k.loft('midship operations citadel','base',
           [(-8,5.5,21,9),(0,6,23,10),(8,5.3,21,10)])
    k.loft('hauler raised navigation cabin','base',
           [(-5,4.5,24,19),(1,4.8,25,20),(5,4,23.5,19)])
    k.box('navigation graphite visor','dark',(0,22.3,5.1),(6.7,2.2,.5))
    for x in (-2.3,0,2.3):
        k.box('navigation warm glazing','lit',(x,22.4,5.4),(1.5,.75,.18))
    k.box('navigation armored brow','trim',(0,23.9,4.6),(9,1,2))
    k.box('roof mounted communications housing','dark',(0,25.15,-1),(4,1.2,4))
    k.box('communications armored cap','trim',(0,25.7,-1),(4.8,.6,3))
    k.box('communications cool aperture','cool',(0,25.6,1.04),(1.8,.5,.15))
    k.box('central cargo routing deck','dark',(0,13.5,-11),(7,3,9))
    for x in (-2,2):
        k.box('cargo routing reinforced channel','trim',(x,15.1,-11),(1,.7,8))
    k.box('citadel ownership panel','accent',(0,24.15,-4),(3,.3,1.8))


def build(kind, g, frame):
    """Emit only new geometry into ``g``; caller owns six-role materials/export.

    ``frame`` is the old asset's complete class frame, never a per-part frame.
    Unknown kinds fail before emitting any geometry. No membership/binding edits.
    """
    builders = {'bomber': _bomber, 'colonizer': _colonizer, 'convoy': _convoy}
    if kind not in builders:
        raise ValueError(f'Unknown Imperium support kind: {kind!r}')
    if any(frame['hi'][i]-frame['lo'][i] <= .0064 for i in range(3)):
        raise ValueError('Support frame must have positive span exceeding the margin')
    kit = _Kit()
    builders[kind](kit)
    kit.emit(g, frame, kind)
