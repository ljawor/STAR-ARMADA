"""Completion wrappers extend the existing template without rewriting approved exports."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('completion_wrapper_generator', ROOT / 'tools/art/gen_export_wrappers.py')
assert SPEC is not None and SPEC.loader is not None
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


class CompletionWrappers(unittest.TestCase):
    def test_completion_sheet_is_transposed_to_wrapper_axis_pairs(self):
        self.assertTrue(hasattr(GEN, 'completion_assets'), 'completion sheet reader is missing')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending = root / 'art/manifests/pending'
            pending.mkdir(parents=True)
            sheet = {'schema': 1, 'assets': [dict(identifier='fixture_station', label='Fixture',
                       envelope=[[-1., -2., -3.], [1., 2., 3.]], min_length=5.8,
                       **{'class': 'station'})]}
            (pending / 'S06-BATCH-B7-FIXTURE.json').write_text(json.dumps(sheet), encoding='utf-8')
            result = GEN.completion_assets(root)
            self.assertEqual(result['fixture_station'],
                             ('Fixture', ((-1., 1.), (-2., 2.), (-3., 3.)), 5.8, 11500, 8000, 2000000))


if __name__ == '__main__':
    unittest.main()
