"""Retain reproducible raw CPU matrix/control receipts; no production writes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import test_s07_selected_geometry_matrix as matrix

parser = argparse.ArgumentParser()
parser.add_argument('--negative-selection',action='store_true')
args = parser.parse_args()
output = ROOT/'artifacts/s07-runtime-acceptance'

class Results(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.cases = []
    def addSubTest(self,test,subtest,error):
        self.cases.append(dict(test=test._testMethodName,params=dict(subtest.params),passed=error is None))
        return super().addSubTest(test,subtest,error)


def protected_hashes():
    paths = list((ROOT/'assets/models').rglob('*.json'))
    paths += [ROOT/'art/manifests'/name for name in ('approvals.json','pipeline.json','pipeline_policy.json')]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

# Install a nonempty outer catalogue, so cleanup is verified by exact object
# identity and row membership, rather than merely restoring an empty singleton.
prior_store = matrix.DataStore(assets_dir=str(ROOT/'assets/data'),mods=[],balance={})
prior_ship_rows = set(prior_store.ships)
prior_station_rows = set(prior_store.stations)
prior_selection = (matrix.selection._selection,matrix.selection._resolver,matrix.selection._generation)
protected_before = protected_hashes()
start = time.perf_counter()
loader = unittest.TestLoader()
name = 'test_s07_selected_geometry_matrix'
if args.negative_selection:
    name += '.SelectedGeometryMatrixTests.test_selected_revision_payload_and_actual_dispatch_closure'
suite = loader.loadTestsFromName(name)
runner = unittest.TextTestRunner(verbosity=2,resultclass=Results)
if args.negative_selection:
    # De-fix only the live selected-mesh seam; configure still builds the real
    # opt-in resolver and all manifests remain unchanged. The closure must fail.
    with patch.object(matrix.selection,'mesh_for',return_value=None):
        result = runner.run(suite)
else:
    result = runner.run(suite)
seconds = time.perf_counter()-start
isolation = dict(datastore_identity_restored=matrix.DataStore._instance is prior_store,
                 datastore_ship_rows_restored=set(matrix.DataStore.get().ships) == prior_ship_rows,
                 datastore_station_rows_restored=set(matrix.DataStore.get().stations) == prior_station_rows,
                 selection_preferences_identity_restored=matrix.selection._selection is prior_selection[0],
                 resolver_identity_restored=matrix.selection._resolver is prior_selection[1],
                 generation_restored=matrix.selection._generation == prior_selection[2],
                 protected_bytes_unchanged=protected_before == protected_hashes())
rows = matrix.SelectedGeometryMatrixTests.rows
summary = dict(mode='negative-selection' if args.negative_selection else 'positive',
               head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               test_module_sha256=hashlib.sha256((ROOT/'tests/test_s07_selected_geometry_matrix.py').read_bytes()).hexdigest(),
               tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
               subtests=len(result.cases),failed_subtests=sum(not c['passed'] for c in result.cases),
               seconds=seconds,core_bindings=len(rows),consumers=sum(len(r['consumers']) for r in rows),
               categories=dict(Counter(r['category'] for r in rows)),isolation=isolation,
               protected_file_count=len(protected_before))
report = dict(summary=summary,rows=rows,cases=result.cases,
              protected_sha256=protected_before,
              coverage=dict(ship_consumer_cases=sum(c['test'].startswith('test_ship_consumers') for c in result.cases),
                            orbital_station_cases=sum(c['test'].startswith('test_40_station') for c in result.cases),
                            attached_cases=sum(c['test'].startswith('test_attached') for c in result.cases)),
              limits=[
                  'CPU only; no GL, pixels, materials, VFX/shield shells, construction preview or packaging acceptance.',
                  'Asteroid prop: selected revision/payload closure only, no per-instance field draw transforms.',
                  'One oblique center-out contact ray per free-ship/station rotation; fallback membership is checked, not exact nearest-point optimality.',
                  'Ships: three yaws and two viewport heights (640 and 64), plus real 180-unit close-zoom refresh and independent near-plane box rejection.',
                  'Stations: three animation rotations, current-owner family and capture radius; real close-zoom refresh and near-plane box rejection.',
                  'Attached: 16 installations x six slots and eight satellite bindings x eight orbital placements; one camera view per placement.',
                  'The south surface slot is deliberately back-face pick-rejected under the legal positive-pitch camera, not claimed selectable from below.',
                  'Input is driven through real _single_select; ordinary ship/station 640px picks explicitly defeat the center fallback. No OS event/GL loop.',
                  'Visibility uses owned entities in real GameState; enemy fog/sensor behavior is outside this geometry matrix.',
                  'No orbit time evolution, every camera/heading combination, negative scale, external packs or approval-policy revalidation.'])
stem = 'geometry-negative-selection' if args.negative_selection else 'geometry-results'
(output/(stem+'.json')).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print('RUN_SUMMARY '+json.dumps(summary,sort_keys=True),flush=True)
if not all(isolation.values()):
    raise SystemExit('fixture isolation or byte preservation failed')
if args.negative_selection:
    if result.wasSuccessful() or len(result.failures)!=102 or result.errors:
        raise SystemExit('negative selected-mesh control did not yield exactly 102 binding assertion failures')
else:
    if not result.wasSuccessful():
        raise SystemExit(1)
