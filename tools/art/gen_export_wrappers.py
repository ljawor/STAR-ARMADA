#!/usr/bin/env python3
"""Render the per-asset export wrappers for the S06 pending batch from one template.

The S03 pipeline refuses an exporter that does not itself open the declared source
(`E_EXPORT_NOT_FROM_SOURCE`), so every asset needs its own wrapper rather than a shared
import. Writing ten near-identical files by hand is how one of them silently drifts; they
are rendered from `tools/art/templates/export_wrapper.tmpl` here, and `--check` proves the
tree still matches that template (it is run by the B1/B2 guard tests).

    python3 tools/art/gen_export_wrappers.py --check
    python3 tools/art/gen_export_wrappers.py            # write missing / mismatched
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / 'tools/art/templates/export_wrapper.tmpl'
FIRST_LINE = '#!/usr/bin/env python3'
SLOTS = ('@@IDENTIFIER@@', '@@LABEL@@', '@@ENVELOPE@@', '@@MIN_LENGTH@@', '@@FLOOR_DECLARATION@@',
         '@@FLOOR_ASSERTION@@', '@@MAX_TRIANGLES@@', '@@MAX_VERTICES@@', '@@MAX_BYTES@@')
# A wrapper outside the small-prop class is generated **byte for byte** as it was before the class
# existed: no new constant, the original assert. Only a row that declares a floor of its own differs,
# which is what keeps every already-approved record's export-script hash valid.
FLOOR_DEFAULT_ASSERTION = ("    assert 1_800 < asset['triangle_count'] <= MAX_TRIANGLES,"
                           "asset['triangle_count']")
# The floor is 1,800 triangles for hulls and structures. A *declared* small prop - one the renderer
# draws many times per frame - carries its own floor instead; a unit rock drawn forty times per field
# cannot be built with the surface density a station needs. Owner decision `s06-small-prop-class-2026-10-17`.
MIN_TRIANGLES = {'shared_asteroid_field': 120}
DEFAULT_MIN_TRIANGLES = 1_800

# Master label, envelope (the binding's legacy procedural extent), minimum authored Z span,
# and this asset's own export caps - each tighter than the runtime loader's 12,000 triangle
# / 10,000 vertex / 2,000,000 byte ceiling.
ASSETS = {
    'alliance_corvette': ('Blockade Runner', ((-21.9, 21.9), (-6.0, 15.3), (-46.46, 45.0)), 91.4, 8000, 6000, 1_200_000),
    'alliance_carrier': ('Independence-class Fleet Carrier', ((-146.51, 146.51), (-30.5, 57.0), (-204.8, 190.0)), 394.0, 11888, 9450, 2_000_000),
    'alliance_interceptor': ('Falcon interceptor', ((-12.0, 12.0), (-3.0, 8.471), (-19.77, 18.0)), 37.7, 5000, 3500, 500_000),
    'alliance_bomber': ('Bulwark bomber', ((-16.0, 16.0), (-6.8, 6.55), (-25.37, 23.0)), 48.3, 5000, 3500, 500_000),
    'legion_vulture': ('Vulture drone', ((-12.831, 12.831), (-3.0, 7.6), (-15.07, 19.4)), 34.4, 5000, 3500, 500_000),
    'legion_hyena': ('Hyena strike craft', ((-17.531, 17.531), (-7.0, 13.0), (-21.65, 26.12)), 47.7, 5000, 3500, 500_000),
    'syndicate_jackal': ('Jackal raider', ((-7.892, 8.45), (-4.024, 12.0), (-17.258, 24.5)), 41.7, 5000, 3500, 500_000),
    'alliance_convoy': ('Colony transport', ((-31.0, 31.0), (-9.0, 16.0), (-72.698, 59.5)), 132.1, 10000, 7000, 1_500_000),
    'legion_convoy': ('Legion hauler', ((-36.5, 36.5), (-7.0, 29.5), (-65.698, 57.6)), 123.2, 10000, 7000, 1_500_000),
    'syndicate_convoy': ('Syndicate bulk hauler', ((-27.786, 42.267), (-9.0, 36.5), (-76.912, 62.04)), 138.9, 10000, 7000, 1_500_000),
    # S06 B3a - the three faction command stations. Stations carry the owner-set 11,500
    # triangle advisory budget, under the loader's hard 12,000.
    'alliance_command_station': ('Alliance command station', ((-48.0, 48.0), (-6.8, 26.48), (-29.6, 29.6)), 59.0, 11500, 8000, 2_000_000),
    'legion_command_station': ('Legion command station', ((-53.8231, 53.8231), (-6.0, 41.6), (-38.4, 60.0)), 98.0, 11500, 8000, 2_000_000),
    # S06 B3b slice 1 - the smaller station kinds across the three faction families. Same
    # station budget policy as B3a; `min_length` is the binding's own footprint depth, which
    # is what a station mesh is measured by rather than a hull's drawn length.
    'alliance_mining_station': ('Alliance mining station', ((-44.8, 44.8), (-15.6, 10.12), (-26.0, 22.8294)), 48.6, 11500, 8000, 2_000_000),
    'legion_mining_station': ('Legion mining station', ((-40.6686, 40.6686), (-31.44, 11.08), (-29.36, 46.96)), 76.1, 11500, 8000, 2_000_000),
    'syndicate_mining_station': ('Syndicate mining station', ((-33.9322, 42.4), (-32.4, 39.6), (-25.0848, 41.4431)), 66.3, 11500, 8000, 2_000_000),
    'alliance_sensor_station': ('Alliance sensor station', ((-46.4, 46.4), (-12.8, 30.48), (-24.8, 16.24)), 40.8, 11500, 8000, 2_000_000),
    'legion_sensor_station': ('Legion sensor station', ((-36.1913, 36.1913), (-14.0, 38.4), (-28.2851, 34.8)), 62.9, 11500, 8000, 2_000_000),
    'syndicate_sensor_station': ('Syndicate sensor station', ((-47.2, 26.3565), (-17.6, 43.857), (-31.137, 21.1423)), 52.1, 11500, 8000, 2_000_000),
    'alliance_energy_relay': ('Alliance energy relay', ((-50.4, 50.4), (-8.4078, 13.2078), (-29.36, 20.9846)), 50.1, 11500, 8000, 2_000_000),
    'legion_energy_relay': ('Legion energy relay', ((-41.4372, 41.4372), (-16.0, 31.6), (-25.7713, 46.4)), 71.9, 11500, 8000, 2_000_000),
    'syndicate_energy_relay': ('Syndicate energy relay', ((-47.5594, 46.5284), (-11.2, 23.36), (-46.5402, 34.4011)), 80.7, 11500, 8000, 2_000_000),
    # S06 B3c - the remaining seventeen faction station rows: research / defense / trade /
    # fighter / repair across the three families plus the two Legion and Syndicate shipyards.
    # Same station budget policy as B3a/B3b; `min_length` is the binding's own authored depth
    # (the legacy Z span), which is what a station mesh is measured by rather than a hull's
    # drawn length.
    'alliance_research_station': ('Alliance research station', ((-40.0, 40.0), (-9.6, 39.28), (-25.6, 35.901)), 61.4, 11500, 8000, 2_000_000),
    'legion_research_station': ('Legion research station', ((-46.3156, 46.3156), (-12.4, 13.88), (-33.48, 52.68)), 86.0, 11500, 8000, 2_000_000),
    'syndicate_research_station': ('Syndicate research station', ((-40.0, 36.4), (-7.2, 37.68), (-27.572, 32.8)), 60.2, 11500, 8000, 2_000_000),
    'alliance_defense_platform': ('Alliance defense platform', ((-45.92, 45.92), (-4.8, 11.166), (-44.32, 44.32)), 88.5, 11500, 8000, 2_000_000),
    'legion_defense_platform': ('Legion defense platform', ((-50.2043, 50.2043), (-8.4, 16.544), (-31.2764, 55.68)), 86.8, 11500, 8000, 2_000_000),
    'syndicate_defense_platform': ('Syndicate defense platform', ((-45.9679, 30.3691), (-10.8, 22.1), (-28.5448, 28.0475)), 56.4, 11500, 8000, 2_000_000),
    'alliance_trade_station': ('Alliance trade station', ((-44.0, 44.0), (-5.948, 6.12), (-38.736, 39.36)), 77.9, 11500, 8000, 2_000_000),
    'legion_trade_station': ('Legion trade station', ((-43.7668, 43.7668), (-6.552, 18.28), (-46.0532, 46.0532)), 91.9, 11500, 8000, 2_000_000),
    'syndicate_trade_station': ('Syndicate trade station', ((-52.3122, 45.2571), (-8.8, 24.5), (-48.6483, 46.5606)), 95.0, 11500, 8000, 2_000_000),
    'alliance_fighter_platform': ('Alliance fighter platform', ((-48.0, 48.0), (-9.2, 6.92), (-39.2, 39.2)), 78.2, 11500, 8000, 2_000_000),
    'legion_fighter_platform': ('Legion fighter platform', ((-42.4021, 42.4021), (-8.8, 11.88), (-36.4, 36.0)), 72.2, 11500, 8000, 2_000_000),
    'syndicate_fighter_platform': ('Syndicate fighter platform', ((-39.6, 32.1135), (-15.2, 30.8), (-39.2, 39.2)), 78.2, 11500, 8000, 2_000_000),
    'alliance_repair_dock': ('Alliance repair dock', ((-38.4, 38.4), (-12.8, 23.6), (-33.6, 39.6)), 73.0, 11500, 8000, 2_000_000),
    'legion_repair_dock': ('Legion repair dock', ((-40.1472, 40.1472), (-14.8, 26.4), (-36.4, 36.4)), 72.6, 11500, 8000, 2_000_000),
    'syndicate_repair_dock': ('Syndicate repair dock', ((-37.4318, 39.7528), (-16.8, 34.8), (-38.931, 37.9495)), 76.7, 11500, 8000, 2_000_000),
    'legion_shipyard': ('Legion shipyard', ((-62.04, 62.04), (-5.6, 41.6), (-45.0564, 62.4)), 107.3, 11500, 8000, 2_000_000),
    'syndicate_shipyard': ('Syndicate shipyard', ((-52.1606, 46.9468), (-18.9928, 45.6), (-53.6606, 48.4056)), 101.9, 11500, 8000, 2_000_000),
}

# S06 B4 - the satellite and planet-installation rows. Envelopes and minimum authored depth are
# the live-code measurements in `tools/art/probe_b4_scope.py`; they are per kind, and the two
# syndicate satellite rows differ because the legacy satellite mesh is parameterised by the
# faction's ring side count and the syndicate's five-sided ring stops short at the rear. These
# rows are script-authoritative per the S03 source-authority policy (repeated modular hardware),
# so `tools/art/build_b4_hardware.py` is the master recipe and the `.blend` is a derived artifact.
# No separate owner class budget exists for modular hardware, so they carry the station class
# budget (11,500 tri / 8,000 vert) rather than a number invented here.
B4_KINDS = {
    'defense_satellite': ('defense satellite', ((-41.1051, 41.1051), (-9.0, 19.5), (-34.0, 44.0))),
    'attack_satellite': ('attack satellite', ((-50.9795, 50.9795), (-9.0, 21.5), (-34.0, 58.0))),
    'planet_extractor': ('planet extractor', ((-34.0, 34.0), (0.0, 43.0), (-32.0, 32.0))),
    'planet_trade_hub': ('trade hub', ((-34.0, 34.0), (0.0, 49.5), (-32.0, 32.0))),
    'planet_shield_generator': ('shield generator', ((-34.0, 34.0), (0.0, 46.5), (-32.0, 32.0))),
    'planet_pulsar_cannon': ('pulsar cannon', ((-34.0, 34.0), (0.0, 42.4), (-32.0, 46.0))),
}
# The two syndicate satellite rows are not faction-independent: the legacy satellite mesh is
# parameterised by the faction's ring side count, so its five-sided ring stops short at the rear.
B4_FACTION_Z_LOW = {('syndicate', 'defense_satellite'): -27.5066,
                    ('syndicate', 'attack_satellite'): -30.299}
# S06 B5 - the one environment row that is geometry: the shared asteroid prop. The row is a *unit*
# prop the field scales, so its envelope is the extent a *typical* legacy rock reaches at scale 1.0
# (x and z within +-0.58, y within +-0.46); the legacy jitter's worst case (+-0.90 / +-0.70) is the
# ceiling the seed asserts against, not the fit - fitting the worst case made every instance bigger
# than the rock it replaced. Its own caps are tighter than the station class on
# purpose: the field draws it forty times, so the prop's budget is the field's budget divided by
# forty, and `validate-models` reports a warning the moment it crosses its own.
ASSETS['shared_asteroid_field'] = ('Shared asteroid prop', ((-0.58, 0.58), (-0.46, 0.46), (-0.58, 0.58)),
                                  0.9, 600, 500, 120_000)
for _faction, _prefix, _family in (('rebel', 'alliance', 'Alliance'), ('confederacy', 'legion',
                                    'Legion'), ('syndicate', 'syndicate', 'Syndicate'),
                                   ('imperial', 'imperial', 'Imperial')):
    for _kind, (_label, _limits) in B4_KINDS.items():
        # The wrapper declares the loader's per-axis pairs - the template walks ENVELOPE[axis] as
        # (low, high) - while a sheet and a sidecar carry [lo, hi] vectors. Two spellings of the
        # same box, and the syndicate override applies to the Z pair.
        _lim = [tuple(a) for a in _limits]
        if (_faction, _kind) in B4_FACTION_Z_LOW:
            _lim[2] = (B4_FACTION_Z_LOW[(_faction, _kind)], _lim[2][1])
        _lim = tuple(_lim)
        ASSETS[f'{_prefix}_{_kind}'] = (f'{_family} {_label}', _lim,
                                        round(_lim[2][1] - _lim[2][0] - 0.2, 1),
                                        11500, 8000, 2_000_000)

# S06 B6 - the Imperial ships, whose first row is the corvette. The envelope and `min_length` are
# the row's own legacy extent, measured from `render/fleet_geometry.py::ship_mesh('needle')` by
# `tools/art/probe_b6_scope.py`; the caps are the standard ship caps, and the row is above the
# 1_800 hull floor, so it declares no floor of its own. Script-authoritative per the S03
# source-authority policy (repeated modular hardware): `tools/art/build_b6_imperial_ships.py` is the
# recipe and `art/blender/imperial_corvette.blend` is a derived artifact.
ASSETS['imperial_corvette'] = ('Vigil Corvette', ((-16.0, 16.0), (-5.0, 24.0), (-43.601, 48.0)),
                               91.4, 11888, 9450, 2_000_000)
# S06 B6 rows 2 and 3 - the two TIE squadron rows. Both are the legacy `wedge` squadron
# archetype, measured from `render/fleet_geometry.py::ship_mesh('wedge')` by
# `tools/art/probe_b6_scope.py` at the same extent -31.250,-3.240,-28.996 .. 31.250,14.000,35.000
# (ShipData.radius=22.0 for the fighter, 24.0 for the bomber), so they share the envelope and the
# Z-span min_length; they are distinct hulls because the seed carries the bomber's heavier pod,
# thicker pylons, doubled wing rim and munition cylinders as row data. The caps are the standard
# ship caps and both rows sit above the 1,800 hull floor, so neither declares a floor of its own.
# Script-authoritative per the S03 source-authority policy (repeated modular hardware):
# `tools/art/build_b6_imperial_ships.py` is the recipe and the `.blend` is a derived artifact.
ASSETS['imperial_tie_squadron'] = ('Talon Interceptor Squadron',
                                   ((-31.25, 31.25), (-3.24, 14.0), (-28.996, 35.0)),
                                   63.8, 11888, 9450, 2_000_000)
ASSETS['imperial_tie_bomber_squadron'] = ('Hammer Torpedo Squadron',
                                          ((-31.25, 31.25), (-3.24, 14.0), (-28.996, 35.0)),
                                          63.8, 11888, 9450, 2_000_000)


def template():
    """The template body, without its own header comment block."""
    text = TEMPLATE_PATH.read_text(encoding='utf-8')
    start = text.index(FIRST_LINE)
    return text[start:]


def render(identifier):
    label, envelope, min_length, max_triangles, max_vertices, max_bytes = ASSETS[identifier]
    floor = MIN_TRIANGLES.get(identifier)
    if floor is None:
        floor_declaration, floor_assertion = '', FLOOR_DEFAULT_ASSERTION
    else:
        floor_declaration = (
            "# A declared small prop (owner decision `s06-small-prop-class-2026-10-17`): the renderer\n"
            "# draws this asset many times per frame, so it is built with the surface density of the\n"
            f"# thing it replaces rather than of a station. Its floor is {floor} triangles.\n"
            f"MIN_TRIANGLES = {floor}\n")
        floor_assertion = ("    assert MIN_TRIANGLES < asset['triangle_count'] <= MAX_TRIANGLES,"
                           "asset['triangle_count']")
    text = template()
    for token, value in (('@@IDENTIFIER@@', identifier), ('@@LABEL@@', label),
                         ('@@ENVELOPE@@', repr(envelope)), ('@@MIN_LENGTH@@', repr(min_length)),
                         ('@@FLOOR_DECLARATION@@', floor_declaration),
                         ('@@FLOOR_ASSERTION@@', floor_assertion),                         ('@@MAX_TRIANGLES@@', repr(max_triangles)), ('@@MAX_VERTICES@@', repr(max_vertices)),
                         ('@@MAX_BYTES@@', '{:,}'.format(max_bytes).replace(',', '_'))):
        assert token in text, token
        text = text.replace(token, value)
    for slot in SLOTS:
        assert slot not in text, slot
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='report drift and exit 1')
    args = parser.parse_args()
    stale, written = [], []
    for identifier in ASSETS:
        path = ROOT / f'tools/art/export_{identifier}.py'
        wanted = render(identifier)
        current = path.read_text(encoding='utf-8') if path.exists() else None
        if current == wanted:
            continue
        stale.append(identifier)
        if not args.check:
            path.write_text(wanted, encoding='utf-8', newline='\n')
            written.append(identifier)
    for identifier in stale:
        print(('DRIFT ' if args.check else 'WROTE ') + identifier)
    if args.check and stale:
        return 1
    print(f'{len(ASSETS) - len(stale)} up to date, {len(written)} written')
    return 0


if __name__ == '__main__':
    sys.exit(main())
