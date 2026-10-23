"""The first style check covers both ship and station using normal native framing."""
import unittest
from tools.art.build_alliance_redesign import ROWS
from tools.render.verify_alliance_redesign import camera_plan, LIVE_IDS, PACK_NAME

class AllianceRedesignCaptureTests(unittest.TestCase):
    def test_representative_rows_are_actual_alliance_factory_ids(self):
        self.assertEqual(len(ROWS),26)
        self.assertTrue({'frigate','shipyard'}.issubset({row[0] for row in ROWS}))
        self.assertEqual(LIVE_IDS['frigate'],'rebel_frigate')
        self.assertEqual(LIVE_IDS['shipyard'],'shipyard')
        self.assertEqual(LIVE_IDS['convoy'],'rebel_crew_transport')
        self.assertEqual(PACK_NAME,'alliance-redesign')

    def test_station_snapshot_uses_production_owner_faction_binding(self):
        from tools.render.verify_alliance_redesign import subject_snapshot
        from game.graphics_benchmark import make_fixture
        from game.core.vectors import Vec3
        fixture=make_fixture('four-player-close-v1')
        fixture.manager.state.entities.clear()
        fixture.manager.state.players[0].faction='rebel'
        fixture.manager.factory.spawn_station('shipyard',0,Vec3())
        payload=subject_snapshot(fixture)
        self.assertEqual([r['binding'] for r in payload['instances']],['rebel:shipyard'])
        self.assertEqual([r['binding'] for r in payload['assets']],['rebel:shipyard'])
        self.assertIn('alliance_shipyard',payload['assets'][0]['path'])
        self.assertEqual(payload['metadata']['factions'][0],'rebel')
        self.assertNotIn('combat_mix_per_player',payload['metadata'])
        self.assertTrue(all('Imperial' not in line for line in payload['metadata']['assumptions']))

    def test_paired_views_are_heading_relative_and_tactical_is_farther(self):
        views=camera_plan(length=100,center=[0,10,0],heading_degrees=90)
        self.assertEqual(set(views),{'close','rear','tactical'})
        self.assertEqual(views['close']['yaw'],138)
        self.assertEqual(views['rear']['yaw'],310)
        self.assertGreater(views['tactical']['distance'],views['close']['distance'])
        self.assertTrue(all(view['target']==[0,10,0] for view in views.values()))

if __name__=='__main__':unittest.main()
