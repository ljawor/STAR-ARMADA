"""Weapon fire, beams and glows as primitives, mirroring the Python renderer's own rules.

Three things are decided here and nowhere else:

  * **which** effects and projectiles are drawn — the same fog predicates the renderer uses
    (`is_position_visible`, `effect_visible`), passed in as id sets so this module never re-derives
    a visibility answer;
  * **how a beam is layered** — a wide soft sheath, a bright sheath and a hot core, each at its own
    width and alpha (`renderer.py::_draw_effects`, the `beam` branch);
  * **how big a bolt is** — the same `projectile_extents` with a pixels-per-world of 1.0, which
    yields the *pixel* extents; the window scales them by its own camera.

Everything is emissive, so everything blends additive and writes no depth.
"""
from __future__ import annotations

from render_bridge import emissive as codec

BEAM_LIFETIME = 0.25            # renderer.py: a = max(0, 1 - t / 0.25)
BEAM_LAYERS = ((9.0, 0.80, 0.50), (3.0, 1.00, 1.00), (1.2, 1.00, 0.95))
GLOW_ENDPOINT = 14.0
GLOW_TARGET = 8.0
GLOW_TARGET_ALPHA = 0.35
JUMP_LIFETIME = 1.0
JUMP_RING_BASE = 60.0
JUMP_RING_GROWTH = 160.0
JUMP_RING_WIDTH = 2.5
JUMP_RING_COLOUR = (0.5, 0.7, 1.0)
HALO_ALPHA = 0.30
CORE_ALPHA = 0.95
CORE_WHITEN = 0.55
HALO_SCALE = (1.9, 2.6)        # BOLT_HALO in renderer.py
FIRE_LIFETIME = 2.0
EXPLOSION_LIFETIME = 1.5        # renderer.py::_draw_explosion `life`
EXPLOSION_SMALL_LIFETIME = 0.6  # the small blast fades out over 0.6 s
EXPLOSION_SMALL_SEED = 3
SHIELD_MIN_FRACTION = 0.001     # renderer.py::_draw_shields: `if frac <= 0.001: continue`
SHIELD_FADE = (0.20, 0.65)      # the renderer's alpha floor and ceiling (`_a_lo`, `_a_hi`)
SHIELD_SHIP_FACTOR = 1.08       # _shield_radius: ships sit at 1.08x their hull radius
SHIELD_STATION_FACTOR = 1.35    # ...and stations at 1.35x their own radius
SHIELD_BUCKETS = 8              # strength is quantised into eight shells (one display list each)
HIT_SHIELD_LIFETIME = 0.55      # render/hit_effects.py::hit_geometry `life` for a shield contact
HIT_HULL_LIFETIME = 0.42        # ...and for a bare-hull contact
HIT_KINDS = ('shield_hit', 'hull_hit', 'impact')

QUADRANTS = ('front', 'rear', 'left', 'right')


def _lift(colour, amount):
    return tuple(min(1.0, c * (1.0 - amount) + amount) for c in colour[:3])


def explosions(effects) -> tuple[list, int]:
    """One parameter record per live blast - the window rebuilds the layers from age and seed.

    `explosion_small` is the same phenomenon at half size and 0.55x the clock, with its own fade,
    exactly as the renderer draws it; both become the same record with different parameters.
    """
    out, skipped = [], 0
    for effect in effects:
        kind = effect.get('kind')
        if kind not in ('explosion', 'explosion_small'):
            continue
        age = effect.get('t', 0.0)
        size = float(effect.get('size', 40))
        seed = int(effect.get('seed', 0))
        if kind == 'explosion_small':
            if max(0.0, 1.0 - age / EXPLOSION_SMALL_LIFETIME) <= 0.0:
                skipped += 1
                continue
            size = max(10.0, size) * 0.5
            age = age * 0.55
            seed = EXPLOSION_SMALL_SEED
        if age >= EXPLOSION_LIFETIME:
            skipped += 1
            continue
        out.append(codec.explosion(effect['pos'], size, age, seed))
    return out, skipped


