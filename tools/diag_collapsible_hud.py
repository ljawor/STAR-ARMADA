"""Real Cocoa SDL/GL HUD collapse and colony-input acceptance.

PYTHONPATH=. .venv/bin/python tools/diag_collapsible_hud.py --out DIR
Controlled owned-colony fixture; commands still pass through production input.
"""
import argparse
import json
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
from game.systems.colonies import eligible_planet
from game.systems.planet_buildings import BUILDING_TYPES
from render.camera import Camera
from render.hud import HUD
from render.input import InputController


class FontProbe:
    def __init__(self, font, sources):
        self.font, self.sources = font, sources

    def __getattr__(self, name):
        return getattr(self.font, name)

    def render(self, text, *args, **kwargs):
        surf = self.font.render(text, *args, **kwargs)
        self.sources[id(surf)] = (str(text), surf)
        return surf


class SurfaceProbe(pygame.Surface):
    def __init__(self, size, sources, glyphs):
        super().__init__(size, pygame.SRCALPHA)
        self.sources, self.glyphs = sources, glyphs

    def blit(self, source, dest, *args, **kwargs):
        result = super().blit(source, dest, *args, **kwargs)
        if id(source) in self.sources:
            text, _ = self.sources[id(source)]
            rect = source.get_bounding_rect(min_alpha=1).move(result.topleft)
            if rect.width and rect.height:
                self.glyphs.append((text, rect))
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    ds = DataStore.get()
    game = GameManager.start_skirmish(ds.maps['skirmish01'])
    st = game.state
    for player in st.players.values():
        player.is_ai = False
    planet = next(e for e in st.entities.values() if eligible_planet(e))
    planet.colonized_by = 0
    observer = next(e for e in st.entities.values() if e.owner == 0 and e.is_ship)
    observer.pos = planet.pos.copy()
    p = st.players[0]
    p.credits = p.materials = p.energy = p.crew = 100000
    report = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            from pygame._sdl2.video import Window
            Window.from_display_module().focus()
            GL.glViewport(0, 0, width, height)
            pygame.event.pump()
            view = HUD(width, height, st)
            ctrl = InputController(st, Camera(width, height), view,
                                   SimpleNamespace(flash=lambda *_: None))
            ctrl.selection = {planet.id}
            view.mission_name = 'Secure the colony'
            view.mission_progress = ['[ ] Build surface infrastructure', '[ ] Defend orbital space']
            sources, glyphs = {}, []
            for name in ('font', 'font_big', 'font_small', 'font_title'):
                setattr(view, name, FontProbe(getattr(view, name), sources))
            view.overlay = SurfaceProbe((width, height), sources, glyphs)

            def dispatch(*events):
                pygame.event.clear()
                for ev in events:
                    pygame.event.post(ev)
                for ev in pygame.event.get():
                    ctrl.handle_event(ev)

            def click(button):
                point = button['rect'].center
                dispatch(*(pygame.event.Event(kind, button=1, pos=point)
                           for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)))

            def capture(name):
                sources.clear(); glyphs.clear()
                before = st.to_dict(precise=True)
                GL.glClearColor(.025, .04, .07, 1)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                view.render(ctrl.selection, None, 0, False)
                view.draw_gl()
                GL.glFinish()
                pixels = np.flipud(np.frombuffer(GL.glReadPixels(
                    0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE), np.uint8)
                    .reshape(height, width, 3)).copy()
                assert GL.glGetError() == GL.GL_NO_ERROR
                assert before == st.to_dict(precise=True), 'render mutated sim'
                viewport = pygame.Rect(0, 0, width, height)
                panel_glyphs = [(t, r) for t, r in glyphs if 44 <= r.y < height - 236]
                for text, rect in panel_glyphs:
                    assert viewport.contains(rect), (text, rect)
                    assert any(r.contains(rect) for r in view.blocked_rects), ('glyph outside card', text, rect)
                    band = pixels[rect.top:rect.bottom, rect.left:rect.right]
                    assert (band.max(axis=2) > 85).any(), ('missing GL glyph', text)
                for i, (text, rect) in enumerate(panel_glyphs):
                    for other, other_rect in panel_glyphs[i + 1:]:
                        assert not rect.colliderect(other_rect), ('overlapping glyphs', text, other)
                for button in view.buttons:
                    assert viewport.contains(button['rect'])
                    assert any(r.contains(button['rect']) for r in view.blocked_rects)
                path = out / f'{width}_{name}.png'
                Image.fromarray(pixels).save(path)
                report.append(dict(file=str(path), glyph_count=len(panel_glyphs),
                                   buttons=len(view.buttons), scroll_regions=len(view.scroll_rects)))
                pygame.display.flip(); pygame.event.pump()

            try:
                capture('surface')
                seen = set()
                for page in range(4):
                    seen.update(b['payload']['station_kind'] for b in view.buttons
                                if b['kind'] == 'build_planet_building')
                    arrow = next((b for b in view.buttons if b['kind'] == 'hud_scroll'
                                  and b['payload']['delta'] > 0), None)
                    if arrow is None:
                        break
                    click(arrow)
                    capture(f'surface_page_{page}')
                assert seen == set(BUILDING_TYPES), ('missing surface rows', seen)
                # Wait until real frames have made the native window visible,
                # then activate this exact process for the actual cursor gate.
                Window.from_display_module().focus()
                if sys.platform == 'darwin':
                    import os
                    import subprocess
                    subprocess.run(['osascript', '-e',
                        'tell application "System Events"\n'
                        f'set qaProcess to first process whose unix id is {os.getpid()}\n'
                        'set frontmost of qaProcess to true\n'
                        'if (count of windows of qaProcess) > 0 then\n'
                        'tell qaProcess to perform action "AXRaise" of window 1\n'
                        'end if\n'
                        'end tell'], check=True, timeout=10)
                    for _ in range(10):
                        pygame.event.pump()
                        pygame.time.wait(30)
                region, key = view.scroll_rects[-1]
                pygame.mouse.set_pos(region.center)
                for _ in range(10):
                    pygame.event.pump()
                    if region.collidepoint(pygame.mouse.get_pos()):
                        break
                    pygame.time.wait(20)
                assert region.collidepoint(pygame.mouse.get_pos()), ('SDL cursor not over list', pygame.mouse.get_pos(), list(region), pygame.display.get_driver(), pygame.mouse.get_focused())
                distance = ctrl.camera.distance
                dispatch(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
                assert ctrl.camera.distance == distance
                capture('surface_wheel')
                row = next(b for b in view.buttons if b['kind'] == 'build_planet_building')
                click(row)
                assert len(st.command_queue) == 1 and st.command_queue[0].type == 'build_planet_building'
                game.step(1 / 30)
                assert planet.build_queue[-1]['kind'] == 'planet_building'
                capture('paid_surface')
                orbit = next(b for b in view.buttons if b['kind'] == 'hud_planet_page' and b['payload']['page'] == 'orbit')
                click(orbit)
                click(row)  # stale surface row in the same SDL event batch
                assert not st.command_queue
                capture('orbit')
                assert {b['payload']['station_kind'] for b in view.buttons if b['kind'] == 'build_satellite'} == {'attack_satellite', 'defense_satellite'}
                for key in ('left', 'right', 'mission'):
                    button = next(b for b in view.buttons if b['kind'] == 'hud_panel' and b['payload']['panel'] == key)
                    stale_rows = [b for b in view.buttons if b.get('panel') == key and b['kind'] != 'hud_panel']
                    click(button)
                    for stale in stale_rows:
                        click(stale)
                    assert not st.command_queue and not ctrl.dragging
                    capture(f'collapsed_{key}')
                assert not view.scroll_rects, 'orphan scroll region'
                assert not any(r.collidepoint((100, 110)) for r in view.blocked_rects)
                assert not any(r.collidepoint((width - 100, 110)) for r in view.blocked_rects)
                for button in list(view.buttons):
                    click(button)
                capture('restored')
                assert not any(view.minimized.values())
                selected = set(ctrl.selection)
                dispatch(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(100, 100)),
                         pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=(100, 100)))
                assert not st.command_queue and ctrl.selection == selected
            finally:
                view.close()
        (out / 'metrics.json').write_text(json.dumps(report, indent=2))
        print(f'COLLAPSIBLE_HUD_DIAG_OK: {len(report)} real GL captures; {out}')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
