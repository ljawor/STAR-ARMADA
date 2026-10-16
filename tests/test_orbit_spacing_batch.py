"""Caller-local terrain reuse: operation counts and explicit pre-change oracles."""
import builtins
import copy
import json
import unittest
from unittest.mock import patch

from game.core import detmath as math
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.systems.colonies import colony_rules, SATELLITE_TYPES
from game.systems.construction import ConstructionSystem
from game.systems.unit_factory import UnitFactory
from game.systems import satellite_orbits as orbits


# Explicit legacy implementations; do not delegate input assembly or spacing to
# the candidate. Only the unchanged numeric terrain solver remains shared.
def legacy_geometry(state, planet, station_radius, slot):
    """Public fixed terrain determines safe rings, never hidden contacts.

    Keep normal rings where the entire circle fits. Crowded planets use
    near-polar planes normal to neighbouring bodies, not a smaller keep-out.
    A shared small shell offset preserves separation between every slot.
    The cache is derived geometry only, excluded from save/replay state.
    """
    cfg = colony_rules()
    from game.data.store import DataStore
    hulls = (station_radius, *(DataStore.get().stations[k].radius for k in SATELLITE_TYPES))
    if (any(type(r) not in (int, float) or not math.isfinite(r) or r <= 0 for r in hulls)
            or type(cfg['satellite_cap']) is not int or not 1 <= cfg['satellite_cap'] <= 64
            or any(type(cfg[k]) not in (int, float) or not math.isfinite(cfg[k]) or cfg[k] <= 0
                   for k in ('orbit_clearance', 'orbit_shell_spacing', 'orbit_inclination'))
            or cfg['orbit_inclination'] > math.pi):
        return None
    shell_radius = max(hulls)
    # Distinct planes cross, so radial shell gaps must protect the largest
    # modded hull pair. Never weaken spacing or rescale a mod's hardware.
    if cfg['satellite_cap'] > 1 and cfg['orbit_shell_spacing'] < 3.2 * shell_radius + .001:
        return None
    # Filter first: ID order of relevant terrain is unchanged, while the often
    # much larger fleet never enters this repeated terrain sort/cache key.
    terrain = sorted((e for e in state.entities.values()
                      if e.alive and e.is_planet and e is not planet
                      and e.data_id != 'asteroid_field'), key=lambda e: e.id)
    bodies = tuple((e.id, e.pos.x, e.pos.y, e.pos.z, e.radius)
                   for e in terrain)
    plans = orbits._terrain_plans(planet.id, planet.pos.to_tuple(), planet.radius, shell_radius,
                           tuple(sorted(cfg.items())), bodies, state.map_info.bounds)
    return plans[slot] if plans is not None and 0 <= slot < len(plans) else None

