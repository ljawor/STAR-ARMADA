"""Faction hardware integration: pure identity, actual geometry and bounds."""
import unittest
from game.data.store import DataStore


class VisualIdentityTests(unittest.TestCase):
    def test_catalogue_identity_is_canonical_and_owner_paint_independent(self):
        from render import faction_visuals as v
        ds = DataStore.get()
        for did, data in ds.ships.items():
            key = v.ship_visual_key(ds, did, 'syndicate')
            if data.faction == 'imperial':
                self.assertEqual(key, ds.ship_visual(did)['shape'])
            else:
                self.assertTrue(key.startswith(data.faction + ':'))
        from types import SimpleNamespace
        mod_ds = SimpleNamespace(ships={'mod_ship': SimpleNamespace(faction='rebel', category='corvette')},
                                 ship_visual=lambda did: {'shape':'needle'})
        self.assertEqual(v.ship_visual_key(mod_ds, 'mod_ship', 'rebel'), 'needle')
        self.assertEqual(v.ship_visual_key(ds, 'rebel_y_squadron'), 'rebel:bomber')
        self.assertEqual(v.ship_visual_key(ds, 'confed_colonizer'), 'confederacy:colonizer')
        self.assertEqual(v.ship_visual_key(ds, 'trade_convoy', 'rebel'), 'rebel:convoy')
        self.assertEqual(v.ship_visual_key(ds, 'mod_missing', 'rebel'), 'box')
        self.assertEqual(v.normalize_ship_key('rebel:corvette_dark'), 'box')
        self.assertEqual(v.normalize_station_key('mod_missing', 'rebel'), ('imperial', 'research_station'))
        self.assertEqual(v.normalize_station_key('shipyard', 'rebel'), ('rebel', 'shipyard'))


