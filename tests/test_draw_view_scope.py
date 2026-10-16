"""Draw-local reuse, exact legacy arithmetic, and live boundary contracts (no GL)."""
import copy
from dataclasses import asdict
import math
import unittest
from contextlib import nullcontext, ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from game.core.entity import Entity
from game.core.vectors import Vec3
from game.data.store import DataStore
from render.camera import Camera
from render.renderer import Renderer, SHIELD_MIN_PX
from render import ship_sizes


class DrawViewScopeTests(unittest.TestCase):
    def make_renderer(self):
        r = Renderer.__new__(Renderer)
        r.camera = Camera(1280, 800)
        r.ds = DataStore.get()
        r.state = SimpleNamespace(players={0: SimpleNamespace(faction='imperial')},
                                  entities={}, can_see=lambda *args: True, tick=1)
        r.local_player = 0
        r.time = 0.
        return r

    def draw_with(self, r, callback):
        # Only the synchronous read-only body is replaced; real draw owns scope.
        with patch.object(r, '_draw_read_only', side_effect=lambda *args: callback()), \
                patch('game.systems.visibility.presentation_sensor_batch', return_value=nullcontext()):
            r.draw(0., set())

    def entity(self, data_id='imperial_corvette', eid=1):
        e = Entity(id=eid, kind='ship', owner=0, data_id=data_id)
        e.is_ship = True
        return e

    def test_one_size_and_view_computation_per_draw(self):
        r = self.make_renderer()
        e = self.entity()
        with patch('render.ship_sizes.readable_size', wraps=ship_sizes.readable_size) as size, \
                patch.object(r.camera, 'basis', wraps=r.camera.basis) as basis:
            def body():
                for _ in range(12):
                    r._ship_size(e)
                    r._shield_radius(e)
                    r._px_per_world((23., 47., -123.))
                    r._in_front((0., 0., 0.), 0.)
            self.draw_with(r, body)
            self.assertEqual(size.call_count, 1)
            self.assertEqual(basis.call_count, 1)
            self.draw_with(r, body)
            self.assertEqual(size.call_count, 2)
            self.assertEqual(basis.call_count, 2)

    def test_uncached_oracle_discriminates_same_repeated_workload(self):
        r = self.make_renderer()
        old = self.oracle(r)
        e = self.entity()
        def workload(renderer):
            for _ in range(12):
                renderer._ship_size(e)
                renderer._shield_radius(e)
                renderer._px_per_world((23., 47., -123.))
                renderer._in_front((0., 0., 0.), 0.)
        with patch('render.ship_sizes.readable_size', wraps=ship_sizes.readable_size) as size, \
                patch.object(r.camera, 'basis', wraps=r.camera.basis) as basis:
            workload(old)
            old_counts = (size.call_count, basis.call_count)
            size.reset_mock()
            basis.reset_mock()
            self.draw_with(r, lambda: workload(r))
            new_counts = (size.call_count, basis.call_count)
        self.assertEqual(old_counts[0], 24)
        self.assertEqual(new_counts, (1, 1))
        self.assertGreater(old_counts[0], new_counts[0])
        self.assertGreater(old_counts[1], new_counts[1])

    def test_scope_restores_absent_attribute_even_on_exception(self):
        r = self.make_renderer()
        def fail():
            r._ship_size(self.entity())
            raise RuntimeError('draw failed')
        with self.assertRaisesRegex(RuntimeError, 'draw failed'):
            self.draw_with(r, fail)
        self.assertFalse(hasattr(r, '_draw_view'))

    def test_apply_refresh_does_not_reuse_pre_apply_safe_eye(self):
        r = self.make_renderer()
        r.skip = {'starfield', 'nebulas', 'star', 'jumppoints', 'planets',
                  'planet_shields', 'effects', 'projectiles', 'ships', 'shields',
                  'sites', 'surface_slots', 'markers', 'rings'}
        r.fog = SimpleNamespace(draw=lambda *args: None)
        r._setup_lighting = lambda: None
        before, after = [], []
        def ensure(selection):
            before.append(r._ship_size(e))
            return {'visible': []}
        e = self.entity()
        r._ensure_frame_cache = ensure
        # Simulate refresh_scene changing collision keep-outs at apply, not a
        # camera parameter mutation: safe eye changes with the same geometry key.
        def refresh():
            r.camera._camera_boxes = ((r.camera._requested_eye(), 900.),)
            r.camera._safe_cache = None
        r.camera.refresh_scene = refresh
        with ExitStack() as stack:
            for name in ('glMatrixMode', 'glLoadIdentity', '_gluPerspective',
                         'gluLookAt', 'glGetFloatv'):
                stack.enter_context(patch('render.camera.' + name))
            for name in ('glMatrixMode', 'glClear'):
                stack.enter_context(patch('render.renderer.' + name))
            stack.enter_context(patch('render.renderer.glFlush',
                side_effect=lambda: after.append(r._ship_size(e))))
            stack.enter_context(patch('game.systems.visibility.presentation_sensor_batch',
                                       return_value=nullcontext()))
            r.draw(0., set())
        self.assertNotEqual(before[0], after[0])
        self.assertEqual(after[0], r._ship_size(e))

    def oracle(self, r):
        old = LegacyOracle()
        old.__dict__.update(r.__dict__)
        return old

    def test_exact_legacy_projection_camera_matrix(self):
        r = self.make_renderer()
        for distance, pitch, fov, height in ((180., 8., 30., 333),
                (3000., 55., 55., 800), (22000., 89., 95., 2160)):
            r.camera.distance, r.camera.pitch = distance, pitch
            r.camera.fov, r.camera.height = fov, height
            r.camera._camera_boxes = ((r.camera._requested_eye(), 250.),)
            r.camera._safe_cache = None
            self.assertNotEqual(r.camera.eye_position(), r.camera._requested_eye())
            eye = r.camera.eye_position()
            fwd = r.camera.basis()[2]
            points = [(0., 0., 0.), (777., -21., -1234.), eye,
                tuple(eye[i]-fwd[i]*100 for i in range(3)),
                tuple(eye[i]+fwd[i]*1e-8 for i in range(3))]
            old = self.oracle(r)
            def body():
                for pos in points:
                    e = self.entity()
                    e.pos = Vec3(*pos)
                    self.assertEqual(r._ship_size(e), old._ship_size(e))
                    self.assertEqual(r._shield_radius(e), old._shield_radius(e))
                    for radius in (0., 25., 1000.):
                        self.assertEqual(r._in_front(pos, radius), old._in_front(pos, radius))
                        self.assertEqual(r._in_front(Vec3(*pos), radius), old._in_front(Vec3(*pos), radius))
                    for depth in (False, True):
                        self.assertEqual(r._px_per_world(pos, camera_depth=depth),
                                         old._px_per_world(pos, camera_depth=depth))
            self.draw_with(r, body)
            body()  # Standalone must use the same exact arithmetic.

    def test_exact_catalogue_sizes_shields_contacts_read_only(self):
        r = self.make_renderer()
        from render.faction_visuals import FACTIONS
        ids = list(r.ds.ships) + ['trade_convoy', 'unknown_mod_ship']
        for faction in FACTIONS:
            r.state.players[0].faction = faction
            for did in ids + ['command_station', 'shipyard']:
                e = self.entity(did)
                e.pos = Vec3(123., -7., -321.)
                e.is_station = did in ('command_station', 'shipyard')
                e.is_ship = not e.is_station
                e.radius = 150.
                r.state.entities = {e.id: e}
                old = self.oracle(r)
                before = copy.deepcopy(asdict(e))
                def body():
                    if not e.is_station:
                        self.assertEqual(r._ship_size(e), old._ship_size(e))
                    self.assertEqual(r._shield_radius(e), old._shield_radius(e))
                    for kind in ('hull_hit', 'shield_hit'):
                        fx = dict(kind=kind, target_id=e.id, normal=(.2,.1,1.),
                                  pos=(123., -7., -201.), radius=33., size=18.)
                        saved = copy.deepcopy(fx)
                        self.assertEqual(r._visual_hit(fx), old._visual_hit(fx))
                        self.assertEqual(fx, saved)
                self.draw_with(r, body)
                self.assertEqual(asdict(e), before)

    def test_same_tick_live_mutation_between_scopes_and_id_collision(self):
        r = self.make_renderer()
        # Isolate catalogue mutation; never modify the shared singleton.
        r.ds = copy.deepcopy(r.ds)
        a, b = self.entity(), self.entity('imperial_supercapital')
        self.assertEqual(a.id, b.id)
        for iteration in range(3):
            old = self.oracle(r)
            def body():
                self.assertEqual(r._ship_size(a), old._ship_size(a))
                self.assertEqual(r._ship_size(b), old._ship_size(b))
                self.assertNotEqual(r._ship_size(a), r._ship_size(b))
            self.draw_with(r, body)
            body()
            a.pos.x += 333.
            a.pos.z -= 765.
            r.camera.distance *= 2.
            r.camera.yaw += 17.
            r.camera.width += 150
            r.camera.height += 100
            r.camera.fov += 4.
            r.ds.ships[a.data_id].category = 'frigate' if iteration % 2 == 0 else 'corvette'
        self.assertEqual(r.state.tick, 1)
        previous = r._shield_radius(a)
        r.camera.distance *= 4.
        self.assertNotEqual(previous, r._shield_radius(a))

    def test_nested_draw_restores_exact_outer_scope(self):
        r = self.make_renderer()
        e = self.entity()
        sentinel = {'prior': object()}
        r._draw_view = sentinel
        def outer():
            scope = r._draw_view
            size = r._ship_size(e)
            self.draw_with(r, lambda: self.assertIsNot(r._draw_view, scope))
            self.assertIs(r._draw_view, scope)
            self.assertIs(r._ship_size(e), size)
            def fail():
                raise ValueError('inner')
            with self.assertRaises(ValueError):
                self.draw_with(r, fail)
            self.assertIs(r._draw_view, scope)
        self.draw_with(r, outer)
        self.assertIs(r._draw_view, sentinel)


