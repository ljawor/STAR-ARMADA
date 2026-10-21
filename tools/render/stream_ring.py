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
import signal
import json
from pathlib import Path
import pygame
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import game.core  # noqa: F401  core/systems import cycle, per the project skill
from game.graphics_benchmark import make_fixture
from render import asset_selection, emissive_batch, fog, primitive_batch
from render.renderer import projectile_extents
from render_bridge import emissive as emissive_codec
from render_bridge import markers as marker_codec
from render.ship_sizes import ship_size
from render_bridge import collect, packed, ring


def configure_assets():
    from tools.render.dump_snapshot import _default_selection
    asset_selection.configure(_default_selection(), asset_root=ROOT, pack_root=ROOT / 'visual_packs')


def _stop_on_sigterm(signum, frame):
    """Turn SIGTERM into the same path Ctrl-C takes, so the summary is still written.

    A launcher that kills its producer would otherwise lose the report that says what happened,
    including the input counters, and a shell-started background job ignores SIGINT by default.
    """
    raise KeyboardInterrupt


def main(argv=None):
    signal.signal(signal.SIGTERM, _stop_on_sigterm)
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
    parser.add_argument('--fog-ring', type=Path,
                        help='ring carrying the classified fog mask to the window (W05 slice 4); '
                             'published once per change, not per frame')
    parser.add_argument('--planet-ring', type=Path,
                        help='ring carrying planet textures to the window (W05); one blob per '
                             'distinct planet, published once')
    parser.add_argument('--planet-texture', type=int, default=256,
                        help='planet texture edge in pixels (W05)')
    parser.add_argument('--emit-ring', type=Path,
                        help='ring carrying weapon fire, beams, glows and jump rings (W05 slice 3)')
    parser.add_argument('--marker-ring', type=Path,
                        help='ring carrying selection rings, planet owner rings and ownership '
                             'markers as primitives (W05 slice 2)')
    parser.add_argument('--marker-mode', choices=('all', 'hostiles', 'off'), default='all',
                        help='which ownership markers to publish (all = every detected unit; '
                             'hostiles = the game\'s decluttered mode)')
    parser.add_argument('--select', action='append', metavar='ID',
                        help='entity id to draw a selection ring around (repeatable)')
    parser.add_argument('--select-owned', action='store_true',
                        help='diagnostic stand-in for live selection: ring every own ship')
    parser.add_argument('--input-ring', type=Path,
                        help='ring the C++ window publishes input on (W04); the producer attaches '
                             'when the file appears and feeds every event to the real '
                             'InputController')
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
    # W05 slice 2: the ownership cues (selection rings, planet owner rings, markers) as one batch
    # of primitives. The game decides them here; the window only draws.
    # W05 slice 3: emissive primitives - weapon fire, beams, glows, jump rings.
    emissive_ring = None
    emit_ms, emit_counts = [], []
    if args.emit_ring is not None:
        emit_slot_bytes = (emissive_codec.HEADER.size
                           + emissive_codec.MAX_RECORDS * emissive_codec.RECORD_BYTES)
        args.emit_ring.parent.mkdir(parents=True, exist_ok=True)
        emissive_ring = ring.Ring.create(args.emit_ring, slots=8, slot_bytes=emit_slot_bytes)

    def weapon_type_of(weapon_id):
        weapon = ds.weapons.get(weapon_id) if weapon_id is not None else None
        return weapon.type if weapon is not None else None

    marker_ring = None
    marker_ms, marker_counts = [], []
    selected_ids = set(int(v) for v in (args.select or []))
    if marker_ring_path := args.marker_ring:
        slot_bytes = marker_codec.HEADER.size + marker_codec.MAX_RECORDS * marker_codec.RECORD_BYTES
        marker_ring_path.parent.mkdir(parents=True, exist_ok=True)
        marker_ring = ring.Ring.create(marker_ring_path, slots=8, slot_bytes=slot_bytes)
    if args.select_owned:
        # Diagnostic stand-in, and the same one the HUD panel already uses: every own ship. Live
        # selection itself is still W04 debt (the input bridge records orders, not selection).
        selected_ids |= {entity.id for entity in state.entities.values()
                         if entity.owner == args.local_player and entity.is_ship}
    def radius_of(entity):
        """World radius of the hull the frame drew, so a ring encloses what it is drawn around.

        `instance scale` is a multiplier on a mesh authored at catalogue size, so a ring built
        from it sits a few percent wide of the hull. `ship_size(...).radius` is the same world
        radius the legacy renderer rings, minus its camera-dependent readability inflation, which
        the window replaces with a pixel floor of its own.
        """
        if entity.is_planet or entity.is_station:
            return float(entity.radius)
        faction = (state.players[entity.owner].faction
                   if entity.owner in state.players else 'imperial')
        binding, scale = collector.visual(is_station=entity.is_station, data_id=entity.data_id,
                                          faction=faction, radius=entity.radius)
        if not isinstance(scale, (int, float)):
            return 0.0        # unresolved binding: not drawn, so no cue around something invisible
        size = ship_size(ds, entity.data_id, faction)
        return float(getattr(size, 'radius', 0.0))
    overlay_ring = overlay_hud = None
    overlay_width, overlay_height = (int(v) for v in args.overlay_size.lower().split('x'))
    overlay_selection = set()
    overlay_sent = []
    overlay_published = 0
    overlay_keyframes = 0
    overlay_last_full = float('-inf')
    if args.overlay_ring is not None:
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

    # W04: the window records events, this process decides what they mean. The bridge attaches
    # when the window creates its ring, so either can start first.
    input_bridge = None
    controller = None
    input_bridge_factory = None
    input_attached_at = None
    input_poll_ms = []
    input_messages = []
    if args.input_ring is not None and overlay_hud is not None:
        from types import SimpleNamespace
        from render.camera import Camera
        from render.input import InputController
        from render.input_bridge import RingInput
        input_camera = Camera(overlay_width, overlay_height)
        paused = {'value': False}

        def _toggle_pause():
            paused['value'] = not paused['value']

        controller = InputController(state, input_camera, overlay_hud,
                                     SimpleNamespace(toggle_pause=_toggle_pause,
                                                     request_exit=lambda: None,
                                                     flash=input_messages.append))
        input_bridge_factory = lambda: RingInput(  # noqa: E731
            args.input_ring, controller, (overlay_width, overlay_height))

    # W05 slice 4: the fog mask. Python classifies one texel per visibility cell (visible / charted
    # / unexplored) and the window samples it; the mask is republished only when that classification
    # changes, because the mask is derived data and re-deriving it natively would be a second
    # opinion about what the player can see.
    fog_ring = None
    fog_mask = None
    fog_generation = 0
    fog_uploads = 0
    fog_last_surface = None
    fog_encode_ms = []
    fog_cells = 0
    if args.fog_ring is not None:
        import math
        from render_bridge import fogmap as fog_codec
        cells = max(1, math.ceil(state.map_info.bounds / state.visibility_cell_size))
        # The ring reserves 20 bytes for its begin tag and length, and the slot's last 8 bytes for
        # the completing tag: 28 in all. A mask sized to the wrong figure either has its tail
        # overwritten by that tag (and then fails its own crc) or is refused outright.
        slot_bytes = fog_codec.HEADER_BYTES + cells * cells * 4 + 28
        args.fog_ring.parent.mkdir(parents=True, exist_ok=True)
        fog_ring = ring.Ring.create(args.fog_ring, slots=4, slot_bytes=slot_bytes)
        fog_mask = fog.FogMask()
        fog_cells = cells

    # W05: planets travel as instances whose binding names a texture; the textures go over their
    # own ring, once each, because they are static for the life of a match.
    planet_ring = None
    planet_textures = None
    planet_blob_bytes = []
    planet_encode_ms = []
    if args.planet_ring is not None:
        from render.planet_blobs import PlanetTextures
        from render_bridge import planets as planet_codec
        size = int(args.planet_texture)
        if not 64 <= size <= 512:
            raise SystemExit('--planet-texture must be 64..512')
        slot_bytes = planet_codec.HEADER_BYTES + planet_codec.MAX_NAME + size * size * 4
        args.planet_ring.parent.mkdir(parents=True, exist_ok=True)
        planet_ring = ring.Ring.create(args.planet_ring, slots=8, slot_bytes=slot_bytes)
        planet_textures = PlanetTextures(size=size)

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
                if args.input_ring is not None and overlay_hud is not None:
                    if input_bridge is None and input_bridge_factory and args.input_ring.exists():
                        input_bridge = input_bridge_factory()
                        input_attached_at = time.monotonic()
                    if input_bridge is not None and controller is not None:
                        poll_started = time.perf_counter()
                        # Drain everything: a click must never be lost because the simulation
                        # ticked slowly. The cost is that a press and its release can land in one
                        # tick, so held-key camera motion degrades when the tick is slower than
                        # the window -- reported, not hidden, in docs/RENDER_DRAW_LIST_W04.md.
                        input_bridge.poll()
                        controller.update(1.0 / 60.0)
                        input_poll_ms.append((time.perf_counter() - poll_started) * 1000.0)
                        if controller.selection:
                            overlay_selection = set(controller.selection)
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
                if emissive_ring is not None:
                    emit_started = time.perf_counter()
                    effect_allow = seen_state.get('effects') if detection else None
                    shot_allow = seen_state.get('shots') if detection else None
                    effects = [fx for fx in state.effects
                               if effect_allow is None or id(fx) in effect_allow]
                    shots = [shot for shot in state.projectiles.values()
                             if shot_allow is None or id(shot) in shot_allow]
                    emit_primitives, emit_stats = emissive_batch.build(
                        effects, shots, weapon_type_of, projectile_extents)
                    # W05 slice 5: standing shield shells. The window cannot know a unit's shield
                    # fraction and must not guess it from hull damage, so the bubble crosses as a
                    # tint plus a strength and the window builds the shell at its own camera.
                    # `visible_ids is None` means the frame carries every entity (omniscient
                    # diagnostic), so visibility is not a filter in that mode.
                    shown = collector.visible_ids
                    shielded = [entity for entity in state.entities.values()
                                if entity.alive
                                and (entity.is_ship or entity.is_squadron or entity.is_station)
                                and (shown is None or entity.id in shown)]
                    shield_primitives = emissive_batch.shields(shielded, radius_of)
                    emit_primitives = emit_primitives + shield_primitives
                    emit_stats['shields'] = len(shield_primitives)
                    emit_stats['primitives'] = len(emit_primitives)
                    emissive_ring.publish(bytes(emissive_codec.encode(emit_primitives)))
                    emit_ms.append((time.perf_counter() - emit_started) * 1000.0)
                    emit_counts.append(emit_stats)
                if marker_ring is not None:
                    cues_started = time.perf_counter()
                    primitives = primitive_batch.build(
                        state, args.local_player, selected_ids, collector.visible_ids,
                        radius_of=radius_of, mode=args.marker_mode)
                    marker_ring.publish(bytes(marker_codec.encode(primitives)))
                    marker_ms.append((time.perf_counter() - cues_started) * 1000.0)
                    marker_counts.append(len(primitives))
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
                if planet_ring is not None and planet_textures is not None:
                    # Encoding is the expensive half (a procedural 256x256 surface per new
                    # planet), so it is timed rather than inferred from the blob size.
                    planet_started = time.perf_counter()
                    pending = planet_textures.pending(state)
                    if pending:
                        for blob in pending:
                            planet_ring.publish(blob)
                            planet_blob_bytes.append(len(blob))
                        planet_encode_ms.append(
                            (time.perf_counter() - planet_started) * 1000.0)
                if fog_ring is not None:
                    fog_started = time.perf_counter()
                    surface = fog_mask.surface(state, args.local_player)
                    if surface is not fog_last_surface:
                        fog_generation += 1
                        rgba = pygame.image.tobytes(surface, 'RGBA', False)
                        fog_ring.publish(bytes(fog_codec.encode_blob(
                            surface.get_width(), state.visibility_cell_size,
                            state.map_info.bounds, fog_generation, rgba)))
                        fog_last_surface = surface
                        fog_uploads += 1
                        fog_encode_ms.append((time.perf_counter() - fog_started) * 1000.0)
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
        'fog': ({
            'ring': str(args.fog_ring) if args.fog_ring else None,
            'cells': fog_cells,
            'uploads': fog_uploads,
            'generation': fog_generation,
            'encode_ms': {'median': statistics.median(fog_encode_ms) if fog_encode_ms else 0.0,
                          'worst': max(fog_encode_ms) if fog_encode_ms else 0.0},
            'note': 'one texel per visibility cell; published only when the classification changes',
        } if args.fog_ring else {}),
        'emissive': ({
            'ring': str(args.emit_ring) if args.emit_ring else None,
            'encode_ms': {'median': statistics.median(emit_ms) if emit_ms else 0.0,
                          'worst': max(emit_ms) if emit_ms else 0.0},
            'frames': len(emit_counts),
            'primitives_max': max((c['primitives'] for c in emit_counts), default=0),
            'beams_skipped': sum(c.get('beams_skipped', 0) for c in emit_counts),
            'legacy_shots': sum(c.get('legacy', 0) for c in emit_counts),
            'bolts': sum(c.get('drawn', 0) for c in emit_counts),
            'explosions': sum(c.get('explosions', 0) for c in emit_counts),
            'explosions_skipped': sum(c.get('explosions_skipped', 0) for c in emit_counts),
            'squares': sum(c.get('squares', 0) for c in emit_counts),
            'note': 'beams and glows in world units, bolts in pixels so the window keeps them at '
                    'its own zoom; blasts travel as position/size/age/seed and are rebuilt by the '
                    'window; additive, no depth write',
        } if args.emit_ring else {}),
        'cues': ({
            'ring': str(args.marker_ring) if args.marker_ring else None,
            'mode': args.marker_mode,
            'selection': sorted(selected_ids) if args.select or args.select_owned else [],
            'selection_is_diagnostic': bool(args.select_owned),
            'encode_ms': {'median': statistics.median(marker_ms) if marker_ms else 0.0, 'worst': max(marker_ms) if marker_ms else 0.0},
            'primitives': {'frames': len(marker_counts),
                           'max': max(marker_counts) if marker_counts else 0,
                           'total': sum(marker_counts)},
            'note': 'selection rings, planet owner rings and ownership markers decided in Python; '
                    'marker pixel size is left to the window camera',
        } if args.marker_ring else {}),
        'visibility': ('detection: visible entity ids supplied per frame, fog predicates for '
                       'effects and shots' if detection else
                       'all_visible (omniscient diagnostic)'),
        'renderer_visibility_ms': _stats(visibility_ms),
        'renderer_visibility_note': ('cost of computing what the player can see, measured outside '
                                     'the gather; the bridge receives these answers'),
        'instances_last_frame': counts['instances'],
        'transients_last_frame': counts['effects'],
    }
    if planet_ring is not None:
        planet_ring.close()
        summary['planets'] = {
            'ring': str(args.planet_ring),
            'blob_bytes': {'samples': len(planet_blob_bytes),
                           'total': sum(planet_blob_bytes),
                           'min': min(planet_blob_bytes) if planet_blob_bytes else 0,
                           'max': max(planet_blob_bytes) if planet_blob_bytes else 0},
            'encode_ms': _stats(planet_encode_ms),
            **(planet_textures.report() if planet_textures is not None else {}),
            'note': ('one blob per distinct planet, published once: the texture is procedural and '
                     'static, the sphere is drawn natively from the frame instance scale'),
        }
    if args.input_ring is not None:
        summary['input'] = {
            'ring': str(args.input_ring),
            'attached': input_bridge is not None,
            'attached_after_s': (round(input_attached_at - started, 3)
                                 if input_attached_at is not None else None),
            'poll_ms': _stats(input_poll_ms),
            **(input_bridge.report() if input_bridge is not None else {}),
            'messages': input_messages[-4:],
            'note': ('the window publishes what the pointer and keyboard did; this process still '
                     'runs InputController and the simulation validates every command'),
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
