"""Bounded CPU acceptance of the registered opt-in catalogue, never GL acceptance.

The oracle reads approval-pinned mesh payloads independently of geometry helpers.
All 102 core bindings have an explicit applicability row; four convoy rows have
both real consumers. Visibility is real GameState visibility of owned entities.
No settings, user data, approved bytes or runtime production code are written.
"""
from collections import Counter
import hashlib
from itertools import product
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
import game.core.manager  # Application import order, before DataStore.
from game.core.entity import Entity
from game.core.state import GameState, PlayerState
from game.core.vectors import Vec3
from game.data.store import DataStore
from game.benchmark import state_hash
from game.systems.unit_factory import UnitFactory
from game.systems.planet_buildings import planet_building_site
from game.systems.satellite_orbits import orbit_position
from render import asset_selection as selection
from render import fleet_geometry, ship_sizes
from render.camera import Camera
from render.camera_geometry import station_bounds, station_radius
from render.faction_visuals import FACTIONS, owner_faction, ship_visual_key
from render.input import InputController
from render.planet_building_geometry import station_world_mesh, station_camera_box
from render.renderer import Renderer
from tools.art.audit_s07_routes import route_identity

ROOT = Path(__file__).resolve().parents[1]
COUNTS = dict(combat_hull=18, squadron=7, construction=8, logistics_hull=4,
              station=40, satellite=8, planet_installation=16, environment_prop=1)
RATIOS = dict(fighter_squadron=.6, corvette=1., frigate=1.5, cruiser=2.5,
              battleship=3.5, supercapital=5., construction=1., crew_transport=.8)
# Unchanged procedural needle's committed all-role Z extrema, not _bounds().
CORVETTE_LENGTH = (48. - (-43.600500000000004)) * .7
SURFACE_NORMALS = ((1.,0.,0.), (0.,0.,1.), (-1.,0.,0.),
                   (0.,0.,-1.), (0.,1.,0.), (0.,-1.,0.))
YAWS = (0., .73, 2.1)


def catalogue_rows(ds):
    registry = json.loads((ROOT / 'assets/models/registry.json').read_text())['bindings']
    core = {r['binding']: r for r in registry if r['status'] == 'core'}
    consumers = {binding: [] for binding in core}
    inventory = json.loads((ROOT / 'art/manifests/model_inventory.json').read_text())
    for item in inventory['rows']:
        binding, data_id, entry = route_identity(ds, item['canonical_binding'])
        if binding in core:
            consumers[binding].append(dict(canonical=item['canonical_binding'],
                                          data_id=data_id, entry=entry))
    rows = []
    for binding, item in sorted(core.items()):
        ship = item['category'] in ('combat_hull', 'squadron', 'construction', 'logistics_hull')
        station = item['category'] in ('station', 'satellite', 'planet_installation')
        rows.append(dict(binding=binding, category=item['category'],
                         consumers=consumers[binding], manifest=item['manifest'],
                         applicability=dict(selected_mesh=True, all_role_bounds=ship or station,
                                            scale=ship or station, contact=ship or station,
                                            camera_refresh=ship or station, input_pick=ship or station),
                         exclusions=[] if ship or station else [
                             'Asteroid field prop: selected payload closure only; per-instance field '
                             'draw transforms, contact, selection and camera are not ship/station consumers.']))
    return rows


def raw_geometry(manifest):
    """Decode indices directly, not via the resolver/mesh/bounds/ray readers."""
    path = ROOT / manifest['files']['mesh']['path']
    payload = json.loads(path.read_text())
    vertices = np.asarray(payload['vertices'], dtype=float)
    batches = {role: vertices[np.asarray(faces, dtype=float)[:, 3:].astype(int)]
               for role, faces in payload['batches'].items()}
    triangles = np.concatenate(list(batches.values()))
    points = triangles.reshape(-1, 3)
    return path, batches, triangles, points.min(axis=0), points.max(axis=0)