class HardwareIntegrationTests(unittest.TestCase):
    def test_camera_same_legacy_shape_keeps_distinct_category_lengths(self):
        from game.core.state import GameState, PlayerState
        from game.core.entity import Entity
        from render.camera_geometry import scene_boxes
        from render.ship_sizes import ship_size, _bounds
        st = GameState()
        st.players[0] = PlayerState(0)
        for i, did in enumerate(('imperial_corvette', 'imperial_frigate'), 1):
            e = Entity(id=i, kind='ship', owner=0, data_id=did)
            e.is_ship = True
            st.entities[i] = e
        boxes = scene_boxes(st, 0, 0.)
        ds = DataStore.get()
        for box, e in zip(boxes, st.entities.values()):
            size = ship_size(ds, e.data_id)
            lo, hi, _ = _bounds(size.shape)
            self.assertEqual(box[2], tuple(v*size.scale for v in lo))
            self.assertEqual(box[3], tuple(v*size.scale for v in hi))

    def test_bounds_cache_introspection_stays_bounded_after_unknown_mods(self):
        from render.ship_sizes import _bounds, _ray_mesh
        from render.camera_geometry import station_bounds
        self.assertEqual(_bounds.cache_info().maxsize, 35)
        self.assertEqual(_ray_mesh.cache_info().maxsize, 35)
        self.assertEqual(station_bounds.cache_info().maxsize, 40)
        before = (_bounds.cache_info().currsize, _ray_mesh.cache_info().currsize, station_bounds.cache_info().currsize)
        for i in range(200):
            _bounds('mod:' + str(i))
            arrays = _ray_mesh('mod:' + str(i))
            self.assertTrue(all(not a.flags.writeable for a in arrays))
            station_bounds('mod_' + str(i), 'alien_' + str(i))
        after = (_bounds.cache_info().currsize, _ray_mesh.cache_info().currsize, station_bounds.cache_info().currsize)
        self.assertTrue(all(a <= b+1 for a,b in zip(after, before)))

    def test_picking_projects_owner_station_and_dataless_convoy_bounds(self):
        import math
        from types import SimpleNamespace
        from game.core.state import GameState, PlayerState
        from game.core.entity import Entity
        from render.input import InputController
        from render.ship_sizes import readable_size, _bounds
        from render.camera_geometry import station_bounds
        st = GameState()
        st.players[0] = PlayerState(0, faction='syndicate')
        camera = SimpleNamespace(eye_position=lambda: (0.,0.,-1000.),
                                 basis=lambda: ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)),
                                 height=800, fov=55., world_to_screen=lambda x,y,z: (x,y),
                                 _station_angle=lambda: 0.)
        controller = InputController.__new__(InputController)
        controller.state, controller.camera = st, camera
        station = Entity(id=1, kind='station', owner=0, data_id='shipyard', radius=120.)
        station.is_station = True
        lo, hi = station_bounds('shipyard', 'syndicate')
        mouse = (hi[0]*120./50., hi[1]*120./50.)
        self.assertLessEqual(controller._ship_pick_distance(station, (0.,0.), mouse, 28.), 14.)
        convoy = Entity(id=2, kind='ship', owner=0, data_id='trade_convoy')
        convoy.is_ship = True
        ppw = 800/(2000*math.tan(math.radians(55./2)))
        size = readable_size(DataStore.get(), 'trade_convoy', ppw, 'syndicate')
        lo, hi, _ = _bounds(size.shape)
        mouse = (hi[0]*size.scale, hi[1]*size.scale)
        self.assertLessEqual(controller._ship_pick_distance(convoy, (0.,0.), mouse, 28.), 14.)

    def test_nonimperial_station_shields_and_contacts_use_all_role_hardware(self):
        import copy, math
        from game.core.state import GameState, PlayerState
        from game.core.entity import Entity
        from render.renderer import Renderer
        from render.fleet_geometry import station_mesh
        from render.ship_sizes import station_contact_distance
        st = GameState()
        st.players[0] = PlayerState(0, faction='syndicate')
        station = Entity(id=1, kind='station', owner=0, data_id='shipyard', radius=120.)
        station.is_station = True
        st.entities = {1:station}
        r = Renderer.__new__(Renderer)
        r.state, r.ds, r.local_player, r.time = st, DataStore.get(), 0, 0.
        r._px_per_world = lambda *args, **kwargs: 1.
        points = [p for mesh in station_mesh('shipyard', 'syndicate').values() for _, tri in mesh for p in tri]
        hardware_radius = max(math.sqrt(sum(v*v for v in p)) for p in points)*120./50.
        self.assertAlmostEqual(r._station_visual_radius(station), hardware_radius)
        self.assertAlmostEqual(r._shield_radius(station), hardware_radius*1.08)
        fx = dict(kind='hull_hit', target_id=1, normal=(0.,0.,1.), pos=(0.,0.,120.), size=5.)
        before = copy.deepcopy(fx)
        contact = r._visual_hit(fx)
        self.assertTrue(contact.get('visual_contact'))
        self.assertAlmostEqual(contact['radius'], station_contact_distance('shipyard', 'syndicate', 120., (0.,0.,1.), 0.))
        self.assertEqual(fx, before)
        st.players[0].faction = 'imperial'
        self.assertEqual(r._visual_hit(fx), fx)
        self.assertAlmostEqual(r._shield_radius(station), 120.*1.35)

    def test_factory_damage_contacts_land_on_disconnected_station_triangles(self):
        import copy, math
        import numpy as np
        from game.core.state import GameState, PlayerState
        from game.core.vectors import Vec3
        from game.systems.unit_factory import UnitFactory
        from game.systems.damage import DamageSystem
        from render.renderer import Renderer
        from render.fleet_geometry import station_mesh
        from render.ship_sizes import station_contact_distance
        cases = [('rebel', did) for did in ('repair_dock', 'shipyard', 'sensor_station', 'fighter_platform')]
        cases += [(faction, 'repair_dock') for faction in ('confederacy', 'syndicate')]
        for faction, did in cases:
            for angle, scale, center in ((0., 1., (0.,0.,0.)), (.73, 1.7, (17.125,-31.25,91.375))):
                with self.subTest(faction=faction, station=did, angle=angle):
                    st = GameState()
                    st.players[0] = PlayerState(0, faction=faction)
                    station = UnitFactory(st).spawn_station(did, 0, Vec3(*center))
                    station.radius *= scale
                    normal = np.array((math.sin(angle), 0., math.cos(angle)))
                    DamageSystem(st)._spawn_hit('hull_hit', station,
                                               station.pos + Vec3(*normal)*100., None, 14.)
                    fx = st.effects[-1]
                    if did == 'repair_dock' and angle == 0. and scale == 1.:
                        self.assertEqual(fx['normal'], [0.,0.,1.])
                        self.assertEqual(fx['pos'], [0.,0.,42.])
                    before, effects = copy.deepcopy(st.to_dict(precise=True)), copy.deepcopy(st.effects)
                    r = Renderer.__new__(Renderer)
                    r.state, r.ds, r.local_player, r.time = st, DataStore.get(), 0, math.degrees(angle)/3.
                    contact = r._visual_hit(fx)
                    self.assertTrue(contact.get('visual_contact'))
                    point = np.asarray(contact['pos']) - center
                    local = np.array((point[0]*math.cos(angle)-point[2]*math.sin(angle),
                                      point[1], point[2]*math.cos(angle)+point[0]*math.sin(angle))) / (station.radius/50.)
                    desired = np.array((0.,0.,fx['radius'])) / (station.radius/50.)
                    candidates = []
                    on_surface = False
                    for mesh in station_mesh(did, faction).values():
                        for _, tri in mesh:
                            a, b, c = np.asarray(tri, dtype=float)
                            ab, ac = b-a, c-a
                            cross = np.cross(ab, ac)
                            if np.dot(cross, cross) > 1e-18:
                                for query, check in ((local, True), (desired, False)):
                                    projected = query-cross*np.dot(query-a, cross)/np.dot(cross,cross)
                                    uv = np.linalg.lstsq(np.column_stack((ab,ac)), projected-a, rcond=None)[0]
                                    if min(uv) >= -1e-8 and sum(uv) <= 1.+1e-8:
                                        if check:
                                            on_surface |= np.linalg.norm(projected-local) < 1e-7
                                        else:
                                            candidates.append(projected)
                            for u, v in ((a,b),(b,c),(c,a)):
                                edge = v-u
                                t = np.clip(np.dot(desired-u, edge)/np.dot(edge,edge), 0., 1.) if np.dot(edge,edge) else 0.
                                candidates.append(u+t*edge)
                    self.assertTrue(np.isfinite(local).all())
                    self.assertTrue(on_surface, f'contact {local} is not on hardware')
                    if station_contact_distance(did, faction, station.radius, normal, angle) == 0.:
                        nearest = min(np.linalg.norm(p-desired) for p in candidates)
                        self.assertAlmostEqual(np.linalg.norm(local-desired), nearest, places=7)
                    self.assertEqual(st.to_dict(precise=True), before)
                    self.assertEqual(st.effects, effects)
                    self.assertIs(fx, st.effects[-1])

    @staticmethod
    def _independent_surface_distance(mesh, query):
        """Scalar triangle/segment oracle independent of batched production code."""
        import numpy as np
        best = float('inf')
        for role in mesh.values():
            for _, tri in role:
                a, b, c = np.asarray(tri, dtype=float)
                ab, ac = b-a, c-a
                cross = np.cross(ab, ac)
                squared = np.dot(cross, cross)
                if squared > 1e-18:
                    projected = query-cross*np.dot(query-a, cross)/squared
                    uv = np.linalg.lstsq(np.column_stack((ab, ac)), projected-a, rcond=None)[0]
                    if min(uv) >= -1e-10 and sum(uv) <= 1.+1e-10:
                        best = min(best, np.linalg.norm(query-projected))
                for start, end in ((a,b), (b,c), (c,a)):
                    edge = end-start
                    squared = np.dot(edge, edge)
                    t = np.clip(np.dot(query-start, edge)/squared, 0., 1.) if squared else 0.
                    best = min(best, np.linalg.norm(query-(start+t*edge)))
        return best

    def test_factory_damage_ship_contacts_on_surface_and_nearest_when_ray_misses(self):
        import copy, math
        import numpy as np
        from game.core.state import GameState, PlayerState
        from game.core.vectors import Vec3
        from game.systems.unit_factory import UnitFactory
        from game.systems.damage import DamageSystem
        from render.renderer import Renderer
        from render.fleet_geometry import ship_mesh
        from render.ship_sizes import hull_contact_distance
        suffixes = ('vulture_squadron', 'bomber_squadron', 'corvette', 'frigate',
                    'cruiser', 'battleship', 'supercapital', 'constructor', 'colonizer')
        misses = set()
        for suffix in suffixes:
            for yaw, ppw in ((0., 1.), (.73, .015)):
                st = GameState()
                # Catalogue faction, not owner paint, must select the resolver.
                st.players[0] = PlayerState(0, faction='imperial')
                center = np.array((17.125, -31.25, 91.375))
                ship = UnitFactory(st).spawn_ship('confed_'+suffix, 0, Vec3(*center), yaw=yaw)
                r = Renderer.__new__(Renderer)
                r.state, r.ds, r.local_player = st, DataStore.get(), 0
                r._px_per_world = lambda *args, **kwargs: ppw
                size = r._ship_size(ship)
                self.assertEqual(size.shape, 'confederacy:'+('fighter' if suffix == 'vulture_squadron'
                                 else 'bomber' if suffix == 'bomber_squadron' else suffix))
                mesh = ship_mesh(size.shape)
                for direction in ((0.,0.,1.), (.4,.2,1.), (-.7,.1,.5), (.1,-.7,-.3)):
                    n = np.asarray(direction)/np.linalg.norm(direction)
                    ca, sa = math.cos(yaw), math.sin(yaw)
                    world = np.array((n[0]*ca+n[2]*sa, n[1], n[2]*ca-n[0]*sa))
                    DamageSystem(st)._spawn_hit('hull_hit', ship, ship.pos+Vec3(*world)*100., None, 14.)
                    fx = st.effects[-1]
                    before, effects = copy.deepcopy(st.to_dict(precise=True)), copy.deepcopy(st.effects)
                    with self.subTest(ship=suffix, yaw=yaw, direction=direction):
                        contact = r._visual_hit(fx)
                        self.assertTrue(contact.get('visual_contact'))
                        point = np.asarray(contact['pos'])-center
                        local = np.array((point[0]*ca-point[2]*sa, point[1], point[2]*ca+point[0]*sa))/size.scale
                        self.assertTrue(np.isfinite(local).all())
                        self.assertLess(self._independent_surface_distance(mesh, local), 1e-7)
                        self.assertAlmostEqual(float(contact['radius']), float(np.linalg.norm(point)), places=7)
                        if hull_contact_distance(size, world, yaw) == 0.:
                            misses.add(suffix)
                            desired_world = np.asarray(fx['pos'])-center
                            desired = np.array((desired_world[0]*ca-desired_world[2]*sa, desired_world[1],
                                                desired_world[2]*ca+desired_world[0]*sa))/size.scale
                            nearest = self._independent_surface_distance(mesh, desired)
                            self.assertAlmostEqual(float(np.linalg.norm(local-desired)), float(nearest), places=7)
                        self.assertEqual(st.to_dict(precise=True), before)
                        self.assertEqual(st.effects, effects)
                        self.assertIs(fx, st.effects[-1])
        self.assertIn('colonizer', misses)  # actual +Z disconnected-hull reproducer

    def test_factory_catalogue_contacts_cover_134_directions_and_convoys(self):
        import copy, math
        import numpy as np
        from game.core.state import GameState, PlayerState
        from game.core.entity import Entity
        from game.core.vectors import Vec3
        from game.systems.unit_factory import UnitFactory
        from game.systems.damage import DamageSystem
        from render.renderer import Renderer
        from render.fleet_geometry import ship_mesh
        from render.faction_visuals import KNOWN_SHIP_IDS
        ds = DataStore.get()
        directions = [tuple(float(sign*(axis == i)) for axis in range(3))
                      for i in range(3) for sign in (-1, 1)]
        for i in range(128):
            y = 1.-2.*(i+.5)/128
            angle = i*math.pi*(3.-math.sqrt(5.))
            radial = math.sqrt(1.-y*y)
            directions.append((radial*math.cos(angle), y, radial*math.sin(angle)))
        self.assertEqual(len(directions), 134)
        cases = [(ds.ships[did].faction, did) for did in sorted(KNOWN_SHIP_IDS)
                 if ds.ships[did].faction != 'imperial']
        cases += [(faction, 'trade_convoy') for faction in ('rebel', 'confederacy', 'syndicate')]
        for faction, did in cases:
            st = GameState()
            st.players[0] = PlayerState(0, faction=faction)
            center, yaw = np.array((17.125,-31.25,91.375)), .73
            if did == 'trade_convoy':
                ship = Entity(id=1, kind='ship', owner=0, data_id=did, pos=Vec3(*center), yaw=yaw, radius=42.)
                ship.is_ship = True
                st.entities[1] = ship
            else:
                ship = UnitFactory(st).spawn_ship(did, 0, Vec3(*center), yaw=yaw)
            r = Renderer.__new__(Renderer)
            r.state, r.ds, r.local_player = st, ds, 0
            r._px_per_world = lambda *args, **kwargs: .015
            size = r._ship_size(ship)
            triangles = np.asarray([tri for role in ship_mesh(size.shape).values() for _,tri in role])
            a, b, c = triangles[:,0], triangles[:,1], triangles[:,2]
            crosses = np.cross(b-a, c-a)
            areas = np.linalg.norm(crosses, axis=1)
            ca, sa = math.cos(yaw), math.sin(yaw)
            before = copy.deepcopy(st.to_dict(precise=True))
            for direction in directions:
                n = np.asarray(direction)
                world = (n[0]*ca+n[2]*sa, n[1], n[2]*ca-n[0]*sa)
                st.effects.clear()
                DamageSystem(st)._spawn_hit('hull_hit', ship, ship.pos+Vec3(*world)*100., None, 14.)
                fx = st.effects[-1]
                effects = copy.deepcopy(st.effects)
                with self.subTest(faction=faction, ship=did, direction=direction):
                    contact = r._visual_hit(fx)
                    self.assertTrue(contact.get('visual_contact'))
                    point = np.asarray(contact['pos'])-center
                    local = np.array((point[0]*ca-point[2]*sa, point[1], point[2]*ca+point[0]*sa))/size.scale
                    # Independent signed-edge and plane membership, not the
                    # production nearest-point/barycentric implementation.
                    valid = (areas > 1e-12) & (np.abs(np.einsum('ij,ij->i', local-a, crosses)) <= areas*1e-7)
                    for start, end in ((a,b), (b,c), (c,a)):
                        sides = np.einsum('ij,ij->i', np.cross(end-start, local-start), crosses)
                        valid &= sides >= -areas*1e-7
                    self.assertTrue(np.isfinite(local).all() and valid.any())
                    self.assertEqual(st.effects, effects)
                    self.assertIs(fx, st.effects[-1])
            self.assertEqual(st.to_dict(precise=True), before)

    def test_ship_contacts_preserve_legacy_shields_hidden_and_unresolved(self):
        import copy, math
        from dataclasses import replace
        from unittest.mock import patch
        from game.core.state import GameState, PlayerState
        from game.core.vectors import Vec3
        from game.systems.unit_factory import UnitFactory
        from game.systems.damage import DamageSystem
        from render.renderer import Renderer
        from render.ship_sizes import hull_contact_distance, hull_contact_offset
        st = GameState()
        st.players[0] = PlayerState(0, faction='rebel')
        st.players[1] = PlayerState(1, faction='confederacy')
        factory = UnitFactory(st)
        r = Renderer.__new__(Renderer)
        r.state, r.ds, r.local_player = st, DataStore.get(), 0
        r._px_per_world = lambda *args, **kwargs: .015
        for did in ('imperial_corvette', 'imperial_colonizer', 'confed_colonizer', 'rebel_corvette'):
            ship = factory.spawn_ship(did, 0, Vec3(17.125,-31.25,91.375), yaw=.73)
            for kind in ('hull_hit', 'shield_hit'):
                DamageSystem(st)._spawn_hit(kind, ship, ship.pos+Vec3(.4,.2,1.)*100., None, 14.)
                fx = st.effects[-1]
                before, effects = copy.deepcopy(st.to_dict(precise=True)), copy.deepcopy(st.effects)
                if kind == 'shield_hit' or did.startswith('imperial'):
                    size = r._ship_size(ship)
                    n = tuple(fx['normal'])
                    length = math.sqrt(sum(x*x for x in n)) or 1.
                    n = tuple(x/length for x in n)
                    center = (ship.pos.x, ship.pos.y, ship.pos.z)
                    radius = r._shield_radius(ship) if kind == 'shield_hit' else hull_contact_distance(size, n, ship.yaw)
                    expected = dict(fx, center=center, radius=radius,
                                    pos=tuple(center[i]+n[i]*radius for i in range(3)),
                                    size=min(float(fx.get('size',5.)), size.length*.12), visual_contact=True)
                    with patch('render.ship_sizes.hull_contact_offset', side_effect=AssertionError('protected path')):
                        self.assertEqual(r._visual_hit(fx), expected)
                else:
                    with patch('render.ship_sizes.hull_contact_offset', return_value=None):
                        self.assertIs(r._visual_hit(fx), fx)
                    bad_size = replace(r._ship_size(ship), scale=0.)
                    self.assertIsNone(hull_contact_offset(bad_size, fx['normal'], ship.yaw, (0.,0.,0.)))
                    self.assertIsNone(hull_contact_offset(r._ship_size(ship), fx['normal'], ship.yaw, (float('nan'),0.,0.)))
                self.assertEqual(st.to_dict(precise=True), before)
                self.assertEqual(st.effects, effects)
        hidden = factory.spawn_ship('confed_colonizer', 1, Vec3(100000.,0.,0.))
        DamageSystem(st)._spawn_hit('hull_hit', hidden, hidden.pos+Vec3(0.,0.,100.), None, 14.)
        fx = st.effects[-1]
        before, effects = copy.deepcopy(st.to_dict(precise=True)), copy.deepcopy(st.effects)
        with patch.object(r, '_ship_size', side_effect=AssertionError('hidden geometry')):
            self.assertIs(r._visual_hit(fx), fx)
        self.assertEqual(st.to_dict(precise=True), before)
        self.assertEqual(st.effects, effects)

    def test_factory_station_contacts_preserve_legacy_visibility_and_unresolved_effects(self):
        import copy
        from unittest.mock import patch
        from game.core.state import GameState, PlayerState
        from game.core.vectors import Vec3
        from game.systems.unit_factory import UnitFactory
        from game.systems.damage import DamageSystem
        from render.renderer import Renderer
        from render.ship_sizes import station_contact_offset
        st = GameState()
        st.players[0] = PlayerState(0, faction='imperial')
        st.players[1] = PlayerState(1, faction='rebel')
        factory = UnitFactory(st)
        station = factory.spawn_station('repair_dock', 0, Vec3())
        hidden = factory.spawn_station('repair_dock', 1, Vec3(100000.,0.,0.))
        r = Renderer.__new__(Renderer)
        r.state, r.ds, r.local_player, r.time = st, DataStore.get(), 0, 0.
        for target in (station, hidden):
            for kind in ('hull_hit', 'shield_hit'):
                DamageSystem(st)._spawn_hit(kind, target, target.pos+Vec3(0.,0.,100.), None, 14.)
                fx = st.effects[-1]
                before, effects = copy.deepcopy(st.to_dict(precise=True)), copy.deepcopy(st.effects)
                with patch('render.ship_sizes.station_contact_offset', side_effect=AssertionError('must not size protected/hidden target')):
                    self.assertIs(r._visual_hit(fx), fx)
                self.assertEqual(st.to_dict(precise=True), before)
                self.assertEqual(st.effects, effects)
        st.players[0].faction = 'rebel'
        station.radius = 0.  # no finite nonzero hardware transform to resolve
        DamageSystem(st)._spawn_hit('hull_hit', station, Vec3(0.,0.,100.), None, 14.)
        fx = st.effects[-1]
        before, effects = copy.deepcopy(st.to_dict(precise=True)), copy.deepcopy(st.effects)
        self.assertIsNone(station_contact_offset('repair_dock', 'rebel', 0., (0.,0.,1.), 0., (0.,0.,0.)))
        self.assertIsNone(station_contact_offset('repair_dock', 'rebel', 70., (0.,0.,1.), 0., (float('nan'),0.,0.)))
        self.assertIs(r._visual_hit(fx), fx)
        self.assertFalse(fx.get('visual_contact'))
        self.assertEqual(st.to_dict(precise=True), before)
        self.assertEqual(st.effects, effects)

    def test_station_outline_scopes_explicit_gl_attribute_groups(self):
        from contextlib import ExitStack
        from unittest.mock import Mock, patch
        from render import renderer as module
        from OpenGL import GL
        r = module.Renderer.__new__(module.Renderer)
        r.time = 0.
        r._emit_detail_mesh = Mock()
        with ExitStack() as stack:
            for name, value in vars(module).items():
                if name.startswith('gl') and callable(value):
                    stack.enter_context(patch.object(module, name, Mock()))
            push = stack.enter_context(patch.object(GL, 'glPushAttrib', Mock()))
            for name in ('glPopAttrib','glDisable','glEnable','glDepthMask','glPolygonMode'):
                stack.enter_context(patch.object(GL, name, Mock()))
            r._draw_station_outline('repair_dock', 'rebel', (0.,0.,0.), 70., (.2,.4,.8))
        expected = (GL.GL_ENABLE_BIT | GL.GL_LIGHTING_BIT | GL.GL_CURRENT_BIT |
                    GL.GL_DEPTH_BUFFER_BIT | GL.GL_COLOR_BUFFER_BIT | GL.GL_POLYGON_BIT |
                    GL.GL_LINE_BIT | GL.GL_TEXTURE_BIT)
        push.assert_called_once_with(expected)

    def test_nonimperial_construction_site_uses_chosen_station_hardware(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from contextlib import ExitStack
        from game.core.state import GameState, PlayerState
        from game.core.vectors import Vec3
        from game.systems.unit_factory import UnitFactory
        from render import renderer as module
        from OpenGL import GL
        st = GameState()
        st.players[0] = PlayerState(0, faction='rebel')
        builder = UnitFactory(st).spawn_ship('imperial_constructor', 0, Vec3())
        builder.build_queue = [dict(kind='station', item='shipyard', pos=(400.,0.,0.), time_left=1., total=2.)]
        r = module.Renderer.__new__(module.Renderer)
        r.ds, r.state, r.local_player = DataStore.get(), st, 0
        r._in_front = lambda *args: True
        r._owner_color = lambda owner: (.2,.4,.8)
        r._draw_station_outline = Mock()
        with ExitStack() as stack:
            for name, value in vars(module).items():
                if name.startswith('gl') and callable(value):
                    stack.enter_context(patch.object(module, name, Mock()))
            for name in ('glPushAttrib','glPopAttrib','glDisable'):
                stack.enter_context(patch.object(GL, name, Mock()))
            r._draw_construction_sites()
        self.assertEqual(r._draw_station_outline.call_args.args[:3], ('shipyard', 'rebel', (400.,0.,0.)))

    def test_preview_payload_and_geometry_are_faction_aware_readonly(self):
        import copy
        from types import SimpleNamespace
        from unittest.mock import patch, Mock
        from contextlib import ExitStack
        from game.core.state import GameState, PlayerState
        from game.core.vectors import Vec3
        from game.systems.unit_factory import UnitFactory
        from render.camera import Camera
        from render.input import InputController
        from render import renderer as module
        from render.fleet_geometry import station_mesh
        from OpenGL import GL
        st = GameState()
        st.players[0] = PlayerState(0, faction='rebel')
        builder = UnitFactory(st).spawn_ship('imperial_constructor', 0, Vec3())
        hud = SimpleNamespace(placement={'builder_id':builder.id, 'station_kind':'shipyard'})
        camera = Camera(1280, 800)
        camera.screen_to_world = lambda *args: (500., 0., 0.)
        controller = InputController(st, camera, hud, SimpleNamespace())
        before = copy.deepcopy(st.to_dict(precise=True))
        with patch('render.input.pygame.mouse.get_pos', return_value=(10,20)):
            controller.update_placement()
        ghost = hud.placement['ghost']
        self.assertEqual(ghost['faction'], 'rebel')
        self.assertEqual(ghost['station_kind'], 'shipyard')
        self.assertEqual(ghost['builder_id'], builder.id)
        r = module.Renderer.__new__(module.Renderer)
        r.ds, r.state, r.local_player, r.time = DataStore.get(), st, 0, 0.
        r._in_front = lambda *args: True
        r.placement = hud.placement
        captured = []
        r._emit_detail_mesh = captured.append
        with ExitStack() as stack:
            for name, value in vars(module).items():
                if name.startswith('gl') and callable(value):
                    stack.enter_context(patch.object(module, name, Mock()))
            for name in ('glPushAttrib','glPopAttrib','glPolygonMode','glDisable','glEnable','glDepthMask'):
                stack.enter_context(patch.object(GL, name, Mock()))
            r._draw_placement_preview()
        self.assertEqual(captured, list(station_mesh('shipyard', 'rebel').values()))
        self.assertEqual(st.to_dict(precise=True), before)
        builder.owner = 1
        captured.clear()
        r._draw_placement_preview()  # stale/foreign builder cannot expose a ghost
        self.assertFalse(captured)

    def test_display_lists_dispatch_canonical_geometry_without_nested_lists(self):
        from contextlib import ExitStack
        from unittest.mock import patch, Mock
        from render import renderer as module
        from OpenGL import GL
        r = module.Renderer.__new__(module.Renderer)
        r.ship_lists = {}
        emitted = []
        r._emit_detail_hull = lambda shape, role: emitted.append((shape, role))
        r._emit_detail_mesh = lambda mesh: emitted.append(mesh)
        with ExitStack() as stack:
            stack.enter_context(patch.object(module._gl, 'glGenLists', side_effect=range(1, 100)))
            for name in ('glNewList', 'glEndList'):
                stack.enter_context(patch.object(module, name, Mock()))
            for name in ('glPushAttrib', 'glPopAttrib', 'glDisable'):
                stack.enter_context(patch.object(GL, name, Mock()))
            first = r._ship_display_list('rebel:corvette_dark')
            self.assertEqual(emitted[0], ('rebel:corvette', 'base'))
            self.assertEqual(len(emitted), 6)
            self.assertEqual(first, r._ship_display_list('rebel:corvette_dark'))
            r._station_detail_list('shipyard', 'base', 'rebel')
            self.assertIn('station_detail:rebel:shipyard:base', r.ship_lists)
            for i in range(20):
                r._ship_display_list('mod_' + str(i))
                r._station_detail_list('mod_' + str(i), 'base', 'unknown')
            self.assertEqual(len(r.ship_lists), 14)  # two ships x six roles + two station roles

    def test_camera_and_renderer_share_owner_convoy_and_station_geometry(self):
        import copy
        from game.core.state import GameState, PlayerState
        from game.core.entity import Entity
        from render.camera_geometry import scene_boxes, station_bounds
        from render.ship_sizes import ship_size, _bounds
        from render.renderer import Renderer
        st = GameState()
        st.players[0] = PlayerState(0, faction='rebel')
        station = Entity(id=1, kind='station', owner=0, data_id='shipyard', radius=120.)
        station.is_station = True
        convoy = Entity(id=2, kind='ship', owner=0, data_id='trade_convoy')
        convoy.is_ship = True
        st.entities = {1:station, 2:convoy}
        r = Renderer.__new__(Renderer)
        r.ds, r.state, r.local_player = DataStore.get(), st, 0
        r._px_per_world = lambda *args, **kwargs: 1.
        before = copy.deepcopy(st.to_dict(precise=True))
        size = r._ship_size(convoy)
        self.assertEqual(size.shape, 'rebel:convoy')
        boxes = scene_boxes(st, 0, 0.)
        lo, hi = station_bounds('shipyard', 'rebel')
        self.assertEqual(boxes[0][2], tuple(v*(120./50.) for v in lo))
        clo, chi, _ = _bounds(size.shape)
        self.assertEqual(boxes[1][2], tuple(v*size.scale for v in clo))
        self.assertEqual(st.to_dict(precise=True), before)

    def test_faction_geometry_and_normalized_lengths(self):
        from render.fleet_geometry import ship_mesh, station_mesh
        from render.ship_sizes import ship_size, _bounds
        ds = DataStore.get()
        reference = ship_size(ds, 'imperial_corvette').length
        for faction, prefix in [('rebel', 'rebel'), ('confederacy', 'confed'), ('syndicate', 'syndicate')]:
            size = ship_size(ds, prefix + '_corvette', faction)
            self.assertEqual(size.shape, faction + ':corvette')
            self.assertAlmostEqual(size.length, reference)
            self.assertIs(ship_mesh(size.shape), ship_mesh(size.shape))
            self.assertNotEqual(ship_mesh(size.shape), ship_mesh('needle'))
            self.assertNotEqual(station_mesh('shipyard', faction), station_mesh('shipyard'))
            lo, hi, radius = _bounds(size.shape)
            self.assertAlmostEqual((hi[2]-lo[2])*size.scale, reference)
            self.assertAlmostEqual(radius*size.scale, size.radius)
        self.assertEqual(ship_mesh('unknown:anything'), ship_mesh('box'))
        self.assertEqual(station_mesh('unknown', 'rebel'), station_mesh('research_station'))


if __name__ == '__main__':
    unittest.main()
