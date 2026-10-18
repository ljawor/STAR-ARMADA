"""CPU resolver evidence; no GL context, encoders or movie bake."""
import unittest
from tools import build_menu_movie as baker
from render import asset_selection as selection


class MovieSelectionTests(unittest.TestCase):
    def test_explicit_legacy_and_preview_restore_exact_prior_selection(self):
        before = selection._selection, selection._resolver
        with baker.offline_selection(True):
            resolver = selection._resolver
            self.assertTrue(selection._selection['model_preview'])
            self.assertIsNotNone(resolver)
            with baker.offline_selection(False):
                self.assertIsNone(selection._resolver)
                self.assertFalse(selection._selection['model_preview'])
            self.assertIs(selection._resolver, resolver)
        self.assertIs(selection._selection, before[0])
        self.assertIs(selection._resolver, before[1])

    def test_live_renderer_owner_refuses_without_mutating_selection(self):
        before = selection._selection, selection._resolver, selection._generation
        token = selection.attach_renderer()
        try:
            with self.assertRaisesRegex(RuntimeError, 'session boundary'):
                with baker.offline_selection(True):
                    self.fail('must refuse')
            self.assertEqual((selection._selection, selection._resolver, selection._generation), before)
            self.assertIn(token, selection._renderer_owners)
        finally:
            selection.release_renderer(token)


class MoviePublicationTests(unittest.TestCase):
    def exercise_publication(self, *, corrupt=False, alias=None):
        import io
        import json
        import os
        import subprocess
        import tempfile
        import zipfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest import mock
        import pygame
        from render import menu_movie

        with tempfile.TemporaryDirectory(dir=baker.ROOT.parent) as folder:
            root = Path(folder)
            target = root / 'arbitrary-directory' / 'candidate.zip'
            target.parent.mkdir()
            previous = b'previous candidate bytes'
            target.write_bytes(previous)
            canary = root / 'canary.zip'
            canary.write_bytes(b'untouched canary')
            predictable = target.with_suffix('.tmp')
            if alias == 'symlink':
                predictable.symlink_to(canary)
            elif alias == 'hardlink':
                os.link(canary, predictable)
            metadata = dict(version=1, width=2, height=2, fps=24,
                            frame_count=360, still_frame=180, loop='baked-crossfade',
                            provenance={'exact': 'staged candidate'})
            image = io.BytesIO()
            pygame.image.save(pygame.Surface((2, 2)), image, 'frame.jpg')
            payload = image.getvalue()
            observed = []
            decoded = []
            real_movie = menu_movie.MenuMovie

            class ObservedMovie(real_movie):
                def __init__(inner, asset_root, relative_path):
                    path = Path(asset_root) / relative_path
                    observed.append(path)
                    self.assertNotEqual(path, target)
                    self.assertEqual(path.parent, target.parent)
                    self.assertEqual(target.read_bytes(), previous)
                    self.assertEqual(path.stat().st_nlink, 1)
                    super().__init__(asset_root, relative_path)
                    self.assertEqual(inner.metadata, metadata)

                def get_frame(inner, elapsed, size, *args, **kwargs):
                    self.assertEqual(target.read_bytes(), previous)
                    decoded.append(int(elapsed * 24))
                    return super().get_frame(elapsed, size, *args, **kwargs)

            def encoder(command, **kwargs):
                if command[-1].endswith('.jpg'):
                    sequence = Path(command[-1])
                    for index in range(360):
                        (sequence.parent / f'{index:05d}.jpg').write_bytes(
                            b'bad jpeg' if corrupt and index == 359 else payload)

            args = SimpleNamespace(asset=target, output_dir=root, ffmpeg='never-executed')
            report = {}
            with mock.patch.object(baker, 'range', side_effect=lambda n: () if n == 384 else range(n), create=True), \
                 mock.patch.object(subprocess, 'run', side_effect=encoder), \
                 mock.patch.object(baker, 'movie_metadata', return_value=metadata), \
                 mock.patch.object(menu_movie, 'MenuMovie', ObservedMovie), \
                 mock.patch.object(pygame.transform, 'smoothscale', side_effect=lambda frame, size: frame):
                if corrupt:
                    with self.assertRaisesRegex(RuntimeError, 'decode verification failed'):
                        baker.build_movie(None, None, None, args, report)
                    self.assertEqual(target.read_bytes(), previous)
                else:
                    baker.build_movie(None, None, None, args, report)
                    with zipfile.ZipFile(target) as archive:
                        self.assertEqual(json.loads(archive.read('metadata.json')), metadata)
                        self.assertEqual(len(archive.namelist()), 361)
                        self.assertTrue(all(entry.compress_type == zipfile.ZIP_STORED
                                            for entry in archive.infolist()))
                    self.assertEqual(report['playback']['frames_verified'], 360)
                self.assertEqual(decoded[:360], list(range(360)))
            self.assertEqual(len(observed), 1)
            self.assertFalse(observed[0].exists())
            self.assertEqual(canary.read_bytes(), b'untouched canary')
            self.assertEqual(set(target.parent.iterdir()),
                             {target, predictable} if alias else {target})
            return observed[0].name

    def test_decode_failure_preserves_previous_bytes_and_cleans_staging(self):
        self.exercise_publication(corrupt=True)

    def test_predictable_symlink_canary_is_untouched(self):
        self.exercise_publication(alias='symlink')

    def test_predictable_hardlink_canary_is_untouched(self):
        self.exercise_publication(alias='hardlink')

    def test_success_verifies_exact_staged_zip_before_atomic_publication(self):
        first = self.exercise_publication()
        second = self.exercise_publication()
        self.assertNotEqual(first, second)


