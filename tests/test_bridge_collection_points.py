"""Issue #161: the collection point has to be visible in the window, not only in the panel.

`render/renderer.py::_draw_collection_points` draws it for the Python renderer — a teal line from the
station and a diamond on the destination — but the native window never received anything to draw, so
on the default (`renderer: cpp`) path a player who right-clicked a command centre saw the coordinates
in the side panel and nothing in the world.

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
        cues = primitive_batch.collection_point_cues(self.state, 0)
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
        cues = primitive_batch.collection_point_cues(self.state, 0)
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
        session.publish(self.state, visible_ids=set(self.state.entities))
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
        hud._minimap(set(), 0)
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


if __name__ == '__main__':
    unittest.main()
