"""Pending original Imperium capital art; geometry only, no scene side effects.

Y is up and +Z is the bow. Frame-relative dimensions are design parameters,
not a post-build fit: class-specific stations intentionally occupy the envelope.
All chamfers are explicit octagonal lofts (no evaluated modifier budget guess).
The caller owns materials, scene lifetime, export, and appearance approval.
"""
import math


def build(kind, g, frame):
    """Create Lancer, Gladiator, Executor or Sovereign through the supplied g API."""
    if kind not in ('frigate', 'cruiser', 'battleship', 'supercapital'):
        raise ValueError('Unsupported Imperium capital kind: ' + str(kind))
    lo = [float(v) + .004 for v in frame['lo']]
    hi = [float(v) - .004 for v in frame['hi']]
    beam = (hi[0] - lo[0]) / 2
    height = hi[1] - lo[1]
    length = hi[2] - lo[2]
    cx = (lo[0] + hi[0]) / 2
    prefix = {'frigate':'Lancer', 'cruiser':'Gladiator',
              'battleship':'Executor', 'supercapital':'Sovereign'}[kind]

    def X(v): return cx + beam * v
    def Y(v): return lo[1] + height * v
    def Z(v): return lo[2] + length * v
    def name(v): return prefix + ' / ' + v
    def hull(label, role, stations, x=0.0):
        g.loft(name(label), role, [(Z(z), beam*w, Y(t), Y(b))
                                 for z,w,t,b in stations], x=X(x))
    def box(label, role, x,y,z, w,h,d):
        g.box(name(label), role, (X(x),Y(y),Z(z)),
              (beam*w,height*h,length*d))
    def block(label, role, x,y,z,w,h,d):
        # Deep chamfered castings, not paper-thin surface decoration.
        hull(label,role,[(z-d/2,w/2,y+h/2,y-h/2),
                         (z+d/2,w/2,y+h/2,y-h/2)],x)
    def plate(label, role, outline, top, bottom):
        # Convex thick plate; explicitly fan-triangulated for predictable budgets.
        n=len(outline)
        vv=[(X(x),Y(y),Z(z)) for y in (bottom,top) for x,z in outline]
        ff=[]
        for j in range(1,n-1):
            ff.extend(((0,j+1,j),(n,n+j,n+j+1)))
        ff.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
        g.mesh(name(label),role,vv,ff)

    # Named class silhouettes: narrow patrol spear, squat assault delta,
    # stepped battery fortress, and an extended blade with paired terraces.
    profiles = {
        'frigate':[(.115,.47,.34,.13),(.28,.58,.41,.09),
                   (.49,.47,.42,.11),(.72,.28,.32,.15),(1,.035,.24,.19)],
        'cruiser':[(.12,.76,.38,.12),(.30,.98,.44,.08),
                   (.48,.88,.44,.1),(.70,.51,.35,.14),(1,.045,.24,.18)],
        'battleship':[(.12,.76,.38,.11),(.28,.98,.45,.08),
                      (.49,.84,.45,.1),(.73,.46,.34,.13),(1,.04,.24,.18)],
        'supercapital':[(.12,.82,.40,.10),(.25,.96,.44,.08),
                        (.43,.77,.44,.1),(.75,.39,.34,.13),(1,.032,.24,.18)],
    }
    stations=profiles[kind]
    hull('continuous faceted pressure wedge','dark',stations)
    hull('deep structural ventral keel','base',[(.15,.24,.18,.04),
         (.37,.32,.2,0),(.62,.23,.19,.04),(.92,.045,.22,.15)])
    hull('solid spear nose armor','base',[(.64,.31,.335,.14),
         (.79,.20,.30,.15),(.94,.075,.26,.17),(1,.032,.24,.18)])

    # Independent armor cheeks share the pressure hull load path. Large seams
    # reveal dark substrate; unequal longitudinal fields avoid tiny-noise tiling.
    for s in (-1,1):
        for j,(za,zb,wa,wb) in enumerate(((.16,.32,.70,.86),
                                        (.34,.50,.80,.69),
                                        (.52,.67,.65,.43))):
            if kind=='frigate': wa*=.57; wb*=.57
            elif kind=='supercapital': wa*=.91; wb*=.91
            outline=[(s*.12,za),(s*wa,za),(s*wb,zb),(s*.12,zb)]
            plate('thick deck armor cheek %s %s'%(s,j),'base',outline,.455,.33)
            # Ownership bands embed into the raised plate with no air gap.
            stripe=[(s*.22,za+.012),(s*.29,za+.012),
                    (s*.29,zb-.012),(s*.22,zb-.012)]
            plate('ownership stripe %s %s'%(s,j),'accent',stripe,.458,.45)
        # Wide battery shoulders, or the frigate's attached nacelle pylons.
        reach=.995 if kind=='frigate' else 1.0
        inner=.34 if kind=='frigate' else .46
        outline=[(s*inner,.14),(s*reach,.18),(s*reach,.29),
                 (s*(.62 if kind=='frigate' else .86),.43),(s*inner,.50)]
        plate('load bearing drive and battery shoulder %s'%s,'base',outline,.34,.18)
        # Shoulder top armor is inset; its outer edge stays on the solid shelf.
        outline2=[(s*(inner+.02),.18),(s*(reach-.06),.20),
                  (s*(reach-.06),.28),(s*(.55 if kind=='frigate' else .76),.40),
                  (s*(inner+.02),.40)]
        plate('layered shoulder roof %s'%s,'trim',outline2,.37,.32)

    # A connected stepped island: Lancer's compact patrol bridge vs Gladiator's
    # wide low command bunker vs Executor's aft fortress. Sovereign instead has
    # twin longitudinal command terraces around a tall central backbone.
    tower = {'frigate':(.15,.24,.36), 'cruiser':(.25,.22,.39),
             'battleship':(.21,.27,.35), 'supercapital':(.17,.38,.38)}
    tw,td,tz=tower[kind]
    block('citadel foundation','base',0,.49,tz,tw*3,.25,td*1.38)
    block('citadel lower fortress step','trim',0,.625,tz-.015,tw*2.6,.15,td*1.04)
    block('citadel recessed upper step','dark',0,.74,tz-.025,tw*2.14,.16,td*.77)
    block('bridge armored sidewall','base',0,.817,tz-.018,tw*2,.12,td*.62)
    # Actual exposed vertical bridge wall; windows penetrate it slightly.
    for s in (-1,1):
        for j in range(7):
            box('warm bridge viewport %s %s'%(s,j),'lit',s*tw,.819,
                tz-.018+(j-3)*td*.073,.014,.026,td*.046)
    block('bridge brow integrated armored overhang','trim',0,.88,tz-.018,
          tw*2.14,.04,td*.69)
    block('reinforced command spine foot','base',0,.925,tz-.04,tw*.72,.07,td*.45)
    block('command sensor armored crown','trim',0,.975,tz-.04,tw*.45,.05,td*.26)
    box('crown inset rangefinder','cool',0,.976,tz-.04+td*.131,
        tw*.26,.015,.003)

    if kind=='supercapital':
        for s in (-1,1):
            hull('twin command terrace %s'%s,'base',[(.16,.18,.58,.32),
                 (.30,.21,.65,.33),(.47,.17,.64,.34),(.65,.085,.45,.31)],x=s*.37)
            hull('terrace armored cap %s'%s,'trim',[(.20,.15,.62,.56),
                 (.31,.17,.68,.62),(.47,.13,.67,.61),(.59,.065,.52,.45)],x=s*.37)
            box('terrace ownership ribbon %s'%s,'accent',s*.37,.686,.365,.16,.014,.09)
        hull('extended central command backbone','base',[(.13,.12,.52,.30),
             (.30,.15,.62,.36),(.51,.12,.57,.35),(.75,.05,.36,.28)])
    elif kind=='battleship':
        hull('long stepped dorsal fortress','base',[(.13,.31,.49,.31),
             (.24,.33,.58,.32),(.43,.25,.57,.34),(.59,.15,.49,.34),
             (.73,.055,.35,.29)])
    elif kind=='cruiser':
        hull('broad assault dorsal glacis','base',[(.38,.36,.50,.35),
             (.53,.30,.49,.34),(.67,.18,.39,.30)])
    else:
        hull('patrol axial sensor spear','trim',[(.51,.10,.47,.38),
             (.67,.08,.37,.30),(.82,.045,.30,.25)])

    # Surface shipyard hardware: broad recessed channels, thermal cassettes,
    # attached transverse clamps and substantial louvres, not floating greebles.
    bank_count=5 if kind=='frigate' else (4 if kind=='supercapital' else 6)
    channel_x=.30 if kind=='frigate' else .52
    for s in (-1,1):
        block('open longitudinal service trench %s'%s,'dark',s*channel_x,
              .462,.415,.14,.033,.42)
        for j in range(bank_count):
            z=.235+j*.061
            block('thermal cassette %s %s'%(s,j),'dark',s*channel_x,
                  .484,z,.115,.041,.049)
            for k in range(6):
                box('broad radiator vane %s %s %s'%(s,j,k),'trim',s*channel_x,
                      .509,z+(k-2.5)*.0068,.098,.020,.0038)
            block('trench manifold clamp %s %s'%(s,j),'base',
                  s*(channel_x+.065),.494,z,.040,.05,.020)
        # Mechanically grounded side equipment bays on the rear shoulders.
        for j in range(4):
            block('shoulder equipment bay %s %s'%(s,j),'dark',s*.79,.375,
                  .205+j*.027,.18,.035,.021)
            for k in (-1,0,1):
                block('shoulder bay cooling rib %s %s %s'%(s,j,k),'base',
                      s*.79,.398,.205+j*.027+k*.0058,.15,.018,.003)

    # Gun batteries are load-bearing deck installations: deep sockets, cast
    # polygonal housings, forward sleeves and open annular muzzles. Broadside
    # shoulders carry visibly heavier batteries on assault/fortress classes.
    gun_sites={'frigate':[(0,.62,.35),(-.59,.30,.37),(.59,.30,.37)],
               'cruiser':[(-.70,.28,.37),(.70,.28,.37),(-.57,.43,.455),
                          (.57,.43,.455),(0,.66,.35)],
               'battleship':[(-.73,.26,.37),(.73,.26,.37),(-.64,.41,.455),
                             (.64,.41,.455),(-.38,.57,.455),(.38,.57,.455)],
               'supercapital':[(-.73,.25,.37),(.73,.25,.37),(-.64,.40,.455),
                               (.64,.40,.455),(0,.64,.38),(0,.79,.30)]}[kind]
    for j,(x,z,deck) in enumerate(gun_sites):
        block('battery socket %s'%j,'dark',x,deck+.023,z,.19,.065,.068)
        hull('armored battery mantlet %s'%j,'base',[(z-.029,.088,deck+.12,deck+.03),
             (z+.006,.10,deck+.12,deck+.03),(z+.037,.073,deck+.10,deck+.035)],x)
        block('battery roof %s'%j,'trim',x,deck+.124,z-.003,.13,.018,.042)
        for s in (-1,1):
            bx=x+s*.038
            block('battery barrel jacket %s %s'%(j,s),'dark',bx,
                  deck+.073,z+.056,.043,.047,.071)
            r=beam*.025
            yy=Y(deck+.073)
            g.ring(name('open battery muzzle %s %s'%(j,s)),'trim',X(bx),yy,
                   [(Z(z+.084),r,r*.58),(Z(z+.101),r*.90,r*.58)],n=8)
            g.disc(name('recessed battery bore %s %s'%(j,s)),'dark',X(bx),yy,
                   Z(z+.086),r*.56,length*.001,n=8)
        box('battery owner marking %s'%j,'accent',x,deck+.135,z-.006,.065,.008,.018)

    # Rear-facing propulsion: EVERY solid pressure cap ends at z >= .12.
    # Emitters at .025 sit aft of all caps, inside genuine annular walls. No
    # solid housing or cross brace is placed behind the cyan disc aperture.
    drive_sites={'frigate':[(-.68,.26,.315),(.68,.26,.315)],
                 'cruiser':[(-.64,.25,.23),(0,.25,.23),(.64,.25,.23)],
                 'battleship':[(-.72,.25,.21),(-.24,.25,.21),
                               (.24,.25,.21),(.72,.25,.21)],
                 'supercapital':[(-.72,.25,.21),(-.24,.25,.21),
                                  (.24,.25,.21),(.72,.25,.21),
                                  (-.40,.52,.18),(.40,.52,.18)]}[kind]
    nozzle_sides = 12 if kind=='supercapital' else 16
    for j,(x,y,rfrac) in enumerate(drive_sites):
        r=beam*rfrac
        hull('integrated drive pressure root %s'%j,'base',[
             (.12,rfrac*.96,y+r/height*.84,y-r/height*.84),
             (.22,rfrac*.99,y+r/height*.94,y-r/height*.94),
             (.32,rfrac*.71,y+r/height*.65,y-r/height*.65)],x)
        g.ring(name('hollow flared thrust throat %s'%j),'dark',X(x),Y(y),
               [(Z(.12),r*.91,r*.63),(Z(.083),r*.94,r*.69),
                (Z(.043),r*.99,r*.77),(Z(0),r,r*.80)],n=nozzle_sides)
        g.ring(name('bright annular exhaust lip %s'%j),'trim',X(x),Y(y),
               [(Z(.014),r*1.005,r*.80),(Z(0),r*1.005,r*.80)],n=nozzle_sides)
        g.disc(name('exposed cyan drive emitter %s'%j),'cool',X(x),Y(y),
               Z(.025),r*.76,length*.002,n=nozzle_sides)
        g.disc(name('small dark drive hub %s'%j),'dark',X(x),Y(y),
               Z(.0235),r*.18,length*.001,n=12)
        # Structural external annuli distinguish a manufactured drive train.
        for k,z in enumerate((.05,.085)):
            g.ring(name('external thrust reinforcement collar %s %s'%(j,k)),
                   'base',X(x),Y(y),[(Z(z-.004),r*.982,r*.935),
                                     (Z(z+.004),r*.982,r*.935)],n=nozzle_sides)
        for a in range(4):
            ang=a*math.pi/2
            # Radial attachments intersect only the outer shell, never the bore.
            bx=x+(r*.91/beam)*math.cos(ang)
            by=y+(r*.91/height)*math.sin(ang)
            block('nozzle external load clamp %s %s'%(j,a),'base',bx,by,
                  .078,r/beam*.16,r/height*.16,.042)
        block('drive cowling ownership band %s'%j,'accent',x,
              y+r/height*.94,.22,rfrac*1.18,.014,.019)

    # Bow axial service recesses are cut visually into thick underlying armor.
    for j,(z,w,y) in enumerate(((.76,.12,.31),(.84,.085,.286),(.92,.05,.261))):
        block('bow axial dark sensor bed %s'%j,'dark',0,y,z,w,.014,.045)
        for s in (-1,1):
            block('bow armored sensor rail %s %s'%(s,j),'trim',s*w*.50,
                  y+.009,z,.016,.022,.048)
    box('tiny inset bow optic','cool',0,.242,.986,.025,.012,.006)