class MovieProvenanceTests(unittest.TestCase):
    def test_bake_revalidates_provenance_before_zip_publication(self):
        from pathlib import Path
        from types import SimpleNamespace
        from unittest import mock
        import tempfile
        import subprocess
        with tempfile.TemporaryDirectory(dir=baker.ROOT.parent) as folder:
            args = SimpleNamespace(ffmpeg='unused-encoder', output_dir=Path(folder),
                                   asset=Path(folder) / 'candidate.zip')
            with mock.patch.object(baker, 'range', return_value=(), create=True), \
                 mock.patch.object(subprocess, 'run'), \
                 mock.patch.object(baker, 'movie_metadata', side_effect=ValueError('stale bake pin')) as meta:
                try:
                    baker.build_movie(None, SimpleNamespace(state=SimpleNamespace(entities={})),
                                      None, args, {'msaa_samples': 4})
                except Exception as exc:
                    self.assertIsInstance(exc, ValueError, 'Bake must revalidate before publishing or decoding')
                    self.assertEqual(str(exc), 'stale bake pin')
                else:
                    self.fail('Bake did not revalidate provenance')
                meta.assert_called_once()
            self.assertFalse(args.asset.exists())

    def test_real_fixture_preview_pins_every_entity_and_candidate_metadata(self):
        import hashlib
        with baker.offline_selection(True):
            fixture = baker.PresentationFixture()
            provenance = baker.movie_provenance(fixture)
            self.assertEqual(provenance['selection_policy'], 'preview')
            self.assertEqual(len(provenance['models']), len(fixture.state.entities))
            for row in provenance['models']:
                entity = fixture.state.entities[row['entity_id']]
                binding = selection.ship_binding(fixture.ds, entity.data_id,
                                                fixture.state.players[entity.owner].faction)
                resolved = selection._resolver.resolve(binding)
                self.assertEqual(row['binding'], binding)
                self.assertEqual(row['resolved_binding'], binding)
                self.assertEqual(row['asset'], resolved.asset)
                self.assertEqual(row['revision'], resolved.revision)
                self.assertEqual(row['runtime_sha256'], hashlib.sha256(
                    (baker.ROOT / row['runtime_path']).read_bytes()).hexdigest())
                self.assertIsNone(row['legacy_fallback'])
            for path in ('tools/build_menu_movie.py', 'render/renderer.py'):
                self.assertEqual(provenance['code_sha256'][path], hashlib.sha256(
                    (baker.ROOT / path).read_bytes()).hexdigest())
            report = {'msaa_samples': 4, 'provenance': provenance}
            self.assertEqual(baker.movie_metadata(fixture, report)['provenance'], provenance)
            baker.verify_movie_provenance(provenance, fixture)

    def test_legacy_explicit_fallback_and_wrong_pin_negative_control(self):
        from copy import deepcopy
        with baker.offline_selection(False):
            fixture = baker.PresentationFixture()
            provenance = baker.movie_provenance(fixture)
            self.assertEqual(provenance['selection_policy'], 'legacy')
            for row in provenance['models']:
                self.assertIsNone(row['resolved_binding'])
                self.assertIsNone(row['revision'])
                self.assertIsNone(row['runtime_sha256'])
                self.assertEqual(row['legacy_fallback'], 'explicit legacy policy')
                self.assertTrue(row['legacy_visual_key'])
            bad = deepcopy(provenance)
            bad['code_sha256']['render/renderer.py'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'provenance'):
                baker.verify_movie_provenance(bad, fixture)
        with baker.offline_selection(True):
            fixture = baker.PresentationFixture()
            provenance = baker.movie_provenance(fixture)
            provenance['models'][0]['runtime_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'provenance'):
                baker.verify_movie_provenance(provenance, fixture)


class MovieCLITests(unittest.TestCase):
    def run_cli(self, argv, *, expected_preview=False, fail_at=None):
        import tempfile
        import json
        from pathlib import Path
        from unittest import mock
        from contextlib import ExitStack
        import pygame
        from OpenGL import GL
        import render.renderer
        events = []
        original_fixture = baker.PresentationFixture

        def fixture():
            events.append('fixture')
            self.assertEqual(selection._selection['model_preview'], expected_preview)
            return original_fixture()

        class FakeRenderer:
            skip = False
            def __init__(self, state, cam):
                events.append('renderer')
                self.token = selection.attach_renderer()
            def draw(self, *args):
                if fail_at == 'draw':
                    raise RuntimeError('injected draw failure')
            def close(self):
                events.append('close')
                selection.release_renderer(self.token)
                if fail_at == 'close':
                    raise RuntimeError('injected close failure')

        with tempfile.TemporaryDirectory(dir=baker.ROOT.parent) as folder, ExitStack() as stack:
            output = Path(folder) / 'stills'
            stack.enter_context(mock.patch.object(baker, 'PresentationFixture', side_effect=fixture))
            stack.enter_context(mock.patch.object(render.renderer, 'Renderer', FakeRenderer))
            for name in ('init', 'gl_set_attribute', 'set_mode', 'set_caption'):
                stack.enter_context(mock.patch.object(pygame.display, name))
            stack.enter_context(mock.patch.object(pygame.display, 'get_init', return_value=False))
            stack.enter_context(mock.patch.object(pygame.event, 'pump'))
            global_quit = stack.enter_context(mock.patch.object(pygame, 'quit'))
            stack.enter_context(mock.patch.object(pygame.display, 'quit',
                                                 side_effect=lambda: events.append('display-quit')))
            for name in ('glEnable', 'glClearColor', 'glViewport', 'glFinish'):
                stack.enter_context(mock.patch.object(GL, name))
            stack.enter_context(mock.patch.object(GL, 'glGetIntegerv', return_value=4))
            stack.enter_context(mock.patch.object(GL, 'glGetError', return_value=0))
            stack.enter_context(mock.patch.object(GL, 'glReadPixels', return_value=bytes(1280*720*3)))
            build = stack.enter_context(mock.patch.object(baker, 'build_movie'))
            stack.enter_context(mock.patch('builtins.print'))
            before = selection._selection, selection._resolver
            if fail_at:
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    baker.main(['--output-dir', str(output), *argv])
            else:
                baker.main(['--output-dir', str(output), *argv])
                report = json.loads((output / 'render-report.json').read_text())
                self.assertEqual(report['provenance']['selection_policy'],
                                 'preview' if expected_preview else 'legacy')
                self.assertFalse(report['candidate_zip_baked'])
                self.assertEqual(report['output_kind'], 'stills-only')
                build.assert_not_called()
            self.assertIs(selection._selection, before[0])
            self.assertIs(selection._resolver, before[1])
            global_quit.assert_not_called()
            self.assertEqual(events, ['fixture', 'renderer', 'close', 'display-quit'])

    def test_display_init_failure_preserves_callers_font_and_audio(self):
        import os
        import tempfile
        from unittest import mock
        import pygame
        owned_font = not pygame.font.get_init()
        if owned_font:
            pygame.font.init()
        font = pygame.font.Font(None, 16)
        owned_audio = pygame.mixer.get_init() is None
        try:
            with mock.patch.dict(os.environ, {'SDL_AUDIODRIVER': 'dummy'}):
                if owned_audio:
                    pygame.mixer.init()
            audio = pygame.mixer.get_init()
            sound = pygame.mixer.Sound(buffer=bytes(128))
            with tempfile.TemporaryDirectory(dir=baker.ROOT.parent) as folder, \
                 mock.patch.object(pygame.display, 'get_init', return_value=False), \
                 mock.patch.object(pygame.display, 'init', side_effect=RuntimeError('injected init failure')), \
                 mock.patch.object(pygame.display, 'quit') as display_quit:
                with self.assertRaisesRegex(RuntimeError, 'injected init failure'):
                    baker.main(['--preview-only', '--output-dir', folder])
                self.assertTrue(pygame.font.get_init(), 'caller font subsystem was shut down')
                self.assertGreater(font.render('still usable', True, 'white').get_width(), 0)
                self.assertEqual(pygame.mixer.get_init(), audio)
                self.assertIsNotNone(sound.play())
                display_quit.assert_called_once()
        finally:
            if owned_audio:
                pygame.mixer.quit()
            if owned_font:
                pygame.font.quit()

    def test_default_legacy_does_not_inherit_preview(self):
        with baker.offline_selection(True):
            self.run_cli(['--preview-only'])

    def test_preview_opt_in_precedes_fixture_and_report_is_stills_only(self):
        self.run_cli(['--preview-only', '--model-preview'], expected_preview=True)

    def test_failure_closes_before_quit_and_restores_selection(self):
        for failure in ('draw', 'close'):
            with self.subTest(failure=failure):
                self.run_cli(['--preview-only', '--model-preview'],
                             expected_preview=True, fail_at=failure)

    def test_candidate_requires_explicit_external_asset_before_gl(self):
        from unittest import mock
        import tempfile
        import pygame
        with tempfile.TemporaryDirectory(dir=baker.ROOT.parent) as folder:
            for extra in ([], ['--asset', str(baker.ROOT / 'assets/menu/battle.zip')]):
                with self.subTest(extra=extra), mock.patch.object(pygame.display, 'init') as init:
                    with self.assertRaises(SystemExit) as caught:
                        baker.main(['--output-dir', folder, '--model-preview', *extra])
                    self.assertEqual(caught.exception.code, 2)
                    init.assert_not_called()

    def test_existing_live_owner_never_initializes_or_quits_pygame(self):
        from unittest import mock
        import tempfile
        import pygame
        before = selection._selection, selection._resolver, selection._generation
        token = selection.attach_renderer()
        try:
            with tempfile.TemporaryDirectory(dir=baker.ROOT.parent) as folder:
                with mock.patch.object(pygame.display, 'init') as init, mock.patch.object(pygame, 'quit') as quit:
                    with self.assertRaisesRegex(RuntimeError, 'session boundary'):
                        baker.main(['--preview-only', '--output-dir', folder])
                    init.assert_not_called()
                    quit.assert_not_called()
                    self.assertEqual((selection._selection, selection._resolver, selection._generation), before)
                    self.assertIn(token, selection._renderer_owners)
        finally:
            selection.release_renderer(token)


if __name__ == '__main__':
    unittest.main()