def legacy_spacing(self, station_id, pos, player_id, *, viewer=None,
                           ignore_work=None, ignore_entity=None) -> tuple[bool, str]:
    st = self.state
    coords = (pos.x, pos.y, pos.z) if hasattr(pos, 'x') else pos
    if not all(math.isfinite(v) for v in coords):
        return False, 'invalid site coordinates'
    if abs(coords[0]) > st.map_info.bounds or abs(coords[2]) > st.map_info.bounds:
        return False, 'outside the map bounds'
    for e in st.entities.values():
        if not e.alive or e is ignore_entity:
            continue
        if e.is_station and (viewer is None or st.can_see(viewer, e.id)):
            minimum = self.station_min_distance(station_id, e.data_id, e.radius, player_id, e.owner)
            distance = math.dist(coords, (e.pos.x, e.pos.y, e.pos.z))
            if e.satellite_slot is not None and e.planet_id is not None:
                orbit_geometry, ring_distance = legacy_geometry, orbits.ring_distance
                parent = st.entity(e.planet_id)
                if parent is not None:
                    plan = orbit_geometry(st, parent, e.radius, e.satellite_slot)
                    if plan is not None:
                        distance = min(distance, ring_distance(parent.pos, *plan, Vec3(*coords)))
            if distance < minimum:
                if e.data_id == 'command_station' and st.is_enemy(player_id, e.owner):
                    return False, 'too close to hostile command station'
                return False, f"too close to {e.data_id.replace('_', ' ')}"
        # Placement shares allied paid reservations, not arbitrary detected
        # production details. Planet terrain owner remains neutral: control
        # AND the paid source must authorize this particular reservation.
        queue_owner = e.colonized_by if e.is_planet else e.owner
        allies = st.allied_player_ids(viewer) if viewer is not None else None
        if allies is not None and queue_owner not in allies:
            continue
        for work in e.build_queue:
            if (allies is not None and e.is_planet
                    and (work.get('source_owner') != queue_owner
                         or work.get('source_owner') not in allies)):
                continue
            if (work is ignore_work or work.get('kind') not in ('station', 'satellite')
                    or work.get('status') != 'paid' or work.get('pos') is None):
                continue
            other = self.ds.stations.get(work.get('item'))
            if other is None:
                continue
            # Only live command centers impose territorial exclusion;
            # queued hardware reserves its physical footprint/market spacing.
            minimum = self.station_min_distance(station_id, other.id, other.radius, player_id)
            distance = math.dist(coords, work['pos'])
            if work['kind'] == 'satellite' and e.is_planet and type(work.get('slot')) is int:
                orbit_geometry, ring_distance = legacy_geometry, orbits.ring_distance
                plan = orbit_geometry(st, e, other.radius, work['slot'])
                if plan is not None:
                    distance = min(distance, ring_distance(e.pos, *plan, Vec3(*coords)))
            if distance < minimum:
                return False, f"too close to {other.id.replace('_', ' ')} site"
    return True, ''


class CountingEntities(dict):
    def __init__(self, entities):
        super().__init__(entities)
        self.scans = 0

    def values(self):
        self.scans += 1
        return super().values()


