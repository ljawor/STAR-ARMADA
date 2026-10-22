"""Units built after session startup must not be omitted from native frame tables."""
import unittest
from pathlib import Path
import test_native_station_lifecycle as station_fixture
from game.core.vectors import Vec3
from render import asset_selection
from render.ship_sizes import ship_size
from render_bridge import collect, packed


class LateUnitTests(unittest.TestCase):
    def setUp(self):
        from tools.render.dump_snapshot import _default_selection
        root = Path(__file__).resolve().parents[1]
        previous = asset_selection.selection_preferences(asset_selection._selection)
        self.addCleanup(asset_selection.configure, previous, asset_root=root, pack_root=root / 'visual_packs')
        asset_selection.configure(_default_selection(), asset_root=root, pack_root=root / 'visual_packs')
        self.fixture = station_fixture.StationLifecycleTests('test_paid_station_created_after_tables_is_present_in_live_frame')
        self.fixture.faction = 'imperial'
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_paid_colonial_outreach_built_after_startup_is_in_native_frame(self):
        f = self.fixture
        yard = f.factory.spawn_station('command_station', 0, Vec3())
        yard.upgrade_level = 4
        before = f.st.players[0].credits
        # Build the player's own faction hull: `type_can_build_ship` refuses another
        # faction's catalogue row, and this fixture's player is not the faction the
        # case name suggests.
        faction = f.st.players[0].faction
        ship_id = f'{faction}_colonizer'
        self.assertTrue(f.cs.start_ship(yard.id, ship_id, 0))
        self.assertLess(f.st.players[0].credits, before)
        f.cs.update(yard.build_queue[0]['total'] + 1)
        colony, = [e for e in f.st.entities.values() if e.data_id == ship_id]
        frame, stats = f.frame()
        rows = [r for r in frame['instances'] if r['entity_id'] == colony.id]
        self.assertEqual(len(rows), 1, ('Colonial Outreach Frigate completed but has no native hull record', stats))
        self.assertEqual(rows[0]['binding'], f'{faction}:colonizer')
        self.assertEqual(stats['unknown_bindings'], [])

    def test_startup_tables_cover_every_data_ship_before_it_exists(self):
        f = self.fixture
        names, weapons = collect.required_names(f.st, f.ds, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        for ship_id, data in f.ds.ships.items():
            with self.subTest(ship=ship_id):
                binding = asset_selection.ship_binding(f.ds, ship_id, data.faction)
                self.assertIsNotNone(binding)
                self.assertIn(binding, names, 'Future unit type missing from session-long table')
        self.assertTrue(set(f.ds.weapons).issubset(weapons), 'Future ships must retain their weapon effect bindings')


if __name__ == '__main__':
    unittest.main()
