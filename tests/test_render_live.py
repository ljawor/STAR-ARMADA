"""The live producer: a running match's rings, as `main.py --renderer cpp` publishes them.

These tests never open a window. They publish a real fixture's frames into a temporary directory and
read the rings back, so what is asserted is what a window would decode: the frame carries the
session's own tables, the HUD's first frame is a whole surface and later ones are rects, and the
cues and effects a window receives are the ones the game's answers produced.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from render_bridge import overlay, packed, ring


def fixture(name='four-player-close-v1'):
    from game.graphics_benchmark import make_fixture
    scene = make_fixture(name)
    return scene.manager, scene.manager.state


class LiveSessionTest(unittest.TestCase):
    def setUp(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        pygame.font.init()
        self.manager, self.state = fixture()
        self.directory = tempfile.mkdtemp(prefix='live-')
        from render_bridge.live import LiveSession
        self.session = LiveSession(self.state, self.manager.ds, directory=self.directory,
                                   local_player=0, size=(320, 200))

    def tearDown(self):
        self.session.close()

    def visible(self):
        return {entity.id for entity in self.state.entities.values() if entity.alive}

    def test_rings_are_created_in_the_given_directory(self):
        inner = Path(self.directory)
        for name in ('frame', 'tables', 'overlay', 'emit', 'markers', 'fog', 'planets'):
            path = self.session.paths[name]
            self.assertEqual(path.parent, inner, f'{name} ring escaped the session directory')
            self.assertTrue(path.exists(), f'{name} ring was not created')

    def test_publish_reports_what_it_sent(self):
        counts = self.session.publish(self.state, visible_ids=self.visible())
        self.assertEqual(self.session.frames, 1)
        for key in ('instances', 'primitives', 'markers', 'overlay_bytes'):
            self.assertIn(key, counts)
            self.assertGreater(counts[key], 0, f'{key} was empty on the first frame')
        self.assertTrue(counts['keyframe'], 'the first HUD frame must be a whole surface')

    def test_the_first_overlay_is_a_keyframe_and_the_next_is_not(self):
        first = self.session.publish(self.state, visible_ids=self.visible())
        second = self.session.publish(self.state, visible_ids=self.visible())
        self.assertTrue(first['keyframe'])
        self.assertFalse(second['keyframe'],
                         'a rect patch after a whole surface is the whole point of design A')
        self.assertLess(second['overlay_bytes'], first['overlay_bytes'])

    def test_a_published_frame_decodes_against_the_sessions_own_tables(self):
        self.session.publish(self.state, visible_ids=self.visible())
        reader = ring.Ring.open(str(self.session.paths['frame']))
        try:
            got = reader.latest()
        finally:
            reader.close()
        self.assertIsNotNone(got, 'no frame was readable back')
        _sequence, payload = got
        tables = packed.Tables.decode(Path(self.session.paths['tables']).read_bytes())
        frame = packed.unpack_frame(payload, tables)
        self.assertEqual(frame['tick'], self.state.tick)
        self.assertGreater(len(frame['instances']), 0)

    def test_an_overlay_frame_decodes_to_the_hud_surface_size(self):
        self.session.publish(self.state, visible_ids=self.visible())
        reader = ring.Ring.open(str(self.session.paths['overlay']))
        try:
            got = reader.latest()
        finally:
            reader.close()
        self.assertIsNotNone(got)
        _sequence, payload = got
        frame = overlay.decode(payload)
        self.assertEqual((frame['width'], frame['height']), (320, 200))

    def test_the_hull_radius_lookup_is_memoized_per_hull_class(self):
        """`ship_size` is a catalogue lookup, and it ran once per entity per frame: 688 shields
        cost 138 ms, which is what the "emit block" measurement was really looking at.

        The fixture's convoy hulls have no mesh, so `visual` answers with a reason and the radius
        is zero; the resolution is stubbed here so the *cache* is what is under test.
        """
        import render.ship_sizes as sizes
        calls = {'n': 0}
        original = sizes.ship_size

        class Size:
            radius = 24.0

        def counted(*_args, **_kwargs):
            calls['n'] += 1
            return Size()

        ships = [entity for entity in self.state.entities.values()
                 if entity.alive and entity.is_ship][:4]
        self.assertGreaterEqual(len(ships), 2, 'fixture has no hulls to memoize')
        self.session.collector.visual = lambda **_kwargs: (0, 1.0)
        sizes.ship_size = counted
        try:
            for _ in range(2):
                for ship in ships:
                    self.assertEqual(self.session.radius_of(ship), 24.0)
            resolved = dict(self.session._radius_cache)
        finally:
            sizes.ship_size = original
        self.assertEqual(calls['n'], len(resolved),
                         'a hull class was resolved more than once')
        self.assertLessEqual(calls['n'], 2, 'two convoys of one class must resolve once')

    def test_a_handed_in_camera_is_published_every_frame(self):
        """The window's camera must be the game's, or a click lands somewhere the player is not
        looking - which is why the input ring stays unread until this pose crosses."""
        from render_bridge import camera as cam
        from render_bridge import ring as ring_mod
        class Pose:
            target, distance, yaw, pitch = [10.0, 20.0, 30.0], 1234.0, 45.0, 60.0
        self.session.camera = Pose()
        self.session.publish(self.state, visible_ids=self.visible())
        reader = ring_mod.Ring.open(str(self.session.paths['camera']))
        try:
            got = reader.latest()
        finally:
            reader.close()
        self.assertIsNotNone(got, 'no camera pose was published')
        _sequence, payload = got
        pose = cam.decode(payload)
        self.assertEqual(pose['target'], (10.0, 20.0, 30.0))
        self.assertEqual(pose['distance'], 1234.0)

    def test_the_window_is_told_what_the_player_is_told(self):
        """Paused, the status line and the drag box reach the composed HUD, not just the legacy one.

        The window used to compose with `paused=False, message=''` unconditionally, so a paused
        match looked like a running one and the replay status line never appeared.
        """
        session = self.session
        session.publish(self.state, selection={1}, visible_ids=None)
        running = session.hud.overlay.copy()
        dirty_box = session.hud.drag_box
        session.publish(self.state, selection={1}, visible_ids=None, paused=True,
                        message="PAUSED 2.0s", drag_box=((10, 20), (300, 400)))
        self.assertTrue(session.hud.drag_box == ((10, 20), (300, 400)))
        self.assertNotEqual(dirty_box, session.hud.drag_box)
        paused_frame = session.hud.overlay.copy()
        changed = 0
        for y in range(0, paused_frame.get_height(), 4):
            for x in range(0, paused_frame.get_width(), 4):
                if paused_frame.get_at((x, y)) != running.get_at((x, y)):
                    changed += 1
        self.assertGreater(changed, 0, "the paused HUD looks identical to the running one")

    def test_close_is_idempotent(self):
        self.session.close()
        self.session.close()


if __name__ == '__main__':
    unittest.main()
