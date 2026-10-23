"""Rim Syndicate rework designs: the three hulls the faction never had.

Geometry only, no scene side effects. Y is up and +Z is the bow. Dimensions are
frame-relative design parameters, so the class silhouette occupies its approved
legacy envelope instead of being stretched into it afterwards.

Composition follows the accepted Imperium capital batch, because that is the
level the owner asked for: a few large chamfered volumes with a clear hierarchy,
flush flank channels doing the detail work, and small parts used only where a
silhouette has to change. It is not an Imperium clone — the Syndicate's own
vocabulary carries the read: a welded barge hull, one thick port armour
sponson opposed by a starboard truss that ends in a counterweight drum, exposed
reactor drums, an offset command tower, a blunt salvage prow with ram jaws, and
drive emitters set inside annular throats.
"""
KINDS = ('bomber', 'battleship', 'supercapital')

# Per-class plan. Every value resolves to the measured legacy envelope, so a
# class can differ in proportion and detail but never in size.
CFG = {
    'bomber': dict(hull=.40, top=.56, bottom=.10, deck_top=.76,
                   tower_z=.30, turrets=1, casemates=2, drums=2, drives=2,
                   rows=2, mouths=0, gantries=0, name='Cutthroat Strike Wing'),
    'battleship': dict(hull=.50, top=.54, bottom=.06, deck_top=.74,
                       tower_z=.26, turrets=3, casemates=4, drums=4, drives=4,
                       rows=3, mouths=2, gantries=0, name='Marauder Battleship'),
    'supercapital': dict(hull=.52, top=.56, bottom=.06, deck_top=.76,
                         tower_z=.24, turrets=4, casemates=6, drums=6,
                         drives=6, rows=4, mouths=3, gantries=3,
                         name='Leviathan Salvage Dreadnought'),
}


