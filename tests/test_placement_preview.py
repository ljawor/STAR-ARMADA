"""The station placement preview (#171): one flagged instance, no simulation change.

The legacy renderer drew the ghost itself and went with it (#160). What survives is
`render/input.py::update_placement`, which answers *where* the station would stand and *whether*
the site is legal, and `render/hud.py::_placement_banner`, which draws a 2D banner. These tests pin
the third thing: that answer crosses to the window as one ordinary frame instance carrying the
station's own binding, tinted by legality, flagged `FLAG_GHOST` - and that publishing it leaves the
simulation exactly as it was.
"""
from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path

from render_bridge import collect, packed

OS_ROOT = Path(__file__).resolve().parents[1]
MAIN = OS_ROOT / 'main.py'


def fixture(name='four-player-close-v1'):
    from game.graphics_benchmark import make_fixture
    scene = make_fixture(name)
    return scene.manager, scene.manager.state


def ghost(**overrides):
    payload = {'station_kind': 'shipyard', 'faction': 'imperial',
               'world': (600.0, 0.0, -400.0), 'radius': 120.0, 'valid': True}
    payload.update(overrides)
    return payload


def main_helpers(*names, **env):
    """Exec named top-level helpers out of the entry point without running it."""
    tree = ast.parse(MAIN.read_text())
    nodes = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN), 'exec'), env)
    return env


