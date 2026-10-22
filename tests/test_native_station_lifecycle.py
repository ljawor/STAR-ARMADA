"""CPU-only paid construction → live records; never opens a GL/native window."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.construction import ConstructionSystem
from game.systems.unit_factory import UnitFactory
from render import asset_selection
from render.ship_sizes import ship_size
from render_bridge import collect, packed


class StationLifecycleTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.home() / '.hermes/cache/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='station-lifecycle-', dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        from render import menus
        for key, value in dict(USER_DIR=Path(self.tmp.name),
                SAVES_DIR=Path(self.tmp.name) / 'saves',
                SETTINGS_PATH=Path(self.tmp.name) / 'settings.json',
                CAMPAIGN_PATH=Path(self.tmp.name) / 'campaign.json',
                BALANCE_PATH=Path(self.tmp.name) / 'balance.json').items():
            owner = patch.object(menus, key, str(value))
            owner.start()
            self.addCleanup(owner.stop)
        original_store = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', original_store)
        DataStore.reset()
        self.st = GameState()
        self.st.players[0] = PlayerState(0, faction='rebel', credits=100000,
            materials=100000, energy=100000, crew=100000, command_capacity=100)
        self.factory = UnitFactory(self.st)
        self.ds = DataStore.get()
        self.builder = self.factory.spawn_ship('rebel_constructor', 0, Vec3())
        self.cs = ConstructionSystem(self.st)
        self.cs.factory = self.factory
        self.st._construction_system = self.cs
        names, weapons = collect.required_names(self.st, self.ds, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        self.tables = collect.build_tables(names, weapons)
        self.collector = collect.FrameCollector(self.ds, self.tables,
            asset_selection=asset_selection, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, local_player=0)

    def frame(self):
        buffer = bytearray(packed.frame_size(64, 64))
        data, stats = self.collector.collect_into(self.st, buffer, tick=self.st.tick, frame_index=0)
        return packed.unpack_frame(data, self.tables), stats

    def pay(self):
        before = self.st.players[0].credits
        self.assertTrue(self.cs.start_station(self.builder.id, 'trade_station', Vec3(), 0))
        self.assertLess(self.st.players[0].credits, before)

    def test_paid_station_created_after_tables_is_present_in_live_frame(self):
        self.pay()
        self.cs.update(self.builder.build_queue[0]['total'] + 1)
        station, = [e for e in self.st.entities.values() if e.is_station]
        before = self.st.to_dict(precise=True)
        frame, stats = self.frame()
        rows = [r for r in frame['instances'] if r['entity_id'] == station.id]
        self.assertEqual(len(rows), 1, stats)
        self.assertEqual(rows[0]['binding'], 'rebel:trade_station')
        self.assertEqual(rows[0]['flags'] & packed.FLAG_DYNAMIC_MESH, packed.FLAG_DYNAMIC_MESH)
        self.assertFalse(rows[0]['flags'] & packed.FLAG_SURFACE_FRAME)
        self.assertEqual(rows[0]['matrix'][9:12], list(station.pos.to_tuple()))
        self.assertEqual(before, self.st.to_dict(precise=True))

    def test_paid_site_grows_and_is_replaced_by_completed_hull(self):
        self.pay()
        before = self.st.to_dict(precise=True)
        early, _ = self.frame()
        sites = [r for r in early['instances'] if r['binding'] == 'shared:construction_scaffold']
        self.assertEqual(len(sites), 1, 'paid work has no construction visual')
        site = sites[0]
        self.assertEqual(site['entity_id'], 0x80000000 | self.builder.id)
        self.assertEqual(site['flags'], packed.FLAG_DYNAMIC_MESH)
        self.assertEqual(before, self.st.to_dict(precise=True))
        self.cs.update(self.builder.build_queue[0]['total'] / 2)
        later, _ = self.frame()
        grown, = [r for r in later['instances'] if r['binding'] == site['binding']]
        self.assertGreater(grown['matrix'][4], site['matrix'][4])
        self.assertEqual(grown['matrix'][0], site['matrix'][0])
        self.cs.update(self.builder.build_queue[0]['total'] + 1)
        done, _ = self.frame()
        self.assertNotIn(site['binding'], [r['binding'] for r in done['instances']])
        self.assertIn('rebel:trade_station', [r['binding'] for r in done['instances']])

    def test_paid_site_shows_the_hull_it_is_building_until_it_is_ready(self):
        """The half-built station is the station, not a mystery box: its own mesh, translucent.

        The legacy renderer drew the model itself while the constructor worked and left it transparent
        until the station was operational, so the player could see what was coming and how far along it
        was. Only the scaffold was ported, which is the frame around the site but not what is inside it.
        """
        self.pay()
        early, _ = self.frame()
        hulls = [r for r in early['instances'] if r['binding'] == 'rebel:trade_station']
        self.assertEqual(len(hulls), 1, 'the paid site must show the hull it is building')
        hull = hulls[0]
        self.assertEqual(hull['entity_id'], 0x90000000 | self.builder.id)
        self.assertEqual(hull['flags'], packed.FLAG_DYNAMIC_MESH)
        self.assertEqual(hull['matrix'][9:12], self.builder.build_queue[0]['pos'],
                         'the hull must stand on the site, not on the constructor')
        first_alpha = hull['tint'][3]
        self.assertGreater(first_alpha, 0.0, 'a fully transparent hull proves nothing')
        self.assertLess(first_alpha, 0.9, 'a site under construction must not read as finished')
        self.cs.update(self.builder.build_queue[0]['total'] / 2)
        later, _ = self.frame()
        half, = [r for r in later['instances'] if r['binding'] == 'rebel:trade_station']
        self.assertGreater(half['tint'][3], first_alpha, 'the hull must fill in as the work completes')
        self.assertLess(half['tint'][3], 0.95, 'still translucent until it is ready')
        self.cs.update(self.builder.build_queue[0]['total'] + 1)
        done, _ = self.frame()
        ready, = [r for r in done['instances'] if r['binding'] == 'rebel:trade_station']
        self.assertEqual(ready['tint'][3], 1.0, 'the finished station is opaque')
        self.assertNotEqual(ready['entity_id'], hull['entity_id'],
                            'the real entity replaces the render-only site row')

    def test_live_session_transports_scaffold_and_hull_without_catalogue(self):
        from render_bridge.live import LiveSession
        from render_bridge import hardware, ring
        session = LiveSession(self.st, self.ds, directory=Path(self.tmp.name) / 'rings',
                              size=(320, 200), planet_texture=16)
        self.addCleanup(session.close)
        self.pay()
        session.publish(self.st, visible_ids={self.builder.id})
        self.assertIn('hardware', session.paths, 'no live mesh channel')
        reader = ring.Ring.open(session.paths['hardware'])
        self.addCleanup(reader.close)
        published = reader.published
        meshes = {}
        for index in range(published):
            record = hardware.decode(reader.read(index)[1])
            meshes[record['name']] = record
        self.assertIn('shared:construction_scaffold', meshes)
        # The site draws the station it is building, so that mesh has to travel while it is being built -
        # not only once the station exists.
        self.assertIn('rebel:trade_station', meshes,
                      'the hull on the site never reached the mesh ring')
        session.publish(self.st, visible_ids={self.builder.id})
        self.assertEqual(reader.published, published, 'unchanged mesh uploaded again')
        self.cs.update(self.builder.build_queue[0]['total'] + 1)
        station, = [e for e in self.st.entities.values() if e.is_station]
        session.publish(self.st, visible_ids={self.builder.id, station.id})
        self.assertEqual(reader.published, published,
                         'completion must reuse the hull already sent for the site')
        hull = meshes['rebel:trade_station']
        from render.fleet_geometry import station_mesh
        self.assertEqual(hull['triangles'], sum(map(len, station_mesh('trade_station', 'rebel').values())))
        frame_reader = ring.Ring.open(session.paths['frame'])
        self.addCleanup(frame_reader.close)
        frame = packed.unpack_frame(frame_reader.latest()[1], session.tables)
        self.assertIn(hull['name'], [r['binding'] for r in frame['instances']])


if __name__ == '__main__':
    unittest.main()
