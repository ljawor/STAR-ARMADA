"""Real-window fog regression: baseline subtraction including HUD/minimap.

Before the core visibility API lands, --fixture uses a strict local contract.
Normal execution requires the actual GameState sensor implementation.
"""
import os
import sys
import json
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pygame
import numpy as np
from OpenGL import GL
from game.data.store import DataStore
from game.core.manager import GameManager
from game.core.state import PlayerState
from game.core.vectors import Vec3
from game.core.world import Projectile
from game.systems.unit_factory import UnitFactory
from render.camera import Camera
from render.renderer import Renderer
from render.hud import HUD


def run():
    out = ROOT / 'saves' / 'fog_of_war'
    out.mkdir(parents=True, exist_ok=True)
    pygame.init()
    w, h = 1280, 800
    pygame.display.set_mode((w, h), pygame.OPENGL | pygame.DOUBLEBUF)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(30)
    DataStore.reset()
    ds = DataStore()
    gm = GameManager.start_skirmish(ds.maps['skirmish01'])
    st = gm.state
    st.entities.clear()
    st.projectiles.clear()
    st.effects.clear()
    st.map_info.nebulas = []
    st.map_info.jump_points = []
    st.map_info.star = {}
    factory = UnitFactory(st)
    st.players[0].team = 0
    st.players[2] = PlayerState(2, team=0, name='Sensor ally')
    scout = factory.spawn_ship('imperial_corvette', 2, Vec3(-6000, 0, 0))
    enemy = factory.spawn_ship('imperial_cruiser', 1, Vec3(0, 0, 0))
    enemy.vel = Vec3(0, 0, 150)
    station = factory.spawn_station('defense_platform', 1, Vec3(380, 0, 0))
    if '--fixture' in sys.argv:
        class Fixture:
            visibility_cell_size = 500
            local_player_id = 0
            explored_cells = {0: set()}
            def __getattr__(self, name):
                return getattr(st, name)
            def sensor_sources(self, pid):
                return [(scout, 2200)] if scout.alive else []
            def is_position_visible(self, pid, pos):
                x, z = (pos.x, pos.z) if hasattr(pos, 'x') else (pos[0], pos[2])
                return scout.alive and (x-scout.pos.x)**2 + (z-scout.pos.z)**2 <= 2200**2
            def is_position_explored(self, pid, pos):
                x, z = (pos.x, pos.z) if hasattr(pos, 'x') else (pos[0], pos[2])
                return (int(x//500), int(z//500)) in self.explored_cells[pid]
            def can_see(self, pid, eid):
                e = st.entity(eid)
                return e is not None and (e.owner in (0, 2) or self.is_position_visible(pid, e.pos))
            def known_entity(self, pid, eid):
                return st.entity(eid) if self.can_see(pid, eid) else None
        view = Fixture()
        def refresh():
            for x in range(-26, 26):
                for z in range(-26, 26):
                    if view.is_position_visible(0, (x*500+250, 0, z*500+250)):
                        view.explored_cells[0].add((x, z))
    else:
        view = st
        def refresh():
            gm.visibility.update(0)
    cam = Camera(w, h)
    cam.target = [0, 0, 0]
    cam.pitch = 65
    cam.distance = 6500
    renderer = Renderer(view, cam)
    renderer.diff_render = True
    hud = HUD(w, h, view)
    hud.set_camera_ref(cam)
    failures = []
    metrics = {}
    def frame(name, include=True, selection=None):
        selected = {enemy.id} if selection is None else selection
        # Identical entry GL state for every comparison, capture BEFORE flip.
        GL.glUseProgram(0)
        GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(True)
        GL.glClearColor(.02, .025, .04, 1)
        if not include:
            projectiles = dict(st.projectiles)
            st.projectiles.clear()
            st.entities.pop(enemy.id, None)
            st.entities.pop(station.id, None)
            fx = st.effects[:]
            st.effects.clear()
        cam.apply(w, h)
        renderer.draw(0, selected)
        GL.glFinish()
        world = np.frombuffer(GL.glReadPixels(0, 0, w, h, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(h, w, 3)[::-1].copy()
        pygame.image.save(pygame.image.frombuffer(world.tobytes(), (w, h), "RGB"), str(out / (name+"_world.png")))
        hud.render(selected, None, 0, False)
        hud.draw_gl()
        GL.glFinish()
        arr = np.frombuffer(GL.glReadPixels(0, 0, w, h, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(h, w, 3)[::-1].copy()
        pygame.image.save(pygame.image.frombuffer(arr.tobytes(), (w, h), 'RGB'), str(out / (name+'.png')))
        if not include:
            st.entities[enemy.id] = enemy
            st.entities[station.id] = station
            st.effects[:] = fx
            st.projectiles.update(projectiles)
        assert GL.glGetError() == GL.GL_NO_ERROR
        return arr
    for stage, x, alive in [('unknown', -6000, True), ('visible', -500, True),
                             ('explored', -6000, True), ('detector_destroyed', -500, False)]:
        scout.pos.x = x
        scout.alive = alive if "--fixture" in sys.argv else True
        scout.systems["sensors"].hp = scout.systems["sensors"].max_hp if alive else 0
        st.projectiles[900] = Projectile(900, 1, "laser_cannon", Vec3(100, 0, 50),
            Vec3(0, 0, 1), scout.id, 10, 1, 1, 1, 2)
        st.effects[:] = [{'kind': 'beam', 'pos': [0, 0, 0], 'target_pos': [380, 0, 0], 't': .03}]
        refresh()
        actual = frame(stage)
        baseline = frame(stage+'_baseline', False)
        diff = np.abs(actual.astype(int)-baseline.astype(int))
        changed = int((diff.max(axis=2)>2).sum())
        metrics[stage+'_changed_pixels'] = changed
        if stage == 'visible':
            if changed < 100: failures.append('visible contacts do not render')
        elif changed != 0:
            failures.append(f'{stage}: hidden contacts leaked {changed} pixels')
    if '--fixture' not in sys.argv:
        # Forgotten live ownership must not alter world OR minimap pixels.
        scout.systems['sensors'].hp = scout.systems['sensors'].max_hp
        scout.pos.x = -6000
        planet = factory.spawn_planet({'id': 'probe', 'type': 'temperate',
            'name': 'Unknown planet', 'pos': [1000, 0, 0], 'radius': 300})
        st.effects.clear()
        st.projectiles.clear()
        refresh()
        unknown = frame('unknown_planet')
        st.entities.pop(planet.id)
        control = frame('unknown_planet_baseline')
        st.entities[planet.id] = planet
        metrics['unknown_planet_changed_pixels'] = int((np.abs(unknown.astype(int)-control.astype(int)).max(axis=2)>2).sum())
        if metrics['unknown_planet_changed_pixels']:
            failures.append('unknown planet leaked')
        scout.pos.x = 500
        refresh()
        frame('discovered_planet')
        scout.pos.x = -6000
        refresh()
        charted = frame('charted_planet')
        planet.colonized_by = 1
        planet.owner = 1
        refresh()
        changed_owner = frame('hidden_ownership_change')
        metrics['hidden_ownership_changed_pixels'] = int((np.abs(charted.astype(int)-changed_owner.astype(int)).max(axis=2)>2).sum())
        if metrics['hidden_ownership_changed_pixels']:
            failures.append('forgotten live planet ownership leaked')
    cam.pitch = 89
    cam.distance = cam.zoom_limits[1]
    frame('overview')
    scout.pos.x = -500
    scout.systems['sensors'].hp = scout.systems['sensors'].max_hp
    refresh()
    frame('overview_visible')
    frame('sensor_readout', selection={scout.id})
    for _ in range(3): frame('warmup')
    GL.glFinish()
    t = time.perf_counter()
    for _ in range(12):
        renderer.draw(0, set())
    GL.glFinish()
    metrics['renderer_ms_per_frame'] = (time.perf_counter()-t)*1000/12
    t = time.perf_counter()
    for i in range(12):
        scout.pos.x += 1
        renderer.fog.surface(view, 0)
    metrics['dirty_mask_ms'] = (time.perf_counter()-t)*1000/12
    t = time.perf_counter()
    for i in range(100):
        renderer.fog.surface(view, 0)
    metrics['cached_mask_ms'] = (time.perf_counter()-t)*1000/100
    (out/'metrics.json').write_text(json.dumps({'metrics': metrics, 'failures': failures}, indent=2))
    print(json.dumps(metrics, indent=2))
    renderer.close()
    hud.close()
    pygame.quit()
    print('FOG_DIAG_FAIL' if failures else 'FOG_DIAG_OK', failures, str(out))
    return bool(failures)

if __name__ == '__main__':
    sys.exit(run())
