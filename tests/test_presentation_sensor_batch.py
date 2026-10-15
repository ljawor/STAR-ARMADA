"""Read-only presentation scopes must not weaken live simulation sensing."""
import unittest
from unittest.mock import patch

import helpers
from game.core.entity import Entity
from game.core.state import PlayerState
from game.core.vectors import Vec3
from game.systems import visibility
from game.systems.stats import effective_sensor_range


class TestPresentationSensorBatch(unittest.TestCase):
    def setUp(self):
        self.gm = helpers.make_game(ai=False)
        self.st = self.gm.state
        self.st.entities.clear()
        self.st.players = {i: PlayerState(i, team=i % 2) for i in range(4)}

    def unit(self, eid, owner, x=0, sensor=1000, kind="ship"):
        e = Entity(eid, kind, owner, "test", pos=Vec3(x, 0, 0),
                   is_ship=kind == "ship", is_station=kind == "station",
                   is_squadron=kind == "squadron", is_planet=kind == "planet",
                   sensor_range=sensor, crew=10, max_crew=10)
        return self.st.add_entity(e)

    def scope(self):
        factory = getattr(visibility, "presentation_sensor_batch", None)
        self.assertTrue(callable(factory), "explicit read-only presentation scope is missing")
        return factory(self.st)

    def test_repeated_queries_compute_each_requested_source_radius_once(self):
        for i in range(12):
            self.unit(i + 1, i % 4, x=i * 3000)
        # Misses force the original path to examine every allied observer.
        positions = [Vec3(100000 + i, i, 0) for i in range(40)]
        original = self.st._sensor_queries
        with patch("game.systems.stats.effective_sensor_range",
                   wraps=effective_sensor_range) as ranges, patch.object(
                       Entity, "sensor_multiplier", autospec=True,
                       side_effect=Entity.sensor_multiplier) as signatures:
            with self.scope():
                for pos in positions:
                    self.assertFalse(self.st.is_position_visible(0, pos))
                    self.assertEqual(len(self.st.sensor_sources(0)), 6)
                self.assertEqual(ranges.call_count, 6)
                # A second allied viewer shares already captured radii.
                self.assertFalse(self.st.is_position_visible(2, positions[0]))
                self.assertEqual(ranges.call_count, 6)
                self.assertFalse(self.st.is_position_visible(1, positions[0]))
                self.assertEqual(ranges.call_count, 12)
                self.assertEqual(signatures.call_count, 12)
        self.assertIs(self.st._sensor_queries, original)

    def test_four_player_contacts_fog_effects_and_memory_match_live_exactly(self):
        import pygame
        from render.fog import FogMask, effect_visible, known_entities
        for i in range(4):
            self.unit(10 + i, i, i * 2300, kind=("station" if i % 2 else "ship"))
            self.unit(20 + i, i, i * 2300 + 700, kind="squadron")
        planet = self.unit(30, -1, 19000, sensor=0, kind="planet")
        planet.data_id = "temperate"
        planet.colonized_by = 2
        self.st.discovered_planets = {0: {30: self.st.planet_snapshot(planet)}}
        self.st.explored_cells = {i: {(i, 0), (i, 1)} for i in range(4)}
        points = [Vec3(x, y, z) for x, y, z in (
            (0, 0, 0), (1000, 0, 0), (1000, .000001, 0),
            (0, 600, 800), (999.999999999, 0, 0), (1000.000000001, 0, 0),
            (2300, 0, 0), (19000, 0, 0), (100000, 0, 0))]
        effects = [{"pos": p.to_dict(True)} for p in points]
        effects += [{"pos": [0, 0, 0], "target_pos": [1000, 0, 0]},
                    {"pos": [0, 0, 0], "target_pos": [4600, 0, 0]}]

        def observations():
            result = []
            for pid in (0, 1, 2, 3, 999):
                known = tuple((e.id, e.owner, e.colonized_by, e.name_override,
                               e.pos.x, e.pos.y, e.pos.z)
                              for e in known_entities(self.st, pid))
                result.append((tuple(self.st.can_see(pid, eid) for eid in self.st.entities),
                               tuple(self.st.is_position_visible(pid, p) for p in points),
                               tuple(effect_visible(self.st, pid, fx) for fx in effects),
                               tuple((e.id, r) for e, r in self.st.sensor_sources(pid)),
                               known,
                               pygame.image.tobytes(FogMask().surface(self.st, pid), "RGBA")))
            return result

        expected = observations()
        saved = self.st.to_dict(precise=True)
        with self.scope():
            self.assertEqual(observations(), expected)
            self.assertEqual(observations(), expected)
            self.assertEqual(self.st.to_dict(precise=True), saved)
        self.assertEqual(self.st.to_dict(precise=True), saved)

    def test_scopes_refresh_all_same_tick_dependencies_and_live_queries_stay_live(self):
        from game.core.world import Fleet
        source = self.gm.factory.spawn_ship("imperial_corvette", 0, Vec3())
        target = self.unit(1000, 1, 1000, sensor=0)
        tech = next(t for t in self.gm.ds.techs.values()
                    if t.effects.get("sensor_range_mult", 1) > 1)
        self.st.fleets[1] = Fleet(id=1, owner=0, name="Sensors", commander="scout")
        # Copy only this test's rule subtree; never mutate the shared loaded rule.
        from copy import deepcopy
        self.gm.ds.rules = deepcopy(self.gm.ds.rules)
        self.gm.ds.rules.setdefault("commanders", {})["scout"] = {"sensor_range": .5}
        tick = self.st.tick

        def check():
            radius = effective_sensor_range(self.st, source)
            points = [Vec3(source.pos.x + x, source.pos.y + y, source.pos.z + z)
                      for x, y, z in ((radius, 0, 0), (radius + .000001, 0, 0),
                                      (0, radius * .6, radius * .8), (500, 0, 0))]
            expected_sources = self.st.sensor_sources(0)
            expected = [self.st.is_position_visible(0, p) for p in points]
            contacts = []
            for p in points:
                target.pos = p
                contacts.append(self.st.can_see(0, target.id))
            with self.scope():
                self.assertEqual(self.st.sensor_sources(0), expected_sources)
                self.assertEqual([self.st.is_position_visible(0, p) for p in points], expected)
                # Targets are fixed during each scope, just as in rendering.
                self.assertEqual(self.st.can_see(0, target.id), contacts[-1])
            self.assertEqual(self.st.tick, tick)

        mutations = [
            lambda: setattr(source.systems["sensors"], "hp", 0),
            lambda: setattr(source.systems["sensors"], "hp", 100),
            lambda: setattr(source.systems["sensors"], "max_hp", 200),
            lambda: setattr(source.systems["sensors"], "max_hp", 100),
            lambda: setattr(source.systems["life_support"], "hp", 0),
            lambda: setattr(source.systems["life_support"], "hp", 100),
            lambda: setattr(source, "alive", False),
            lambda: setattr(source, "alive", True),
            lambda: setattr(source, "crew", 0),
            lambda: setattr(source, "crew", 1),
            lambda: setattr(source, "max_crew", 100),
            lambda: setattr(source, "crew", 100),
            lambda: setattr(source, "sensor_range", 1234.56789),
            lambda: setattr(source, "xp", 100000),
            lambda: self.st.players[0].researched.add(tech.id),
            lambda: self.st.players[0].researched.clear(),
            lambda: setattr(source, "fleet_id", 1),
            lambda: setattr(self.st.fleets[1], "commander", None),
            lambda: source.ability_active.update(sensor_jammed=.1),
            lambda: source.ability_active.clear(),
            lambda: setattr(self.st.map_info, "nebulas", [{"pos": [0, 0, 0], "radius": 100}]),
            lambda: self.st.map_info.nebulas[0].update(radius=0),
            lambda: setattr(source.pos, "y", 1),
            lambda: setattr(source, "owner", 2),
            lambda: setattr(self.st.players[2], "team", 7),
            lambda: setattr(self.st.players[0], "team", 7),
            lambda: setattr(source, "jump_travelling", True),
            lambda: setattr(source, "jump_travelling", False),
            lambda: self.st.entities.pop(source.id),
            lambda: self.st.entities.update({source.id: source}),
            lambda: self.unit(2000, 0, x=500, sensor=2000),
            lambda: setattr(source.pos, "x", 10000),
        ]
        check()
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                mutate()
                check()

    def test_colony_policy_updates_between_scopes_without_exploring_hidden_changes(self):
        planet = self.unit(1, -1, 19000, sensor=0, kind="planet")
        planet.data_id = "temperate"
        tick = self.st.tick
        for owner, expected in ((None, False), (2, True), (1, False), (0, True)):
            planet.colonized_by = owner
            self.assertEqual(self.st.can_see(0, planet.id), expected)
            with self.scope():
                self.assertEqual(self.st.can_see(0, planet.id), expected)
                self.assertFalse(self.st.is_position_visible(0, planet.pos))
            self.assertEqual(self.st.tick, tick)

    def test_nested_scopes_share_snapshot_and_restore_after_exceptions(self):
        self.unit(1, 0)
        self.st.is_position_visible(0, Vec3())
        original = self.st._sensor_queries
        saved = self.st.to_dict(precise=True)
        with self.scope():
            batch = self.st._sensor_queries
            with self.assertRaisesRegex(ValueError, "inner"):
                with self.scope():
                    self.assertIs(self.st._sensor_queries, batch)
                    self.assertTrue(self.st.is_position_visible(0, Vec3()))
                    raise ValueError("inner")
            self.assertIs(self.st._sensor_queries, batch)
            self.assertTrue(self.st.is_position_visible(0, Vec3()))
        self.assertIs(self.st._sensor_queries, original)
        with self.assertRaisesRegex(ValueError, "outer"):
            with self.scope():
                raise ValueError("outer")
        self.assertIs(self.st._sensor_queries, original)
        self.assertEqual(self.st.to_dict(precise=True), saved)
        self.st._sensor_queries = None
        with self.assertRaisesRegex(ValueError, "uninitialized"):
            with self.scope():
                self.assertTrue(self.st.is_position_visible(0, Vec3()))
                raise ValueError("uninitialized")
        self.assertIsNone(self.st._sensor_queries)
        self.st.entities[1].sensor_range = 0
        self.assertFalse(self.st.is_position_visible(0, Vec3()))

    def test_renderer_and_hud_public_entrypoints_scope_their_bodies(self):
        from render.renderer import Renderer
        from render.hud import HUD
        self.unit(1, 0)
        point = Vec3(100000, 0, 0)
        original = self.st._sensor_queries
        for cls, entry, body, args in (
                (Renderer, "draw", "_draw_read_only", (.125, {1}, 7)),
                (HUD, "render", "_render_read_only", ({1}, 7, 0, True, "msg", 2., 60.))):
            with self.subTest(entry=entry):
                self.assertTrue(callable(getattr(cls, body, None)),
                                "presentation entrypoint needs a scoped body")
                obj = object.__new__(cls)
                obj.state = self.st

                def probe(*forwarded):
                    self.assertEqual(forwarded, args)
                    self.assertIsNot(self.st._sensor_queries, original)
                    for _ in range(10):
                        self.assertFalse(self.st.is_position_visible(0, point))
                    raise RuntimeError("render failed")

                with patch.object(obj, body, side_effect=probe), patch(
                        "game.systems.stats.effective_sensor_range",
                        wraps=effective_sensor_range) as ranges:
                    with self.assertRaisesRegex(RuntimeError, "render failed"):
                        getattr(obj, entry)(*args)
                    self.assertEqual(ranges.call_count, 1)
                self.assertIs(self.st._sensor_queries, original)


if __name__ == "__main__":
    unittest.main()
