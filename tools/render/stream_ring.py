"""Stream a running match into the W02 ring, for the native viewer to consume.

This is the producer half of the live link: a real `GameManager` is stepped at a fixed dt,
and every step is gathered into the v2 frame profile and published into the ring. It is not
the game's own main loop — that integration is a later step — but the frames come from a
running simulation, not from a file.

The session's binding/kind tables are written once beside the ring (`<ring>.tables`) because
the frame records only index them; the viewer refuses frames whose table it does not hold.

Frames carry every entity (`all_visible`), because the renderer's per-player visibility set
is the live-integration seam: recomputing it here with `state.can_see` costs ~45 ms a frame
(see docs/RENDER_BRIDGE_W02.md section 4).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game.core  # noqa: F401  core/systems import cycle, per the project skill
from game.graphics_benchmark import make_fixture
from render import asset_selection
from render.ship_sizes import ship_size
from render_bridge import collect, packed, ring


def configure_assets():
    from tools.render.dump_snapshot import _default_selection
    asset_selection.configure(_default_selection(), asset_root=ROOT, pack_root=ROOT / 'visual_packs')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ring', type=Path, required=True)
    parser.add_argument('--fixture', default='four-player-combat-v1')
    parser.add_argument('--seconds', type=float, default=10.0)
    parser.add_argument('--hz', type=float, default=60.0, help='Publish cadence (0 = unthrottled)')
    parser.add_argument('--slot-bytes', type=int, default=1 << 20)
    parser.add_argument('--slots', type=int, default=8)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)

    configure_assets()
    fixture = make_fixture(args.fixture)
    state, ds = fixture.manager.state, fixture.manager.ds
    _, _, stats = collect.collect(
        state, ds, None, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, all_visible=True)
    tables = stats['tables']
    collector = collect.FrameCollector(
        ds, tables, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, all_visible=True)

    args.ring.parent.mkdir(parents=True, exist_ok=True)
    tables_path = Path(str(args.ring) + '.tables')
    tables_path.write_bytes(tables.encode())

    buffer = bytearray(packed.frame_size(packed.MAX_INSTANCES, packed.MAX_EFFECTS))
    encode_ms, step_ms = [], []
    published = 0
    period = 1.0 / args.hz if args.hz > 0 else 0.0
    started = time.monotonic()
    deadline = started + args.seconds if args.seconds > 0 else None
    next_at = started
    with ring.Ring.create(args.ring, slots=args.slots, slot_bytes=args.slot_bytes) as out:
        try:
            while True:
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    break
                step_started = time.perf_counter()
                fixture.manager.step(1.0 / 60.0)
                step_ms.append((time.perf_counter() - step_started) * 1000.0)
                frame_started = time.perf_counter()
                frame, counts = collector.collect_into(
                    state, buffer, tick=state.tick, frame_index=published)
                out.publish(bytes(frame))
                encode_ms.append((time.perf_counter() - frame_started) * 1000.0)
                published += 1
                if period:
                    next_at += period
                    sleep = next_at - time.monotonic()
                    if sleep > 0:
                        time.sleep(sleep)
                    else:
                        next_at = time.monotonic()
        except KeyboardInterrupt:
            pass

    elapsed = time.monotonic() - started
    summary = {
        'tool': 'stream_ring',
        'fixture': args.fixture,
        'ring': str(args.ring),
        'tables': str(tables_path),
        'tables_crc32': tables.crc32,
        'bindings': len(tables.bindings),
        'kinds': len(tables.kinds),
        'published_frames': published,
        'ticks_advanced': state.tick,
        'elapsed_s': round(elapsed, 3),
        'publish_hz': round(published / elapsed, 2) if elapsed else 0.0,
        'encode_ms': _stats(encode_ms),
        'sim_step_ms': _stats(step_ms),
        'visibility': 'all_visible (player visibility is the live-integration seam)',
        'instances_last_frame': counts['instances'],
        'transients_last_frame': counts['effects'],
    }
    text = json.dumps(summary, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n', encoding='utf-8')
    return 0


def _stats(values):
    if not values:
        return {'samples': 0}
    ordered = sorted(values)
    return {'samples': len(values),
            'median_ms': round(statistics.median(ordered), 3),
            'p95_ms': round(ordered[max(0, int(0.95 * len(ordered)) - 1)], 3),
            'max_ms': round(ordered[-1], 3)}


if __name__ == '__main__':
    raise SystemExit(main())
