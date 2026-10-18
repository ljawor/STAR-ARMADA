"""Production construction seam: selected scaffold only, immutable queue and stock fallback."""
from contextlib import ExitStack, nullcontext
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import game.core.manager
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.systems.unit_factory import UnitFactory
from game.data.store import DataStore
from render import renderer as module, asset_selection
from render.authored_mesh import _load_profile
from OpenGL import GL

ROOT=Path(__file__).resolve().parents[1]

class ConstructionSelection(unittest.TestCase):
    def fixture(self):
        state=GameState()
        state.players[0]=PlayerState(0,faction='imperial')
        builder=UnitFactory(state).spawn_ship('imperial_constructor',0,Vec3())
        builder.build_queue=[dict(kind='station',item='shipyard',pos=(400.,0.,0.),time_left=1.,total=2.)]
        r=module.Renderer.__new__(module.Renderer)
        r.state,r.ds,r.local_player,r.time=state,DataStore.get(),0,0.
        r._in_front=lambda *_:True
        r._owner_color=lambda _:(.2,.4,.8)
        r._draw_station_outline=Mock()
        r._emit_detail_mesh=Mock()
        r.materials=SimpleNamespace(use=lambda *a,**kw:nullcontext(),hull_pass=lambda *a:None,available=False)
        return state,r

    def gl_scope(self,stack):
        mocks={}
        for name,value in vars(module).items():
            if name.startswith('gl') and callable(value):
                mocks[name]=stack.enter_context(patch.object(module,name,Mock()))
        for name in ('glPushAttrib','glPopAttrib','glDisable','glEnable','glDepthMask',
                     'glMaterialfv','glMaterialf'):
            stack.enter_context(patch.object(GL,name,Mock()))
        return mocks

    def test_selected_imperial_station_construction_outline_uses_candidate(self):
        _,r=self.fixture()
        with ExitStack() as stack:
            self.gl_scope(stack)
            stack.enter_context(patch.object(asset_selection,'mesh_for',lambda b:{} if b=='imperial:shipyard' else None))
            r._draw_construction_sites()
        r._draw_station_outline.assert_called_once()
        self.assertEqual(r._draw_station_outline.call_args.args[:3],('shipyard','imperial',(400.,0.,0.)))

    def test_authored_scaffold_draws_six_roles_at_progress_height_and_preserves_queue(self):
        state,r=self.fixture()
        row=next(a for a in json.loads((ROOT/'art/manifests/pending/S06-BATCH-B9-CONSTRUCTION.json').read_text())['assets'] if a['class']=='scaffold')
        mesh=_load_profile(ROOT/row['mesh'],row['identifier'],tuple(zip(*row['envelope'])),row['min_length'])
        before=deepcopy(state.to_dict(precise=True))
        with ExitStack() as stack:
            mocks=self.gl_scope(stack)
            stack.enter_context(patch.object(asset_selection,'mesh_for',lambda b:mesh if b=='shared:construction_scaffold' else None))
            r._draw_construction_sites()
        self.assertEqual(r._emit_detail_mesh.call_count,6)
        self.assertEqual([c.args[0] for c in r._emit_detail_mesh.call_args_list],list(mesh.values()))
        radius=r.ds.stations['shipyard'].radius
        self.assertIn(unittest.mock.call(radius/50.,radius/50.*.7,radius/50.),mocks['glScalef'].call_args_list)
        self.assertEqual(state.to_dict(precise=True),before)
        # The legacy lattice is replaced; only the separate green progress arc remains.
        self.assertEqual(mocks['glBegin'].call_args_list,[unittest.mock.call(module.GL_LINE_STRIP)])

    def test_stock_scaffold_is_still_legacy_and_unselected_imperial_outline_absent(self):
        _,r=self.fixture()
        with ExitStack() as stack:
            mocks=self.gl_scope(stack)
            stack.enter_context(patch.object(asset_selection,'mesh_for',lambda _:None))
            r._draw_construction_sites()
        r._draw_station_outline.assert_not_called()
        r._emit_detail_mesh.assert_not_called()
        self.assertEqual(len(mocks['glBegin'].call_args_list),4)

if __name__=='__main__': unittest.main()
