"""Issue #162: a hull in hyperspace has no hull, glow or cue in the world view — for anyone.

`render/renderer.py` (the legacy path) has always dropped travelling hulls from its one visibility
list. The native bridge never did, so the default renderer kept drawing the ship while it crossed
the map; and because `state.can_see` answers True for the owner regardless of transit, the owner saw
their own hull sitting in the corridor. The minimap must keep tracking it, which is why the fix is a
renderer gate and not a simulation one.
"""
import tempfile
import unittest

from game.core.manager import GameManager
from game.data.store import DataStore
from render import asset_selection, menus
from render.hud import HUD
from render_bridge import markers as marker_codec, packed, ring
from render_bridge.live import LiveSession


class HyperjumpVisibilityTests(unittest.TestCase):
    def setUp(self):
        previous = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous)
        # The shipped default draws the authored catalogue; without a resolver the collector
        # cannot name a ship binding at all and every hull would be missing for the wrong reason.
        self.addCleanup(asset_selection.configure, {})
        asset_selection.configure({'model_preview': True}, asset_root=menus.ASSET_ROOT)
        self.manager = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        state = self.manager.state
        self.everything = set(state.entities)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.session = LiveSession(state, self.manager.ds, directory=self.directory.name,
                                   local_player=0)
        self.addCleanup(self.session.close)

    def instances(self):
        with ring.Ring.open(self.session.paths['frame']) as reader:
            return packed.unpack_frame(reader.latest()[1], self.session.tables)['instances']

    def frame_ids(self):
        self.session.publish(self.manager.state, visible_ids=self.everything)
        return {record['entity_id'] for record in self.instances()}

    def own_ships_in_frame(self):
        """Two of this player's hulls that the baseline frame really draws."""
        drawn = self.frame_ids()
        return [entity for entity in sorted(self.manager.state.entities.values(), key=lambda e: e.id)
                if entity.alive and entity.is_ship and entity.owner == 0
                and entity.id in drawn][:2]

    def test_the_frame_carries_no_instance_for_a_travelling_hull(self):
        traveller, sibling = self.own_ships_in_frame()
        traveller.jump_travelling = True
        traveller.jump_charge = 3.0
        ids = self.frame_ids()
        self.assertNotIn(traveller.id, ids,
                         'the hull is still published to the window while in hyperspace')
        self.assertIn(sibling.id, ids, 'the gate must not remove the rest of the fleet')

    def test_no_ownership_cue_is_left_hanging_where_the_hull_is_not(self):
        traveller = self.own_ships_in_frame()[0]
        traveller.jump_travelling = True
        traveller.jump_charge = 3.0
        self.session.publish(self.manager.state, visible_ids=self.everything)
        with ring.Ring.open(self.session.paths['markers']) as reader:
            records = marker_codec.decode(reader.latest()[1])
        centres = {(round(r['centre'][0], 3), round(r['centre'][1], 3), round(r['centre'][2], 3))
                   for r in records}
        where = (round(traveller.pos.x, 3), round(traveller.pos.y, 3),
                 round(traveller.pos.z, 3))
        self.assertNotIn(where, centres, 'a chevron over empty space is a marker for nothing')

    def test_the_minimap_keeps_tracking_the_travelling_contact(self):
        state = self.manager.state
        hud = HUD(1280, 800, state)
        self.addCleanup(hud.close)
        traveller = self.own_ships_in_frame()[0]
        traveller.jump_travelling = True
        traveller.jump_charge = 3.0
        hud._minimap(set(), 0)
        rect = hud.minimap_rect
        half = max(1.0, getattr(state.map_info, 'bounds', 26000.0)) / 2.0
        x = int(rect.centerx + traveller.pos.x / half * (rect.width / 2 - 4))
        y = int(rect.centery + traveller.pos.z / half * (rect.width / 2 - 4))
        painted = hud.overlay.get_at((x, y))
        expected = state.players[0].color
        self.assertGreater(painted.a, 0, 'nothing was drawn at the contact')
        self.assertLessEqual(
            max(abs(painted[i] - round(expected[i] * 255)) for i in range(3)), 6,
            f'minimap blip {tuple(painted)} is not the owner colour {tuple(expected)}')


if __name__ == '__main__':
    unittest.main()
