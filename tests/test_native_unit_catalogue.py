"""CPU catalogue census and REAL paid queue/completion audit (no native/GL)."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import tempfile
import unittest
from pathlib import Path

from tools.render.audit_unit_builds import isolated_catalogue, inventory, audit_catalogue


class NativeUnitCatalogueTests(unittest.TestCase):
    def test_manifest_exactly_covers_datastore_without_duplicates(self):
        with isolated_catalogue() as ds:
            rows = inventory(ds)
            keys = [(r['kind'], r['id']) for r in rows]
            expected = {('ship', key) for key in ds.ships} | {('station', key) for key in ds.stations}
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(set(keys), expected)
            self.assertTrue(all(r['classification'] in ('buildable', 'auto-spawned', 'nonbuildable') for r in rows))
            self.assertTrue(all(r['name'] and r['binding'] for r in rows))

    def test_every_declared_buildable_pays_queues_and_completes(self):
        scratch = Path.home() / '.hermes/cache/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='sa-catalogue-test-', dir=scratch) as output:
            report = audit_catalogue(Path(output))
            self.assertEqual(report['inventory_count'], report['result_count'])
            self.assertEqual(report['failures'], [], report['failures'])
            cases = [(r['kind'], r['id'], c['faction']) for r in report['rows'] for c in r['cases']]
            variants = {(r['kind'], r['id'], v['faction']) for r in report['rows'] for v in r['variants']}
            self.assertEqual(len(cases), len(set(cases)))
            self.assertEqual(set(cases), variants)
            self.assertEqual(report['paid_cases'], report['passed_paid_cases'])
            self.assertEqual(report['variant_count'], len(cases))
            for row in report['rows']:
                with self.subTest(kind=row['kind'], id=row['id']):
                    if row['classification'] == 'buildable':
                        self.assertTrue(row['cases'])
                        for case in row['cases']:
                            if case['classification'] != 'buildable':
                                self.assertEqual(case['test_scope'], 'factory-only visual candidate')
                                self.assertFalse(case['paid'] or case['queued'] or case['completed'])
                                self.assertGreater(case['mesh_triangles'], 0)
                                continue
                            self.assertTrue(case['paid'])
                            self.assertTrue(case['queued'])
                            self.assertTrue(case['completed'])
                            self.assertEqual(case['entity']['data_id'], row['id'])
                            self.assertTrue(case['binding'])
                            self.assertGreater(case['mesh_triangles'], 0)
                    else:
                        self.assertEqual(row['test_scope'], 'factory-only visual candidate')


if __name__ == '__main__':
    unittest.main()
