"""Bounded real-fixture export checks; no renderer or game loop."""
import importlib.util
import json
import hashlib
from pathlib import Path
import unittest
from game.graphics_benchmark import make_fixture, semantic_inventory
from game.benchmark import state_hash

ROOT = Path(__file__).resolve().parents[1]


class RenderSnapshotTests(unittest.TestCase):
    def test_real_fixture_export_is_read_only(self):
        self.assertTrue((ROOT / 'tools/render/dump_snapshot.py').exists(), 'snapshot exporter missing')
        from tools.render.dump_snapshot import build_snapshot
        from render.ship_sizes import ship_size
        fixture = make_fixture('four-player-combat-v1')
        st, ds = fixture.manager.state, fixture.manager.ds
        before = state_hash(st)
        payload = build_snapshot(fixture)
        self.assertEqual(before, state_hash(st))
        self.assertEqual(payload['state_sha256'], before)
        self.assertEqual(payload['fixture'], fixture.name)
        self.assertEqual(payload['metadata']['visibility'], 'player0-detection')
        self.assertEqual(payload['metadata']['inventory'], semantic_inventory(st))
        expected = {e.id for e in st.entities.values() if e.alive and not e.is_planet and st.can_see(0, e.id)}
        self.assertEqual({i['entity_id'] for i in payload['instances']}, expected)
        self.assertEqual(payload['camera']['target'], list(fixture.camera.target))
        self.assertTrue(payload['metadata']['omitted_planets'])
        assets = {a['binding']: a for a in payload['assets']}
        for i in payload['instances']:
            e = st.entities[i['entity_id']]
            self.assertEqual(i['position'], list(e.pos.to_tuple()))
            self.assertEqual(i['yaw'], e.yaw)
            self.assertEqual(i['scale'], e.radius / 50. if e.is_station else ship_size(ds, e.data_id, st.players[e.owner].faction).scale)
            self.assertIn(i['binding'], assets)
            if e.data_id == 'trade_convoy':
                self.assertEqual(i['binding'], 'imperial:convoy')
        for a in assets.values():
            path = (ROOT / 'assets' / a['path']).resolve()
            self.assertTrue(path.is_relative_to(ROOT / 'assets'))
            raw = path.read_bytes(); mesh = json.loads(raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), a['sha256'])
            self.assertEqual(len(mesh['vertices']), a['vertex_count'])
            self.assertEqual(sum(len(rows) for rows in mesh['batches'].values()), a['triangle_count'])
        self.assertEqual(payload, build_snapshot(fixture))
    def test_cli_visibility_and_file(self):
        import os
        import subprocess
        import tempfile
        import sys
        from render_bridge.protocol import decode, WORLD
        script = ROOT / 'tools/render/dump_snapshot.py'
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            out = Path(temp) / 'real.snap'
            command = [sys.executable, str(script), '--fixture', 'four-player-combat-v1',
                       '--units', '600', '--all-visible', '--out', str(out)]
            result = subprocess.run(command, cwd=temp, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.exists(), 'CLI did not write a snapshot')
            frame = decode(out.read_bytes())
            self.assertEqual(frame.kind, WORLD)
            self.assertEqual(frame.tick, 0)
            self.assertEqual(frame.payload['metadata']['visibility'], 'omniscient-diagnostic')
            self.assertEqual(len(frame.payload['instances']), 752)
            self.assertEqual(len(frame.payload['metadata']['omitted_planets']), 8)
            report = json.loads(result.stdout)
            self.assertEqual(report['instances'], 752)
            self.assertEqual(report['state_sha256'], frame.payload['state_sha256'])
            bad = subprocess.run([sys.executable, str(script), '--units', '599', '--out', str(out)],
                                 cwd=temp, text=True, capture_output=True)
            self.assertNotEqual(bad.returncode, 0)
    def test_catalogue_runtime_mesh_closure(self):
        from tools.render import dump_snapshot
        self.assertTrue(hasattr(dump_snapshot, 'build_catalogue'), 'catalogue export missing')
        fixture = make_fixture('four-player-combat-v1')
        before = state_hash(fixture.manager.state)
        payload = dump_snapshot.build_catalogue(fixture)
        self.assertEqual(before, state_hash(fixture.manager.state))
        self.assertEqual(payload['state_sha256'], before)
        self.assertEqual(payload['metadata']['visibility'], 'catalogue-inspection-not-gameplay')
        registry = json.loads((ROOT / 'assets/models/registry.json').read_text())
        expected = {r['binding'] for r in registry['bindings'] if r['status'] == 'core'}
        self.assertEqual(len(expected), 103)
        self.assertEqual({i['binding'] for i in payload['instances']}, expected)
        self.assertEqual({a['binding'] for a in payload['assets']}, expected)
        self.assertEqual(len({a['path'] for a in payload['assets']}), 103)
        self.assertEqual(len(payload['instances']), 103)
        for a in payload['assets']:
            raw = (ROOT / 'assets' / a['path']).read_bytes()
            mesh = json.loads(raw)
            self.assertEqual(a['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(a['vertex_count'], len(mesh['vertices']))
            self.assertEqual(a['triangle_count'], mesh['triangle_count'])
        import subprocess
        import sys
        import os
        import tempfile
        from render_bridge.protocol import decode
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            out = Path(temp) / 'catalogue.snap'
            result = subprocess.run([sys.executable, str(ROOT / 'tools/render/dump_snapshot.py'),
                                     '--catalogue', '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(decode(out.read_bytes()).payload['assets']), 103)


if __name__ == '__main__':
    unittest.main()