def hits(effects) -> tuple[list, int]:
    """Damage contacts as parameters: the window rebuilds the cap, the ripple and the sparks.

    A contact is ~90 triangles of curved shell plus seeded sparks, all derived from position,
    normal, size, age and seed - so those cross and the geometry does not. What stays on this side
    is every decision: the aperture is a function of the size the damage system chose, the ripple
    timing and the spark seeds come from the contact's own seed, and the colours are the renderer's
    cool/warm pair.

    The camera-dependent part stays on the window's side, where the camera is: the shield contact
    is floored to `SHIELD_MIN_PX` across and the hull contact to 7 px, both of which the renderer
    applies with its own `px_per_world`.
    """
    out, skipped = [], 0
    for effect in effects:
        kind = effect.get('kind')
        if kind not in HIT_KINDS:
            continue
        age = max(0.0, float(effect.get('t', 0.0)))
        life = HIT_SHIELD_LIFETIME if kind == 'shield_hit' else HIT_HULL_LIFETIME
        if age >= life:
            skipped += 1
            continue
        seed = int(effect.get('seed', 0))
        normal = effect.get('normal') or tuple(-v for v in effect.get('direction', (0.0, 0.0, -1.0)))
        visual_contact = bool(effect.get('visual_contact'))
        size = min(18.0, max(1.0, float(effect.get('size', 5.0))))
        if kind == 'shield_hit':
            centre = effect.get('center', effect['pos'])
            radius = float(effect.get('radius', 1.0))
            out.append(codec.shield_hit(centre, normal, radius, size, age, seed,
                                        visual_contact=visual_contact))
        else:
            out.append(codec.hull_hit(effect['pos'], normal, size, age, seed,
                                      visual_contact=visual_contact))
    return out, skipped


def beams(effects) -> tuple[list, int]:
    """The layered ribbon for every live beam, plus a count of the ones too old to draw."""
    out, skipped = [], 0
    for effect in effects:
        if effect.get('kind') != 'beam':
            continue
        fade = max(0.0, 1.0 - effect.get('t', 0.0) / BEAM_LIFETIME)
        if fade <= 0.0 or 'target_pos' not in effect:
            skipped += 1
            continue
        start, end = effect['pos'], effect['target_pos']
        colour = effect.get('color', (1.0, 1.0, 1.0))
        for width, gain, alpha in BEAM_LAYERS:
            tint = tuple(min(1.0, c + (0.5 if gain == 1.0 and width == 1.2 else 0.0))
                         for c in colour[:3])
            tint = tuple(c * gain for c in tint)
            out.append(codec.ribbon(start, end, width * 0.5, (*tint, fade * alpha)))
        out.append(codec.disc(start, GLOW_ENDPOINT, (*colour[:3], fade * 0.8)))
        if not effect.get('resolved_contact', False):
            out.append(codec.disc(end, GLOW_TARGET,
                                  (*colour[:3], fade * GLOW_TARGET_ALPHA)))
    return out, skipped


def rings(effects) -> list:
    """Jump charge / arrival / departure rings and fire glows."""
    out = []
    for effect in effects:
        kind = effect.get('kind')
        fade = max(0.0, 1.0 - effect.get('t', 0.0) / JUMP_LIFETIME)
        if kind in ('jump_charge', 'jump_arrive', 'jump_depart'):
            if fade <= 0.0:
                continue
            radius = JUMP_RING_BASE + JUMP_RING_GROWTH * (1.0 - fade)
            out.append(codec.ring(effect['pos'], radius, JUMP_RING_WIDTH,
                                  (*JUMP_RING_COLOUR, fade * 0.8)))
        elif kind == 'fire':
            if fade <= 0.0:
                continue
            out.append(codec.disc(effect['pos'], 26.0,
                                  (*effect.get('color', (1.0, 0.7, 0.3))[:3],
                                   max(0.0, 1.0 - effect.get('t', 0.0) / FIRE_LIFETIME) * 0.6),
                                  flat=True))
    return out


