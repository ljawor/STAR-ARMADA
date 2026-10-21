"""W02 producer receipt: gather + pack + publish cost for one real frame.

Prints the numbers the W02 gate is judged on and, with `--out`, writes them as JSON.
Nothing here is a frame rate: this is the Python-side cost of handing one frame to a
native consumer, measured on the shipped fixture with the shipped default packs.

Two frames are measured, and the difference matters:

* **shipped** — the fixture as it stands (600 combat ships plus infrastructure). The
  fixture starts at tick 0 with no fire in the air, so its transient count is real: 0.
* **worst case** — the same real instances plus a synthetic transient set at the
  simulation's own ceilings (`1200` effects, `200` projectiles, both caps in
  `game/core/state.py`). Labelled synthetic because only a fight in progress produces
  them; the records themselves are packed by the production packer.

The state hash is compared before and after: the producer is read-only, and this tool
asserts it rather than trusting it.
"""
from __future__ import annotations

import argparse
import json
import random
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
from render import asset_selection
from render.ship_sizes import ship_size
from render_bridge import collect, packed, ring
from tools.render.dump_snapshot import _default_selection

WARMUP, REPS = 10, 120
GATE_MS = 1.0


def configure_assets():
    selection = _default_selection()
    report = asset_selection.configure(selection, asset_root=ROOT, pack_root=ROOT / 'visual_packs')
    if any(not pack['accepted'] for pack in report['pack_order']):
        raise SystemExit('a current default visual pack was rejected; refusing a stale fallback')
    if not report['coverage']['ok']:
        raise SystemExit('approved catalogue is incomplete')
    return report


def synthetic_transients(tables, effects=1200, projectiles=200):
    """Records at the simulation's own caps, deterministic and clearly synthetic."""
    rng = random.Random(20261021)
    kind_ids = [index for index, name in enumerate(tables.kinds)] or [0]
    out = []
    for _ in range(effects):
        out.append(packed.effect_record(
            cls=packed.EFFECT_CLASS, kind_id=rng.choice(kind_ids),
            position=(rng.uniform(-40000, 40000), rng.uniform(-8000, 8000), rng.uniform(-40000, 40000)),
            life=rng.uniform(0.0, 1.0), size=rng.uniform(1.0, 60.0),
            color=(rng.random(), rng.random(), rng.random(), 1.0)))
    for _ in range(projectiles):
        out.append(packed.effect_record(
            cls=packed.PROJECTILE_CLASS, kind_id=rng.choice(kind_ids),
            position=(rng.uniform(-40000, 40000), rng.uniform(-8000, 8000), rng.uniform(-40000, 40000)),
            velocity=(rng.uniform(-40, 40), rng.uniform(-40, 40), rng.uniform(-40, 40)),
            life=rng.uniform(0.0, 2.0), size=rng.uniform(1.0, 8.0),
            color=(1.0, 0.8, 0.3, 1.0), is_beam=False))
    return out


def bench(fn, reps=REPS):
    for _ in range(WARMUP):
        fn()
    samples = []
    for _ in range(reps):
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    samples.sort()
    return {'median_ms': round(statistics.median(samples), 4),
            'p95_ms': round(samples[int(len(samples) * 0.95) - 1], 4),
            'max_ms': round(samples[-1], 4), 'reps': len(samples)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', default='four-player-combat-v1')
    parser.add_argument('--ring', type=Path, help='ring file to publish into (default: scratch)')
    parser.add_argument('--out', type=Path, help='write the receipt JSON here')
    args = parser.parse_args(argv)

    configure_assets()
    fixture = make_fixture(args.fixture)
    state, ds = fixture.manager.state, fixture.manager.ds
    before = state_hash(state)

    _, _, stats = collect.collect(
        state, ds, None, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, all_visible=True)
    tables = stats['tables']
    ring_path = args.ring or (Path.home() / '.hermes' / 'cache' / 'scratch' / 'w02-ring.bin')
    worst = synthetic_transients(tables)
    buffer = bytearray(packed.frame_size(packed.MAX_INSTANCES, packed.MAX_EFFECTS))

    # The renderer already knows which entities a player can see. Stand in for it once,
    # outside every timed region: in the live writer this set arrives per frame.
    visible = {entity.id for entity in state.entities.values()
               if entity.alive and not entity.is_planet
               and state.can_see(0, entity.id)}

    modes = (
        ('all-visible', dict(all_visible=True)),
        ('detection-set-supplied', dict(all_visible=False, visible_ids=visible)),
        ('detection-recomputed', dict(all_visible=False)),
    )

    receipts = []
    for mode, options in modes:
        collector = collect.FrameCollector(
            ds, tables, asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, local_player=0, **options)
        for label, extra in (('shipped', ()), ('worst-case-synthetic', worst)):
            with ring.Ring.create(ring_path, slots=8, slot_bytes=1 << 20) as out:
                def encode():
                    return collector.collect_into(state, buffer, tick=state.tick,
                                                  frame_index=0, extra_effects=extra)

                frame_bytes, counts = encode()
                frame_bytes = bytes(frame_bytes)

                def publish():
                    out.publish(frame_bytes)

                def combined():
                    collector.collect_into(state, buffer, tick=state.tick,
                                           frame_index=0, extra_effects=extra)
                    out.publish(frame_bytes)

                encode_ms, publish_ms = bench(encode), bench(publish)
                combined_ms = bench(combined)
                decoded = packed.unpack_frame(out.latest()[1], tables)

            total = round(encode_ms['median_ms'] + publish_ms['median_ms'], 4)
            receipt = {
                'visibility': mode, 'frame': label,
                'instances': counts['instances'], 'transients': counts['effects'],
                'omitted_planets': counts['omitted_planets'],
                'unknown_bindings': counts['unknown_bindings'],
                'frame_bytes': len(frame_bytes),
                'decode_roundtrip_instances': len(decoded['instances']),
                'decode_roundtrip_transients': len(decoded['effects']),
                'encode': encode_ms, 'publish': publish_ms, 'combined': combined_ms,
                'producer_total_ms': total,
                'gate_ms': GATE_MS, 'gate_pass': total <= GATE_MS,
            }
            receipts.append(receipt)
            print(f"{mode:<24} {label:<20} {counts['instances']:>4} inst "
                  f"{counts['effects']:>5} tr {len(frame_bytes):>8,} B  "
                  f"encode {encode_ms['median_ms']:8.3f} publish {publish_ms['median_ms']:6.3f} "
                  f"= {total:8.3f} ms  {'PASS' if receipt['gate_pass'] else 'FAIL'}")

    if state_hash(state) != before:
        raise SystemExit('producer mutated simulation state')
    print(f'state_sha256 unchanged: {before[:16]}…')

    payload = {
        'receipt': 'w02-producer-v2-packed',
        'fixture': args.fixture,
        'gate_ms': GATE_MS,
        'labels': [
            'Python producer only: gather + pack + publish. Not end-to-end latency, not a frame rate.',
            'worst-case transients are synthetic at the simulation ceilings (1200 effects, 200 projectiles)',
            'one process, no concurrent suite; see loadavg in the environment block',
        ],
        'frames': receipts,
        'tables': {'bindings': len(tables.bindings), 'kinds': len(tables.kinds),
                   'crc32': tables.crc32, 'bytes': len(tables.encode())},
        'environment': {'python': sys.version.split()[0],
                        'platform': sys.platform, 'loadavg': list(__import__('os').getloadavg())},
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        print(f'receipt: {args.out}')
    return 0 if all(frame['gate_pass'] for frame in receipts) else 1


if __name__ == '__main__':
    raise SystemExit(main())
