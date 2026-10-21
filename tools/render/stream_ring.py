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
from render import asset_selection, fog
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
    parser.add_argument('--local-player', type=int, default=0)
    parser.add_argument('--visibility', choices=('detection', 'all'), default='detection',
                        help='detection = the renderer supplies what the player can see; '
                             'all = omniscient diagnostic frame')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--overlay-ring', type=Path,
                        help='second ring carrying the composed HUD surface (W03 design A); '
                             'written beside the frame ring, with its own slots')
    parser.add_argument('--overlay-size', default='1280x800',
                        help='HUD surface size, WxH (the C++ window size)')
    parser.add_argument('--overlay-slots', type=int, default=4)
    parser.add_argument('--overlay-all', action='store_true',
                        help='publish every overlay frame as a full surface (slow; for diagnosis)')
    parser.add_argument('--overlay-keyframe', type=float, default=2.0,
                        help='publish a full overlay surface at least this often, so a window '
                             'that attaches late still gets a complete HUD (0 disables)')
    args = parser.parse_args(argv)

    configure_assets()
    fixture = make_fixture(args.fixture)
    state, ds = fixture.manager.state, fixture.manager.ds
    _, _, stats = collect.collect(
        state, ds, None, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, all_visible=True)
    tables = stats['tables']
    # Two collectors' worth of behaviour, one object: the detection mode is handed the
    # renderer's answers every frame (visible entity ids, plus fog decisions for effects and
    # shots, which are not entities and cannot travel in the id set).
    detection = args.visibility == 'detection'
    seen_state = {'ids': None, 'effects': None, 'shots': None}
    collector = collect.FrameCollector(
        ds, tables, asset_selection=asset_selection, ship_size=ship_size,
        ship_binding=asset_selection.ship_binding, local_player=args.local_player,
        all_visible=not detection,
        visible_ids=set() if detection else None,
        effect_allow=set() if detection else None,
        projectile_allow=set() if detection else None)

    args.ring.parent.mkdir(parents=True, exist_ok=True)
    tables_path = Path(str(args.ring) + '.tables')
    tables_path.write_bytes(tables.encode())

    # W03: the HUD is painted here, by the same Python code the legacy window uses, and only the
    # rects the recorder says changed are published. `compose` is the GL-free half of `render`.
    overlay_ring = overlay_hud = None
    overlay_width, overlay_height = (int(v) for v in args.overlay_size.lower().split('x'))
    overlay_selection = set()
    overlay_sent = []
    overlay_published = 0
    overlay_keyframes = 0
    overlay_last_full = float('-inf')
    if args.overlay_ring is not None:
        import pygame
        pygame.font.init()
        from render.hud import HUD
        from render_bridge import overlay as overlay_codec
        overlay_hud = HUD(overlay_width, overlay_height, state)
        overlay_selection = {entity.id for entity in state.entities.values()
                             if entity.owner == args.local_player and entity.is_ship}
        slot_bytes = (overlay_codec.HEADER_BYTES + overlay_codec.MAX_RECTS * overlay_codec.RECT_BYTES
                      + overlay_width * overlay_height * 4)
        if slot_bytes > (1 << 26):
            raise SystemExit(f'overlay slot would be {slot_bytes} bytes; pick a smaller --overlay-size')
        args.overlay_ring.parent.mkdir(parents=True, exist_ok=True)
        overlay_ring = ring.Ring.create(args.overlay_ring, slots=args.overlay_slots,
                                        slot_bytes=slot_bytes)

    buffer = bytearray(packed.frame_size(packed.MAX_INSTANCES, packed.MAX_EFFECTS))
    encode_ms, step_ms, visibility_ms, hud_ms = [], [], [], []
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
                if detection:
                    # This is the renderer's own cost, measured apart from the gather. The
                    # bridge is supposed to receive these answers, not derive them.
                    seen_started = time.perf_counter()
                    seen_state['ids'] = {entity.id for entity in state.entities.values()
                                         if entity.alive
                                         and state.can_see(args.local_player, entity.id)}
                    seen_state['effects'] = {id(effect) for effect in state.effects
                                             if fog.effect_visible(state, args.local_player, effect)}
                    seen_state['shots'] = {id(shot) for shot in state.projectiles.values()
                                           if state.is_position_visible(args.local_player, shot.pos)}
                    collector.visible_ids = seen_state['ids']
                    collector.effect_allow = seen_state['effects']
                    collector.projectile_allow = seen_state['shots']
                    visibility_ms.append((time.perf_counter() - seen_started) * 1000.0)
                frame_started = time.perf_counter()
                frame, counts = collector.collect_into(
                    state, buffer, tick=state.tick, frame_index=published)
                out.publish(bytes(frame))
                encode_ms.append((time.perf_counter() - frame_started) * 1000.0)
                if overlay_ring is not None:
                    hud_started = time.perf_counter()
                    overlay_hud.compose(overlay_selection, None, args.local_player, False,
                                        '', 0.0, 0.0)
                    dirty = overlay_hud.recorder.take_dirty()
                    # The first frame and periodic keyframes are whole surfaces: a window that
                    # attaches late has no base texture, so dirty rects alone would never
                    # complete the HUD.
                    keyframe = (overlay_published == 0 or args.overlay_all
                                or (args.overlay_keyframe > 0
                                    and time.monotonic() - overlay_last_full
                                    >= args.overlay_keyframe))
                    if keyframe:
                        overlay_last_full = time.monotonic()
                        overlay_keyframes += 1
                        payload = overlay_codec.encode_surface_full(overlay_hud.overlay)
                    else:
                        payload = overlay_codec.encode_surface(overlay_hud.overlay, dirty)
                    overlay_ring.publish(payload)
                    overlay_published += 1
                    overlay_sent.append(len(payload))
                    hud_ms.append((time.perf_counter() - hud_started) * 1000.0)
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

    if overlay_ring is not None:
        overlay_ring.close()
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
        'visibility': ('detection: visible entity ids supplied per frame, fog predicates for '
                       'effects and shots' if detection else
                       'all_visible (omniscient diagnostic)'),
        'renderer_visibility_ms': _stats(visibility_ms),
        'renderer_visibility_note': ('cost of computing what the player can see, measured outside '
                                     'the gather; the bridge receives these answers'),
        'instances_last_frame': counts['instances'],
        'transients_last_frame': counts['effects'],
    }
    if overlay_ring is not None:
        summary['overlay'] = {
            'ring': str(args.overlay_ring),
            'size': [overlay_width, overlay_height],
            'published_frames': overlay_published,
            'frame_bytes': _stats([float(v) for v in overlay_sent]),
            'publish_ms': _stats(hud_ms),
            'publish_note': ('paint the HUD, encode the dirty rects and publish them; the paint is '
                             'renderer work the bridge receives, the encode+publish is the cost of '
                             'this transport'),
            'keyframes': overlay_keyframes,
            'keyframe_seconds': args.overlay_keyframe,
            'note': ('the first overlay frame and every keyframe after --overlay-keyframe seconds '
                     'are whole surfaces; the rest are dirty rects only, so a window that '
                     'attaches late still converges on a complete HUD'),
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
