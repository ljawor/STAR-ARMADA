"""Rim Syndicate fleet rework: the 23 bindings that predate the capital batch.

Geometry only, no scene side effects. Y is up and +Z is forward, and every part
is placed from frame fractions of the binding's approved containment box, so a
class can change proportion and detail but never size.

The vocabulary is the one the approved Marauder/Leviathan batch established:
welded barge volumes, plate belts that follow the taper, exposed reactor drums in
cradles, a port armour sponson opposed by a starboard truss, blunt salvage prows
and drive emitters inside annular throats. Stations and ground hardware take the
same language into their own idiom: a horizontal spine with a docking hoop, a
trussed gantry instead of a deckhouse, drums and silos instead of turrets.
"""
import math

HULLS = ('corvette', 'frigate', 'cruiser', 'convoy', 'colonizer', 'constructor')
STATIONS = ('command_station', 'defense_platform', 'energy_relay', 'fighter_platform',
            'mining_station', 'repair_dock', 'research_station', 'sensor_station',
            'shipyard', 'trade_station')
SATELLITES = ('attack_satellite', 'defense_satellite')
INSTALLATIONS = ('planet_extractor', 'planet_pulsar_cannon', 'planet_shield_generator',
                 'planet_trade_hub')
KINDS = HULLS + ('fighter',) + STATIONS + SATELLITES + INSTALLATIONS

# Per-class plan. Values are frame fractions, never world units.
HULL_CFG = {
    'corvette': dict(turrets=1, casemates=2, drums=2, drives=2, tower=.30, prow=.86,
                     belt=1, truss=0, transport=None),
    'frigate': dict(turrets=2, casemates=2, drums=3, drives=3, tower=.34, prow=.88,
                    belt=2, truss=1, transport=None),
    'cruiser': dict(turrets=3, casemates=4, drums=4, drives=4, tower=.30, prow=.90,
                    belt=2, truss=1, transport=None),
    'convoy': dict(turrets=0, casemates=0, drums=3, drives=3, tower=.42, prow=.90,
                   belt=0, truss=1, transport='containers'),
    'colonizer': dict(turrets=0, casemates=0, drums=2, drives=3, tower=.40, prow=.88,
                      belt=1, truss=0, transport='habitat'),
    'constructor': dict(turrets=0, casemates=0, drums=2, drives=2, tower=.44, prow=.86,
                        belt=0, truss=1, transport='crane'),
}

STATION_CFG = {
    'shipyard': dict(kit='shipyard', arms=6, hoop=.82, drum=.26, tower=.30),
    'command_station': dict(kit='command', arms=6, hoop=.72, drum=.22, tower=.46),
    'mining_station': dict(kit='mining', arms=4, hoop=.60, drum=.30, tower=.22),
    'repair_dock': dict(kit='repair', arms=4, hoop=.74, drum=.24, tower=.24),
    'research_station': dict(kit='research', arms=5, hoop=.70, drum=.22, tower=.26),
    'sensor_station': dict(kit='sensor', arms=3, hoop=.48, drum=.20, tower=.40),
    'trade_station': dict(kit='trade', arms=5, hoop=.74, drum=.24, tower=.20),
    'energy_relay': dict(kit='relay', arms=4, hoop=.54, drum=.28, tower=.34),
    'fighter_platform': dict(kit='hangar', arms=4, hoop=.56, drum=.28, tower=.26),
    'defense_platform': dict(kit='defense', arms=4, hoop=.62, drum=.34, tower=.18),
}

SAT_CFG = {
    'attack_satellite': dict(kind='attack', wings=1, core=.30, kit=2),
    'defense_satellite': dict(kind='defense', wings=1, core=.34, kit=3),
}

INSTALL_CFG = {
    'planet_extractor': dict(kit='drill', base=.22, mast=.62),
    'planet_pulsar_cannon': dict(kit='cannon', base=.24, mast=.50),
    'planet_shield_generator': dict(kit='dome', base=.26, mast=.44),
    'planet_trade_hub': dict(kit='depot', base=.24, mast=.58),
}


class Frame:
    """Frame fractions in, world coordinates out, always inside the box."""

    def __init__(self, g, frame, label):
        self.g = g
        self.label = label
        lo = [float(v) + .004 for v in frame['lo']]
        hi = [float(v) - .004 for v in frame['hi']]
        self.lo, self.hi = lo, hi
        self.cx = (lo[0] + hi[0]) / 2
        self.beam = (hi[0] - lo[0]) / 2
        self.y0, self.y1 = lo[1], hi[1]
        self.z0, self.z1 = lo[2], hi[2]
        self.height = self.y1 - self.y0
        self.length = self.z1 - self.z0

    def X(self, v):
        return self.cx + self.beam * v

    def Y(self, v):
        return self.y0 + self.height * v

    def Z(self, v):
        return self.z0 + self.length * v

    def SX(self, v):
        """A size along X from a beam fraction."""
        return self.beam * 2 * v

    def SY(self, v):
        return self.height * v

    def SZ(self, v):
        return self.length * v

    def name(self, part):
        return self.label + ' / ' + part

    def loft(self, name, role, stations, **kw):
        """Lofts are always centred on the box, never on the world origin."""
        kw.setdefault('x', self.cx)
        return self.g.loft(name, role, stations, **kw)

    def aspect(self):
        return (self.beam * 2) / self.length if self.length else 1.


def _cladding(f, n, *, y_lo, y_hi, x_frac, z_lo, z_hi, size, roles=('trim', 'dark', 'base')):
    """Deterministic welded detail: hatches, vents and junction boxes on a face.

    Positions come from a fixed arithmetic sequence, so a rebuild is byte-stable;
    each box is seated inside the parent surface rather than floating on it.
    """
    g = f.g
    for j in range(n):
        side = -1 if j % 2 else 1
        t = (j * 0.6180339887) % 1.
        y = f.Y(y_lo + (y_hi - y_lo) * t)
        z = f.Z(z_lo + (z_hi - z_lo) * ((j * 0.4142135623) % 1.))
        role = roles[j % len(roles)]
        g.box(f.name(f'cladding {j}'), role,
              (f.X(side * x_frac), y, z),
              (f.beam * size * 1.6, f.SY(size * .9), f.SZ(size * 1.3)))
        if j % 4 == 1:
            g.drum(f.name(f'vent drum {j}'), 'dark',
                   (f.X(side * (x_frac + .02)), y, z), f.beam * size * .5,
                   f.SZ(size * .8))