class OrbitSpacingBatchTests(unittest.TestCase):
    def setUp(self):
        DataStore.reset()
        self.addCleanup(DataStore.reset)
        self.st = GameState()
        self.st.map_info.bounds = 20000
        self.st.players[0] = PlayerState(0)
        self.st.players[1] = PlayerState(1)
        self.factory = UnitFactory(self.st)
        self.cs = ConstructionSystem(self.st)
        self.planets, self.satellites = [], []
        for x in (-5000, 5000):
            planet = self.factory.spawn_planet(dict(id='test', type='temperate',
                                                    pos=[x, 0, 0], radius=600))
            planet.colonized_by = 0
            self.planets.append(planet)
            for slot in (0, 1):
                sat = self.factory.spawn_station('attack_satellite', 0, Vec3(x, 5000, slot * 500))
                sat.planet_id, sat.satellite_slot = planet.id, slot
                self.satellites.append(sat)
            planet.build_queue.append(dict(kind='satellite', item='defense_satellite',
                status='paid', pos=[x, -5000, 0], slot=2, source_owner=0))
        self.far = Vec3(0, 15000, 0)

    def counted_spacing(self, spacing):
        self.st.entities = CountingEntities(self.st.entities)
        sizes = []
        def measured_sorted(values, *args, **kwargs):
            values = list(values)
            if kwargs.get('key') is not None:
                sizes.append(len(values))
            return builtins.sorted(values, *args, **kwargs)
        with patch.object(orbits, 'sorted', side_effect=measured_sorted, create=True), \
                patch(__name__ + '.sorted', side_effect=measured_sorted, create=True):
            result = spacing(self.cs, 'mining_station', self.far, 0)
        return result, self.st.entities.scans, sizes

    def test_active_and_paid_satellites_assemble_terrain_once_per_spacing_call(self):
        for _ in range(2):
            result, scans, sizes = self.counted_spacing(ConstructionSystem._check_station_spacing)
            self.assertEqual(result, (True, ''))
            self.assertEqual(scans, 2, 'one entity loop plus one lazy terrain assembly')
            self.assertEqual(sizes, [2], 'sort eligible terrain once, including parents')

    def test_negative_control_legacy_reassembles_for_every_active_and_paid_satellite(self):
        result, scans, sizes = self.counted_spacing(legacy_spacing)
        self.assertEqual(result, (True, ''))
        self.assertEqual(scans, 7)
        self.assertEqual(sizes, [1] * 6)

    def state_bytes(self):
        return json.dumps(self.st.to_dict(precise=True), sort_keys=True)

    @staticmethod
    def outcome(query):
        try:
            return ('result', query())
        except Exception as exc:
            return ('exception', type(exc), str(exc))

    def assert_spacing_matches(self, pos=None, **kwargs):
        """Compare results AND every exact terrain-solver key, without stubs."""
        if pos is None:
            pos = self.far
        before = self.state_bytes()
        solver = orbits._terrain_plans
        with patch.object(orbits, '_terrain_plans', wraps=solver) as calls:
            expected = legacy_spacing(self.cs, 'mining_station', pos, 0, **kwargs)
            expected_keys = [c.args for c in calls.call_args_list]
            calls.reset_mock()
            actual = self.cs._check_station_spacing('mining_station', pos, 0, **kwargs)
            actual_keys = [c.args for c in calls.call_args_list]
        self.assertEqual(actual, expected)
        # JSON also gives stable comparisons for retained nonfinite legacy inputs.
        self.assertEqual(json.dumps(actual_keys), json.dumps(expected_keys))
        self.assertEqual(self.state_bytes(), before, 'validation must not mutate simulation state')
        return actual

    def assert_geometry_matches(self, planet, radius, slot, inputs):
        solver = orbits._terrain_plans
        with patch.object(orbits, '_terrain_plans', wraps=solver) as calls:
            expected = self.outcome(lambda: legacy_geometry(self.st, planet, radius, slot))
            expected_keys = [c.args for c in calls.call_args_list]
            calls.reset_mock()
            actual = self.outcome(lambda: orbits._orbit_geometry(self.st, planet, radius, slot, inputs))
            self.assertEqual(json.dumps([c.args for c in calls.call_args_list]), json.dumps(expected_keys))
        self.assertEqual(actual, expected)
        self.assertEqual(self.outcome(lambda: orbits.orbit_geometry(self.st, planet, radius, slot)), expected)

    def test_exact_legacy_geometry_for_every_parent_and_slot(self):
        inputs = orbits._OrbitTerrainInputs()
        before = self.state_bytes()
        for parent in self.planets:
            for radius in (30, 45., 49.):
                for slot in (*range(colony_rules()['satellite_cap']), -1, 6, True, .5, '0'):
                    with self.subTest(parent=parent.id, radius=radius, slot=slot):
                        self.assert_geometry_matches(parent, radius, slot, inputs)
        self.assertEqual(self.state_bytes(), before)

    def test_malformed_cfg_and_hulls_retain_validation_before_terrain_capture(self):
        cfg = self.cs.ds.rules.setdefault('colonies', {})
        original = copy.deepcopy(cfg)
        cases = [('satellite_cap', v) for v in (False, 0, 65, 2., '6')]
        cases += [(key, v) for key in ('orbit_clearance', 'orbit_shell_spacing', 'orbit_inclination')
                  for v in (False, 0, -1., 'x', float('nan'), float('inf'))]
        cases += [('orbit_inclination', math.pi + .1), ('orbit_shell_spacing', 100.)]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                cfg.clear(); cfg.update(original); cfg[key] = value
                inputs = orbits._OrbitTerrainInputs()
                self.assert_geometry_matches(self.planets[0], 45, 0, inputs)
                self.assertIsNone(inputs._terrain)
                self.assert_spacing_matches()
        cfg.clear(); cfg.update(original)
        for radius in (False, 0, -1, '45', float('nan'), float('inf')):
            with self.subTest(radius=radius):
                inputs = orbits._OrbitTerrainInputs()
                self.assert_geometry_matches(self.planets[0], radius, 0, inputs)
                self.assertIsNone(inputs._terrain)
        for kind in SATELLITE_TYPES:
            hull = self.cs.ds.stations[kind]
            old_radius = hull.radius
            for value in (False, '45', -1, float('nan'), 100):
                with self.subTest(hull=kind, value=value):
                    hull.radius = value
                    self.assert_geometry_matches(self.planets[0], 45, 0, orbits._OrbitTerrainInputs())
            hull.radius = old_radius

    def test_malformed_parent_radius_and_bounds_keep_legacy_outcomes(self):
        parent = self.planets[0]
        radius, bounds = parent.radius, self.st.map_info.bounds
        for value in (0, -600, float('nan'), float('inf'), '600', None):
            with self.subTest(parent_radius=value):
                parent.radius = value
                self.assert_geometry_matches(parent, 45, 0, orbits._OrbitTerrainInputs())
        parent.radius = radius
        for value in (0, -1, 5500, float('nan'), float('inf'), '20000', None):
            with self.subTest(bounds=value):
                self.st.map_info.bounds = value
                self.assert_geometry_matches(parent, 45, 0, orbits._OrbitTerrainInputs())
        self.st.map_info.bounds = bounds

    def test_duplicate_ids_exclude_only_parent_object_and_keep_stable_sort_order(self):
        first, second = self.planets
        second.id = first.id
        duplicate = copy.deepcopy(second)
        duplicate.pos.z += 37
        # Distinct dictionary keys intentionally model duplicate mutable entity IDs.
        self.st.entities[90001] = duplicate
        for reverse in (False, True):
            if reverse:
                self.st.entities = dict(reversed(tuple(self.st.entities.items())))
            inputs = orbits._OrbitTerrainInputs()
            for parent in (first, second, duplicate):
                expected = tuple((e.id, e.pos.x, e.pos.y, e.pos.z, e.radius)
                                 for e in sorted(self.st.entities.values(), key=lambda e: e.id)
                                 if e.alive and e.is_planet and e is not parent
                                 and e.data_id != 'asteroid_field')
                self.assertEqual(inputs.bodies_for(self.st, parent), expected)
                self.assertEqual(len(expected), 2)
                self.assert_geometry_matches(parent, 45, 0, inputs)
            self.assert_spacing_matches()

    def test_numeric_snapshot_freezes_bodies_not_entity_references(self):
        parent, other = self.planets
        inputs = orbits._OrbitTerrainInputs()
        before = inputs.bodies_for(self.st, parent)
        other.pos.x += 123
        other.radius += 12
        other.alive = False
        self.assertEqual(inputs.bodies_for(self.st, parent), before)
        self.assertEqual(before, ((other.id, 5000, 0, 0, 600),))
        self.assertEqual(orbits._OrbitTerrainInputs().bodies_for(self.st, parent), ())
        # The next normal query reads live inputs; there is no global batch.
        with patch.object(orbits, '_terrain_plans', wraps=orbits._terrain_plans) as calls:
            orbits.orbit_geometry(self.st, parent, 45, 0)
        self.assertEqual(calls.call_args.args[5], ())

    def test_same_tick_mutations_between_spacing_calls_are_live(self):
        parent, other = self.planets
        self.assert_spacing_matches()
        tick = self.st.tick
        mutations = [
            ('position', lambda: setattr(other.pos, 'x', other.pos.x + 123)),
            ('radius', lambda: setattr(other, 'radius', 720)),
            ('death', lambda: setattr(other, 'alive', False)),
            ('revival', lambda: setattr(other, 'alive', True)),
            ('asteroid', lambda: setattr(other, 'data_id', 'asteroid_field')),
            ('restore type', lambda: setattr(other, 'data_id', 'temperate')),
            ('ID', lambda: setattr(other, 'id', 9876)),
            ('reorder', lambda: setattr(self.st, 'entities', dict(reversed(tuple(self.st.entities.items()))))),
            ('insertion', lambda: self.st.entities.__setitem__(90002, copy.deepcopy(other))),
            ('deletion', lambda: self.st.entities.pop(90002)),
            ('parent position', lambda: setattr(parent.pos, 'z', -120)),
            ('bounds', lambda: setattr(self.st.map_info, 'bounds', 19000)),
            ('config', lambda: self.cs.ds.rules['colonies'].__setitem__('orbit_clearance', 400)),
            ('catalogue hull', lambda: setattr(self.cs.ds.stations['attack_satellite'], 'radius', 48)),
            ('entity hull', lambda: setattr(self.satellites[0], 'radius', 49)),
            ('paid slot', lambda: parent.build_queue[0].__setitem__('slot', 3)),
        ]
        for name, mutate in mutations:
            with self.subTest(mutation=name):
                mutate()
                self.assert_spacing_matches()
                self.assertEqual(self.st.tick, tick)
                for p in self.planets:
                    self.assert_geometry_matches(p, 45, 0, orbits._OrbitTerrainInputs())

    def test_no_geometry_means_no_terrain_scan(self):
        for sat in self.satellites:
            sat.satellite_slot = None
        for planet in self.planets:
            planet.build_queue.clear()
        result, scans, sizes = self.counted_spacing(ConstructionSystem._check_station_spacing)
        self.assertEqual(result, (True, ''))
        self.assertEqual((scans, sizes), (1, []))

    def test_invalid_cfg_does_not_assemble_terrain_even_for_many_queries(self):
        self.cs.ds.rules['colonies']['satellite_cap'] = False
        result, scans, sizes = self.counted_spacing(ConstructionSystem._check_station_spacing)
        self.assertEqual(result, (True, ''))
        self.assertEqual((scans, sizes), (1, []))

    def test_first_rejection_endpoint_ring_paid_and_hostile_boundaries(self):
        parent = self.planets[0]
        sat = self.satellites[0]
        self.assertEqual(self.assert_spacing_matches(sat.pos), (False, 'too close to attack satellite'))
        # Endpoint is far away, but every point on the future ring is reserved.
        ring_point = orbits.orbit_position(parent, sat.radius, 2.3, sat.satellite_slot, state=self.st)
        self.assertGreater(ring_point.dist(sat.pos), 1000)
        self.assertEqual(self.assert_spacing_matches(ring_point), (False, 'too close to attack satellite'))
        # Planet queues precede live satellites in insertion order.
        work = parent.build_queue[0]
        paid_point = orbits.orbit_position(parent, self.cs.ds.stations[work['item']].radius,
                                          1.7, work['slot'], state=self.st)
        self.assertEqual(self.assert_spacing_matches(paid_point), (False, 'too close to defense satellite site'))
        self.assertEqual(self.assert_spacing_matches(Vec3(*work['pos'])),
                         (False, 'too close to defense satellite site'))
        self.assertEqual(self.assert_spacing_matches(Vec3(*work['pos']), ignore_work=work), (True, ''))
        self.assertEqual(self.assert_spacing_matches(sat.pos, ignore_entity=sat), (True, ''))
        center = self.factory.spawn_station('command_station', 1, Vec3(0, 12000, 0))
        self.assertEqual(self.assert_spacing_matches(Vec3(0, 9000.01, 0)),
                         (False, 'too close to hostile command station'))
        self.assertEqual(self.assert_spacing_matches(Vec3(0, 9000, 0)), (True, ''))
        # A hidden live hostile does not leak through the preview.
        self.assertEqual(self.assert_spacing_matches(Vec3(0, 9000.01, 0), viewer=0), (True, ''))
        self.assertTrue(center.alive)
        for coords, reason in (([float('nan'), 0, 0], 'invalid site coordinates'),
                               ([20001, 0, 0], 'outside the map bounds')):
            self.assertEqual(self.assert_spacing_matches(coords), (False, reason))

    def test_viewer_paid_source_authority_ignores_and_parent_checks(self):
        parent = self.planets[0]
        work = parent.build_queue[0]
        point = Vec3(*work['pos'])
        for owner, source, allied, blocked in ((0, 0, False, True), (1, 1, False, False),
                                               (1, 1, True, True), (0, 1, False, False)):
            with self.subTest(owner=owner, source=source, allied=allied):
                parent.colonized_by, work['source_owner'] = owner, source
                self.st.players[0].team = 3 if allied else None
                self.st.players[1].team = 3 if allied else None
                self.assertEqual(self.assert_spacing_matches(point, viewer=0)[0], not blocked)
        # Parent None/dead and malformed paid slots keep the original fallbacks.
        for value in (None, 99999):
            self.satellites[0].planet_id = value
            self.assert_spacing_matches()
        parent.alive = False
        self.assert_spacing_matches()
        parent.alive = True
        for slot in (None, True, '2', -1, 99):
            work['slot'] = slot
            self.assert_spacing_matches()
        work['status'] = 'unpaid'
        self.assert_spacing_matches(point)
        work['status'], work['item'] = 'paid', 'unknown_hull'
        self.assert_spacing_matches(point)

    def test_swept_legality_matches_legacy_spacing_and_geometry(self):
        system = orbits.SatelliteOrbitSystem(self.st, None, self.cs)
        parent, sat = self.planets[0], self.satellites[0]
        ring = orbits.orbit_position(parent, sat.radius, .7, sat.satellite_slot, state=self.st)
        work_point = Vec3(*parent.build_queue[0]['pos'])
        self.factory.spawn_station('command_station', 1, Vec3(0, 10000, 0))
        cases = [(sat.pos, sat.pos + Vec3(1, 0, 0)),
                 (self.far, self.far + Vec3(1, 0, 0)),
                 (parent.pos - Vec3(1000, 0, 0), parent.pos + Vec3(1000, 0, 0)),
                 (work_point - Vec3(1000, 0, 0), work_point + Vec3(1000, 0, 0)),
                 (Vec3(0, 6000, 0), Vec3(0, 14000, 0)),
                 (ring, ring + Vec3(1, 0, 0))]
        before = self.state_bytes()
        results = []
        for start, end in cases:
            with self.subTest(start=start.to_tuple(), end=end.to_tuple()):
                with patch.object(self.cs, '_check_station_spacing',
                                  side_effect=lambda *a, **kw: legacy_spacing(self.cs, *a, **kw)), \
                        patch.object(orbits, 'orbit_geometry', side_effect=legacy_geometry):
                    expected = system.legal_segment(sat, parent, start, end)
                actual = system.legal_segment(sat, parent, start, end)
                self.assertEqual(actual, expected)
                results.append(actual)
        self.assertIn(True, results)
        self.assertIn(False, results)
        self.assertEqual(self.state_bytes(), before)

    def test_early_rejections_and_missing_parents_do_not_capture_terrain(self):
        with patch.object(orbits._OrbitTerrainInputs, 'bodies_for',
                          side_effect=AssertionError('unnecessary terrain assembly')):
            self.assertEqual(self.cs._check_station_spacing('mining_station', [float('inf'), 0, 0], 0),
                             (False, 'invalid site coordinates'))
            self.assertEqual(self.cs._check_station_spacing('mining_station', [20001, 0, 0], 0),
                             (False, 'outside the map bounds'))
            for planet in self.planets:
                planet.build_queue.clear()
            for sat in self.satellites:
                sat.planet_id = 99999
            self.assertEqual(self.cs._check_station_spacing('mining_station', self.far, 0), (True, ''))

    def test_four_player_fixture_all_geometry_and_spacing_are_pure(self):
        from game.graphics_benchmark import make_fixture
        self.st = make_fixture('four-player-stock-distributed-v1').manager.state
        self.cs = ConstructionSystem(self.st)
        before = self.state_bytes()
        inputs = orbits._OrbitTerrainInputs()
        satellites = [e for e in self.st.entities.values() if e.satellite_slot is not None]
        self.assertEqual(len(satellites), 32)
        for sat in satellites:
            parent = self.st.entity(sat.planet_id)
            self.assert_geometry_matches(parent, sat.radius, sat.satellite_slot, inputs)
            self.assert_spacing_matches(sat.pos, ignore_entity=sat)
        self.assertEqual(self.state_bytes(), before)


if __name__ == '__main__':
    unittest.main()
