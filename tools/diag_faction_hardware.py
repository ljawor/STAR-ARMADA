"""Production SDL/GL catalogue coverage and locked Imperial pixel regression.

PYTHONPATH=. SDL_AUDIODRIVER=dummy .venv/bin/python tools/diag_faction_hardware.py --out DIR
Uses real factory subjects, all catalogue ships, all four x ten stations and
four data-less convoys. No simulation writes occur during frame capture.
Tiles are individually framed; these contact sheets are not scale comparisons.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pygame
from PIL import Image, ImageDraw, ImageFont
from OpenGL import GL
from game.core.entity import Entity
from game.core.manager import GameManager
from game.core.state import PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from render.camera import Camera
from render.fleet_geometry import ship_mesh, station_mesh
from render.renderer import Renderer
from render.ship_sizes import ship_size

FACTIONS = ('imperial', 'rebel', 'confederacy', 'syndicate')
NAMES = ('Galactic Imperium', 'Free Systems Alliance', 'Automated Legions', 'Outer Rim Syndicate')
BASELINE = '56e09ea'
W, H = 600, 420
SKIP = {'starfield', 'star', 'planets', 'nebulas', 'jumppoints', 'rings',
        'sites', 'effects', 'projectiles', 'shields', 'markers'}


def committed_module(path, name):
    source = subprocess.check_output(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT, text=True)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / path)
    sys.modules[name] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def font(size):
    for candidate in ('/System/Library/Fonts/Supplemental/Arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default()


def sheet(columns, rows, title, subtitle, tiles, out):
    header, row_h = 116, 340
    board = Image.new('RGB', (W * len(columns), header + row_h * len(rows) + 36), (8, 13, 23))
    draw = ImageDraw.Draw(board)
    draw.text((20, 12), title, font=font(26), fill=(235, 242, 255))
    draw.text((20, 48), subtitle, font=font(16), fill=(155, 184, 218))
    for col, heading in enumerate(columns):
        draw.text((col * W + 16, 84), heading, font=font(21), fill=(210, 230, 255))
    for row, label in enumerate(rows):
        for col in range(len(columns)):
            x, y = col * W, header + row * row_h
            draw.rectangle((x + 8, y + 5, x + W - 8, y + row_h - 5), outline=(40, 53, 73))
            draw.text((x + 20, y + 12), label, font=font(19), fill=(215, 230, 245))
            tile = tiles.get((col, row))
            if tile is None:
                draw.text((x + 20, y + 100), 'Not in current faction catalogue', font=font(17), fill=(115, 132, 156))
            else:
                # Crop only empty capture margins for readable contact sheets.
                # Raw per-subject PNGs remain untouched measurements; every
                # cell uses a square crop with a 15% margin and equal layout.
                yy, xx = np.where(tile.max(axis=2) > 35)
                cx, cy = (xx.min()+xx.max())/2., (yy.min()+yy.max())/2.
                extent = max(xx.max()-xx.min()+1, yy.max()-yy.min()+1) * 1.3
                subject = Image.fromarray(tile).crop((round(cx-extent/2), round(cy-extent/2),
                                                      round(cx+extent/2), round(cy+extent/2)))
                subject = subject.resize((280, 280), Image.Resampling.LANCZOS)
                board.paste(subject, (x + (W-subject.width)//2, y + 42))
    draw.text((20, board.height - 28), 'Actual game renderer | same ownership blue | individual framing, not a scale comparison', font=font(16), fill=(145, 162, 187))
    board.save(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.display.set_mode((W, H), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.event.pump()
    GL.glViewport(0, 0, W, H)
    GL.glClearColor(0., 0., 0., 1.)
    DataStore.reset()
    ds = DataStore.get()
    game = GameManager.start_skirmish(ds.maps['skirmish01'])
    st = game.state
    ds = DataStore.get()
    st.entities.clear()
    st.players = {i: PlayerState(i, faction=f, color=(.35, .55, 1.)) for i, f in enumerate(FACTIONS)}
    cam = Camera(W, H)
    cam.target, cam.pitch, cam.yaw = [0., 0., 0.], 53., 27.
    current = Renderer(st, cam)
    current.skip, current.diff_render, current.time = set(SKIP), True, 0.
    old_geometry = committed_module('render/fleet_geometry.py', 'render._faction_control_geometry')
    old_module = committed_module('render/renderer.py', 'render._faction_control_renderer')
    old_module.ship_mesh, old_module.station_mesh = old_geometry.ship_mesh, old_geometry.station_mesh
    control = old_module.Renderer(st, cam)
    control.skip, control.diff_render, control.time = set(SKIP), True, 0.
    # Both renderers bind the same live camera; its geometry is unchanged for
    # locked Imperial subjects. Rendering is read-only for either implementation.
    metrics = {'baseline': BASELINE, 'gl': GL.glGetString(GL.GL_RENDERER).decode(),
               'ships': [], 'stations': [], 'convoys': [], 'imperial_pixel_controls': [],
               'owner_paint_controls': [], 'changed_pixel_controls': [],
               'placement_previews': [], 'construction_sites': [], 'close_camera': []}
    ship_tiles, station_tiles = {}, {}
    rows = ['fighter', 'bomber', 'corvette', 'frigate', 'cruiser', 'battleship', 'supercapital', 'constructor', 'colonizer']
    def frame(renderer, e, shields=False, sites=False):
        renderer.local_player = e.owner
        # The control shares this camera: bind BOTH viewer and animation getter
        # to the renderer being captured, not whichever was constructed last.
        cam.bind_scene(st, lambda: renderer.local_player,
                       lambda: math.radians(renderer.time*3.))
        renderer.skip = set(SKIP)
        if sites:
            renderer.skip.discard('sites')
            renderer.skip.add('ships')
        if shields:
            renderer.skip.discard('shields')
        before = json.dumps(st.to_dict(precise=True), sort_keys=True)
        GL.glUseProgram(0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glDisable(GL.GL_BLEND)
        GL.glDepthMask(True)
        renderer.draw(0., set())
        GL.glFinish()
        pixels = np.flipud(np.frombuffer(GL.glReadPixels(0, 0, W, H, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8).reshape(H, W, 3)).copy()
        assert GL.glGetError() == 0, f'GL error: {e.data_id}'
        assert before == json.dumps(st.to_dict(precise=True), sort_keys=True), f'render mutated state: {e.data_id}'
        return pixels
    def setup(did, owner, station=False):
        st.entities.clear()
        e = (game.factory.spawn_station(did, owner, Vec3()) if station else
             game.factory.spawn_ship(did, owner, Vec3()))
        e.sensor_range = 100000.
        if station:
            mesh = station_mesh(did, FACTIONS[owner])
            radius = max(math.sqrt(sum(v*v for v in p)) for role in mesh.values() for _, tri in role for p in tri) * e.radius / 50.
        else:
            radius = ship_size(ds, did).radius
        cam.distance = max(230., radius * 5.2)
        return e
    def coverage(a, did, faction):
        mask = a.max(axis=2) > 35
        yy, xx = np.where(mask)
        assert len(xx) > 350, (did, faction, 'empty subject', len(xx))
        assert xx.min() > 5 and xx.max() < W-6 and yy.min() > 5 and yy.max() < H-6, (did, faction, 'clipped subject')
        return {'data_id': did, 'faction': faction, 'pixels': int(len(xx)), 'gl_error': 0}
    def imperial_control(e, new):
        old = frame(control, e)
        delta = int(np.count_nonzero(np.any(old != new, axis=2)))
        assert delta == 0, ('Imperial pixel regression', e.data_id, delta)
        metrics['imperial_pixel_controls'].append({'data_id': e.data_id, 'changed_pixels': delta})
    try:
        # Mesh control is independent of live wrapper dispatch/materials.
        for shape in ('wedge', 'needle', 'cruiser', 'dagger', 'box'):
            assert dict(ship_mesh(shape)) == dict(old_geometry.ship_mesh(shape)), shape
        for did in ds.stations:
            assert dict(station_mesh(did)) == dict(old_geometry.station_mesh(did)), did
        for did, data in ds.ships.items():
            faction = data.faction
            assert faction in FACTIONS, (did, faction)
            owner = FACTIONS.index(faction)
            e = setup(did, owner)
            a = frame(current, e)
            # Prime and re-render: no hidden clock/cache changes allowed.
            assert np.array_equal(a, frame(current, e)), f'unstable frame: {did}'
            metrics['ships'].append(coverage(a, did, faction))
            Image.fromarray(a).save(args.out / f'{did}.png')
            if faction == 'imperial':
                imperial_control(e, a)
            if 'squadron' in did:
                row = 'bomber' if ('bomber' in did or '_y_' in did) else 'fighter'
            else:
                row = did.rsplit('_', 1)[-1]
            assert row in rows, (did, row)
            ship_tiles[(owner, rows.index(row))] = a
        for owner, faction in enumerate(FACTIONS):
            for row, did in enumerate(ds.stations):
                e = setup(did, owner, True)
                a = frame(current, e)
                metrics['stations'].append(coverage(a, did, faction))
                Image.fromarray(a).save(args.out / f'{faction}_{did}.png')
                station_tiles[(owner, row)] = a
                if owner == 0:
                    imperial_control(e, a)
                elif did in ('command_station', 'shipyard'):
                    before = frame(control, e)
                    delta = int(np.count_nonzero(np.any(before != a, axis=2)))
                    assert delta > 500, (faction, did, 'unchanged station')
                    metrics['changed_pixel_controls'].append({'faction': faction, 'data_id': did, 'changed_pixels': delta})
            # Convoys are deliberately absent from the ship data store.
            st.entities.clear()
            e = Entity(id=900000 + owner, kind='ship', data_id='trade_convoy', owner=owner,
                       is_ship=True, sensor_range=100000., pos=Vec3())
            st.entities[e.id] = e
            cam.distance = 700.
            a = frame(current, e)
            metrics['convoys'].append(coverage(a, e.data_id, faction))
            Image.fromarray(a).save(args.out / f'{faction}_convoy.png')
            # Ownership is paint, not a different mesh. Keep faction/camera fixed.
            did = next(k for k, data in ds.ships.items() if data.faction == faction and k.endswith('_cruiser'))
            e = setup(did, owner)
            blue = frame(current, e)
            st.players[owner].color = (1., .30, .15)
            orange = frame(current, e)
            st.players[owner].color = (.35, .55, 1.)
            delta = int(np.count_nonzero(np.any(blue != orange, axis=2)))
            assert delta > 100, (faction, 'ownership color has no effect')
            metrics['owner_paint_controls'].append({'faction': faction, 'changed_pixels': delta})
            Image.fromarray(np.concatenate((blue, orange), axis=1)).save(args.out / f'{faction}_owner_colors.png')
            # Real shields must cover the mesh without changing authoritative radius.
            a = frame(current, e, shields=True)
            assert np.count_nonzero(np.any(a != blue, axis=2)) > 100, (faction, 'missing shield')
            Image.fromarray(a).save(args.out / f'{faction}_cruiser_shield.png')
        # Every race/type preview uses the real production path, not a mocked
        # mesh emitter. Construction sites are independently captured too.
        for owner, faction in enumerate(FACTIONS):
            constructor = next(k for k, data in ds.ships.items()
                               if data.faction == faction and k.endswith('_constructor'))
            for did in ds.stations:
                st.entities.clear()
                builder = game.factory.spawn_ship(constructor, owner, Vec3(-2000., 0., -2000.))
                builder.sensor_range = 100000.
                mesh = station_mesh(did, faction)
                radius = max(math.sqrt(sum(v*v for v in p)) for role in mesh.values()
                             for _, tri in role for p in tri) * ds.stations[did].radius / 50.
                cam.distance = max(230., radius*5.2)
                current.placement = {'builder_id': builder.id, 'station_kind': did,
                                     'ghost': {'world': (0.,0.,0.), 'valid': True}}
                preview = frame(current, builder, sites=True)
                record = coverage(preview, did, faction)
                current.placement['ghost']['valid'] = False
                invalid = frame(current, builder, sites=True)
                record['invalid_pixels'] = coverage(invalid, did, faction)['pixels']
                record['valid_invalid_changed_pixels'] = int(np.count_nonzero(np.any(preview != invalid, axis=2)))
                assert record['valid_invalid_changed_pixels'] > 100, 'invalid ghost did not turn red'
                metrics['placement_previews'].append(record)
                assert np.all(GL.glGetIntegerv(GL.GL_POLYGON_MODE) == GL.GL_FILL), 'preview leaked polygon mode'
                assert bool(GL.glGetBooleanv(GL.GL_DEPTH_WRITEMASK)), 'preview leaked depth mask'
                # Enter outline drawing with deliberately nondefault GL state:
                # restores must preserve caller state, not just reset to defaults.
                flags = (GL.GL_ENABLE_BIT | GL.GL_LIGHTING_BIT | GL.GL_CURRENT_BIT |
                         GL.GL_DEPTH_BUFFER_BIT | GL.GL_COLOR_BUFFER_BIT |
                         GL.GL_POLYGON_BIT | GL.GL_LINE_BIT | GL.GL_TEXTURE_BIT)
                GL.glPushAttrib(flags)
                try:
                    GL.glEnable(GL.GL_BLEND)
                    GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)
                    GL.glDepthMask(False)
                    GL.glLineWidth(2.)
                    GL.glEnable(GL.GL_CULL_FACE)
                    GL.glColor4f(.11, .22, .33, .44)
                    def gl_state():
                        return tuple(tuple(np.asarray(GL.glGetIntegerv(key)).reshape(-1)) for key in
                                     (GL.GL_POLYGON_MODE, GL.GL_BLEND_SRC, GL.GL_BLEND_DST)) + (
                            tuple(GL.glGetFloatv(GL.GL_CURRENT_COLOR)), float(GL.glGetFloatv(GL.GL_LINE_WIDTH)),
                            bool(GL.glGetBooleanv(GL.GL_DEPTH_WRITEMASK)),
                            tuple(bool(GL.glIsEnabled(key)) for key in (GL.GL_BLEND,GL.GL_LIGHTING,GL.GL_TEXTURE_2D,GL.GL_CULL_FACE)))
                    entry = gl_state()
                    current._draw_station_outline(did, faction, (0.,0.,0.), ds.stations[did].radius, (.3,.9,.55))
                    assert gl_state() == entry, (faction, did, 'outline leaked caller GL state')
                    assert GL.glGetError() == 0
                finally:
                    GL.glPopAttrib()
                record['caller_gl_state_restored'] = True
                Image.fromarray(invalid).save(args.out / f'{faction}_{did}_invalid_preview.png')
                Image.fromarray(preview).save(args.out / f'{faction}_{did}_preview.png')
                current.placement = None
                builder.build_queue = [{'kind':'station', 'item':did, 'pos':[0.,0.,0.],
                                        'time_left':5., 'total':10.}]
                site = frame(current, builder, sites=True)
                record = coverage(site, did, faction)
                if faction != 'imperial':
                    from unittest.mock import patch
                    with patch.object(current, '_draw_station_outline', return_value=None) as disabled:
                        scaffold = frame(current, builder, sites=True)
                        disabled.assert_called_once()
                        assert disabled.call_args.args[:2] == (did, faction)
                    changed = int(np.count_nonzero(np.any(site != scaffold, axis=2)))
                    assert changed > 100, (faction, did, 'missing faction construction hardware')
                    record['outline_changed_pixels'] = changed
                metrics['construction_sites'].append(record)
                builder.build_queue = []
                empty = frame(current, builder, sites=True)
                assert np.count_nonzero(empty.max(axis=2)>35) == 0, 'site remains after queue cleared'
                Image.fromarray(site).save(args.out / f'{faction}_{did}_site.png')
            # New stations must protect very close cameras at low pitch using
            # exactly the same all-role bounds as the actual draw.
            e = setup('shipyard', owner, True)
            cam.distance, cam.pitch = 25., 8.
            frame(current, e)
            from render.camera_geometry import box_interval, readable_intervals, camera_ray
            from render.camera_geometry import station_bounds
            lo, hi = station_bounds(e.data_id, faction)
            expected_box = ((e.pos.x, e.pos.y, e.pos.z), math.radians(current.time*3.),
                            tuple(v*(e.radius/50.) for v in lo), tuple(v*(e.radius/50.) for v in hi))
            assert expected_box in cam._camera_boxes, (faction, 'expected station obstacle missing')
            assert len(cam._camera_boxes) == 1, (faction, 'unexpected close-camera fixture')
            eye = cam.eye_position()
            distance = math.dist(cam.target, eye)
            assert distance > math.dist(cam.target, cam._requested_eye()) + 1., (faction, 'keep-out inactive')
            requested = cam._requested_eye() if hasattr(cam, '_requested_eye') else eye
            ray = camera_ray(cam.target, requested, cam.near, cam.fov, W/H, H)
            assert ray is not None
            _, direction, clearance, slope, cap = ray
            # Recompute direction from effective eye: same radial camera ray.
            direction = tuple((eye[i]-cam.target[i])/distance for i in range(3))
            for box in cam._camera_boxes:
                intervals = readable_intervals(cam.target, direction, box, clearance, slope, cap) if len(box)==5 else [box_interval(cam.target,direction,box,clearance)]
                assert all(interval is None or not interval[0]<=distance<=interval[1] for interval in intervals), (faction,'unsafe close eye')
            metrics['close_camera'].append({'faction':faction, 'requested_distance':25., 'effective_distance':distance})
            cam.pitch = 53.
        assert len(metrics['placement_previews']) == 40
        assert len(metrics['construction_sites']) == 40
        assert len(metrics['ships']) == len(ds.ships)
        assert len(metrics['stations']) == len(FACTIONS) * len(ds.stations)
        assert len(metrics['convoys']) == 4
        sheet(NAMES, [s.upper() for s in rows], 'STAR ARMADA — faction ships', 'Implemented catalogue / Imperial geometry preserved', ship_tiles, args.out / 'all_ships.png')
        sheet(NAMES, [s.replace('_', ' ').upper() for s in ds.stations], 'STAR ARMADA — faction stations', 'All ten station types for every faction / Imperial geometry preserved', station_tiles, args.out / 'all_stations.png')
        metrics['total_subjects'] = len(metrics['ships']) + len(metrics['stations']) + len(metrics['convoys'])
        (args.out / 'verification.json').write_text(json.dumps(metrics, indent=2))
        print('DIAG_OK', json.dumps({k: len(metrics[k]) for k in ('ships', 'stations', 'convoys', 'imperial_pixel_controls', 'owner_paint_controls', 'changed_pixel_controls')}))
    finally:
        current.close()
        control.close()
        pygame.quit()


if __name__ == '__main__':
    main()
