"""Production input/camera regressions for attached station transforms."""
import unittest
from types import SimpleNamespace
from game.core.entity import Entity
from game.core.vectors import Vec3
from game.systems.planet_buildings import planet_building_site
from render.camera import Camera
from render.input import InputController
from render.planet_building_geometry import station_world_mesh, station_camera_box


class SurfaceIntegrationTests(unittest.TestCase):
    def fixture(self):
        planet = Entity(id=1, kind='planet', owner=-1, data_id='temperate', radius=650)
        pos, _ = planet_building_site(planet, 4)
        building = Entity(id=2, kind='station', owner=0,
                          data_id='planet_pulsar_cannon', radius=85, pos=pos,
                          planet_id=1, planet_building_slot=4)
        planet.is_planet = True
        building.is_station = True
        state = SimpleNamespace(entities={1: planet, 2: building}, players={},
                                entity=lambda i: {1: planet, 2: building}.get(i),
                                known_entity=lambda *_: None, can_see=lambda *_: True)
        return state, building

    def test_input_selects_projected_surface_hardware(self):
        state, building = self.fixture()
        cam = Camera(960, 640)
        cam.world_to_screen = lambda x, y, z: (x, y)
        cam.eye_position = lambda: (0., 2000., 2000.)
        controller = InputController(state, cam, SimpleNamespace(), SimpleNamespace())
        point = max((p for m in station_world_mesh(state, building).values()
                     for _, tri in m for p in tri), key=lambda p: p[1])
        controller._single_select(point[0], point[1])
        self.assertEqual(controller.selection, {building.id})
        state.can_see = lambda _, eid: eid != building.id
        controller._single_select(point[0], point[1])
        self.assertNotIn(building.id, controller.selection)

    def test_camera_reads_outward_surface_box(self):
        state, building = self.fixture()
        cam = Camera(960, 640)
        cam.target = list(building.pos.to_tuple())
        cam.bind_scene(state, lambda: 0, lambda: 1.2)
        self.assertIn(station_camera_box(state, building, 1.2), cam._camera_boxes)
        state.can_see = lambda *_: False
        cam.refresh_scene()
        self.assertEqual(cam._camera_boxes, ())

    def test_renderer_contacts_follow_outward_surface_frame_and_do_not_spin(self):
        from copy import deepcopy
        from render.renderer import Renderer
        state, building = self.fixture()
        renderer = Renderer.__new__(Renderer)
        renderer.state, renderer.local_player, renderer.time = state, 0, 1.
        points = [p for role in station_world_mesh(state, building).values()
                  for _, tri in role for p in tri]
        desired = max(points, key=lambda p: p[1])
        effect = dict(kind='hull_hit', target_id=building.id, pos=desired,
                      normal=(0., 1., 0.), size=5.)
        before = deepcopy(effect)
        contact = renderer._visual_hit(effect)
        self.assertTrue(contact.get('visual_contact'))
        self.assertGreater(contact['pos'][1], building.pos.y)
        renderer.time = 37.
        self.assertEqual(renderer._visual_hit(effect), contact)
        self.assertEqual(effect, before)
        state.can_see = lambda *_: False
        self.assertIs(renderer._visual_hit(effect), effect)

    def test_surface_identity_reaches_existing_mesh_readers(self):
        from render.faction_visuals import normalize_station_key
        self.assertEqual(normalize_station_key('planet_pulsar_cannon', 'rebel'),
                         ('rebel', 'planet_pulsar_cannon'))