def build(kind, g, frame):
    if kind not in KINDS:
        raise ValueError('Unsupported Syndicate kind: ' + str(kind))
    lo = [float(v) + .004 for v in frame['lo']]
    hi = [float(v) - .004 for v in frame['hi']]
    beam = (hi[0] - lo[0]) / 2
    height = hi[1] - lo[1]
    length = hi[2] - lo[2]
    cx = (lo[0] + hi[0]) / 2
    cfg = CFG[kind]
    prefix = cfg['name']

    def X(v):
        return cx + beam * v

    def Y(v):
        return lo[1] + height * v

    def Z(v):
        return lo[2] + length * v

    def name(label):
        return prefix + ' / ' + label

    # ---- plan tables: the one source every part is placed from ------------
    hull_st = [(.05, cfg['hull'] * .80, cfg['top'] * .86, cfg['bottom']),
               (.16, cfg['hull'] * .96, cfg['top'], cfg['bottom']),
               (.34, cfg['hull'], cfg['top'], cfg['bottom'] + .02),
               (.54, cfg['hull'] * .88, cfg['top'] * .96, cfg['bottom'] + .04),
               (.72, cfg['hull'] * .68, cfg['top'] * .86, cfg['bottom'] + .09),
               (.88, cfg['hull'] * .42, cfg['top'] * .72, cfg['bottom'] + .16),
               (.99, cfg['hull'] * .20, cfg['top'] * .58, cfg['bottom'] + .22)]
    deck_st = [(.10, cfg['hull'] * .62, cfg['deck_top'] - .24, cfg['top'] - .10),
               (.20, cfg['hull'] * .74, cfg['deck_top'] - .04, cfg['top'] - .06),
               (.40, cfg['hull'] * .70, cfg['deck_top'], cfg['top'] - .04),
               (.58, cfg['hull'] * .56, cfg['deck_top'] - .06, cfg['top'] - .06),
               (.72, cfg['hull'] * .34, cfg['deck_top'] - .16, cfg['top'] - .12)]

    def sample(st, z, index):
        if z <= st[0][0]:
            return st[0][index]
        if z >= st[-1][0]:
            return st[-1][index]
        for a, b in zip(st, st[1:]):
            if a[0] <= z <= b[0]:
                t = (z - a[0]) / (b[0] - a[0])
                return a[index] + (b[index] - a[index]) * t
        return st[-1][index]

    def half_at(z, st=hull_st):
        return sample(st, z, 1)

    def top_at(z, st=hull_st):
        return sample(st, z, 2)

    def loft(label, role, stations, x=0.0):
        g.loft(name(label), role, [(Z(z), beam * w, Y(t), Y(b))
                                   for z, w, t, b in stations], x=X(x))

    def flank(label, role, z0, z1, y0, y1, edges):
        """A chamfered volume between two X edges that follow the hull taper.

        ``edges(z)`` returns the two beam-fraction edges at that station, so an
        armour sponson can run from the flank out to a fixed beam extreme while
        a detail channel can sit just proud of the flank and follow it exactly.
        Built as an eight-sided loft rather than a prism: the bevel is what makes
        welded plate read as plate instead of as a flat card.
        """
        ring = 8
        verts, faces = [], []
        span = y1 - y0
        stations = (z0, (z0 + z1) / 2, z1)
        for z in stations:
            a, b = edges(z)
            cxx, half = (a + b) / 2, abs(b - a) / 2
            cut = min(span * .32, beam * half * .45)
            verts.extend([
                (X(cxx - half + cut / beam), Y(y1), Z(z)),
                (X(cxx + half - cut / beam), Y(y1), Z(z)),
                (X(cxx + half), Y(y1 - cut / height), Z(z)),
                (X(cxx + half), Y(y0 + cut / height), Z(z)),
                (X(cxx + half - cut / beam), Y(y0), Z(z)),
                (X(cxx - half + cut / beam), Y(y0), Z(z)),
                (X(cxx - half), Y(y0 + cut / height), Z(z)),
                (X(cxx - half), Y(y1 - cut / height), Z(z)),
            ])
        faces.append(tuple(reversed(range(ring))))
        faces.append(tuple(range((len(verts) // ring - 1) * ring, len(verts))))
        for k in range(len(verts) // ring - 1):
            for j in range(ring):
                faces.append((k * ring + j, k * ring + (j + 1) % ring,
                              (k + 1) * ring + (j + 1) % ring, (k + 1) * ring + j))
        g.mesh(name(label), role, verts, faces)

    def band(label, role, side, z0, z1, y0, y1, outset, inner=.995):
        """Detail channel flush on the flank, following its taper exactly."""
        flank(label, role, z0, z1, y0, y1,
              lambda z: tuple(sorted((half_at(z) * side * inner,
                                      half_at(z) * side * (1 + outset)))))

    def wing(label, role, side, plan, root, tip):
        """Swept wing volume: thick at the root, thin at the tip.

        Squadron craft in this class are wing-wide, and a rectangular slab of
        that span reads as a shelf. ``plan`` gives the four planform corners
        (x, z) in beam/z fractions; ``root`` and ``tip`` give (top, bottom)
        heights, so the wing has dihedral and a real taper.
        """
        verts, faces = [], []
        for (px, pz), (top, bot) in zip(plan, (root, root, tip, tip)):
            verts.extend([(X(side * px), Y(top), Z(pz)),
                          (X(side * px), Y(bot), Z(pz))])
        faces.append((0, 2, 4, 6))
        faces.append((1, 3, 5, 7))
        for j in range(4):
            k = (j + 1) % 4
            faces.append((j * 2, k * 2, k * 2 + 1, j * 2 + 1))
        g.mesh(name(label), role, verts, faces)

    def block(label, role, x, y, z, w, h, d):
        g.box(name(label), role, (X(x), Y(y), Z(z)),
              (beam * w, height * h, length * d))

    # ---- welded barge pressure hull, keel, deckhouse ----------------------
    loft('welded barge pressure hull', 'dark', hull_st)
    loft('ventral structural keel', 'base',
         [(.08, cfg['hull'] * .34, cfg['bottom'] + .12, 0.),
          (.26, cfg['hull'] * .46, cfg['bottom'] + .16, 0.),
          (.54, cfg['hull'] * .40, cfg['bottom'] + .18, .01),
          (.80, cfg['hull'] * .24, cfg['bottom'] + .22, .05)])
    loft('dorsal deckhouse', 'base', deck_st)
    loft('deckhouse upper step', 'base',
         [(.22, cfg['hull'] * .48, cfg['deck_top'] + .06, cfg['deck_top'] - .06),
          (.40, cfg['hull'] * .44, cfg['deck_top'] + .08, cfg['deck_top'] - .04),
          (.58, cfg['hull'] * .30, cfg['deck_top'] + .02, cfg['deck_top'] - .06)])

    # ---- prow: layered plates over a blunt ram, not a spear ---------------
    loft('prow armour plate', 'base',
         [(.66, cfg['hull'] * .70, cfg['top'] * .90, cfg['bottom'] + .06),
          (.82, cfg['hull'] * .50, cfg['top'] * .76, cfg['bottom'] + .12),
          (.92, cfg['hull'] * .38, cfg['top'] * .62, cfg['bottom'] + .18),
          (1.0, cfg['hull'] * .26, cfg['top'] * .52, cfg['bottom'] + .22)])
    loft('prow upper plate', 'trim',
         [(.72, cfg['hull'] * .42, cfg['top'] * .74, cfg['top'] * .58),
          (.88, cfg['hull'] * .30, cfg['top'] * .64, cfg['top'] * .52),
          (1.0, cfg['hull'] * .16, cfg['top'] * .54, cfg['top'] * .46)])
    # Blunt face plate: the prow ends like a welded ram, not a knife edge.
    loft('prow blunt face', 'trim',
         [(.955, cfg['hull'] * .26, cfg['top'] * .56, cfg['bottom'] + .22),
          (1.0, cfg['hull'] * .22, cfg['top'] * .50, cfg['bottom'] + .26)])
    for side in (-1, 1):
        g.prism(name(f'ram jaw {side}'), 'trim', Y(cfg['bottom'] + .16),
                Y(cfg['top'] * .44),
                [(X(side * .055), Z(.70)), (X(side * .185), Z(.76)),
                 (X(side * .150), Z(1.0)), (X(side * .040), Z(1.0))])
        block(f'jaw grapple {side}', 'dark', side * .095, cfg['top'] * .34, .965,
              .060, .08, .055)

    # ---- sponsons: two chamfered volumes welded onto the flank -----------
    # Port is the thick uninterrupted citadel; starboard is shorter and feeds
    # the truss, so the asymmetry reads as structure rather than decoration.
    if kind == 'bomber':
        # A squadron craft is wing-wide by design: the span is carried by swept
        # wing volumes with real taper and dihedral, not by armour shelves.
        for side in (-1, 1):
            wing(f'strike wing {side}', 'base', side,
                 ((.42, .26), (.97, .46), (.97, .60), (.42, .70)),
                 (.44, .27), (.40, .37))
            wing(f'wing leading edge {side}', 'trim', side,
                 ((.46, .28), (.95, .47), (.95, .52), (.46, .34)),
                 (.445, .425), (.405, .385))
            block(f'wing root fairing {side}', 'base', side * .46, .38, .48,
                  .10, .12, .16)
            g.drum(name(f'wingtip pod {side}'), 'dark',
                   (X(side * .955), Y(.44), Z(.53)), beam * .050,
                   length * .05, sides=10)
            g.ring(name(f'wingtip pod collar {side}'), 'trim',
                   X(side * .955), Y(.44),
                   [(Z(.505), beam * .058, beam * .048),
                    (Z(.509), beam * .058, beam * .048)], n=10)
    else:
        flank('port armour citadel', 'base', .20, .68, .18, .42,
              lambda z: (-half_at(z) * .90, -.97))
        flank('port citadel rail', 'trim', .24, .64, .42, .445,
              lambda z: (-half_at(z) * .92, -.945))
        flank('starboard sponson', 'base', .28, .58, .22, .40,
              lambda z: (half_at(z) * .90, .62))
        flank('starboard sponson rail', 'trim', .32, .54, .40, .422,
              lambda z: (half_at(z) * .92, .598))
    for j in range(3):
        z = .30 + j * .13
        band(f'port citadel light {j}', 'lit', -1, z, z + .05, .385, .405,
             .004, inner=.985)
    for j in range(2):
        z = .36 + j * .12
        band(f'sponson light {j}', 'lit', 1, z, z + .05, .368, .388, .004,
             inner=1.235)

    # ---- starboard truss and its counterweight drum ----------------------
    g.strut(name('outrigger main spar'), 'base',
            (X(.60), Y(.30), Z(.40)), (X(.99), Y(.34), Z(.46)), beam * .026)
    g.lattice(name('outrigger truss web'), 'trim',
              (X(.63), Y(.28), Z(.41)), (X(.97), Y(.32), Z(.45)),
              bays=2 if kind == 'bomber' else 4, thickness=beam * .009,
              width=beam * .040)
    g.drum(name('counterweight drum'), 'dark',
           (X(.97), Y(.34), Z(.46)), beam * .046, length * .046, sides=12)
    for side in (-1, 1):
        g.ring(name(f'counterweight cradle {side}'), 'base', X(.97), Y(.34),
               [(Z(.46 + side * .017), beam * .054, beam * .044),
                (Z(.46 + side * .019), beam * .054, beam * .044)], n=12)
        g.strut(name(f'counterweight stay {side}'), 'trim',
                (X(.97), Y(.34), Z(.46 + side * .017)),
                (X(.62), Y(.30), Z(.38 + side * .04)), beam * .008)

    # ---- flank detailing: flush channels, cassettes, ownership bands ------
    rows = int(cfg['rows'])
    lo_y = cfg['bottom'] + .30
    hi_y = cfg['top'] - .10
    step = (hi_y - lo_y) / max(1, rows)
    for side in (-1, 1):
        band(f'service trench {side}', 'dark', side, .20, .62, lo_y, hi_y,
             .004, inner=.985)
        for k in range(rows):
            y0 = lo_y + k * step + step * .18
            band(f'trench cassette {side} {k}', 'trim', side, .24 + k * .02,
                 .58 - k * .02, y0, y0 + step * .30, .010, inner=.99)
        band(f'ownership band {side}', 'accent', side, .30, .52, hi_y + .006,
             hi_y + .034, .006, inner=.99)

    # ---- external reactor drums in load cradles --------------------------
    drum_y = cfg['deck_top'] + .055
    for j in range(int(cfg['drums'])):
        z = .26 + j * (.24 / max(1, int(cfg['drums']) - 1))
        x = -half_at(z, deck_st) * .84
        # Pedestal first: a drum that only floats above the deck fails the part
        # contact check's intent even when two bounding boxes happen to touch.
        block(f'drum pedestal {j}', 'base', x, cfg['deck_top'] + .012, z,
              .080, .036, .050)
        g.drum(name(f'reactor drum {j}'), 'trim', (X(x), Y(drum_y), Z(z)),
               beam * .050, length * .044, sides=10)
        for side in (-1, 1):
            g.ring(name(f'drum cradle {j} {side}'), 'base', X(x), Y(drum_y),
                   [(Z(z + side * .016), beam * .058, beam * .048),
                    (Z(z + side * .018), beam * .058, beam * .048)], n=10)
        # Short feed pipe straight off the drum crown into the pedestal: a long
        # diagonal conduit reads as a stray wire crossing the deck.
        g.ring(name(f'drum feed pipe {j}'), 'cool', X(x), Y(drum_y),
               [(Z(z), beam * .012, beam * .006),
                (Z(z + .028), beam * .012, beam * .006)], n=8)

    # ---- one strong command tower, offset to port ------------------------
    tower_z = cfg['tower_z']
    tower_x = -half_at(tower_z, deck_st) * .40
    y = cfg['deck_top'] - .02
    fixed = .012 + .022 + .012 + .006
    room = .994 - fixed - y
    for k, (share, w, d, role, dz) in enumerate(
            ((.44, .26, .20, 'base', 0.0), (.26, .22, .16, 'trim', .012),
             (.20, .17, .13, 'dark', .022), (.10, .13, .11, 'base', .030))):
        h = room * share
        block(f'tower step {k}', role, tower_x, y + h / 2, tower_z - dz, w, h, d)
        y += h
    for side in (-1, 1):
        for j in range(6 if kind != 'bomber' else 3):
            block(f'bridge viewport {side} {j}', 'lit', tower_x + side * .062,
                  y - .014, tower_z + .028 + (j - 2.5) * .0072, .004, .012,
                  .0055)
    block('tower brow', 'trim', tower_x, y + .006, tower_z + .02, .18, .012, .09)
    y += .012
    block('sensor mast', 'base', tower_x, y + .011, tower_z + .014, .06, .022,
          .045)
    y += .022
    block('mast crown', 'trim', tower_x, y + .006, tower_z + .014, .036, .012,
          .030)
    y += .012
    block('rangefinder optic', 'cool', tower_x, y + .003, tower_z + .022, .014,
          .006, .010)

    # ---- main battery: turrets on the spine, casemates on the sponsons ---
    for j in range(int(cfg['turrets'])):
        z = .34 + j * .105
        x = half_at(z, deck_st) * .10
        base_y = cfg['deck_top'] + .06
        loft(f'turret barbette {j}', 'dark',
             [(z - .028, .085, base_y + .05, cfg['deck_top'] + .01),
              (z + .028, .085, base_y + .05, cfg['deck_top'] + .01)], x)
        loft(f'turret house {j}', 'base',
             [(z - .026, .075, base_y + .11, base_y + .04),
              (z + .006, .082, base_y + .115, base_y + .04),
              (z + .030, .060, base_y + .09, base_y + .05)], x)
        block(f'turret roof {j}', 'trim', x, base_y + .122, z, .11, .010, .038)
        for side in (-1, 1):
            bx = x + side * .026
            g.ring(name(f'gun barrel {j} {side}'), 'dark', X(bx),
                   Y(base_y + .085),
                   [(Z(z + .030), beam * .012, beam * .007),
                    (Z(z + .075), beam * .011, beam * .0065)], n=8)
            g.ring(name(f'open muzzle {j} {side}'), 'trim', X(bx),
                   Y(base_y + .085),
                   [(Z(z + .073), beam * .015, beam * .010),
                    (Z(z + .082), beam * .014, beam * .010)], n=8)
            g.disc(name(f'recessed bore {j} {side}'), 'dark', X(bx),
                   Y(base_y + .085), Z(z + .076), beam * .0095,
                   length * .0012, n=8)
        block(f'turret marking {j}', 'accent', x, base_y + .128, z - .004,
              .045, .004, .010)
    for j in range(int(cfg['casemates'])):
        side = 1 if j % 2 else -1
        z = .30 + (j // 2) * .10
        x = side * (.62 if side > 0 else .90)
        block(f'casemate housing {j}', 'dark', x, .30, z, .05, .07, .06)
        g.ring(name(f'casemate barrel {j}'), 'trim', X(x + side * .03),
               Y(.30), [(Z(z), beam * .010, beam * .006),
                        (Z(z + .035), beam * .009, beam * .0055)], n=8)
        g.disc(name(f'casemate bore {j}'), 'dark', X(x + side * .03), Y(.30),
               Z(z + .033), beam * .0055, length * .001, n=8)

    # ---- salvage deck: one-sided mouths and crane jibs -------------------
    for j in range(int(cfg['mouths'])):
        z = .32 + j * .11
        x = -half_at(z) * .96
        block(f'salvage deck mouth {j}', 'dark', x, .26, z, .06, .09, .07)
        block(f'salvage mouth light {j}', 'lit', x, .30, z, .05, .005, .006)
        g.strut(name(f'salvage crane jib {j}'), 'trim',
                (X(x * .92), Y(.30), Z(z - .03)), (X(x * 1.06), Y(.42), Z(z)),
                beam * .007)

    # ---- drive block: emitters inside annular throats --------------------
    for j in range(int(cfg['drives'])):
        x = -(cfg['hull'] * .52) + (j % 3) * (cfg['hull'] * .52)
        y = .22 if j < 3 else .40
        r = beam * (.080 if kind != 'bomber' else .10)
        loft(f'drive housing {j}', 'base',
             [(.05, r / beam * .95, y + r / height * .85, y - r / height * .85),
              (.12, r / beam * 1.02, y + r / height * .96, y - r / height * .96),
              (.22, r / beam * .62, y + r / height * .60, y - r / height * .60)],
             x)
        g.ring(name(f'hollow thrust throat {j}'), 'dark', X(x), Y(y),
               [(Z(.055), r * .90, r * .60), (Z(.036), r * .94, r * .66),
                (Z(.016), r * .99, r * .74), (Z(.001), r, r * .78)], n=12)
        g.ring(name(f'exhaust lip {j}'), 'trim', X(x), Y(y),
               [(Z(.009), r * 1.004, r * .78), (Z(.001), r * 1.004, r * .78)],
               n=12)
        g.disc(name(f'cyan drive emitter {j}'), 'cool', X(x), Y(y), Z(.011),
               r * .73, length * .0014, n=12)

    # ---- deck hardware ---------------------------------------------------
    for side in (-1, 1):
        for j in range(3):
            z = .34 + j * .11
            block(f'deck conduit {side} {j}', 'trim',
                  side * half_at(z, deck_st) * .90, cfg['deck_top'] + .006, z,
                  .010, .006, .09)
            block(f'mooring cleat {side} {j}', 'base',
                  side * half_at(z) * .90, cfg['top'] + .010, z + .04,
                  .030, .018, .016)
    block('lit landing strip', 'lit', -half_at(.46, deck_st) * .86,
          cfg['deck_top'] + .004, .46, .008, .003, .14)
    block('bow optic', 'cool', 0, cfg['top'] * .40, .975, .014, .006, .008)

    # ---- class-specific superstructure ----------------------------------
    if kind == 'supercapital':
        for side in (-1, 1):
            loft(f'machinery terrace {side}', 'base',
                 [(.30, .10, cfg['deck_top'] + .14, cfg['top'] - .02),
                  (.46, .12, cfg['deck_top'] + .18, cfg['top'] - .02),
                  (.64, .08, cfg['deck_top'] + .10, cfg['top'] - .04)],
                 x=side * .28)
            # On the terrace's outer face, inside its own height, so the strip
            # is welded into the volume instead of floating above its roof.
            block(f'terrace light band {side}', 'lit', side * .395, .70, .46,
                  .010, .006, .08)
        for j, z in enumerate((.32, .48, .64)):
            for side in (-1, 1):
                g.strut(name(f'cathedral gantry leg {j} {side}'), 'trim',
                        (X(side * .15), Y(cfg['deck_top']), Z(z)),
                        (X(side * .085), Y(.93), Z(z)), beam * .008)
            g.strut(name(f'cathedral gantry beam {j}'), 'trim',
                    (X(-.085), Y(.93), Z(z)), (X(.085), Y(.93), Z(z)),
                    beam * .008)
    elif kind == 'bomber':
        loft('strike spine', 'base',
             [(.22, .13, cfg['deck_top'] + .08, cfg['top'] - .02),
              (.38, .15, cfg['deck_top'] + .12, cfg['top'] - .02),
              (.56, .09, cfg['deck_top'] + .05, cfg['top'] - .04)])
