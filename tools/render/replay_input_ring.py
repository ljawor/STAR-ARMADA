"""Replay a ring written by the native window through the real game controller.

The W03 parity tool proved the HUD crosses the bridge exactly; this is the same idea in the other
direction. `armada_viewer --input-ring r.bin --input-exercise` publishes a scripted click/key
sequence through its real SDL pump. This tool then:

    viewer --input-ring--> ring.bin --> RingInput --> InputController --> GameManager state

and records what the *game* did with it: the camera followed the selection, a held rotation key
moved the yaw and releasing it stopped the yaw, a zoom key changed the distance, and a click
reached the selection path. Nothing here simulates the window's behaviour twice: the events come
from the native encoder and every decision is the production controller's.

    PYTHONPATH=.:tests .venv/bin/python tools/render/replay_input_ring.py \\
        --ring ~/.hermes/cache/scratch/w04/input.bin --report artifacts/.../input-replay.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from game.core.manager import GameManager          # noqa: E402
from game.data.store import DataStore             # noqa: E402
from render.camera import Camera                  # noqa: E402
from render.input import InputController          # noqa: E402
from render.input_bridge import RingInput         # noqa: E402
from render_bridge import input as wire           # noqa: E402

SURFACE = (1280, 800)


def build(seed_ship=True):
    DataStore.reset()
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    state, camera = gm.state, Camera(*SURFACE)
    hud = SimpleNamespace(placement=None, fleet_panel=False, fleet_formation='line',
                          fleet_commander=None, buttons=[], minimap_rect=None, scroll_rects=[])
    messages = []
    paused = {'value': False}

    def toggle_pause():
        paused['value'] = not paused['value']

    app = SimpleNamespace(toggle_pause=toggle_pause, request_exit=lambda: None,
                          flash=messages.append)
    controller = InputController(state, camera, hud, app)
    ship = next(e for e in state.entities.values() if e.owner == 0 and e.alive and e.is_ship)
    if seed_ship:
        controller.selection = {ship.id}
    return gm, state, camera, controller, ship, messages, paused


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ring', required=True)
    parser.add_argument('--report')
    args = parser.parse_args(argv)

    gm, state, camera, controller, ship, messages, paused = build()
    steps = []
    with RingInput(args.ring, controller, SURFACE, from_oldest=True) as bridge:
        # One poll per "frame": the events land in the controller exactly as they would in the
        # game loop, and `update()` is what turns held keys into camera motion.
        while True:
            before = (camera.follow_id, camera.yaw, camera.distance, camera.pitch,
                      len(controller.selection), paused['value'], len(messages))
            delivered = bridge.poll(limit=1)
            controller.update(1 / 30.0)
            after = (camera.follow_id, camera.yaw, camera.distance, camera.pitch,
                     len(controller.selection), paused['value'], len(messages))
            steps.append({'delivered': delivered,
                          'follow_id': camera.follow_id, 'yaw': camera.yaw,
                          'distance': camera.distance, 'pitch': camera.pitch,
                          'selection': sorted(controller.selection),
                          'paused': paused['value'], 'messages': list(messages[-2:]),
                          'changed': [name for name, a, b in
                                      zip(('follow', 'yaw', 'distance', 'pitch', 'selection',
                                           'paused', 'messages'), before, after) if a != b]})
            if delivered == 0:
                if steps[-1]['delivered'] == 0 and len(steps) > 1:
                    break
                steps.append(steps[-1])
        receipt = bridge.report()

    receipt['surface'] = list(SURFACE)
    receipt['steps'] = steps
    receipt['final'] = {'follow_id': camera.follow_id, 'yaw': camera.yaw,
                        'distance': camera.distance, 'pitch': camera.pitch,
                        'selection': sorted(controller.selection), 'paused': paused['value']}
    receipt['checks'] = {
        'events_arrived': receipt['events_delivered'] > 0,
        'some_frame_changed_game_state': any(step['changed'] for step in steps),
        'camera_followed_a_selection': camera.follow_id is not None,
    }
    receipt['verified'] = all(receipt['checks'].values())
    print(json.dumps(receipt, indent=2))
    if args.report:
        path = Path(args.report)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, indent=2) + '\n')
    return 0 if receipt['verified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
