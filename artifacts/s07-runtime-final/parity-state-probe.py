"""CPU record of production cached/uncached material state; never native GL."""
from contextlib import contextmanager
import json
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import patch
from test_s07_lod_environment import production_namespace, renderer_fixture, entity, noop


def trace(cached, available):
    ns = production_namespace()
    renderer, size, _ = renderer_fixture(ns, 'rebel:frigate')
    e = entity('rebel:frigate')
    renderer.state = NS(entities={e.id: e}, can_see=lambda *a: True)
    renderer._draw_ship_trail = renderer._draw_ship_glow = noop
    current = {'material': None, 'shader': None, 'lighting': True, 'texture': True}
    calls = []

    def enable(name, enabled=True):
        if name == 'GL_LIGHTING':
            current['lighting'] = enabled
        elif name == 'GL_TEXTURE_2D':
            current['texture'] = enabled

    class GL(ModuleType):
        def __getattr__(self, name):
            if name in ('GL_ENABLE_BIT', 'GL_TEXTURE_BIT'):
                return 1
            if name.startswith('GL_'):
                return name
            return noop
    gl = GL('OpenGL.GL')
    gl.glEnable = enable
    gl.glDisable = lambda name: enable(name, False)
    package = ModuleType('OpenGL')
    package.GL = gl
    for name in list(ns):
        if name.startswith('GL_'):
            ns[name] = name
    ns['glEnable'] = gl.glEnable
    ns['glDisable'] = gl.glDisable
    ns['glCallList'] = lambda key: calls.append(dict(key=key, **current))

    def metal(shininess, spec):
        current['material'] = dict(shininess=shininess, spec=spec)
    renderer._material_metal = metal
    renderer._material_matte = lambda: metal(0., (0., 0., 0.))

    def hull_pass(value, authored=False):
        if available and current['shader'] is not None:
            current['shader'] = dict(materialPass=value, authoredSurface=float(authored))
    @contextmanager
    def use(name, **uniforms):
        previous = current['shader']
        if available:
            current['shader'] = {'authoredSurface': 0., **uniforms}
        try:
            yield
        finally:
            current['shader'] = previous
    renderer.materials = NS(available=available, hull_pass=hull_pass, use=use)
    cache = {'visible': [(e, None)], 'relation': {0: 'own'},
             'owner_color': {0: (.3, .6, .9)}, e.id: {'apparent': 60., 'size': size}}
    with patch.dict('sys.modules', {'OpenGL': package, 'OpenGL.GL': gl}):
        ns['_draw_ships'](renderer, set(), cache if cached else None)
    return calls


report = {'scope': 'CPU high-level state submission only, not pixels', 'modes': []}
for available in (True, False):
    cached, uncached = trace(True, available), trace(False, available)
    assert len(cached) == len(uncached) == 6
    differences = [{'cached': a, 'uncached': b}
                   for a, b in zip(cached, uncached) if a != b]
    assert [d['cached']['key'] for d in differences] == ['rebel:frigate_accent']
    report['modes'].append(dict(shader_available=available, cached=cached,
                                uncached=uncached, differences=differences))
print(json.dumps(report, indent=2))
