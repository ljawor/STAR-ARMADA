"""Real Cocoa SDL/GL UI and controlled-fixture tutorial continuation probe.
PYTHONPATH=. .venv/bin/python tools/diag_campaign_phase7.py --out DIR
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pygame
from OpenGL import GL
from PIL import Image
from game.core.manager import GameManager
from game.core.state import GameState
from game.core.vectors import Vec3
from game.data.store import DataStore
from render import menus
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.renderer import Renderer


class RecordingSurface(pygame.Surface):
    def blit(self, source, dest, *args, **kwargs):
        if self.recording:
            self.text_rects.append(source.get_rect(topleft=dest))
        return super().blit(source, dest, *args, **kwargs)


class MeasuredHUD(HUD):
    """Observe actual mission-card text surfaces and emitted blocked rectangle."""
    def _mission_panel(self, local_player):
        controls = list(self.blocked_rects)
        self.overlay.text_rects = []
        self.overlay.recording = True
        try:
            super()._mission_panel(local_player)
        finally:
            self.overlay.recording = False
        card = self.blocked_rects[-1]
        rects = self.overlay.text_rects
        inner = card.inflate(-20, -12)
        overflow = max(max(0, inner.left-r.left, r.right-inner.right,
                           inner.top-r.top, r.bottom-inner.bottom) for r in rects)
        overlaps = any(card.colliderect(r) for r in controls)
        assert rects and pygame.Rect(0, 0, self.width, self.height).contains(card)
        assert overflow == 0, (card, rects)
        assert not overlaps, (card, controls)
        assert not any(r.colliderect(s) for i, r in enumerate(rects) for s in rects[i+1:])
        self.mission_measurement = dict(card=list(card), text_rects=[list(r) for r in rects],
            text_overflow_px=overflow, card_control_overlap=overlaps)


def deliver(control, event):
    pygame.event.clear()
    pygame.event.post(event)
    for item in pygame.event.get():
        control.handle_event(item)


def click(control, point):
    deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    assert os.environ.get('SDL_VIDEODRIVER') != 'dummy'
    pygame.display.init(); pygame.font.init()
    report = []
    with tempfile.TemporaryDirectory() as tmp, patch.object(menus, 'CAMPAIGN_PATH', str(Path(tmp) / 'campaign.json')):
        try:
            for width, height in ((1024, 768), (1280, 800)):
                pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
                GL.glViewport(0, 0, width, height)
                pygame.event.pump()
                assert pygame.display.get_driver() == 'cocoa'
                menu = menus.MenuStack(width, height)
                screen = pygame.Rect(0, 0, width, height)
                entry: dict[str, Any] = dict(resolution=[width, height], driver=pygame.display.get_driver(), captures=[],
                             briefings=[], mission_frames={})
                report.append(entry)

                def capture(name):
                    GL.glFinish()
                    raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                    pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    assert int((pixels.max(axis=2) > 85).sum()) > 1000
                    path = args.out / f'{width}_{name}.png'
                    Image.fromarray(pixels).save(path)
                    entry['captures'].append(str(path))
                    pygame.display.flip(); pygame.event.pump()

                def menu_frame(name):
                    panels = []
                    original_panel = menu._panel
                    def panel(rect, alpha=200):
                        panels.append(pygame.Rect(rect)); original_panel(rect, alpha)
                    menu._panel = panel
                    try:
                        menu.render(0)
                    finally:
                        menu._panel = original_panel
                    for i, b in enumerate(menu.buttons):
                        assert screen.contains(b['rect']), b
                        assert not any(b['rect'].colliderect(c['rect']) for c in menu.buttons[i+1:])
                    assert all(screen.contains(r) for r in panels)
                    if menu.screen == 'briefing':
                        assert not any(r.colliderect(b['rect']) for r in panels for b in menu.buttons)
                    menu.draw_gl(); capture(name)

                menu.screen = 'campaign'
                # Fresh profile: mandatory introductory tutorial only.
                menu_frame('fresh_tutorial_only')
                assert [b['payload'] for b in menu.buttons if b['action'] == 'select_mission'] == [0]
                Path(menus.CAMPAIGN_PATH).write_text(json.dumps({'mission_index': 9}))
                assert menus.load_campaign_progress() == 10
                union = set()
                for page in range(3):
                    menu_frame(f'catalogue_page_{page+1}')
                    union.update(menu.campaign_rows)
                    for b in list(menu.buttons):
                        if b['action'] != 'select_mission': continue
                        buttons = list(menu.buttons)
                        click(menu, b['rect'].center)
                        assert menu.screen == 'briefing' and menu.selected_mission == b['payload']
                        mission_id = menu.campaign['missions'][menu.selected_mission]['id']
                        menu_frame('briefing_' + mission_id)
                        entry['briefings'].append(mission_id)
                        menu.screen = 'campaign'; menu.buttons = buttons
                    next_button = next((b for b in menu.buttons if b['action'] == 'campaign_page' and b['payload'] == 1), None)
                    if next_button is None: break
                    click(menu, next_button['rect'].center)
                expected = {m['id'] for m in menu.campaign['missions']}
                assert union == expected and len(union) == 11
                assert set(entry['briefings']) == expected and len(entry['briefings']) == 11
                entry['catalogue_ids'] = sorted(union)
                menu.selected_mission = 0; menu.screen = 'briefing'
                menu_frame('tutorial_briefing')
                launch = next(b for b in menu.buttons if b['action'] == 'launch_mission')
                click(menu, launch['rect'].center)
                assert menu.result == menus.MenuResult.START_MISSION
                definition = menu.result_payload
                DataStore.reset(); ds = DataStore.get()
                gm = GameManager.start_mission(ds.maps[definition['map']], definition)
                gm.step(1/30)
                st = gm.state
                transport = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_crew_transport')
                cruiser = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_cruiser')
                target = next(e for e in gm.player_entities(1) if e.data_id == 'syndicate_corvette')
                frigate = next(e for e in gm.player_entities(0) if e.data_id == 'imperial_frigate')
                camera = Camera(width, height)
                camera.target = [-9500, 0, 0]; camera.distance = 7800; camera.pitch = 65; camera.yaw = 0
                hud = MeasuredHUD(width, height, st)
                hud.overlay = RecordingSurface((width, height), pygame.SRCALPHA)
                hud.overlay.recording = False
                flashes = []
                control = InputController(st, camera, hud, SimpleNamespace(flash=flashes.append))
                renderer = Renderer(st, camera)
                renderer.diff_render = True
                try:
                    def frame(name, selection, stress=None):
                        control.selection = set(selection)
                        hud.mission_name = definition['name']
                        hud.mission_progress = gm.mission.progress_text()
                        hud.mission_done = gm.mission.completed
                        hud.mission_failed = gm.mission.failed
                        if stress is not None:
                            hud.mission_name = 'Recovery drill with an unusually long mission title'
                            hud.mission_progress = ['[x] ' + 'LongUnbrokenModObjective' * 3,
                                '[ ] Restore personnel to the abandoned frigate (0/10)']
                            hud.mission_done, hud.mission_failed = stress
                        before = st.to_dict(precise=True)
                        renderer.draw(0, control.selection)
                        hud.render(control.selection, None, 0, False)
                        hud.draw_gl()
                        assert st.to_dict(precise=True) == before
                        entry['mission_frames'][name] = hud.mission_measurement
                        capture(name)

                    for tag, flags in (('active', (False, False)), ('complete', (True, False)), ('failed', (False, True))):
                        frame('long_token_' + tag, {cruiser.id}, stress=flags)
                    frame('tutorial_objectives_board_controls', {cruiser.id})
                    assert len(hud.mission_progress) == 1 and 'capture' in hud.mission_progress[0].lower()
                    button = next(b for b in hud.buttons if b['kind'] == 'board')
                    click(control, button['rect'].center)
                    assert control._pending_ability['ability_id'] == '_board'
                    frame('board_target_prompt', {cruiser.id})
                    point = camera.world_to_screen(target.pos.x, target.pos.y, target.pos.z)
                    assert point and not any(r.collidepoint(point) for r in hud.blocked_rects)
                    click(control, point)
                    assert not any(c.player == 0 for c in st.command_queue)
                    assert 'choose a detected enemy' in flashes, flashes
                    assert not st.can_see(0, target.id), 'hidden-target rejection control is vacuous'
                    deliver(control, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                    frame('crew_load_controls', {transport.id})
                    button = next(b for b in hud.buttons if b['kind'] == 'crew_load')
                    click(control, button['rect'].center)
                    assert st.command_queue[-1].type == 'crew_load'
                    for _ in range(120): gm.step(1/30)
                    assert transport.crew_cargo > 0
                    passengers_loaded = transport.crew_cargo
                    frame('crew_loaded_controls', {transport.id})
                    button = next(b for b in hud.buttons if b['kind'] == 'crew_deliver')
                    click(control, button['rect'].center)
                    assert control._pending_ability['ability_id'] == '_crew_deliver'
                    frame('crew_target_prompt', {transport.id})
                    point = camera.world_to_screen(frigate.pos.x, frigate.pos.y, frigate.pos.z)
                    assert point and not any(r.collidepoint(point) for r in hud.blocked_rects)
                    click(control, point)
                    assert st.command_queue[-1].type == 'crew_deliver'
                    assert st.command_queue[-1].target_id == frigate.id
                    initial = transport.pos.copy()
                    for _ in range(180): gm.step(1/30)
                    assert transport.pos.dist(initial) > 10, 'delivery order did not navigate'
                    frame('crew_delivery_navigation', {transport.id})
                    movement = transport.pos.dist(initial)
                    # Controlled fixture starts here: bounded production-order
                    # acceptance, explicitly NOT natural human navigation/balance.
                    cruiser.pos = Vec3(target.pos.x, 0, target.pos.z - 200)
                    cruiser.systems['weapons'].hp = 0
                    gm.visibility.update()
                    assert st.can_see(0, target.id)
                    camera.target = [target.pos.x, target.pos.y, target.pos.z]
                    camera.distance = 6500
                    frame('controlled_detected_board_target', {cruiser.id})
                    click(control, next(b for b in hud.buttons if b['kind'] == 'board')['rect'].center)
                    frame('controlled_detected_board_prompt', {cruiser.id})
                    point = camera.world_to_screen(target.pos.x, target.pos.y, target.pos.z)
                    assert point and not any(r.collidepoint(point) for r in hud.blocked_rects)
                    click(control, point)
                    command = st.command_queue[-1]
                    assert command.type == 'board' and command.target_id == target.id
                    assert command.unit_ids == (cruiser.id,)
                    events = []
                    for event_type in ('boarding_launched', 'unit_captured', 'crew_delivered'):
                        st.events.subscribe(event_type, lambda ev: events.append(dict(type=ev.type, data=ev.data)))

                    def precise(state):
                        return json.loads(json.dumps(state.to_dict(precise=True)))

                    entry['precise_restore_continuation_match'] = True
                    entry['restore_divergence'] = []
                    entry['restore_stages'] = {}
                    def continuation(stage, ticks):
                        restored = GameManager(GameState.from_dict(precise(st)))
                        assert precise(st) == precise(restored.state)
                        stage_matches = True
                        for _ in range(ticks):
                            gm.step(1/30); restored.step(1/30)
                            actual, replayed = precise(st), precise(restored.state)
                            if actual != replayed:
                                def differences(a, b, path=''):
                                    if isinstance(a, dict) and isinstance(b, dict):
                                        return [d for k in a.keys() | b.keys() for d in differences(a.get(k), b.get(k), path + '/' + str(k))]
                                    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                                        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, path + '/' + str(i))]
                                    return [] if a == b else [(path, a, b)]
                                if entry['precise_restore_continuation_match']:
                                    delta = differences(actual, replayed)
                                    entry['restore_divergence'] = dict(tick=st.tick, differences=delta)
                                    (args.out / f'{width}_restore_divergence.json').write_text(json.dumps(entry['restore_divergence'], indent=2))
                                entry['precise_restore_continuation_match'] = False
                                stage_matches = False
                        entry['restore_stages'][stage] = dict(ticks=ticks, exact_match=stage_matches)

                    gm.step(1/30)
                    assert cruiser.boarding_party_id is not None, 'board command was not accepted'
                    frame('controlled_boarding_craft', {cruiser.id})
                    continuation('capture', 240)
                    assert target.owner == 0 and gm.mission.objectives[0]['done']
                    recovery = next(o for o in gm.mission.objectives if o['id'] == 'recover')
                    assert recovery['active'] and not recovery['done']
                    frame('controlled_capture_recovery_stage', {target.id})
                    transport.pos = Vec3(frigate.pos.x, 0, frigate.pos.z + 100)
                    gm.visibility.update()
                    camera.target = [frigate.pos.x, frigate.pos.y, frigate.pos.z]
                    frame('controlled_crew_delivery_controls', {transport.id})
                    click(control, next(b for b in hud.buttons if b['kind'] == 'crew_deliver')['rect'].center)
                    frame('controlled_crew_delivery_prompt', {transport.id})
                    point = camera.world_to_screen(frigate.pos.x, frigate.pos.y, frigate.pos.z)
                    assert point and not any(r.collidepoint(point) for r in hud.blocked_rects)
                    click(control, point)
                    assert st.command_queue[-1].type == 'crew_deliver'
                    assert st.command_queue[-1].target_id == frigate.id
                    continuation('delivery', 90)
                    assert gm.mission.completed and recovery['done'] and frigate.crew >= 4
                    assert {'boarding_launched', 'unit_captured', 'crew_delivered'} <= {e['type'] for e in events}
                    frame('controlled_tutorial_completed', {frigate.id})
                    entry.update(gl_error=0, passengers_loaded=passengers_loaded,
                                 delivery_movement=movement, board_hidden_target_rejected=True,
                                 board_detected_target_command=True, real_capture=target.owner == 0,
                                 recovered_crew=frigate.crew, objective_events=events,
                                 precise_restore_continuation_ticks=330,
                                 mission_completed=gm.mission.completed,
                                 objective_text_overflow_px=max(m['text_overflow_px'] for m in entry['mission_frames'].values()),
                                 objective_card_overlaps_controls=any(m['card_control_overlap'] for m in entry['mission_frames'].values()),
                                 limits='Natural initial crew loading/delivery navigation and hidden-target rejection. Controlled detected-target fixture repositions cruiser near target, disables cruiser weapons, then repositions loaded transport near frigate. Real SDL clicks, authoritative boarding craft/capture and crew delivery; no timer jumps or synthetic events. Not a naturally navigated human playthrough or combat-balance/platform acceptance.')
                finally:
                    renderer.close(); hud.close(); menu.close()
                Path(menus.CAMPAIGN_PATH).unlink(missing_ok=True)
            (args.out / 'report.json').write_text(json.dumps(report, indent=2))
            print('DIAG_CAMPAIGN_PHASE7_UI_AND_CONTROLLED_CONTINUATION_OK', json.dumps(report, indent=2))
            if not all(r['precise_restore_continuation_match'] for r in report):
                print('DIAG_CAMPAIGN_PHASE7_EXTENDED_RESTORE_PARTIAL: see resolution restore_divergence artifacts; not a HUD/capture gate success claim')
        finally:
            pygame.quit()


if __name__ == '__main__':
    main()
