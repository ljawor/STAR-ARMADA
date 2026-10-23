"""CPU checks for the exact native review scene and camera scale contract."""
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ImperiumFleetCaptureTests(unittest.TestCase):
    def test_native_review_plan_uses_live_catalogue_and_heading_relative_cameras(self):
        path=ROOT/'tools/render/verify_imperium_fleet.py'
        self.assertTrue(path.is_file(),'Native fleet review capture adapter is missing')
        spec=importlib.util.spec_from_file_location('imperium_capture_test',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        plan=module.camera_plan(length=100,center=[0,10,0],heading_degrees=90)
        self.assertEqual(set(plan),{'close','rear','tactical'})
        self.assertEqual(plan['close']['yaw'],138)
        self.assertEqual(plan['rear']['yaw'],310)
        self.assertEqual(plan['close']['target'],[0,10,0])
        self.assertGreater(plan['tactical']['distance'],plan['close']['distance'])
        self.assertEqual(module.PACK_NAME,'imperium-fleet-prototypes')
        self.assertEqual(len(module.ROWS),7)
        self.assertEqual(getattr(module,'LIVE_IDS',{}).get('convoy'),
                         'imperial_crew_transport',
                         'Convoy manifest template is not a live ship catalogue ID')

if __name__=='__main__':unittest.main()
