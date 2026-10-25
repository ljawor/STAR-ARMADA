"""LAN Host labels survive scanning, translation and byte-exact regeneration."""
import contextlib
from collections import Counter
import io
import json
from pathlib import Path
import string
import tempfile
import unittest
from unittest.mock import patch

from render import i18n
from tools import build_lang_packs as builder, lang_coverage as coverage

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = (
    'Humans {count} / {capacity}', 'AI {count} / {capacity}',
    'Human {n}', 'AI {n}', 'Unused {n}', 'Start {n}',
)
LABELS = TEMPLATES + (
    'Host a multiplayer game', 'Session settings', 'Humans vs AI', 'Free for all',
    'FLEET ROSTER', 'Nickname', 'TCP port', 'Apply setup', 'Create lobby',
    'Hosting opens a lobby. It does not launch the match.',
)


class LANLanguageTests(unittest.TestCase):
    def test_host_surface_and_templates_are_visible_to_catalogue(self):
        self.assertIn('render/lan_screen.py', coverage.UI_SURFACE)
        catalogue = coverage.catalogue()
        for key in LABELS:
            with self.subTest(key=key):
                self.assertIn(key, catalogue)
        for key in TEMPLATES:
            with self.subTest(template=key):
                self.assertIn(key, coverage.EXTRA_UI_KEYS)

    def test_host_labels_are_authored_with_exact_format_field_parity(self):
        formatter = string.Formatter()

        def fields(text):
            return Counter((name, spec, conversion)
                           for _, name, spec, conversion in formatter.parse(text)
                           if name is not None)

        previous = i18n.language()
        try:
            for code, _ in i18n.LANGUAGES:
                pack = json.loads((ROOT / f'assets/data/lang/{code}.json').read_text(encoding='utf-8'))
                authored = builder.load_source(code)[0] if code != 'en' else None
                i18n.set_language(code)
                for key in LABELS:
                    with self.subTest(code=code, key=key):
                        self.assertIn(key, pack)
                        self.assertTrue(pack[key].strip())
                        self.assertEqual(fields(key), fields(pack[key]))
                        if authored is not None:
                            self.assertEqual(pack[key], authored[key])
                            if key in TEMPLATES:
                                self.assertNotEqual(pack[key], key)
                for key in TEMPLATES:
                    for n in (1, 4, 8):
                        with self.subTest(code=code, template=key, n=n):
                            self.assertIn(key, pack)
                            values = dict(n=n, count=n, capacity=8)
                            self.assertEqual(i18n.t(key, **values), pack[key].format(**values))
        finally:
            i18n.set_language(previous)

    def test_live_catalogue_and_all_packs_regenerate_byte_exactly(self):
        # Exercise the actual documented pipeline, without writing shipped files.
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(coverage, 'LANG_DIR', directory), \
                    patch.object(builder, 'LANG_DIR', directory), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(coverage.write_catalogue(), 0)
                self.assertEqual(builder.main(), 0)
            for code, _ in i18n.LANGUAGES:
                with self.subTest(code=code):
                    self.assertEqual((Path(directory) / f'{code}.json').read_bytes(),
                                     (ROOT / f'assets/data/lang/{code}.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
