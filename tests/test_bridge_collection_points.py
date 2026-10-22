"""Issue #161: the collection point has to be visible in the window, not only in the panel.

The native window receives a teal diamond on the destination and the minimap paints its tether.
Both cues must follow station selection, not the lifetime of the saved collection point.

Two cues are pinned here: the diamond in the world (a four-segment flat ring, which puts a vertex on
each axis exactly like the legacy hand-built diamond) and, on the minimap, the diamond plus its tether.
"""
import tempfile
import unittest

from game.core.entity import Vec3
from game.core.manager import GameManager
from game.data.store import DataStore
from game.systems.collection_points import collection_capable
from render import asset_selection, menus, primitive_batch
from render.hud import COLLECTION, HUD
from render_bridge import markers as marker_codec, packed, ring
from render_bridge.live import LiveSession


class CollectionPointCueTests(unittest.TestCase):
    def setUp(self):
        previous = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous)
        self.addCleanup(asset_selection.configure, {})
        asset_selection.configure({'model_preview': True}, asset_root=menus.ASSET_ROOT)
        self.manager = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        self.state = self.manager.state
        self.stations = [e for e in self.state.entities.values()
                         if e.is_station and e.alive and collection_capable(e)]
        self.assertGreaterEqual(len(self.stations), 3, 'the skirmish should field buildable stations')
        self.station = next(e for e in self.stations if e.owner == 0)
        self.point = Vec3(self.station.pos.x + 900.0, 0.0, self.station.pos.z - 600.0)
        self.station.collection_point = self.point

    def radius_of(self, entity):
        return float(getattr(entity, 'radius', 40.0))

    def test_the_window_is_told_where_an_owned_station_sends_its_units(self):
        cues = primitive_batch.collection_point_cues(self.state, 0, {self.station.id})
        mine = [cue for cue in cues
                if (round(cue['centre'][0], 3), round(cue['centre'][2], 3))
                == (round(self.point.x, 3), round(self.point.z, 3))]
        self.assertEqual(len(mine), 1, 'the destination of an owned station drew no cue')
        cue = mine[0]
        self.assertEqual(cue['kind'], marker_codec.CIRCLE)
        self.assertEqual(cue['shape'], marker_codec.SHAPE_XZ, 'the marker must lie in the ecliptic')
        self.assertEqual(cue['segments'], 4, 'four segments of a flat ring is the legacy diamond')
        self.assertEqual(cue['colour'], (89, 242, 204, 242))
        self.assertFalse(cue['flags'] & marker_codec.FLAG_DEPTH, 'a destination is never occluded')

    def test_no_cue_without_a_point_and_none_for_a_foreign_station(self):
        enemy = next(e for e in self.stations if e.owner != 0)
        enemy.collection_point = Vec3(enemy.pos.x - 700.0, 0.0, enemy.pos.z + 400.0)
        bare = next(e for e in self.stations if e.owner == 0 and e.id != self.station.id)
        self.assertIsNone(bare.collection_point)
        cues = primitive_batch.collection_point_cues(
            self.state, 0, {self.station.id, bare.id, enemy.id, -999})
        self.assertEqual(len(cues), 1, f'expected one owned cue, got {len(cues)}')
        centres = {(round(c['centre'][0], 3), round(c['centre'][1], 3), round(c['centre'][2], 3))
                   for c in cues}
        self.assertNotIn((round(enemy.collection_point.x, 3), 0.0,
                          round(enemy.collection_point.z, 3)), centres)

    def test_the_cue_reaches_the_window_through_the_published_batch(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        session = LiveSession(self.state, self.manager.ds, directory=directory.name, local_player=0)
        self.addCleanup(session.close)
        session.publish(self.state, selection={self.station.id}, visible_ids=set(self.state.entities))
        with ring.Ring.open(session.paths['markers']) as reader:
            records = marker_codec.decode(reader.latest()[1])
        where = (round(self.point.x, 3), round(self.point.y, 3), round(self.point.z, 3))
        diamonds = [r for r in records
                    if r['kind'] == marker_codec.CIRCLE and r['segments'] == 4
                    and tuple(round(v, 3) for v in r['centre']) == where]
        self.assertEqual(len(diamonds), 1, 'the published batch carries no destination cue')
        self.assertEqual(diamonds[0]['colour'], (89, 242, 204, 242))

    def test_the_minimap_draws_the_diamond_and_its_tether(self):
        hud = HUD(1280, 800, self.state)
        self.addCleanup(hud.close)
        hud._minimap({self.station.id}, 0)
        rect = hud.minimap_rect
        half = max(1.0, getattr(self.state.map_info, 'bounds', 26000.0)) / 2.0

        def px(wx, wz):
            return (int(rect.centerx + wx / half * (rect.width / 2 - 4)),
                    int(rect.centery + wz / half * (rect.width / 2 - 4)))

        tip = px(self.point.x, self.point.z)
        self.assertEqual(tuple(hud.overlay.get_at((tip[0], tip[1] - 4)))[:3], COLLECTION,
                         'the diamond tip is not the collection tint')
        middle = px((self.station.pos.x + self.point.x) / 2.0,
                    (self.station.pos.z + self.point.z) / 2.0)
        painted = tuple(hud.overlay.get_at(middle))[:3]
        self.assertGreater(sum(painted), 0, 'the tether to the station was not drawn')


    def test_published_marker_follows_selection_without_clearing_saved_point(self):
        from game.net.replay import state_checksum
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        session = LiveSession(self.state, self.manager.ds, directory=directory.name, local_player=0)
        self.addCleanup(session.close)
        other = next(e for e in self.stations if e.owner == 0 and e.id != self.station.id)
        other.collection_point = Vec3(self.point.x + 500, 0, self.point.z + 500)
        ship = next(e for e in self.state.entities.values() if e.owner == 0 and e.is_ship)
        before = state_checksum(self.state)
        for selection, expected in [({self.station.id}, [self.point]),
                                    ({other.id}, [other.collection_point]),
                                    ({ship.id}, []), (set(), []),
                                    ({self.station.id, other.id}, [self.point, other.collection_point]),
                                    ({self.station.id}, [self.point])]:
            with self.subTest(selection=selection):
                session.publish(self.state, selection=selection, visible_ids=set(self.state.entities))
                with ring.Ring.open(session.paths['markers']) as reader:
                    records = marker_codec.decode(reader.latest()[1])
                diamonds = [r for r in records if r['kind'] == marker_codec.CIRCLE
                            and r['segments'] == 4]
                self.assertEqual(sorted(tuple(round(v, 3) for v in r['centre']) for r in diamonds),
                                 sorted((round(p.x, 3), round(p.y, 3), round(p.z, 3)) for p in expected))
                self.assertEqual(state_checksum(self.state), before)

    def test_minimap_hides_point_when_station_is_deselected_and_restores_it(self):
        import pygame
        hud = HUD(1280, 800, self.state)
        self.addCleanup(hud.close)
        other = next(e for e in self.stations if e.owner == 0 and e.id != self.station.id)
        # Compare the complete minimap with the same scene without this one point, so a station
        # icon or fog pixel cannot masquerade as the collection cue.
        for selection, visible in [({self.station.id}, True), ({other.id}, False),
                                   (set(), False), ({self.station.id}, True)]:
            with self.subTest(selection=selection):
                hud.overlay.fill((0, 0, 0, 0))
                hud._minimap(selection, 0)
                actual = pygame.image.tobytes(hud.overlay.subsurface(hud.minimap_rect), 'RGBA')
                self.station.collection_point = None
                try:
                    hud.overlay.fill((0, 0, 0, 0))
                    hud._minimap(selection, 0)
                    control = pygame.image.tobytes(hud.overlay.subsurface(hud.minimap_rect), 'RGBA')
                finally:
                    self.station.collection_point = self.point
                self.assertEqual(actual != control, visible)


if __name__ == '__main__':
    unittest.main()