def _hoop(f, label, y, radius, n, thickness, role='trim'):
    """Horizontal docking hoop built from struts: open, weldable, no thin card."""
    pts = [(f.cx + radius * math.cos(j * 2 * math.pi / n), y,
            f.Z(.5) + radius * math.sin(j * 2 * math.pi / n)) for j in range(n)]
    for j in range(n):
        f.g.strut(f.name(f'{label} {j}'), role, pts[j], pts[(j + 1) % n], thickness)


def _turret(f, label, z, scale=1.0, role='dark'):
    """Drum housing plus a pair of barrels: reads as a mount from every angle."""
    g = f.g
    base = f.Y(.68)
    r = f.beam * .11 * scale
    g.drum(f.name(label + ' housing'), role, (f.cx, base, f.Z(z)), r, f.SZ(.07) * scale)
    g.ring(f.name(label + ' collar'), 'trim', f.cx, base,
           [(f.Z(z) + f.SZ(.030) * scale, r * 1.06, r * .92),
            (f.Z(z) + f.SZ(.038) * scale, r * 1.06, r * .92)], n=10)
    for side in (-1, 1):
        g.box(f.name(label + ' barrel'), 'trim',
              (f.cx + side * r * .42, base + r * .30, f.Z(z) + f.SZ(.055) * scale),
              (r * .26, r * .26, f.SZ(.090) * scale))


def build(kind, g, frame):
    if kind not in KINDS:
        raise ValueError('Unsupported Syndicate kind: ' + str(kind))
    f = Frame(g, frame, kind.replace('_', ' ').title())
    if kind == 'fighter':
        _fighter(f)
    elif kind in HULLS:
        _hull(f, HULL_CFG[kind])
    elif kind in STATIONS:
        _station(f, STATION_CFG[kind])
    elif kind in SATELLITES:
        _satellite(f, SAT_CFG[kind])
    else:
        _installation(f, INSTALL_CFG[kind])
    return ensure_roles(f)


def ensure_roles(f):
    """Every asset ships six material batches; a class missing one gets a trim.

    The runtime draws one call per role, so a role with no geometry is a budget
    mismatch rather than a saving. Missing roles get the smallest honest part:
    a lamp, a vent or an ownership band on the spine.
    """
    g = f.g
    def roles_present():
        return {obj['role'] for obj in g.bpy.context.scene.objects if obj.type == 'MESH'}
    missing = [role for role in ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
               if role not in roles_present()]
    for j, role in enumerate(missing):
        g.box(f.name('fitment band ' + role), role,
              (f.cx + (j - 1) * f.beam * .04, f.Y(.50), f.Z(.50 + j * .01)),
              (f.beam * .10, f.SY(.03), f.SZ(.02)))
    return missing


