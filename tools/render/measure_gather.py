"""W02 producer cost at a *steady state*, with real effects and real visibility.

`measure_bridge.py` measures the fixture at tick 0 (no fire in the air) and a synthetic
ceiling. Neither is what a live frame looks like, so this tool advances the real
simulation into combat and measures the production gather on what it finds:

* **all-visible** — every entity and every transient in the frame.
* **detection, set supplied** — the renderer's own visibility answers, handed in as an
  id set plus fog predicates, exactly how the live writer is meant to be used.

The cost of *computing* those answers (`state.can_see` per entity) is timed separately
and never folded into the gather, because that work belongs to the renderer that needs
it for its own draw list.

Read-only: the state hash is compared before and after.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import game.core  # noqa: F401  break the core/systems import cycle before anything else
from game.benchmark import state_hash
from game.graphics_benchmark import make_fixture
from render import asset_selection, fog
from render.ship_sizes import ship_size
from render_bridge import collect, packed
from tools.render.dump_snapshot import _default_selection

GATE_MS = 1.0
LOCAL_PLAYER = 0


def configure_assets():
    selection = _default_selection()
    report = asset_selection.configure(selection, asset_root=ROOT, pack_root=ROOT / 'visual_packs')
    if any(not pack['accepted'] for pack in report['pack_order']):
        raise SystemExit('a current default visual pack was rejected; refusing a stale fallback')
    if not report['coverage']['ok']:
        raise SystemExit('approved catalogue is incomplete')


def stats(values):
    if not values:
        return {'samples': 0}
    ordered = sorted(values)
    return {'samples': len(values),
            'median_ms': round(statistics.median(ordered), 3),
            'p95_ms': round(ordered[max(0, int(0.95 * len(ordered)) - 1)], 3),
            'max_ms': round(ordered[-1], 3)}


def measure(collector, state, buffer, repeats):
    times, counts = [], None
    for index in range(repeats):
        started = time.perf_counter()
        _, counts = collector.collect_into(state, buffer, tick=state.tick, frame_index=index)
        times.append((time.perf_counter() - started) * 1000.0)
    return stats(times), counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', default='four-player-combat-v1')
    parser.add_argument('--ticks', type=int, default=300, help='Ticks to advance before measuring')
    parser.add_argument('--repeats', type=int, default=60)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)

    configure_assets()
    fixture = make_fixture(args.fixture)
    manager = fixture.manager
    state = manager.state
    # Let the match reach the state the fixture is named for: hulls engaged, shots in the
    # air, hulls dying. 300 ticks is the fixture's own documented ceiling. Stepping is
    # what changes state, so the read-only hash is taken after it, not before.
    ticks = 0
    while ticks < args.ticks and any(entity.alive for entity in state.entities.values()):
        manager.step(1.0 / 60.0)
        ticks += 1
    before = state_hash(state)

    _, _, seeded = collect.collect(
        state, manager.ds, None, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, local_player=LOCAL_PLAYER,
        all_visible=True)
    tables = seeded['tables']
    buffer = bytearray(packed.frame_size(packed.MAX_INSTANCES, packed.MAX_EFFECTS))

    everything = collect.FrameCollector(
        manager.ds, tables, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, all_visible=True)
    all_visible_stats, all_visible_counts = measure(everything, state, buffer, args.repeats)

    # What the renderer already knows, computed once per frame outside the gather.
    seen_started = time.perf_counter()
    visible_ids = {entity.id for entity in state.entities.values()
                   if entity.alive and state.can_see(LOCAL_PLAYER, entity.id)}
    seen_ms = (time.perf_counter() - seen_started) * 1000.0

    # Fog decisions for transients are the renderer's work and cost real money per
    # effect, so they are timed here once and handed to the gather as an identity set
    # instead of being called back per record inside the measured region.
    filter_started = time.perf_counter()
    visible_effects = {id(effect) for effect in state.effects
                       if fog.effect_visible(state, LOCAL_PLAYER, effect)}
    visible_shots = {id(shot) for shot in state.projectiles.values()
                     if state.is_position_visible(LOCAL_PLAYER, shot.pos)}
    fog_filter_ms = (time.perf_counter() - filter_started) * 1000.0

    detection = collect.FrameCollector(
        manager.ds, tables, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, local_player=LOCAL_PLAYER,
        all_visible=False, visible_ids=visible_ids,
        effect_allow=visible_effects, projectile_allow=visible_shots)
    detection_stats, detection_counts = measure(detection, state, buffer, args.repeats)

    after = state_hash(state)
    report = {
        'tool': 'measure_gather',
        'fixture': args.fixture,
        'ticks_advanced': ticks,
        'repeats': args.repeats,
        'gate_ms': GATE_MS,
        'live_composition': {'instances': all_visible_counts['instances'],
                             'transients': all_visible_counts['effects'],
                             'bytes_all_visible': all_visible_counts['instances'] * packed.INSTANCE.size
                                                 + all_visible_counts['effects'] * packed.EFFECT.size
                                                 + packed.FRAME.size},
        'all_visible': {'total': all_visible_stats,
                        'instances': all_visible_counts['instances'],
                        'transients': all_visible_counts['effects'],
                        'gate_met': all_visible_stats['median_ms'] <= GATE_MS},
        'detection_set_supplied': {'total': detection_stats,
                                   'instances': detection_counts['instances'],
                                   'transients': detection_counts['effects'],
                                   'gate_met': detection_stats['median_ms'] <= GATE_MS},
        'visibility_query_ms': round(seen_ms, 3),
        'transient_fog_filter_ms': round(fog_filter_ms, 3),
        'transient_fog_filter_note': ('render.fog.effect_visible / is_position_visible for every '
                                      'transient, once, outside the gather. The legacy renderer '
                                      'pays this per frame too; the C++ path should filter '
                                      'transients against the fog mask instead of querying.'),
        'transient_counts_after_filter': {'effects': len(visible_effects),
                                          'projectiles': len(visible_shots)},
        'visibility_query_note': ('state.can_see for every entity, once, outside the gather. '
                                 'The renderer pays this for its own draw list; it is not part '
                                 'of the serialization budget.'),
        'state_sha256_before': before,
        'state_sha256_after': after,
        'state_unchanged': before == after,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + '\n', encoding='utf-8')
    return 0 if (before == after) else 3


if __name__ == '__main__':
    raise SystemExit(main())