class _Session(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        pygame.font.init()
        self.manager, self.state = fixture()
        self.directory = tempfile.mkdtemp(prefix='ghost-')
        from render_bridge.live import LiveSession
        self.session = LiveSession(self.state, self.manager.ds, directory=self.directory,
                                   local_player=0, size=(320, 200))

    def tearDown(self):
        self.session.close()

    def publish(self, **kwargs):
        return self.session.publish(self.state, visible_ids=self.visible(), **kwargs)

    def visible(self):
        return {entity.id for entity in self.state.entities.values() if entity.alive}

    def instances(self):
        from render_bridge import ring
        reader = ring.Ring.open(str(self.session.paths['frame']))
        try:
            got = reader.latest()
        finally:
            reader.close()
        self.assertIsNotNone(got, 'no frame was readable back')
        _sequence, payload = got
        tables = packed.Tables.decode(Path(self.session.paths['tables']).read_bytes())
        frame = packed.unpack_frame(payload, tables)
        return frame['instances'], frame


class GhostInstanceTests(_Session):
    def test_a_legal_ghost_crosses_as_one_flagged_instance(self):
        self.publish()                       # a real frame, so the ring has a baseline to compare
        before, _ = self.instances()
        self.publish(ghost=ghost())
        after, frame = self.instances()
        self.assertEqual(len(after), len(before) + 1, 'the preview must add exactly one instance')
        entry = [record for record in after if record['flags'] & packed.FLAG_GHOST]
        self.assertEqual(len(entry), 1)
        entry = entry[0]
        self.assertEqual(entry['entity_id'], collect.GHOST_ENTITY)
        self.assertEqual(entry['binding'], 'imperial:shipyard',
                         'the preview must be the station binding the player is placing')
        r, g, b, _alpha = entry['tint']
        self.assertGreater(g, r, 'a legal site is green')
        self.assertGreater(g, b)

    def test_the_preview_is_translucent_not_opaque(self):
        # The window draws any instance below full alpha in its own depth-testing-but-not-writing
        # view, so translucency is what makes the ghost show the site behind it instead of
        # covering the ground the player is trying to judge.
        for valid in (True, False):
            with self.subTest(valid=valid):
                self.publish(ghost=ghost(valid=valid))
                entries, _ = self.instances()
                entry = [r for r in entries if r['flags'] & packed.FLAG_GHOST][0]
                self.assertLess(entry['tint'][3], 0.9, 'an opaque preview is not a preview')
                self.assertGreater(entry['tint'][3], 0.2, 'a preview too faint to read is not a preview')

    def test_an_illegal_site_turns_the_preview_red(self):
        self.publish(ghost=ghost(valid=False))
        entries, _ = self.instances()
        entry = [record for record in entries if record['flags'] & packed.FLAG_GHOST][0]
        r, g, b, _alpha = entry['tint']
        self.assertGreater(r, g, 'an illegal site is red')
        self.assertGreater(r, b)

    def test_no_placement_means_no_ghost_instance(self):
        self.publish()
        entries, _ = self.instances()
        self.assertFalse([r for r in entries if r['flags'] & packed.FLAG_GHOST])
        self.assertFalse(self.session.counts.get('ghost', False))

    def test_a_ghost_without_a_world_position_is_not_drawn(self):
        # `update_placement` sets `ghost` to None when the cursor is off the world plane; a partial
        # payload must not invent an origin, which would draw a preview at 0,0,0.
        self.publish(ghost={'station_kind': 'shipyard', 'faction': 'imperial', 'world': None})
        entries, _ = self.instances()
        self.assertFalse([r for r in entries if r['flags'] & packed.FLAG_GHOST])

    def test_the_preview_carries_the_station_scale_from_its_radius(self):
        from game.benchmark import state_hash
        before = state_hash(self.state)
        self.publish(ghost=ghost(radius=200.0))
        entries, _ = self.instances()
        entry = [record for record in entries if record['flags'] & packed.FLAG_GHOST][0]
        # The 3x4 matrix is column-major with `scale` on the three diagonal entries (0, 4, 8).
        matrix = list(entry['matrix'])
        self.assertAlmostEqual(matrix[0], 200.0 / 50.0, places=5)
        self.assertAlmostEqual(matrix[4], 200.0 / 50.0, places=5)
        self.assertAlmostEqual(matrix[8], 200.0 / 50.0, places=5)
        self.assertEqual(state_hash(self.state), before,
                         'drawing a preview must not change the simulation')


class GateTests(unittest.TestCase):
    """The game decides whether a ghost is drawn, so the gate is tested where it lives."""

    class _World:
        def __init__(self, builder):
            self.entities = {} if builder is None else {builder.id: builder}

    class _Builder:
        def __init__(self, owner=0, alive=True, is_construction=True):
            self.id, self.owner, self.alive = 7, owner, alive
            self.is_construction = is_construction

    def run_gate(self, placement, builder, local_player=0):
        env = main_helpers('cpp_placement_ghost', hud=type('H', (), {'placement': placement})())
        return env['cpp_placement_ghost'](self._World(builder), local_player)

    def test_own_live_construction_hull_gets_the_preview(self):
        result = self.run_gate({'builder_id': 7, 'ghost': ghost()}, self._Builder())
        self.assertIsNotNone(result)
        self.assertEqual(result['world'], (600.0, 0.0, -400.0))

    def test_no_placement_is_no_preview(self):
        self.assertIsNone(self.run_gate(None, self._Builder()))

    def test_a_ghost_without_a_world_does_not_draw(self):
        self.assertIsNone(self.run_gate({'builder_id': 7, 'ghost': {'world': None}},
                                        self._Builder()))

    def test_someone_elses_builder_does_not_draw(self):
        self.assertIsNone(self.run_gate({'builder_id': 7, 'ghost': ghost()},
                                        self._Builder(owner=1)))

    def test_a_dead_builder_does_not_draw(self):
        self.assertIsNone(self.run_gate({'builder_id': 7, 'ghost': ghost()},
                                        self._Builder(alive=False)))

    def test_a_non_construction_hull_does_not_draw(self):
        # Only a construction ship may place hardware; a warship with a stale payload must not
        # paint a station.
        self.assertIsNone(self.run_gate({'builder_id': 7, 'ghost': ghost()},
                                        self._Builder(is_construction=False)))


if __name__ == '__main__':
    unittest.main()
