"""Real Cocoa/GL proof of #70 CMD totals and station/surface/orbit build labels.

Run: PYTHONPATH=. python tools/diag_infrastructure_commands.py --out <scratch>
No mouse-focus claim: rows are paged programmatically, production painters remain real.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame
from OpenGL import GL
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.economy import EconomySystem
from render.camera import Camera
from render.hud import HUD
from render.renderer import Renderer


class FontProbe:
    def __init__(self, font):
        self.font = font
        self.texts = []

    def __getattr__(self, key):
        return getattr(self.font, key)

    def render(self, text, *args, **kwargs):
        self.texts.append(str(text))
        return self.font.render(text, *args, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1280, 800), pygame.DOUBLEBUF | pygame.OPENGL)
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    st = gm.state
    for p in st.players.values():
        p.is_ai = False
    p = st.players[0]
    p.credits = p.materials = p.energy = p.crew = 100000
    builder = next(e for e in st.entities.values() if e.data_id == 'imperial_constructor' and e.owner == 0)
    builder.pos = Vec3(-17000, 0, -5000)
    planet = next(e for e in st.entities.values() if e.data_id == 'temperate')
    planet.colonized_by = 0
    EconomySystem.recompute_command_capacity(st)
    used = p.command_used(st.entities)
    assert gm.construction.start_station(builder.id, 'research_station', builder.pos, 0)
    assert gm.construction.start_satellite(planet.id, 'defense_satellite', 0)
    from game.systems.planet_buildings import start_building, BUILDING_TYPES
    assert start_building(gm.construction, planet.id, 'planet_extractor', 0)
    assert p.command_used(st.entities) == used + 7
    gm.visibility.update()
    before = json.loads(json.dumps(st.to_dict(precise=True)))
    camera = Camera(1280, 800)
    camera.target = [builder.pos.x, builder.pos.y, builder.pos.z]
    camera.yaw, camera.pitch, camera.distance = 0, 30, 3200
    renderer = Renderer(st, camera)
    renderer.diff_render = True
    hud = HUD(1280, 800, st)
    report = []
    try:
        for width, height in ((1280, 800), (1024, 768)):
            pygame.display.set_mode((width, height), pygame.DOUBLEBUF | pygame.OPENGL)
            GL.glViewport(0, 0, width, height)
            camera.width, camera.height = width, height
            hud.resize(width, height)
            probe = FontProbe(hud.font_big)
            hud.font_big = probe
            rows, labels = [], []
            original_row, original_label = hud._build_row, hud._label

            def label(x, y, text, color=None, font=None):
                labels.append((str(text), pygame.Rect(x, y, *(font or hud.font).size(str(text)))))
                return original_label(x, y, text, color, font)

            def row(panel, y, data, player, payload, kind):
                start = len(labels)
                result = original_row(panel, y, data, player, payload, kind)
                rect = pygame.Rect(panel.x + 12, y, 296, 50)
                painted = labels[start:]
                assert any(f'{data.command_cost} cmd' in text and rect.contains(box)
                           for text, box in painted), (data.id, painted)
                assert all(rect.contains(box) for _, box in painted), data.id
                rows.append(data.id)
                return result

            hud._label, hud._build_row = label, row
            cases = [('stations', builder, 'surface', set(gm.ds.ships[builder.data_id].can_build_stations)),
                     ('planet_buildings', planet, 'surface', set(BUILDING_TYPES)),
                     ('satellites', planet, 'orbit', {'attack_satellite', 'defense_satellite'})]
            for key, selected, page, expected in cases:
                rows.clear()
                hud.planet_page = page
                for offset in range(len(expected) + 1):
                    hud.scroll[key] = offset
                    renderer.draw(0, {selected.id})
                    hud.render({selected.id}, None, 0, False, '', 0, 0)
                    hud.draw_gl()
                    assert GL.glGetError() == GL.GL_NO_ERROR
                    assert f'{used + 7}/{p.command_capacity}' in probe.texts
                    if offset == 0 or 'research_station' in rows:
                        GL.glFinish()
                        raw = GL.glReadPixels(0, 0, width, height, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                        image = pygame.image.frombuffer(bytes(raw), (width, height), 'RGB')
                        pygame.image.save(pygame.transform.flip(image, False, True),
                                          str(out / f'{width}x{height}-{key}-{offset}.png'))
                assert set(rows) == expected, (key, set(rows), expected)
                report.append(dict(size=[width, height], panel=key, rows=sorted(set(rows)),
                                   committed_cmd=used + 7, capacity=p.command_capacity))
            hud._label, hud._build_row = original_label, original_row
            hud.font_big = probe.font
        assert before == json.loads(json.dumps(st.to_dict(precise=True)))
        (out / 'report.json').write_text(json.dumps(report, indent=2))
        print('INFRASTRUCTURE_CMD_GL_OK', json.dumps(report))
    finally:
        hud.close()
        renderer.close()
        pygame.quit()


if __name__ == '__main__':
    main()
