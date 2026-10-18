"""Pending catalogue meshes must pass the actual immutable runtime loader."""
import json
from pathlib import Path
import unittest
from render.authored_mesh import _load_profile

ROOT = Path(__file__).resolve().parents[1]


class CompletionPayloads(unittest.TestCase):
    def test_all_27_payloads_load_at_their_exact_declared_envelopes(self):
        rows = [row for sheet in sorted((ROOT/'art/manifests/pending').glob('S06-BATCH-B[789]-*.json'))
                for row in json.loads(sheet.read_text(encoding='utf-8'))['assets']]
        self.assertEqual(len(rows), 27)
        for row in rows:
            with self.subTest(binding=row['binding']):
                mesh = _load_profile(ROOT/row['mesh'], row['identifier'],
                                     tuple(zip(*row['envelope'])), row['min_length'])
                self.assertEqual(set(mesh), {'base','dark','trim','accent','lit','cool'})
                self.assertTrue(all(mesh.values()))
                self.assertGreater(sum(map(len, mesh.values())), 1800)


if __name__ == '__main__':
    unittest.main()
