"""CPU-only regressions for the native catalogue fixture's ownership boundary."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_model_context_lifecycle as native


class ContextFixtureIsolationTests(unittest.TestCase):
    def run_fixture(self, *, display_initialized=False, surface=None, owners=(),
                    close_error=None):
        """Run the real inner fixture; only its native dependencies are mocked."""
        stack = self.enterContext(ExitStack())
        selection = {'model_preview': True, 'visual_packs': ['caller-pack']}
        resolver = Mock(name='caller resolver')
        store = object()
        for name, value in (('_selection', selection), ('_resolver', resolver),
                            ('_generation', 731), ('_renderer_owners', set(owners))):
            stack.enter_context(patch.object(native.asset_selection, name, value))
        stack.enter_context(patch.object(native.DataStore, '_instance', store))
        display = stack.enter_context(patch.object(native.pygame, 'display'))
        display.get_init.return_value = display_initialized
        display.get_surface.return_value = surface
        invalidate = stack.enter_context(patch.object(
            native.asset_selection, 'invalidate_geometry_helpers'))

        candidate = Mock(name='fixture resolver')
        invalidated_states = []
        def record_invalidation():
            invalidated_states.append((native.asset_selection._selection,
                                       native.asset_selection._resolver,
                                       native.asset_selection._generation))
        invalidate.side_effect = record_invalidation

        def configure(settings):
            native.asset_selection._selection = dict(settings)
            native.asset_selection._resolver = candidate
            native.asset_selection._generation += 1
            invalidate()

        configure_mock = stack.enter_context(patch.object(
            native.asset_selection, 'configure', side_effect=configure))
        stack.enter_context(patch.object(native.DataStore, 'get',
            return_value=SimpleNamespace(maps={'skirmish01': object()})))
        def start(*args):
            native.DataStore._instance = object()
            return SimpleNamespace(state=object())
        stack.enter_context(patch.object(native.GameManager, 'start_skirmish', side_effect=start))
        stack.enter_context(patch('game.benchmark.state_hash', return_value='unchanged'))
        renderer = Mock()
        renderer.materials.available = False  # Stop before any GPU-list operation.
        renderer.materials.error = 'fixture stop'
        renderer.close.side_effect = close_error
        factory = stack.enter_context(patch.object(native, 'Renderer', return_value=renderer))
        stack.enter_context(patch.object(native, 'Camera'))
        gl = stack.enter_context(patch.object(native, 'GL'))
        inner = native.ModelContextLifecycleTests(
            'test_registered_catalogue_lists_close_and_rebuild_across_preview_cycles')
        result = unittest.TestResult()
        inner.run(result)
        self.assertEqual(gl.mock_calls, [], 'CPU isolation regression reached GPU operations')
        return SimpleNamespace(result=result, selection=selection, resolver=resolver,
                               store=store, display=display, renderer=renderer,
                               factory=factory, configure=configure_mock, invalidate=invalidate,
                               candidate=candidate, invalidated_states=invalidated_states)

    def test_refuses_caller_display_without_replacing_or_shutting_it_down(self):
        probe = self.run_fixture(display_initialized=True, surface=object())
        self.assertEqual(len(probe.result.skipped), 1)
        probe.display.init.assert_not_called()
        probe.display.set_mode.assert_not_called()
        probe.display.quit.assert_not_called()
        probe.factory.assert_not_called()
        probe.configure.assert_not_called()
        self.assertIs(native.DataStore._instance, probe.store)

    def test_restores_exact_prior_preview_resolver_and_generation(self):
        probe = self.run_fixture()
        self.assertEqual(len(probe.result.failures), 1)
        self.assertIn('fixture stop', probe.result.failures[0][1])
        self.assertFalse(probe.result.errors)
        self.assertIs(native.asset_selection._selection, probe.selection)
        self.assertIs(native.asset_selection._resolver, probe.resolver)
        self.assertEqual(native.asset_selection._generation, 731)
        self.assertIs(native.DataStore._instance, probe.store)
        probe.resolver.cache_clear.assert_called_once_with()
        probe.candidate.cache_clear.assert_called_once_with()
        self.assertEqual(probe.invalidate.call_count, 2)
        restored_selection, restored_resolver, restored_generation = probe.invalidated_states[-1]
        self.assertIs(restored_selection, probe.selection)
        self.assertIs(restored_resolver, probe.resolver)
        self.assertEqual(restored_generation, 731)
        probe.display.quit.assert_called_once_with()

    def test_close_error_cannot_suppress_independent_cleanup(self):
        probe = self.run_fixture(close_error=RuntimeError('injected close failure'))
        self.assertEqual(len(probe.result.errors), 1)
        self.assertIn('injected close failure', probe.result.errors[0][1])
        self.assertIs(native.DataStore._instance, probe.store)
        self.assertIs(native.asset_selection._selection, probe.selection)
        self.assertIs(native.asset_selection._resolver, probe.resolver)
        self.assertEqual(native.asset_selection._generation, 731)
        probe.renderer.close.assert_called_once_with()
        probe.resolver.cache_clear.assert_called_once_with()
        probe.candidate.cache_clear.assert_called_once_with()
        self.assertEqual(probe.invalidate.call_count, 2)
        restored_selection, restored_resolver, restored_generation = probe.invalidated_states[-1]
        self.assertIs(restored_selection, probe.selection)
        self.assertIs(restored_resolver, probe.resolver)
        self.assertEqual(restored_generation, 731)
        probe.display.quit.assert_called_once_with()

    def test_refuses_initialized_subsystem_even_without_a_surface(self):
        probe = self.run_fixture(display_initialized=True)
        self.assertEqual(len(probe.result.skipped), 1)
        probe.display.set_mode.assert_not_called()
        probe.display.quit.assert_not_called()

    def test_refuses_live_renderer_even_without_an_initialized_display(self):
        owner = object()
        probe = self.run_fixture(owners=(owner,))
        self.assertEqual(len(probe.result.skipped), 1)
        self.assertEqual(native.asset_selection._renderer_owners, {owner})
        probe.display.init.assert_not_called()
        probe.display.set_mode.assert_not_called()
        probe.display.quit.assert_not_called()
        probe.configure.assert_not_called()


if __name__ == '__main__':
    unittest.main()
