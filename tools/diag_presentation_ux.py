"""Real SDL/GL presentation acceptance; never substitutes dummy video.
Run: PYTHONPATH=. .venv/bin/python tools/diag_presentation_ux.py --out DIR
Controlled cargo/objective/visibility fixtures are not human drill completion.
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
from game.core.manager import GameManager
from game.data.store import DataStore
from render.camera import Camera
from render.hud import HUD
from render.input import InputController
from render.menus import MenuStack, DEFAULT_SETTINGS
from render.presentation import PresentationOverlay, HELP_PAGES
from render.renderer import Renderer


class RecordingSurface(pygame.Surface):
    """Record emitted glyph blits, including helpers not in metadata lists."""
    def __init__(self, size, flags=0):
        super().__init__(size, flags)
        self.glyph_rects = []

    def blit(self, source, dest, *args, **kwargs):
        actual = super().blit(source, dest, *args, **kwargs)
        if source.get_height() <= 48:
            # Use the *unclipped* glyph extent, not Surface.blit's clipped return.
            point = dest.topleft if isinstance(dest, pygame.Rect) else dest[:2]
            self.glyph_rects.append(source.get_rect(topleft=point))
        return actual


def deliver(target, event):
    pygame.event.clear()
    pygame.event.post(event)
    answers = [target.handle_event(e) for e in pygame.event.get() if e.type == event.type]
    assert answers
    return answers[-1]


def gl_state():
    integer = ('GL_MATRIX_MODE', 'GL_ACTIVE_TEXTURE', 'GL_CURRENT_PROGRAM',
               'GL_UNPACK_ALIGNMENT', 'GL_UNPACK_ROW_LENGTH', 'GL_UNPACK_SKIP_ROWS',
               'GL_UNPACK_SKIP_PIXELS', 'GL_BLEND_SRC_RGB', 'GL_BLEND_DST_RGB',
               'GL_BLEND_SRC_ALPHA', 'GL_BLEND_DST_ALPHA', 'GL_BLEND_EQUATION_RGB',
               'GL_BLEND_EQUATION_ALPHA', 'GL_DEPTH_WRITEMASK', 'GL_TEXTURE_BINDING_2D')
    floating = ('GL_MODELVIEW_MATRIX', 'GL_PROJECTION_MATRIX', 'GL_TEXTURE_MATRIX',
                'GL_CURRENT_COLOR', 'GL_CURRENT_TEXTURE_COORDS')
    enabled = ('GL_DEPTH_TEST', 'GL_BLEND', 'GL_LIGHTING', 'GL_CULL_FACE',
               'GL_TEXTURE_2D', 'GL_SCISSOR_TEST', 'GL_STENCIL_TEST', 'GL_FOG', 'GL_ALPHA_TEST')
    result = {name: np.asarray(GL.glGetIntegerv(getattr(GL, name))).tolist() for name in integer}
    result.update({name: np.asarray(GL.glGetFloatv(getattr(GL, name))).tolist() for name in floating})
    result.update({name: bool(GL.glIsEnabled(getattr(GL, name))) for name in enabled})
    active = int(GL.glGetIntegerv(GL.GL_ACTIVE_TEXTURE))
    GL.glActiveTexture(GL.GL_TEXTURE0)
    result['unit0_binding'] = int(GL.glGetIntegerv(GL.GL_TEXTURE_BINDING_2D))
    GL.glActiveTexture(active)
    return result


def pixels(width, height):
    GL.glFinish()
    raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
    return np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    assert os.environ.get('SDL_VIDEODRIVER') != 'dummy'
    pygame.display.init(); pygame.font.init()
    report = []
    try:
        for width, height in ((1024, 768), (1280, 800)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            pygame.event.pump(); GL.glViewport(0, 0, width, height)
            driver = pygame.display.get_driver()
            assert driver != 'dummy'
            ds = DataStore.get()
            definition = next(m for m in ds.campaign['missions'] if m['id'] == 'm00_recovery_drill')
            gm = GameManager.start_mission(ds.maps[definition['map']], definition)
            gm.step(1 / 30)
            st = gm.state
            camera = Camera(width, height)
            owned = [e for e in st.entities.values() if e.owner == 0 and e.alive]
            camera.target = [owned[0].pos.x, owned[0].pos.y, owned[0].pos.z]
            camera.distance = 6000; camera.pitch = 65
            hud = HUD(width, height, st)
            control = InputController(st, camera, hud, SimpleNamespace(flash=lambda *_: None))
            renderer = Renderer(st, camera)
            overlay = PresentationOverlay(width, height)
            overlay.surface = RecordingSurface((width, height), pygame.SRCALPHA)
            menu = MenuStack(width, height)
            menu._surface = RecordingSurface((width, height))
            sentinel = GL.glGenTextures(1)
            from OpenGL.GL.shaders import compileProgram, compileShader
            program = compileProgram(
                compileShader('#version 120\nvoid main(){gl_Position=gl_ModelViewProjectionMatrix*gl_Vertex;}', GL.GL_VERTEX_SHADER),
                compileShader('#version 120\nvoid main(){gl_FragColor=vec4(1.,0.,0.,1.);}', GL.GL_FRAGMENT_SHADER))
            try:
                # First upload must allocate lazily and preserve nondefault GL state.
                assert overlay.overlay_tex is None
                overlay.help_visible = True
                overlay.draw(None)
                GL.glBindTexture(GL.GL_TEXTURE_2D, sentinel)
                GL.glEnable(GL.GL_LIGHTING); GL.glEnable(GL.GL_CULL_FACE)
                GL.glEnable(GL.GL_DEPTH_TEST); GL.glDisable(GL.GL_BLEND)
                GL.glBlendFuncSeparate(GL.GL_ONE, GL.GL_ZERO, GL.GL_ZERO, GL.GL_ONE)
                GL.glBlendEquationSeparate(GL.GL_FUNC_REVERSE_SUBTRACT, GL.GL_FUNC_SUBTRACT)
                GL.glColor4f(.2, .3, .4, .5)
                GL.glMatrixMode(GL.GL_TEXTURE); GL.glLoadIdentity(); GL.glTranslatef(.1, .2, 0)
                GL.glMatrixMode(GL.GL_PROJECTION); GL.glLoadIdentity(); GL.glScalef(.7, .8, 1)
                GL.glActiveTexture(GL.GL_TEXTURE1)
                GL.glBindTexture(GL.GL_TEXTURE_2D, sentinel)
                GL.glEnable(GL.GL_TEXTURE_2D)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
                GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
                GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, 1, 1, 0, GL.GL_RGBA,
                                GL.GL_UNSIGNED_BYTE, bytes((192, 17, 33, 255)))
                GL.glClearColor(17 / 255, 29 / 255, 41 / 255, 1)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 8)
                GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, width + 8)
                GL.glPixelStorei(GL.GL_UNPACK_SKIP_ROWS, 2)
                GL.glPixelStorei(GL.GL_UNPACK_SKIP_PIXELS, 2)
                before = gl_state()
                GL.glUseProgram(program)
                before = gl_state()
                overlay.draw_gl()
                assert gl_state() == before, 'first GL upload leaks state'
                first_frame = pixels(width, height)
                rgba = np.frombuffer(pygame.image.tobytes(overlay.surface, 'RGBA'), np.uint8).reshape(height, width, 4)
                alpha = rgba[:, :, 3:4].astype(float) / 255
                expected = rgba[:, :, :3] * alpha + np.asarray([17, 29, 41]) * (1 - alpha)
                assert np.abs(first_frame.astype(float) - expected).max() <= 2, 'inherited GL state corrupts SDL alpha composite'
                assert GL.glIsTexture(overlay.overlay_tex)
                overlay.draw_gl()
                assert gl_state() == before, 'repeat upload leaks state'
                tex = overlay.overlay_tex
                overlay.cleanup(); overlay.cleanup()
                assert overlay.overlay_tex is None and not GL.glIsTexture(tex)
                assert gl_state() == before, 'cleanup changed foreign GL state'
                # Restore a conventional scene context after adversarial test.
                GL.glUseProgram(0)
                GL.glActiveTexture(GL.GL_TEXTURE1)
                GL.glDisable(GL.GL_TEXTURE_2D)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
                GL.glActiveTexture(GL.GL_TEXTURE0)
                GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
                GL.glBlendEquation(GL.GL_FUNC_ADD)
                for mode in (GL.GL_TEXTURE, GL.GL_PROJECTION, GL.GL_MODELVIEW):
                    GL.glMatrixMode(mode); GL.glLoadIdentity()
                for key, value in ((GL.GL_UNPACK_ALIGNMENT, 4), (GL.GL_UNPACK_ROW_LENGTH, 0),
                                   (GL.GL_UNPACK_SKIP_ROWS, 0), (GL.GL_UNPACK_SKIP_PIXELS, 0)):
                    GL.glPixelStorei(key, value)
                overlay.help_visible = False

                def save(name, array, rects, glyphs):
                    path = args.out / f'{width}x{height}_{name}.png'
                    Image.fromarray(array).save(path)
                    report.append(dict(file=str(path), driver=driver, gl_error=0,
                                       panels=[list(r) for r in rects], glyphs=glyphs))
                    pygame.display.flip(); pygame.event.pump()

                def capture(name, selection=(), help_page=None, high=False):
                    control.selection = set(selection)
                    overlay.help_visible = help_page is not None
                    if help_page is not None: overlay.help_page = help_page
                    overlay.apply_settings(dict(high_contrast_ui=high, tutorial_hints=True))
                    snapshot = json.dumps(st.to_dict(precise=True), sort_keys=True)
                    renderer.draw(0, control.selection)
                    hud.mission_progress = gm.mission.progress_text()
                    hud.mission_name = gm.mission.mission.get('name', '')
                    hud.mission_done, hud.mission_failed = gm.mission.completed, gm.mission.failed
                    hud.render(control.selection, None, 0, False)
                    hud.draw_gl()
                    underlying = pixels(width, height)
                    occupied = list(hud.blocked_rects)
                    overlay.surface.glyph_rects.clear()
                    overlay.draw(st, control, blocked_rects=occupied)
                    assert overlay.surface.glyph_rects == [r for _, r in overlay.text_bounds], 'unmeasured overlay glyph'
                    for i, r in enumerate(overlay.surface.glyph_rects):
                        assert not any(r.colliderect(other) for other in overlay.surface.glyph_rects[i+1:]), 'overlapping overlay glyphs'
                    assert overlay.panel_rects, (name, 'hint missing', occupied)
                    if help_page is None:
                        assert not any(a.colliderect(b) for a in overlay.panel_rects for b in occupied), (name, overlay.panel_rects, occupied)
                    overlay.draw_gl()
                    image = pixels(width, height)
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    assert snapshot == json.dumps(st.to_dict(precise=True), sort_keys=True)
                    mask = np.zeros((height, width), bool)
                    for r in overlay.panel_rects:
                        assert pygame.Rect(0, 0, width, height).contains(r)
                        mask[r.y:r.bottom, r.x:r.right] = True
                    assert np.array_equal(image[~mask], underlying[~mask]), 'overlay changed transparent world pixels'
                    glyphs = {}
                    for label, bounds in overlay.text_bounds:
                        assert any(r.inflate(-24, -24).contains(bounds) for r in overlay.panel_rects), label
                        band = image[bounds.y:bounds.bottom, bounds.x:bounds.right]
                        count = int((band.max(axis=2) > 180).sum())
                        assert count, ('missing/upright glyph', label)
                        glyphs[label] = count
                    # Framebuffer top/left and bottom/right follow SDL UV orientation.
                    r = overlay.panel_rects[0]
                    sx, sy = r.x + 8, r.y + 8
                    assert np.max(np.abs(image[sy, sx].astype(int) - np.asarray(overlay.surface.get_at((sx, sy))[:3]))) <= 15
                    if high:
                        assert (image[r.bottom - 12, r.x + 12] == 0).all(), 'high contrast background not black'
                    save(name, image, overlay.panel_rects, glyphs)
                    hud.blocked_rects.extend(overlay.panel_rects)
                    assert deliver(overlay, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=r.center))

                for page in range(len(HELP_PAGES)):
                    capture(f'help_{page}', help_page=page, high=page == 1)
                queued_before_help = json.dumps(st.to_dict(precise=True), sort_keys=True)
                overlay.help_visible = False
                assert deliver(overlay, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
                assert overlay.help_visible
                assert deliver(overlay, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN))
                assert overlay.help_page == len(HELP_PAGES) - 1
                assert deliver(overlay, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_b))
                assert deliver(overlay, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
                assert not overlay.help_visible
                assert queued_before_help == json.dumps(st.to_dict(precise=True), sort_keys=True)

                capture('hint_none')
                for e in sorted(st.entities.values(), key=lambda e: e.id):
                    if e.alive and (e.owner == 0 or st.can_see(0, e.id)):
                        capture('hint_' + e.data_id + '_' + str(e.id), [e.id], high=True)
                cruiser = next(e for e in owned if 'cruiser' in e.data_id)
                transport = next(e for e in owned if 'crew_transport' in e.data_id)
                frigate = next(e for e in owned if e.data_id == 'imperial_frigate')
                capture('hint_multi', [cruiser.id, transport.id, frigate.id])
                target = next(e for e in st.entities.values() if e.data_id == 'syndicate_corvette')
                capture('hint_hidden_target', [target.id])
                # Controlled positioning to test detected-target readouts; no claim
                # of natural navigation or successful physical boarding.
                target.pos.set(cruiser.pos)
                target.pos.x += 400
                assert st.can_see(0, target.id)
                capture('hint_detected_target_down', [target.id], high=True)
                target.shields['front'] = 100
                capture('hint_detected_target_up', [target.id])
                enemy_station = next(e for e in st.entities.values() if e.owner == 1 and e.is_station)
                enemy_station.pos.set(cruiser.pos); enemy_station.pos.z += 700
                assert st.can_see(0, enemy_station.id)
                capture('hint_detected_enemy_station', [enemy_station.id])
                transport.crew = 0
                capture('hint_empty_transport', [transport.id])
                transport.crew = transport.max_crew
                from game.core.vectors import Vec3
                constructor = gm.factory.spawn_ship('imperial_constructor', 0, Vec3(cruiser.pos.x - 400, 0, cruiser.pos.z))
                capture('hint_constructor', [constructor.id])
                transport.crew_cargo = 4  # Explicit controlled UI fixture.
                gm.mission.objectives[0]['done'] = True
                gm.mission.objectives[1]['active'] = True
                capture('hint_delivery', [transport.id])
                frigate.systems['life_support'].hp = 1
                capture('hint_low_support', [frigate.id])
                gm.mission.completed = True
                capture('hint_complete', [])
                gm.mission.completed = False; gm.mission.failed = True
                capture('hint_failed', [])
                gm.mission.failed = False
                target = next(e for e in st.entities.values() if e.owner not in (0, -1) and e.alive)
                # Visibility invariance uses actual sensor geometry, no mocked predicate.
                target.pos.x = st.map_info.bounds * 20
                assert not st.can_see(0, target.id)
                a = overlay.tutorial_paragraphs(st, [target.id])
                target.crew = 987; target.systems['life_support'].hp = 0
                assert a == overlay.tutorial_paragraphs(st, [target.id])
                overlay.apply_settings({'tutorial_hints': False})
                overlay.draw(st, control)
                assert not overlay.panel_rects and not overlay.text_bounds

                menu.settings = dict(DEFAULT_SETTINGS); menu.screen = 'settings'
                seen = set()
                for page in range(3):
                    menu.settings_page = page
                    menu._surface.glyph_rects.clear()
                    menu.render(0)
                    viewport = pygame.Rect(0, 0, width, height)
                    assert menu._surface.glyph_rects == [r for _, r in menu.settings_text_bounds], 'unmeasured settings glyph'
                    content = pygame.Rect(width // 2 - 330, 112, 660, height - 222)
                    for i, r in enumerate(menu._surface.glyph_rects):
                        assert viewport.contains(r)
                        assert not any(r.colliderect(other) for other in menu._surface.glyph_rects[i+1:]), 'overlapping settings glyphs'
                        if r.y < 112: continue  # SETTINGS title above card.
                        hit = [b for b in menu.buttons if b['rect'].colliderect(r)]
                        assert (any(b['rect'].contains(r) for b in hit) if hit else content.contains(r)), ('glyph outside control/card', r)
                        for b in menu.buttons:
                            payload = b.get('payload')
                            if b['action'] == 'slider' and isinstance(payload, dict):
                                assert not r.colliderect(payload['rect']), 'slider covers glyph'
                    for index, b in enumerate(menu.buttons):
                        assert viewport.contains(b['rect'])
                        assert not any(b['rect'].colliderect(other['rect']) for other in menu.buttons[index+1:])
                        payload = b.get('payload')
                        if isinstance(payload, dict) and 'key' in payload:
                            key = payload['key']; seen.add(key)
                            old = menu.settings[key]
                            menu.settings_focus = index
                            deliver(menu, pygame.event.Event(pygame.KEYDOWN, key=(pygame.K_LEFT if b['action'] == 'slider' else pygame.K_RIGHT)))
                            assert menu.settings[key] != old, ('unreachable keyboard control', key)
                            # Mouse activation must also reach every option.
                            point = (b['payload']['rect'].center if b['action'] == 'slider' else b['rect'].center)
                            mouse_old = menu.settings[key]
                            deliver(menu, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
                            assert menu.settings[key] != mouse_old, ('unreachable mouse control', key)
                    menu._surface.glyph_rects.clear()
                    menu.render(0)
                    assert menu._surface.glyph_rects == [r for _, r in menu.settings_text_bounds]
                    menu.draw_gl()
                    image = pixels(width, height)
                    glyphs = {}
                    for label, r in menu.settings_text_bounds:
                        assert viewport.contains(r), label
                        if label in ('PREVIOUS', 'NEXT', 'BACK'):
                            assert any(b['rect'].contains(r) for b in menu.buttons), label
                        count = int((image[r.y:r.bottom, r.x:r.right].max(axis=2) > 110).sum())
                        assert count, ('missing setting glyph', label)
                        glyphs[label] = count
                    save(f'settings_{page}', image, [b['rect'] for b in menu.buttons], glyphs)
                    deliver(menu, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN))
                assert seen == set(DEFAULT_SETTINGS), (seen, set(DEFAULT_SETTINGS))
                assert GL.glGetError() == GL.GL_NO_ERROR
            finally:
                GL.glUseProgram(0); GL.glDeleteProgram(program)
                overlay.cleanup(); menu.close(); renderer.close()
                GL.glDeleteTextures([int(t) for t in (sentinel, hud.tex) if t is not None])
        (args.out / 'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(result='PRESENTATION_UX_DIAG_OK', captures=len(report),
                              drivers=sorted({row['driver'] for row in report}),
                              report=str(args.out / 'report.json')), indent=2))
    finally:
        pygame.display.quit()


if __name__ == '__main__':
    main()