class LegacyOracle:
    """Frozen 6ea098f helper bodies, independent of candidate helpers."""

    def _in_front(self, pos, radius: float) -> bool:
        """False when the object's center is behind/at the eye plane.

        Triangle fans crossing the near plane project with mirrored winding
        and smear giant shapes across the screen — this guard prevents that.
        """
        cam = self.camera
        eye = cam.eye_position()
        _, _, fwd = cam.basis()
        depth = ((pos[0] if hasattr(pos, "__len__") else pos.x) - eye[0]) * fwd[0] \
            + ((pos[1] if hasattr(pos, "__len__") else pos.y) - eye[1]) * fwd[1] \
            + ((pos[2] if hasattr(pos, "__len__") else pos.z) - eye[2]) * fwd[2]
        return depth > radius

    def _station_visual_radius(self, e):
        from render.faction_visuals import owner_faction, normalize_station_key
        faction, data_id = normalize_station_key(e.data_id,
                            owner_faction(getattr(self, 'state', None), e.owner))
        if faction == 'imperial':
            return e.radius
        from render.camera_geometry import station_radius
        return station_radius(data_id, faction) * (e.radius / 50.)

    def _ship_size(self, e):
        from render.ship_sizes import readable_size
        from render.faction_visuals import owner_faction
        return readable_size(self.ds, e.data_id,
                             self._px_per_world((e.pos.x, e.pos.y, e.pos.z), camera_depth=True),
                             owner_faction(getattr(self, 'state', None), e.owner))

    def _visual_hit(self, fx):
        """Copy sim contacts onto visual surfaces; never modify effect/save data."""
        target_id = fx.get('target_id')
        # Ballistic effects may expose a legal historical contact, not a hidden
        # target's current transform. Gate before any live-position sizing/remap.
        if not self.state.can_see(self.local_player, target_id):
            return fx
        e = self.state.entities.get(target_id)
        if e is None:
            return fx
        if e.is_station:
            if e.planet_building_slot is not None or e.satellite_slot is not None:
                from render.planet_building_geometry import attached_contact_point
                center = e.pos.to_tuple()
                n = tuple(fx.get('normal', (0., 0., 1.)))
                length = math.sqrt(sum(x*x for x in n)) or 1.
                n = tuple(x / length for x in n)
                point = attached_contact_point(self.state, e, n, tuple(fx.get('pos', center)))
                if point is None:
                    return fx
                return dict(fx, center=center, pos=point,
                            radius=math.dist(center, point), visual_contact=True)
            from render.faction_visuals import owner_faction, normalize_station_key
            faction, _ = normalize_station_key(e.data_id, owner_faction(self.state, e.owner))
            if faction == "imperial":
                return fx  # protected legacy station effect path
            from render.ship_sizes import station_contact_offset
            n = tuple(fx.get("normal", (0., 0., 1.)))
            length = math.sqrt(sum(x*x for x in n)) or 1.
            n = tuple(x/length for x in n)
            center = (e.pos.x, e.pos.y, e.pos.z)
            if fx.get("kind") == "shield_hit":
                radius = self._shield_radius(e)
                offset = tuple(x*radius for x in n)
            else:
                desired = tuple(fx.get('pos', center)[i]-center[i] for i in range(3))
                offset = station_contact_offset(e.data_id, faction, e.radius, n,
                                                math.radians(self.time * 3.), desired)
                if offset is None:
                    return fx
                radius = math.sqrt(sum(x*x for x in offset))
            return dict(fx, center=center, radius=radius,
                        pos=tuple(center[i]+offset[i] for i in range(3)),
                        visual_contact=True)
        if not (e.is_ship or e.is_squadron):
            return fx
        from render.ship_sizes import hull_contact_distance, hull_contact_offset
        from render.faction_visuals import normalize_ship_key
        size = self._ship_size(e)
        n = tuple(fx.get('normal', (0., 0., 1.)))
        length = math.sqrt(sum(x*x for x in n)) or 1.
        n = tuple(x/length for x in n)
        center = (e.pos.x, e.pos.y, e.pos.z)
        # Canonical render identity protects legacy/unknown-mod hulls even
        # when captured by a non-Imperial owner. Shields retain their old path.
        if fx.get('kind') != 'shield_hit' and ':' in normalize_ship_key(size.shape):
            desired = tuple(fx.get('pos', center)[i]-center[i] for i in range(3))
            offset = hull_contact_offset(size, n, e.yaw, desired)
            if offset is None:
                return fx
            radius = math.sqrt(sum(x*x for x in offset))
        else:
            radius = (self._shield_radius(e) if fx.get('kind') == 'shield_hit' else
                      hull_contact_distance(size, n, e.yaw))
            offset = tuple(x*radius for x in n)
        return dict(fx, center=center, radius=radius,
                    pos=tuple(center[i]+offset[i] for i in range(3)),
                    size=min(float(fx.get('size', 5.)), size.length*.12),
                    visual_contact=True)

    def _shield_radius(self, e) -> float:
        """World radius of a unit's shield shell.

        Includes the readability floor (see SHIELD_MIN_PX) so the bubble and
        the quadrant hit-flash it sits on always agree on where the surface is.
        """
        if not e.is_station and (e.is_ship or e.is_squadron):
            return self._ship_size(e).radius * 1.08
        r = e.radius * 1.35
        if e.is_station:
            from render.faction_visuals import owner_faction, normalize_station_key
            faction, _ = normalize_station_key(e.data_id, owner_faction(getattr(self, "state", None), e.owner))
            if faction != "imperial":
                r = self._station_visual_radius(e) * 1.08
        ppw = self._px_per_world((e.pos.x, e.pos.y, e.pos.z))
        if ppw > 0.0:
            want_r = SHIELD_MIN_PX * 0.5 / ppw
            if want_r > r:
                r = want_r
        return r

    def _px_per_world(self, pos, *, camera_depth=False) -> float:
        """Screen pixels per world unit at `pos` (0.0 if behind the camera)."""
        if not self._in_front(pos, 0.0):
            return 0.0
        eye = self.camera.eye_position()
        if camera_depth:
            # Ship LOD must agree at equal camera depth, including off-axis hulls.
            _, _, forward = self.camera.basis()
            dist = sum((pos[i]-eye[i])*forward[i] for i in range(3))
        else:
            # Preserve the existing station/planet/general-effects appearance.
            dist = math.sqrt(sum((pos[i]-eye[i])**2 for i in range(3)))
        if dist <= 1e-6:
            return 0.0
        return self.camera.height / (
            2.0 * dist * math.tan(math.radians(self.camera.fov / 2)))
