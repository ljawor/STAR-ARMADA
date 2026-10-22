"""CPU-only contract tests: never execute main.py or initialize a GPU."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'tools/play_imperium_fleet.py'


def load_launcher():
    spec = importlib.util.spec_from_file_location('play_imperium_fleet', LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProfileTests(unittest.TestCase):
    def test_isolated_profile_never_writes_source_or_inherits_balance(self):
        self.assertTrue(LAUNCHER.is_file(), 'isolated native review launcher is missing')
        launcher = load_launcher()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source'
            root.mkdir()
            (root / 'saves').mkdir()
            original = b'{"fullscreen":true,"visual_packs":["personal"],"autosave_index":2}'
            (root / 'saves/settings.json').write_bytes(original)
            (root / 'saves/balance.json').write_text('{"do_not_copy":true}')
            for pack in launcher.REVIEW_PACKS:
                folder = root / 'visual_packs' / pack
                folder.mkdir(parents=True)
                (folder / 'visual-pack.json').write_text('{}')
            defaults = {'fullscreen': True, 'visual_packs': ['personal'], 'resolution': 'auto'}
            before = copy.deepcopy(defaults)
            with launcher.isolated_profile(root, defaults) as user:
                self.assertFalse(user.is_relative_to(root))
                self.assertEqual(json.loads((user / 'saves/settings.json').read_text())['visual_packs'], list(launcher.REVIEW_PACKS))
                settings = json.loads((user / 'saves/settings.json').read_text())
                self.assertTrue(settings['model_preview'])
                self.assertEqual(settings['renderer'], 'cpp')
                self.assertFalse(settings['fullscreen'])
                self.assertTrue((user / 'saves').is_dir())
                self.assertTrue((user / 'replays').is_dir())
                self.assertFalse((user / 'saves/balance.json').exists())
                target = user / 'visual_packs' / launcher.REVIEW_PACKS[0] / 'visual-pack.json'
                target.write_text('{"isolated":true}')
                self.assertEqual((root / 'visual_packs' / launcher.REVIEW_PACKS[0] / 'visual-pack.json').read_text(), '{}')
            self.assertFalse(user.exists())
            self.assertEqual(defaults, before)
            self.assertEqual((root / 'saves/settings.json').read_bytes(), original)


class SubjectTests(unittest.TestCase):
    def test_focus_mapping_factory_and_heading_relative_native_selection(self):
        import math
        from types import SimpleNamespace
        from game.core.manager import GameManager
        from game.data.store import DataStore
        from render.camera import Camera
        from render.input import InputController
        launcher = load_launcher()
        expected = {
            'hammer': ('imperial_tie_bomber_squadron', 'bomber'),
            'lancer': ('imperial_frigate', 'frigate'),
            'gladiator': ('imperial_cruiser', 'cruiser'),
            'executor': ('imperial_battleship', 'battleship'),
            'sovereign': ('imperial_supercapital', 'supercapital'),
            'colonial': ('imperial_colonizer', 'colonizer'),
            'transport': ('imperial_crew_transport', 'convoy'),
        }
        self.assertEqual(launcher.FOCUS, expected)
        for focus, (ship_id, role) in expected.items():
            with self.subTest(focus=focus):
                DataStore.reset()
                gm = GameManager.start_skirmish(DataStore().maps['skirmish01'])
                before = gm.state.to_dict(precise=True)
                subject, spawned = launcher.prepare_subject(gm, focus)
                self.assertTrue(spawned)
                self.assertEqual(len(gm.state.entities), len(before['entities']) + 1)
                self.assertIn('REVIEW', subject.name_override)
                self.assertEqual(subject.data_id, ship_id)
                self.assertEqual(subject.hull, gm.ds.ships[ship_id].hull)
                self.assertEqual(subject.radius, gm.ds.ships[ship_id].radius)
                again, spawned = launcher.prepare_subject(gm, focus)
                self.assertIs(again, subject)
                self.assertFalse(spawned)
                subject.yaw = 1.2
                camera = Camera(1280, 800)
                launcher.frame_subject(camera, gm.ds, subject)
                self.assertAlmostEqual(camera.yaw, (math.degrees(subject.yaw) + 35.) % 360.)
                self.assertGreaterEqual(camera.distance, camera.zoom_limits[0])
                self.assertLessEqual(camera.distance, camera.zoom_limits[1])
                self.assertEqual(camera.target, [subject.pos.x, subject.pos.y, subject.pos.z])
                hud = SimpleNamespace(buttons=[], blocked_rects=[], minimap_rect=None, placement=None)
                inputc = InputController(gm.state, camera, hud, None)
                launcher.select_subject(inputc, subject)
                self.assertEqual(inputc.selection, {subject.id})
                # Same native key path still queues ordinary player commands.
                import pygame
                inputc.app = SimpleNamespace(flash=lambda _: None)
                inputc.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0))
                self.assertTrue(gm.state.command_queue)
                self.assertTrue(all(math.isfinite(v) for v in camera.eye_position()))


class ValidationTests(unittest.TestCase):
    def test_rejection_and_missing_pack_never_silently_fall_back(self):
        launcher = load_launcher()
        from render import asset_selection
        try:
            report = asset_selection.configure({'model_preview': True, 'visual_packs': list(launcher.REVIEW_PACKS)},
                                               asset_root=ROOT, pack_root=ROOT / 'visual_packs')
            # Pending assets may arrive concurrently: both states must be handled strictly.
            if all(p['accepted'] for p in report['pack_order']):
                launcher.validate_selection(report)
            else:
                with self.assertRaisesRegex(ValueError, 'rejected|missing'):
                    launcher.validate_selection(report)
            damaged = copy.deepcopy(report)
            damaged['pack_order'][0]['accepted'] = False
            with self.assertRaisesRegex(ValueError, 'rejected|missing'):
                launcher.validate_selection(damaged)
            damaged = copy.deepcopy(report)
            damaged['enabled_order'] = list(launcher.ACCEPTED_PACKS)
            with self.assertRaises(ValueError):
                launcher.validate_selection(damaged)
        finally:
            asset_selection.configure({'model_preview': False})

    def test_profile_path_bindings_and_cli_are_explicit(self):
        launcher = load_launcher()
        user = Path('/isolated/review')
        paths = launcher.profile_paths(user)
        self.assertEqual(paths['SETTINGS_PATH'], str(user / 'saves/settings.json'))
        self.assertEqual(paths['BALANCE_PATH'], str(user / 'saves/balance.json'))
        self.assertEqual(paths['CAMPAIGN_PATH'], str(user / 'saves/campaign.json'))
        self.assertEqual(paths['USER_DIR'], str(user))
        args = launcher.parse_args(['--focus', 'hammer', '--frames', '12', '--capture', '/capture.png'])
        self.assertEqual(args.frames, 12)
        self.assertEqual(args.capture, Path('/capture.png'))
        with self.assertRaises(SystemExit):
            launcher.parse_args(['--focus', 'unrelated'])
        with self.assertRaises(SystemExit):
            launcher.parse_args(['--frames', '0'])


class NativeHookTests(unittest.TestCase):
    def test_hooks_frame_once_keep_input_usable_and_finish_by_presents(self):
        from argparse import Namespace
        from types import SimpleNamespace
        import pygame
        from game.core.manager import GameManager
        from game.data.store import DataStore
        from render.camera import Camera
        from render.input import InputController
        from unittest.mock import patch
        launcher = load_launcher()
        args = Namespace(focus='lancer', frames=3, capture=None)
        hooks = launcher.ReviewHooks(args)
        DataStore.reset()
        gm = hooks.start_game(GameManager.start_skirmish, DataStore().maps['skirmish01'])
        camera = Camera(1280, 800)
        hud = SimpleNamespace(buttons=[], blocked_rects=[], minimap_rect=None, placement=None)
        inputc = InputController(gm.state, camera, hud, None)
        ns = dict(state=gm.state, gm=gm, camera=camera, inputc=inputc, local_player=0,
                  running=True, CPP={'failed': False}, mode='game')
        with patch.object(pygame.display, 'set_caption'):
            hooks.before_events(ns)
        self.assertEqual(inputc.selection, {hooks.subject.id})
        camera.yaw = 200.
        hooks.before_events(ns)
        self.assertEqual(camera.yaw, 200., 'review hook must not fight user camera input')
        hooks.after_present()
        hooks.after_present()
        self.assertTrue(ns['running'])
        hooks.after_present()
        self.assertFalse(ns['running'])
        self.assertEqual(hooks.presented, 3)
        self.assertIn('REVIEW', ns['replay_notice'])
        ns['mode'] = 'menu'
        ns['running'] = True
        with self.assertRaisesRegex(RuntimeError, 'left the match'):
            hooks.before_events(ns)

    def test_full_authored_review_profile_and_seven_real_camera_picks(self):
        launcher = load_launcher()
        if not (ROOT / 'visual_packs/imperium-fleet-prototypes/visual-pack.json').is_file():
            self.skipTest('Remaining fleet pack is not exported yet')
        from types import SimpleNamespace
        from game.core.manager import GameManager
        from game.data.store import DataStore
        from render import asset_selection, menus
        from render.camera import Camera
        from render.input import InputController
        from render_bridge.protocol import decode, WORLD
        from unittest.mock import patch
        try:
            with launcher.isolated_profile(ROOT, menus.DEFAULT_SETTINGS) as user:
                settings = json.loads((user / 'saves/settings.json').read_text())
                report = launcher.build_review_catalogue(settings, user / 'review.snap')
                self.assertEqual(len(report['pack_order']), 14)
                with patch.multiple(menus, **launcher.profile_paths(user)):
                    launcher.validate_selection(asset_selection.configure_from_settings(settings))
                    for focus in launcher.FOCUS:
                        DataStore.reset()
                        gm = GameManager.start_skirmish(DataStore().maps['skirmish01'])
                        subject, _ = launcher.prepare_subject(gm, focus)
                        camera = Camera(1280, 800)
                        controller = InputController(gm.state, camera,
                            SimpleNamespace(buttons=[], blocked_rects=[], minimap_rect=None, placement=None), None)
                        launcher.frame_subject(camera, gm.ds, subject)
                        launcher.select_subject(controller, subject)
                        self.assertEqual(controller.selection, {subject.id}, focus)
                        self.assertTrue(gm.state.can_see(0, subject.id))
        finally:
            asset_selection.configure({'model_preview': False})

    def test_source_entry_is_guarded_and_uses_actual_main_not_a_viewer(self):
        import ast
        import sys
        from unittest.mock import patch
        launcher = load_launcher()
        with patch.object(sys, 'frozen', True, create=True):
            with self.assertRaisesRegex(ValueError, 'Source-run review only'):
                launcher.main([])
        tree = ast.parse(LAUNCHER.read_text())
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'run_path']
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.unparse(calls[0].args[0]), "str(ROOT / 'main.py')")
        self.assertNotIn('render.renderer', LAUNCHER.read_text())
        self.assertNotIn('--smoke', LAUNCHER.read_text())

    def test_capture_is_finite_and_png_only(self):
        launcher = load_launcher()
        self.assertEqual(launcher.parse_args(['--capture', '/proof.png']).frames, 90)
        from contextlib import redirect_stderr
        import io
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            launcher.parse_args(['--capture', '/proof.json'])

    def test_catalogue_uses_review_packs_not_shipped_or_inherited_snapshot(self):
        launcher = load_launcher()
        from unittest.mock import patch
        from render import asset_selection
        from render_bridge.protocol import decode, WORLD
        settings = {'model_preview': True, 'visual_packs': list(launcher.ACCEPTED_PACKS)}
        # Exercise the real CPU exporter even while the seventh-model pack is being authored.
        with tempfile.TemporaryDirectory() as directory, patch.object(launcher, 'REVIEW_PACKS', launcher.ACCEPTED_PACKS), patch.object(launcher, 'FOCUS', {}):
            target = Path(directory) / 'review.snap'
            report = launcher.build_review_catalogue(settings, target)
            self.assertEqual(report['enabled_order'], list(launcher.ACCEPTED_PACKS))
            self.assertTrue(target.is_file())
            self.assertGreater(target.stat().st_size, 1000)
        asset_selection.configure({'model_preview': False})


if __name__ == '__main__':
    unittest.main()
