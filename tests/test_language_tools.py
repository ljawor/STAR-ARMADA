"""Reproducible language maintenance, without writing shipped packs in tests."""
import ast
import contextlib
from types import SimpleNamespace
import io
import json
from pathlib import Path
import string
from collections import Counter
import tempfile
import unittest
from unittest.mock import patch

from render import i18n
from tools import build_lang_packs as builder, lang_coverage as coverage

ROOT = Path(__file__).resolve().parent.parent


class LanguageToolsTests(unittest.TestCase):
    def test_builder_regenerates_every_registered_translation_byte_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'en.json').write_bytes((ROOT / 'assets/data/lang/en.json').read_bytes())
            with patch.object(builder, 'LANG_DIR', directory), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(builder.main(), 0)
            for code, _ in i18n.LANGUAGES:
                if code != 'en':
                    with self.subTest(code=code):
                        self.assertTrue((target / f'{code}.json').exists())
                        self.assertEqual((target / f'{code}.json').read_bytes(),
                                         (ROOT / f'assets/data/lang/{code}.json').read_bytes())

    def test_live_catalogue_preserves_shipped_dynamic_and_lowercase_keys(self):
        keys = coverage.catalogue()
        for key in ('+{count} per level', '+{percent}% per level',
                    'Gated hulls: {gated}', 'Retuned station types: {tuned}',
                    'The gain each refit level adds, as a share of the shipped value. 100% doubles it.',
                    'as shipped', 'convoys', 'extra shots', 'level {level}',
                    '{station} is back to the shipped balance.'):
            with self.subTest(key=key):
                self.assertIn(key, keys)
        self.assertNotIn('Recovery requires a detached LAN manager', keys)
        self.assertNotIn('Recovered manager differs from the drained canonical barrier', keys)

    def test_report_uses_registered_languages_including_russian(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(coverage.report(markdown=True), 0)
        for code, _ in i18n.LANGUAGES:
            if code != 'en':
                self.assertIn(f'| {code} |', output.getvalue())
        with patch.object(i18n, 'LANGUAGES', (('en', 'English'), ('qx', 'Test'))), \
                contextlib.redirect_stdout(io.StringIO()) as extra:
            coverage.report(markdown=True)
        self.assertIn('| qx |', extra.getvalue())

    def test_new_player_labels_are_translated_with_unchanged_fields_in_all_packs(self):
        labels = ('COLLECTION POINT', 'Clear collection point',
                  'Not set · new units remain nearby',
                  'Right-click space to set destination.', 'Station upgrades ›',
                  'Reset all tuning', 'Reset this station', 'LAN session failed.',
                  'Reconnect cancelled. You left the LAN match.')
        formatter = string.Formatter()
        fields = lambda text: Counter((name, spec, conversion)
            for _, name, spec, conversion in formatter.parse(text) if name is not None)
        for code, _ in i18n.LANGUAGES:
            pack = json.loads((ROOT / f'assets/data/lang/{code}.json').read_text(encoding='utf-8'))
            for key in labels:
                with self.subTest(code=code, key=key):
                    self.assertIn(key, pack)
                    self.assertTrue(pack[key].strip())
                    if code != 'en':
                        self.assertNotEqual(pack[key], key)
            for key, value in pack.items():
                if key != 'names':
                    with self.subTest(code=code, template=key):
                        self.assertEqual(fields(key), fields(value))

    def test_catalogue_writer_roundtrips_shipped_english_byte_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(coverage, 'LANG_DIR', directory), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(coverage.write_catalogue(), 0)
            self.assertEqual((Path(directory) / 'en.json').read_bytes(),
                             (ROOT / 'assets/data/lang/en.json').read_bytes())

    def test_report_does_not_count_empty_or_non_string_entries_as_translated(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'en.json').write_text(json.dumps({'Label': 'Label', 'names': {'Ship': 'Ship'}}))
            (target / 'ru.json').write_text(json.dumps({'Label': '   ', 'names': {'Ship': None}}))
            with patch.object(coverage, 'LANG_DIR', directory), \
                    patch.object(coverage, 'catalogue', return_value={'Label': 'ui', 'Ship': 'ships'}), \
                    patch.object(i18n, 'LANGUAGES', (('en', 'English'), ('ru', 'Русский'))), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(coverage.report(markdown=True), 0)
            self.assertIn('| ru | 0 | 2 | 2 | 0.0% |', output.getvalue())


class LanguageIOEncodingTests(unittest.TestCase):
    def test_localization_file_io_ignores_non_utf8_defaults(self):
        # Execute actual file-IO expressions without starting the GL probe.
        # pathlib resolves omitted encodings through io.text_encoding. Emulate
        # a non-UTF-8 locale there while leaving explicitly supplied encodings intact.
        for encoding in ('cp1252', 'cp1251'):
            def locale_encoding(requested, stacklevel=2):
                return default_encoding if requested in (None, 'locale') else requested

            default_encoding = encoding
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                settings = target / 'settings.json'
                settings.write_text(json.dumps({'language': 'ru', 'label': 'Русский'},
                                               ensure_ascii=False), encoding='utf-8')
                namespace = dict(ROOT=ROOT, code='ru', saves=target,
                                 self=SimpleNamespace(saves=target),
                                 args=SimpleNamespace(out=target), json=json,
                                 report={'settings_text': ['Русский', 'Язык']})
                calls = []
                for filename in ('test_language_tools.py', 'probe_i18n_russian.py',
                                 'test_i18n_russian.py'):
                    source = ROOT / 'tests' / filename
                    tree = ast.parse(source.read_text(encoding='utf-8'))
                    for node in ast.walk(tree):
                        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                            continue
                        if node.func.attr == 'read_text' and filename != 'test_language_tools.py':
                            calls.append((filename, node))
                        elif node.func.attr == 'read_text' and 'assets/data/lang/' in ast.unparse(node):
                            calls.append((filename, node))
                        elif node.func.attr == 'write_text' and 'report.json' in ast.unparse(node):
                            calls.append((filename, node))
                self.assertEqual(len(calls), 5)
                for filename, node in calls:
                    with self.subTest(default=encoding, file=filename, line=node.lineno):
                        # The UTF-8 control is independent of the emulated locale.
                        expression = compile(ast.Expression(node), filename, 'eval')
                        if node.func.attr == 'read_text':
                            expected = eval(expression, namespace)
                            with patch.object(io, 'text_encoding', locale_encoding):
                                self.assertEqual(eval(expression, namespace), expected)
                        else:
                            with patch.object(io, 'text_encoding', locale_encoding):
                                eval(expression, namespace)
                            self.assertEqual((target / 'report.json').read_bytes(),
                                             (json.dumps(namespace['report'], ensure_ascii=False,
                                                         indent=2) + '\n').encode('utf-8'))


if __name__ == '__main__':
    unittest.main()