# ---------------------------------------------------------------- hulls ------
def _hull(f, cfg):
    g = f.g
    hw = .30
    stations = [(.02, hw * .72, .40, .10), (.16, hw * .92, .50, .06),
                (.40, hw, .52, .04), (.66, hw * .84, .50, .08),
                (.84, hw * .58, .44, .16), (.98, hw * .30, .34, .26)]
    f.loft(f.name('hull'), 'base',
           [(f.Z(z), f.beam * w, f.Y(t), f.Y(b)) for z, w, t, b in stations])
    # deckhouse and bridge: the silhouette's second volume
    f.loft(f.name('deckhouse'), 'dark',
           [(f.Z(.24), f.beam * hw * .60, f.Y(.66), f.Y(.48)),
            (f.Z(.42), f.beam * hw * .66, f.Y(.70), f.Y(.48)),
            (f.Z(.62), f.beam * hw * .50, f.Y(.64), f.Y(.48))])
    g.box(f.name('bridge'), 'trim',
          (f.cx, f.Y(.66 + cfg['tower'] * .10), f.Z(.40)),
          (f.beam * hw * .52, f.SY(cfg['tower'] * .22), f.SZ(.13)))
    g.box(f.name('bridge lamps'), 'lit',
          (f.cx, f.Y(.62 + cfg['tower'] * .16), f.Z(.44)),
          (f.beam * hw * .34, f.SY(.012), f.SZ(.09)))

    # port armour sponson: welded plate that follows the taper
    for row in range(max(cfg['belt'], 0)):
        y0 = .12 + row * .10
        g.prism(f.name(f'armour belt {row}'), 'base',
                f.Y(y0), f.Y(y0 + .09),
                [(f.X(-hw * 1.34), f.Z(.18)), (f.X(-hw * .30), f.Z(.16)),
                 (f.X(-hw * .30), f.Z(.80)), (f.X(-hw * 1.20), f.Z(.74))])
    if cfg['casemates']:
        for j in range(cfg['casemates']):
            z = .24 + j * (.52 / cfg['casemates'])
            g.box(f.name(f'casemate {j}'), 'dark',
                  (f.X(-hw * 1.05), f.Y(.26), f.Z(z)),
                  (f.beam * .10, f.SY(.08), f.SZ(.045)))

    # starboard truss with a counterweight drum: the faction's asymmetry
    if cfg['truss']:
        # starboard outrigger boom: a welded tube, not a bundle of loose braces
        f.loft(f.name('outrigger boom'), 'trim',
               [(f.Z(.28), f.beam * .045, f.Y(.37), f.Y(.29)),
                (f.Z(.34), f.beam * .060, f.Y(.38), f.Y(.28)),
                (f.Z(.70), f.beam * .060, f.Y(.38), f.Y(.28)),
                (f.Z(.76), f.beam * .042, f.Y(.36), f.Y(.30))],
               x=f.X(hw * 1.55))
        for z in (.34, .52, .70):
            g.strut(f.name('boom stay'), 'trim',
                    (f.X(hw * .96), f.Y(.40), f.Z(z)),
                    (f.X(hw * 1.50), f.Y(.37), f.Z(z)), f.beam * .024)
        g.drum(f.name('counterweight drum'), 'base',
               (f.X(hw * 1.55), f.Y(.33), f.Z(.80)), f.beam * .11, f.SZ(.10))

    for j in range(cfg['drums']):
        z = .30 + j * (1.0 / max(cfg['drums'], 1)) * .52
        side = -1 if j % 2 == 0 else 1
        g.drum(f.name(f'reactor drum {j}'), 'base',
               (f.X(side * hw * 1.20), f.Y(.18), f.Z(z)), f.beam * .075, f.SZ(.10))
        g.ring(f.name(f'drum cradle {j}'), 'trim', f.X(side * hw * 1.20), f.Y(.18),
               [(f.Z(z - .01), f.beam * .095, f.beam * .078),
                (f.Z(z + .01), f.beam * .095, f.beam * .078)], n=10)

    for j in range(cfg['turrets']):
        z = .30 + (j + .5) * (.42 / max(cfg['turrets'], 1))
        _turret(f, f'centreline turret {j}', z, 1.0)

    # drive throats: emitters sit inside an open bore, never behind a cap
    for j in range(cfg['drives']):
        off = (j - (cfg['drives'] - 1) / 2) * .16
        g.ring(f.name(f'drive throat {j}'), 'dark', f.X(off * 1.2), f.Y(.30),
               [(f.Z(.012), f.beam * .13, f.beam * .085),
                (f.Z(.055), f.beam * .15, f.beam * .10)], n=10)
        g.disc(f.name(f'drive emitter {j}'), 'cool',
               f.X(off * 1.2), f.Y(.30), f.Z(.034), f.beam * .075, f.SZ(.012), n=10)

    # blunt salvage prow with ram jaws
    # salvage ram: a blunt welded cap that stays inside the loft's own taper
    g.box(f.name('ram plate'), 'trim',
          (f.cx, f.Y(.31), f.Z(.95)),
          (f.beam * hw * .68, f.SY(.09), f.SZ(.045)))
    for side in (-1, 1):
        g.box(f.name('ram jaw'), 'dark',
              (f.X(side * hw * .30), f.Y(.30), f.Z(.93)),
              (f.beam * .07, f.SY(.15), f.SZ(.08)))

    _hull_detail(f, hw)
    _transport_kit(f, cfg.get('transport'))
    _cladding(f, 38, y_lo=.12, y_hi=.44, x_frac=hw * .82, z_lo=.14, z_hi=.84, size=.05)
    # Ownership bands: the faction's ochre stripe, welded on both flanks and the arms
    for side in (-1, 1):
        g.box(f.name('ownership band'), 'accent',
              (f.X(side * hw * .90), f.Y(.46), f.Z(.52)),
              (f.beam * .04, f.SY(.05), f.SZ(.34)))
        g.box(f.name('arm band'), 'accent',
              (f.X(side * .58), f.Y(.325), f.Z(.50)),
              (f.beam * .16, f.SY(.045), f.SZ(.07)))
    # Lateral outriggers: a pylon arm carrying a slim nacelle, the salvage
    # barge's working hulls. The arm is welded into the flank and the nacelle
    # carries its own drive throat, so the width is engineering, not a plate.
    reach = .90 if f.aspect() > .50 else .62
    for side in (-1, 1):
        g.prism(f.name('outrigger arm'), 'base',
                f.Y(.29), f.Y(.34),
                [(f.X(side * hw * .70), f.Z(.44)), (f.X(side * reach * .80), f.Z(.40)),
                 (f.X(side * reach * .80), f.Z(.52)), (f.X(side * hw * .70), f.Z(.60))])
        g.strut(f.name('outrigger brace'), 'trim',
                (f.X(side * hw * .86), f.Y(.44), f.Z(.50)),
                (f.X(side * reach * .70), f.Y(.34), f.Z(.50)), f.beam * .022)
        g.loft(f.name('outrigger nacelle'), 'dark',
               [(f.Z(.26), f.beam * .070, f.Y(.40), f.Y(.32)),
                (f.Z(.32), f.beam * .100, f.Y(.42), f.Y(.30)),
                (f.Z(.46), f.beam * .110, f.Y(.43), f.Y(.29)),
                (f.Z(.60), f.beam * .100, f.Y(.42), f.Y(.30)),
                (f.Z(.68), f.beam * .062, f.Y(.39), f.Y(.32))],
               x=f.X(side * reach * .88))
        g.ring(f.name('nacelle throat'), 'trim', f.X(side * reach * .88), f.Y(.335),
               [(f.Z(.245), f.beam * .062, f.beam * .040),
                (f.Z(.285), f.beam * .075, f.beam * .050)], n=10)
        g.disc(f.name('nacelle emitter'), 'cool', f.X(side * reach * .88), f.Y(.335),
               f.Z(.262), f.beam * .038, f.SZ(.010), n=10)
        g.box(f.name('runner lamp'), 'lit' if side < 0 else 'cool',
              (f.X(side * reach * .88), f.Y(.425), f.Z(.50)),
              (f.beam * .04, f.SY(.02), f.SZ(.06)))
    for j, role in enumerate(('lit', 'cool')):
        g.box(f.name(f'flank lamp {j}'), role,
              (f.X((1 if j else -1) * hw * .80), f.Y(.42), f.Z(.52)),
              (f.beam * .05, f.SY(.03), f.SZ(.08)))


def _module(f, label, loc, size, role):
    """A bolted working module, not a bare box: corner posts, a weld seam, a hatch.

    Bare accent boxes were the weakest read on the stations: a flat slab of colour
    where the eye expects a manufactured volume. Four posts, a seam band, a lit hatch
    and a vent are enough to turn the same silhouette into hardware.
    """
    g = f.g
    x, y, z = loc
    sx, sy, sz = size
    g.box(label, role, loc, size)
    post = min(sx, sz) * .18
    for i in (-1, 1):
        for k in (-1, 1):
            g.box(f'{label} post', 'trim',
                  (x + i * (sx / 2 - post / 2), y, z + k * (sz / 2 - post / 2)),
                  (post, sy * 1.05, post))
    g.box(f'{label} seam', 'dark', (x, y, z), (sx * 1.04, sy * .12, sz * 1.04))
    g.box(f'{label} hatch', 'lit', (x, y + sy / 2, z), (sx * .36, sy * .03, sz * .20))
    g.box(f'{label} vent', 'dark', (x, y + sy / 2 - sy * .03, z - sz * .30),
          (sx * .46, sy * .05, sz * .08))