def projectiles(shots, weapon_type_of, extents_of) -> tuple[list, dict]:
    """A halo quad and a hot core per shaped bolt.

    `extents_of(shape, size, 1.0)` returns *pixel* extents because a pixels-per-world of 1.0 makes
    world units and pixels the same number: the window converts them back with its own camera.
    """
    out = []
    stats = {'drawn': 0, 'legacy': 0, 'squares': 0}
    for shot in shots:
        shape = _shape(weapon_type_of(getattr(shot, 'weapon_id', None)))
        if shape == 'legacy':
            stats['legacy'] += 1          # Python draws these as point sprites; not carried yet
            continue
        length, width = extents_of(shape, shot.size, 1.0)
        heading = shot.vel.to_tuple()
        colour = tuple(float(c) for c in shot.color[:3])
        pos = (shot.pos.x, shot.pos.y, shot.pos.z)
        if shape == 'square':
            stats['squares'] += 1
            out.append(codec.bolt(pos, (0.0, 0.0, 0.0), length * HALO_SCALE[0] * 0.5,
                                  length * HALO_SCALE[0] * 0.5, (*colour, HALO_ALPHA), square=True))
            out.append(codec.bolt(pos, (0.0, 0.0, 0.0), length * 0.5, length * 0.5,
                                  (*_lift(colour, CORE_WHITEN), CORE_ALPHA), square=True))
        else:
            out.append(codec.bolt(pos, heading, length * HALO_SCALE[0] * 0.5,
                                  width * HALO_SCALE[1] * 0.5, (*colour, HALO_ALPHA)))
            out.append(codec.bolt(pos, heading, length * 0.5, width * 0.5,
                                  (*_lift(colour, CORE_WHITEN), CORE_ALPHA)))
        stats['drawn'] += 1
    return out, stats


def _shape(weapon_type):
    from render.shapes import projectile_shape       # local: keeps the import graph unchanged
    return projectile_shape(weapon_type)


def shield_fraction(unit) -> float:
    """Mean quadrant fraction, the same figure the side panel shows (renderer.py::_draw_shields)."""
    total = unit.max_shield_total()
    if total <= 0:
        return 0.0
    return sum(unit.shields.get(q, 0.0) for q in QUADRANTS) / total


def shield_radius(unit, radius_of) -> float:
    """World radius of a unit's bubble, without the camera-dependent readability floor.

    `radius_of` is the caller's hull-radius lookup - the same one the selection rings use, so a
    bubble and the ring around it cannot disagree about how big the hull is. The floor
    (SHIELD_MIN_PX across) is presentation: it depends on how far away the camera is, so the window
    applies it at its own camera, exactly as it does for marker footprints and bolts.
    """
    if not unit.is_station and (unit.is_ship or unit.is_squadron):
        return float(radius_of(unit)) * SHIELD_SHIP_FACTOR
    return float(unit.radius) * SHIELD_STATION_FACTOR


def shields(units, radius_of, tint_of=None) -> list:
    """A standing shell for every unit whose shields are worth drawing.

    Everything that decides whether a bubble exists crosses: which units are drawn is the caller's
    visibility answer, `frac <= 0.001` hides an empty field, and the tint comes from the renderer's
    own strength ramp. What does not cross is the shell itself - the rim falloff is a function of
    the camera, so the window builds it.
    """
    out = []
    for unit in units:
        if not getattr(unit, 'alive', False) or unit.is_planet:
            continue
        if getattr(unit, 'planet_building_slot', None) is not None:
            continue                      # surface hardware is protected by its own generator
        fraction = shield_fraction(unit)
        if fraction <= SHIELD_MIN_FRACTION:
            continue
        bucket = max(1, min(SHIELD_BUCKETS, int(round(fraction * SHIELD_BUCKETS))))
        strength = bucket / float(SHIELD_BUCKETS)
        rgb = (tint_of or _shield_colour)(strength)
        # Alpha is floored, not ramped to zero: a field at 5% is the one the player must notice, and
        # a linear fade spends its most urgent quarter below the visibility threshold.
        alpha = SHIELD_FADE[0] + (SHIELD_FADE[1] - SHIELD_FADE[0]) * strength
        radius = shield_radius(unit, radius_of)
        if radius <= 0.0:
            continue                      # not drawn by the frame, so it gets no bubble
        out.append(codec.shield((unit.pos.x, unit.pos.y, unit.pos.z), radius,
                                fraction, (rgb[0], rgb[1], rgb[2], alpha)))
    return out


