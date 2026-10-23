"""Original Alliance industrial shipyard; pure, frame-relative geometry recipe.

Two genuinely empty longitudinal slips flank an inhabited coalition-service spine.
Crane travel runs on the OUTSIDE rail, not across the vessel clearance. All detail
is modeled using the native six material roles; no Blender or export side effects.
Coordinates below are fractions of the asset envelope, centered on its midpoint.
"""
import math


def build(kind, g, frame):
    """Emit a connected twin-slip shipyard through the existing geometry facade."""
    if kind != 'shipyard':
        raise ValueError('Alliance station design supports only shipyard')
    lo, hi = frame['lo'], frame['hi']
    if (len(lo) != 3 or len(hi) != 3 or
            not all(math.isfinite(a) and math.isfinite(b) and b > a
                    for a, b in zip(lo, hi))):
        raise ValueError('Expected finite, positive three-axis bounds')
    span = [b-a for a, b in zip(lo, hi)]
    center = [(a+b)/2 for a, b in zip(lo, hi)]
    scale = [s*.998 for s in span]

    def point(p):
        return tuple(center[i]+p[i]*scale[i] for i in range(3))

    def box(name, role, loc, size):
        g.box(name, role, point(loc), tuple(size[i]*scale[i] for i in range(3)))

    def module(name, role, x, y, z, w, h, length):
        # Real eight-sided transverse chamfers, not a post-export bevel modifier.
        g.loft(name, role, [(center[2]+zz*scale[2], w*scale[0]/2,
                            center[1]+(y+h/2)*scale[1],
                            center[1]+(y-h/2)*scale[1])
                           for zz in (z-length/2, z+length/2)],
               x=center[0]+x*scale[0])

    def beam(name, role, a, b, width):
        # Oriented, closed square-section structural member in normalized space.
        d = [b[i]-a[i] for i in range(3)]
        length = math.sqrt(sum(c*c for c in d))
        d = [c/length for c in d]
        ref = (0, 1, 0) if abs(d[1]) < .9 else (1, 0, 0)
        u = [d[1]*ref[2]-d[2]*ref[1], d[2]*ref[0]-d[0]*ref[2],
             d[0]*ref[1]-d[1]*ref[0]]
        norm = math.sqrt(sum(c*c for c in u))
        u = [c/norm*width/2 for c in u]
        v = [(d[1]*u[2]-d[2]*u[1]), (d[2]*u[0]-d[0]*u[2]),
             (d[0]*u[1]-d[1]*u[0])]
        verts = [point(tuple(p[i]+su*u[i]+sv*v[i] for i in range(3)))
                 for p in (a, b) for su, sv in ((-1,-1),(1,-1),(1,1),(-1,1))]
        faces = [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        g.mesh(name, role, verts, faces)

    def habitat_collar(name, y, outer, inner, depth):
        # Y-up open collar, deliberately not the geometry API's Z-axis ring.
        n = 24
        verts = [point((r*math.cos(j*2*math.pi/n), yy,
                        r*math.sin(j*2*math.pi/n)))
                 for yy in (y-depth/2, y+depth/2) for r in (outer, inner)
                 for j in range(n)]
        faces = []
        for j in range(n):
            k = (j+1) % n
            faces.extend(((j,k,2*n+k,2*n+j), (n+j,3*n+j,3*n+k,n+k),
                          (j,n+j,n+k,k), (2*n+j,2*n+k,3*n+k,3*n+j)))
        g.mesh(name, 'trim', verts, faces)

    # A stout inhabited spine, stepped habitat and pressure-service foundation.
    module('inhabited central service spine', 'base', 0,-.075,0,.23,.22,.94)
    module('hub pressure habitat', 'base', 0,.075,0,.205,.22,.55)
    module('hub command habitat', 'base', 0,.245,0,.142,.16,.26)
    module('hub traffic control crown', 'trim', 0,.405,0,.112,.19,.15)
    habitat_collar('hub open habitat collar', .29,.108,.078,.035)
    module('attached reactor foundation', 'dark', 0,-.29,0,.165,.25,.33)
    module('attached reactor armored sump', 'base', 0,-.447,0,.12,.106,.23)
    for side in (-1, 1):
        s = 'port' if side < 0 else 'starboard'
        # Inner/outer rails leave a wide through-going void, with no floor sheet.
        for rail, x in (('inner',.143),('outer',.453)):
            module(f'{s} {rail} slipway rail', 'base', side*x,-.16,0,.049,.075,1)
            box(f'{s} {rail} travel track', 'trim', (side*x,-.117,0),(.020,.012,.99))
            for j in range(12):
                z = -.451+j*.082
                box(f'{s} {rail} track joint {j}', 'dark', (side*x,-.11,z),(.024,.009,.008))
                box(f'{s} {rail} guide beacon {j}', 'cool', (side*x,-.104,z),(.011,.006,.012))
        # Narrow cross-ties below the slips are isolated ribs, never a solid deck.
        for j in range(8):
            z = -.434+j*.124
            box(f'{s} cradle {j} lower tie', 'dark', (side*.277,-.265,z),(.397,.033,.024))
            for edge, x in (('in',.163),('out',.433)):
                beam(f'{s} cradle {j} {edge} diagonal', 'trim',
                     (side*x,-.258,z), (side*(x + (.025 if edge == 'in' else -.025)),-.15,z), .018)
                module(f'{s} cradle {j} {edge} jaw', 'accent', side*x,-.112,z,.054,.035,.038)
            beam(f'{s} cradle {j} underside brace', 'base',
                 (side*.10,-.185,z-.035),(side*.438,-.257,z),.016)
            # Attached fabrication and utilities face outward from the dock.
            module(f'{s} fabrication module {j}', 'base', side*.473,-.205,z,.054,.09,.085)
            box(f'{s} fabrication access door {j}', 'dark', (side*.499,-.201,z),(.002,.044,.043))
            box(f'{s} fabrication task light {j}', 'lit', (side*.5,-.176,z),(.0008,.008,.032))
            for k in range(3):
                box(f'{s} fabrication vent {j}.{k}', 'trim', (side*.4995,-.218+k*.009,z),(.001,.004,.041))
        # Continuous outer truss below the rail: attached open triangular bays.
        for j in range(14):
            z = -.455+j*.065
            beam(f'{s} rail truss rising {j}', 'trim',
                 (side*.453,-.195,z),(side*.453,-.258,z+.0325),.011)
            beam(f'{s} rail truss falling {j}', 'base',
                 (side*.453,-.258,z+.0325),(side*.453,-.195,z+.065),.011)
        box(f'{s} truss lower chord','trim',(side*.453,-.26,0),(.017,.017,.96))
        # Four external crane towers. Longitudinal booms stay outside clear bays.
        for j, z in enumerate((-.35,-.12,.12,.35)):
            module(f'{s} crane {j} rail bogie','dark',side*.453,-.084,z,.062,.06,.10)
            for k in (-1,1):
                box(f'{s} crane {j} foot {k}','accent',(side*(.453+k*.019),-.04,z),(.017,.034,.078))
                beam(f'{s} crane {j} mast {k}','base',
                     (side*(.453+k*.019),-.04,z-.026),
                     (side*(.453+k*.019),.29,z-.026),.018)
            module(f'{s} crane {j} operator cab','base',side*.453,.20,z,.067,.084,.083)
            box(f'{s} crane {j} cab warm glazing','lit',(side*.453,.208,z+.042),(.046,.033,.003))
            box(f'{s} crane {j} overhead boom','trim',(side*.438,.292,z+.025),(.05,.033,.188))
            beam(f'{s} crane {j} boom tension brace','accent',
                 (side*.453,.285,z-.04),(side*.438,.31,z+.11),.012)
            box(f'{s} crane {j} hoist cable housing','dark',(side*.418,.215,z+.09),(.012,.13,.016))
            module(f'{s} crane {j} attached service gripper','accent',side*.418,.147,z+.09,.029,.025,.035)
            box(f'{s} crane {j} safety beacon','cool',(side*.453,.313,z),(.020,.009,.025))
            for k in range(5):
                box(f'{s} crane {j} ladder rung {k}','trim',(side*.474,.005+k*.035,z-.026),(.014,.008,.025))
        # Modular inhabited pods branch off the hub, never float in the dock.
        for j in range(6):
            z = -.237+j*.095
            module(f'{s} attached habitat pod {j}','trim',side*.108,.074,z,.066,.105,.078)
            box(f'{s} pod warm glazing {j}','lit',(side*.1415,.088,z),(.003,.033,.053))
            box(f'{s} pod pressure shutter {j}','dark',(side*.142,.044,z),(.003,.013,.050))
            box(f'{s} pod service stripe {j}','accent',(side*.142,.113,z),(.003,.010,.054))
        # Spine face panels are practical access/thermal hardware, not spikes.
        for j in range(12):
            z = -.429+j*.078
            box(f'{s} spine service panel {j}','trim',(side*.1158,-.076,z),(.003,.086,.060))
            for k in range(2):
                box(f'{s} spine panel louver {j}.{k}','dark',(side*.1178,-.10+k*.023,z),(.0015,.008,.027))
        # Upper decks have actual warm window ribbons, grouped into pressure bays.
        for deck, y, x, count, pitch in ((0,.15,.103,12,.043),(1,.26,.072,6,.038),
                                         (2,.435,.057,4,.032)):
            for j in range(count):
                z = (j-(count-1)/2)*pitch
                box(f'{s} habitat deck {deck} window {j}','lit',(side*x,y,z),(.003,.023,.027))
                box(f'{s} habitat deck {deck} mullion {j}','dark',(side*(x+.001),y,z+.0155),(.004,.027,.004))
    # The control crown reaches the top of the envelope as a broad occupied roof.
    box('control roof attached navigation plate','accent',(0,.495,0),(.09,.01,.123))
    for j in range(6):
        z = -.046+j*.0184
        box(f'control roof cyan guidance {j}','cool',(0,.5,z),(.052,.0008,.009))
    for j in range(12):
        z = -.137+j*.025
        module(f'reactor armored cooling rib {j}','trim',0,-.36,z,.183,.029,.013)
        box(f'reactor maintenance label {j}','accent',(0,-.376,z),(.06,.004,.009))
    return None