def rotate(points, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.asarray(points) @ np.asarray(((c,0.,-s), (0.,1.,0.), (s,0.,c)))


def frame_oracle(entity, planet=None, angle=0.):
    if entity.planet_building_slot is not None:
        assert planet is not None
        up = np.asarray(SURFACE_NORMALS[entity.planet_building_slot])
        seed = np.asarray((0.,0.,1.) if abs(up[2]) < .9 else (1.,0.,0.))
        right = np.cross(up, seed)
        right /= np.linalg.norm(right)
        forward = np.cross(right, up)
        return (np.asarray(planet.pos.to_tuple()) + up * (planet.radius + 1.),
                np.asarray((right, up, forward)))
    yaw = entity.yaw if entity.satellite_slot is not None else angle
    return np.asarray(entity.pos.to_tuple()), rotate(np.eye(3), yaw)


def plane_ray_distance(triangles, direction):
    """Independent ray-plane + oriented edge containment, not Moller-Trumbore."""
    direction = np.asarray(direction)
    a, b, c = triangles[:,0], triangles[:,1], triangles[:,2]
    normals = np.cross(b-a, c-a)
    denom = normals @ direction
    valid = np.abs(denom) > 1e-10
    t = np.divide(np.einsum('ij,ij->i', normals, a), denom,
                  out=np.zeros_like(denom), where=valid)
    hit = t[:,None] * direction
    valid &= t > 0.
    for start, end in ((a,b), (b,c), (c,a)):
        signed = np.einsum('ij,ij->i', np.cross(end-start, hit-start), normals)
        valid &= signed >= -1e-9*np.einsum('ij,ij->i', normals, normals)
    return float(t[valid].max(initial=0.))


def lies_on_triangle_mesh(point, triangles):
    """Independent surface membership: plane distance and oriented edge tests."""
    a, b, c = triangles[:,0], triangles[:,1], triangles[:,2]
    normals = np.cross(b-a, c-a)
    lengths = np.linalg.norm(normals, axis=1)
    delta = np.asarray(point) - a
    valid = (lengths > 1e-10) & (np.abs(np.einsum('ij,ij->i', normals, delta)) <= 2e-5*lengths)
    for start, end in ((a,b), (b,c), (c,a)):
        signed = np.einsum('ij,ij->i', np.cross(end-start, np.asarray(point)-start), normals)
        valid &= signed >= -1e-7*lengths*lengths
    return bool(valid.any())


class SelectedGeometryMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        previous_store = DataStore._instance
        cls.addClassCleanup(setattr, DataStore, '_instance', previous_store)
        previous = (selection._selection, selection._resolver, selection._generation)
        def restore_selection():
            selection._selection, selection._resolver, selection._generation = previous
            selection.invalidate_geometry_helpers()
        cls.addClassCleanup(restore_selection)
        cls.ds = DataStore(assets_dir=str(ROOT / 'assets/data'), mods=[], balance={})
        selection.configure({'model_preview': True, 'visual_packs': []}, asset_root=ROOT)
        cls.rows = catalogue_rows(cls.ds)
        cls.manifests = {}
        for path in (ROOT / 'assets/models/manifests').glob('*.json'):
            item = json.loads(path.read_text())
            if item.get('contract') == 'star-armada/model-manifest':
                cls.manifests[item['asset']] = item
        cls.raw = {r['binding']: raw_geometry(cls.manifests[r['manifest']]) for r in cls.rows}

    def fixture(self, row, data_id, *, captured=False):
        faction = row['binding'].split(':')[0]
        owner = FACTIONS[(FACTIONS.index(faction)+1) % 4] if captured else faction
        state = GameState(players={0: PlayerState(0, faction=owner)})
        factory = UnitFactory(state)
        if row['category'] in ('station', 'satellite', 'planet_installation'):
            entity = factory.spawn_station(data_id, 0, Vec3(200.,5000.,-300.))
        elif data_id == 'trade_convoy':
            entity = Entity(id=1, kind='ship', owner=0, data_id=data_id,
                            is_ship=True, pos=Vec3(200.,5000.,-300.), radius=32.)
            state.add_entity(entity)
        else:
            entity = factory.spawn_ship(data_id, 0, Vec3(200.,5000.,-300.))
        return state, entity

    def view(self, state, entity, angle=0., *, height=640, distance=180.):
        camera = Camera(960, height)
        camera.target = list(entity.pos.to_tuple())
        camera.distance, camera.yaw, camera.pitch = distance, 35., 28.
        controller = InputController(state, camera, SimpleNamespace(), SimpleNamespace())
        camera.bind_scene(state, lambda: 0, lambda: angle)
        renderer = Renderer.__new__(Renderer)
        renderer.camera, renderer.ds, renderer.state = camera, self.ds, state
        renderer.local_player, renderer.time = 0, math.degrees(angle)/3.
        return camera, controller, renderer

    def assert_mesh(self, mesh, raw_batches):
        self.assertEqual(set(mesh), set(raw_batches))
        for role, raw in raw_batches.items():
            np.testing.assert_array_equal(np.asarray([tri for _,tri in mesh[role]]), raw)

    def assert_safe_eye(self, camera, world_triangles):
        # A triangle-surface oracle, independent of the camera slab solver:
        # the rendered eye cannot be within the mesh's conservative world box.
        points = world_triangles.reshape(-1,3)
        eye = np.asarray(camera.eye_position())
        self.assertFalse(bool(np.all(eye > points.min(axis=0)) and
                              np.all(eye < points.max(axis=0))), tuple(eye))

    def assert_near_plane_clear(self, camera, origin, basis, lo, hi):
        # Independently invert the declared frame and expand by the near-plane
        # rectangle's bounding ball. No camera interval/solver helper is used.
        eye = (np.asarray(camera.eye_position())-origin) @ np.asarray(basis).T
        tangent = math.tan(math.radians(camera.fov/2.))
        clearance = camera.near*math.sqrt(1.+tangent*tangent*(1.+(camera.width/camera.height)**2))+2.
        self.assertFalse(bool(np.all(eye >= np.asarray(lo)-clearance) and
                              np.all(eye <= np.asarray(hi)+clearance)),
                         ('near plane enters selected all-role box', tuple(eye)))

    def pick_triangle(self, camera, controller, entity, world_triangles, *, backside=False):
        if (entity.planet_building_slot is None and entity.satellite_slot is None
                and camera.height == 640):
            # Prove the large-visual-hull path, not only the 28px center fallback.
            points = world_triangles.reshape(-1,3)
            indices = []
            for axis in camera.basis()[:2]:
                projected_axis = points @ np.asarray(axis)
                indices.extend((int(projected_axis.argmin()),int(projected_axis.argmax())))
            center = camera.world_to_screen(*entity.pos.to_tuple())
            candidates = [camera.world_to_screen(*points[i]) for i in indices]
            candidates = [p for p in candidates if p is not None]
            self.assertTrue(candidates)
            mouse = max(candidates,key=lambda p: math.dist(p,center))
            self.assertGreater(math.dist(mouse,center),28.,'pick sample must defeat center fallback')
            controller._single_select(*mouse)
            self.assertEqual(controller.selection,{entity.id})
            controller._single_select(100000.,100000.)
            self.assertEqual(controller.selection,set())
            return
        # A centroid of a nondegenerate projected *actual* authored triangle,
        # rather than the entity center or a bounds-helper-derived coordinate.
        for triangle in world_triangles[:64]:
            projected = [camera.world_to_screen(*p) for p in triangle]
            if any(p is None for p in projected):
                continue
            a,b,c = np.asarray(projected)
            edge1, edge2 = b-a, c-a
            if abs(float(edge1[0]*edge2[1]-edge1[1]*edge2[0])) > 1e-5:
                mouse = tuple((a+b+c)/3.)
                if backside:
                    distance = controller._ship_pick_distance(entity,
                        camera.world_to_screen(*entity.pos.to_tuple()), mouse, 28.)
                    self.assertEqual(distance, math.inf)
                else:
                    controller._single_select(*mouse)
                    self.assertEqual(controller.selection, {entity.id})
                return
        self.fail('No projected nondegenerate authored triangle in bounded pick sample')

    def assert_contact(self, renderer, entity, world_triangles, normal):
        desired = tuple(world_triangles[0].mean(axis=0))
        effect = dict(kind='hull_hit', target_id=entity.id, pos=desired,
                      normal=tuple(normal), size=5.)
        original = dict(effect)
        result = renderer._visual_hit(effect)
        self.assertTrue(result.get('visual_contact'), result)
        self.assertTrue(lies_on_triangle_mesh(result['pos'], world_triangles),
                        ('contact not on selected geometry', result['pos']))
        self.assertEqual(effect, original)

    def test_102_registered_bindings_have_complete_live_consumer_applicability(self):
        self.assertEqual(len(self.rows), 102)
        self.assertEqual(Counter(r['category'] for r in self.rows), COUNTS)
        self.assertEqual(sum(len(r['consumers']) for r in self.rows), 106)
        for row in self.rows:
            with self.subTest(binding=row['binding']):
                self.assertTrue(row['consumers'])
                self.assertTrue(all(row['applicability'].values()) or row['exclusions'])
                expected = 2 if row['category'] == 'logistics_hull' else 1
                self.assertEqual(len(row['consumers']), expected)

    def test_selected_revision_payload_and_actual_dispatch_closure(self):
        from render.faction_stations import station_mesh as faction_station_mesh
        for row in self.rows:
            binding = row['binding']
            with self.subTest(binding=binding):
                manifest = self.manifests[row['manifest']]
                path, batches, _, _, _ = self.raw[binding]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 manifest['files']['mesh']['sha256'])
                body = '\n'.join(f"{key}:{manifest['files'][key]['sha256']}"
                                 for key in sorted(manifest['files']))
                revision = hashlib.sha256(f"{manifest['asset']}\n{body}".encode()).hexdigest()
                resolved = selection._resolver.resolve(binding)
                self.assertIsNotNone(resolved)
                self.assertEqual(resolved.revision, revision)
                self.assertEqual(selection.gpu_cache_key(binding, 'base', 'legacy')[1], revision)
                mesh = selection.mesh_for(binding)
                self.assertTrue(mesh is resolved.mesh, binding + ': selected geometry absent/mismatched')
                self.assert_mesh(mesh, batches)
                for consumer in row['consumers']:
                    if consumer['canonical'].startswith('ship:'):
                        faction = binding.split(':')[0]
                        key = ship_visual_key(self.ds, consumer['data_id'], faction)
                        self.assertEqual(key, binding)
                        self.assertIs(fleet_geometry.ship_mesh(key), mesh)
                    elif consumer['entry']:
                        data_id = consumer['data_id']
                        faction = binding.split(':')[0]
                        self.assertIs(fleet_geometry.station_mesh(data_id, faction), mesh)
                        # This subsidiary facade only consumes its three non-Imperial
                        # ten-station families. Fleet dispatch owns Imperial/attached rows.
                        if faction != 'imperial' and row['category'] == 'station':
                            self.assertTrue(faction_station_mesh(faction, data_id) is mesh,
                                            binding + ': subsidiary station facade differs')

    def test_all_role_bounds_are_raw_payload_extrema(self):
        for row in self.rows:
            binding = row['binding']
            if not row['applicability']['all_role_bounds']:
                continue
            with self.subTest(binding=binding):
                _, _, triangles, lo, hi = self.raw[binding]
                radius = np.linalg.norm(triangles.reshape(-1,3), axis=1).max()
                if row['category'] in ('station','satellite','planet_installation'):
                    faction, data_id = binding.split(':')
                    actual_lo, actual_hi = station_bounds(data_id, faction)
                    self.assertAlmostEqual(station_radius(data_id, faction), radius)
                else:
                    actual_lo, actual_hi, actual_radius = ship_sizes._bounds(binding)
                    self.assertAlmostEqual(actual_radius, radius)
                np.testing.assert_array_equal(actual_lo, lo)
                np.testing.assert_array_equal(actual_hi, hi)

    def test_ship_consumers_capture_scale_rotated_contact_camera_and_pick(self):
        for row in self.rows:
            if not row['consumers'][0]['canonical'].startswith('ship:'):
                continue
            binding = row['binding']
            _, _, raw, lo, hi = self.raw[binding]
            for consumer in row['consumers']:
                data_id = consumer['data_id']
                # Captured catalogue ships retain data faction; dataless convoys use owner.
                state, entity = self.fixture(row, data_id, captured=data_id != 'trade_convoy')
                entity.radius = 1e6  # Collision scale must never enter ship visual consumers.
                ratio = RATIOS[self.ds.ships[data_id].category] if data_id in self.ds.ships else 1.
                expected_length = CORVETTE_LENGTH * ratio
                for yaw, height in product(YAWS, (640,64)):
                    with self.subTest(binding=binding, consumer=data_id, yaw=yaw, height=height):
                        entity.yaw = yaw
                        before = state_hash(state)
                        camera, controller, renderer = self.view(state, entity, height=height,
                            distance=max(180., expected_length*4.))
                        size = renderer._ship_size(entity)
                        self.assertEqual(size.shape, binding)
                        eye = np.asarray(camera.eye_position())
                        depth = np.dot(np.asarray(entity.pos.to_tuple())-eye, camera.basis()[2])
                        ppw = height/(2.*depth*math.tan(math.radians(55./2.)))
                        boost = max(1., 7./(max(.01,26.*ppw)*.7))
                        expected_scale = expected_length/(hi[2]-lo[2])*boost
                        self.assertAlmostEqual(size.scale, expected_scale)
                        self.assertAlmostEqual(size.length, expected_length*boost)
                        world = rotate(raw*expected_scale, yaw) + entity.pos.to_tuple()
                        camera.refresh_scene()
                        self.assertEqual(len(camera._camera_boxes), 1)
                        box = camera._camera_boxes[0]
                        np.testing.assert_allclose(box[2], lo*expected_length/(hi[2]-lo[2]))
                        np.testing.assert_allclose(box[3], hi*expected_length/(hi[2]-lo[2]))
                        self.assertAlmostEqual(box[1], yaw)
                        self.assert_safe_eye(camera, world)
                        normal = np.asarray((.23,.51,.83)); normal /= np.linalg.norm(normal)
                        local_world = world - entity.pos.to_tuple()
                        self.assertAlmostEqual(ship_sizes.hull_contact_distance(size, normal, yaw),
                                               plane_ray_distance(local_world, normal), places=6)
                        self.assert_contact(renderer, entity, world, normal)
                        self.pick_triangle(camera, controller, entity, world)
                        # Exercise the actual close-zoom safety path as well as
                        # far/readability views; rederive boost at the effective eye.
                        camera.distance, camera.pitch, camera.yaw = 180., 8., 0.
                        camera.refresh_scene()
                        eye = np.asarray(camera.eye_position())
                        depth = np.dot(np.asarray(entity.pos.to_tuple())-eye, camera.basis()[2])
                        ppw = height/(2.*depth*math.tan(math.radians(55./2.)))
                        close_boost = max(1.,7./(max(.01,26.*ppw)*.7))
                        close_scale = expected_length/(hi[2]-lo[2])*close_boost
                        self.assert_near_plane_clear(camera,np.asarray(entity.pos.to_tuple()),
                            rotate(np.eye(3),yaw),lo*close_scale,hi*close_scale)
                        self.assertEqual(state_hash(state), before)

    def test_convoy_aliases_share_revision_but_not_crew_trade_scale(self):
        rows = [r for r in self.rows if r['category'] == 'logistics_hull']
        self.assertEqual(len(rows), 4)
        for row in rows:
            with self.subTest(binding=row['binding']):
                faction = row['binding'].split(':')[0]
                crew = next(c['data_id'] for c in row['consumers'] if c['data_id'] != 'trade_convoy')
                self.assertGreater(self.ds.ships[crew].crew_capacity, 0)
                crew_size = ship_sizes.ship_size(self.ds, crew, 'invalid-owner-faction')
                trade_size = ship_sizes.ship_size(self.ds, 'trade_convoy', faction)
                self.assertEqual(crew_size.shape, row['binding'])
                self.assertEqual(trade_size.shape, row['binding'])
                self.assertAlmostEqual(crew_size.length, CORVETTE_LENGTH*.8)
                self.assertAlmostEqual(trade_size.length, CORVETTE_LENGTH)
                self.assertAlmostEqual(crew_size.scale/trade_size.scale, .8)

    def test_40_station_current_owner_rotated_contact_camera_scale_and_pick(self):
        for row in self.rows:
            if row['category'] != 'station':
                continue
            binding = row['binding']
            faction, data_id = binding.split(':')
            _, _, raw, lo, hi = self.raw[binding]
            state, entity = self.fixture(row, data_id)
            for angle in YAWS:
                with self.subTest(binding=binding, angle=angle):
                    before = state_hash(state)
                    scale = entity.radius/50.
                    camera, controller, renderer = self.view(state, entity, angle,
                        distance=max(300., float(np.linalg.norm(hi-lo))*scale*3.))
                    self.assertEqual(owner_faction(state, entity.owner), faction)
                    self.assertAlmostEqual(renderer._station_visual_radius(entity),
                                           np.linalg.norm(raw.reshape(-1,3),axis=1).max()*scale)
                    world = rotate(raw*scale, angle) + entity.pos.to_tuple()
                    camera.refresh_scene()
                    self.assertEqual(len(camera._camera_boxes), 1)
                    box = camera._camera_boxes[0]
                    self.assertAlmostEqual(box[1], angle)
                    np.testing.assert_allclose(box[2],lo*scale)
                    np.testing.assert_allclose(box[3],hi*scale)
                    self.assert_safe_eye(camera, world)
                    normal = np.asarray((.23,.51,.83)); normal /= np.linalg.norm(normal)
                    self.assertAlmostEqual(ship_sizes.station_contact_distance(data_id,faction,entity.radius,normal,angle),
                        plane_ray_distance(world-entity.pos.to_tuple(),normal), places=6)
                    self.assert_contact(renderer, entity, world, normal)
                    self.pick_triangle(camera, controller, entity, world)
                    camera.distance, camera.pitch, camera.yaw = 180., 8., 0.
                    camera.refresh_scene()
                    self.assert_near_plane_clear(camera,np.asarray(entity.pos.to_tuple()),
                        rotate(np.eye(3),angle),lo*scale,hi*scale)
                    self.assertEqual(state_hash(state), before)

    def test_attached_16_installations_all_six_slots_and_8_satellites_all_eight_placements(self):
        for row in self.rows:
            if row['category'] not in ('planet_installation','satellite'):
                continue
            binding = row['binding']
            faction, data_id = binding.split(':')
            _, _, raw, lo, hi = self.raw[binding]
            surface = row['category'] == 'planet_installation'
            for slot in range(6 if surface else 8):
                with self.subTest(binding=binding, slot=slot):
                    state, entity = self.fixture(row, data_id)
                    planet = Entity(id=100, kind='planet', owner=0, data_id='temperate',
                                    is_planet=True, pos=Vec3(200.,5000.,-300.),radius=650.)
                    state.add_entity(planet)
                    entity.planet_id = planet.id
                    if surface:
                        entity.planet_building_slot = slot
                        entity.pos, _ = planet_building_site(planet, slot)
                    else:
                        entity.satellite_slot = slot
                        entity.pos = orbit_position(planet, entity.radius, slot*math.pi/4.,slot)
                        entity.yaw = .37 + slot*.31
                    origin, basis = frame_oracle(entity, planet, angle=1.23)
                    scale = entity.radius/50.
                    world = (raw*scale) @ basis + origin
                    corners = (np.asarray(list(product(*zip(lo,hi))))*scale) @ basis + origin
                    before = state_hash(state)
                    camera, controller, renderer = self.view(state, entity, 1.23,distance=400.)
                    if surface:
                        up = SURFACE_NORMALS[slot]
                        # Real stock-range camera can see equatorial/north sites,
                        # but the south pole is deliberately a back-face reject.
                        camera.pitch = 80. if slot in (4,5) else 8.
                        camera.yaw = (90.,0.,270.,180.,35.,35.)[slot]
                    camera.refresh_scene()
                    actual_box = station_camera_box(state,entity,1.23)
                    np.testing.assert_allclose(actual_box[0], origin)
                    np.testing.assert_allclose(actual_box[2],corners.min(axis=0)-origin,atol=1e-9)
                    np.testing.assert_allclose(actual_box[3],corners.max(axis=0)-origin,atol=1e-9)
                    self.assertIn(actual_box,camera._camera_boxes)
                    self.assert_safe_eye(camera,world)
                    actual_world = np.asarray([tri for role in station_world_mesh(state,entity,1.23).values()
                                               for _,tri in role])
                    np.testing.assert_allclose(actual_world,world,atol=1e-9)
                    normal = basis[1] if surface else np.asarray((.23,.51,.83))/np.linalg.norm((.23,.51,.83))
                    self.assert_contact(renderer,entity,world,normal)
                    self.pick_triangle(camera,controller,entity,world,backside=surface and slot==5)
                    # Surface installations ignore animation; satellites follow yaw, not angle.
                    np.testing.assert_allclose(np.asarray([tri for role in station_world_mesh(state,entity,9.87).values()
                                                          for _,tri in role]),world,atol=1e-9)
                    self.assertEqual(state_hash(state),before)

    def test_stations_change_selected_family_with_current_owner_not_origin(self):
        for row in self.rows:
            if row['category'] not in ('station','satellite','planet_installation'):
                continue
            faction, data_id = row['binding'].split(':')
            with self.subTest(binding=row['binding']):
                state, entity = self.fixture(row,data_id)
                prior_faction = FACTIONS[(FACTIONS.index(faction)+1)%4]
                state.players[1] = PlayerState(1,faction=prior_faction)
                entity.owner = 1
                _, _, prior_raw, _, _ = self.raw[f'{prior_faction}:{data_id}']
                renderer = Renderer.__new__(Renderer)
                renderer.state = state
                self.assertAlmostEqual(renderer._station_visual_radius(entity),
                    np.linalg.norm(prior_raw.reshape(-1,3),axis=1).max()*entity.radius/50.)
                entity.owner = 0  # Capture changes paint/family, not station data identity.
                before = state_hash(state)
                _, _, raw, _, _ = self.raw[row['binding']]
                self.assertAlmostEqual(renderer._station_visual_radius(entity),
                    np.linalg.norm(raw.reshape(-1,3),axis=1).max()*entity.radius/50.)
                self.assertEqual(state_hash(state),before)


if __name__ == '__main__':
    unittest.main()
