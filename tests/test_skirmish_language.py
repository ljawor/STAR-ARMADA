"""Deployment labels stay reachable through the authored language pipeline."""
import unittest

from render import i18n
from tools import build_lang_packs as builder, lang_coverage as coverage


class SkirmishLanguageTests(unittest.TestCase):
    def test_deployment_labels_are_catalogued_and_translated(self):
        labels = (
            'Click a start to deploy here.',
            'Gold: resources · Teal: worlds · Rings: starts',
            'Same team = allies. AI allies share vision, not control.',
            'Start {n}',
        )
        self.assertIn('render/skirmish_screen.py', coverage.UI_SURFACE)
        self.assertIn('Start {n}', coverage.EXTRA_UI_KEYS)
        catalogue = coverage.catalogue()
        previous = i18n.language()
        try:
            for code, _ in i18n.LANGUAGES:
                i18n.set_language(code)
                authored = builder.load_source(code)[0] if code != 'en' else None
                for key in labels:
                    with self.subTest(code=code, key=key):
                        self.assertIn(key, catalogue)
                        self.assertIn(key, i18n.load_pack(code))
                        if authored is not None:
                            self.assertTrue(authored[key].strip())
                            self.assertNotEqual(authored[key], key)
                            self.assertEqual(i18n.t(key), authored[key])
                for n in (1, 4, 8):
                    with self.subTest(code=code, start=n):
                        expected = (authored['Start {n}'] if authored else 'Start {n}').format(n=n)
                        self.assertEqual(i18n.t('Start {n}', n=n) + ' ›', expected + ' ›')
        finally:
            i18n.set_language(previous)


if __name__ == '__main__':
    unittest.main()
