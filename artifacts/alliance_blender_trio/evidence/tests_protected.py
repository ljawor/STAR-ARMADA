"""Focused tests with five persistence redirects + outer native write barrier."""
from pathlib import Path
import sys,unittest,os
import capture_slice as h
S=Path(__file__).parent;out=S/'protected-focused-tests';out.mkdir()
h.isolate(h.LIVE,out)
# Lazy-import subprocesses need the source path despite the isolated scratch cwd.
os.environ['PYTHONPATH']=str(h.LIVE)
sys.path.insert(0,str(h.LIVE/'tests'))
modules=['test_alliance_blender_trio','test_alliance_blender_battleship','test_alliance_visual_slice',
         'test_ship_material_passes','test_fleet_materials','test_ship_sizes','test_detmath',
         'test_faction_ships','test_faction_stations','test_faction_visuals']
suite=unittest.defaultTestLoader.loadTestsFromNames(modules)
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