def _hull_detail(f, hw):
    """Deck ribs, a signal mast and flank pipe runs: the class's welded read."""
    g = f.g
    for j in range(5):
        z = .20 + j * .13
        g.box(f.name(f'deck rib {j}'), 'trim',
              (f.cx, f.Y(.505), f.Z(z)), (f.beam * hw * 1.1, f.SY(.016), f.SZ(.011)))
    g.strut(f.name('signal mast'), 'trim', (f.cx, f.Y(.50), f.Z(.30)),
            (f.cx, f.Y(.78), f.Z(.30)), f.beam * .022)
    for j, role in enumerate(('lit', 'cool')):
        g.box(f.name(f'mast lamp {j}'), role,
              (f.cx + (j * 2 - 1) * f.beam * .03, f.Y(.785), f.Z(.30)),
              (f.beam * .025, f.SY(.012), f.SZ(.020)))
    for side in (-1, 1):
        g.box(f.name('pipe run'), 'accent',
              (f.X(side * hw * .62), f.Y(.20), f.Z(.52)),
              (f.beam * .05, f.SY(.03), f.SZ(.60)))


def _transport_kit(f, style):
    """Container stacks, a habitat hoop or a construction crane replace turrets."""
    if not style:
        return
    g = f.g
    if style == 'containers':
        for row in range(2):
            for j in range(4):
                role = 'accent' if (row + j) % 3 == 0 else 'base'
                g.box(f.name(f'container {row} {j}'), role,
                      (f.cx + (row - .5) * f.beam * .34, f.Y(.60 + row * .06),
                       f.Z(.28 + j * .13)),
                      (f.beam * .26, f.SY(.10), f.SZ(.10)))
        g.lattice(f.name('cargo gantry'), 'trim',
                  (f.X(-.34), f.Y(.78), f.Z(.26)), (f.X(-.34), f.Y(.78), f.Z(.80)),
                  3, f.beam * .018, width=f.beam * .06)
    elif style == 'habitat':
        _hoop(f, 'habitat hoop', f.Y(.62), f.beam * .34, 12, f.beam * .028, role='base')
        for j in range(4):
            a = j * math.pi / 2 + math.pi / 4
            g.strut(f.name(f'habitat spoke {j}'), 'trim',
                    (f.cx, f.Y(.58), f.Z(.46)),
                    (f.cx + f.beam * .34 * math.cos(a), f.Y(.62),
                     f.Z(.46) + f.beam * .34 * math.sin(a)), f.beam * .022)
        g.box(f.name('habitat core'), 'accent',
              (f.cx, f.Y(.58), f.Z(.46)), (f.beam * .22, f.SY(.14), f.SZ(.16)))
    elif style == 'crane':
        g.lattice(f.name('crane mast'), 'trim',
                  (f.X(.30), f.Y(.52), f.Z(.30)), (f.X(.30), f.Y(.92), f.Z(.30)),
                  2, f.beam * .020, width=f.beam * .06)
        g.strut(f.name('crane arm'), 'trim',
                (f.X(.30), f.Y(.92), f.Z(.30)), (f.X(.62), f.Y(.84), f.Z(.46)),
                f.beam * .026)
        g.drum(f.name('crane winch'), 'dark',
               (f.X(.62), f.Y(.84), f.Z(.46)), f.beam * .05, f.SZ(.04))
        g.box(f.name('scaffold rack'), 'accent',
              (f.cx, f.Y(.56), f.Z(.66)), (f.beam * .40, f.SY(.10), f.SZ(.16)))


