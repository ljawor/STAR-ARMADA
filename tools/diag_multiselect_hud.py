"""Real SDL/OpenGL selection inspector acceptance probe (no dummy driver).

PYTHONPATH=. .venv/bin/python tools/diag_multiselect_hud.py --out DIR
--baseline loads HEAD's HUD in memory without changing the working tree.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pygame
from OpenGL import GL
from PIL import Image
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from render.hud import HUD, ACCENT, BAR_HULL


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--out', type=Path, required=True)
    args.add_argument('--baseline', action='store_true')
    options = args.parse_args()
    options.out.mkdir(parents=True, exist_ok=True)
    if os.environ.get('SDL_VIDEODRIVER') == 'dummy':
        raise RuntimeError('Real SDL/OpenGL display required')
    cls = HUD
    if options.baseline:
        mod = ModuleType('baseline_hud')
        exec(subprocess.check_output(['git', 'show', 'HEAD:render/hud.py'], text=True), mod.__dict__)
        cls = mod.HUD
    pygame.display.init()
    pygame.font.init()
    ds = DataStore.get()
    game = GameManager.start_skirmish(ds.maps['skirmish01'])
    ds = DataStore.get()
    st = game.state
    constructor = next(e for e in st.entities.values() if e.owner == 0 and e.is_construction)
    constructor.order_type = 'move'
    constructor.build_queue = [{'item': 'sensor_station', 'time_left': 34, 'total': 60}]
    constructor.name_override = 'Engineering Corps Long Range Orbital Construction Corvette'
    base = constructor.pos.copy()
    mixed = [constructor]
    for sd in list(ds.ships.values()):
        if sd.is_squadron or sd.abilities:
            ship = game.factory.spawn_ship(sd.id, 0, base + Vec3(80 * len(mixed), 0, 0))
            ship.energy = 1000
            if sd.abilities and len(mixed) % 2:
                ship.ability_cooldowns[sd.abilities[0]] = 12
            mixed.append(ship)
        if len(mixed) >= 8:
            break
    capable = next(s for s in ds.ships.values() if s.abilities)
    large = [game.factory.spawn_ship(capable.id, 0, base.copy()) for _ in range(60)]
    for e in large:
        e.energy = 1000
    original_ship = ds.ships[capable.id]
    report = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            pygame.event.pump()
            GL.glViewport(0, 0, width, height)
            view = cls(width, height, st)
            labels, bars = [], []
            label_fn, bar_fn = view._label, view._bar
            def label(x, y, text, color=None, font=None):
                labels.append((str(text), pygame.Rect(x, y, *(font or view.font).size(str(text)))))
                label_fn(x, y, text, color, font)
            def bar(x, y, w, h, *args):
                bars.append((pygame.Rect(x, y, w, h), tuple(args[1][:3])))
                bar_fn(x, y, w, h, *args)
            view._label, view._bar = label, bar
            def capture(name, selection):
                labels.clear(); bars.clear()
                before = st.to_dict(precise=True)
                GL.glClearColor(.025, .04, .07, 1)
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                view.render(selection, None, 0, False)
                view.draw_gl()
                GL.glFinish()
                raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
                path = options.out / f'{width}_{name}{"_baseline" if options.baseline else ""}.png'
                Image.fromarray(pixels).save(path)
                assert GL.glGetError() == GL.GL_NO_ERROR
                assert before == st.to_dict(precise=True), 'HUD mutated simulation'
                panel = view.blocked_rects[1]
                screen = pygame.Rect(0, 0, width, height)
                assert screen.contains(panel)
                glyphs = {}
                for text, rect in labels:
                    if rect.x >= 330:
                        continue
                    assert panel.contains(rect), f'clipped label {text}: {rect}'
                    assert not any(rect.colliderect(b) for b, _ in bars), f'bar overlaps {text}'
                    band = pixels[rect.top:rect.bottom, rect.left:rect.right].astype(int)
                    count = int((band.max(axis=2) > 85).sum())
                    assert count > 0, f'no framebuffer glyphs: {text}'
                    for _, color in bars:
                        assert not (np.abs(band - np.array(color)).max(axis=2) < 4).any(), f'bar-colored pixels over text {text}'
                    glyphs[text] = count
                for b in view.buttons:
                    if b['rect'].x < 330:
                        assert panel.contains(b['rect']), f'clipped hitbox {b}'
                report.append({'file': str(path), 'labels': glyphs,
                               'panel': list(panel), 'buttons': len(view.buttons)})
                pygame.display.flip(); pygame.event.pump()
            try:
                capture('mixed', {e.id for e in mixed} | {999999})
                assert any(t == f'SELECTED UNITS · {len(mixed)}' for t, _ in labels), 'first unit masquerades as selection'
                seen = set(view.visible_selection_ids)
                for offset in range(len(mixed)):
                    view.scroll['selection'] = offset
                    capture(f'mixed_page_{offset}', {e.id for e in mixed})
                    seen.update(view.visible_selection_ids)
                assert seen == {e.id for e in mixed}, 'roster omits units'
                capture('constructor', {constructor.id})
                order = next(r for t, r in labels if t.startswith('ORDER:'))
                building = next(r for t, r in labels if t.startswith('BUILDING'))
                assert not order.colliderect(building), 'order/build overlap'
                ds.ships[capable.id] = replace(original_ship, abilities=list(ds.abilities))
                seen_units, seen_abilities = set(), set()
                for off in range(0, 65, 3):
                    view.scroll['selection'] = off
                    view.scroll['abilities'] = off
                    capture(f'large_page_{off}', {e.id for e in large})
                    seen_units.update(view.visible_selection_ids)
                    seen_abilities.update(b['payload']['ability_id'] for b in view.buttons if b['kind'] == 'ability')
                assert seen_units == {e.id for e in large}, 'large roster inaccessible'
                assert seen_abilities == set(ds.abilities), f'ability union inaccessible: {seen_abilities} vs {set(ds.abilities)}'
                ds.ships[capable.id] = original_ship
            finally:
                view.close()
        (options.out / 'metrics.json').write_text(json.dumps(report, indent=2))
        print(f'MULTISELECT_HUD_DIAG_OK: {len(report)} framebuffer captures; {options.out}')
    finally:
        ds.ships[capable.id] = original_ship
        pygame.quit()


if __name__ == '__main__':
    main()
