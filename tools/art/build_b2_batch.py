#!/usr/bin/env python3
"""INITIAL AUTHORING RECIPES ONLY. Each editable .blend is authoritative afterwards.

S06 batch B2 - squadron and logistics meshes. Eight new appearances in one seed:

  rebel:fighter       alliance_interceptor   Falcon fighter squadron
  rebel:bomber        alliance_bomber        Bulwark bomber squadron
  confederacy:fighter legion_vulture        Vulture drone wing
  confederacy:bomber  legion_hyena          Hyena strike wing
  syndicate:fighter   syndicate_jackal      Jackal raid wing
  rebel:convoy        alliance_convoy       crew transport / trade convoy
  confederacy:convoy  legion_convoy         crew transport / trade convoy
  syndicate:convoy    syndicate_convoy      crew transport / trade convoy

Each mesh is authored inside its binding's legacy procedural envelope, so
`render/ship_sizes.ship_size` derives the same class scale and drawn length as the
procedural hull it replaces; the union-safe review cameras and the unchanged collision
radius therefore still frame it. Every one is a distinct design - the squadrons share a
kit of primitives, not a hull with different paint. No proprietary geometry or textures.
None of these replaces a production binding.

Refuses overwriting an existing editable master unless `--replace-seed` is explicit.

    Blender --background --python-exit-code 1 --python tools/art/build_b2_batch.py -- --all
    Blender --background --python-exit-code 1 --python tools/art/build_b2_batch.py -- --asset rebel:fighter
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDENTIFIERS = {
    'rebel:fighter': 'alliance_interceptor', 'rebel:bomber': 'alliance_bomber',
    'confederacy:fighter': 'legion_vulture', 'confederacy:bomber': 'legion_hyena',
    'syndicate:fighter': 'syndicate_jackal', 'rebel:convoy': 'alliance_convoy',
    'confederacy:convoy': 'legion_convoy', 'syndicate:convoy': 'syndicate_convoy',
}
_ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def _refuse_existing_masters(argv):
    """Refuse before Blender is imported, and before any target is written.

    One seed authors eight masters, so a half-run that dies on the fourth one leaves the
    batch inconsistent: pre-flight every target. Treating an empty argument list as "all"
    is deliberate - the seed is only ever driven by Blender with an explicit `--`, so the
    no-argument case is the refusal guard's own path, not a way to author everything
    silently.
    """
    if not argv or '--all' in argv:
        targets = list(IDENTIFIERS)
    elif '--asset' in argv:
        targets = [argv[argv.index('--asset') + 1]]
    else:
        targets = []
    for key in targets:
        master = ROOT / f'art/blender/{IDENTIFIERS[key]}.blend'
        if master.exists() and '--replace-seed' not in argv:
            raise RuntimeError(f'{master.name} is the editable master. Use '
                               f'export_{IDENTIFIERS[key]}.py; --replace-seed destroys edits.')


_refuse_existing_masters(_ARGV)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alliance_common import loft, plate, annulus, cylinder, weld_scene  # noqa: E402
from hull_detail import surface, deck_panel, deck_strake, flank_detail, louvre_bank, panel  # noqa: E402
import bpy  # noqa: E402,F401


def sides(name, role, sections, offset, bevel=.25):
    """A lofted body mirrored to both sides of the centreline."""
    for side in (-1, 1):
        loft(f'{name} {"port" if side < 0 else "starboard"}', role, sections, bevel,
             center=(side * offset, 0, 0))


def nozzle(tag, x, y, z_aft, outer, inner, disc_r, n=12, casing=None):
    """A shallow drive mouth: lip ring, dark collar, then the emissive disc inside them.

    Three rules, each one learnt from a measured failure on this batch:

    * the recess stays under half the disc radius and the aperture stays wider than the
      disc, because the review camera's 60-unit height floor views these small hulls from
      35-50 degrees, where a deep throat shadows its own disc and reads as a closed socket;
    * the dark collar is a thin tube whose inner radius clears the disc, never a cone
      across the mouth - a capped collar hides the disc behind its own aft face;
    * `casing` bridges the mouth forward to the host body, whose own loft must STOP short
      of the mouth. A closed loft ends in a flat cap that sits in front of the disc and
      blocks it completely from every view.
    """
    annulus(f'{tag} lip', 'trim', x, y, [(z_aft, outer, inner), (z_aft + .5, outer, inner - .04)], n=n)
    annulus(f'{tag} throat', 'dark', x, y, [(z_aft + .06, inner, disc_r + .14),
                                            (z_aft + .4, inner * .96, disc_r + .14)], n=n)
    cylinder(f'{tag} emitter', 'cool', (x, y, z_aft + .22), disc_r, .22, n=n)
    if casing is not None:
        z_to, radius = casing
        annulus(f'{tag} casing', 'base', x, y, [(z_aft + .5, outer, inner), (z_to, radius, inner)], n=n)


# --------------------------------------------------------------------------- squadrons
def build_rebel_fighter():
    """Falcon interceptor: a slim dart on two outboard booms, bubble canopy, swept X-fin."""
    hull = ((-18.2, 1.35, 1.05, -2.6), (-14.5, 2.1, 1.7, -2.3), (-6, 2.7, 2.3, -1.9),
            (3.5, 2.5, 2.1, -1.5), (12, 1.8, 1.5, -.9), (18.0, .85, .95, -.45))
    loft('01 Interceptor pressure hull', 'base', hull, .3)
    # The boom stops at -11.5; the nozzle casing carries the afterbody to the mouth.
    boom = ((-11.5, 1.25, 1.5, -1.2), (-8, 1.65, 2.05, -1.6), (0, 1.55, 1.85, -1.4), (8, 1.15, 1.35, -1.0))
    sides('02 Outboard drive boom', 'base', boom, 8.15, .2)
    # Pylons tie the booms to the hull; they are the wing, so they carry the trim colour.
    for side in (-1, 1):
        plate(f'03 Boom pylon {side}', 'trim', (5.6, 1.1, 5.4), (side * 5.4, 1.9, .4), .16)
    # Tall swept dorsal blade - the silhouette that survives tactical zoom.
    loft('04 Swept dorsal blade', 'trim', ((9, .3, 8.3, 4.6), (2.5, .45, 7.15, 4.3), (-3.5, .35, 6.05, 4.1)), .2)
    loft('05 Ventral fin', 'base', ((2, .3, -0.9, -2.85), (-3.5, .35, -1.3, -2.85), (-8, .25, -1.5, -2.5)), .16)
    # Cockpit: a faceted canopy band on the forward spine.
    loft('06 Canopy frame', 'dark', ((12.5, 1.15, 2.75, 1.5), (7, 1.5, 3.55, 1.6), (1.5, .95, 2.9, 1.5)), .22)
    plate('07 Canopy glazing', 'lit', (2.0, .55, 5.4), (0, 3.35, 8.6), .12)
    for side in (-1, 1):
        # Forward gun rails and the outboard recognition stripes.
        plate(f'08 Laser rail {side}', 'dark', (1.15, 1.0, 9.5), (side * 3.1, -.35, 12.2), .12)
        plate(f'09 Wing flash {side}', 'accent', (.6, 1.5, 8.5), (side * 9.6, 2.6, -3.2), .1)
        louvre_bank(boom, f'10 Boom vent {side}', side, -3.5, rows=3, pitch=1.35, tall=1.4,
                    length=2.6, role='trim', x_offset=side * 7.6)
        nozzle(f'11 Boom drive', side * 8.15, 0, -13.4, 1.62, 1.32, 1.05,
               casing=(-11.5, 1.42))
    nozzle('12 Auxiliary drive', 0, -0.4, -19.77, 1.15, .92, .72, casing=(-18.2, 1.2))
    for z in (6.5, -1.5):
        deck_panel(hull, '13 Dorsal equipment bay', z - 2.2, z + 2.2, 0, .62, 'trim', .5, .5)


def build_rebel_bomber():
    """Bulwark bomber: broad armoured belly, outboard torpedo drums, stern turret."""
    hull = ((-23.6, 2.6, 2.0, -4.0), (-17, 3.5, 3.1, -5.2), (-4, 4.3, 3.9, -5.6),
            (9, 3.9, 3.3, -4.6), (17, 2.7, 2.2, -3.2), (23.0, 1.15, 1.15, -1.6))
    loft('01 Bomber pressure hull', 'base', hull, .34)
    # Payload bay: the deep armoured keel that makes the bomber read bottom-heavy.
    loft('02 Armoured payload bay', 'base', ((-22, 2.6, -4.3, -6.6), (-8, 3.4, -4.9, -6.65),
                                              (8, 3.0, -4.4, -6.5), (18, 2.0, -3.4, -5.2)), .24)
    drum = ((-12.4, 2.15, 1.1, -4.6), (-6, 2.2, 1.3, -4.9), (6, 2.1, 1.2, -4.6), (13, 1.5, .9, -3.7))
    sides('03 Outboard torpedo drum', 'base', drum, 11.2, .3)
    # Dorsal spine ridge and the tail fin that gives it the squadron silhouette.
    loft('04 Dorsal spine ridge', 'trim', ((-20, 2.2, 5.3, 3.4), (-6, 2.6, 6.0, 3.9), (10, 2.0, 5.0, 3.4)), .2)
    loft('05 Tail fin', 'trim', ((-20, .32, 6.45, 3.4), (-25.0, .3, 5.55, 3.0)), .16)
    loft('06 Ventral sensor fin', 'base', ((-16, .3, -4.4, -6.65), (-22, .28, -4.0, -6.0)), .16)
    for side in (-1, 1):
        plate(f'07 Forward gun rail {side}', 'dark', (1.2, 1.05, 10.5), (side * 3.4, -1.2, 13.5), .12)
        plate(f'08 Belly torpedo louvre {side}', 'dark', (7.0, .5, 12.0), (side * 5.4, -6.4, -2.0), .1)
        plate(f'09 Squadron stripe {side}', 'accent', (.7, 1.6, 11.0), (side * 12.9, 2.4, -4.0), .1)
        louvre_bank(drum, f'10 Drum vent {side}', side, -5.0, rows=5, pitch=1.5, tall=2.2,
                    length=3.4, role='trim', x_offset=side * 11.2)
        nozzle(f'11 Boom drive {side}', side * 11.2, 0, -14.0, 1.9, 1.5, 1.2, casing=(-12.4, 2.05))
    nozzle('12 Hull drive port', -3.4, -2.2, -25.37, 1.85, 1.45, 1.15, casing=(-23.6, 2.4))
    nozzle('13 Hull drive starboard', 3.4, -2.2, -25.37, 1.85, 1.45, 1.15, casing=(-23.6, 2.4))
    # Tail turret: a barbette under the stern, the second thing the eye reads.
    loft('14 Tail barbette', 'dark', ((-18, 1.5, -1.5, -3.6), (-24.4, 1.7, -1.2, -3.9)), .2)
    cylinder('15 Barbette barrel', 'trim', (0, -2.4, -22.8), .55, 5.0, axis='Z', n=10)
    plate('16 Cockpit glazing', 'lit', (2.6, .6, 6.5), (0, 3.6, 11.0), .12)
    for z in (6, -6):
        deck_panel(hull, '17 Dorsal service bay', z - 3.0, z + 3.0, 0, .55, 'dark', .4, .6)


def build_confederacy_fighter():
    """Vulture drone wing: a narrow thorax, forward mandibles and four splayed delta wings."""
    thorax = ((-15.07, 1.15, 1.5, -1.6), (-9, 2.0, 2.4, -2.2), (-1, 2.55, 3.0, -2.4),
              (8, 2.2, 2.6, -2.0), (19.4, .8, 1.1, -.9))
    loft('01 Drone thorax', 'base', thorax, .28)
    # Four wings sweep back and outward; the loft grows from the centreline, so each wing
    # is one swept delta whose root reaches the thorax.
    upper = ((3, .9, 2.2, 1.0), (-1, 4.5, 1.9, .6), (-6, 8.7, 1.5, .2), (-11, 12.45, 1.1, -.2))
    lower = ((2, .8, .2, -1.0), (-2, 4.1, 0, -1.5), (-7, 8.0, -.3, -1.9), (-12, 11.4, -.6, -2.2))
    for tag, sections in (('02 Upper wing', upper), ('03 Lower wing', lower)):
        sides(tag, 'base', sections, 0, .22)
    # Mandibles: the forward pincer that identifies the Legion drone at a glance.
    for side in (-1, 1):
        loft(f'04 Mandible {side}', 'trim', ((19.2, .55, 2.2, 1.1), (14.5, .8, 3.0, 1.3),
                                             (10.5, .6, 2.4, 1.2)), .2, center=(side * 1.6, 0, 0))
        plate(f'05 Mandible rail {side}', 'dark', (.6, .9, 8.0), (side * 2.6, .2, 15.0), .1)
        plate(f'06 Wing emblem {side}', 'accent', (.5, 1.3, 6.4), (side * 9.4, 1.2, -4.4), .1)
        # Both wings sweep back past the mouth: the upper tip ends at z=-11 and the lower
        # at z=-12, so a mouth at either tip is covered by the other wing. The thruster
        # rides the lower wing's aft-most tip instead, clear of everything behind it.
        nozzle(f'07 Wingtip thruster {side}', side * 11.0, -1.4, -12.4, 1.35, 1.05, .85,
               casing=(-12.0, 1.35))
    # Tail sting and the twin main drives.
    loft('08 Tail sting', 'trim', ((-11, 1.1, 1.9, -1.6), (-15.0, .35, 1.2, -1.0)), .18)
    nozzle('09 Main drive port', -2.2, -.2, -12.6, 1.6, 1.3, 1.0)
    nozzle('10 Main drive starboard', 2.2, -.2, -12.6, 1.6, 1.3, 1.0)
    # Sensor cluster and the window band; the drone has no bridge, only optics.
    loft('11 Dorsal sensor crest', 'dark', ((9, .7, 5.6, 3.2), (4, 1.0, 6.9, 3.6), (-1, .6, 5.8, 3.2)), .2)
    plate('12 Optic band', 'lit', (1.5, .5, 4.2), (0, 6.2, 5.5), .1)
    plate('13 Chin optic', 'lit', (.9, .45, 2.2), (0, 2.9, 17.0), .08)


def build_confederacy_bomber():
    """Hyena strike wing: a heavy thorax, six wings, belly pods, a tall dorsal crest."""
    thorax = ((-19.8, 2.1, 2.3, -2.6), (-14, 3.0, 3.4, -3.4), (-4, 3.4, 4.2, -3.6),
              (8, 2.9, 3.6, -3.0), (26.12, 1.0, 1.4, -1.2))
    loft('01 Strike thorax', 'base', thorax, .3)
    # Six wings: two upper, two mid, two lower - the wing count is the species read.
    upper = ((5, .9, 3.4, 2.2), (0, 5.6, 3.0, 1.6), (-7, 11.0, 2.4, 1.0), (-14, 17.4, 1.6, .4))
    mid = ((6, .9, 1.6, .4), (1, 6.0, 1.2, -.2), (-6, 11.6, .6, -.8), (-13, 16.4, .0, -1.4))
    lower = ((4, .8, -.4, -1.6), (-1, 5.0, -1.0, -2.2), (-8, 9.8, -1.6, -2.8), (-15, 14.2, -2.2, -3.4))
    for tag, sections in (('02 Upper wing', upper), ('03 Mid wing', mid), ('04 Lower wing', lower)):
        sides(tag, 'base', sections, 0, .22)
    # Belly launch pods under each wing root.
    pod = ((-12.6, 1.8, -3.1, -6.4), (-6, 2.0, -3.4, -6.9), (3, 1.7, -2.8, -5.8))
    sides('05 Belly launch pod', 'base', pod, 5.4, .24)
    # Dorsal crest reaching the top of the envelope.
    loft('06 Dorsal crest', 'trim', ((14, .4, 12.45, 5.0), (5, .55, 12.85, 5.4), (-4, .45, 12.05, 5.2),
                                     (-11, .3, 10.3, 4.6)), .2)
    # Twin forward mandibles, mirrored at both ends of the thorax are the family signature.
    for side in (-1, 1):
        loft(f'07 Fore mandible {side}', 'trim', ((26.0, .7, 2.8, 1.2), (19, .95, 3.6, 1.4),
                                                 (14, .7, 2.8, 1.2)), .2, center=(side * 2.0, 0, 0))
        plate(f'08 Mandible rail {side}', 'dark', (.65, .95, 9.0), (side * 3.2, .2, 20.0), .1)
        plate(f'09 Strike emblem {side}', 'accent', (.55, 1.5, 8.0), (side * 12.6, 1.8, -6.4), .1)
        louvre_bank(pod, f'10 Pod vent {side}', side, -8.0, rows=5, pitch=1.6, tall=2.4,
                    length=3.6, role='trim', x_offset=side * 5.4)
        nozzle(f'11 Pod drive {side}', side * 5.4, -4.6, -14.0, 1.8, 1.45, 1.15, casing=(-12.6, 2.0))
    nozzle('12 Main drive port', -2.6, -.3, -21.65, 1.9, 1.5, 1.2, casing=(-19.8, 3.0))
    nozzle('13 Main drive starboard', 2.6, -.3, -21.65, 1.9, 1.5, 1.2, casing=(-19.8, 3.0))
    plate('14 Optic band', 'lit', (1.8, .55, 5.0), (0, 4.0, 22.5), .1)
    loft('15 Sensor crest', 'dark', ((18, .8, 7.0, 4.6), (12, 1.1, 8.4, 5.0), (6, .7, 7.2, 4.6)), .2)


def build_syndicate_fighter():
    """Jackal raid wing: a blunt armoured ram-brick, a tall dorsal blade, asymmetric pods."""
    hull = ((-15.6, 3.2, 2.5, -3.4), (-10, 4.6, 3.5, -3.95), (-2, 5.0, 4.2, -3.8),
            (6, 4.6, 3.6, -3.0), (14, 3.5, 2.6, -2.2), (21, 2.3, 1.6, -1.4), (24.5, .85, .8, -.6))
    loft('01 Raider pressure hull', 'base', hull, .34)
    # Ram prow: a heavy wedge, the jackal's snout.
    loft('02 Ram prow', 'trim', ((24.3, 2.0, 1.5, -1.2), (19, 3.0, 2.4, -1.8), (15, 2.2, 1.8, -1.4)), .2)
    # Tall dorsal blade - the raider's whole silhouette at tactical range.
    loft('03 Dorsal blade', 'trim', ((8, .38, 11.75, 4.0), (0, .5, 11.85, 4.4), (-8, .4, 10.9, 4.0),
                                     (-14, .28, 9.3, 3.6)), .2)
    # Twin outboard engine pods with the drive mouths at the stern.
    # The hull and pods stop forward of their mouths so no closed cap covers a disc.
    pod = ((-15.4, 1.45, 1.45, -1.6), (-11, 1.6, 2.0, -2.2), (-1, 1.55, 1.8, -2.0), (8, 1.25, 1.3, -1.4))
    sides('04 Outboard engine pod', 'base', pod, 5.4, .2)
    for side in (-1, 1):
        plate(f'05 Pod pylon {side}', 'dark', (3.4, 1.4, 6.0), (side * 4.2, .2, -3.0), .14)
        plate(f'06 Ram cheek armour {side}', 'dark', (1.1, 2.2, 9.0), (side * 4.2, -1.0, 18.0), .12)
        plate(f'07 Raider flash {side}', 'accent', (.7, 1.7, 9.0), (side * 7.5, 2.6, -4.0), .1)
        # The Jackal's envelope is asymmetric (-7.892 port / +8.45 starboard), so the port
        # vents sit further inboard than the starboard ones.
        louvre_bank(pod, f'08 Pod vent {side}', side, -6.0, rows=3, pitch=1.5, tall=1.6,
                    length=3.0, role='trim', x_offset=side * (5.4 if side > 0 else 5.15))
        nozzle(f'09 Pod drive {side}', side * 5.4, 0, -17.258, 1.5, 1.2, .9, casing=(-15.4, 1.5))
    # Asymmetric sensor pod on the starboard shoulder: only this hull carries it.
    loft('10 Starboard sensor pod', 'dark', ((12, .8, 3.4, 1.6), (7, 1.2, 4.4, 2.0), (2, .8, 3.6, 1.6)),
         .18, center=(6.8, 0, 0))
    cylinder('11 Sensor lens', 'lit', (7.0, 2.9, 11.0), .55, 2.2, axis='Z', n=10)
    plate('12 Bridge glazing', 'lit', (2.4, .6, 5.0), (0, 4.3, 12.0), .12)
    nozzle('13 Centre drive', 0, -1.6, -17.258, 1.5, 1.2, .95, casing=(-15.6, 2.2))
    for z in (4, -7):
        deck_panel(hull, '14 Dorsal armour bay', z - 2.6, z + 2.6, 0, .6, 'trim', .55, .55)


# --------------------------------------------------------------------------- logistics
def build_alliance_convoy():
    """Colony transport: a long open spine under two rows of rounded freight drums."""
    spine = ((-60, 3.4, 3.4, -4.4), (-30, 4.6, 4.6, -5.4), (10, 4.8, 4.8, -5.6),
             (34, 4.2, 4.2, -4.8), (57.5, 2.4, 2.6, -3.0))
    loft('01 Convoy spine', 'base', spine, .34)
    # Bridge and habitat pod forward, standing above the spine.
    loft('02 Forward bridge pod', 'base', ((44, 3.4, 9.0, 3.6), (52, 4.6, 12.4, 3.8), (59.5, 2.6, 10.0, 3.4)), .3)
    loft('03 Pod roof plant', 'trim', ((46, 2.4, 13.6, 12.0), (56, 3.0, 14.8, 12.4)), .2)
    # Two rows of freight drums per side: the loaded hull the eye counts.
    for row, x in ((0, 14.5), (1, 23.5)):
        for i in range(5):
            z = -46 + i * 19.0
            cylinder(f'04 Freight drum {row} {i}', 'base', (x, 4.4, z), 6.4, 15.2, axis='Z', n=14)
            cylinder(f'05 Freight drum port {row} {i}', 'base', (-x, 4.4, z), 6.4, 15.2, axis='Z', n=14)
            for tag, s in (('06 Drum strap starboard', 1), ('07 Drum strap port', -1)):
                plate(f'{tag} {row} {i}', 'trim', (13.4, 1.0, 1.6), (s * x, 4.4, z + 5.2), .1)
    # Gantry frames holding the drums down to the spine.
    for i in range(6):
        z = -50 + i * 20.0
        for x in (14.5, 23.5):
            for s in (-1, 1):
                plate(f'08 Cargo gantry {i} {x} {s}', 'dark', (13.6, .8, 1.4), (s * x, 11.4, z), .1)
    for side in (-1, 1):
        plate(f'09 Keel girder {side}', 'dark', (1.6, 2.0, 100.0), (side * 4.4, -5.0, -6.0), .12)
        plate(f'10 Convoy stripe {side}', 'accent', (.7, 2.6, 46.0), (side * 4.9, 1.0, 6.0), .1)
        louvre_bank(spine, f'11 Spine vent {side}', side, -24, rows=5, pitch=1.7, tall=3.4,
                    length=6.0, role='trim')
    # Stern machinery: the engine block sits on the spine centreline, not at the sides.
    loft('12 Stern engine block', 'base', ((-70.4, 8.6, 7.6, -5.0), (-64, 9.4, 8.6, -5.4),
                                           (-56, 8.0, 7.4, -4.6)), .3)
    nozzle('13 Main drive port', -5.6, -.6, -72.698, 3.5, 2.9, 2.3, n=14, casing=(-70.4, 4.0))
    nozzle('14 Main drive starboard', 5.6, -.6, -72.698, 3.5, 2.9, 2.3, n=14, casing=(-70.4, 4.0))
    nozzle('15 Centre drive', 0, 1.4, -72.698, 2.2, 1.8, 1.45, n=12, casing=(-70.4, 2.6))
    plate('16 Bridge window band', 'lit', (4.6, .8, 1.6), (0, 10.6, 57.0), .1)
    for z in (48, 53, 57):
        plate(f'17 Pod window {z}', 'lit', (5.0, .7, 1.2), (0, 11.4, z), .1)
    for row, x in ((0, 14.5), (1, 23.5)):
        for i in (1, 3):
            z = -46 + i * 19.0
            for s in (-1, 1):
                plate(f'18 Drum marking {row} {i} {s}', 'lit', (1.4, 1.0, 5.0), (s * x, 10.0, z), .08)


def build_legion_convoy():
    """Legion hauler: a spine under a tall dorsal cargo sail and six clamped pods."""
    spine = ((-56.4, 3.2, 3.2, -4.6), (-28, 4.6, 4.4, -5.6), (8, 4.8, 4.6, -5.8),
             (32, 4.0, 4.0, -5.0), (56.1, 2.2, 2.4, -3.2))
    loft('01 Hauler spine', 'base', spine, .32)
    # The dorsal sail: a lattice mast that carries the Legion's stacked cargo frames.
    loft('02 Dorsal cargo sail', 'base', ((46, 3.0, 18.0, 4.0), (24, 4.4, 26.0, 4.2),
                                          (-6, 4.8, 29.4, 4.4), (-34, 3.6, 22.0, 4.0),
                                          (-50, 2.4, 14.0, 3.6)), .34)
    for i in range(5):
        z = -40 + i * 18.0
        plate(f'03 Sail frame {i}', 'dark', (9.6, 1.1, 1.6), (0, 27.0, z), .1)
        plate(f'04 Sail frame lower {i}', 'dark', (9.6, 1.1, 1.6), (0, 17.0, z), .1)
        for s in (-1, 1):
            plate(f'05 Sail brace {i} {s}', 'trim', (1.2, 12.0, 1.4), (s * 4.0, 22.0, z), .1)
    # Six clamped cargo pods flanking the spine.
    for i, z0 in enumerate((-44, -24, -4)):
        for s in (-1, 1):
            # The pod sections carry their own span; a z offset in `center` would move them
            # a second time and blow the envelope (the first build ran 27 units past it).
            pod = ((z0 - 10, 4.4, 3.0, -1.6), (z0 - 2, 5.6, 4.2, -2.6), (z0 + 10, 5.6, 4.2, -2.6),
                   (z0 + 20, 4.2, 2.8, -1.4))
            loft(f'06 Cargo pod {i} {s}', 'base', pod, .28, center=(s * 19.0, 8.0, 0))
            plate(f'07 Pod clamp {i} {s}', 'trim', (11.4, 1.2, 2.0), (s * 19.0, 8.0, z0 + 13.0), .1)
            plate(f'08 Pod brace {i} {s}', 'dark', (9.0, 1.0, 2.4), (s * 14.5, 6.0, z0 + 4.0), .1)
            louvre_bank(spine, f'09 Spine vent {i} {s}', s, z0 + 6.0, rows=4, pitch=1.7,
                        tall=3.2, length=5.4, role='trim')
    for s in (-1, 1):
        plate(f'10 Hauler stripe {s}', 'accent', (.7, 2.4, 40.0), (s * 4.9, .8, 2.0), .1)
        plate(f'11 Keel girder {s}', 'dark', (1.5, 2.2, 92.0), (s * 4.2, -5.2, -4.0), .12)
    loft('12 Forward bridge pod', 'base', ((44, 2.8, 8.4, 3.8), (50, 3.8, 11.0, 4.0), (57.6, 2.2, 8.6, 3.6)), .26)
    loft('13 Aft machinery block', 'base', ((-63.4, 8.0, 7.0, -5.0), (-57, 8.8, 8.0, -5.4),
                                             (-50, 7.2, 6.6, -4.6)), .28)
    nozzle('14 Main drive port', -5.0, -.4, -65.698, 3.2, 2.6, 2.1, n=14, casing=(-63.4, 3.7))
    nozzle('15 Main drive starboard', 5.0, -.4, -65.698, 3.2, 2.6, 2.1, n=14, casing=(-63.4, 3.7))
    for s in (-1, 1):
        nozzle(f'16 Sail thruster {s}', s * 3.0, 20.0, -50.0, 1.8, 1.45, 1.15, casing=(-48.4, 1.6))
    plate('17 Bridge window band', 'lit', (4.2, .8, 1.6), (0, 9.6, 55.0), .1)
    for i in range(3):
        plate(f'18 Pod window {i}', 'lit', (8.0, .8, 1.4), (19.0, 8.0, -46 + i * 20.0), .1)
        plate(f'19 Pod window port {i}', 'lit', (8.0, .8, 1.4), (-19.0, 8.0, -46 + i * 20.0), .1)


def build_syndicate_convoy():
    """Syndicate bulk hauler: an offset superstructure tower over a stacked drum deck."""
    spine = ((-64, 3.4, 3.2, -4.8), (-30, 4.8, 4.4, -5.8), (12, 5.0, 4.6, -6.0),
             (40, 4.2, 4.0, -5.2), (62.04, 2.4, 2.6, -3.4))
    loft('01 Hauler spine', 'base', spine, .32)
    # Offset superstructure: a stepped tower on the starboard quarter, the hull's identity.
    loft('02 Offset superstructure', 'base', ((52, 6.0, 14.0, 4.0), (40, 9.0, 24.0, 4.2),
                                               (24, 10.4, 32.0, 4.4), (6, 9.0, 28.0, 4.2),
                                               (-14, 6.6, 18.0, 4.0)), .34, center=(14.0, 0, 0))
    loft('03 Tower crown', 'trim', ((30, 5.0, 35.4, 30.0), (16, 5.6, 36.3, 30.4), (4, 4.4, 33.6, 29.0)),
         .24, center=(14.0, 0, 0))
    for i in range(4):
        z = 22 - i * 12.0
        plate(f'04 Tower deck rail {i}', 'dark', (20.0, 1.1, 1.6), (14.0, 30.0, z), .1)
        plate(f'05 Tower window band {i}', 'lit', (14.0, .9, 1.8), (17.0, 30.4, z), .1)
    # Stacked freight deck: four drums per side in two tiers, inside the port envelope.
    for tier, (x, y, r) in enumerate(((13.0, 5.0, 5.6), (22.0, 5.0, 5.6), (13.0, 15.0, 4.6))):
        for i in range(4):
            z = -50 + i * 22.0
            for s in (-1, 1):
                xx = s * x * (.92 if s < 0 else 1.0)
                cylinder(f'06 Freight drum {tier} {i} {s}', 'base', (xx, y, z), r, 17.0, axis='Z', n=14)
                plate(f'07 Drum band {tier} {i} {s}', 'trim', (2 * r + .6, 1.0, 1.5), (xx, y, z + 6.0), .1)
    for i in range(5):
        z = -52 + i * 21.0
        plate(f'08 Deck gantry {i}', 'dark', (44.0, .9, 1.5), (-2.0, 20.0, z), .1)
    for s in (-1, 1):
        plate(f'09 Keel girder {s}', 'dark', (1.6, 2.2, 104.0), (s * 4.6, -5.4, -10.0), .12)
        louvre_bank(spine, f'11 Spine vent {s}', s, -22, rows=5, pitch=1.7, tall=3.6, length=6.4)
    # The accent stripe rides the tower's starboard face, not the flank: the freight drums
    # (centre y 5.0, r 5.6) overhang the flank and hide anything below y ~13 from the review
    # camera's 35 degree elevation, which measured 0 changed pixels for a flank stripe.
    for i, (zc, yc, hx, hy, lz, xc) in enumerate(((22.0, 22.0, 1.1, 12.0, 12.0, 24.3),
                                                 (42.0, 20.0, 1.1, 10.0, 10.0, 23.1))):
        plate(f'10 Raider stripe {i}', 'accent', (hx, hy, lz), (xc, yc, zc), .1)
    # Three engine pods on a stern crossbeam. The crossbeam stops at -74.9 and each bell is
    # a hollow flare, not a capped cylinder: both would otherwise sit in front of the pod
    # discs, whose mouths protrude 2.0 units aft of the beam as the ship's whole drive
    # silhouette. The lips still set the mesh's Z minimum, so the envelope span is intact.
    loft('12 Stern crossbeam', 'base', ((-74.9, 20.0, 8.4, -5.4), (-72, 21.5, 9.0, -5.8),
                                        (-66, 20.0, 8.4, -5.4)), .3)
    for i, x in enumerate((-14.0, 2.0, 20.0)):
        annulus(f'13 Engine bell {i}', 'base', x, -1.0,
                [(-76.412, 4.4, 3.2), (-74.9, 5.6, 3.4)], n=14)
        nozzle(f'14 Pod drive {i}', x, -1.0, -76.912, 3.5, 2.9, 2.3, n=14, casing=(-68.4, 4.4))
    plate('15 Bridge window band', 'lit', (12.0, .9, 1.8), (14.0, 15.4, 50.0), .1)
    plate('16 Cargo deck lighting', 'lit', (6.0, .7, 3.0), (-2.0, 20.6, 30.0), .1)


SEEDS = {
    'rebel:fighter': dict(
        identifier='alliance_interceptor', data_id='rebel_x_squadron', builder=build_rebel_fighter,
        design='Falcon interceptor - slim dart, outboard boom drives, swept dorsal blade',
        limits=((-12.0, 12.0), (-3.0, 8.471), (-19.77, 18.0)), min_length=37.7,
        mesh_cap=(5000, 3500),
        emitter_centers=[[-8.15, 0, -13.18], [8.15, 0, -13.18], [0, -0.4, -19.55]]),
    'rebel:bomber': dict(
        identifier='alliance_bomber', data_id='rebel_y_squadron', builder=build_rebel_bomber,
        design='Bulwark bomber - armoured payload keel, outboard torpedo drums, stern barbette',
        limits=((-16.0, 16.0), (-6.8, 6.55), (-25.37, 23.0)), min_length=48.3,
        mesh_cap=(5000, 3500),
        emitter_centers=[[-11.2, 0, -13.78], [11.2, 0, -13.78], [-3.4, -2.2, -25.15], [3.4, -2.2, -25.15]]),
    'confederacy:fighter': dict(
        identifier='legion_vulture', data_id='confed_vulture_squadron', builder=build_confederacy_fighter,
        design='Vulture drone wing - narrow thorax, four splayed deltas, forward mandibles',
        limits=((-12.831, 12.831), (-3.0, 7.6), (-15.07, 19.4)), min_length=34.4,
        mesh_cap=(5000, 3500),
        emitter_centers=[[-11.0, -1.4, -12.18], [11.0, -1.4, -12.18], [-2.2, -0.2, -12.38], [2.2, -0.2, -12.38]]),
    'confederacy:bomber': dict(
        identifier='legion_hyena', data_id='confed_bomber_squadron', builder=build_confederacy_bomber,
        design='Hyena strike wing - heavy thorax, six wings, belly pods, tall dorsal crest',
        limits=((-17.531, 17.531), (-7.0, 13.0), (-21.65, 26.12)), min_length=47.7,
        mesh_cap=(5000, 3500),
        emitter_centers=[[-5.4, -4.6, -13.78], [5.4, -4.6, -13.78], [-2.6, -0.3, -21.43], [2.6, -0.3, -21.43]]),
    'syndicate:fighter': dict(
        identifier='syndicate_jackal', data_id='syndicate_raid_squadron', builder=build_syndicate_fighter,
        design='Jackal raid wing - blunt ram hull, dorsal blade, offset sensor pod',
        limits=((-7.892, 8.45), (-4.024, 12.0), (-17.258, 24.5)), min_length=41.7,
        mesh_cap=(5000, 3500),
        emitter_centers=[[-5.4, 0, -17.038], [5.4, 0, -17.038], [0, -1.6, -17.038]]),
    'rebel:convoy': dict(
        identifier='alliance_convoy', data_id='rebel_crew_transport', builder=build_alliance_convoy,
        design='Colony transport - open spine, two rows of freight drums, forward bridge pod',
        limits=((-31.0, 31.0), (-9.0, 16.0), (-72.698, 59.5)), min_length=132.1,
        mesh_cap=(10000, 7000),
        emitter_centers=[[-5.6, -0.6, -72.478], [5.6, -0.6, -72.478], [0, 1.4, -72.478]]),
    'confederacy:convoy': dict(
        identifier='legion_convoy', data_id='confed_crew_transport', builder=build_legion_convoy,
        design='Legion hauler - spine under a tall dorsal cargo sail, six clamped pods',
        limits=((-36.5, 36.5), (-7.0, 29.5), (-65.698, 57.6)), min_length=123.2,
        mesh_cap=(10000, 7000),
        emitter_centers=[[-5.0, -0.4, -65.478], [5.0, -0.4, -65.478], [-3.0, 20.0, -49.78], [3.0, 20.0, -49.78]]),
    'syndicate:convoy': dict(
        identifier='syndicate_convoy', data_id='syndicate_crew_transport', builder=build_syndicate_convoy,
        design='Syndicate bulk hauler - offset superstructure tower, stacked drum deck',
        limits=((-27.786, 42.267), (-9.0, 36.5), (-76.912, 62.04)), min_length=138.9,
        mesh_cap=(10000, 7000),
        emitter_centers=[[-14.0, -1.0, -76.692], [2.0, -1.0, -76.692], [20.0, -1.0, -76.692]]),
}


def build(key):
    spec = SEEDS[key]
    master = ROOT / f'art/blender/{spec["identifier"]}.blend'
    if master.exists() and '--replace-seed' not in sys.argv:
        raise RuntimeError(
            f'{master.name} is the editable master. Use export_{spec["identifier"]}.py; '
            f'--replace-seed destroys edits.')
    # alliance_common's import already emptied the startup scene and built the role
    # materials; a per-asset reset must not reload factory settings or those materials go
    # with it (`ReferenceError: StructRNA of type Material has been removed`).
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    spec['builder']()
    # Nothing floats: a kit is authored by centre and by reach, so contact is not implied.
    weld_scene()
    features = dict(
        authority='blend', approval='pending_owner_approval', binding=key,
        data_id=spec['data_id'], original_design=True, design=spec['design'],
        emitter_centers=spec['emitter_centers'], legacy_envelope=[list(a) for a in spec['limits']],
        seed_recipe='tools/art/build_b2_batch.py; initial authoring only, never rebuild hand edits',
        provenance='Original geometry authored in Blender; no external mesh or texture dependencies')
    bpy.context.scene['asset'] = spec['identifier']
    bpy.context.scene['features_json'] = json.dumps(features, sort_keys=True)
    bpy.context.scene['authority'] = 'blend'
    bpy.context.scene['design'] = spec['design']
    bpy.context.scene['binding'] = key
    bpy.context.scene['review'] = 'pending owner approval - not a production binding'
    bpy.context.scene['coordinates'] = 'X beam; Y up; +Z forward'
    bpy.context.scene['runtime'] = 'immutable evaluated triangles; no runtime Blender'
    bpy.context.preferences.filepaths.save_version = 0
    master.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(master), compress=True)
    print(f'SEED_OK {key} -> {master.name}')


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if '--all' in argv:
        keys = list(SEEDS)
    elif '--asset' in argv:
        keys = [argv[argv.index('--asset') + 1]]
    else:
        raise SystemExit('usage: --all | --asset <faction:role>')
    for key in keys:
        if key not in SEEDS:
            raise SystemExit(f'unknown mesh key {key}; known: {sorted(SEEDS)}')
        build(key)


main()
