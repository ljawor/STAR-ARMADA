"""Deterministic performance contract, without timing assertions."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from game.core.manager import GameManager
from game.core.state import PlayerState
from game.core.vectors import Vec3


class AcquisitionPerformanceTests(unittest.TestCase):
    def test_nearest_visible_target_does_not_validate_farther_candidates(self):
        gm = GameManager()
        gm.state.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=1)}
        shooter = gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        enemies = [gm.factory.spawn_ship('imperial_corvette', 1, Vec3(100 + i * 10, 0, 0))
                   for i in range(30)]
        gm.state.grid.rebuild(gm.state.entities)
        # Explicitly exercise nearest-first order; the grid's actual ordering
        # remains the authority for equal-distance ties.
        with patch.object(type(gm.state.grid), 'query_sphere', return_value=[e.id for e in enemies]), \
             patch.object(gm.weapons, '_target_valid', wraps=gm.weapons._target_valid) as validate:
            self.assertIs(gm.weapons.find_target(shooter, 1000), enemies[0])
            self.assertEqual(validate.call_count, 1,
                             'farther candidates cannot win, so live visibility is wasted')


    def test_precise_manager_ticks_match_exhaustive_acquisition(self):
        from game.benchmark import make_scene
        from game.systems.weapons import WeaponSystem
        def exhaustive(system, entity, radius):
            best, best_d = None, 1e18
            for tid in system.state.grid.query_sphere(system.state.entities, entity.pos, radius):
                if tid == entity.id or not system._target_valid(entity, tid):
                    continue
                target = system.state.entity(tid)
                distance = entity.pos.dist_sq(target.pos)
                if distance < best_d:
                    best, best_d = target, distance
            return best
        optimized, reference = make_scene(80), make_scene(80)
        for tick in range(40):
            optimized.step(1 / 30)
            with patch.object(WeaponSystem, 'find_target', exhaustive):
                reference.step(1 / 30)
            self.assertEqual(json.dumps(optimized.state.to_dict(precise=True), sort_keys=True),
                             json.dumps(reference.state.to_dict(precise=True), sort_keys=True),
                             f'precise state diverged at tick {tick + 1}')
        self.assertTrue(optimized.state.projectiles or optimized.state.effects)

    def test_hidden_nearer_enemy_and_equal_distance_tie(self):
        gm = GameManager()
        gm.state.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=1)}
        shooter = gm.factory.spawn_ship('imperial_corvette', 0, Vec3())
        shooter.sensor_range = 0
        hidden = gm.factory.spawn_ship('imperial_corvette', 1, Vec3(300, 0, 0))
        first = gm.factory.spawn_ship('imperial_corvette', 1, Vec3(600, 0, 0))
        tied = gm.factory.spawn_ship('imperial_corvette', 1, Vec3(600, 0, 0))
        witness = gm.factory.spawn_ship('imperial_corvette', 0, Vec3(650, 0, 0))
        witness.sensor_range = 100
        gm.state.grid.rebuild(gm.state.entities)
        self.assertFalse(gm.state.can_see(0, hidden.id))
        self.assertTrue(gm.state.can_see(0, first.id))
        before = json.dumps(gm.state.to_dict(precise=True), sort_keys=True)
        with patch.object(type(gm.state.grid), 'query_sphere',
                          return_value=[hidden.id, first.id, tied.id, witness.id]):
            self.assertIs(gm.weapons.find_target(shooter, 1000), first)
        self.assertEqual(json.dumps(gm.state.to_dict(precise=True), sort_keys=True), before)


class FogRasterPerformanceTests(unittest.TestCase):
    def test_live_off_plane_spheres_and_exact_radius_boundaries(self):
        import math
        import pygame
        from render.fog import FogMask
        # 2501 retains non-cell-aligned bounds; 2400 gives exact representable
        # centers for inside/on/outside 3-4-5 sphere boundary assertions.
        for bounds in (2501, 2400):
            with self.subTest(bounds=bounds):
                gm = GameManager()
                st = gm.state
                st.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=0)}
                st.map_info.bounds = bounds
                st.explored_cells = {0: {(-1, -1), (0, 0)}, 1: {(1, 1)}}
                n = math.ceil(bounds / st.visibility_cell_size)
                # HEAD FogMask's exact original texel-center arithmetic:
                # arange(n) * step - half + step / 2, not (i+.5)*bounds/n.
                step, half = bounds / n, bounds / 2
                center = lambda i: i * step - half + step / 2
                sensor = gm.factory.spawn_ship('imperial_corvette', 1,
                    Vec3(center(3) - 300, 400, center(3)))
                sensor.sensor_range = 500
                above = gm.factory.spawn_ship('imperial_corvette', 0,
                    Vec3(center(0), 501, center(0)))
                above.sensor_range = 500  # Never intersects the map plane.
                st.grid.rebuild(st.entities)
                sources = st.sensor_sources(0)
                self.assertEqual(dict((e.id, r) for e, r in sources)[sensor.id], 500)
                expected = pygame.Surface((n, n), pygame.SRCALPHA)
                alphas = set()
                for z in range(n):
                    for x in range(n):
                        pos = Vec3(center(x), 0, center(z))
                        # SensorQueries._covers: positive radius, 3D squared
                        # distance <= radius squared, without epsilon.
                        def covers(e, r):
                            dx, dy, dz = e.pos.x-pos.x, e.pos.y-pos.y, e.pos.z-pos.z
                            return r > 0 and dx*dx + dy*dy + dz*dz <= r*r
                        visible = any(covers(e, r) for e, r in sources)
                        self.assertEqual(visible, st.is_position_visible(0, pos))
                        charted = st.is_position_explored(0, pos)
                        alpha = 0 if visible else 155 if charted else 255
                        alphas.add(alpha)
                        expected.set_at((x, z), (*((12, 22, 38) if charted else (3, 6, 13)), alpha))
                self.assertEqual(alphas, {0, 155, 255})
                if bounds == 2400:
                    boundary = Vec3(center(3), 0, center(3))
                    self.assertEqual(sensor.pos.dist_sq(boundary), 500**2)
                    self.assertTrue(st.is_position_visible(0, boundary))
                    self.assertTrue(st.is_position_visible(0, Vec3(center(2), 0, center(3))))
                    self.assertFalse(st.is_position_visible(0, Vec3(center(4), 0, center(3))))
                with patch.object(type(st), 'is_position_explored') as explored, \
                        patch.object(type(st), 'is_position_visible') as live:
                    actual = FogMask().surface(st, 0)
                    explored.assert_not_called()
                    live.assert_not_called()
                self.assertEqual(pygame.image.tobytes(actual, 'RGBA'),
                                 pygame.image.tobytes(expected, 'RGBA'))

    def test_raster_matches_authoritative_cells_without_per_texel_queries(self):
        import math
        import pygame
        from render.fog import FogMask
        gm = GameManager()
        st = gm.state
        st.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=0)}
        st.map_info.bounds = 2501  # Non-cell-aligned map bounds.
        st.explored_cells = {0: {(-1, -1), (0, 0)}, 1: {(1, 1)}}
        n = math.ceil(st.map_info.bounds / st.visibility_cell_size)
        step, half = st.map_info.bounds / n, st.map_info.bounds / 2
        expected = pygame.Surface((n, n), pygame.SRCALPHA)
        for z in range(n):
            for x in range(n):
                pos = Vec3(x * step - half + step / 2,
                           0, z * step - half + step / 2)
                charted = st.is_position_explored(0, pos)
                expected.set_at((x, z), (12, 22, 38, 155) if charted else (3, 6, 13, 255))
        fog = FogMask()
        with patch.object(type(st), 'is_position_explored', wraps=None) as query:
            # The raster can use one authoritative explored union, not N calls
            # that each re-aggregate alliance membership.
            actual = fog.surface(st, 0)
            self.assertEqual(query.call_count, 0)
        self.assertEqual(pygame.image.tobytes(actual, 'RGBA'),
                         pygame.image.tobytes(expected, 'RGBA'))

    def test_allied_exploration_invalidates_cached_mask(self):
        from render.fog import FogMask
        gm = GameManager()
        st = gm.state
        st.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=0)}
        st.explored_cells = {0: set(), 1: set()}
        fog = FogMask()
        first = fog.surface(st, 0)
        st.explored_cells[1].add((0, 0))
        second = fog.surface(st, 0)
        self.assertIsNot(second, first)
        self.assertIs(fog.surface(st, 0), second)
        st.players[1].team = 1
        self.assertIsNot(fog.surface(st, 0), second)


class BenchmarkContractTests(unittest.TestCase):
    def setUp(self):
        # Never use the system temp directory, including for test artifacts.
        scratch = Path.home() / '.hermes/cache/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_parse_errors_and_help_are_json_without_console(self):
        import game.benchmark as benchmark
        output = self.root / 'explicit.json'
        default = self.root / 'user/benchmark.json'
        for argv, status, code in [(['--units', 'bad'], 'error', 1),
                (['--mode', 'bad'], 'error', 1), (['--unknown'], 'error', 1),
                (['--help'], 'help', 0)]:
            with self.subTest(argv=argv), \
                    patch.object(benchmark, 'default_output_path', return_value=default), \
                    patch.object(benchmark, 'run_benchmark') as run, \
                    patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
                output.write_text('{"status":"ok","stale":true}')
                self.assertEqual(benchmark.cli(argv + ['--output', str(output)]), code)
                report = json.loads(output.read_text())
                self.assertEqual(report['status'], status)
                self.assertNotIn('stale', report)
                run.assert_not_called()
                if status == 'help':
                    self.assertIn('--output', report['help'])
                    self.assertEqual(report['default_output'], str(default))

    def test_parse_error_recovers_equals_output_and_default(self):
        import game.benchmark as benchmark
        default = self.root / 'user/benchmark.json'
        explicit = self.root / 'explicit.json'
        with patch.object(benchmark, 'default_output_path', return_value=default), \
                patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
            self.assertEqual(benchmark.cli(['--wat', '--output=' + str(explicit)]), 1)
            self.assertEqual(json.loads(explicit.read_text())['status'], 'error')
            self.assertEqual(benchmark.cli(['--output']), 1)
            self.assertEqual(json.loads(default.read_text())['status'], 'error')

    def test_bad_output_is_rejected_before_measurement_and_reported_in_default(self):
        import game.benchmark as benchmark
        default = self.root / 'user/benchmark.json'
        readonly = self.root / 'readonly.json'
        readonly.write_text('unchanged')
        readonly.chmod(0o444)
        self.addCleanup(readonly.chmod, 0o644)
        for output in (self.root, self.root / 'missing/report.json', readonly):
            with self.subTest(output=output), \
                    patch.object(benchmark, 'default_output_path', return_value=default), \
                    patch.object(benchmark, 'run_benchmark') as run, \
                    patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
                self.assertEqual(benchmark.cli(['--output', str(output)]), 1)
                run.assert_not_called()
                report = json.loads(default.read_text())
                self.assertEqual(report['status'], 'error')
                self.assertEqual(report['requested_output'], str(output))
                self.assertIn('output', report['error'].lower())

    def test_late_write_failure_is_not_reported_as_success(self):
        import game.benchmark as benchmark
        output = self.root / 'report.json'
        default = self.root / 'user/benchmark.json'
        replace = os.replace
        def fail_explicit(src, dst):
            if Path(dst) == output:
                raise OSError('disk write failed')
            return replace(src, dst)
        with patch.object(benchmark, 'default_output_path', return_value=default), \
                patch.object(benchmark, 'run_benchmark', return_value={'status': 'ok'}), \
                patch('os.replace', side_effect=fail_explicit), \
                patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
            self.assertEqual(benchmark.cli(['--output', str(output)]), 1)
        report = json.loads(default.read_text())
        self.assertEqual(report['status'], 'error')
        self.assertIn('disk write failed', report['error'])
        self.assertEqual(report['measurement_result']['status'], 'ok')
        self.assertFalse(output.exists())

    def test_full_mode_is_retired_with_the_renderer(self):
        # `full` timed glFinish around the Python renderer's world/HUD passes; that renderer is
        # gone (#160), so asking for it must say so instead of measuring half a frame.
        from game.benchmark import run_benchmark
        with self.assertRaisesRegex(ValueError, 'native window'):
            run_benchmark(mode='full', frames=1, warmup=0)

    def test_swap_interval_is_unknown_when_sdl_symbol_is_unavailable(self):
        import game.benchmark as benchmark
        from types import SimpleNamespace
        self.assertTrue(hasattr(benchmark, 'reported_swap_interval'))
        with patch('ctypes.CDLL', side_effect=OSError('unavailable')):
            self.assertIsNone(benchmark.reported_swap_interval(
                SimpleNamespace(base=SimpleNamespace(__file__='missing'))))

    def test_sim_report_is_deterministic_and_executes_every_tick(self):
        spec = importlib.util.find_spec('game.benchmark')
        self.assertIsNotNone(spec, 'player-runnable benchmark module is missing')
        from game.benchmark import run_benchmark
        first = run_benchmark(units=12, frames=4, warmup=2, mode='sim')
        second = run_benchmark(units=12, frames=4, warmup=2, mode='sim')
        self.assertEqual(first['state_sha256'], second['state_sha256'])
        self.assertEqual(first['initial_state_sha256'], second['initial_state_sha256'])
        self.assertEqual(first['executed_ticks'], 6)
        self.assertEqual(first['stages']['sim']['count'], 4)
        self.assertEqual(first['counts_initial']['ships'], 12)
        self.assertGreater(first['counts_final']['projectiles'], 0)
        self.assertFalse(first['game_over'])
        self.assertEqual(first['stages'].keys(), {'sim'})
        json.dumps(first, allow_nan=False)


if __name__ == '__main__':
    unittest.main()