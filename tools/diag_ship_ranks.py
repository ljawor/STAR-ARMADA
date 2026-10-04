"""Real SDL/GL selected ship rank probe; no dummy driver, no synthetic frame.

PYTHONPATH=. .venv/bin/python tools/diag_ship_ranks.py [scratch-output-directory]
Captures BEFORE flip, asserts glyph pixels and absence of bars over rank text.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pygame
from OpenGL import GL
from PIL import Image

from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.experience import max_rank
from render.hud import HUD, BAR_HULL, ship_rank_panel_data


def main():
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        raise RuntimeError("This diagnostic requires a real SDL/GL window")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ["TMPDIR"]) / "ship-ranks"
    out.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    DataStore.reset()
    ds = DataStore.get()
    game = GameManager.start_skirmish(ds.maps["skirmish01"])
    st = game.state
    ship = next(e for e in st.entities.values()
                if e.owner == 0 and e.is_ship and not e.is_construction)
    squad_id = next(s.id for s in ds.ships.values() if s.is_squadron)
    squad = game.factory.spawn_ship(squad_id, 0, ship.pos + Vec3(100, 0, 0))
    tiles = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
            pygame.event.pump()
            GL.glViewport(0, 0, width, height)
            view = HUD(width, height, st)
            labels, bars = [], []
            original_label, original_bar = view._label, view._bar

            def label(x, y, text, color=None, font=None):
                chosen = font or view.font
                labels.append((str(text), pygame.Rect(x, y, *chosen.size(str(text)))))
                original_label(x, y, text, color, font)

            def bar(x, y, w, h, *args):
                bars.append(pygame.Rect(x, y, w, h))
                original_bar(x, y, w, h, *args)

            view._label, view._bar = label, bar
            try:
                for name, entity, rank in (("rookie", ship, 1), ("promoted", ship, 3),
                                           ("maximum", ship, max_rank(ship)),
                                           ("squadron", squad, 2)):
                    entity.xp = ds.rules["experience"]["levels"][rank - 1] * ds.ships[entity.data_id].veteran_xp / 100
                    entity.level = 1  # Prove the UI reads XP, not stale saved level.
                    entity.jump_target = entity.pos.copy()
                    before = st.to_dict(precise=True)
                    labels.clear()
                    bars.clear()
                    GL.glClearColor(.025, .04, .07, 1)
                    GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                    view.render({entity.id}, None, 0, False)
                    view.draw_gl()
                    GL.glFinish()
                    raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                    pixels = np.flipud(np.frombuffer(raw, np.uint8).reshape(height, width, 3)).copy()
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    assert st.to_dict(precise=True) == before, "HUD mutated simulation state"
                    expected = ship_rank_panel_data(entity)
                    panel = view.blocked_rects[1]  # top bar then selection panel
                    counts = {}
                    for text in expected.values():
                        matching = [rect for value, rect in labels if value == text and rect.x < 330]
                        assert len(matching) == 1, f"missing readout {text}"
                        rect = matching[0]
                        assert panel.contains(rect), f"clipped readout {text}"
                        assert not any(rect.colliderect(b) for b in bars), f"bar overlaps {text}"
                        band = pixels[rect.top:rect.bottom, rect.left:rect.right].astype(int)
                        glyphs = int((band.max(axis=2) > 100).sum())
                        green = int((np.abs(band - np.array(BAR_HULL)).max(axis=2) < 8).sum())
                        assert glyphs > 20, f"GL text invisible: {text} ({glyphs} px)"
                        assert green == 0, f"hull bar paints over {text}"
                        counts[text] = glyphs
                    for button in view.buttons:
                        if button["kind"] == "ability":
                            assert panel.contains(button["rect"]), "ability outside selection panel"
                    if entity.is_squadron:
                        assert any(value.startswith("FIGHTERS ") for value, _ in labels)
                    image = Image.fromarray(pixels)
                    filename = out / f"{width}_{name}.png"
                    image.save(filename)
                    tiles.append(image.crop((10, 44, 330, 474)))
                    print(f"{filename}: glyph_pixels={counts}")
                    pygame.display.flip()
                    pygame.event.pump()
            finally:
                view.close()
        montage = Image.new("RGB", (320 * 4, 430 * 2))
        for index, tile in enumerate(tiles):
            montage.paste(tile, ((index % 4) * 320, (index // 4) * 430))
        montage.save(out / "rank_panels.png")
        print(f"SHIP_RANKS_DIAG_OK: {len(tiles)} framebuffer captures; {out / 'rank_panels.png'}")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
