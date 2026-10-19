"""CPU GL-state submission parity; no native GL or relaxed pixel criterion."""
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch
from test_s07_lod_environment import production_namespace, renderer_fixture, entity, noop


def trace(cached, available, authored=True, station=False):
    ns=production_namespace(); ns['is_authored']=lambda binding: authored
    renderer,size,_=renderer_fixture(ns,'rebel:frigate');e=entity('rebel:shipyard' if station else 'rebel:frigate', station)
    if station:
        import ast
        from test_s07_lod_environment import SOURCE, fake_imports
        tree = ast.parse(SOURCE.read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_draw_station')
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), ns)
        renderer._draw_station=lambda item: ns['_draw_station'](renderer,item)
        renderer._draw_station_queue_ring=noop
        renderer.ds=NS(stations={'shipyard':object()})
        e.build_queue=[]
    renderer.state=NS(entities={e.id:e},can_see=lambda *a:True)
    renderer._draw_ship_trail=renderer._draw_ship_glow=noop
    current={'material':None,'shader':None,'lighting':True,'texture':True};calls=[]
    def enable(name,enabled=True):
        if name=='GL_LIGHTING':current['lighting']=enabled
        elif name=='GL_TEXTURE_2D':current['texture']=enabled
    class FakeGL(ModuleType):
        def __getattr__(self,name):
            if name in ('GL_ENABLE_BIT','GL_TEXTURE_BIT'):return 1
            if name.startswith('GL_'):return name
            return noop
    gl=FakeGL('OpenGL.GL');gl.glEnable=enable;gl.glDisable=lambda name:enable(name,False)
    package=ModuleType('OpenGL');package.GL=gl
    for name in list(ns):
        if name.startswith('GL_'):ns[name]=name
    ns['glEnable']=gl.glEnable;ns['glDisable']=gl.glDisable
    ns['glCallList']=lambda key:calls.append(dict(key=key,**current))
    def metal(shininess,spec):current['material']={'shininess':shininess,'spec':spec}
    renderer._material_metal=metal;renderer._material_matte=lambda:metal(0.,(0.,0.,0.))
    def hull_pass(value,authored=False):
        if available and current['shader'] is not None:current['shader']={'materialPass':value,'authoredSurface':float(authored)}
    @contextmanager
    def use(name,**uniforms):
        previous=current['shader']
        if available:current['shader']={'authoredSurface':0.,**uniforms}
        try:yield
        finally:current['shader']=previous
    renderer.materials=NS(available=available,hull_pass=hull_pass,use=use)
    cache={'visible':[(e,None)],'relation':{0:'own'},'owner_color':{0:(.3,.6,.9)},e.id:{'apparent':60.,'size':size}}
    from contextlib import nullcontext
    with (fake_imports() if station else nullcontext()), patch.dict('sys.modules',{'OpenGL':package,'OpenGL.GL':gl}):
        ns['_draw_ships'](renderer,set(),cache if cached else None)
    return calls

class MaterialParityTests(unittest.TestCase):
    def test_authored_station_roles_submit_identical_material_state(self):
        for available in (True, False):
            with self.subTest(shader_available=available):
                cached, uncached = trace(True, available, station=True), trace(False, available, station=True)
                self.assertEqual(len(cached), 6)
                self.assertEqual(cached, uncached)

    def test_legacy_station_accent_retains_original_alloy_material(self):
        for available in (True, False):
            calls = trace(False, available, authored=False, station=True)
            accent = next(c for c in calls if c['key'].endswith(':accent'))
            self.assertEqual(accent['material'], {'shininess':8., 'spec':(.50,.55,.62)})

    def test_authored_roles_submit_identical_material_shader_and_enable_state(self):
        for available in (True,False):
            with self.subTest(shader_available=available):
                cached,uncached=trace(True,available),trace(False,available)
                self.assertEqual(len(cached),6);self.assertEqual(cached,uncached)
    def test_legacy_uncached_accent_retains_original_trim_metal(self):
        for available in (True,False):
            calls=trace(False,available,False)
            accent=next(c for c in calls if c['key'].endswith('_accent'))
            self.assertEqual(accent['material'],{'shininess':12.,'spec':(.85,.85,.85)})
if __name__=='__main__':unittest.main()
