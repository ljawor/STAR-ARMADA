"""CPU campaign entry acceptance; deliberately not a real-GL campaign frame.

MenuStack paints CPU controls and handles a real click; the production main
START_MISSION branch and extracted start_game execute without rewriting them.
Only view/audio constructors are doubles. Resolver/configure are never mocked.
"""
import ast
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_lan_main import factories, ROOT
from game.data.store import DataStore
from game.benchmark import state_hash
from render import asset_selection as selection
from render import menus
import pygame


class CampaignPreviewEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in dict(USER_DIR=root, SAVES_DIR=root / 'saves',
                                SETTINGS_PATH=root / 'settings.json',
                                CAMPAIGN_PATH=root / 'campaign.json',
                                BALANCE_PATH=root / 'balance.json').items():
            p = patch.object(menus, name, str(value))
            p.start()
            self.addCleanup(p.stop)
        self.root = root
        mouse = patch.object(pygame.mouse, 'get_pos', return_value=(-1, -1))
        mouse.start()
        self.addCleanup(mouse.stop)
        old_store = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', old_store)
        saved = (selection._selection, selection._resolver, selection._generation,
                 selection._renderer_owners)
        def restore():
            (selection._selection, selection._resolver, selection._generation,
             selection._renderer_owners) = saved
            selection.invalidate_geometry_helpers()
        self.addCleanup(restore)
        selection._renderer_owners = set()
        selection._resolver = None
        selection._selection = {'model_preview': False, 'visual_packs': []}
        owned_font = not pygame.font.get_init()
        if owned_font:
            def close_font():
                from render.clean_classic import font
                font.cache_clear()
                pygame.font.quit()
            self.addCleanup(close_font)
        self.menu = menus.MenuStack(800, 600)
        self.addCleanup(self.menu.close)
        self.manifest = json.loads((ROOT / 'assets/models/manifests/alliance_frigate.json').read_text())

    def click(self, action):
        button = next(b for b in self.menu.buttons if b['action'] == action)
        self.menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                 button=1, pos=button['rect'].center))

    def launch(self, preview, *, broken_close=False, wrong_selection=False):
        settings = dict(menus.DEFAULT_SETTINGS, model_preview=preview,
                        cinematics_enabled=False)
        menus.save_settings(settings)
        # Save and progression sentinels must survive the actual launch branch.
        (self.root / 'saves').mkdir(exist_ok=True)
        save = self.root / 'saves' / 'campaign-preserve.json'
        save.write_bytes(b'campaign save sentinel')
        progress = self.root / 'campaign.json'
        progress.write_bytes(b'{"mission_index":0}')
        menus.load_campaign_progress()  # Migrate only inside the isolated root.
        before = {p: p.read_bytes() for p in (save, progress, self.root / 'settings.json')}
        self.menu.screen = 'campaign'
        self.menu.buttons = []
        self.menu._screen_campaign()
        self.click('select_mission')
        self.assertEqual(self.menu.screen, 'briefing')
        self.menu.buttons = []
        self.menu._screen_briefing()
        self.click('launch_mission')
        self.assertEqual(self.menu.result, menus.MenuResult.START_MISSION)
        events = []
        selection.configure({'model_preview': not preview})
        generation = selection.diagnostics()['generation']
        old_token = selection.attach_renderer()
        self.addCleanup(selection.release_renderer, old_token)
        def close_old():
            events.append('old-close')
            if not broken_close:
                selection.release_renderer(old_token)
        ns = factories()
        ns.update(menu=self.menu, SETTINGS=settings, mode='menu',
                  renderer=SimpleNamespace(close=close_old),
                  save_settings=menus.save_settings, MenuResult=menus.MenuResult,
                  res=self.menu.result, payload=self.menu.result_payload)
        if wrong_selection:
            ns['SETTINGS'] = dict(settings, model_preview=not preview)
        def renderer(state, camera):
            events.append('new-renderer')
            self.assertNotIn(old_token, selection._renderer_owners)
            self.assertEqual(selection.diagnostics()['generation'], generation + 1)
            self.assertEqual(selection.diagnostics()['mode'], 'preview' if preview else 'legacy')
            key = selection.gpu_cache_key('rebel:frigate', 'base', 'legacy')
            mesh = selection.mesh_for('rebel:frigate')
            if preview:
                self.assertIsNotNone(mesh)
                self.assertIn(self.manifest['revision'], key)
            else:
                self.assertIsNone(mesh)
                self.assertEqual(key, 'legacy')
            token = selection.attach_renderer()
            self.addCleanup(selection.release_renderer, token)
            return SimpleNamespace(close=lambda: selection.release_renderer(token))
        ns['Renderer'] = renderer
        tree = ast.parse((ROOT / 'main.py').read_text())
        branch = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                      and isinstance(n.test, ast.Compare)
                      and any(isinstance(c, ast.Attribute) and c.attr == 'START_MISSION'
                              for c in n.test.comparators))
        code = ast.Module(body=copy.deepcopy(branch.body), type_ignores=[])
        exec(compile(ast.fix_missing_locations(code), str(ROOT / 'main.py'), 'exec'), ns)
        self.addCleanup(ns['presentation'].cleanup)
        self.assertEqual(events, ['old-close', 'new-renderer'])
        self.assertEqual(ns['mode'], 'game')
        self.assertEqual(ns['mission_def'], self.menu.result_payload)
        self.assertIsNotNone(ns['gm'].mission)
        self.assertEqual(ns['recording'].user_dir, str(self.root))
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data, str(path))
        self.assertFalse((self.root / 'balance.json').exists())
        self.assertFalse((self.root / 'replays').exists())
        digest = state_hash(ns['state'])
        ns['renderer'].close()
        print('campaign-entry', json.dumps(dict(preview=preview, events=events,
              revision=self.manifest['revision'] if preview else None, state_hash=digest)))
        return digest

    def test_campaign_launch_preview_on_off_preserves_authoritative_state(self):
        self.assertEqual(self.launch(True), self.launch(False))

    def test_negative_ordering_control_refuses_live_old_renderer(self):
        with self.assertRaisesRegex(RuntimeError, 'renderers closed'):
            self.launch(True, broken_close=True)
        print('campaign-negative-ordering: real configure refused unreleased old owner')

    def test_negative_selection_control_detects_wrong_preview(self):
        with self.assertRaisesRegex(AssertionError, "'legacy' != 'preview'"):
            self.launch(True, wrong_selection=True)
        print('campaign-negative-selection: renderer observation caught wrong preview mode')


if __name__ == '__main__':
    unittest.main()
