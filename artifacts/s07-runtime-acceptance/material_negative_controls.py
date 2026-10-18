"""Prove material-mode and GPU-delete acceptance tests reject broken behavior."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import game.core
from render.fleet_materials import FleetMaterials
import render.renderer as renderer
from test_ship_material_passes import ShipMaterialPassTests
from test_model_context_lifecycle import ModelContextLifecycleTests
original=FleetMaterials.hull_pass
controls=[('authored_leaks_to_legacy',patch.object(FleetMaterials,'hull_pass',lambda self,value,authored=False:original(self,value,True)),ShipMaterialPassTests('test_cached_roles_preserve_explicit_unselected_sibling')),
          ('authored_disabled_in_preview',patch.object(FleetMaterials,'hull_pass',lambda self,value,authored=False:original(self,value,False)),ShipMaterialPassTests('test_cached_roles_use_their_actual_shader_and_emissive_state'))]
for name,scope,test in controls:
    print('\nCONTROL',name,flush=True)
    with scope:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([test]))
    assert result.failures and not result.errors,(name,result)
print('Both material-mode sabotage controls produced assertion failures; no production files modified.')
