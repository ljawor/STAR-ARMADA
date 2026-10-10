"""Actual Cocoa SDL/GL support controls, physical ticks and framebuffer evidence.
Run: PYTHONPATH=. .venv/bin/python tools/diag_support_orders.py --out DIR
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pygame
from OpenGL import GL
from PIL import Image
from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.repairs import missing_hp
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.renderer import Renderer


def deliver(control, event):
    pygame.event.clear()
    pygame.event.post(event)
    for item in pygame.event.get():
        control.handle_event(item)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    assert os.environ.get('SDL_VIDEODRIVER') != 'dummy', 'real display required'
    pygame.display.init(); pygame.font.init()
    report = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            pygame.event.pump()
            GL.glViewport(0, 0, width, height)
            driver = pygame.display.get_driver()
            assert driver != 'dummy'
            DataStore.reset()
            definition = dict(DataStore.get().maps['skirmish01'])
            definition['players'] = [dict(p, is_ai=False) for p in definition['players']]
            gm = GameManager.start_skirmish(definition)
            st, ds = gm.state, DataStore.get()
            st.entities.clear(); st.explored_cells.clear(); st.discovered_planets.clear()
            st.map_info.bounds = 6000
            builder = gm.factory.spawn_ship('imperial_constructor', 0, Vec3(-450, 0, 0))
            ship = gm.factory.spawn_ship('imperial_frigate', 0, Vec3(180, 0, 0))
            station = gm.factory.spawn_station('shipyard', 0, Vec3(650, 0, 450))
            scout = gm.factory.spawn_ship('imperial_tie_squadron', 0, Vec3(-600, 0, -900))
            enemy = gm.factory.spawn_ship('imperial_frigate', 1, Vec3(2900, 0, 2900))
            enemy.order_type = 'hold'
            ship.hull -= 100
            station.hull -= 100; station.crew = 0; station.systems['life_support'].hp = 0
            for item in ds.stations.values(): item.income = {}
            ds.rules['economy']['planet_income'] = {}
            p = st.players[0]
            p.credits = p.materials = p.crew = p.energy = 100000
            camera = Camera(width, height)
            camera.target = [0, 0, 0]; camera.distance = 4800; camera.pitch = 65; camera.yaw = 0
            hud = HUD(width, height, st)
            control = InputController(st, camera, hud, SimpleNamespace(flash=lambda *_: None))
            renderer = Renderer(st, camera)
            renderer.diff_render = True
            labels, bars = [], []
            original_label, original_bar = hud._label, hud._bar
            def label(x, y, text, color=None, font=None):
                labels.append((str(text), pygame.Rect(x, y, *(font or hud.font).size(str(text)))))
                original_label(x, y, text, color, font)
            def bar(x, y, w, h, *rest):
                bars.append(pygame.Rect(x, y, w, h))
                original_bar(x, y, w, h, *rest)
            hud._label, hud._bar = label, bar

            def capture(name, selection):
                control.selection = set(selection)
                labels.clear(); bars.clear()
                before = st.to_dict(precise=True)
                renderer.draw(0, control.selection)
                hud.render(control.selection, None, 0, False)
                hud.draw_gl(); GL.glFinish()
                raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
                assert GL.glGetError() == GL.GL_NO_ERROR
                assert before == st.to_dict(precise=True), 'render mutated simulation'
                panels = [r for r in hud.blocked_rects if r.y == 44 and r.width == 320]
                screen = pygame.Rect(0, 0, width, height)
                assert all(screen.contains(r) for r in panels)
                counts = {}
                for text, rect in labels:
                    if rect.y < 44: continue
                    panel = next((r for r in panels if r.x <= rect.x < r.right), None)
                    if panel is None: continue
                    assert panel.contains(rect), f'{name}: clipped text {text}: {rect}, {panel}'
                    assert not any(rect.colliderect(b) for b in bars), f'{name}: bar overlaps {text}'
                    band = pixels[rect.top:rect.bottom, rect.left:rect.right]
                    glyphs = int((band.max(axis=2) > 85).sum())
                    assert glyphs, f'{name}: missing GL glyph pixels for {text}'
                    counts[text] = glyphs
                for button in hud.buttons:
                    if button['kind'] == 'hud_scroll': continue
                    assert any(r.contains(button['rect']) for r in panels), f'clipped hitbox: {button}'
                    if button['kind'] in ('build_ship', 'build_station_place', 'build_satellite'):
                        payload = button['payload']
                        data = (ds.ships[payload['ship_id']] if button['kind'] == 'build_ship'
                                else ds.stations[payload['station_kind']])
                        assert any(f'{data.crew_cost:,.0f} crew' in text
                                   and button['rect'].contains(rect) for text, rect in labels), (
                                       name, 'missing exact crew label in row', data.id)
                for i, button in enumerate(hud.buttons):
                    assert not any(button['rect'].colliderect(b['rect']) for b in hud.buttons[i+1:]), 'overlapping hitboxes'
                path = args.out / f'{width}_{name}.png'
                Image.fromarray(pixels).save(path)
                report.append(dict(file=str(path), driver=driver, gl_error=0, labels=counts,
                                   panels=[list(r) for r in panels], buttons=len(hud.buttons)))
                pygame.display.flip(); pygame.event.pump()

            try:
                capture('constructor_controls', {builder.id})
                cancellations = []
                for name, event in (
                        ('escape', pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)),
                        ('right_click', pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(width//2, height//2))),
                        ('focus_loss', pygame.event.Event(pygame.WINDOWFOCUSLOST)),
                        ('stop', pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s))):
                    repair = next(b for b in hud.buttons if b['kind'] == 'repair')
                    before = st.to_dict(precise=True)
                    deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=repair['rect'].center))
                    assert control._pending_ability is not None
                    deliver(control, event)
                    assert control._pending_ability is None and not hud.ability_prompt
                    assert not control.dragging and control.right_drag is None
                    if name == 'stop':
                        assert [c.type for c in st.command_queue] == ['stop']
                        st.command_queue.clear()
                    assert before == st.to_dict(precise=True), f'{name}: cancellation mutated simulation'
                    control.keys.clear()
                    cancellations.append(name)
                capture('repair_cancelled', {builder.id})
                repair = next(b for b in hud.buttons if b['kind'] == 'repair')
                credits, materials = p.credits, p.materials
                deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=repair['rect'].center))
                assert control._pending_ability['ability_id'] == '_repair'
                # Real projected target picking, not a replaced/mocked picker.
                point = camera.world_to_screen(ship.pos.x, ship.pos.y, ship.pos.z)
                assert point is not None
                assert not any(r.collidepoint(point) for r in hud.blocked_rects)
                deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                cmd = PlayerCommand.from_dict(st.command_queue[-1].to_dict())
                assert cmd.type == 'repair' and cmd.target_id == ship.id and tuple(cmd.unit_ids) == (builder.id,)
                assert (p.credits, p.materials) == (credits, materials), 'UI spent resources'
                tick_start = st.tick
                missing = missing_hp(ship)
                gm.step(.5)
                for _ in range(180):
                    if missing_hp(ship) < missing: break
                    gm.step(1/30)
                gained = missing - missing_hp(ship)
                assert gained > 0, (builder.order_type, builder.pos, ship.pos)
                assert abs((credits - p.credits) - gained * .2) < 1e-6
                assert abs((materials - p.materials) - gained * .1) < 1e-6
                capture('paid_ship_repair_progress', {builder.id})
                # Abandoned station gets equipment only, with the same explicit UI.
                repair = next(b for b in hud.buttons if b['kind'] == 'repair')
                deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=repair['rect'].center))
                point = camera.world_to_screen(station.pos.x, station.pos.y, station.pos.z)
                deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                assert st.command_queue[-1].target_id == station.id
                # Approach is physical; do not teleport source into service range.
                support_before = station.systems['life_support'].hp
                for _ in range(360): gm.step(1/30)
                assert station.systems['life_support'].hp > support_before
                assert station.crew == 0
                capture('abandoned_station_repair', {builder.id})
                capture('fighter_controls', {scout.id})
                explore = next(b for b in hud.buttons if b['kind'] == 'explore')
                before = st.to_dict(precise=True)
                deliver(control, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=explore['rect'].center))
                assert st.command_queue[-1].type == 'explore'
                assert tuple(st.command_queue[-1].unit_ids) == (scout.id,)
                assert scout.order_type != 'explore'
                after = st.to_dict(precise=True)
                before['command_queue'] = after['command_queue']
                assert before == after, 'UI performed survey simulation'
                cells_before = len(st.explored_cells.get(0, set()))
                start = scout.pos.copy()
                for _ in range(300): gm.step(1/30)
                assert scout.order_type == 'explore'
                assert scout.pos.dist(start) > 10
                assert len(st.explored_cells.get(0, set())) > cells_before
                assert scout.current_target is None
                obstacles = list(gm.exploration._obstacles(scout))
                if scout.order_target_pos is not None:
                    assert gm.exploration._route_safe(scout.pos, scout.order_target_pos, obstacles)
                capture('physical_exploration_progress', {scout.id})
                previous = scout.order_target_pos.copy()
                threat_pos = scout.pos + (previous - scout.pos).normalized() * 200
                threat = gm.factory.spawn_station('sensor_station', 1, threat_pos)
                assert st.can_see(0, threat.id), 'avoidance fixture must be detected'
                obstacles = list(gm.exploration._obstacles(scout))
                assert any(pos.dist(threat.pos) < 1e-6 for pos, _ in obstacles)
                assert not gm.exploration._route_safe(scout.pos, previous, obstacles), 'threat must invalidate the old route'
                fired = []
                st.events.subscribe('weapon_fired', lambda event: fired.append(event.data))
                gm.step(1/30)
                assert scout.current_target is None
                assert scout.order_target_pos is None or gm.exploration._route_safe(
                    scout.pos, scout.order_target_pos, list(gm.exploration._obstacles(scout)))
                assert not any(event.get('attacker_id') == scout.id for event in fired)
                capture('detected_enemy_avoidance', {scout.id})
                capture('boarding_help', {ship.id})
                dock = gm.factory.spawn_station('repair_dock', 0, Vec3(-700, 0, 500))
                capture('dock_help', {dock.id})
                capture('mixed_support', {builder.id, scout.id, ship.id})
                # S stops the physical survey too, not merely its target prompt.
                capture('exploration_before_stop', {scout.id})
                deliver(control, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s))
                assert st.command_queue[-1].type == 'stop'
                gm.step(1/30)
                assert scout.order_type != 'explore'
                control.keys.clear()
                capture('exploration_stopped', {scout.id})
                # Real production panels for EVERY registered faction, including
                # command-center engineering hulls and fighter platforms omitted
                # by a single Imperial shipyard-only probe.
                crew_coverage = {'ships': set(), 'stations': set()}
                faction_coverage = {}
                production_scroll_events = 0
                original_faction = p.faction
                for faction in ds.factions:
                    p.faction = faction
                    sources = [(gm.factory.spawn_ship(d.id, 0, Vec3()), 'stations')
                               for d in ds.ships.values() if d.faction == faction and d.can_build_stations]
                    sources += [(gm.factory.spawn_station(d.id, 0, Vec3()), 'ships')
                                for d in ds.stations.values() if d.builds_ships]
                    faction_seen = set()
                    for unit, key in sources:
                        items = ([ds.stations[s] for s in ds.ships[unit.data_id].can_build_stations]
                                 if key == 'stations' else hud._shipyard_items(unit, ds.stations[unit.data_id]))
                        seen = set()
                        hud.scroll[key] = 0
                        for offset in range(len(items)):
                            capture(f'{faction}_{unit.data_id}_{key}_page_{offset}', {unit.id})
                            seen.update(b['payload'].get('station_kind', b['payload'].get('ship_id'))
                                        for b in hud.buttons if b['kind'] in ('build_ship', 'build_station_place'))
                            region = next(rect for rect, region_key in hud.scroll_rects if region_key == key)
                            pygame.mouse.set_pos(region.center)
                            pygame.event.pump()
                            assert region.collidepoint(pygame.mouse.get_pos()), 'real SDL pointer must be over production list'
                            previous_offset, distance = hud.scroll[key], camera.distance
                            deliver(control, pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
                            assert hud.scroll[key] == previous_offset + 1
                            assert camera.distance == distance, 'production wheel changed camera zoom'
                            production_scroll_events += 1
                        assert seen == {d.id for d in items}, (faction, unit.data_id, seen, {d.id for d in items})
                        crew_coverage[key].update(seen)
                        if key == 'ships': faction_seen.update(seen)
                        # Keep added hardware from occluding later world captures.
                        st.entities.pop(unit.id)
                    faction_coverage[faction] = sorted(faction_seen)
                    assert faction_seen == {d.id for d in ds.ships.values() if d.faction == faction}
                p.faction = original_faction
                planet = gm.factory.spawn_planet(dict(id='diagnostic_colony', type='temperate', pos=[0,0,1800], radius=300))
                planet.colonized_by = 0
                capture('satellite_crew_costs', {planet.id})
                crew_coverage['stations'].update(b['payload']['station_kind'] for b in hud.buttons if b['kind'] == 'build_satellite')
                assert crew_coverage['ships'] == set(ds.ships)
                assert crew_coverage['stations'] == set(ds.stations)
                report.append(dict(resolution=[width,height], repaired_ship_hp=gained,
                    station_support_hp=station.systems['life_support'].hp, station_crew=station.crew,
                    exploration_new_cells=len(st.explored_cells.get(0,set()))-cells_before,
                    scout_distance=scout.pos.dist(start), ticks=st.tick-tick_start,
                    detected_enemy_avoidance=True, scout_weapon_launches=len([e for e in fired if e.get('attacker_id') == scout.id]),
                    cancellations=cancellations, exploration_stop=True,
                    production_scroll_events=production_scroll_events,
                    crew_label_coverage={key: sorted(value) for key,value in crew_coverage.items()},
                    factions=faction_coverage))
            finally:
                hud.close(); renderer.close()
        (args.out / 'metrics.json').write_text(json.dumps(report, indent=2))
        print(f'SUPPORT_ORDERS_DIAG_OK: {len(report)} evidence records; {args.out}')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
