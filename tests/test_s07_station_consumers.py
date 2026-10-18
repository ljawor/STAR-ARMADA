"""Selected Imperial station consumers, paired with protected stock controls."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import game.core.manager
from game.core.entity import Entity
from game.core.vectors import Vec3
from render.camera import Camera
from render.input import InputController
from render.renderer import Renderer
from render.authored_mesh import _load_profile
from render.camera_geometry import station_radius, station_bounds
from render import asset_selection

ROOT = Path(__file__).resolve().parents[1]

class SelectedStationConsumers(unittest.TestCase):
    def fixture(self):
        entity = Entity(id=3,kind='station',owner=0,data_id='command_station',
                        radius=130,pos=Vec3(0,0,0))
        entity.is_station = True
        state = SimpleNamespace(players={0:SimpleNamespace(faction='imperial')},
                                entities={3:entity},can_see=lambda *_:True)
        renderer = Renderer.__new__(Renderer)
        renderer.state, renderer.local_player, renderer.time = state,0,0.
        renderer._px_per_world = lambda *a,**kw:100.
        row = json.loads((ROOT/'art/manifests/pending/S06-BATCH-B7-IMPERIAL-STATIONS.json').read_text())['assets'][0]
        mesh = _load_profile(ROOT/row['mesh'],row['identifier'],tuple(zip(*row['envelope'])),row['min_length'])
        return state,entity,renderer,mesh

    def selection(self,mesh):
        self.addCleanup(asset_selection.invalidate_geometry_helpers)
        asset_selection.invalidate_geometry_helpers()
        return patch.object(asset_selection,'mesh_for',lambda b:mesh if b=='imperial:command_station' else None)

    def test_stock_radius_shield_and_contact_are_unchanged(self):
        state,e,r,_ = self.fixture()
        with patch.object(asset_selection,'mesh_for',lambda _:None):
            self.assertEqual(r._station_visual_radius(e),e.radius)
            self.assertEqual(r._shield_radius(e),e.radius*1.35)
            fx=dict(kind='hull_hit',target_id=e.id,pos=(130.,0.,0.),normal=(1.,0.,0.))
            self.assertIs(r._visual_hit(fx),fx)

    def test_selected_radius_and_shield_use_all_role_geometry(self):
        _,e,r,mesh=self.fixture()
        with self.selection(mesh):
            expected=station_radius(e.data_id,'imperial')*(e.radius/50.)
            self.assertNotEqual(expected,e.radius)
            self.assertAlmostEqual(r._station_visual_radius(e),expected)
            self.assertAlmostEqual(r._shield_radius(e),expected*1.08)

    def test_selected_contact_remaps_without_mutating_sim_effect_and_hidden_is_unchanged(self):
        from copy import deepcopy
        state,e,r,mesh=self.fixture()
        fx=dict(kind='hull_hit',target_id=e.id,pos=(130.,0.,0.),normal=(1.,0.,0.))
        before=deepcopy(fx)
        with self.selection(mesh):
            result=r._visual_hit(fx)
            self.assertTrue(result.get('visual_contact'))
            self.assertNotEqual(result['pos'],fx['pos'])
            self.assertEqual(fx,before)
            state.can_see=lambda *_:False
            self.assertIs(r._visual_hit(fx),fx)

    def test_selected_station_hull_is_pickable_while_stock_keeps_center_affordance(self):
        state,e,_,mesh=self.fixture()
        cam=Camera(960,640)
        cam.world_to_screen=lambda x,y,z:(x,y)
        cam.eye_position=lambda:(0.,0.,1000.)
        cam.basis=lambda:((1.,0.,0.),(0.,1.,0.),(0.,0.,-1.))
        cam._station_angle=lambda:0.
        control=InputController(state,cam,SimpleNamespace(),SimpleNamespace())
        mouse=(100.,0.)
        with patch.object(asset_selection,'mesh_for',lambda _:None):
            self.assertEqual(control._ship_pick_distance(e,(0.,0.),mouse,28.),100.)
        with self.selection(mesh):
            self.assertLess(control._ship_pick_distance(e,(0.,0.),mouse,28.),28.)

if __name__=='__main__': unittest.main()
