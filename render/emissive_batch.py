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


def _lift(colour, amount):
    return tuple(min(1.0, c * (1.0 - amount) + amount) for c in colour[:3])


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
    from render.renderer import projectile_shape       # local: keeps the import graph unchanged
    return projectile_shape(weapon_type)


def build(effects, shots, weapon_type_of, extents_of) -> tuple[list, dict]:
    primitives, skipped = beams(effects)
    primitives += rings(effects)
    bolts, stats = projectiles(shots, weapon_type_of, extents_of)
    primitives += bolts
    stats['beams_skipped'] = skipped
    stats['primitives'] = len(primitives)
    return primitives, stats
