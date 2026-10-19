"""Same-object ownership transitions; CPU consumers, reusable native-frame oracle.

Ownership assignments are explicit fixture mutations, not read-only operations.
The oracle reads registry/manifest/raw triangles without resolver geometry reads.
"""
from contextlib import ExitStack
from itertools import product
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from test_s07_selected_geometry_matrix import (
    ROOT, SelectedGeometryMatrixTests, raw_geometry, rotate, frame_oracle,
    RATIOS, CORVETTE_LENGTH, lies_on_triangle_mesh,
    Entity, GameState, PlayerState, Vec3, UnitFactory, Camera, Renderer,
    InputController, selection, state_hash, planet_building_site, orbit_position,
)


def assert_transition_consumers(state, entity, renderer, camera, station_angle=0.):
    """Assert real consumers on caller's graph; return JSON-safe frame measurements.

    Caller supplies an active selected catalogue and renderer camera/time consistent
    with station_angle. No selection reconfiguration/cache purge is performed.
    Camera scene is explicitly refreshed for the current owner each invocation.
    """
    check = SelectedGeometryMatrixTests()
    before = state_hash(state)
    assert renderer.state is state and renderer.camera is camera
    ds = renderer.ds
    owner_family = state.players[entity.owner].faction
    if entity.is_station:
        binding = f'{owner_family}:{entity.data_id}'
    else:
        data = ds.ships.get(entity.data_id)
        family = data.faction if data is not None else owner_family
        role = 'convoy' if data is None or data.category == 'crew_transport' else data.category
        binding = f'{family}:{role}'
    registry = json.loads((ROOT/'assets/models/registry.json').read_text())['bindings']
    row = next(r for r in registry if r['binding'] == binding)
    manifests = [json.loads(p.read_text()) for p in (ROOT/'assets/models/manifests').glob('*.json')]
    manifest = next(m for m in manifests if m.get('asset') == row['manifest'])
    _, _, raw, lo, hi = raw_geometry(manifest)
    generation = selection._generation
    controller = InputController(state, camera, SimpleNamespace(), SimpleNamespace())
    controller.local_player = entity.owner
    renderer.local_player = entity.owner
    camera.bind_scene(state, lambda: entity.owner, lambda: station_angle)
    camera.refresh_scene()
    if entity.is_station:
        origin, basis = frame_oracle(entity, state.entities.get(entity.planet_id), station_angle)
        scale = entity.radius/50.
        world = (raw*scale) @ basis + origin
        if entity.planet_building_slot is not None or entity.satellite_slot is not None:
            corners = (np.asarray(list(product(*zip(lo, hi))))*scale) @ basis
            expected_lo, expected_hi = corners.min(axis=0), corners.max(axis=0)
            box_yaw = 0.
        else:
            expected_lo, expected_hi = lo*scale, hi*scale
            box_yaw = entity.yaw if entity.satellite_slot is not None else station_angle
    else:
        size = renderer._ship_size(entity)
        assert size.shape == binding, (size.shape, binding)
        data = ds.ships.get(entity.data_id)
        length = CORVETTE_LENGTH * (RATIOS[data.category] if data is not None else 1.)
        eye = np.asarray(camera.eye_position())
        depth = np.dot(np.asarray(entity.pos.to_tuple())-eye, camera.basis()[2])
        ppw = camera.height/(2.*depth*math.tan(math.radians(55./2.)))
        scale = length/(hi[2]-lo[2])*max(1., 7./(max(.01,26.*ppw)*.7))
        check.assertAlmostEqual(size.scale, scale)
        origin, basis = np.asarray(entity.pos.to_tuple()), rotate(np.eye(3),entity.yaw)
        world = (raw*scale) @ basis + origin
        expected_lo, expected_hi = lo*length/(hi[2]-lo[2]), hi*length/(hi[2]-lo[2])
        box_yaw = entity.yaw
    # The refreshed snapshot must contain this family's raw-derived bounds.
    matching = [b for b in camera._camera_boxes if np.allclose(b[0],origin)
                and abs(b[1]-box_yaw)<1e-8
                and np.allclose(b[2],expected_lo) and np.allclose(b[3],expected_hi)]
    assert matching, ('snapshot family bounds mismatch', binding, camera._camera_boxes)
    check.assert_safe_eye(camera, world)
    check.assert_near_plane_clear(camera, origin, basis, lo*scale, hi*scale)
    normal = basis[1] if entity.planet_building_slot is not None else np.asarray((.23,.51,.83))/np.linalg.norm((.23,.51,.83))
    effect = dict(kind='hull_hit',target_id=entity.id,pos=tuple(world[0].mean(axis=0)),normal=tuple(normal),size=5.)
    original = dict(effect)
    result = renderer._visual_hit(effect)
    assert result.get('visual_contact') and lies_on_triangle_mesh(result['pos'],world), ('contact not on selected raw triangles',binding,result)
    assert effect == original
    check.pick_triangle(camera,controller,entity,world)
    controller._single_select(100000.,100000.)
    assert controller.selection == set(), 'nonpoint selected an entity'
    assert selection._generation == generation
    assert state_hash(state) == before, 'helper reads mutated authoritative state'
    return dict(entity_id=entity.id,data_id=entity.data_id,owner=entity.owner,
                owner_family=owner_family,binding=binding,generation=generation,
                snapshot_generation=generation,snapshot_bounds=[expected_lo.tolist(),expected_hi.tolist()],
                world_bounds=[world.reshape(-1,3).min(axis=0).tolist(),world.reshape(-1,3).max(axis=0).tolist()],
                contact=list(result['pos']),eye=list(camera.eye_position()),state_hash=before,
                pick=True,nonpoint_rejected=True,near_clear=True)


class CaptureTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SelectedGeometryMatrixTests.setUpClass.__func__(cls)

    def fixture(self, data_id):
        state = GameState(players={0:PlayerState(0,faction='imperial'),1:PlayerState(1,faction='syndicate')})
        factory = UnitFactory(state)
        pos = Vec3(200.,5000.,-300.)
        if data_id == 'trade_convoy':
            entity = Entity(id=1,kind='ship',owner=0,data_id=data_id,is_ship=True,pos=pos,radius=32.)
            state.add_entity(entity)
        elif data_id in self.ds.ships:
            entity = factory.spawn_ship(data_id,0,pos)
        else:
            entity = factory.spawn_station(data_id,0,pos)
        if data_id in ('defense_satellite','planet_extractor'):
            planet = Entity(id=100,kind='planet',owner=0,data_id='temperate',is_planet=True,pos=pos,radius=650.)
            state.add_entity(planet)
            entity.planet_id = planet.id
            if data_id == 'planet_extractor':
                entity.planet_building_slot = 4
                entity.pos, _ = planet_building_site(planet,4)
            else:
                entity.satellite_slot = 0
                entity.pos = orbit_position(planet,entity.radius,0.,0)
        entity.yaw = .73
        camera = Camera(960,640)
        camera.target = list(entity.pos.to_tuple())
        camera.distance,camera.pitch,camera.yaw = 400.,80.,35.
        renderer = Renderer.__new__(Renderer)
        renderer.state,renderer.camera,renderer.ds = state,camera,self.ds
        renderer.local_player,renderer.time = 0,0.
        return state,entity,renderer,camera

    def test_same_entities_owner_roundtrip(self):
        measurements=[]
        # Fail closed if any CPU consumer unexpectedly reaches a native GL call.
        import render.renderer as rr
        import render.camera as cc
        with ExitStack() as guards:
            for module in (rr,cc):
                for name in vars(module):
                    if name.startswith(('gl','_glu')) and callable(getattr(module,name)):
                        guards.enter_context(patch.object(module,name,side_effect=AssertionError('CPU reached GL: '+name)))
            for data_id in ('imperial_frigate','imperial_crew_transport','trade_convoy','shipyard','defense_satellite','planet_extractor'):
                state,entity,renderer,camera = self.fixture(data_id)
                identity=id(entity)
                rows=[]
                for owner in (0,1,0):
                    entity.owner=owner  # Explicit authoritative fixture transition.
                    if entity.planet_id is not None:
                        state.entities[entity.planet_id].owner=owner
                    rows.append(assert_transition_consumers(state,entity,renderer,camera))
                    self.assertIs(state.entities[entity.id],entity)
                    self.assertEqual(id(entity),identity)
                self.assertEqual(rows[0]['binding'],rows[2]['binding'])
                if data_id in ('imperial_frigate','imperial_crew_transport'):
                    self.assertEqual(rows[0]['binding'],rows[1]['binding'])
                else:
                    self.assertNotEqual(rows[0]['binding'],rows[1]['binding'])
                measurements.extend(rows)
        print('CAPTURE_TRANSITION_MEASUREMENTS='+json.dumps(measurements,sort_keys=True))

    def test_stale_owner_family_is_rejected_in_memory(self):
        state,entity,renderer,camera = self.fixture('shipyard')
        assert_transition_consumers(state,entity,renderer,camera)
        entity.owner=1
        # Real consumers sabotaged together; independent raw metadata stays current.
        import render.renderer as rr
        import render.camera as cc
        with ExitStack() as guards:
            for module in (rr,cc):
                for name in vars(module):
                    if name.startswith(('gl','_glu')) and callable(getattr(module,name)):
                        guards.enter_context(patch.object(module,name,side_effect=AssertionError('CPU reached GL: '+name)))
            guards.enter_context(patch('render.faction_visuals.owner_faction',return_value='imperial'))
            with self.assertRaisesRegex(AssertionError, 'snapshot family bounds mismatch') as caught:
                assert_transition_consumers(state,entity,renderer,camera)
            print('STALE_FAMILY_CONTROL_REJECTED='+str(caught.exception))


if __name__ == '__main__':
    unittest.main()