PLANET_FLASH_DECAY = 3.0         # renderer.py::_planet_shield_dome, flash -= dt*3


class PlanetDomes:
    """The field a colony's surface generator holds, and how recently it absorbed a hit.

    A dome is the same shell as a ship bubble - additive, bucketed by strength, scaled to the planet -
    so it crosses as the same `kind 6` record. Two things are this side's business and are decided
    here rather than in the window:

    * whether a planet has a field at all: only an operational generator owned by the planet's
      colonizer raises one, and it protects surface hardware only, never an orbital shell;
    * the pulse after a loss. Python shows it by drawing the same additive shell two or three times,
      which for `(SRC_ALPHA, ONE)` is exactly a brightness multiplier - so the pulse is published as
      repeated identical records instead of a tint the window would have to invent.
    """

    def __init__(self):
        self._previous = {}
        self._flash = {}

    def step(self, state, dt):
        """One record per pulse pass for every colony field standing right now.

        `state.entities` is scanned once per frame by `planet_shield_fields`, which also owns the
        dome radius (`planet.radius * 1.04 + 48.0`) - it is not re-derived here.
        """
        from render.planet_building_geometry import planet_shield_fields
        fields = planet_shield_fields(state)
        out = []
        for planet_id, (generator, strength, radius) in sorted(fields.items()):
            total = generator.total_shield()
            previous = self._previous.get(planet_id)
            if previous is not None and total < previous - 1e-6:
                self._flash[planet_id] = 1.0
            self._previous[planet_id] = total
            flash = self._flash.get(planet_id, 0.0)
            if flash > 0.0:
                flash = max(0.0, flash - dt * PLANET_FLASH_DECAY)
                self._flash[planet_id] = flash
            fraction = max(0.0, min(1.0, strength))
            if fraction <= SHIELD_MIN_FRACTION:
                continue
            bucket = max(1, min(SHIELD_BUCKETS, int(round(fraction * SHIELD_BUCKETS))))
            ramp = bucket / float(SHIELD_BUCKETS)
            rgb = _shield_colour(ramp)
            alpha = SHIELD_FADE[0] + (SHIELD_FADE[1] - SHIELD_FADE[0]) * ramp
            planet = state.entity(planet_id)
            if planet is None:
                continue
            pos = (planet.pos.x, planet.pos.y, planet.pos.z)
            record = codec.shield(pos, float(radius), fraction, (rgb[0], rgb[1], rgb[2], alpha))
            # 1 + round(flash*2) passes in the renderer; additive passes compose by addition.
            for _ in range(1 + int(round(flash * 2.0))):
                out.append(dict(record))
        live = set(fields)
        for planet_id in [key for key in self._previous if key not in live]:
            self._previous.pop(planet_id, None)
            self._flash.pop(planet_id, None)
        return out


def _shield_colour(strength: float):
    from render.shapes import shield_color
    return shield_color(strength)


def build(effects, shots, weapon_type_of, extents_of) -> tuple[list, dict]:
    blast_primitives, blasts_skipped = explosions(effects)
    primitives, skipped = beams(effects)
    primitives += blast_primitives
    primitives += rings(effects)
    bolts, stats = projectiles(shots, weapon_type_of, extents_of)
    primitives += bolts
    stats['beams_skipped'] = skipped
    stats['explosions'] = len(blast_primitives)
    stats['explosions_skipped'] = blasts_skipped
    stats['primitives'] = len(primitives)
    return primitives, stats
