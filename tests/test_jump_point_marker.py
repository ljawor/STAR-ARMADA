"""The world view draws no jump-point marker at all.

The old marker (two line loops, later a ring plus a light cone) read as a stray
circle - or an opaque blue teardrop - beside whatever object sat nearby, because a
jump point is a map cell and nothing was ever modelled there. The owner asked for
nothing, so this guard fails if the pass starts emitting geometry again.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from render.renderer import Renderer


class JumpPointMarkerTests(unittest.TestCase):
    def renderer(self):
        r = Renderer.__new__(Renderer)
        jp = {"pos": [700.0, 0.0, 500.0]}
        r.state = SimpleNamespace(
            map_info=SimpleNamespace(jump_points=[jp, {"pos": [-900.0, 0.0, 300.0]}]),
            is_position_explored=lambda player, position: True,
            entities={},
            players={0: SimpleNamespace(faction="imperial")},
        )
        r.local_player = 0
        r.time = 0.0
        r.camera = SimpleNamespace(distance=2000.0)
        return r

    def test_pass_emits_no_geometry(self):
        names = ("glBegin", "glPushMatrix", "glColor3f", "glColor4f", "glVertex3f",
                 "glLineWidth", "glEnable", "glDisable", "glTranslatef")
        r = self.renderer()
        patches = [patch(f"render.renderer.{name}") for name in names]
        mocks = [p.start() for p in patches]
        try:
            r._draw_jump_points()
        finally:
            for p in patches:
                p.stop()
        for name, mock in zip(names, mocks):
            self.assertFalse(mock.called, f"{name} called by the jump-point pass")

    def test_pass_survives_an_empty_map(self):
        r = self.renderer()
        r.state.map_info = SimpleNamespace(jump_points=[])
        self.assertIsNone(r._draw_jump_points())


if __name__ == "__main__":
    unittest.main()
