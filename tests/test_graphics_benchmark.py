"""Representative fixture contracts: real catalogue objects, not render stand-ins."""
import importlib.util
import unittest


class FixtureInventoryTests(unittest.TestCase):
    def test_four_player_inventory_and_real_routes(self):
        self.assertIsNotNone(importlib.util.find_spec('game.graphics_benchmark'),
                             'versioned representative fixtures are missing')
        from game.graphics_benchmark import make_fixture, semantic_inventory
        scene = make_fixture('four-player-distributed-v1')
        gm, st = scene.manager, scene.manager.state
        inventory = semantic_inventory(st)
        expected = dict(combat_ships=600, ordinary_stations=40, trade_stations=16,
                        transports=64, planets=8, satellites=32)
        self.assertEqual(inventory['total'], expected)
        for owner in range(4):
            self.assertEqual(inventory['players'][str(owner)],
                             {key: value // 4 for key, value in expected.items()})
        for e in st.entities.values():
            if e.is_ship and e.data_id != 'trade_convoy':
                self.assertIn(e.data_id, gm.ds.ships)
                self.assertEqual(e.max_hull, gm.ds.ships[e.data_id].hull)
            if e.is_station:
                self.assertIn(e.data_id, gm.ds.stations)
            if e.data_id == 'trade_convoy':
                src, dest = st.entity(e.convoy_source), st.entity(e.convoy_dest)
                self.assertEqual(src.data_id, 'trade_station')
                self.assertTrue(gm.trading.valid_destination(st, e, dest))
                self.assertEqual(e.order_target_id, dest.id)
            if e.satellite_slot is not None:
                planet = st.entity(e.planet_id)
                self.assertTrue(planet.is_planet)
                self.assertEqual(planet.colonized_by, e.owner)
                self.assertTrue(gm.satellite_orbits.legal(e, planet, e.pos))
        sources = [e.convoy_source for e in st.entities.values() if e.data_id == 'trade_convoy']
        self.assertEqual({source: sources.count(source) for source in set(sources)},
                         {e.id: 4 for e in st.entities.values() if e.data_id == 'trade_station'})
    def test_combat_uses_all_classes_all_owners_and_remains_active_for_ten_seconds(self):
        from game.graphics_benchmark import make_fixture, COMBAT_MIX
        scene = make_fixture('four-player-combat-v1')
        gm, st = scene.manager, scene.manager.state
        fired, owners_by_window = set(), [set(), set(), set()]
        classes_by_window = [set(), set(), set()]
        visible = [e for e in st.entities.values() if e.is_ship and e.data_id != 'trade_convoy'
                   and st.can_see(0, e.id)]
        self.assertEqual(len(visible), 600, 'all four fighting fleets must be detected legitimately')
        def shot(event):
            e = st.entities[event.data['attacker_id']]
            fired.add(e.data_id)
            owners_by_window[min((st.tick - 1) // 100, 2)].add(e.owner)
            classes_by_window[min((st.tick - 1) // 100, 2)].add(e.data_id)
        st.events.subscribe('weapon_fired', shot)
        for _ in range(scene.max_ticks):
            gm.step(1 / 30)
        self.assertTrue({kind for kind, _ in COMBAT_MIX} <= fired)
        self.assertEqual(owners_by_window, [set(range(4))] * 3)
        for classes in classes_by_window:
            self.assertTrue({kind for kind, _ in COMBAT_MIX} <= classes)
        self.assertFalse(st.game_over)
        self.assertTrue(any(e.hull < e.max_hull or sum(e.shields.values()) < 4 * e.max_shield_quad
                            for e in st.entities.values() if e.is_ship and e.data_id != 'trade_convoy'))
        self.assertLessEqual(sum(e.alive and e.data_id == 'trade_convoy'
                                 for e in st.entities.values()), 64)

    def test_distributed_traffic_income_and_satellite_orbits_are_live(self):
        from game.graphics_benchmark import make_fixture, semantic_inventory
        gm = make_fixture('four-player-distributed-v1').manager
        st = gm.state
        transports = {e.id: e.pos.copy() for e in st.entities.values() if e.data_id == 'trade_convoy'}
        satellites = {e.id: e.pos.copy() for e in st.entities.values() if e.satellite_slot is not None}
        credits = {p: v.credits for p, v in st.players.items()}
        arrivals = []
        st.events.subscribe('convoy_arrived', lambda event: arrivals.append(event.data))
        for _ in range(90):
            gm.step(1 / 30)
        self.assertTrue(all(st.players[p].credits > value for p, value in credits.items()))
        self.assertTrue(all(st.players[p].income_frame['credits'] > 0 for p in credits))
        self.assertTrue(any(st.entity(i) is not None and st.entity(i).pos.dist(pos) > 1
                            for i, pos in transports.items()))
        self.assertTrue(all(st.entity(i).pos.dist(pos) > 1 for i, pos in satellites.items()))
        self.assertTrue(arrivals, 'staggered cargo must actually pay a destination')
        self.assertLess(semantic_inventory(st)['total']['transports'], 64)
        self.assertEqual(semantic_inventory(st)['total']['combat_ships'], 600)

    def test_recipes_repeat_and_close_view_does_not_change_world(self):
        from dataclasses import FrozenInstanceError
        from game.benchmark import state_hash
        from game.graphics_benchmark import FIXTURES, make_fixture
        for name in FIXTURES:
            a, b = make_fixture(name), make_fixture(name)
            metadata = a.metadata()
            self.assertEqual(metadata['command_budget_initial']['0'], {'used': 906, 'capacity': 78})
            self.assertEqual(state_hash(a.manager.state), state_hash(b.manager.state))
            for _ in range(2):
                a.manager.step(1 / 30)
                b.manager.step(1 / 30)
            self.assertEqual(state_hash(a.manager.state), state_hash(b.manager.state))
            self.assertEqual(a.metadata(), metadata, 'live simulation must not mutate recipe metadata')
            with self.assertRaises(FrozenInstanceError):
                a.camera.distance = 1
            meta = a.metadata()
            meta['camera']['distance'] = -1
            self.assertGreater(a.metadata()['camera']['distance'], 0)
        distributed = make_fixture('four-player-distributed-v1')
        close = make_fixture('four-player-close-v1')
        self.assertEqual(state_hash(distributed.manager.state), state_hash(close.manager.state))
        self.assertNotEqual(distributed.camera, close.camera)
        flagship = close.manager.state.entity(close.selection[0])
        self.assertEqual(close.camera.target, flagship.pos.to_tuple())
        self.assertLess(close.camera.distance, 2500)
        with self.assertRaises(ValueError):
            make_fixture('unknown')

    def test_combat_camera_analytically_frames_all_four_fleets_without_gl_context(self):
        from game.graphics_benchmark import make_fixture, visibility_sample
        from render.camera import Camera
        scene = make_fixture('four-player-combat-v1')
        for width, height in ((1280, 800), (1920, 1080)):
            camera = Camera(width, height)
            scene.camera.apply(camera)
            camera.bind_scene(scene.manager.state, lambda: 0)
            visible = visibility_sample(scene.manager.state, camera)
            self.assertEqual(visible['centres_in_viewport']['total']['combat_ships'], 600)
            self.assertEqual(camera.eye_position(), camera._requested_eye())


class BenchmarkReportTests(unittest.TestCase):
    def test_fixture_reports_precise_repeatable_state_inventory_and_separate_lan_stage(self):
        from game import benchmark
        self.assertIn('fixture', __import__('inspect').signature(benchmark.run_benchmark).parameters,
                      'fixture selection has not reached the benchmark driver')
        from game.graphics_benchmark import make_fixture
        plain = benchmark.run_benchmark(fixture='four-player-combat-v1', mode='sim', frames=2, warmup=1)
        lan = benchmark.run_benchmark(fixture='four-player-combat-v1', mode='sim', frames=2,
                                     warmup=1, lan_checksum=True)
        self.assertEqual(plain['initial_state_sha256'], lan['initial_state_sha256'])
        self.assertEqual(plain['state_sha256'], lan['state_sha256'])
        gm = make_fixture('four-player-combat-v1').manager
        self.assertEqual(plain['initial_state_sha256'], benchmark.state_hash(gm.state))
        for _ in range(3):
            gm.step(benchmark.TICK_DT)
        self.assertEqual(plain['state_sha256'], benchmark.state_hash(gm.state))
        self.assertEqual(plain['inventory_initial']['total']['combat_ships'], 600)
        self.assertEqual(len(plain['inventory_per_sample']), 2)
        self.assertEqual(plain['inventory_final'], plain['inventory_per_sample'][-1])
        self.assertEqual(plain['units'], 600)
        self.assertEqual(plain['stages'].keys(), {'sim'})
        self.assertEqual(lan['stages'].keys(), {'sim', 'lan_precise_checksum'})
        self.assertEqual(lan['stages']['lan_precise_checksum']['count'], 2)
        self.assertIn('not real-network pacing', lan['lan_checksum_semantics'])
        self.assertIn('p99_ms', plain['stages']['sim'])
        self.assertEqual(len(plain['visibility_per_sample']), 2)
        self.assertEqual(plain['visibility_per_sample'][0]['detected']['total']['combat_ships'], 600)
        self.assertEqual(len(plain['activity_per_sample']), 2)
        self.assertEqual(plain['activity_total']['shots_by_owner'].keys(), {'0', '1', '2', '3'})
        self.assertGreater(plain['activity_total']['visible_shots'], 0)

    def test_cli_validation_utf8_and_no_user_persistence_or_imports(self):
        from pathlib import Path
        import json
        import tempfile
        from unittest.mock import patch
        from game import benchmark
        scratch = Path.home() / '.hermes/cache/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory)
            default = root / 'user/benchmark.json'
            output = root / 'raport-Ł.json'
            with patch.object(benchmark, 'default_output_path', return_value=default):
                for args, code in [(['--help'], 0),
                                   (['--fixture', 'bad'], 1),
                                   (['--fixture', 'four-player-combat-v1', '--units', '600'], 1),
                                   (['--fixture', 'four-player-combat-v1', '--frames', '301'], 1)]:
                    self.assertEqual(benchmark.cli(args + ['--output', str(output)]), code)
                    raw = output.read_bytes()
                    self.assertNotIn(b'\r\n', raw)
                    result = json.loads(raw.decode('utf-8'))
                    import sys
                    with patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', None):
                        self.assertEqual(benchmark.cli(args + ['--output', str(output)]), code)
                    self.assertEqual(output.read_bytes(), raw, 'GUI help/errors must be byte-repeatable JSON')
                    self.assertEqual(result['status'], 'help' if '--help' in args else 'error')
                    if '--help' in args:
                        self.assertIn('--fixture', result['help'])
                        self.assertIn('--lan-checksum', result['help'])
                self.assertFalse(default.exists())
            # Fresh interpreter: import + actual fixture simulation must not load
            # SDL/menus or touch save/settings/campaign/balance paths.
            import subprocess
            import sys
            probe = '''
import sys
import os
from pathlib import Path
root = Path(sys.argv[1]).resolve()
def audit(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        if args[0] == os.devnull:
            return  # platform.platform() may open the null device for uname stderr.
        mode, flags = args[1:3]
        if ((isinstance(mode, str) and any(c in mode for c in 'wax+'))
                or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))):
            raise RuntimeError('unexpected write: ' + str(args[0]))
sys.addaudithook(audit)
try:
    open(root / 'write-canary', 'w')
except RuntimeError:
    pass
else:
    raise AssertionError('write barrier did not catch canary')
from game.benchmark import run_benchmark
r = run_benchmark(fixture='four-player-distributed-v1', mode='sim', frames=1, warmup=0)
assert r['counts_initial']['entities'] == 760
assert 'pygame' not in sys.modules
assert 'render.menus' not in sys.modules
print('isolated simulation ok')
'''
            result = subprocess.run([sys.executable, '-B', '-c', probe, str(root)],
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('isolated simulation ok', result.stdout)

    def test_default_legacy_hash_contract_and_percentiles(self):
        from game.benchmark import make_scene, run_benchmark, state_hash, summarize
        gm = make_scene(12)
        self.assertEqual(state_hash(gm.state), 'c94517b69a9a0209672934f17de5eedd7982cc25772e91bd4dd40014bf6ba1a1')
        for _ in range(6):
            gm.step(1 / 30)
        self.assertEqual(state_hash(gm.state), '3e9007788f942d600c1cf5da42d5bb39b681a297e9b8250642e13469ce21e45c')
        report = run_benchmark(units=12, frames=4, warmup=2, mode='sim')
        self.assertEqual(report['fixture'], 'corvette-combat-v1')
        self.assertEqual(report['state_sha256'], state_hash(gm.state))
        self.assertEqual(summarize(list(range(100)))['p99_ms'], 98)
        for kwargs in [dict(fixture='unknown'), dict(fixture='four-player-combat-v1', units=600),
                       dict(fixture='four-player-combat-v1', frames=291, warmup=10),
                       dict(lan_checksum='yes')]:
            with self.assertRaises(ValueError):
                run_benchmark(mode='sim', **kwargs)

    def test_full_report_records_actual_drawable_viewport_driver_and_camera(self):
        import os
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from game import benchmark
        pygame = Mock()
        pygame.QUIT, pygame.OPENGL, pygame.DOUBLEBUF = 99, 1, 2
        pygame.event.get.return_value = []
        pygame.version.ver = 'test'
        pygame.get_sdl_version.return_value = (2, 0, 0)
        pygame.display.get_driver.return_value = 'test-sdl'
        pygame.display.get_window_size.return_value = (800, 600)
        gl = Mock()
        gl.glGetString.return_value = b'test-driver'
        gl.glGetIntegerv.side_effect = lambda name: [0, 0, 1000, 750] if name == gl.GL_VIEWPORT else 4
        gl.glReadPixels.return_value = b'\x10\x20\x30' * (1000 * 750)
        camera = SimpleNamespace(width=1000, height=750, apply=Mock(),
                                 world_to_screen=lambda *p: (500., 375.),
                                 eye_position=lambda: (0., 1000., 0.))
        camera_factory, hud_factory, renderer_factory = Mock(return_value=camera), Mock(), Mock()
        renderer_factory.return_value.materials.available = True
        modules = {'pygame': pygame, 'OpenGL': SimpleNamespace(GL=gl),
                   'render.camera': SimpleNamespace(Camera=camera_factory),
                   'render.hud': SimpleNamespace(HUD=hud_factory),
                   'render.renderer': SimpleNamespace(Renderer=renderer_factory)}
        self.assertTrue(hasattr(benchmark, 'reported_drawable_size'), 'actual SDL drawable query missing')
        with patch.dict(sys.modules, modules), \
                patch.dict(os.environ, {'STAR_ARMADA_SKIP': '', 'STAR_ARMADA_NO_CULL': ''}), \
                patch.object(benchmark, 'reported_swap_interval', return_value=0), \
                patch.object(benchmark, 'reported_drawable_size', return_value=[1000, 750]):
            report = benchmark.run_benchmark(fixture='four-player-combat-v1', frames=2, warmup=0,
                                            width=800, height=600)
        camera_factory.assert_called_once_with(1000, 750)
        self.assertEqual(camera.target, [0., 0., 1400.])
        self.assertEqual(camera.distance, 14000.)
        self.assertEqual(report['graphics']['resolution'], [800, 600])
        self.assertEqual(report['graphics']['drawable_size'], [1000, 750])
        self.assertEqual(report['graphics']['gpu'], 'test-driver')
        self.assertEqual(len(report['graphics_per_sample']), 2)
        self.assertEqual(report['graphics_per_sample'][0]['viewport'], [0, 0, 1000, 750])
        self.assertEqual(report['graphics_per_sample'][0]['camera_eye'], [0., 1000., 0.])
        self.assertEqual(report['visibility_per_sample'][0]['centres_in_viewport']['total']['combat_ships'], 600)

    def test_sdl_drawable_is_unknown_not_a_requested_size_when_unavailable(self):
        from game import benchmark
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        self.assertTrue(hasattr(benchmark, 'reported_drawable_size'))
        pg = SimpleNamespace(base=SimpleNamespace(__file__='not-a-library'))
        with patch('ctypes.CDLL', side_effect=OSError('unavailable')):
            self.assertIsNone(benchmark.reported_drawable_size(pg))
        library = Mock()
        library.SDL_GL_GetCurrentWindow.return_value = 123
        def size(window, width, height):
            width._obj.value, height._obj.value = 1600, 1200
        library.SDL_GL_GetDrawableSize.side_effect = size
        with patch('ctypes.CDLL', return_value=library):
            self.assertEqual(benchmark.reported_drawable_size(pg), [1600, 1200])


if __name__ == '__main__':
    unittest.main()