# ------------------------------------------------------------- enrichment ----
def _station_detail(f, cfg):
    """Hoop lighting, hull plates and drum cradles: detail that follows the ring."""
    g = f.g
    mid = f.Y(.50)
    hoop_r = min(f.beam * .86, f.length * .46) * cfg['hoop']
    for j in range(8):
        a = j * 2 * math.pi / 8
        g.box(f.name(f'hoop lamp {j}'), 'lit' if j % 2 else 'cool',
              (f.cx + hoop_r * math.cos(a), mid, f.Z(.50) + hoop_r * math.sin(a)),
              (f.beam * .030, f.SY(.035), f.beam * .030))
    for j in range(6):
        a = j * 2 * math.pi / 6 + .5
        r0 = min(f.beam * .30, hoop_r * .5)
        g.strut(f.name(f'hoop brace {j}'), 'trim',
                (f.cx + r0 * math.cos(a), mid, f.Z(.50) + r0 * math.sin(a)),
                (f.cx + hoop_r * .96 * math.cos(a), mid, f.Z(.50) + hoop_r * .96 * math.sin(a)),
                f.beam * .020)
    for j in range(4):
        side = -1 if j % 2 else 1
        g.drum(f.name(f'cradle drum {j}'), 'dark',
               (f.X(side * .12), f.Y(.455), f.Z(.28 + (j // 2) * .44)),
               f.beam * .055, f.SZ(.07))
    # inner service ring and the modules bolted to the main hoop
    inner = hoop_r * .54
    _hoop(f, 'service ring', mid, inner, 12, f.beam * .020, role='base')
    for j in range(8):
        a = j * 2 * math.pi / 8 + .39
        _module(f, f.name(f'hoop module {j}'),
                (f.cx + hoop_r * .90 * math.cos(a), mid + f.SY(.06),
                 f.Z(.50) + hoop_r * .90 * math.sin(a)),
                (f.beam * .10, f.SY(.09), f.beam * .10),
                ('trim', 'base', 'accent')[j % 3])
        g.strut(f.name(f'module stay {j}'), 'trim',
                (f.cx + inner * math.cos(a), mid, f.Z(.50) + inner * math.sin(a)),
                (f.cx + hoop_r * .86 * math.cos(a), mid, f.Z(.50) + hoop_r * .86 * math.sin(a)),
                f.beam * .016)
    _cladding(f, 40, y_lo=.44, y_hi=.56, x_frac=.05, z_lo=.10, z_hi=.90, size=.045,
              roles=('trim', 'base', 'dark'))


def _sat_detail(f, cfg):
    """Wing sub-panels, radiator fins and spar trusses."""
    g = f.g
    mid = f.Y(.50)
    for side in (-1, 1):
        for j in range(3):
            g.box(f.name(f'panel rib {j}'), 'trim',
                  (f.X(side * (.30 + j * .22)), mid + f.SY(.05), f.Z(.50)),
                  (f.beam * .05, f.SY(.03), f.SZ(.30)))
        g.prism(f.name('radiator fin'), 'accent',
                mid + f.SY(.05), mid + f.SY(.09),
                [(f.X(side * .60), f.Z(.34)), (f.X(side * .88), f.Z(.40)),
                 (f.X(side * .88), f.Z(.58)), (f.X(side * .60), f.Z(.64))])
        g.lattice(f.name('spar truss'), 'trim',
                  (f.X(side * .16), mid, f.Z(.50)), (f.X(side * .80), mid, f.Z(.50)),
                  3, f.beam * .014)
        g.drum(f.name('bus collar'), 'trim',
               (f.X(side * .18), mid, f.Z(.50)), f.beam * .05, f.SZ(.03), sides=10)
    _cladding(f, 18, y_lo=.46, y_hi=.54, x_frac=.04, z_lo=.30, z_hi=.68, size=.040)


def _install_detail(f, cfg):
    """Pad railings, a pipe network and gantry beams."""
    g = f.g
    top = f.Y(cfg['base']) + f.SY(.02)
    for j in range(6):
        for side in (-1, 1):
            g.box(f.name(f'rail post {j}'), 'trim',
                  (f.X(side * .84), top + f.SY(.03), f.Z(.36 + j * .056)),
                  (f.beam * .03, f.SY(.06), f.beam * .03))
            g.box(f.name(f'rail beam {j}'), 'trim',
                  (f.X(side * .84), top + f.SY(.06), f.Z(.38 + j * .056)),
                  (f.beam * .02, f.SY(.02), f.SZ(.06)))
    for j in range(3):
        g.box(f.name(f'pipe duct {j}'), 'accent',
              (f.cx, top + f.SY(.02), f.Z(.50 + (j - 1) * .07)),
              (f.beam * .70, f.SY(.03), f.beam * .03))
    g.lattice(f.name('service gantry'), 'trim',
              (f.X(-.60), f.Y(cfg['base'] + .18), f.Z(.44)),
              (f.X(.60), f.Y(cfg['base'] + .18), f.Z(.44)), 4, f.beam * .014,
              width=f.beam * .04)
    _cladding(f, 36, y_lo=.30, y_hi=.44, x_frac=.28, z_lo=.42, z_hi=.60, size=.05,
              roles=('base', 'trim', 'dark'))


def _fighter_detail(f, cfg=None):
    g = f.g
    for side in (-1, 1):
        g.box(f.name('missile rail'), 'trim',
              (f.X(side * .70), f.Y(.42), f.Z(.34)),
              (f.beam * .04, f.SY(.04), f.SZ(.26)))
        g.drum(f.name('missile pod'), 'accent',
               (f.X(side * .70), f.Y(.42), f.Z(.44)), f.beam * .035, f.SZ(.05), sides=8)
        g.strut(f.name('landing skid'), 'dark',
                (f.X(side * .16), f.Y(.34), f.Z(.26)),
                (f.X(side * .16), f.Y(.30), f.Z(.60)), f.beam * .020)
        g.box(f.name('intake'), 'dark',
              (f.X(side * .18), f.Y(.45), f.Z(.62)),
              (f.beam * .06, f.SY(.05), f.SZ(.12)))
    g.box(f.name('canopy frame'), 'trim',
          (f.cx, f.Y(.635), f.Z(.52)), (f.beam * .24, f.SY(.01), f.SZ(.26)))
    _cladding(f, 14, y_lo=.34, y_hi=.52, x_frac=.12, z_lo=.18, z_hi=.84, size=.04)


# --------------------------------------------------------------- fighter -----
def _fighter(f):
    g = f.g
    f.loft(f.name('fuselage'), 'base',
           [(f.Z(.06), f.beam * .18, f.Y(.56), f.Y(.34)),
            (f.Z(.30), f.beam * .26, f.Y(.60), f.Y(.30)),
            (f.Z(.66), f.beam * .22, f.Y(.58), f.Y(.32)),
            (f.Z(.94), f.beam * .10, f.Y(.50), f.Y(.42))])
    for side in (-1, 1):
        g.prism(f.name('wing'), 'base',
                f.Y(.44), f.Y(.50),
                [(f.X(side * .10), f.Z(.24)), (f.X(side * .96), f.Z(.16)),
                 (f.X(side * .96), f.Z(.40)), (f.X(side * .10), f.Z(.58))])
        g.box(f.name('tip pod'), 'dark',
              (f.X(side * .92), f.Y(.47), f.Z(.28)),
              (f.beam * .12, f.SY(.10), f.SZ(.16)))
    g.box(f.name('canopy'), 'cool',
          (f.cx, f.Y(.62), f.Z(.52)), (f.beam * .20, f.SY(.08), f.SZ(.22)))
    for side in (-1, 1):
        g.ring(f.name('drive throat'), 'dark', f.X(side * .12), f.Y(.44),
               [(f.Z(.02), f.beam * .10, f.beam * .06),
                (f.Z(.07), f.beam * .12, f.beam * .07)], n=8)
        g.disc(f.name('drive emitter'), 'cool',
               f.X(side * .12), f.Y(.44), f.Z(.045), f.beam * .055, f.SZ(.02), n=8)
    g.box(f.name('nose lamp'), 'lit',
          (f.cx, f.Y(.50), f.Z(.90)), (f.beam * .10, f.SY(.04), f.SZ(.06)))
    # dorsal spine, tail fins and gun pods: the Jackal's silhouette read
    g.box(f.name('dorsal spine'), 'trim',
          (f.cx, f.Y(.60), f.Z(.46)), (f.beam * .10, f.SY(.06), f.SZ(.52)))
    for side in (-1, 1):
        g.prism(f.name('tail fin'), 'base', f.Y(.52), f.Y(.60),
                [(f.X(side * .04), f.Z(.10)), (f.X(side * .30), f.Z(.06)),
                 (f.X(side * .26), f.Z(.30)), (f.X(side * .04), f.Z(.34))])
        g.box(f.name('gun pod'), 'dark',
              (f.X(side * .52), f.Y(.40), f.Z(.44)),
              (f.beam * .08, f.SY(.06), f.SZ(.30)))
        g.box(f.name('gun barrel'), 'trim',
              (f.X(side * .52), f.Y(.40), f.Z(.66)),
              (f.beam * .03, f.SY(.02), f.SZ(.22)))
        g.strut(f.name('pylon'), 'trim',
                (f.X(side * .30), f.Y(.44), f.Z(.30)),
                (f.X(side * .52), f.Y(.42), f.Z(.36)), f.beam * .022)
    _fighter_detail(f)
    _cladding(f, 10, y_lo=.36, y_hi=.56, x_frac=.10, z_lo=.20, z_hi=.78, size=.05)


# -------------------------------------------------------------- stations -----
def _station(f, cfg):
    """A trussed wheel: spine, docking hoop, spokes, then one working kit on top.

    The composition is deliberately hierarchical -- one readable hull, one ring
    and one purpose -- because a station is read at a glance from a distance.
    """
    g = f.g
    mid = f.Y(.50)
    hub_r = min(f.beam * .30, f.length * .15) * (cfg['drum'] / .24)
    hub_len = f.SZ(.24)
    # spine through the hub, the station's load path
    f.loft(f.name('spine'), 'base',
           [(f.Z(.03), f.beam * .07, f.Y(.54), f.Y(.46)),
            (f.Z(.30), f.beam * .10, f.Y(.55), f.Y(.45)),
            (f.Z(.70), f.beam * .10, f.Y(.55), f.Y(.45)),
            (f.Z(.97), f.beam * .06, f.Y(.53), f.Y(.47))])
    g.drum(f.name('hub drum'), 'dark', (f.cx, mid, f.Z(.50)), hub_r, hub_len)
    for z in (.38, .62):
        g.ring(f.name('hub collar'), 'trim', f.cx, mid,
               [(f.Z(z), hub_r * 1.08, hub_r * .90),
                (f.Z(z + .018), hub_r * 1.08, hub_r * .90)], n=12)
    # docking hoop: the faction's ring silhouette, welded to the spine by spokes
    hoop_r = min(f.beam * .86, f.length * .46) * cfg['hoop']
    _hoop(f, 'docking hoop', mid, hoop_r, 16, max(f.beam * .028, .9), role='trim')
    for j in range(cfg['arms']):
        a = j * 2 * math.pi / cfg['arms'] + .2
        g.strut(f.name(f'spoke {j}'), 'base',
                (f.cx, mid, f.Z(.50)),
                (f.cx + hoop_r * math.cos(a), mid, f.Z(.50) + hoop_r * math.sin(a)),
                f.beam * .034)
    for j in range(3):
        g.drum(f.name(f'fuel drum {j}'), 'base',
               (f.cx, f.Y(.44), f.Z(.20 + j * .10)), f.beam * .07, f.SZ(.08))
    g.box(f.name('reactor block'), 'dark',
          (f.cx, f.Y(.40), f.Z(.50)), (f.beam * .22, f.SY(.10), f.SZ(.16)))

    kit = cfg['kit']
    if kit == 'shipyard':
        for side in (-1, 1):
            g.lattice(f.name('berth rail'), 'trim',
                      (f.X(side * .52), f.Y(.74), f.Z(.16)),
                      (f.X(side * .52), f.Y(.74), f.Z(.84)), 2, f.beam * .034,
                      width=f.beam * .10)
            for j in range(3):
                g.strut(f.name('rail post'), 'trim',
                        (f.X(side * .52), f.Y(.74), f.Z(.24 + j * .26)),
                        (f.X(side * .20), f.Y(.57), f.Z(.24 + j * .26)),
                        f.beam * .028)
        for j in range(2):
            side = -1 if j else 1
            g.box(f.name(f'crane pedestal {j}'), 'dark',
                  (f.X(side * .52), f.Y(.745), f.Z(.44 + j * .12)),
                  (f.beam * .14, f.SY(.05), f.SZ(.10)))
            _module(f, f.name(f'crane house {j}'),
                    (f.X(side * .52), f.Y(.795), f.Z(.44 + j * .12)),
                    (f.beam * .19, f.SY(.08), f.SZ(.13)), 'accent')
            g.strut(f.name(f'crane jib {j}'), 'trim',
                    (f.X(side * .52), f.Y(.78), f.Z(.44 + j * .12)),
                    (f.X(side * .16), f.Y(.68), f.Z(.52 + j * .12)), f.beam * .022)
    elif kit == 'command':
        g.box(f.name('command tower'), 'base',
              (f.cx, f.Y(.50 + cfg['tower'] * .50), f.Z(.52)),
              (f.beam * .30, f.SY(cfg['tower']), f.SZ(.18)))
        g.box(f.name('tower lamps'), 'lit',
              (f.cx, f.Y(.50 + cfg['tower'] * .96), f.Z(.52)),
              (f.beam * .24, f.SY(.04), f.SZ(.13)))
        g.disc(f.name('command dish'), 'trim', f.cx, f.Y(.50 + cfg['tower'] * 1.02),
               f.Z(.52), f.beam * .16, f.SZ(.02), n=14)
    elif kit == 'mining':
        g.lattice(f.name('drill derrick'), 'trim',
                  (f.X(-.40), f.Y(.56), f.Z(.34)), (f.X(-.40), f.Y(.94), f.Z(.46)),
                  3, f.beam * .026, width=f.beam * .08)
        g.drum(f.name('drill head'), 'dark', (f.X(-.40), f.Y(.94), f.Z(.48)),
               f.beam * .09, f.SZ(.09))
        for j in range(2):
            g.drum(f.name(f'ore silo {j}'), 'base',
                   (f.X(.36), f.Y(.60), f.Z(.36 + j * .20)), f.beam * .14, f.SZ(.17))
        g.strut(f.name('conveyor'), 'accent',
                (f.X(-.26), f.Y(.74), f.Z(.46)), (f.X(.22), f.Y(.68), f.Z(.46)),
                f.beam * .030)
    elif kit == 'repair':
        for side in (-1, 1):
            g.strut(f.name('cradle arm'), 'trim',
                    (f.X(side * .24), f.Y(.58), f.Z(.46)),
                    (f.X(side * .78), f.Y(.50), f.Z(.70)), f.beam * .030)
            g.drum(f.name('cradle clamp'), 'dark',
                   (f.X(side * .78), f.Y(.50), f.Z(.72)), f.beam * .07, f.SZ(.05))
        g.lattice(f.name('repair gantry'), 'base',
                  (f.X(-.70), f.Y(.78), f.Z(.30)), (f.X(.70), f.Y(.78), f.Z(.30)),
                  4, f.beam * .022, width=f.beam * .06)
        for j in range(2):
            g.strut(f.name('gantry leg'), 'trim',
                    (f.X(-.70 + j * 1.40), f.Y(.78), f.Z(.30)),
                    (f.X(-.70 + j * 1.40), f.Y(.56), f.Z(.30)), f.beam * .024)
    elif kit == 'research':
        g.box(f.name('lab block'), 'base',
              (f.cx, f.Y(.66), f.Z(.50)), (f.beam * .34, f.SY(.16), f.SZ(.24)))
        g.strut(f.name('dish mast'), 'trim', (f.cx, f.Y(.72), f.Z(.50)),
                (f.cx, f.Y(.94), f.Z(.50)), f.beam * .022)
        g.disc(f.name('research dish'), 'trim', f.cx, f.Y(.94), f.Z(.50),
               f.beam * .20, f.SZ(.02), n=14)
        for j in range(2):
            g.box(f.name(f'lab pod {j}'), 'accent',
                  (f.X(.30 * (-1 if j else 1)), f.Y(.66), f.Z(.50)),
                  (f.beam * .14, f.SY(.10), f.SZ(.16)))
    elif kit == 'sensor':
        for j in range(3):
            a = j * 2 * math.pi / 3
            px = f.cx + f.beam * .42 * math.cos(a)
            pz = f.Z(.50) + f.length * .26 * math.sin(a)
            g.strut(f.name(f'antenna mast {j}'), 'trim', (px, f.Y(.58), pz),
                    (px, f.Y(.90), pz), f.beam * .018)
            g.disc(f.name(f'sensor dish {j}'), 'base', px, f.Y(.90), pz,
                   f.beam * .14, f.SZ(.015), n=14)
        g.box(f.name('sensor core'), 'dark',
              (f.cx, f.Y(.64), f.Z(.50)), (f.beam * .26, f.SY(.14), f.SZ(.20)))
    elif kit == 'trade':
        for j in range(4):
            side = -1 if j % 2 else 1
            _module(f, f.name(f'cargo stack {j}'),
                    (f.X(side * .30), f.Y(.62 + (j // 2) * .12), f.Z(.34 + (j % 2) * .32)),
                    (f.beam * .26, f.SY(.12), f.SZ(.20)),
                    'accent' if j % 3 == 0 else 'base')
        for side in (-1, 1):
            g.strut(f.name('docking boom'), 'trim',
                    (f.X(side * .16), mid, f.Z(.50)),
                    (f.X(side * .84), mid, f.Z(.60)), f.beam * .028)
    elif kit == 'relay':
        for j in range(4):
            g.disc(f.name(f'coil disc {j}'), 'cool' if j % 2 else 'trim',
                   f.cx, f.Y(.58 + j * .08), f.Z(.50), hub_r * .90, f.SY(.03), n=14)
        for j in range(4):
            a = j * 2 * math.pi / 4 + math.pi / 4
            px = f.cx + f.beam * .26 * math.cos(a)
            pz = f.Z(.50) + f.length * .13 * math.sin(a)
            g.strut(f.name(f'pylon {j}'), 'base', (px, mid, pz),
                    (px, f.Y(.84), pz), f.beam * .026)
    elif kit == 'hangar':
        g.box(f.name('hangar block'), 'base',
              (f.cx, f.Y(.66), f.Z(.34)), (f.beam * .50, f.SY(.16), f.SZ(.32)))
        g.box(f.name('hangar mouth'), 'lit',
              (f.cx, f.Y(.64), f.Z(.50)), (f.beam * .32, f.SY(.09), f.SZ(.04)))
        for side in (-1, 1):
            g.strut(f.name('launch rail'), 'trim',
                    (f.X(side * .14), f.Y(.74), f.Z(.20)),
                    (f.X(side * .14), f.Y(.74), f.Z(.84)), f.beam * .024)
    elif kit == 'defense':
        for j in range(4):
            a = j * 2 * math.pi / 4 + math.pi / 4
            g.prism(f.name(f'armour skirt {j}'), 'base',
                    f.Y(.40), f.Y(.54),
                    [(f.cx + f.beam * .34 * math.cos(a - .34),
                      f.Z(.50) + f.length * .20 * math.sin(a - .34)),
                     (f.cx + f.beam * .84 * math.cos(a - .16),
                      f.Z(.50) + f.length * .42 * math.sin(a - .16)),
                     (f.cx + f.beam * .84 * math.cos(a + .16),
                      f.Z(.50) + f.length * .42 * math.sin(a + .16)),
                     (f.cx + f.beam * .34 * math.cos(a + .34),
                      f.Z(.50) + f.length * .20 * math.sin(a + .34))])
        for j in range(3):
            g.drum(f.name(f'platform turret {j}'), 'dark',
                   (f.cx + f.beam * .26 * math.cos(j * 2.1), f.Y(.58),
                    f.Z(.50) + f.length * .16 * math.sin(j * 2.1)), f.beam * .09, f.SZ(.05))

    _station_detail(f, cfg)
    for j, role in enumerate(('lit', 'cool')):
        g.box(f.name(f'beacon {j}'), role,
              (f.cx + (j * 2 - 1) * f.beam * .06, f.Y(.545), f.Z(.10)),
              (f.beam * .04, f.SY(.05), f.SZ(.05)))


# ------------------------------------------------------------- satellites ----
def _satellite(f, cfg):
    g = f.g
    mid = f.Y(.50)
    core = min(f.beam, f.length / 2) * cfg['core']
    g.box(f.name('bus'), 'base', (f.cx, mid, f.Z(.50)),
          (core * 1.5, core * 1.1, core * 1.5))
    for side in (-1, 1):
        g.box(f.name('solar wing'), 'dark',
              (f.X(side * .55), mid + f.SY(.04), f.Z(.50)),
              (f.beam * .56, f.SY(.04), f.length * .34))
        g.strut(f.name('wing spar'), 'trim',
                (f.X(side * .10), mid, f.Z(.50)), (f.X(side * .84), mid, f.Z(.50)),
                f.beam * .024)
    if cfg['kind'] == 'attack':
        for j in range(cfg['kit']):
            g.drum(f.name(f'warhead {j}'), 'accent',
                   (f.cx + (j - (cfg['kit'] - 1) / 2) * core * .5, mid, f.Z(.80)),
                   core * .18, f.SZ(.14))
            g.box(f.name(f'warhead lamp {j}'), 'lit',
                  (f.cx + (j - (cfg['kit'] - 1) / 2) * core * .5, mid, f.Z(.88)),
                  (core * .12, core * .12, f.SZ(.03)))
    else:
        g.drum(f.name('defense turret'), 'dark', (f.cx, mid + core * .6, f.Z(.56)),
               core * .30, f.SZ(.08))
        for side in (-1, 1):
            g.box(f.name('armour petal'), 'base',
                  (f.X(side * .34), mid, f.Z(.38)),
                  (f.beam * .22, f.SY(.10), f.SZ(.22)))
    g.strut(f.name('sensor mast'), 'trim', (f.cx, mid + core * .4, f.Z(.50)),
            (f.cx, mid + f.SY(.32), f.Z(.50)), f.beam * .020)
    g.disc(f.name('mast dish'), 'trim', f.cx, mid + f.SY(.33), f.Z(.50),
           f.beam * .14, f.SZ(.012), n=14)
    g.box(f.name('mast lamp'), 'lit', (f.cx, mid + f.SY(.36), f.Z(.50)),
          (f.beam * .05, f.SY(.02), f.SZ(.04)))
    _sat_detail(f, cfg)


# ----------------------------------------------------------- installations ---
def _installation(f, cfg):
    """Ground hardware: a wide anchored pad, then a mast and the function kit."""
    g = f.g
    base_top = f.Y(cfg['base'])
    g.box(f.name('pad'), 'base', (f.cx, f.Y(cfg['base'] * .5), f.Z(.50)),
          (f.SX(.88), f.SY(cfg['base']), f.SZ(.30)))
    for sx in (-1, 1):
        for sz in (-1, 1):
            g.box(f.name('pad foot'), 'dark',
                  (f.X(sx * .80), f.Y(.06), f.Z(.5 + sz * .12)),
                  (f.beam * .12, f.SY(.10), f.beam * .12))
    g.box(f.name('control block'), 'trim',
          (f.X(-.40), f.Y(cfg['base'] + .10), f.Z(.34)),
          (f.beam * .30, f.SY(.18), f.SZ(.16)))
    g.box(f.name('control lamp'), 'lit',
          (f.X(-.40), f.Y(cfg['base'] + .19), f.Z(.34)),
          (f.beam * .18, f.SY(.02), f.SZ(.10)))
    _install_detail(f, cfg)
    mast_top = f.Y(cfg['base'] + cfg['mast'] * .70)
    f.loft(f.name('mast'), 'base',
           [(f.Z(.44), f.beam * .10, base_top + f.SY(.04), base_top),
            (f.Z(.52), f.beam * .13, mast_top, base_top),
            (f.Z(.58), f.beam * .10, mast_top - f.SY(.04), base_top)])
    kit = cfg['kit']
    if kit == 'drill':
        g.lattice(f.name('derrick'), 'trim',
                  (f.cx, base_top, f.Z(.50)), (f.cx, f.Y(.96), f.Z(.50)), 4,
                  f.beam * .022, width=f.beam * .08)
        g.drum(f.name('drill collar'), 'dark', (f.cx, f.Y(.80), f.Z(.50)),
               f.beam * .12, f.SY(.06))
        for side in (-1, 1):
            g.drum(f.name('slurry tank'), 'base',
                   (f.X(side * .52), f.Y(cfg['base']) + f.SY(.05), f.Z(.60)),
                   f.beam * .12, f.SZ(.18))
        g.strut(f.name('pipe run'), 'accent',
                (f.X(.40), f.Y(cfg['base']) + f.SY(.05), f.Z(.52)),
                (f.cx, f.Y(.72), f.Z(.50)), f.beam * .026)
    elif kit == 'cannon':
        g.drum(f.name('barrel housing'), 'dark',
               (f.cx, f.Y(cfg['base'] + cfg['mast'] * .55), f.Z(.50)),
               f.beam * .16, f.SZ(.20))
        g.drum(f.name('barrel'), 'trim',
               (f.cx, f.Y(cfg['base'] + cfg['mast'] * .55), f.Z(.76)),
               f.beam * .09, f.SZ(.42))
        for j in range(2):
            g.drum(f.name(f'capacitor {j}'), 'accent',
                   (f.X(.46 * (-1 if j else 1)), f.Y(cfg['base'] + .18), f.Z(.42)),
                   f.beam * .12, f.SZ(.18))
        g.disc(f.name('muzzle glow'), 'cool', f.cx,
               f.Y(cfg['base'] + cfg['mast'] * .55), f.Z(.96), f.beam * .075,
               f.SZ(.02), n=12)
    elif kit == 'dome':
        for j in range(3):
            g.disc(f.name(f'shield emitter {j}'), 'cool' if j == 2 else 'trim',
                   f.cx, f.Y(cfg['base'] + .16 + j * .10), f.Z(.50),
                   f.beam * (.34 - j * .07), f.SY(.05), n=16)
        for j in range(3):
            a = j * 2 * math.pi / 3
            px = f.cx + f.beam * .62 * math.cos(a)
            pz = f.Z(.50) + f.length * .22 * math.sin(a)
            g.strut(f.name(f'field pylon {j}'), 'base',
                    (px, base_top, pz), (px, f.Y(.72), pz), f.beam * .026)
            g.drum(f.name(f'pylon cap {j}'), 'trim', (px, f.Y(.72), pz),
                   f.beam * .05, f.SZ(.04))
        g.strut(f.name('field mast'), 'trim', (f.cx, f.Y(.60), f.Z(.50)),
                (f.cx, f.Y(.95), f.Z(.50)), f.beam * .024)
        g.disc(f.name('field lens'), 'lit', f.cx, f.Y(.96), f.Z(.50),
               f.beam * .12, f.SY(.02), n=12)
    elif kit == 'depot':
        for j in range(4):
            g.box(f.name(f'cargo module {j}'), 'accent' if j % 2 else 'base',
                  (f.X(.34 if j % 2 else -.34), f.Y(cfg['base'] + .12 + (j // 2) * .12),
                   f.Z(.70)),
                  (f.beam * .30, f.SY(.10), f.SZ(.18)))
        g.lattice(f.name('depot crane'), 'trim',
                  (f.X(.50), base_top, f.Z(.30)), (f.X(.50), f.Y(.86), f.Z(.30)), 2,
                  f.beam * .020, width=f.beam * .05)
        g.strut(f.name('crane jib'), 'trim',
                (f.X(.50), f.Y(.86), f.Z(.30)), (f.X(.20), f.Y(.80), f.Z(.48)),
                f.beam * .024)
        g.strut(f.name('sign mast'), 'trim', (f.X(-.62), base_top, f.Z(.30)),
                (f.X(-.62), f.Y(.66), f.Z(.30)), f.beam * .020)
        g.box(f.name('depot sign'), 'lit', (f.X(-.62), f.Y(.66), f.Z(.30)),
              (f.beam * .10, f.SY(.05), f.SZ(.10)))
