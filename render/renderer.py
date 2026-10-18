"""Main renderer: draws the world from GameState (pure view — never mutates sim).

Compatibility OpenGL renderer: GLSL 1.20 materials shade opaque ships and planets,
with a fixed-function fallback. Cached solid meshes, procedural sky/planet maps
and screen-space scale LOD keep fleets readable.
"""
from __future__ import annotations

import math
import hashlib
import os
import random

import pygame

from OpenGL.GL import (
    glBegin, glBlendFunc, glClear, glCallList, glColor3f, glColor4f,
    glDepthMask, glDisable, glEnable, glEnd, glEndList, glFlush, glLineWidth,
    glMatrixMode, glNewList, glNormal3f, glPopAttrib, glPopMatrix,
    glPushMatrix, glRotatef, glScalef, glTexCoord2f, glTranslatef, glVertex3f,
    glBindTexture, GL_BLEND, GL_CULL_FACE, GL_COLOR_BUFFER_BIT, GL_COMPILE,
    GL_CURRENT_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_LIGHTING,
    GL_LINE_LOOP, GL_LINE_STRIP, GL_LINES, GL_MODELVIEW, GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA, GL_POINTS, GL_POLYGON, GL_QUADS, GL_QUAD_STRIP,
    GL_SRC_ALPHA,
    GL_TEXTURE_2D, GL_TRANSFORM_BIT, GL_TRIANGLES, GL_TRIANGLE_FAN,
)
import OpenGL.GL as _gl

from render.camera import cross3, normalize3
from render.fog import FogMask, known_entities, effect_visible, position, segment_visible
from render import textures as tex
from render import markers as mk
from render.fleet_materials import FleetMaterials
from render.fleet_geometry import armor_loft, ship_mesh, station_mesh, ROLES
from render.asset_selection import is_authored, gpu_cache_key, selected_binding

from game.core.entity import Entity, QUADRANTS
from game.core.vectors import Vec3
from game.data.store import DataStore

# Shield bubbles never render smaller than this across, in screen pixels. The
# hull pass applies the same idea to ship scale (spec §35 readability): without
# it a distant bubble resolves to nothing but its rim and collapses back into
# the flat outline circle the additive shell replaced.
SHIELD_MIN_PX = 74.0

# Ownership markers are clamped in screen pixels, so a marker keeps the same
# readable footprint whether the hull under it is 2 px or 200 px. This is the
# opposite of SHIELD_MIN_PX's job above: that one keeps the bubble honest about
# how big the object is, this one deliberately ignores apparent size.
MARKER_ALPHA = 0.92

# --- weapon fire look (#90) -------------------------------------------------
# Laser-family projectiles are thin rectangles elongated along their heading and
# torpedoes/missiles are squares, instead of every bolt being the same round
# glow-and-speck. Ion, plasma, kinetic and beam weapons keep that treatment: the
# brief is explicit that super weapons like the biggest ships and the pulsar
# cannon stay as they are.
BOLT_WEAPON_TYPES = ("laser", "point_defense", "turbolaser")
SQUARE_WEAPON_TYPES = ("torpedo", "missile")

BOLT_LENGTH_PER_SIZE = 5.5      # bolt length, in weapon data sizes
BOLT_WIDTH_PER_SIZE = 0.85      # bolt width: long and thin, never a dot
BOLT_MIN_PX = (3.6, 1.8)        # SCREEN-space floor (length, width) in pixels
SQUARE_SIDE_PER_SIZE = 2.1
SQUARE_MIN_PX = 3.0
# Soft additive halo around the hot core, as a multiple of the core's extents.
# Kept tight on purpose: the halo is drawn additively OVER the core, so an
# oversized or over-bright halo sums past 1.0 and bleaches the bolt to white,
# throwing away the per-weapon colour at close range.
BOLT_HALO = (1.7, 2.2)
SQUARE_HALO = 2.0
HALO_ALPHA = 0.26
CORE_ALPHA = 0.92
#: How far the core is pushed towards white. Deliberately partial: a flat
#: "+0.45 clamped" turned every light-coloured bolt into a white slab.
CORE_WHITEN = 0.28


def projectile_shape(weapon_type: str | None) -> str:
    """'bolt', 'square' or 'legacy' for a weapon family (#90)."""
    if weapon_type in BOLT_WEAPON_TYPES:
        return "bolt"
    if weapon_type in SQUARE_WEAPON_TYPES:
        return "square"
    return "legacy"


def projectile_extents(shape: str, size: float, px_per_world: float) -> tuple[float, float]:
    """(length, width) of one projectile's core quad, in world units.

    Pure, so the proportions are testable without a GL context. Both extents
    carry a SCREEN-space floor: a world-only size is ~1 px at overview range,
    which is exactly the readability failure the old point sprites had.
    """
    if shape == "square":
        side = max(size * SQUARE_SIDE_PER_SIZE, SQUARE_MIN_PX * px_per_world)
        return side, side
    return (max(size * BOLT_LENGTH_PER_SIZE, BOLT_MIN_PX[0] * px_per_world),
            max(size * BOLT_WIDTH_PER_SIZE, BOLT_MIN_PX[1] * px_per_world))


def square_quad_offsets(side: float):
    """Axis-aligned corners for a square projectile.

    Squares are deliberately NOT oriented by their heading: a square rotated to
    follow a diagonal heading reads as a diamond, which is not what "torpedoes
    look like squares" means. Caught by eye in the close-combat capture.
    """
    half = side / 2.0
    return ((half, half), (half, -half), (-half, -half), (-half, half))


def projectile_quad_offsets(vel, right, up, length: float, width: float):
    """Four corners, in the camera plane, of a projectile quad.

    Offsets are (u, v) along `right`/`up`; the renderer maps them to world space.
    The long axis follows the projectile's heading projected into the view plane.
    A shot fired straight at or away from the camera has no screen-space heading
    at all — falling back to a fixed axis keeps it a visible streak instead of
    collapsing to a dot.
    """
    v = normalize3((vel[0], vel[1], vel[2])) if any(vel) else (0.0, 0.0, 0.0)
    dr = v[0] * right[0] + v[1] * right[1] + v[2] * right[2]
    du = v[0] * up[0] + v[1] * up[1] + v[2] * up[2]
    proj = math.hypot(dr, du)
    if proj < 0.15:
        ux, uy = 0.0, 1.0
    else:
        ux, uy = dr / proj, du / proj
    px_, py_ = -uy, ux
    hl, hw = length / 2.0, width / 2.0
    return ((ux * hl + px_ * hw, uy * hl + py_ * hw),
            (ux * hl - px_ * hw, uy * hl - py_ * hw),
            (-ux * hl - px_ * hw, -uy * hl - py_ * hw),
            (-ux * hl + px_ * hw, -uy * hl + py_ * hw))


def shield_color(s: float) -> tuple[float, float, float]:
    """Bubble colour for a shield-strength fraction.

    Blue at full strength, shifting through yellow and orange to red as the
    field weakens, so a glance at the 3D view says how much shield is left
    without reading the side panel. The bubble vanishes entirely at zero (see
    the `frac <= 0.001` guard in `_draw_shields`), so the ramp's last readable
    state is the red warning.
    """
    stops = ((0.12, (1.00, 0.18, 0.12)),     # red    — about to fail
             (0.30, (1.00, 0.48, 0.06)),     # orange
             (0.62, (1.00, 0.86, 0.06)),     # yellow — long, saturated band so
                                             # "damaged but holding" is its own
                                             # readable state, not a brief
                                             # transition
             (0.85, (1.00, 0.97, 0.90)),     # warm white — see below
             (1.00, (0.30, 0.55, 1.00)))     # blue   — nominal
    # The warm-white stop is not decoration. A straight yellow->blue blend
    # passes through (0.65, 0.69, 0.58), where green outweighs both red and
    # blue — the bubble turns olive at ~75% shields, exactly when it should
    # still read as healthy, and olive is nowhere on the requested ramp.
    # Routing through a white with R >= G keeps red the dominant channel on
    # the yellow half and blue the dominant one on the blue half, so green
    # never leads at any strength.
    if s <= stops[0][0]:
        return stops[0][1]
    for (s0, c0), (s1, c1) in zip(stops, stops[1:]):
        if s <= s1:
            k = (s - s0) / max(1e-6, s1 - s0)
            return (c0[0] + (c1[0] - c0[0]) * k,
                    c0[1] + (c1[1] - c0[1]) * k,
                    c0[2] + (c1[2] - c0[2]) * k)
    return stops[-1][1]


# --------------------------------------------------------------------------- stars
def make_starfield(count: int = 1400, bounds: float = 30000.0, seed: int = 7):
    rng = random.Random(seed)
    stars = []
    for _ in range(count):
        x = rng.uniform(-bounds, bounds)
        y = rng.uniform(-bounds * 0.4, bounds * 0.4)
        z = rng.uniform(-bounds, bounds)
        s = rng.uniform(0.6, 2.6)
        c = rng.uniform(0.5, 1.0)
        stars.append((x, y, z, s, c))
    return stars


class Renderer:
    def __init__(self, state, camera):
        # Establish cleanup ownership before any fallible initialization. A
        # failed constructor never reaches the application's candidate variable.
        self.materials = None
        self.fog = None
        self.ship_lists = {}
        self._star_list = self._unit_sphere_tex = None
        self._planet_tex_cache = {}
        self._hull_tex = self._space_tex = self._star_tex = self._nebula_tex = None
        from render.asset_selection import attach_renderer
        self._model_selection_owner = attach_renderer()
        try:
            self._initialize(state, camera)
        except BaseException:
            try:
                self.close()
            except BaseException:
                # Rollback must not replace the original construction error.
                pass
            raise

    def _initialize(self, state, camera):
        self.state = state
        self.local_player = 0
        # Ownership marker verbosity: 'all' | 'hostiles' | 'off'. Read-only
        # view state (never serialized, never in the sim).
        self.marker_mode = "all"
        self.fog = FogMask()
        self.camera = camera
        self.ds = DataStore.get()
        # Keep the helper reachable even if its initialization raises after
        # allocating programs but before its constructor would return.
        self.materials = FleetMaterials.__new__(FleetMaterials)
        self.materials.__init__()
        self.starfield = make_starfield()
        self.ship_lists: dict = {}       # (shape, scale, colorkey) -> display list id
        self._star_list = None
        self.time = 0.0
        self.camera.bind_scene(state, lambda: self.local_player,
                               lambda: math.radians(self.time * 3.))
        # debug isolation: STAR_ARMADA_SKIP=nebulas,star,planets,ships,... skips passes
        self.skip = {s for s in os.environ.get("STAR_ARMADA_SKIP", "").split(",") if s}
        self._planet_tex_cache: dict = {}   # data_id -> GL texture id
        self._hull_tex: int | None = None   # grayscale panel map (modulated)
        self._space_tex = None
        self._star_tex = None
        self._nebula_tex = None
        # shield bubbles: last seen quadrant values (to detect a hit) and the
        # per-quadrant flash timers that decay after one
        self._prev_shields: dict = {}
        self._shield_flash: dict = {}
        # planet-wide surface shield field: same drop-detection, keyed by planet
        self._planet_shield_prev: dict = {}
        self._planet_shield_flash: dict = {}
        # unit sphere with UVs (unit radius, scaled at draw time)
        self._unit_sphere_tex = self._build_textured_sphere_list()
        # per-frame render cache: keyed by state tick + camera geometry + view
        # inputs so repeated subpasses do not recompute view-dependent values.
        self._frame_key = None
        self._frame_cache = {}
        self._reset_frame_cache()
        # set by diag/probe scripts: freeze the animation clock so consecutive
        # frames are otherwise identical (baseline-subtraction diffs)
        self.diff_render = False

    def _reset_frame_cache(self):
        """Invalidate cached view data so the next draw rebuilds it."""
        self._frame_key = None
        self._frame_cache.clear()

    def _ensure_frame_cache(self, selection: set) -> dict:
        """Return a frame cache valid for the current state/camera/selection.

        Cached values are render-only and never enter saves/checksums.  The key
        includes state.tick so newly spawned/killed units are picked up, the
        camera geometry key so any view change rebuilds the cache, and the
        selection/marker inputs so HUD feedback stays current.
        """
        cam = self.camera
        key = (
            id(self.state),
            self.state.tick,
            cam._geometry_key(cam._requested_eye()),
            frozenset(selection),
            self.local_player,
            self.marker_mode,
            frozenset(self.skip),
            self.time if getattr(self, "diff_render", False) else None,
        )
        if self._frame_key == key:
            return self._frame_cache
        cache = {}
        eye = cam.eye_position()
        right, up, fwd = cam.basis()
        cache["eye"] = eye
        cache["basis"] = (right, up, fwd)
        cache["toward_eye"] = (-fwd[0], -fwd[1], -fwd[2])
        cache["px_scale"] = cam.height / (2.0 * math.tan(math.radians(cam.fov / 2.0)))
        # reuse owner colors/relations for markers/rings
        cache["owner_color"] = {}
        cache["relation"] = {}
        for owner_id in self.state.players:
            cache["owner_color"][owner_id] = self._owner_color(owner_id)
            cache["relation"][owner_id] = self._relation(owner_id)
        # one visibility-filtered list for all world passes
        visible = []
        mode = mk.marker_mode(getattr(self, "marker_mode", "all"))
        for e in self.state.entities.values():
            if not e.alive or e.is_planet:
                continue
            if not self.state.can_see(self.local_player, e.id):
                continue
            if e.jump_travelling:
                # In hyperspace: no hull, no glow, no marker on the strategic
                # view for anyone — including the owner (issue #92). The HUD
                # minimap still tracks the moving contact from sim position.
                continue
            entry = self._entity_view_data(e, eye, right, up, fwd, cache["px_scale"])
            entry["shows_marker"] = mode == "off" or mk.shows_marker(
                cache["relation"].get(e.owner, "neutral"), mode)
            cache[e.id] = entry
            visible.append((e, entry))
        cache["visible"] = visible
        self._frame_key = key
        self._frame_cache = cache
        return cache

    def _entity_view_data(self, e, eye, right, up, fwd, px_scale):
        """Precompute position, sizes and screen metrics for one visible entity."""
        pos = (e.pos.x, e.pos.y, e.pos.z)
        dx = pos[0] - eye[0]
        dy = pos[1] - eye[1]
        dz = pos[2] - eye[2]
        depth = dx * fwd[0] + dy * fwd[1] + dz * fwd[2]
        in_front = depth > 0.0
        if in_front:
            camera_depth = dx * fwd[0] + dy * fwd[1] + dz * fwd[2]
            ppw_camera = px_scale / camera_depth if camera_depth > 1e-6 else 0.0
        else:
            ppw_camera = 0.0
        if e.is_station:
            size = None
            visual_radius = self._station_visual_radius(e)
            shield_radius = self._shield_radius(e)
        else:
            size = self._ship_size(e)
            visual_radius = size.radius
            shield_radius = visual_radius * 1.08
        # marker/shield apparent size at camera depth
        if in_front and ppw_camera > 0.0:
            apparent = visual_radius * 2.0 * ppw_camera
        else:
            apparent = 0.0
        return {
            "pos": pos,
            "depth": depth,
            "in_front": in_front,
            "ppw_camera": ppw_camera,
            "size": size,
            "visual_radius": visual_radius,
            "shield_radius": shield_radius,
            "apparent": apparent,
        }

    def _in_front_cached(self, cache: dict, pos, radius: float = 0.0) -> bool:
        """In-front test reusing the cached eye and forward vector."""
        eye, (right, up, fwd) = cache["eye"], cache["basis"]
        depth = (pos[0] - eye[0]) * fwd[0] + (pos[1] - eye[1]) * fwd[1] + (pos[2] - eye[2]) * fwd[2]
        return depth > radius

    def _px_per_world_cached(self, cache: dict, pos, *, camera_depth=False) -> float:
        if not self._in_front_cached(cache, pos, 0.0):
            return 0.0
        eye, (right, up, fwd) = cache["eye"], cache["basis"]
        dx = pos[0] - eye[0]
        dy = pos[1] - eye[1]
        dz = pos[2] - eye[2]
        if camera_depth:
            dist = dx * fwd[0] + dy * fwd[1] + dz * fwd[2]
        else:
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist <= 1e-6:
            return 0.0
        return cache["px_scale"] / dist

    def close(self):
        """Release owned GL objects once, while their context is still current.

        Attempt every independent release even if one cleanup raises. Constructor
        rollback preserves its original error; explicit close reports the first
        cleanup error after releasing the remaining resources.
        """
        releases = []
        materials = getattr(self, "materials", None)
        if materials is not None:
            releases.append(materials.close)
        fog = getattr(self, "fog", None)
        if fog is not None:
            releases.append(fog.close)
        lists = set(self.ship_lists.values())
        lists.update((self._star_list, self._unit_sphere_tex))
        self.ship_lists.clear()
        self._star_list = self._unit_sphere_tex = None
        for list_id in lists:
            if list_id:
                releases.append(lambda list_id=list_id: _gl.glDeleteLists(list_id, 1))
        textures = set(self._planet_tex_cache.values())
        textures.update((self._hull_tex, self._space_tex,
                         self._star_tex, self._nebula_tex))
        textures.discard(None)
        textures.discard(0)
        self._planet_tex_cache.clear()
        self._hull_tex = self._space_tex = self._star_tex = self._nebula_tex = None
        if textures:
            releases.append(lambda: _gl.glDeleteTextures(sorted(textures)))
        error = None
        for release in releases:
            try:
                release()
            except BaseException as exc:
                if error is None:
                    error = exc
        from render.asset_selection import release_renderer
        release_renderer(getattr(self, '_model_selection_owner', None))
        self._model_selection_owner = None
        if error is not None:
            raise error

    # ------------------------------------------------------------------ per frame
    def draw(self, dt: float, selection: set, hover_id: int | None = None) -> None:
        from game.systems.visibility import presentation_sensor_batch
        # One synchronous, read-only draw only. Never borrow the persistent
        # frame cache's lifetime: callers can edit entities/catalogues same tick.
        had_scope = hasattr(self, '_draw_view')
        previous = getattr(self, '_draw_view', None)
        self._draw_view = {}
        try:
            with presentation_sensor_batch(self.state):
                self._draw_read_only(dt, selection, hover_id)
        finally:
            if had_scope:
                self._draw_view = previous
            else:
                del self._draw_view

    def _draw_view_geometry(self):
        """Lazy exact safe eye/basis; standalone helper calls remain live."""
        scope = getattr(self, '_draw_view', None)
        if scope is not None and 'geometry' in scope:
            return scope['geometry']
        geometry = (self.camera.eye_position(), self.camera.basis())
        if scope is not None:
            scope['geometry'] = geometry
        return geometry

    def _draw_read_only(self, dt: float, selection: set,
                        hover_id: int | None = None) -> None:
        # Probe/test hook: freeze the animation clock so consecutive frames are
        # otherwise identical. `self.time` drives the planet spin, station
        # rotation and starfield drift, so with it advancing every pixel of the
        # background changes between two "identical" frames — which defeats
        # baseline-subtraction diffs used to measure a single effect's
        # contribution (an effect mask then covers the whole screen). Normal
        # gameplay never sets this.
        if not getattr(self, "diff_render", False):
            self.time += dt
        st = self.state
        cache = self._ensure_frame_cache(selection)
        glMatrixMode(GL_MODELVIEW)
        self.camera.apply()
        # apply refreshes collision keep-outs even with the same camera key.
        # Preserve legacy pre-apply frame metrics, but never reuse that eye or
        # its readable sizes after a refresh moved the actual safe eye.
        scope = getattr(self, '_draw_view', None)
        if (scope is not None and 'geometry' in scope
                and scope['geometry'][0] != self.camera.eye_position()):
            scope.clear()
        # frame start: clear color+depth. Without this, frames accumulate
        # (smeared wedges, z-fight dither, HUD depth blocking the 3D scene).
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._setup_lighting()
        if "starfield" not in self.skip:
            self._draw_starfield()
        if "nebulas" not in self.skip:
            self._draw_nebulas()
        if "star" not in self.skip:
            self._draw_star()
        if "jumppoints" not in self.skip:
            self._draw_jump_points()
        if "planets" not in self.skip:
            self._draw_planets()
        # Chart remembered terrain, not friendly units: own/allied contacts are
        # always known even when their sensor subsystem is disabled. Live
        # combat passes below independently enforce exact current detection.
        self.fog.draw(st, self.local_player)
        if "planet_shields" not in self.skip:
            # After the fog quad: the shell is translucent hardware, not terrain
            # the fog chart owns, and drawing it first let the ground overlay
            # composite over the lit limb.
            self._draw_planet_shields(dt)
        if "effects" not in self.skip:
            self._draw_effects()
        if "projectiles" not in self.skip:
            self._draw_projectiles()
        if "ships" not in self.skip:
            self._draw_ships(selection, cache)
        if "shields" not in self.skip:
            # after the hull pass so the bubble composites over the ship it
            # encloses; before the selection rings so those stay on top
            self._draw_shields([e for e, _ in cache["visible"]], dt, cache)
        if "effects" not in self.skip:
            self._draw_hits()
        if "sites" not in self.skip:
            self._draw_construction_sites()
            self._draw_placement_preview()
        if "surface_slots" not in self.skip:
            self._draw_surface_slots(selection)
        if "markers" not in self.skip:
            # After the bubbles: a hostile diamond must never be swallowed by an
            # allied bubble drawn on top of it. Before the selection rings so
            # the local player's own selection stays the topmost cue.
            self._draw_ownership_markers(cache)
        if "rings" not in self.skip:
            self._draw_selection_rings(selection, cache)
            self._draw_collection_points(selection)
        glFlush()

    def _draw_collection_points(self, selection):
        """View-only destination links for selected, owned production stations."""
        from game.systems.collection_points import collection_capable
        stations = [self.state.entity(eid) for eid in sorted(selection)]
        stations = [e for e in stations if collection_capable(e)
                    and e.owner == self.local_player and e.collection_point is not None]
        if not stations:
            return
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glLineWidth(2.0)
        glColor4f(0.35, 0.95, 0.8, 0.95)
        glBegin(GL_LINES)
        for station in stations:
            point = station.collection_point
            glVertex3f(*station.pos.to_dict(True))
            glVertex3f(*point.to_dict(True))
            # World-space diamond + cross make the endpoint legible from above.
            radius = max(45.0, 9.0 / max(0.001, self._px_per_world(point.to_dict(True))))
            corners = [(point.x + radius, point.y, point.z),
                       (point.x, point.y, point.z + radius),
                       (point.x - radius, point.y, point.z),
                       (point.x, point.y, point.z - radius)]
            for index, corner in enumerate(corners):
                glVertex3f(*corner)
                glVertex3f(*corners[(index + 1) % 4])
            glVertex3f(point.x - radius * 0.5, point.y, point.z)
            glVertex3f(point.x + radius * 0.5, point.y, point.z)
            glVertex3f(point.x, point.y, point.z - radius * 0.5)
            glVertex3f(point.x, point.y, point.z + radius * 0.5)
        glEnd()
        glLineWidth(1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def _draw_surface_slots(self, selection):
        """Depth-tested surface pads: empty ticks, occupied rings, paid scaffolds."""
        from render.planet_building_geometry import visible_surface_slots
        slots = visible_surface_slots(self.state, self.local_player, selection)
        if not slots:
            return
        _gl.glPushAttrib(_gl.GL_ENABLE_BIT | _gl.GL_CURRENT_BIT | _gl.GL_LINE_BIT |
                         _gl.GL_DEPTH_BUFFER_BIT | _gl.GL_COLOR_BUFFER_BIT | _gl.GL_POLYGON_BIT)
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_CULL_FACE)
        for pad in slots:
            color = self._owner_color(self.local_player)
            if pad['status'] == 'building':
                color = (1., .72, .22)
            elif pad['status'] == 'empty':
                color = (.42, .75, .86)
            glColor3f(*color)
            glLineWidth(2.)
            glPushMatrix()
            glTranslatef(*pad['origin'])
            basis=pad['basis']
            _gl.glMultMatrixf([*basis[0],0.,*basis[1],0.,*basis[2],0.,0.,0.,0.,1.])
            r=pad['radius']
            glBegin(GL_LINE_LOOP)
            for i in range(32):
                a=i/32*2*math.pi
                glVertex3f(math.sin(a)*r,2.,math.cos(a)*r)
            glEnd()
            if pad['status'] == 'empty':
                glBegin(_gl.GL_LINES)
                for x,z in ((1,0),(-1,0),(0,1),(0,-1)):
                    glVertex3f(x*r*.65,2.,z*r*.65)
                    glVertex3f(x*r*1.2,2.,z*r*1.2)
                glEnd()
            elif pad['status'] == 'building':
                sd=self.ds.stations.get(pad['kind'])
                if sd:
                    glPushMatrix()
                    scale=sd.radius/50.
                    glScalef(scale,scale,scale)
                    _gl.glPolygonMode(_gl.GL_FRONT_AND_BACK,_gl.GL_LINE)
                    glCallList(self._station_detail_list(pad['kind'],'base',
                        self.state.players[self.local_player].faction))
                    _gl.glPolygonMode(_gl.GL_FRONT_AND_BACK,_gl.GL_FILL)
                    glPopMatrix()
                glColor3f(.4,1.,.5)
                glLineWidth(3.)
                glBegin(GL_LINE_STRIP)
                for i in range(int(40*pad['progress'])+1):
                    a=i/40*2*math.pi
                    glVertex3f(math.sin(a)*r*1.25,3.,math.cos(a)*r*1.25)
                glEnd()
            glPopMatrix()
        glPopAttrib()

    def _draw_surface_selection(self, e):
        from render.planet_building_geometry import station_frame
        origin,basis,scale=station_frame(self.state,e)
        glPushMatrix()
        glTranslatef(*origin)
        _gl.glMultMatrixf([*basis[0],0.,*basis[1],0.,*basis[2],0.,0.,0.,0.,1.])
        glEnable(GL_DEPTH_TEST)
        glColor3f(.4,1.,.5)
        glLineWidth(3.)
        glBegin(GL_LINE_LOOP)
        for x,z in ((-38,-38),(38,-38),(38,38),(-38,38)):
            glVertex3f(x*scale,2.,z*scale)
        glEnd()
        glDisable(GL_DEPTH_TEST)
        glPopMatrix()

    def _draw_placement_preview(self):
        """Knowledge-limited input feedback, never an authoritative site query."""
        placement = getattr(self, "placement", None)
        ghost = placement.get("ghost") if placement else None
        if not ghost:
            return
        builder = self.state.entities.get(placement.get("builder_id"))
        if (builder is None or not builder.alive or not builder.is_construction
                or builder.owner != self.local_player):
            return
        data_id = placement.get("station_kind")
        data = self.ds.stations.get(data_id)
        pos = ghost.get("world")
        if data is None or pos is None or not self._in_front(pos, data.radius * 3.):
            return
        from render.faction_visuals import owner_faction
        faction = owner_faction(self.state, builder.owner)
        color = (.30, .90, .55) if ghost.get("valid") else (1., .25, .20)
        self._draw_station_outline(data_id, faction, pos, data.radius, color)

    def _draw_station_outline(self, data_id, faction, pos, radius, color):
        """Exact all-role hardware wireframe with fully scoped preview GL state."""
        import OpenGL.GL as GL
        # Direct triangle emission: list construction must never nest in a list.
        mesh = station_mesh(data_id, faction)
        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_LIGHTING_BIT | GL.GL_CURRENT_BIT |
                        GL.GL_DEPTH_BUFFER_BIT | GL.GL_COLOR_BUFFER_BIT |
                        GL.GL_POLYGON_BIT | GL.GL_LINE_BIT | GL.GL_TEXTURE_BIT)
        glPushMatrix()
        try:
            GL.glDisable(GL.GL_LIGHTING)
            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glDisable(GL.GL_CULL_FACE)
            GL.glEnable(GL.GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            GL.glDepthMask(False)
            GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
            glLineWidth(1.)
            glColor4f(*color, .55)
            glTranslatef(*pos)
            glRotatef(self.time * 3., 0, 1, 0)
            glScalef(radius / 50., radius / 50., radius / 50.)
            for triangles in mesh.values():
                self._emit_detail_mesh(triangles)
        finally:
            glPopMatrix()
            GL.glPopAttrib()

    def _draw_authored_construction_scaffold(self, pos, radius, fraction, color):
        """Draw only a selected scaffold; otherwise retain the exact legacy lattice.

        Nominal source height and radius are 50. Progress changes only visual height,
        never collision, build costs, timers, or any serialized state.
        """
        from render.asset_selection import mesh_for
        mesh = mesh_for('shared:construction_scaffold')
        if mesh is None:
            return False
        from OpenGL import GL
        groups = (GL.GL_ENABLE_BIT | GL.GL_CURRENT_BIT | GL.GL_LIGHTING_BIT |
                  GL.GL_DEPTH_BUFFER_BIT | GL.GL_POLYGON_BIT | GL.GL_TEXTURE_BIT)
        GL.glPushAttrib(groups)
        glPushMatrix()
        try:
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_LIGHTING)
            GL.glDisable(GL.GL_TEXTURE_2D)
            GL.glDepthMask(True)
            glTranslatef(pos[0], 0., pos[2])
            scale = radius / 50.
            height = .4 + .6 * max(0., min(1., fraction))
            glScalef(scale, scale * height, scale)
            self._material_metal(8.0, (0.50, 0.55, 0.62))
            with self.materials.use('hull', materialPass=0.0, authoredSurface=1.0):
                for role, material_pass, tint in (
                        ('base', 0.0, color),
                        ('dark', 1.0, (0.20, 0.24, 0.30)),
                        ('trim', 2.0, (0.68, 0.76, 0.84))):
                    self.materials.hull_pass(material_pass, True)
                    if not self.materials.available and role == 'base':
                        tint = tuple(.42 + .18*c for c in color)
                    glColor3f(*tint)
                    self._emit_detail_mesh(mesh[role])
            glDisable(GL_TEXTURE_2D)
            glColor3f(*color)
            self._emit_detail_mesh(mesh['accent'])
            self._material_matte()
            glDisable(GL_LIGHTING)
            for role, tint in (('lit', (1., .80, .52)), ('cool', (.38, .82, 1.))):
                glColor3f(*tint)
                self._emit_detail_mesh(mesh[role])
        finally:
            glPopMatrix()
            GL.glPopAttrib()
        return True

    def _draw_construction_sites(self):
        """Wireframe scaffold + progress ring at each queued station site.

        The station entity only exists once construction completes; this makes
        the pending build visible (and selectable via the minimap/panel).
        """
        st = self.state
        for e in st.entities.values():
            if (not e.alive or not e.is_construction or e.owner != self.local_player):
                continue
            item = e.build_queue[0] if e.build_queue else None
            if item is None or item.get("kind") != "station":
                continue
            pos = item.get("pos")
            if not pos:
                continue
            pos = (pos["x"] if isinstance(pos, dict) else pos[0],
                   pos["y"] if isinstance(pos, dict) else pos[1],
                   pos["z"] if isinstance(pos, dict) else pos[2])
            sd = self.ds.stations.get(item.get("item", ""))
            if sd is None:
                continue
            if not self._in_front(pos, sd.radius * 2.5):
                continue
            r = sd.radius
            frac = 1.0 - max(0.0, item.get("time_left", 0)) / \
                max(0.1, item.get("total", 1))
            color = self._owner_color(e.owner)
            from render.faction_visuals import owner_faction
            faction = owner_faction(st, e.owner)
            from render.faction_visuals import normalize_station_key
            faction, station_id = normalize_station_key(item['item'], faction)
            if faction != 'imperial' or is_authored(f'{faction}:{station_id}'):
                self._draw_station_outline(station_id, faction, pos, r, color)
            import OpenGL.GL as GL
            GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_LIGHTING_BIT |
                            GL.GL_CURRENT_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDisable(GL.GL_LIGHTING)
            glDisable(GL_DEPTH_TEST)
            glLineWidth(2.0)
            if not self._draw_authored_construction_scaffold(pos, r, frac, color):
                # scaffold ring on the ground plane
                glColor4f(color[0], color[1], color[2], 0.85)
                glBegin(GL_LINE_LOOP)
                for i in range(24):
                    a = i / 24 * 2 * math.pi
                    glVertex3f(pos[0] + math.sin(a) * r, 0,
                               pos[2] + math.cos(a) * r)
                glEnd()
                # lattice: 8 vertical posts + height ring (grows with progress)
                glBegin(GL_LINES)
                for i in range(8):
                    a = i / 8 * 2 * math.pi
                    sa, ca = math.sin(a) * r * 0.85, math.cos(a) * r * 0.85
                    glVertex3f(pos[0] + sa, 0, pos[2] + ca)
                    glVertex3f(pos[0] + sa, r * (0.4 + 0.6 * frac),
                               pos[2] + ca)
                glEnd()
                h = r * (0.4 + 0.6 * frac)
                glBegin(GL_LINE_LOOP)
                for i in range(24):
                    a = i / 24 * 2 * math.pi
                    glVertex3f(pos[0] + math.sin(a) * r * 0.85, h,
                               pos[2] + math.cos(a) * r * 0.85)
                glEnd()
            # green progress arc
            glColor3f(0.4, 1.0, 0.5)
            glLineWidth(3.0)
            glBegin(GL_LINE_STRIP)
            for i in range(int(40 * min(1.0, frac)) + 1):
                a = i / 40 * 2 * math.pi
                glVertex3f(pos[0] + math.sin(a) * r * 1.25, r * 0.5,
                           pos[2] + math.cos(a) * r * 1.25)
            glEnd()
            glPopAttrib()
            glEnable(GL_DEPTH_TEST)

    # ---------------------------------------------------------- view culling
    def _setup_lighting(self):
        """Fixed-function lighting: the star is the key light; soft ambient.

        GL_COLOR_MATERIAL keeps faction colors; normals in display lists give
        the shading. Effects/projectiles pass disables lighting themselves.

        A specular material is set once here so the metal pass in
        ``_draw_ship``/``_draw_station`` has something to reflect: without it
        GL_MATERIAL defaults give no highlight at all, and every hull reads as
        flat plastic regardless of how good its geometry is.
        """
        import OpenGL.GL as GL
        star = self.state.map_info.star
        sp = star.get("pos", [0, -3000, 0]) if star else [0, -3000, 0]
        GL.glEnable(GL.GL_LIGHT0)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, (sp[0], max(sp[1], 2000.0), sp[2], 1.0))
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, (0.85, 0.8, 0.72, 1.0))
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_SPECULAR, (1.0, 0.97, 0.90, 1.0))
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, (0.0, 0.0, 0.0, 1.0))
        GL.glLightModelfv(GL.GL_LIGHT_MODEL_AMBIENT, (0.34, 0.37, 0.44, 1.0))
        # per-vertex evaluation of the highlight: the cheap "infinite viewer"
        # default collapses to a single value across a large hull, visible only
        # on a few coincidental normals.
        GL.glLightModeli(GL.GL_LIGHT_MODEL_LOCAL_VIEWER, 1)
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glShadeModel(GL.GL_SMOOTH)

    def _in_front(self, pos, radius: float) -> bool:
        """False when the object's center is behind/at the eye plane.

        Triangle fans crossing the near plane project with mirrored winding
        and smear giant shapes across the screen — this guard prevents that.
        """
        eye, (_, _, fwd) = self._draw_view_geometry()
        depth = ((pos[0] if hasattr(pos, "__len__") else pos.x) - eye[0]) * fwd[0] \
            + ((pos[1] if hasattr(pos, "__len__") else pos.y) - eye[1]) * fwd[1] \
            + ((pos[2] if hasattr(pos, "__len__") else pos.z) - eye[2]) * fwd[2]
        return depth > radius

    # ------------------------------------------------------------------ background
    def _draw_starfield(self):
        # An eye-centered sphere gives the sky angular parallax on orbit, never
        # translation on pan. Depth writes stay off; it cannot hide world objects.
        _gl.glPushAttrib(_gl.GL_ENABLE_BIT | _gl.GL_TEXTURE_BIT |
                         _gl.GL_DEPTH_BUFFER_BIT | _gl.GL_CURRENT_BIT |
                         _gl.GL_LIGHTING_BIT)
        if self._space_tex is None:
            self._space_tex = tex.surface_to_texture(tex.deep_space_texture())
        glDisable(GL_LIGHTING)
        glDisable(GL_CULL_FACE)
        glDisable(GL_DEPTH_TEST)
        glDepthMask(False)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self._space_tex)
        glColor3f(1, 1, 1)
        glPushMatrix()
        glTranslatef(*self.camera.eye_position())
        glScalef(40000, 40000, 40000)
        glCallList(self._unit_sphere_tex)
        glPopMatrix()
        glDisable(GL_TEXTURE_2D)
        if self._star_list is None:
            lst = _gl.glGenLists(1)
            glNewList(lst, GL_COMPILE)
            glBegin(GL_POINTS)
            for (x, y, z, s, c) in self.starfield:
                glColor3f(c * 0.9, c * 0.9, c)
                glVertex3f(x, y, z)
            glEnd()
            glEndList()
            self._star_list = lst
        glPointSize = _gl.glPointSize
        glPointSize(1.6)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(False)
        glPushMatrix()
        # stars follow camera target so the field feels endless
        glTranslatef(self.camera.target[0], 0, self.camera.target[2])
        glCallList(self._star_list)
        glPopMatrix()
        glDepthMask(True)
        glPopAttrib()

    def _draw_nebulas(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        for n in self.state.map_info.nebulas:
            if not self.state.is_position_explored(self.local_player, position(n["pos"])):
                continue
            if not self._in_front(n["pos"], n["radius"]):
                continue
            color = n.get("color", [0.4, 0.2, 0.55])
            if self._nebula_tex is None:
                self._nebula_tex = tex.surface_to_texture(
                    tex.nebula_texture(color=tuple(color)))
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            self._draw_textured_billboard(n["pos"], n["radius"],
                                          self._nebula_tex, 0.30)
            self._draw_textured_billboard(n["pos"], n["radius"] * 0.55,
                                          self._nebula_tex, 0.35)
        glDepthMask(True)
        glDisable(GL_BLEND)

    def _draw_star(self):
        star = self.state.map_info.star
        if not star:
            return
        if not self._in_front(star["pos"], star.get("size", 2000) * 2.2):
            return
        glEnable(GL_BLEND)
        glDepthMask(False)
        col = star.get("color", [1, 0.9, 0.6])
        size = star.get("size", 2000)
        # textured star billboard (granulated surface)
        if self._star_tex is None:
            self._star_tex = tex.surface_to_texture(tex.star_texture())
        self._draw_textured_billboard(star["pos"], size, self._star_tex, 1.0)
        # soft additive halo
        self._draw_glow(star["pos"], size * 2.0, col, alpha=0.30, additive=True)
        glDepthMask(True)
        glDisable(GL_BLEND)

    def _draw_textured_billboard(self, pos, radius, tex_id, alpha):
        """Camera-facing quad with a texture (star/nebula sprites).

        Drawn unlit with identity color material so the texture's own
        luminance shows (lit billboards facing away from the key light go
        near-black).
        """
        import OpenGL.GL as GL
        right, up, _ = self.camera.basis()
        GL.glPushAttrib(GL.GL_LIGHTING_BIT | GL.GL_CURRENT_BIT |
                        GL.GL_ENABLE_BIT | GL.GL_COLOR_BUFFER_BIT)
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glColor4f(1, 1, 1, alpha)
        rx, ry, rz = right
        ux, uy, uz = up
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex3f((-rx - ux) * radius, (-ry - uy) * radius, (-rz - uz) * radius)
        glTexCoord2f(1, 1); glVertex3f((rx - ux) * radius, (ry - uy) * radius, (rz - uz) * radius)
        glTexCoord2f(1, 0); glVertex3f((rx + ux) * radius, (ry + uy) * radius, (rz + uz) * radius)
        glTexCoord2f(0, 0); glVertex3f((-rx + ux) * radius, (-ry + uy) * radius, (-rz + uz) * radius)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        glPopMatrix()
        GL.glPopAttrib()

    def _draw_jump_points(self):
        for jp in self.state.map_info.jump_points:
            if not self.state.is_position_explored(self.local_player, position(jp["pos"])):
                continue
            pos = jp["pos"]
            glPushMatrix()
            glTranslatef(pos[0], pos[1], pos[2])
            glRotatef(self.time * 20.0, 0, 1, 0)
            glColor4f(0.4, 0.7, 1.0, 0.5)
            glLineWidth(2.0)
            glBegin(GL_LINE_LOOP)
            r = 220.0
            for i in range(24):
                a = i / 24 * 2 * math.pi
                glVertex3f(math.sin(a) * r, 0, math.cos(a) * r)
            glEnd()
            glBegin(GL_LINE_LOOP)
            for i in range(24):
                a = i / 24 * 2 * math.pi
                glVertex3f(math.sin(a) * r * 0.7, 40, math.cos(a) * r * 0.7)
            glEnd()
            glPopMatrix()

    def _draw_glow(self, pos, radius, color, alpha, additive=False):
        """True camera-facing billboard disc with radial falloff.

        Vertices are computed analytically from the camera basis (yaw/pitch
        conventions of TacticalCamera) so the disc always faces the viewer.
        Replaces the old ground-plane disc, which smeared into giant wedges
        when the camera viewed it near edge-on.
        """
        if radius <= 0:
            return
        cam = self.camera
        right, up, fwd = cam.basis()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE if additive else GL_ONE_MINUS_SRC_ALPHA)
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        segments = 32
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(color[0], color[1], color[2], alpha)      # hot center
        glVertex3f(0.0, 0.0, 0.0)
        for i in range(segments + 1):
            a = i / segments * 2 * math.pi
            ca, sa = math.cos(a), math.sin(a)
            glColor4f(color[0], color[1], color[2], 0.0)    # transparent rim
            glVertex3f((right[0] * ca + up[0] * sa) * radius,
                       (right[1] * ca + up[1] * sa) * radius,
                       (right[2] * ca + up[2] * sa) * radius)
        glEnd()
        glPopMatrix()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # ------------------------------------------------------------------ planets
    def _planet_texture_for(self, e):
        key = (e.data_id, e.name_override or e.data_id)
        if key not in self._planet_tex_cache:
            # Python hash() changes per process; worlds must not change on reload.
            seed = int.from_bytes(hashlib.blake2s(key[1].encode(), digest_size=4).digest(), 'little')
            surf = tex.planet_texture(e.data_id, size=512, seed=seed % 1000000)
            self._planet_tex_cache[key] = tex.surface_to_texture(surf)
        return self._planet_tex_cache[key]

    def _draw_planets(self):
        for e in known_entities(self.state, self.local_player):
            if not e.alive or not e.is_planet:
                continue
            kind = e.data_id
            if kind == "asteroid_field":
                self._draw_asteroid_field(e)
                continue
            glPushMatrix()
            glTranslatef(e.pos.x, e.pos.y, e.pos.z)
            glRotatef(self.time * 1.2, 0, 1, 0)      # slow axial spin
            glEnable(GL_DEPTH_TEST)
            # textured sphere (procedural equirect texture per planet type)
            texture = self._planet_texture_for(e)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, texture)
            glEnable(GL_CULL_FACE)
            glColor3f(1, 1, 1)
            glPushMatrix()
            glScalef(e.radius, e.radius, e.radius)
            air = 0.0 if kind == "barren" else 1.0
            with self.materials.use("planet", atmosphere=air, shell=0.0):
                glCallList(self._unit_sphere_tex)
            # Thin, depth-tested atmosphere: transparent center, soft lit limb.
            # Do not emit a second opaque planet on the fixed-function fallback.
            if air and self.materials.available:
                _gl.glPushAttrib(_gl.GL_ENABLE_BIT | _gl.GL_COLOR_BUFFER_BIT |
                                 _gl.GL_DEPTH_BUFFER_BIT)
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE)
                glDepthMask(False)
                glScalef(1.018, 1.018, 1.018)
                with self.materials.use("planet", atmosphere=air, shell=1.0):
                    glCallList(self._unit_sphere_tex)
                glPopAttrib()
            glPopMatrix()
            glDisable(GL_CULL_FACE)
            glDisable(GL_TEXTURE_2D)
            # owner ring
            if e.colonized_by is not None and e.colonized_by >= 0:
                p = self.state.players.get(e.colonized_by)
                if p:
                    glColor3f(*p.color)
                    glLineWidth(3.0)
                    glBegin(GL_LINE_LOOP)
                    r = e.radius + 120
                    for i in range(40):
                        a = i / 40 * 2 * math.pi
                        glVertex3f(math.sin(a) * r, 0, math.cos(a) * r)
                    glEnd()
            glPopMatrix()

    def _build_textured_sphere_list(self, lons=64, lats=40):
        """Unit-radius UV sphere display list (scaled per planet at draw)."""
        lst = _gl.glGenLists(1)
        # Own the reserved name before compilation or helper return can fail.
        self._unit_sphere_tex = lst
        try:
            glNewList(lst, GL_COMPILE)
            for i in range(lons):
                lon0 = 2 * math.pi * i / lons
                lon1 = 2 * math.pi * (i + 1) / lons
                for j in range(lats):
                    lat0 = math.pi * j / lats - math.pi / 2
                    lat1 = math.pi * (j + 1) / lats - math.pi / 2

                    def vert(lon, lat):
                        return (math.cos(lat) * math.sin(lon),
                                math.sin(lat),
                                math.cos(lat) * math.cos(lon))

                    a, b = vert(lon0, lat0), vert(lon1, lat0)
                    c, d = vert(lon1, lat1), vert(lon0, lat1)
                    u0, u1 = i / lons, (i + 1) / lons
                    v0, v1 = j / lats, (j + 1) / lats
                    for tri, uvs in (((a, b, c), ((u0, v0), (u1, v0), (u1, v1))),
                                     ((a, c, d), ((u0, v0), (u1, v1), (u0, v1)))):
                        ax_, ay_, az_ = (tri[1][0] - tri[0][0], tri[1][1] - tri[0][1],
                                         tri[1][2] - tri[0][2])
                        bx_, by_, bz_ = (tri[2][0] - tri[0][0], tri[2][1] - tri[0][1],
                                         tri[2][2] - tri[0][2])
                        nx = ay_ * bz_ - az_ * by_
                        ny = az_ * bx_ - ax_ * bz_
                        nz = ax_ * by_ - ay_ * bx_
                        centroid = (sum(v[k] for v in tri) / 3 for k in range(3))
                        cx_, cy_, cz_ = centroid
                        if nx * cx_ + ny * cy_ + nz * cz_ < 0:
                            tri = (tri[0], tri[2], tri[1])
                            uvs = (uvs[0], uvs[2], uvs[1])
                        glBegin(GL_TRIANGLES)
                        try:
                            for v, (u, w_) in zip(tri, uvs):
                                nn = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
                                glNormal3f(v[0] / nn, v[1] / nn, v[2] / nn)
                                glTexCoord2f(u, w_)
                                glVertex3f(*v)
                        except BaseException:
                            try:
                                glEnd()
                            except BaseException:
                                pass
                            raise
                        else:
                            glEnd()
            glEndList()
        except BaseException:
            try:
                if int(_gl.glGetIntegerv(_gl.GL_LIST_INDEX)) == lst:
                    _gl.glEndList()
            except BaseException:
                pass
            raise
        return lst

    def _draw_asteroid_field(self, e):
        """Irregular lit rock clusters: 3-5 lumpy sub-rocks per asteroid,
        facet-shaded with a warm gray-brown palette, slow tumble."""
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        spin = self.time * 0.15
        # The authored prop, when the row is selected, is resolved once for the field and drawn per
        # instance in place of the procedural facets. The placements come from their own pure
        # function, so a guard can prove the field is the same field with a different rock in it.
        prop = self._asteroid_prop_lists()
        rng = random.Random(int(e.pos.x) % 9973)
        for _ in range(40):
            # Placement first, then the rock: the two alternate, so the field's layout depends on
            # both streams in the order they have always been drawn in.
            x, y, z, s, angle = field_placement(e.radius, rng)
            glPushMatrix()
            glTranslatef(x, y, z)
            # slow tumble (deterministic per asteroid)
            glRotatef(spin * angle, 0.3, 0.7, 0.2)
            self._draw_rock(s, rng, prop)
            glPopMatrix()
        glPopMatrix()

    def _draw_rock(self, s: float, rng, prop=None):
        """One asteroid: the shared authored prop when the row is selected, else 3-5 overlapping
        lit sub-rocks with irregular vertex-jittered facets.

        Both paths take their parameters from `rock_params` *before* the branch, so the RNG is
        advanced identically either way: every later rock's angle, radius, height, size and tumble -
        and therefore the field's whole layout - is the same whichever path draws. That is what makes
        a before/after capture an isolated change of shape rather than a rearranged field.
        """
        base, subs = rock_params(s, rng)
        if prop is not None:
            glPushMatrix()
            # The prop is authored as a unit rock, where the procedural facets were generated *at*
            # scale s: the instance's own scale is applied here and nothing else about it changes.
            glScalef(s, s, s)
            for role, tint in ASTEROID_ROLE_TINTS:
                mesh = prop.get(role)
                if mesh is None:
                    continue
                glColor3f(*[min(1.0, c * tint) for c in base])
                glCallList(mesh)
            glPopMatrix()
            return
        m = len(subs)
        for k, (jx, jy, jz, ss, radii) in enumerate(subs):
            shade = 1.0 - 0.16 * k / max(1, m - 1)
            glColor3f(base[0] * shade, base[1] * shade, base[2] * shade)
            self._rock_facets(ss, jx, jy, jz, radii)

    def _asteroid_prop_lists(self):
        """The authored asteroid prop's per-role display lists, or None when none is selected.

        Follows the station path exactly: one compiled list per role, cached under the resolver's
        own content key so a revision change cannot leave a stale list behind. Returning None is the
        explicit legacy fallback, and it is what an unselected row gets.
        """
        binding = 'environment:asteroid_field'
        # Imported here, not at module scope: every other seam in this codebase reads it at call time,
        # which is what lets the review harnesses serve a candidate and what makes the reference follow
        # a reconfiguration.
        from render.asset_selection import mesh_for
        authored = mesh_for(binding)
        if authored is None:
            return None
        lists = {}
        for role in ('base', 'dark', 'trim', 'accent', 'lit', 'cool'):
            mesh = authored.get(role)
            if not mesh:
                continue
            key = gpu_cache_key(binding, role, 'asteroid_prop:' + role)
            if key not in self.ship_lists:
                lst = _gl.glGenLists(1)
                glNewList(lst, GL_COMPILE)
                self._emit_detail_mesh(mesh)
                glEndList()
                self.ship_lists[key] = lst
            lists[role] = self.ship_lists[key]
        return lists or None

    def _rock_facets(self, s: float, jx: float, jy: float, jz: float, radii):
        """Faceted lump: an icosphere-ish hull via 8 corner + 6 face bulge
        points, jittered, emitted as GL_TRIANGLES with per-face normals."""
        # 8 corners of a cube, jittered radially - the jitter itself comes from `rock_params`
        c = []
        for k, (sx, sy, sz) in enumerate((a, b, c_) for a in (-1, 1) for b in (-1, 1)
                                         for c_ in (-1, 1)):
            rr = s * 0.5 * radii[k]
            c.append((sx * rr * 0.72 + jx, sy * rr * 0.6 + jy,
                      sz * rr * 0.72 + jz))
        # 6 face-bulge points for a lumpy silhouette
        f = []
        for k, (dx, dy, dz) in enumerate(((0, 0, 1), (0, 0, -1), (0, 1, 0),
                                          (0, -1, 0), (1, 0, 0), (-1, 0, 0))):
            rr = s * 0.5 * radii[8 + k]
            f.append((dx * rr + jx, dy * rr * 0.8 + jy, dz * rr + jz))
        # explicit hull: each face is a quad of 4 jittered corners fanned
        # through its face-bulge point -> 4 lit triangles per face
        quads = [
            # +z face (bulge f[0]): corners 1,3,7,5
            ((c[1], c[3], c[7], c[5]), f[0]),
            # -z face (bulge f[1]): corners 2,6,4,0
            ((c[2], c[6], c[4], c[0]), f[1]),
            # +y face (bulge f[2]): corners 2,3,7,6
            ((c[2], c[3], c[7], c[6]), f[2]),
            # -y face (bulge f[3]): corners 0,4,5,1
            ((c[0], c[4], c[5], c[1]), f[3]),
            # +x face (bulge f[4]): corners 3,1,5,7
            ((c[3], c[1], c[5], c[7]), f[4]),
            # -x face (bulge f[5]): corners 0,2,6,4
            ((c[0], c[2], c[6], c[4]), f[5]),
        ]
        glBegin(GL_TRIANGLES)
        for corners, bulge in quads:
            a_, b_, cc_, d_ = corners
            for tri in ((a_, b_, bulge), (a_, bulge, cc_),
                        (a_, cc_, d_), (a_, d_, bulge)):
                # per-face normal via cross product
                ax_, ay_, az_ = (tri[1][0] - tri[0][0],
                                 tri[1][1] - tri[0][1],
                                 tri[1][2] - tri[0][2])
                bx_, by_, bz_ = (tri[2][0] - tri[0][0],
                                 tri[2][1] - tri[0][1],
                                 tri[2][2] - tri[0][2])
                nx = ay_ * bz_ - az_ * by_
                ny = az_ * bx_ - ax_ * bz_
                nz = ax_ * by_ - ay_ * bx_
                nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                # outward check vs sub-rock center
                cx_ = (tri[0][0] + tri[1][0] + tri[2][0]) / 3 - jx
                cy_ = (tri[0][1] + tri[1][1] + tri[2][1]) / 3 - jy
                cz_ = (tri[0][2] + tri[1][2] + tri[2][2]) / 3 - jz
                if nx * cx_ + ny * cy_ + nz * cz_ < 0:
                    nx, ny, nz = -nx, -ny, -nz
                    tri = (tri[0], tri[2], tri[1])
                glNormal3f(nx / nl, ny / nl, nz / nl)
                for v in tri:
                    glVertex3f(*v)
        glEnd()

    def _draw_sphere(self, radius, lons=16, lats=10):
        """Backface-culled sphere (no speckle/moire from double-sided quads)."""
        if os.environ.get("STAR_ARMADA_NO_CULL") != "1":
            glEnable(GL_CULL_FACE)
        glCallList(self._sphere_list(radius))
        glDisable(GL_CULL_FACE)

    def _sphere_list(self, radius):
        key = round(radius)
        if key in self.ship_lists:
            return self.ship_lists[key]
        lst = _gl.glGenLists(1)
        glNewList(lst, GL_COMPILE)
        # NOTE: no glColor here — caller's color applies (planets/stations were
        # rendering gray-white because the list overrode their color).
        # GL_TRIANGLES with deterministic outward winding (normal-flip check):
        # mixed winding + culling produced the dithered/patchy sphere.
        lons, lats = 18, 10
        for i in range(lons):
            lon0 = 2 * math.pi * i / lons
            lon1 = 2 * math.pi * (i + 1) / lons
            for j in range(lats):
                lat0 = math.pi * j / lats - math.pi / 2
                lat1 = math.pi * (j + 1) / lats - math.pi / 2

                def vert(lon, lat):
                    return (radius * math.cos(lat) * math.sin(lon),
                            radius * math.sin(lat),
                            radius * math.cos(lat) * math.cos(lon))

                a, b = vert(lon0, lat0), vert(lon1, lat0)
                c, d = vert(lon1, lat1), vert(lon0, lat1)
                for tri in ((a, b, c), (a, c, d)):
                    # outward winding: face normal must point away from origin
                    ax_, ay_, az_ = (tri[1][0] - tri[0][0],
                                     tri[1][1] - tri[0][1],
                                     tri[1][2] - tri[0][2])
                    bx_, by_, bz_ = (tri[2][0] - tri[0][0],
                                     tri[2][1] - tri[0][1],
                                     tri[2][2] - tri[0][2])
                    nx = ay_ * bz_ - az_ * by_
                    ny = az_ * bx_ - ax_ * bz_
                    nz = ax_ * by_ - ay_ * bx_
                    centroid = ((tri[0][0] + tri[1][0] + tri[2][0]) / 3,
                                (tri[0][1] + tri[1][1] + tri[2][1]) / 3,
                                (tri[0][2] + tri[1][2] + tri[2][2]) / 3)
                    if nx * centroid[0] + ny * centroid[1] + nz * centroid[2] < 0:
                        tri = (tri[0], tri[2], tri[1])       # flip winding
                    glBegin(GL_TRIANGLES)
                    for v in tri:
                        # sphere normal = normalized vertex position
                        n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
                        glNormal3f(v[0] / n, v[1] / n, v[2] / n)
                        glVertex3f(*v)
                    glEnd()
        glEndList()
        self.ship_lists[key] = lst
        return lst

    def _draw_box(self, sx, sy, sz):
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        glBegin(GL_QUADS)
        # top
        glVertex3f(-hx, hy, -hz); glVertex3f(-hx, hy, hz)
        glVertex3f(hx, hy, hz); glVertex3f(hx, hy, -hz)
        # bottom
        glVertex3f(-hx, -hy, -hz); glVertex3f(hx, -hy, -hz)
        glVertex3f(hx, -hy, hz); glVertex3f(-hx, -hy, hz)
        # front (+z)
        glVertex3f(-hx, -hy, hz); glVertex3f(hx, -hy, hz)
        glVertex3f(hx, hy, hz); glVertex3f(-hx, hy, hz)
        # back
        glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, hy, -hz)
        glVertex3f(hx, hy, -hz); glVertex3f(hx, -hy, -hz)
        # left
        glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, -hy, hz)
        glVertex3f(-hx, hy, hz); glVertex3f(-hx, hy, -hz)
        # right
        glVertex3f(hx, -hy, -hz); glVertex3f(hx, -hy, hz)
        glVertex3f(hx, hy, hz); glVertex3f(hx, hy, -hz)
        glEnd()

    # ------------------------------------------------------------------ ships
    def _draw_ships(self, selection: set, cache=None):
        st = self.state
        # hull panel texture scoped to the ship/station pass only: grayscale
        # plate map multiplied by owner color (GL_MODULATE). Untextured passes
        # (starfield points, rings, sites) must not inherit the bound texture.
        import OpenGL.GL as GL
        if self._hull_tex is None:
            self._hull_tex = tex.surface_to_texture(tex.hull_texture(),
                                                    repeat=True)
        GL.glPushAttrib(int(GL.GL_ENABLE_BIT) | int(GL.GL_TEXTURE_BIT))
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._hull_tex)
        GL.glTexEnvi(GL.GL_TEXTURE_ENV, GL.GL_TEXTURE_ENV_MODE, GL.GL_MODULATE)
        # Ships/stations are scaled uniformly at draw time (same factor on all
        # axes), so GL_NORMALIZE is unnecessary work per vertex.  Disabling it
        # cuts driver overhead without changing the output.
        GL.glDisable(GL.GL_NORMALIZE)
        if cache is not None:
            visible = cache.get("visible", [])
            ships = [e for e, _ in visible
                     if (e.is_ship and "ships" not in self.skip) or
                        (e.is_squadron and "squadrons" not in self.skip)]
            stations = [e for e, _ in visible
                        if e.is_station and "stations" not in self.skip]
            # Engine trails are emitted before hulls so motion cues stay behind.
            for e in ships:
                self._draw_ship_trail(e)
            # Batch roles:
            #   1. opaque base/dark/trim (hull GLSL program)
            #   2. accent (matte, no texture)
            #   3. lit/cool emissive (unlit, no texture)
            # This keeps per-entity transforms and owner colors while reducing
            # the number of GL state switches per ship from six to three.
            with self.materials.use("hull", materialPass=0.0):
                for role, material_pass in (
                        ("base", 0.0),
                        ("dark", 1.0),
                        ("trim", 2.0)):
                    self._draw_ship_role_batch(role, ships, stations, cache,
                                               material_pass=material_pass)
            # Dedicated accent pass: lighting on, texturing off.
            if ships or stations:
                glDisable(GL_TEXTURE_2D)
                glEnable(GL_LIGHTING)
                self._material_matte()
                self._draw_ship_role_batch("accent", ships, stations, cache)
                glEnable(GL_TEXTURE_2D)
            # Dedicated emissive batch: lighting/texturing disabled once.
            if ships or stations:
                glDisable(GL_LIGHTING)
                glDisable(GL_TEXTURE_2D)
                self._draw_ship_role_batch("lit", ships, stations, cache)
                self._draw_ship_role_batch("cool", ships, stations, cache)
                glEnable(GL_LIGHTING)
                glEnable(GL_TEXTURE_2D)
            # Per-ship engine glows (additive world-space billboards) after hulls.
            for e in ships:
                self._draw_ship_glow(e)
            # Station construction rings on top of station hulls.
            for e in stations:
                self._draw_station_queue_ring(e)
        else:
            for e in st.entities.values():
                if not e.alive or not st.can_see(self.local_player, e.id):
                    continue
                if e.is_planet or e.jump_travelling:
                    # in hyperspace: no fixed-function hull either (#92)
                    continue
                if (e.is_ship and "ships" not in self.skip) or \
                        (e.is_squadron and "squadrons" not in self.skip):
                    self._draw_ship(e)
                elif e.is_station and "stations" not in self.skip:
                    self._draw_station(e)
        if self.materials.available:
            _gl.glUseProgram(0)
        GL.glPopAttrib()

    def _draw_ship_trail(self, e):
        size = self._ship_size(e)
        spd = e.vel.length()
        if spd <= 2:
            return
        trail_length = size.length * (1.1 + spd / 240.0)
        tail_offset = size.stern - trail_length
        tail = Vec3(e.pos.x + tail_offset * math.sin(e.yaw), e.pos.y,
                    e.pos.z + tail_offset * math.cos(e.yaw))
        if not segment_visible(self.state, self.local_player, e.pos, tail):
            return
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        glColor4f(0.4, 0.7, 1.0, min(0.55, spd / 400.0))
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        glRotatef(math.degrees(e.yaw), 0, 1, 0)
        glBegin(GL_TRIANGLES)
        glVertex3f(0, 0, size.stern - trail_length)
        glVertex3f(-size.half_width * 0.35, 0, size.stern)
        glVertex3f(size.half_width * 0.35, 0, size.stern)
        glEnd()
        glPopMatrix()
        glDepthMask(True)
        glDisable(GL_BLEND)

    def _draw_ship_glow(self, e):
        size = self._ship_size(e)
        spd = e.vel.length()
        if spd <= 8:
            return
        L = -size.stern
        rear = (e.pos.x - L * math.sin(e.yaw),
                e.pos.y,
                e.pos.z - L * math.cos(e.yaw))
        glow_radius = size.length * (.10 + .06 * min(1., spd / 300.))
        if (self._in_front(rear, glow_radius) and self.state.is_position_visible(
                self.local_player, position(rear))):
            glEnable(GL_BLEND)
            glDepthMask(False)
            self._draw_glow(rear, glow_radius,
                            (0.45, 0.75, 1.0), alpha=0.55, additive=True)
            glDepthMask(True)
            glDisable(GL_BLEND)

    def _draw_ship_role_batch(self, role, ships, stations, cache, material_pass=None):
        """Draw one material role for all visible ships/squadrons and stations.

        Uses the cached transform matrices per entity; color is computed from
        the cached owner color and relation.  Ships below the configured LOD
        thresholds skip detail roles to save per-entity GL work without changing
        the silhouette or owner color.
        """
        rel_cache = cache["relation"]
        col_cache = cache["owner_color"]
        # LOD thresholds: detail roles become visually noise below these sizes.
        LOD_BASE_ONLY = getattr(self, '_LOD_BASE_ONLY_PX', 16.0)
        LOD_DETAIL = getattr(self, '_LOD_DETAIL_PX', 34.0)
        if role == "lit" or role == "cool":
            # Caller already disabled lighting/texture for the emissive batch.
            pass
        elif role == "accent":
            # Caller already set matte lighting and disabled texturing.
            pass
        elif material_pass is not None:
            # base/dark/trim under hull shader
            self._material_metal(8.0 if role == "base" else 12.0 if role == "trim" else 8.0,
                                 (0.42, 0.42, 0.42) if role != "trim" else (0.85, 0.85, 0.85))
            self.materials.hull_pass(material_pass)
        for e in ships:
            entry = cache.get(e.id)
            if entry is None:
                continue
            apparent = entry["apparent"]
            # LOD: skip detail and emissive roles for very small/on-screen ships.
            if apparent < LOD_BASE_ONLY and role != "base":
                continue
            if apparent < LOD_DETAIL and role in ("dark", "trim", "accent", "cool"):
                continue
            size = entry["size"]
            authored = is_authored(size.shape) if ":" in size.shape else False
            if material_pass is not None:
                self.materials.hull_pass(material_pass, authored)
            color = col_cache.get(e.owner, (0.6, 0.6, 0.6))
            paint = color
            color = mk.hull_shade(color, rel_cache.get(e.owner, "neutral"))
            glPushMatrix()
            glTranslatef(e.pos.x, e.pos.y, e.pos.z)
            glRotatef(math.degrees(e.yaw), 0, 1, 0)
            glScalef(size.scale, size.scale, size.scale)
            if role == "base":
                glColor3f(*color)
            elif role == "dark":
                glColor3f(color[0] * 0.52, color[1] * 0.52, color[2] * 0.52)
            elif role == "trim":
                glColor3f(min(1.0, color[0] * 1.4 + 0.25),
                           min(1.0, color[1] * 1.4 + 0.25),
                           min(1.0, color[2] * 1.4 + 0.25))
            elif role == "accent":
                # Authored paint is already broad geometry: keep owner saturation,
                # rather than lifting its color twice toward white.
                glColor3f(*(paint if authored else
                            tuple(min(1.0, c * 1.15 + .14) for c in color)))
            elif role == "lit":
                glColor3f(1.0, 0.80, 0.52)
            elif role == "cool":
                # lighting/texture already disabled by the lit pass; keep off
                glColor3f(0.38, 0.82, 1.0)
            glCallList(self._ship_display_list(size.shape + ("" if role == "base" else "_" + role)))
            glPopMatrix()
        for e in stations:
            if role in ("base", "dark", "trim") and material_pass is None:
                continue
            entry = cache.get(e.id)
            if entry is None:
                continue
            color = col_cache.get(e.owner, (0.6, 0.6, 0.6))
            from render.planet_building_geometry import station_frame
            from render.faction_visuals import owner_faction
            faction = owner_faction(self.state, e.owner)
            origin, basis, _ = station_frame(self.state, e, math.radians(self.time * 3.))
            authored_station = is_authored(f"{faction}:{e.data_id}")
            glPushMatrix()
            glTranslatef(*origin)
            _gl.glMultMatrixf([*basis[0], 0., *basis[1], 0., *basis[2], 0., 0., 0., 0., 1.])
            scale = e.radius / 50.0
            glScalef(scale, scale, scale)
            if role in ("base", "dark", "trim"):
                if role == "base":
                    tint = color
                    if not self.materials.available:
                        tint = tuple(.42 + .18 * c for c in color)
                elif role == "dark":
                    tint = (0.20, 0.24, 0.30)
                else:
                    tint = (0.68, 0.76, 0.84)
                glColor3f(*tint)
                if self.materials.available:
                    self.materials.hull_pass(material_pass, authored_station)
                glCallList(self._station_detail_list(e.data_id, role, faction))
            elif role == "accent":
                glColor3f(*(color if authored_station else
                            tuple(min(1.0, c * 1.15 + .14) for c in color)))
                glCallList(self._station_detail_list(e.data_id, "accent", faction))
            elif role == "lit":
                glColor3f(1.0, 0.80, 0.52)
                glCallList(self._station_detail_list(e.data_id, "lit", faction))
            elif role == "cool":
                glColor3f(0.38, 0.82, 1.0)
                glCallList(self._station_detail_list(e.data_id, "cool", faction))
            glPopMatrix()
        # The caller owns program, lighting and texture scopes across roles.
        # In particular lit must not re-enable lighting before cool is emitted.

    def _draw_station_queue_ring(self, e):
        if not e.build_queue:
            return
        item = e.build_queue[0]
        frac = 1.0 - max(0.0, item.get("time_left", 0)) / max(0.1, item.get("total", 1))
        glDisable(GL_DEPTH_TEST)
        glColor3f(0.4, 1.0, 0.5)
        glLineWidth(3.0)
        glBegin(GL_LINE_STRIP)
        for i in range(int(40 * min(1.0, frac)) + 1):
            a = i / 40 * 2 * math.pi
            glVertex3f(math.sin(a) * e.radius * 1.5, e.radius * 0.8,
                       math.cos(a) * e.radius * 1.5)
        glEnd()
        glEnable(GL_DEPTH_TEST)

    # ------------------------------------------------------- ownership markers
    def _relation(self, owner: int) -> str:
        """Own/ally/enemy/neutral for an owner from the local player's view."""
        return mk.relation_of(self.local_player, owner,
                              self.state.allied_player_ids(self.local_player))

    def _hull_color(self, e):
        """Base hull tint, pushed apart by relation.

        Hull tint is the ownership channel the additive shield bubble washes
        out, so own/ally hulls are lifted and hostile hulls darkened to keep the
        tint readable in a scrum. Planets/terrain are left alone.
        """
        color = self._owner_color(e.owner)
        if e.is_planet:
            return color
        return mk.hull_shade(color, self._relation(e.owner))

    def _draw_ownership_markers(self, cache):
        """Screen-clamped chevron (own/ally) / diamond (hostile) on each unit.

        Only currently detected units get a marker — a marker outside sensor
        coverage would be the same intelligence leak the fog mask exists to
        prevent.  This implementation batches all markers into two immediate-mode
        calls (fill triangles + outline segments) to avoid per-entity matrix
        push/pop overhead.
        """
        visible = cache.get("visible")
        if not visible:
            return
        mode = mk.marker_mode(getattr(self, "marker_mode", "all"))
        if mode == "off":
            return
        import OpenGL.GL as GL
        rel_cache = cache["relation"]
        col_cache = cache["owner_color"]
        right, up, _ = cache["basis"]
        GL.glPushAttrib(int(GL.GL_ENABLE_BIT) | int(GL.GL_CURRENT_BIT) |
                        int(GL.GL_LIGHTING_BIT) | int(GL.GL_LINE_BIT))
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glDisable(GL.GL_CULL_FACE)
        glDisable(GL_DEPTH_TEST)          # a cue that can be hidden is useless
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDepthMask(False)
        GL.glLineWidth(1.6)

        # Build list of visible markers with relation/color so we can group
        # by fill color and emit everything in one triangle batch + one outline
        # line batch instead of 500 separate glBegin/glPushMatrix pairs.
        markers = []
        for e, entry in visible:
            if not entry.get("shows_marker"):
                continue
            ppw = entry["ppw_camera"]
            apparent = entry["apparent"]
            if ppw <= 0.0 or apparent <= 0.0:
                continue
            r = mk.world_radius(mk.marker_px(apparent), ppw)
            if r <= 0.0:
                continue
            rel = rel_cache.get(e.owner, "neutral")
            col = mk.marker_color(rel, col_cache.get(e.owner)
                                  if rel in ("own", "ally") else None)
            poly = mk.shape_for(rel)
            markers.append((entry["pos"], r, col, poly))
        if not markers:
            GL.glDepthMask(True)
            GL.glDisable(GL.GL_BLEND)
            glEnable(GL_DEPTH_TEST)
            GL.glEnable(GL.GL_CULL_FACE)
            GL.glPopAttrib()
            return

        # --- fill pass: one GL_TRIANGLES block, color changes only when needed ---
        glBegin(GL_TRIANGLES)
        cur_fill = None
        for pos, r, col, poly in markers:
            if cur_fill != col:
                GL.glColor4f(col[0], col[1], col[2], MARKER_ALPHA)
                cur_fill = col
            # camera-aligned billboard offset above the hull
            cx = pos[0] + up[0] * r * 1.55
            cy = pos[1] + up[1] * r * 1.55
            cz = pos[2] + up[2] * r * 1.55
            # expand polygon vertices to world space
            it = iter(poly)
            base_px, base_py = next(it)
            base = (cx + right[0] * (base_px * r) + up[0] * (base_py * r),
                    cy + right[1] * (base_px * r) + up[1] * (base_py * r),
                    cz + right[2] * (base_px * r) + up[2] * (base_py * r))
            prev_px, prev_py = next(it)
            prev = (cx + right[0] * (prev_px * r) + up[0] * (prev_py * r),
                    cy + right[1] * (prev_px * r) + up[1] * (prev_py * r),
                    cz + right[2] * (prev_px * r) + up[2] * (prev_py * r))
            for px_, py_ in it:
                p = (cx + right[0] * (px_ * r) + up[0] * (py_ * r),
                     cy + right[1] * (px_ * r) + up[1] * (py_ * r),
                     cz + right[2] * (px_ * r) + up[2] * (py_ * r))
                glVertex3f(*base)
                glVertex3f(*prev)
                glVertex3f(*p)
                prev = p
        glEnd()

        # --- outline pass: one GL_LINES block, single outline color ---
        GL.glColor4f(mk.OUTLINE_COLOR[0], mk.OUTLINE_COLOR[1],
                     mk.OUTLINE_COLOR[2], MARKER_ALPHA)
        glBegin(GL_LINES)
        for pos, r, _col, poly in markers:
            cx = pos[0] + up[0] * r * 1.55
            cy = pos[1] + up[1] * r * 1.55
            cz = pos[2] + up[2] * r * 1.55
            it = iter(poly)
            first_px, first_py = next(it)
            prev = (cx + right[0] * (first_px * r) + up[0] * (first_py * r),
                    cy + right[1] * (first_px * r) + up[1] * (first_py * r),
                    cz + right[2] * (first_px * r) + up[2] * (first_py * r))
            first = prev
            for px_, py_ in it:
                p = (cx + right[0] * (px_ * r) + up[0] * (py_ * r),
                     cy + right[1] * (px_ * r) + up[1] * (py_ * r),
                     cz + right[2] * (px_ * r) + up[2] * (py_ * r))
                glVertex3f(*prev)
                glVertex3f(*p)
                prev = p
            glVertex3f(*prev)
            glVertex3f(*first)
        glEnd()

        GL.glDepthMask(True)
        GL.glDisable(GL.GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glPopAttrib()

    def _owner_color(self, owner: int):
        p = self.state.players.get(owner)
        if p is None:
            return (0.6, 0.6, 0.6)
        return p.color

    def _out_tri(self, a, b, c, ref=(0.0, 0.0, 0.0), uvs=None):
        """Emit one triangle with an outward-facing normal (optional UVs).

        Normal direction is checked against the shape's reference center and
        the winding flipped when needed — guarantees correct culling + shading
        regardless of how the corners were specified.
        """
        nx = (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1])
        ny = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2])
        nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        cx = (a[0] + b[0] + c[0]) / 3.0 - ref[0]
        cy = (a[1] + b[1] + c[1]) / 3.0 - ref[1]
        cz = (a[2] + b[2] + c[2]) / 3.0 - ref[2]
        if nx * cx + ny * cy + nz * cz < 0:
            b, c = c, b
            nx, ny, nz = -nx, -ny, -nz
        n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        glNormal3f(nx / n, ny / n, nz / n)
        if uvs is not None:
            glTexCoord2f(uvs[0][0], uvs[0][1])
            glVertex3f(*a)
            glTexCoord2f(uvs[1][0], uvs[1][1])
            glVertex3f(*b)
            glTexCoord2f(uvs[2][0], uvs[2][1])
            glVertex3f(*c)
        else:
            glVertex3f(*a)
            glVertex3f(*b)
            glVertex3f(*c)

    def _panel(self, x0, z0, x1, z1, y=0.0, u0=0.0, v0=0.0, u1=1.0, v1=1.0):
        """Textured horizontal panel (normal +y) with explicit UVs."""
        glBegin(GL_QUADS)
        glNormal3f(0.0, 1.0, 0.0)
        glTexCoord2f(u0, v0); glVertex3f(x0, y, z0)
        glTexCoord2f(u1, v0); glVertex3f(x1, y, z0)
        glTexCoord2f(u1, v1); glVertex3f(x1, y, z1)
        glTexCoord2f(u0, v1); glVertex3f(x0, y, z1)
        glEnd()

    def _octa_tube(self, r0, r1, z0, z1, squash=1.0, rot=0.0):
        """Octagonal tube frustum (flat facets, rounded silhouette).

        Radii interpolate r0->r1 over z0->z1; squash flattens y (ship keels);
        rot spins the cross-section so panels alternate per segment.
        """
        col = [(math.cos(rot + i * math.pi / 4),
                math.sin(rot + i * math.pi / 4) * squash) for i in range(8)]
        glBegin(GL_TRIANGLES)
        for i in range(8):
            x0_, y0_ = col[i]
            x1_, y1_ = col[(i + 1) % 8]
            a = (x0_ * r0, y0_ * r0, z0)
            b = (x1_ * r0, y1_ * r0, z0)
            c = (x1_ * r1, y1_ * r1, z1)
            d = (x0_ * r1, y0_ * r1, z1)
            # quad (a,b,c,d) with plate-proportional UVs
            self._out_tri(a, b, c, ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2, (a[2] + c[2]) / 2),
                          uvs=((i / 8, z0 / 64), ((i + 1) / 8, z0 / 64), ((i + 1) / 8, z1 / 64)))
            self._out_tri(a, c, d, ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2, (a[2] + c[2]) / 2),
                          uvs=((i / 8, z0 / 64), ((i + 1) / 8, z1 / 64), (i / 8, z1 / 64)))
        # end caps (octagonal fans)
        for zz, rr, flip in ((z0, r0, 1), (z1, r1, -1)):
            if rr <= 0.05:
                continue
            center = (0, 0, zz)
            ring = [(col[i][0] * rr, col[i][1] * rr, zz) for i in range(8)]
            for i in range(8):
                p, q = ring[i], ring[(i + 1) % 8]
                if flip > 0:
                    self._out_tri(center, q, p, center,
                                  uvs=((0.5, zz / 64), ((i + 1) / 8, zz / 64), (i / 8, zz / 64)))
                else:
                    self._out_tri(center, p, q, center,
                                  uvs=((0.5, zz / 64), (i / 8, zz / 64), ((i + 1) / 8, zz / 64)))
        glEnd()

    def _capsule(self, radius, cy=0.0, z0=0.0, z1=0.0, lons=8, lats=3,
                 squash=1.0):
        """Rounded end cap: hemisphere band emitted inline (textured UVs)."""
        glBegin(GL_TRIANGLES)
        for i in range(lons):
            lon0 = 2 * math.pi * i / lons
            lon1 = 2 * math.pi * (i + 1) / lons
            for j in range(lats):
                lat0 = math.pi * 0.5 * j / lats
                lat1 = math.pi * 0.5 * (j + 1) / lats

                def vert(lon, lat):
                    return (radius * math.cos(lat) * math.sin(lon),
                            cy + radius * math.sin(lat) * squash,
                            z0 + (radius - radius * math.cos(lat))
                            if z1 >= z0 else
                            z0 - (radius - radius * math.cos(lat)))

                a, b = vert(lon0, lat0), vert(lon1, lat0)
                c, d = vert(lon1, lat1), vert(lon0, lat1)
                for tri, uvs in (((a, b, c),
                                  ((i / lons, 0.5 + lat0 / 3),
                                   ((i + 1) / lons, 0.5 + lat0 / 3),
                                   ((i + 1) / lons, 0.5 + lat1 / 3))),
                                 ((a, c, d),
                                  ((i / lons, 0.5 + lat0 / 3),
                                   ((i + 1) / lons, 0.5 + lat1 / 3),
                                   (i / lons, 0.5 + lat1 / 3)))):
                    aa, bb, cc = tri
                    self._out_tri(aa, bb, cc,
                                  (cy, cy + radius, z0 + radius), uvs=uvs)
        glEnd()

    def _lit_box(self, sx, sy, sz, cx=0.0, cy=0.0, cz=0.0):
        """Axis-aligned box with per-face outward normals (caller color).

        UVs derive from world coordinates / 64 so the hull-panel texture
        keeps one plate scale on every part, box or tube.
        """
        hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
        x0, x1 = cx - hx, cx + hx
        y0, y1 = cy - hy, cy + hy
        z0, z1 = cz - hz, cz + hz
        ref = (cx, cy, cz)
        s = 1.0 / 64.0
        glBegin(GL_TRIANGLES)          # REQUIRED: _out_tri only emits vertices
        # (quad corners, uv-mapping: v spans the vertical axis, u horizontal)
        for quad, umap, vmap in (
                (((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),
                 lambda p: p[0] * s, lambda p: p[1] * s),   # front  (+z)
                (((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)),
                 lambda p: p[0] * s, lambda p: p[1] * s),   # back   (-z)
                (((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)),
                 lambda p: p[2] * s, lambda p: p[1] * s),   # right  (+x)
                (((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)),
                 lambda p: p[2] * s, lambda p: p[1] * s),   # left   (-x)
                (((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)),
                 lambda p: p[0] * s, lambda p: p[2] * s),   # top    (+y)
                (((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),
                 lambda p: p[0] * s, lambda p: p[2] * s)):  # bottom (-y)
            a, b, c, d = quad
            uvs = lambda *pts: [(umap(p), vmap(p)) for p in pts]
            self._out_tri(a, b, c, ref, uvs=uvs(a, b, c))
            self._out_tri(a, c, d, ref, uvs=uvs(a, c, d))
        glEnd()

    def _out_pyr(self, tip, base, ref=(0.0, 0.0, 0.0)):
        """Pyramid: tip point + 4 base corners (base face included)."""
        a, b, c, d = base
        glBegin(GL_TRIANGLES)          # REQUIRED: _out_tri only emits vertices
        self._out_tri(a, b, c, ref)
        self._out_tri(a, c, d, ref)
        self._out_tri(tip, a, b, ref)
        self._out_tri(tip, b, c, ref)
        self._out_tri(tip, c, d, ref)
        self._out_tri(tip, d, a, ref)
        glEnd()

    def _dome(self, radius, lons=10, lats=7, cy=0.0):
        """Hemisphere dome emitted inline (safe inside display lists)."""
        glBegin(GL_TRIANGLES)
        for i in range(lons):
            lon0 = 2 * math.pi * i / lons
            lon1 = 2 * math.pi * (i + 1) / lons
            for j in range(lats):
                lat0 = math.pi * 0.5 * j / lats        # 0..pi/2 (equator->top)
                lat1 = math.pi * 0.5 * (j + 1) / lats

                def vert(lon, lat):
                    return (radius * math.cos(lat) * math.sin(lon),
                            cy + radius * math.sin(lat),
                            radius * math.cos(lat) * math.cos(lon))

                a, b = vert(lon0, lat0), vert(lon1, lat0)
                c, d = vert(lon1, lat1), vert(lon0, lat1)
                for tri in ((a, b, c), (a, c, d)):
                    ax_, ay_, az_ = (tri[1][0] - tri[0][0],
                                     tri[1][1] - tri[0][1],
                                     tri[1][2] - tri[0][2])
                    bx_, by_, bz_ = (tri[2][0] - tri[0][0],
                                     tri[2][1] - tri[0][1],
                                     tri[2][2] - tri[0][2])
                    nx = ay_ * bz_ - az_ * by_
                    ny = az_ * bx_ - ax_ * bz_
                    nz = ax_ * by_ - ay_ * bx_
                    centroid = ((tri[0][0] + tri[1][0] + tri[2][0]) / 3,
                                (tri[0][1] + tri[1][1] + tri[2][1]) / 3 - cy,
                                (tri[0][2] + tri[1][2] + tri[2][2]) / 3)
                    if nx * centroid[0] + ny * centroid[1] + nz * centroid[2] < 0:
                        tri = (tri[0], tri[2], tri[1])
                    for v in tri:
                        n = math.sqrt(v[0] ** 2 + (v[1] - cy) ** 2
                                      + v[2] ** 2) or 1.0
                        glNormal3f(v[0] / n, (v[1] - cy) / n, v[2] / n)
                        glVertex3f(*v)
        glEnd()

    def _station_visual_radius(self, e):
        from render.faction_visuals import owner_faction, normalize_station_key
        faction, data_id = normalize_station_key(e.data_id,
                            owner_faction(getattr(self, 'state', None), e.owner))
        if faction == 'imperial' and not is_authored(f'{faction}:{data_id}'):
            return e.radius
        from render.camera_geometry import station_radius
        return station_radius(data_id, faction) * (e.radius / 50.)

    def _ship_size(self, e):
        from render.ship_sizes import readable_size
        from render.faction_visuals import owner_faction
        scope = getattr(self, '_draw_view', None)
        if scope is not None:
            sizes = scope.setdefault('sizes', {})
            entry = sizes.get(id(e))
            if entry is not None and entry[0] is e:
                return entry[1]
        size = readable_size(self.ds, e.data_id,
                             self._px_per_world((e.pos.x, e.pos.y, e.pos.z), camera_depth=True),
                             owner_faction(getattr(self, 'state', None), e.owner))
        if scope is not None:
            # Retain identity, not mutable/public entity IDs (or recycled ids).
            scope['sizes'][id(e)] = (e, size)
        return size

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
            faction, data_id = normalize_station_key(e.data_id, owner_faction(self.state, e.owner))
            if faction == "imperial" and not is_authored(f"{faction}:{data_id}"):
                return fx  # protected unselected legacy station effect path
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

    def _draw_ship(self, e: Entity):
        ds = self.ds
        # NOTE: deliberately NO bail-out when there is no ShipData entry.
        # ``trade_convoy`` is minted by TradingSystem with no ShipData by
        # design, and ship_visual() already knows how to describe it. The old
        # ``if sd is None: return`` made convoys draw on the MINIMAP (which
        # iterates entities directly) but never in the 3D view, so they were
        # impossible to find or attack.
        size = self._ship_size(e)
        vis = {"shape": size.shape}
        color = self._hull_color(e)
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        # sim facing is (sin(yaw), 0, cos(yaw)); +yaw in GL's right-handed Y
        # rotation matches it exactly (negative sign mirrored the ships —
        # nose trailed while moving sideways/backwards)
        glRotatef(math.degrees(e.yaw), 0, 1, 0)
        # engine trail behind ship (keeps motion readable)
        spd = e.vel.length()
        trail_length = size.length * (1.1 + spd / 240.0)
        tail_offset = size.stern - trail_length
        tail = Vec3(e.pos.x + tail_offset * math.sin(e.yaw), e.pos.y,
                    e.pos.z + tail_offset * math.cos(e.yaw))
        if spd > 2 and segment_visible(self.state, self.local_player, e.pos, tail):
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(False)
            glColor4f(0.4, 0.7, 1.0, min(0.55, spd / 400.0))
            glBegin(GL_TRIANGLES)
            glVertex3f(0, 0, size.stern - trail_length)
            glVertex3f(-size.half_width * 0.35, 0, size.stern)
            glVertex3f(size.half_width * 0.35, 0, size.stern)
            glEnd()
            glDepthMask(True)
            glDisable(GL_BLEND)
        # hull display list
        lst = self._ship_display_list(vis["shape"])
        scale = size.scale
        glScalef(scale, scale, scale)
        # four tone passes: base owner color, dark accents, bright trim, then
        # emissive windows/nozzles/nav-lights. Ships read as multi-tone hardware
        # instead of flat single-color, and the lit pass carries its own glow.
        base = color
        darkc = (color[0] * 0.52, color[1] * 0.52, color[2] * 0.52)
        trimc = (min(1.0, color[0] * 1.4 + 0.25), min(1.0, color[1] * 1.4 + 0.25),
                 min(1.0, color[2] * 1.4 + 0.25))
        dark_lst = self._ship_display_list(vis["shape"] + "_dark")
        trim_lst = self._ship_display_list(vis["shape"] + "_trim")
        lit_lst = self._ship_display_list(vis["shape"] + "_lit")
        # metal pass (A2): base + dark hull plates get a broad metallic sheen.
        # Shininess is LOW on purpose — probed on these hull facets, 24+ puts
        # the highlight on normals that mostly are not there (0 visible px),
        # while 8 gives a wide sheen across many plates.
        self._material_metal(8.0, (0.42, 0.42, 0.42))
        authored = is_authored(size.shape) if ":" in size.shape else False
        with self.materials.use("hull", materialPass=0.0,
                                authoredSurface=float(authored)):
            glColor3f(*base)
            glCallList(lst)
            self.materials.hull_pass(1.0, authored)
            glColor3f(*darkc)
            glCallList(dark_lst)
            self._material_metal(12.0, (0.85, 0.85, 0.85))
            self.materials.hull_pass(2.0, authored)
            glColor3f(*trimc)
            glCallList(trim_lst)
        glDisable(GL_TEXTURE_2D)
        glColor3f(*(self._owner_color(e.owner) if authored else
                    tuple(min(1.0, c * 1.15 + .14) for c in color)))
        glCallList(self._ship_display_list(vis["shape"] + "_accent"))
        self._material_matte()
        # emissive details: drawn UNLIT so they read as light sources rather
        # than surfaces being lit (with lighting on, a window on the ship's
        # dark side goes black — the opposite of the intent)
        import OpenGL.GL as GL
        GL.glDisable(GL.GL_LIGHTING)
        GL.glDisable(GL.GL_TEXTURE_2D)
        glColor3f(1.0, 0.80, 0.52)
        glCallList(lit_lst)
        glColor3f(0.38, 0.82, 1.0)
        glCallList(self._ship_display_list(vis["shape"] + "_cool"))
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glEnable(GL.GL_LIGHTING)
        glPopMatrix()
        # engine glow: additive billboard at the ship's tail (world space)
        if spd > 8:
            L = -size.stern
            rear = (e.pos.x - L * math.sin(e.yaw),
                    e.pos.y,
                    e.pos.z - L * math.cos(e.yaw))
            glow_radius = size.length * (.10 + .06 * min(1., spd / 300.))
            if (self._in_front(rear, glow_radius) and self.state.is_position_visible(
                    self.local_player, position(rear))):
                glEnable(GL_BLEND)
                glDepthMask(False)
                self._draw_glow(rear, glow_radius,
                                (0.45, 0.75, 1.0), alpha=0.55, additive=True)
                glDepthMask(True)
                glDisable(GL_BLEND)

    def _material_metal(self, shininess: float, spec: tuple):
        """Give the current pass a specular response — without touching colour.

        GL_COLOR_MATERIAL is deliberately left ENABLED and bound to
        AMBIENT_AND_DIFFUSE. Disabling it (the obvious way to keep the
        highlight independent of the part's colour) looks correct in
        isolation but silently drops glColor's *diffuse* contribution: every
        plate then shades with the default grey-white material and the
        owner's colour is lost. Measured on a P0 cruiser — with
        GL_COLOR_MATERIAL off the dark/trim tone passes collapse onto the
        base pass; with it on they stay correctly separated.

        Setting GL_SPECULAR/GL_SHININESS alone leaves the faction tint
        intact and still produces the highlight.

        Shininess is kept LOW (see callers): these hull facets have few
        normals, and a tight exponent concentrates the highlight onto
        geometry that mostly is not there — probed, shininess 24+ leaves no
        visible highlight at all, while 2-12 gives a broad metallic sheen.
        """
        import OpenGL.GL as GL
        GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR,
                        (spec[0], spec[1], spec[2], 1.0))
        GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, shininess)

    def _material_matte(self):
        """Back to diffuse-only (no highlight) for the next pass."""
        import OpenGL.GL as GL
        GL.glMaterialfv(GL.GL_FRONT_AND_BACK, GL.GL_SPECULAR, (0.0, 0.0, 0.0, 1.0))
        GL.glMaterialf(GL.GL_FRONT_AND_BACK, GL.GL_SHININESS, 0.0)

    def _ship_display_list(self, shape: str) -> int:
        """Multi-part lit hulls in four baked tone passes.

        Builds four lists per shape: base (owner color), dark (a 0.52 tint of
        the caller color), trim (near-white highlights) and lit (emissive —
        windows, nozzle interiors, running lights; unlit and untextured).
        _draw_ship sets colors and calls them in sequence, so hulls read
        multi-tone instead of flat single-color, and the lit pass gives every
        ship a set of glowing details that survive even in shadow.
        """
        from render.faction_visuals import normalize_ship_key
        requested_role = "base"
        for role in ROLES[1:]:
            if shape.endswith("_" + role):
                shape, requested_role = shape[:-len(role)-1], role
                break
        shape = normalize_ship_key(shape)
        key = gpu_cache_key(shape, requested_role,
                            shape if requested_role == "base" else shape + "_" + requested_role)
        if key in self.ship_lists:
            return self.ship_lists[key]
        import OpenGL.GL as GL
        passes = {p: _gl.glGenLists(1) for p in ROLES}
        for pname, lst in passes.items():
            glNewList(lst, GL_COMPILE)
            GL.glPushAttrib(GL.GL_ENABLE_BIT)
            GL.glDisable(GL.GL_CULL_FACE)
            if pname == "lit":
                # emissive pass: no lighting (a window is its own light source)
                # and no hull-panel texture (it would darken the glow).
                GL.glDisable(GL.GL_LIGHTING)
                GL.glDisable(GL.GL_TEXTURE_2D)
            self._emit_detail_hull(shape, pname)
            GL.glPopAttrib()
            glEndList()
        for pname in ROLES:
            legacy = shape if pname == "base" else shape + "_" + pname
            self.ship_lists[gpu_cache_key(shape, pname, legacy)] = passes[pname]
        return passes[requested_role]

    def _armor_loft(self, sections, bevel=2.0):
        glBegin(GL_TRIANGLES)
        for normal, vertices in armor_loft(sections, bevel):
            glNormal3f(*normal)
            for x, y, z in vertices:
                glTexCoord2f(x / 32.0, z / 32.0)
                glVertex3f(x, y, z)
        glEnd()

    def _emit_hull(self, shape: str, pname: str) -> None:
        """Geometry for one tone pass of a ship hull."""
        dark = pname == "dark"
        trim = pname == "trim"
        lit = pname == "lit"
        if shape == "wedge":
            if not dark and not trim and not lit:
                # fighter: fuselage + canopy + swept wings + tail fin
                self._lit_box(14, 6, 40, cy=3)
                self._out_pyr((0, 4, 34), ((-7, 1, 16), (7, 1, 16),
                                           (7, 6, 16), (-7, 6, 16)))
                self._lit_box(34, 1.6, 16, cx=18, cy=4, cz=-4)   # right wing
                self._lit_box(34, 1.6, 16, cx=-18, cy=4, cz=-4)  # left wing
                self._lit_box(2.5, 12, 14, cy=9, cz=-12)         # tail fin
            elif dark:
                # intakes, missile racks, nozzles, stabilizers
                self._lit_box(7, 3.2, 9, cy=7.6, cz=9)           # canopy hump
                self._lit_box(4.5, 2.2, 5, cy=9.4, cz=4)         # canopy step
                self._lit_box(6, 3, 11, cx=18, cy=1.2, cz=-7)    # wing intakes
                self._lit_box(6, 3, 11, cx=-18, cy=1.2, cz=-7)
                self._lit_box(2.2, 2.2, 15, cx=10, cy=3, cz=-8)  # missile racks
                self._lit_box(2.2, 2.2, 15, cx=-10, cy=3, cz=-8)
                self._lit_box(3.4, 3.4, 3, cx=5, cy=0, cz=-21)   # twin nozzles
                self._lit_box(3.4, 3.4, 3, cx=-5, cy=0, cz=-21)
                self._lit_box(4, 4, 3, cz=-20.5)
                self._lit_box(3, 2, 2, cy=6.5, cz=-20.5)
                self._lit_box(9, 1.4, 7, cx=30, cy=7.5, cz=-8)   # stab fins
                self._lit_box(9, 1.4, 7, cx=-30, cy=7.5, cz=-8)
            elif trim:
                # trim: nose probe, wingtip cannons, comm whip
                self._lit_box(1.4, 6, 1.4, cy=6, cz=20)          # nose probe
                self._lit_box(3, 3, 12, cx=34, cy=4, cz=4)       # wingtip cannons
                self._lit_box(3, 3, 12, cx=-34, cy=4, cz=4)
                self._lit_box(1.2, 7, 1.2, cy=13, cz=-16)        # comm whip
        elif shape == "needle":
            if not dark and not trim and not lit:
                # corvette/frigate — rounded hull: tapered octagonal nose,
                # octagonal main tube, capsule stern, rounded bridge pod
                self._octa_tube(8.5, 3.0, 14, 46, squash=0.55)     # tapered nose
                self._capsule(3.0, cy=0.0, z0=46, z1=52)           # nose cap
                self._octa_tube(10.5, 10.5, -30, 14, squash=0.55)  # main hull
                self._capsule(10.5, cy=0.0, z0=-30, z1=-42, squash=0.55)  # stern
                # bridge pod (rounded, sits dorsal-aft)
                self._octa_tube(5.5, 4.5, -24, -8, squash=0.8, rot=math.pi / 8)
                self._capsule(4.5, cy=0.8, z0=-24, z1=-30, squash=0.8)
            elif dark:
                # nozzles, gun pods, keel fins, intake band, armor skirt
                self._lit_box(3.4, 3.4, 4, cx=-4.5, cy=0.5, cz=-43)
                self._lit_box(3.4, 3.4, 4, cx=4.5, cy=0.5, cz=-43)  # twin nozzles
                self._lit_box(4, 4, 14, cx=12.5, cy=-2, cz=-6)      # gun pods
                self._lit_box(4, 4, 14, cx=-12.5, cy=-2, cz=-6)
                self._lit_box(13, 2.4, 2, cy=-5.2, cz=-10)          # keel fins
                self._lit_box(13, 2.4, 2, cy=-5.2, cz=-22)
                self._lit_box(15, 1.8, 8, cy=5.4, cz=-16)           # intake band
                self._lit_box(9, 3, 5, cy=-4.5, cz=-14)             # ventral skid
                self._octa_tube(6.2, 6.2, -38, -30, squash=0.55)    # armor skirt
            elif trim:
                # trim: dorsal turret + barrels (forward, on the hull spine),
                # comm mast, sensor pods, running lights, deck strip
                self._lit_box(4.5, 4.5, 4.5, cy=6.2, cz=0)          # dorsal turret
                self._lit_box(1.6, 1.6, 9, cy=6.2, cz=-8)           # twin barrels
                self._lit_box(1.2, 9, 1.2, cy=10, cz=-18)           # comm mast
                self._lit_box(2.6, 2.6, 2.6, cx=8.5, cy=4.2, cz=-26)  # sensor pods
                self._lit_box(2.6, 2.6, 2.6, cx=-8.5, cy=4.2, cz=-26)
                self._lit_box(1.8, 1.8, 1.8, cx=10.4, cy=2, cz=6)   # running lights
                self._lit_box(1.8, 1.8, 1.8, cx=-10.4, cy=2, cz=6)
                self._lit_box(16, 1.2, 5, cy=5.0, cz=2)             # deck strip
        elif shape == "cruiser":
            if not dark and not trim and not lit:
                # heavy hull + bow + command tower + nacelles + engine block
                self._armor_loft(((-58, 13, 7, -7), (-30, 18, 7, -7),
                                  (30, 14, 7, -7), (78, 2, 5, -3)), 2.8)
                self._armor_loft(((-32, 9, 18.5, 7), (-12, 9, 18.5, 7),
                                  (-4, 5, 13, 7)), 2.0)
                self._lit_box(8, 6, 44, cx=20, cz=-26)           # right nacelle
                self._lit_box(8, 6, 44, cx=-20, cz=-26)          # left nacelle
                self._lit_box(22, 7, 10, cz=-56)                 # engine block
            elif dark:
                # nozzles, hangar bay, armor ribs, bridge wing
                self._lit_box(6, 6, 5, cx=-7, cy=-2, cz=-61)
                self._lit_box(6, 6, 5, cx=0, cy=-2, cz=-61)
                self._lit_box(6, 6, 5, cx=7, cy=-2, cz=-61)
                self._lit_box(10, 8, 14, cy=-6, cz=-40)          # ventral hangar
                self._lit_box(8, 1.5, 12, cy=-10.2, cz=-40)      # gantry lip
                for cz_ in (44, 20, -4, -28, -50):               # armor ribs
                    self._lit_box(24, 2.5, 4, cy=7.5, cz=cz_)
                self._lit_box(14, 2, 8, cy=17, cz=-30)           # aft bridge wing
                self._lit_box(14, 2, 6, cy=16, cz=-18)           # windows band
            elif trim:
                # trim: turret rows, spinal cannon, masts, emitters, dome
                for cz_ in (18, -2, -22):                        # broadsides
                    self._lit_box(6, 5, 6, cx=16, cy=5, cz=cz_)
                    self._lit_box(6, 5, 6, cx=-16, cy=5, cz=cz_)
                self._lit_box(4, 4, 26, cy=8, cz=58)             # spinal cannon
                self._out_pyr((0, 8, 92), ((-2.5, 6.5, 66), (2.5, 6.5, 66),
                                           (2.5, 9.5, 66), (-2.5, 9.5, 66)))
                self._lit_box(3, 14, 3, cy=18, cz=6)             # sensor mast A
                self._lit_box(8, 1.5, 1.5, cy=24, cz=18)         # mast crossbar
                self._lit_box(3, 9, 3, cy=15, cz=-48)            # sensor mast B
                self._lit_box(5, 2.5, 5, cx=13.4, cy=1, cz=-56)  # shield emitters
                self._lit_box(5, 2.5, 5, cx=-13.4, cy=1, cz=-56)
                self._dome(4.5, 10, 7)                           # comm dome
        elif shape == "dagger":
            if not dark and not trim and not lit:
                # battleship: hull + bow + tower + spine + engine block
                self._armor_loft(((-75, 20, 10, -10), (-48, 27, 10, -10),
                                  (30, 23, 10, -10), (72, 16, 8, -7),
                                  (108, 2, 5, -3)), 3.5)
                # Stepped command citadel instead of a featureless tall cube.
                self._armor_loft(((-50, 12, 22, 9), (-24, 12, 22, 9),
                                  (-16, 8, 17, 9)), 2.5)
                self._armor_loft(((-45, 8, 30, 21), (-30, 8, 30, 21),
                                  (-24, 5, 26, 21)), 1.8)
                self._lit_box(4, 18, 18, cy=14, cz=28)           # dorsal spine
                self._lit_box(30, 10, 12, cz=-70)                # engine block
            elif dark:
                # nozzles, keel battery, hull trench, gantries, deflector
                for cx_ in (-11, -4, 4, 11):                     # quad nozzles
                    self._lit_box(5.5, 5.5, 5, cx=cx_, cy=-4, cz=-76)
                self._lit_box(10, 5, 22, cy=-12, cz=-20)         # keel battery
                self._lit_box(4, 3, 8, cy=-15, cz=-14)           # barrel housing
                for cz_ in (60, 40, 8, -18, -44, -62):           # hull trench
                    self._lit_box(2.5, 6, 8, cx=19.5, cy=-6, cz=cz_)
                    self._lit_box(2.5, 6, 8, cx=-19.5, cy=-6, cz=cz_)
                self._lit_box(2.5, 10, 2.5, cx=5.5, cy=20, cz=-14)
                self._lit_box(2.5, 10, 2.5, cx=-5.5, cy=20, cz=-14)
                self._lit_box(20, 2, 5, cy=9.5, cz=-68)          # deflector plate
                self._lit_box(6, 8, 30, cx=21, cy=-3, cz=30)     # armor sponsons
                self._lit_box(6, 8, 30, cx=-21, cy=-3, cz=30)
                self._lit_box(6, 8, 30, cx=21, cy=-3, cz=-30)
                self._lit_box(6, 8, 30, cx=-21, cy=-3, cz=-30)
            elif trim:
                # trim: windows, flag mast, turret bank, bow clamps
                self._lit_box(16, 3, 8, cy=30, cz=-34)           # tower windows
                self._lit_box(1.5, 12, 1.5, cy=40, cz=-34)       # flag mast
                for cz_ in (48, 24, -6, -52):                    # turret bank
                    self._lit_box(9, 7, 9, cy=12, cz=cz_)
                    self._lit_box(3.5, 3.5, 10, cy=14, cz=cz_ + 7)
                self._lit_box(12, 3, 10, cy=14, cz=64)           # bow clamps
        else:
            if not dark and not trim and not lit:
                # construction/generic: cargo box + cab + skids
                self._lit_box(26, 14, 36, cy=2)
                self._lit_box(12, 8, 10, cy=11, cz=12)
                self._lit_box(30, 3, 8, cy=-7, cz=-10)
                self._lit_box(30, 3, 8, cy=-7, cz=12)
            elif dark:
                # cargo pods, skid tank
                self._lit_box(8, 8, 8, cx=8, cy=-8, cz=16)
                self._lit_box(8, 8, 8, cx=-8, cy=-8, cz=16)
                self._lit_box(6, 2, 4, cx=0, cy=-8, cz=-12)      # underslug tank
            elif trim:
                # trim: crane mast + jib + welder, beacon, plating, lamps
                self._lit_box(2.5, 14, 2.5, cx=-12, cy=16, cz=-8)
                self._lit_box(14, 2, 2.5, cx=-5, cy=22, cz=-8)
                self._lit_box(2, 2, 12, cx=14, cy=8, cz=6)       # crane jib tip
                self._lit_box(1.5, 1.5, 1.5, cx=14, cy=8, cz=12) # welder head
                self._lit_box(1.2, 6, 1.2, cx=-14, cy=8, cz=-14) # comm beacon
                self._lit_box(20, 1.6, 5, cy=7.6, cz=-14)        # roof plating
                self._lit_box(3, 3, 2, cx=15, cy=2, cz=-14)      # spot lamps
                self._lit_box(5, 5, 3, cz=-18.5)                 # engine nozzles
                self._lit_box(4, 3, 2, cy=7, cz=18.5)
        if lit:
            # emissive details last so they are visible in every shape branch
            self._emit_glazing(shape if shape in
                               ("needle", "cruiser", "dagger", "wedge", "box")
                               else "box")

    def _emit_glazing(self, shape: str) -> None:
        """Emissive windows, nozzle interiors and running lights.

        Drawn in the ``lit`` pass, which runs unlit and untextured, so these
        boxes read as their own light sources. Window strips are long/thin and
        inset just proud of the hull plating they sit on; running lights are
        small port(red)/starboard(green) markers placed so the eye can read
        which way a hull is facing at tactical zoom.
        """
        # warm cabin white — the lit pass has no lighting, so this colour is
        # exactly what hits the framebuffer
        w = (1.0, 0.80, 0.52)
        # ---- window strips -------------------------------------------------
        # strips are per-shape; widths/heights are a fraction of the hull
        strips = {
            # (x, y, z, sx, sy, sz)
            "needle": [(-9.6, 3.0, -4, 0.5, 1.1, 16), (9.6, 3.0, -4, 0.5, 1.1, 16),
                       (-5.0, 5.6, -14, 6.0, 0.5, 0.9), (5.0, 5.6, -14, 6.0, 0.5, 0.9),
                       (-6.6, 4.0, 8, 0.5, 0.9, 9), (6.6, 4.0, 8, 0.5, 0.9, 9),
                       (-8.5, 3.2, -34, 4.0, 0.5, 0.9), (8.5, 3.2, -34, 4.0, 0.5, 0.9)],
            "cruiser": [(-13.6, 4.0, -30, 0.5, 1.3, 46), (13.6, 4.0, -30, 0.5, 1.3, 46),
                        (-13.6, -2.0, -6, 0.5, 0.9, 26), (13.6, -2.0, -6, 0.5, 0.9, 26),
                        (-9.0, 17.5, -18, 16.0, 1.4, 0.8),
                        (-11.0, 15.0, -30, 8.0, 0.8, 0.8),
                        (-15.0, 4.0, -40, 10.0, 0.7, 0.8)],
            "dagger": [(-17.6, 6.0, -44, 0.5, 1.6, 66), (17.6, 6.0, -44, 0.5, 1.6, 66),
                       (-19.5, 8.0, 20, 0.5, 1.1, 40), (19.5, 8.0, 20, 0.5, 1.1, 40),
                       (-17.5, -6.0, -30, 0.5, 0.9, 30), (17.5, -6.0, -30, 0.5, 0.9, 30),
                       (-11.0, 30.5, -34, 18.0, 1.6, 0.8),
                       (-5.0, 26.0, -34, 0.8, 0.8, 8.0), (5.0, 26.0, -34, 0.8, 0.8, 8.0),
                       (-11.0, 21.5, 28, 6.0, 0.8, 0.8)],
            "wedge": [(6.0, 4.6, 2, 0.5, 1.2, 8), (-6.0, 4.6, 2, 0.5, 1.2, 8),
                      (14.0, 4.6, -6, 0.6, 0.8, 8), (-14.0, 4.6, -6, 0.6, 0.8, 8),
                      (0.0, 4.2, 30, 3.2, 0.6, 0.8)],
            "box": [(0.0, 6.0, 19.0, 6.0, 1.2, 0.8),
                    (-13.0, 2.0, 4, 0.6, 2.0, 10), (13.0, 2.0, 4, 0.6, 2.0, 10),
                    (0.0, 9.0, 17.0, 3.0, 0.8, 0.8)],
        }[shape] if shape in ("needle", "cruiser", "dagger", "wedge", "box") else []
        for x, y, z, sx, sy, sz in strips:
            self._lit_box(sx, sy, sz, cx=x, cy=y, cz=z)
        # ---- engine nozzle interiors --------------------------------------
        # a bright disc inside each nozzle: the same positions the `dark` pass
        # cuts the nozzle bodies into
        nozzles = {
            "needle": [(-4.5, 0.5, -44.2), (4.5, 0.5, -44.2)],
            "cruiser": [(-7, -2, -62.4), (0, -2, -62.4), (7, -2, -62.4)],
            "dagger": [(-11, -4, -77.4), (-4, -4, -77.4), (4, -4, -77.4), (11, -4, -77.4)],
            "wedge": [(5, 0, -22.0), (-5, 0, -22.0)],
            "box": [(0, 0, -20.0)],
        }.get(shape, [])
        for x, y, z in nozzles:
            self._lit_box(4.2, 4.2, 0.7, cx=x, cy=y, cz=z)
        # ---- running lights ----------------------------------------------
        # port = red, starboard = green. Colour is per-vertex here; the pass is
        # unlit so these stay crisp at any distance.
        nav = {
            "needle": [(10.6, 2.2, 4), (-10.6, 2.2, 4)],
            "cruiser": [(20, 6, 6), (-20, 6, 6)],
            "dagger": [(21, 9, 0), (-21, 9, 0)],
            "wedge": [(35, 4, 4), (-35, 4, 4)],
            "box": [(13, 8, -14), (-13, 8, -14)],
        }.get(shape, [])
        for i, (x, y, z) in enumerate(nav):
            col = (1.0, 0.18, 0.14) if i == 0 else (0.25, 1.0, 0.35)
            glColor3f(*col)
            self._lit_box(1.7, 1.7, 1.7, cx=x, cy=y, cz=z)
        glColor3f(*w)

    def _station_ring(self, r: float, segments: int = 36):
        """Chunky solid ring: top/bottom annuli + outer/inner walls.

        Explicit normals (annulus faces are degenerate for the ref-dot trick
        because all corners share the ref's plane); culling off so the ring
        reads solid from every angle.
        """
        import OpenGL.GL as GL
        GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_LIGHTING_BIT)
        GL.glDisable(GL.GL_CULL_FACE)
        top_w = r * 0.20          # annulus width
        h = r * 0.10              # wall height
        for i in range(segments):
            a0 = i / segments * 2 * math.pi
            a1 = (i + 1) / segments * 2 * math.pi
            ro, ri = r, r - top_w
            o0 = (math.sin(a0) * ro, 0.0, math.cos(a0) * ro)
            o1 = (math.sin(a1) * ro, 0.0, math.cos(a1) * ro)
            n0 = (math.sin(a0) * ri, 0.0, math.cos(a0) * ri)
            n1 = (math.sin(a1) * ri, 0.0, math.cos(a1) * ri)
            # top annulus (normal up)
            glNormal3f(0, 1, 0)
            glBegin(GL_QUADS)
            glVertex3f(*o0); glVertex3f(*o1); glVertex3f(*n1); glVertex3f(*n0)
            # bottom annulus (normal down)
            glNormal3f(0, -1, 0)
            glVertex3f(*o1); glVertex3f(*o0); glVertex3f(*n0); glVertex3f(*n1)
            glEnd()
            # outer wall (normal outward), two tris
            nx0, nz0 = math.sin(a0), math.cos(a0)
            nx1, nz1 = math.sin(a1), math.cos(a1)
            glNormal3f(nx0, 0, nz0)
            glBegin(GL_TRIANGLES)
            glVertex3f(*o0)
            glVertex3f(o0[0], h, o0[2])
            glVertex3f(o1[0], h, o1[2])
            glNormal3f(nx1, 0, nz1)
            glVertex3f(*o0)
            glVertex3f(o1[0], h, o1[2])
            glVertex3f(*o1)
            glEnd()
        GL.glPopAttrib()

    def _draw_station(self, e: Entity):
        """Radius-50 cached hardware with scoped alloy shading and faction paint."""
        if self.ds.stations.get(e.data_id) is None:
            return
        from render.faction_visuals import owner_faction
        faction = owner_faction(self.state, e.owner)
        color = self._owner_color(e.owner)
        authored_station = is_authored(f"{faction}:{e.data_id}")
        glPushMatrix()
        from render.planet_building_geometry import station_frame
        origin, basis, scale = station_frame(self.state, e, math.radians(self.time * 3.))
        glTranslatef(*origin)
        _gl.glMultMatrixf([*basis[0], 0., *basis[1], 0., *basis[2], 0., 0., 0., 0., 1.])
        glPushMatrix()
        # Keep shader model coordinates near ship dimensions: scaling unit-radius
        # geometry would make every station fit inside a single shader plate.
        scale = e.radius / 50.0
        glScalef(scale, scale, scale)
        self._material_metal(8.0, (0.50, 0.55, 0.62))
        with self.materials.use("hull", materialPass=0.0,
                                authoredSurface=float(authored_station)):
            for role, material_pass, tint in (
                    ("base", 0.0, color),
                    ("dark", 1.0, (0.20, 0.24, 0.30)),
                    ("trim", 2.0, (0.68, 0.76, 0.84))):
                self.materials.hull_pass(material_pass, authored_station)
                if not self.materials.available and role == "base":
                    tint = tuple(.42 + .18*c for c in color)
                glColor3f(*tint)
                glCallList(self._station_detail_list(e.data_id, role, faction))
        # Dedicated broad painted armor, not an overall owner tint. Draw outside
        # the alloy shader so faction saturation survives on the actual plates.
        glDisable(GL_TEXTURE_2D)
        glColor3f(*(color if authored_station else
                    tuple(min(1.0, c*1.15+.14) for c in color)))
        glCallList(self._station_detail_list(e.data_id, "accent", faction))
        self._material_matte()
        glDisable(GL_LIGHTING)
        glColor3f(1.0, 0.80, 0.52)
        glCallList(self._station_detail_list(e.data_id, "lit", faction))
        glColor3f(0.38, 0.82, 1.0)
        glCallList(self._station_detail_list(e.data_id, "cool", faction))
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_LIGHTING)
        glPopMatrix()
        if e.build_queue:
            item = e.build_queue[0]
            frac = 1.0 - max(0.0, item.get("time_left", 0)) / max(0.1, item.get("total", 1))
            glDisable(GL_DEPTH_TEST)
            glColor3f(0.4, 1.0, 0.5)
            glLineWidth(3.0)
            glBegin(GL_LINE_STRIP)
            for i in range(int(40 * min(1.0, frac)) + 1):
                a = i / 40 * 2 * math.pi
                glVertex3f(math.sin(a) * e.radius * 1.5, e.radius * 0.8,
                           math.cos(a) * e.radius * 1.5)
            glEnd()
            glEnable(GL_DEPTH_TEST)
        glPopMatrix()

    def _station_detail_list(self, data_id, role, faction="imperial"):
        from render.faction_visuals import normalize_station_key
        from game.systems.planet_buildings import BUILDING_TYPES
        if data_id not in BUILDING_TYPES:
            faction, data_id = normalize_station_key(data_id, faction)
        role = role if role in ROLES else "base"
        legacy = "station_detail:" + faction + ":" + data_id + ":" + role
        key = gpu_cache_key(f"{faction}:{data_id}", role, legacy)
        if key not in self.ship_lists:
            lst = _gl.glGenLists(1)
            glNewList(lst, GL_COMPILE)
            self._emit_detail_mesh(station_mesh(data_id, faction)[role])
            glEndList()
            self.ship_lists[key] = lst
        return self.ship_lists[key]

    def _emit_detail_mesh(self, mesh):
        """One batch per material role; normals and UVs stay in model space."""
        glBegin(GL_TRIANGLES)
        for normal, vertices in mesh:
            glNormal3f(*normal)
            for x, y, z in vertices:
                glTexCoord2f(x / 32.0, z / 32.0)
                glVertex3f(x, y, z)
        glEnd()

    def _emit_detail_hull(self, shape, role):
        self._emit_detail_mesh(ship_mesh(shape)[role])

    # ------------------------------------------------------------------ projectiles
    def _station_lit_list(self, data_id: str) -> int:
        """Baked emissive details for one station type (built once, reused).

        A station is drawn every frame from `r`-relative calls, so the lit
        windows cannot be a fixed world-size box: the list is compiled for a
        UNIT radius and scaled by `e.radius` at call time, exactly like the
        hull lists are scaled by ship visual scale.
        """
        key = "station_lit:" + data_id
        cached = self.ship_lists.get(key)
        if cached is not None:
            return cached
        import OpenGL.GL as GL
        lst = _gl.glGenLists(1)
        glNewList(lst, GL_COMPILE)
        GL.glPushAttrib(GL.GL_ENABLE_BIT)
        GL.glDisable(GL.GL_CULL_FACE)
        self._emit_station_lit(data_id)
        GL.glPopAttrib()
        glEndList()
        self.ship_lists[key] = lst
        return lst

    def _emit_station_lit(self, data_id: str) -> None:
        """Windows, hangar mouths and nav beacons at unit radius.

        Warm cabin light for inhabited volumes, cyan for hangar/work areas,
        and red/green beacon pairs so a station reads as *operating* rather
        than as dead geometry.
        """
        warm = (1.0, 0.80, 0.52)
        cool = (0.62, 0.88, 1.0)
        if data_id == "command_station":
            # ring habitation pods: window band around each pod
            for i in range(8):
                a = i / 8 * 2 * math.pi
                px_, pz_ = math.sin(a), math.cos(a)
                glColor3f(*warm)
                self._lit_box(0.10, 0.035, 0.20, cx=px_ * 1.02, cy=0.0, cz=pz_ * 1.02)
                self._lit_box(0.20, 0.035, 0.10, cx=px_ * 1.02, cy=0.0, cz=pz_ * 1.02)
            # core: a band of lit deck lines + the command tower glazing
            for i in range(12):
                a = i / 12 * 2 * math.pi
                glColor3f(*warm)
                self._lit_box(0.03, 0.05, 0.05, cx=math.sin(a) * 0.43,
                              cy=-0.10, cz=math.cos(a) * 0.43)
            glColor3f(*warm)
            self._lit_box(0.34, 0.04, 0.34, cy=0.70)          # tower cap glazing
            self._lit_box(0.26, 0.03, 0.05, cy=0.50, cz=0.17)  # observation deck
            glColor3f(*cool)                                    # docking bay mouths
            for sgn in (-1, 1):
                self._lit_box(0.04, 0.10, 0.34, cx=sgn * 1.55, cy=0.0)
            # nav beacons: red top, green bottom
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=0.92)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=-0.92)
        elif data_id == "shipyard":
            # build cradles: work-light strips along both gantries
            glColor3f(*cool)
            for sgn in (-1, 1):
                for k in range(4):
                    self._lit_box(0.05, 0.04, 0.20, cx=sgn * 0.95,
                                  cy=0.34, cz=-0.30 + k * 0.20)
            glColor3f(*warm)
            # gantry top strip sits ON TOP of the beam, not inside it: the beam
            # is 0.16 tall about y=0.80, so a strip at 0.80 is fully buried and
            # the whole warm pass renders zero visible pixels (probed).
            self._lit_box(0.40, 0.05, 0.05, cy=0.90)           # gantry top strip
            # pylon lights are pushed to the OUTER face (pylons span x 0.64-0.80)
            self._lit_box(0.06, 0.30, 0.06, cx=0.83, cy=0.30)  # pylon lights
            self._lit_box(0.06, 0.30, 0.06, cx=-0.83, cy=0.30)
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cx=0.83, cy=0.92)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cx=-0.83, cy=0.92)
        elif data_id == "fighter_platform":
            glColor3f(*warm)
            # pushed proud of the control tower's front face (tower spans
            # z -0.75..-0.35 about cz=-0.55); at cz=-0.55 it was buried.
            self._lit_box(0.30, 0.03, 0.05, cy=0.30, cz=-0.32)  # tower glazing
            self._lit_box(0.05, 0.03, 0.22, cx=0.30, cy=0.30, cz=-0.32)
            glColor3f(*cool)                                     # deck edge lighting
            for i in range(5):
                self._lit_box(0.06, 0.03, 0.06, cx=-2 * 0.32 + i * 0.32,
                              cy=0.32, cz=0.78)
                self._lit_box(0.06, 0.03, 0.06, cx=-2 * 0.32 + i * 0.32,
                              cy=0.32, cz=-0.78)
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=1.02, cz=-0.55)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=0.32, cz=0.80)
        elif data_id == "mining_station":
            glColor3f(*warm)
            self._lit_box(0.55, 0.04, 0.05, cy=0.22, cz=0.46)    # refinery windows
            self._lit_box(0.05, 0.04, 0.45, cx=0.56, cy=0.22)
            glColor3f(*cool)                                      # drill head work lights
            for i in range(4):
                a = i / 4 * 2 * math.pi + 0.4
                self._lit_box(0.05, 0.05, 0.05, cx=math.sin(a) * 0.20,
                              cy=-0.86, cz=math.cos(a) * 0.20)
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cx=0.55, cy=0.86)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cx=-0.55, cy=0.86)
        elif data_id == "sensor_station":
            glColor3f(*cool)                                      # array emitter ring
            for i in range(10):
                a = i / 10 * 2 * math.pi
                self._lit_box(0.04, 0.04, 0.04, cx=math.sin(a) * 0.45,
                              cy=1.30, cz=math.cos(a) * 0.45)
            glColor3f(*warm)
            self._lit_box(0.14, 0.04, 0.14, cy=0.16, cz=0.30)     # crew blister
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=1.62)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=-0.42)
        elif data_id == "trade_station":
            for deck, y in ((0.62, 0.62), (0.42, 0.15)):
                glColor3f(*warm)
                for i in range(8):
                    a = i / 8 * 2 * math.pi
                    self._lit_box(0.07, 0.04, 0.07, cx=math.sin(a) * deck,
                                  cy=y, cz=math.cos(a) * deck)
            glColor3f(*cool)                                      # docking pad lights
            for i in range(4):
                a = i / 4 * 2 * math.pi
                glPushMatrix()
                glRotatef(-i * 90.0, 0, 1, 0)
                self._lit_box(0.10, 0.04, 0.10, cx=1.45, cy=0.08)
                glPopMatrix()
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=1.55)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=-0.45)
        elif data_id == "defense_platform":
            glColor3f(*cool)
            for i in range(4):                                    # barbette lights
                glPushMatrix()
                glRotatef(-i * 90.0, 0, 1, 0)
                self._lit_box(0.08, 0.04, 0.08, cx=0.52, cy=0.42)
                glPopMatrix()
            glColor3f(*warm)
            self._lit_box(0.30, 0.04, 0.05, cy=0.12, cz=0.42)     # bunker windows
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=0.62, cz=-0.20)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=-0.45)
        elif data_id == "repair_dock":
            glColor3f(*cool)                                      # welding arcs in the cradle
            for sgn in (-1, 1):
                for k in range(3):
                    self._lit_box(0.05, 0.05, 0.05, cx=sgn * 0.72,
                                  cy=0.40, cz=-0.40 + k * 0.40)
            glColor3f(*warm)
            self._lit_box(0.22, 0.04, 0.05, cy=0.92, cz=0.40)
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=1.00)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=-0.40)
        elif data_id == "energy_relay":
            glColor3f(*cool)                                      # collector coils glow
            for i in range(6):
                a = i / 6 * 2 * math.pi
                self._lit_box(0.07, 0.14, 0.07, cx=math.sin(a) * 0.85,
                              cy=-0.20, cz=math.cos(a) * 0.85)
            glColor3f(0.70, 0.55, 1.0)                            # reactor core seam
            self._lit_box(0.10, 0.10, 0.10)
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=1.14)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=-0.62)
        else:
            glColor3f(*warm)
            self._lit_box(0.60, 0.04, 0.06, cy=0.42, cz=0.52)
            self._lit_box(0.06, 0.04, 0.50, cx=0.52, cy=0.22)
            glColor3f(1.0, 0.18, 0.14)
            self._lit_box(0.05, 0.05, 0.05, cy=1.12)
            glColor3f(0.25, 1.0, 0.35)
            self._lit_box(0.05, 0.05, 0.05, cy=-0.50)

    def _draw_projectiles(self):
        """Shaped weapon fire: bolts for lasers, squares for torpedoes (#90).

        Laser-family bolts are thin rectangles elongated along their heading and
        torpedoes/missiles are squares; each is a soft additive halo around a hot
        core, so a volley still reads as fire instead of noise at tactical zoom.
        Ion, plasma, kinetic and beam projectiles keep the previous additive glow
        plus point-sprite core.

        Every shaped projectile is expanded into triangles and emitted in ONE
        glBegin(GL_TRIANGLES): a begin/end pair per bolt is what made the old
        per-projectile glow path expensive at fleet scale.
        """
        st = self.state
        # bolts are emissive — without this they are lit like surfaces and lose
        # most of their brightness
        import OpenGL.GL as GL
        GL.glDisable(GL.GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        eye = self.camera.eye_position()
        right, up, _fwd = self.camera.basis()
        half_fov_tan = math.tan(math.radians(self.camera.fov / 2))
        pts = []
        shaped = []     # (pos, colour, alpha) vertices for one additive pass
        for p in st.projectiles.values():
            if not st.is_position_visible(self.local_player, p.pos):
                continue
            pos = (p.pos.x, p.pos.y, p.pos.z)
            if not self._in_front(pos, 4.0):
                continue
            col = (p.color[0], p.color[1], p.color[2])
            dist = math.sqrt((pos[0] - eye[0]) ** 2 + (pos[1] - eye[1]) ** 2
                             + (pos[2] - eye[2]) ** 2)
            # world units per screen pixel at this depth
            px_per_world = self.camera.height / (2.0 * max(1.0, dist) * half_fov_tan)
            wd = self.ds.weapons.get(p.weapon_id)
            shape = projectile_shape(wd.type if wd is not None else None)
            if shape == "legacy":
                halo = max(9.0, 5.0 / max(1e-6, px_per_world))
                self._draw_glow(pos, halo, col, alpha=0.45, additive=True)
                pts.append((pos[0], pos[1], pos[2],
                            min(1.0, col[0] + 0.55), min(1.0, col[1] + 0.55),
                            min(1.0, col[2] + 0.55)))
                continue
            length, width = projectile_extents(shape, p.size, px_per_world)
            vel = p.vel.to_tuple()
            if shape == "square":
                halo_l = halo_w = length * SQUARE_HALO
                corners = [self._plane_point(pos, right, up, u, v)
                           for (u, v) in square_quad_offsets(halo_l)]
            else:
                halo_l = length * BOLT_HALO[0]
                halo_w = width * BOLT_HALO[1]
                corners = [self._plane_point(pos, right, up, u, v)
                           for (u, v) in projectile_quad_offsets(vel, right, up,
                                                                 halo_l, halo_w)]
            # halo: centre bright, rim transparent — a flat quad would read as a
            # hard-edged slab instead of fire
            for i in range(4):
                shaped.append((pos, col, HALO_ALPHA))
                shaped.append((corners[i], col, 0.0))
                shaped.append((corners[(i + 1) % 4], col, 0.0))
            hot = tuple(min(1.0, c * (1.0 - CORE_WHITEN) + CORE_WHITEN)
                        for c in col)
            core = [self._plane_point(pos, right, up, u, v)
                    for (u, v) in (square_quad_offsets(length) if shape == "square"
                                   else projectile_quad_offsets(vel, right, up,
                                                                length, width))]
            for a, b, c in ((0, 1, 2), (0, 2, 3)):
                for index in (a, b, c):
                    shaped.append((core[index], hot, CORE_ALPHA))
        if shaped:
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)       # bolts are additive
            glBegin(GL_TRIANGLES)
            for (point, colour, alpha) in shaped:
                glColor4f(colour[0], colour[1], colour[2], alpha)
                glVertex3f(point[0], point[1], point[2])
            glEnd()
        # cores batched into one point list — cheap, and the additive halo has
        # already given each bolt its footprint
        if pts:
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            _gl.glPointSize(3.2)
            glBegin(GL_POINTS)
            for (x, y, z, cr, cg, cb) in pts:
                glColor4f(cr, cg, cb, 0.95)
                _gl.glVertex3f(x, y, z)
            glEnd()
        glDepthMask(True)
        glDisable(GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def _plane_point(self, pos, right, up, u, v):
        """World position for a camera-plane offset from `pos` (no GL matrix use)."""
        return (pos[0] + right[0] * u + up[0] * v,
                pos[1] + right[1] * u + up[1] * v,
                pos[2] + right[2] * u + up[2] * v)

    # ------------------------------------------------------------------ effects
    def _draw_effects(self):
        st = self.state
        # Effects are EMISSIVE — they must not be modulated by the scene
        # lighting. With GL_LIGHTING left on, additive glows get multiplied by
        # the (dark) lit surface under them and a detonation peaks at ~0.62
        # instead of white-hot, losing roughly half its brightness and area
        # (measured: blast pixels 1406 -> 2471 with lighting off).
        # Billboards here also carry no normals, so lighting only darkens them.
        import OpenGL.GL as GL
        GL.glDisable(GL.GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        for fx in st.effects[:400]:
            if not effect_visible(st, self.local_player, fx):
                continue
            kind = fx["kind"]
            t = fx.get("t", 0.0)
            pos = fx["pos"]
            color = fx.get("color", [1, 1, 1])
            if kind == "explosion":
                self._draw_explosion(pos, fx.get("size", 40), t,
                                     fx.get("seed", 0))
            elif kind == "explosion_small":
                a = max(0.0, 1.0 - t / 0.6)
                if a <= 0:
                    continue
                # scaled-down version of the full blast so small kills read as
                # the same phenomenon, not a different (orange blob) effect
                self._draw_explosion(pos, max(10.0, fx.get("size", 20)) * 0.5,
                                     t * 0.55, fx.get("seed", 3))
            elif kind in ("shield_hit", "hull_hit", "impact"):
                continue  # rendered after opaque hulls and the standing shell
            elif kind == "beam":
                a = max(0.0, 1.0 - t / 0.25)
                if a <= 0 or "target_pos" not in fx:
                    continue
                tgt = fx["target_pos"]
                # layered ribbon: wide soft sheath + hot narrow core. A single
                # 2.5px GL_LINES beam read as a hairline scratch; this gives
                # beam fire actual presence without any post-processing.
                self._beam_ribbon(pos, tgt, 9.0,
                                  (color[0] * 0.8, color[1] * 0.8, color[2] * 0.8,
                                   a * 0.5))
                self._beam_ribbon(pos, tgt, 3.0, (color[0], color[1], color[2], a))
                self._beam_ribbon(pos, tgt, 1.2,
                                  (min(1.0, color[0] + 0.5), min(1.0, color[1] + 0.5),
                                   min(1.0, color[2] + 0.5), a * 0.95))
                # glow at both ends of the beam
                self._draw_glow(pos, 14, color, alpha=a * 0.8, additive=True)
                if not fx.get("resolved_contact", False):
                    self._draw_glow(tgt, 8, color, alpha=a * 0.35, additive=True)
            elif kind in ("jump_charge", "jump_arrive", "jump_depart"):
                a = max(0.0, 1.0 - t / 1.0)
                self._bb_ring(pos, 60 + 160 * (1 - a),
                              (0.5, 0.7, 1.0, a * 0.8), 2.5)
            elif kind == "fire":
                a = max(0.0, 1.0 - t / 2.0)
                if a <= 0:
                    continue
                # flickering billboard flames on the burning hull
                sz = fx.get("size", 40)
                flick = 0.7 + 0.3 * math.sin(self.time * 23.0 + sz)
                self._draw_glow(pos, sz * 0.55 * flick, (1.0, 0.45, 0.15),
                                alpha=a * 0.55, additive=True)
                self._draw_glow(pos, sz * 0.3 * flick, (1.0, 0.8, 0.4),
                                alpha=a * 0.7, additive=True)
            elif kind == "muzzle":
                a = max(0.0, 1.0 - t / 0.15)
                if a > 0:
                    self._draw_glow(pos, 10, color, alpha=a * 0.85,
                                    additive=True)
            elif kind == "shield_down":
                a = max(0.0, 1.0 - t / 0.6)
                # billboard shimmer ring around the whole ship
                self._bb_ring(pos, fx.get("size", 60) * 1.3,
                              (0.5, 0.8, 1.0, a * 0.85), 2.5)
                self._draw_glow(pos, fx.get("size", 60), (0.5, 0.8, 1.0),
                                alpha=a * 0.4, additive=True)
            elif kind == "emp":
                a = max(0.0, 1.0 - t / 0.8)
                self._bb_ring(pos, 50 + 120 * (1 - a),
                              (0.6, 0.4, 1.0, a * 0.8), 3.0)
        glDepthMask(True)
        glDisable(GL_BLEND)
        GL.glEnable(GL.GL_LIGHTING)

    def _draw_hits(self):
        """Contact markings composite after hulls, not underneath their armor."""
        from render.hit_effects import draw_hit
        for fx in self.state.effects[:400]:
            if not effect_visible(self.state, self.local_player, fx):
                continue
            if fx["kind"] in ("shield_hit", "hull_hit", "impact"):
                visual_fx = self._visual_hit(fx)
                # A detected center does not imply its visual surface is sensed.
                if effect_visible(self.state, self.local_player, visual_fx):
                    draw_hit(self, visual_fx)

    # ------------------------------------------------------------------ explosions
    @staticmethod
    def _fx_ramp(age: float) -> tuple:
        """Fireball colour over its life: white-hot -> yellow -> orange -> red.

        A single fixed colour reads as a flat sticker. Ramping through the
        blackbody sequence is what makes a blast look like it is *cooling*.
        """
        stops = (
            (0.00, (1.00, 0.97, 0.88)),
            (0.16, (1.00, 0.88, 0.52)),
            (0.40, (1.00, 0.55, 0.16)),
            (0.70, (0.86, 0.26, 0.07)),
            (1.00, (0.44, 0.10, 0.04)),
        )
        a = max(0.0, min(1.0, age))
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if a <= t1:
                f = 0.0 if t1 <= t0 else (a - t0) / (t1 - t0)
                return (c0[0] + (c1[0] - c0[0]) * f,
                        c0[1] + (c1[1] - c0[1]) * f,
                        c0[2] + (c1[2] - c0[2]) * f)
        return stops[-1][1]

    def _fx_streak(self, pos, direction, length: float, width: float,
                   color4) -> None:
        """Camera-facing quad along `direction` — a glowing debris fragment.

        Discs read as soft puffs; a fragment needs a *directional* mark so the
        debris field looks thrown rather than sprayed.
        """
        d = normalize3(direction)
        if d[0] == 0.0 and d[1] == 0.0 and d[2] == 0.0:
            return
        cam = self.camera
        eye = cam.eye_position()
        view = (pos[0] - eye[0], pos[1] - eye[1], pos[2] - eye[2])
        px = d[1] * view[2] - d[2] * view[1]
        py = d[2] * view[0] - d[0] * view[2]
        pz = d[0] * view[1] - d[1] * view[0]
        plen = math.sqrt(px * px + py * py + pz * pz)
        if plen < 1e-6:
            return
        hw = width * 0.5
        px, py, pz = px / plen * hw, py / plen * hw, pz / plen * hw
        a = (pos[0] - d[0] * length * 0.5, pos[1] - d[1] * length * 0.5,
             pos[2] - d[2] * length * 0.5)
        b = (pos[0] + d[0] * length * 0.5, pos[1] + d[1] * length * 0.5,
             pos[2] + d[2] * length * 0.5)
        glDisable(GL_CULL_FACE)
        glColor4f(*color4)
        glBegin(GL_QUADS)
        glVertex3f(a[0] - px, a[1] - py, a[2] - pz)
        glVertex3f(b[0] - px, b[1] - py, b[2] - pz)
        glVertex3f(b[0] + px, b[1] + py, b[2] + pz)
        glVertex3f(a[0] + px, a[1] + py, a[2] + pz)
        glEnd()

    @staticmethod
    def _fx_ring(seed: int, phase: float, lobes: int, wobble: float,
                 n: int) -> list:
        """Precompute (radius_mult, brightness_jitter) around a circle, once.

        A radially symmetric fan is geometrically perfect, and a perfect circle
        reads as a DRAWN shape rather than as fire (measured on the real
        renderer: silhouette roughness 0.01 — literally a compass circle).
        Modulating the radius with a few shifted harmonics gives a churning,
        lumpy outline instead.

        Computing that per VERTEX cost ~2.9 ms per explosion (30 simultaneous
        blasts fell under 30 fps), because it is several sin() calls per vertex
        in Python. Precomputing one ring and having every shell index into it
        at a different offset cuts the trig by an order of magnitude while
        still giving each shell a differently-shaped silhouette.
        """
        out = []
        for i in range(n):
            a = i / n * 6.28318
            m = 1.0
            for k in range(lobes):
                ph = (((seed >> (k * 5)) & 0xFF) / 255.0) * 6.28318
                m += (wobble / (k + 1)) * math.sin(
                    (k + 2) * a + ph + phase * (0.6 + 0.35 * k))
            # per-angle brightness jitter: breaks the smooth radial ramp so the
            # cloud is mottled instead of an even gradient. Kept DELIBERATELY
            # SUBTLE (0.84..1.0): under additive blending a strong per-angle
            # swing renders as radial spokes/pinwheel, because adjacent vertices
            # differ in colour and the blend adds them as bands. The irregular
            # SILHOUETTE (m, above) is what should carry the shape — brightness
            # only mottles it.
            j = 1.0
            for k in range(3):
                ph = ((((seed + 13) >> (k * 5)) & 0xFF) / 255.0) * 6.28318
                j += (0.5 / (k + 1)) * math.sin(
                    (k + 2) * (a * 1.7 + 0.9) + ph
                    + phase * 1.69 * (0.6 + 0.35 * k))
            out.append((max(0.22, m), 0.84 + 0.16 * max(0.22, j) ** 0.5))
        return out

    @staticmethod
    def _ring_lookup(ring: list, i: int, rot: int):
        """Ring sample at angular index i, rotated by `rot` (wraps)."""
        return ring[(i + rot) % len(ring)]

    def _draw_glow_ring(self, pos, radius, color, alpha, ring, rot=0,
                        additive=True, inner=0.0, nrings=1) -> None:
        """Camera-facing billboard with an irregular silhouette from `ring`.

        `nrings` > 1 splits the billboard into nested lumpy contours with a
        radial alpha falloff. This matters MORE than the outline, and an
        outline-only fix is exactly what failed: a plain fan's brightest point
        is one shared centre vertex, so several overlapping shells pile up
        there and clip to a saturated flat plate (measured on a real frame:
        85% of bright pixels pinned at full white, 3,214 px of ONE colour).
        However lumpy the rim is, the eye lands on that white disc — which is
        what "still the same, I do not see any change" was looking at.

        `inner` > 0 starts the shape at that fraction of the radius, giving a
        lumpy RING with a soft inner edge, so the flash has no solid core.
        """
        if radius <= 0 or alpha <= 0:
            return
        cam = self.camera
        right, up, fwd = cam.basis()
        n = len(ring)
        bands = max(1, int(nrings))
        glBlendFunc(GL_SRC_ALPHA, GL_ONE if additive else GL_ONE_MINUS_SRC_ALPHA)
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        if inner <= 0.0 and bands == 1:
            # Plain blob: keep the single shared centre vertex. With a
            # GL_QUAD_STRIP the centre is duplicated once per angle, and each
            # copy carries that angle's brightness jitter, so neighbouring
            # wedges disagree at the middle and the puff renders as a pinwheel
            # of radial spokes. One centre vertex cannot disagree with itself.
            glBegin(GL_TRIANGLE_FAN)
            glColor4f(color[0], color[1], color[2], min(1.0, alpha))
            glVertex3f(0.0, 0.0, 0.0)
            for i in range(n + 1):
                m, j = self._ring_lookup(ring, i, rot)
                a = (i % n) / n * 6.28318
                ca, sa = math.cos(a), math.sin(a)
                glColor4f(color[0] * j, color[1] * j, color[2] * j, 0.0)
                glVertex3f((right[0] * ca + up[0] * sa) * radius * m,
                           (right[1] * ca + up[1] * sa) * radius * m,
                           (right[2] * ca + up[2] * sa) * radius * m)
            glEnd()
            glPopMatrix()
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            return
        r0 = radius * inner if inner > 0.0 else 0.0
        # One GL_QUAD_STRIP per band, with exactly TWO vertices per angle.
        #
        # A single strip carrying every band's vertices per angle does NOT
        # work: a quad strip joins CONSECUTIVE vertices, so it must alternate
        # between two curves. With 3 vertices per angle the strip runs
        # inner -> mid -> outer and then pairs outer(angle i) with
        # inner(angle i+1) — a quad spanning the entire band radially, which
        # renders as a dark radial SPOKE. One shock shell drawn alone produced
        # 12+ wedges and no ring at all; that pinwheel, not the shock colour,
        # was what made the blast look wrong.
        for k in range(bands):
            fa = k / bands
            fb = (k + 1) / bands

            def _band_alpha(f):
                if inner > 0.0:
                    return alpha * (4.0 * f * (1.0 - f)) ** 0.8   # soft both edges
                return alpha * (1.0 - f) ** 1.4              # blob: centre -> rim

            glBegin(GL_QUAD_STRIP)
            for i in range(n + 1):
                m, j = self._ring_lookup(ring, i, rot)
                a = (i % n) / n * 6.28318
                ca, sa = math.cos(a), math.sin(a)
                ix = (right[0] * ca + up[0] * sa)
                iy = (right[1] * ca + up[1] * sa)
                iz = (right[2] * ca + up[2] * sa)
                jr, jg, jb = color[0] * j, color[1] * j, color[2] * j
                for f in (fa, fb):
                    rr = r0 + (radius * m - r0) * f
                    glColor4f(jr, jg, jb, min(1.0, _band_alpha(f)))
                    glVertex3f(ix * rr, iy * rr, iz * rr)
            glEnd()
        glPopMatrix()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _draw_shock_shell(self, pos, radius, color, alpha, thickness, ring,
                          rot=0) -> None:
        """Irregular expanding annulus: a shock FRONT, not a drawn circle.

        Ramped from faint on the inside to bright at the leading edge, so the
        shell has a direction. The radius comes from an irregular ring — a true
        circle here was the single most artificial-looking part of the blast.
        """
        if radius <= 0 or alpha <= 0:
            return
        cam = self.camera
        right, up, fwd = cam.basis()
        n = len(ring)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDisable(GL_CULL_FACE)
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        # Two strips, TWO vertices per angle (see the note in
        # _draw_glow_ring): three vertices per angle makes a quad strip emit a
        # full-width radial quad per segment, which renders as dark spokes.
        glBegin(GL_QUAD_STRIP)
        for i in range(n + 1):
            m, _j = self._ring_lookup(ring, i, rot)
            a = (i % n) / n * 6.28318
            rm = radius * m
            ca, sa = math.cos(a), math.sin(a)
            ix = (right[0] * ca + up[0] * sa)
            iy = (right[1] * ca + up[1] * sa)
            iz = (right[2] * ca + up[2] * sa)
            inner = rm - thickness * m
            mid = inner + (rm - inner) * 0.55
            glColor4f(color[0], color[1], color[2], alpha * 0.13)
            glVertex3f(ix * inner, iy * inner, iz * inner)
            glColor4f(color[0], color[1], color[2], alpha * 0.55)
            glVertex3f(ix * mid, iy * mid, iz * mid)
        glEnd()
        glBegin(GL_QUAD_STRIP)
        for i in range(n + 1):
            m, _j = self._ring_lookup(ring, i, rot)
            a = (i % n) / n * 6.28318
            rm = radius * m
            ca, sa = math.cos(a), math.sin(a)
            ix = (right[0] * ca + up[0] * sa)
            iy = (right[1] * ca + up[1] * sa)
            iz = (right[2] * ca + up[2] * sa)
            inner = rm - thickness * m
            mid = inner + (rm - inner) * 0.55
            # The OUTER edge must fade to nothing. Ending the strip on a bright
            # vertex gives the shell a crisp outer contour, and a crisp contour
            # at this size reads as a drawn olive donut.
            glColor4f(color[0], color[1], color[2], alpha * 0.55)
            glVertex3f(ix * mid, iy * mid, iz * mid)
            glColor4f(color[0], color[1], color[2], alpha * 0.10)
            glVertex3f(ix * (rm + thickness * 0.85 * m),
                       iy * (rm + thickness * 0.85 * m),
                       iz * (rm + thickness * 0.85 * m))
        glEnd()
        glPopMatrix()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def _draw_explosion(self, pos, size: float, t: float, seed: int = 0) -> None:
        """Layered detonation, staged so the eye reads an EVENT.

        All of it derives from `t` and `seed`, so there is no per-particle
        state. The shapes are deliberately IRREGULAR: an earlier revision drew
        mathematically perfect circles (measured silhouette roughness 0.01)
        with a smooth symmetric core, which read as drawn graphics rather than
        as fire.

        Geometry comes from a few precomputed irregular rings rather than
        per-vertex trig, so a 30-blast battle stays realtime.
        """
        life = 1.5
        age = t / life
        if age >= 1.0:
            return
        r = max(16.0, float(size))
        h = (seed * 2654435761) & 0xFFFFFFFF

        def rnd(i: int) -> float:
            return (((h >> (i * 3)) ^ (i * 1103515245)) & 0xFFFF) / 65535.0

        spin = age * 3.4            # the fire churns as it expands

        # --- 1. flash: white-hot, only a few frames. This is the BRIGHTEST and
        # most-looked-at layer, so it must NOT be the smooth disc it used to be:
        # left as a plain _draw_glow it re-introduced exactly the perfect-circle
        # look the rest of this function was rewritten to remove (reported:
        # "still the same, I do not see any change"). It is drawn as a lumpy
        # RING (inner=0.4) rather than a blob so there is no solid saturated
        # core, and the alpha is deliberately below 1.0: overlapping additive
        # shells were clipping the centre to flat white.
        if age < 0.14:
            fa = 1.0 - age / 0.14
            self._draw_glow_ring(pos, r * (1.1 + 2.0 * age), (1.0, 1.0, 0.96),
                                 alpha=fa * 0.40,
                                 ring=self._fx_ring(seed + 900, spin, 4, 0.40, 26),
                                 rot=2, additive=True, nrings=3)

        # --- 2. fireball: several LUMPY shells instead of one smooth disc, so
        # the silhouette is turbulent and the interior mottled. One ring is
        # built and every shell reads it at a different rotation, so the shells
        # disagree on shape without paying for 5 separate trig sweeps.
        cool = self._fx_ramp(age / 0.85)
        fade = max(0.0, 1.0 - age) ** 1.25
        grow = r * (0.90 + 2.10 * age ** 0.5)
        ring_big = self._fx_ring(seed, spin, 5, 0.34, 34)
        for i in range(7):
            ang = (i / 7.0) * 6.28318 + rnd(i) * 1.3 + spin * 0.5
            off = r * (0.20 + 0.30 * rnd(10 + i)) * (0.4 + age)
            self._draw_glow_ring(
                (pos[0] + math.cos(ang) * off,
                 pos[1] + (rnd(30 + i) - 0.5) * off,
                 pos[2] + math.sin(ang) * off),
                grow * (0.55 + 0.42 * rnd(20 + i)), cool,
                alpha=0.16 * fade, ring=ring_big, rot=i * 7)
        ring_mid = self._fx_ring(seed + 77, -spin * 0.8, 4, 0.26, 26)
        if age < 0.75:                                   # mid, hotter shell
            hot = max(0.0, 1.0 - age / 0.75)
            self._draw_glow_ring(pos, r * (0.50 + 1.30 * age ** 0.6),
                                 (1.0, 0.70 + 0.28 * hot, 0.28 + 0.35 * hot),
                                 alpha=0.34 * hot ** 1.1, ring=ring_mid, rot=3)
        ring_core = self._fx_ring(seed + 99, spin * 1.4, 3, 0.18, 18)
        if age < 0.30:                                   # white-hot core
            hc = 1.0 - age / 0.30
            self._draw_glow_ring(pos, r * (0.35 + 0.75 * hc), (1.0, 0.98, 0.92),
                                 alpha=0.34 * hc, ring=ring_core, rot=1)

        # --- 3. shock front: irregular, faint and SHORT-LIVED. Deliberately
        # kept subordinate to the fire — a large crisp ring was what made the
        # blast read as a drawn circle. Tuned against a STATION-scale blast
        # (size 300), where the old parameters produced a ~560 px radius torus
        # with a 165 px band: an unmistakable khaki donut dominating the frame.
        # A pressure front should be a thin, faint ripple, so both the band and
        # the peak opacity are much smaller than the fireball's.
        if age < 0.34:
            sa = age / 0.34
            self._draw_shock_shell(
                pos, r * (1.10 + 1.30 * sa ** 0.62),
                (1.0, 0.88, 0.70), (1.0 - sa) ** 2.2 * 0.20, r * 0.22,
                ring=self._fx_ring(seed + 5, sa * 2.2, 4, 0.34, 40))

        # --- 4. smoke: many faint, large, overlapping puffs. Fewer/stronger
        # puffs composite into a single grey mass with its own visible
        # boundary, which reads as a sticker; low-alpha and heavily overlapped
        # it reads as haze instead.
        if age > 0.08:
            sm = min(1.0, (age - 0.08) / 0.35)
            sfade = max(0.0, 1.0 - max(0.0, (age - 0.40) / 0.60))
            smoke = tuple(c * 0.10 for c in cool)
            # n=48/wobble=0.16, not n=20/0.30: a coarse ring renders as a
            # jagged star with visible facets, and because it is a big dark
            # additive-less mass the facets read as radial spokes/pinwheel
            # around the fireball. Verified by drawing this layer alone.
            ring_sm = self._fx_ring(seed + 40, age * 1.6, 4, 0.18, 28)
            for k in range(9):
                ang = (k / 9.0) * 6.28318 + rnd(k) * 1.4
                # sqrt spreads the puffs over the DISC. A linear spread crowds
                # them into an annulus, which leaves a hole at the centre and
                # renders as a dark smoke RING around the fire — plainly
                # visible on a station-scale blast.
                spread = math.sqrt(0.05 + 0.95 * rnd(10 + k))
                drift = r * (0.9 + 2.8 * age) * spread
                self._draw_glow_ring(
                    (pos[0] + math.cos(ang) * drift * 0.9,
                     pos[1] + r * 0.45 * age + drift * 0.25,
                     pos[2] + math.sin(ang) * drift * 0.9),
                    r * (0.95 + 2.1 * age) * (0.70 + 0.60 * rnd(20 + k)),
                    smoke, alpha=0.13 * sm * sfade,
                    ring=ring_sm, rot=k * 3, additive=False)

        # --- 5. embers and debris thrown on ballistic arcs
        if age < 0.95:
            ea = max(0.0, 1.0 - age / 0.95)
            n = 18
            ring_deb = self._fx_ring(seed + 200, spin * 2.0, 3, 0.45, 12)
            col_ember = self._fx_ramp(min(1.0, age * 1.5 + 0.25))
            for i in range(n):
                ang = (i / n) * 6.28318 + rnd(i) * 0.9
                elev = (rnd(60 + i) - 0.5) * 1.1
                sp = r * (1.1 + 4.2 * age) * (0.55 + 0.9 * rnd(40 + i))
                vel = (math.cos(ang) * math.cos(elev),
                       math.sin(elev),
                       math.sin(ang) * math.cos(elev))
                p = (pos[0] + vel[0] * sp, pos[1] + vel[1] * sp,
                     pos[2] + vel[2] * sp)
                big = i % 4 == 0        # a few real fragments, not just sparks
                self._draw_glow_ring(
                    p,
                    (4.0 + 7.0 * rnd(80 + i)) * (0.4 + ea) * (1.8 if big else 1.0),
                    col_ember, alpha=0.80 * ea, ring=ring_deb, rot=i)
                if (big or i % 3 == 0) and ea > 0.30 and sp > r * 1.4:
                    self._fx_streak((p[0] + vel[0] * r * 0.30,
                                     p[1] + vel[1] * r * 0.30,
                                     p[2] + vel[2] * r * 0.30),
                                    vel, r * 0.65 * (0.5 + ea), 2.2,
                                    (col_ember[0], col_ember[1], col_ember[2],
                                     0.40 * ea))

        # --- 6. secondaries: staggered pops inside the fireball
        for k in range(3):
            t0 = 0.14 + 0.13 * k + 0.10 * rnd(k)
            if 0.0 <= (age - t0) < 0.24:
                sub = (age - t0) / 0.24
                ang = rnd(70 + k) * 6.28318
                off = r * 0.75 * (0.4 + rnd(90 + k))
                self._draw_glow_ring(
                    (pos[0] + math.cos(ang) * off,
                     pos[1] + (rnd(100 + k) - 0.5) * off * 0.6,
                     pos[2] + math.sin(ang) * off),
                    r * (0.35 + 0.80 * sub), self._fx_ramp(sub),
                    alpha=0.85 * (1.0 - sub),
                    ring=self._fx_ring(seed + 300 + k, sub * 3.0, 4, 0.38, 22),
                    rot=k * 5)

    def _beam_ribbon(self, a, b, width: float, color4) -> None:
        """Camera-facing quad from `a` to `b` — a beam with real thickness.

        A GL_LINES beam is one pixel wide no matter how close the camera is,
        so capital-ship fire reads as a hairline scratch. This builds a quad
        in the billboard plane: the perpendicular offset is the beam axis
        crossed with the eye vector, so the ribbon always faces the camera
        and keeps its width at any angle.
        """
        if not self._in_front(a, 1.0) and not self._in_front(b, 1.0):
            return
        import OpenGL.GL as GL
        cam = self.camera
        eye = cam.eye_position()
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
        axis = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        alen = math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2)
        if alen < 1e-6:
            return
        axis = (axis[0] / alen, axis[1] / alen, axis[2] / alen)
        view = (mid[0] - eye[0], mid[1] - eye[1], mid[2] - eye[2])
        # perpendicular = axis x view, normalised
        px = axis[1] * view[2] - axis[2] * view[1]
        py = axis[2] * view[0] - axis[0] * view[2]
        pz = axis[0] * view[1] - axis[1] * view[0]
        plen = math.sqrt(px * px + py * py + pz * pz)
        if plen < 1e-6:
            return
        hw = width * 0.5
        px, py, pz = px / plen * hw, py / plen * hw, pz / plen * hw
        GL.glDisable(GL.GL_CULL_FACE)
        glColor4f(*color4)
        glBegin(GL_QUADS)
        glVertex3f(a[0] - px, a[1] - py, a[2] - pz)
        glVertex3f(b[0] - px, b[1] - py, b[2] - pz)
        glVertex3f(b[0] + px, b[1] + py, b[2] + pz)
        glVertex3f(a[0] + px, a[1] + py, a[2] + pz)
        glEnd()

    def _bb_ring(self, pos, radius, color4, width=2.0):
        """Camera-facing ring billboard (billboard-plane line loop)."""
        if radius <= 0 or not self._in_front(pos, radius):
            return
        right, up, fwd = self.camera.basis()
        glLineWidth(width)
        glColor4f(*color4)
        glBegin(GL_LINE_LOOP)
        for i in range(28):
            a = i / 28 * 2 * math.pi
            ca, sa = math.cos(a), math.sin(a)
            glVertex3f(pos[0] + (right[0] * ca + up[0] * sa) * radius,
                       pos[1] + (right[1] * ca + up[1] * sa) * radius,
                       pos[2] + (right[2] * ca + up[2] * sa) * radius)
        glEnd()

    def _flat_ring(self, pos, radius):
        if not self._in_front(pos, radius):
            return
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, 0)
        segments = 20
        for i in range(segments + 1):
            a = i / segments * 2 * math.pi
            glVertex3f(math.sin(a) * radius, 0, math.cos(a) * radius)
        glEnd()
        glPopMatrix()

    # ------------------------------------------------------------------ overlays
    # ---------------------------------------------------------------- shields
    def _shield_shell_list(self, bucket: int = 8, detail: str = "high") -> int:
        """Unit shell for shield bubbles, with the rim glow BAKED IN.

        Fixed-function GL cannot evaluate a Fresnel term per fragment, and a
        plain specular highlight lands wherever the normal bisects light and
        view — a sun-glint on a ball, not the bright limb the reference art
        shows. So the shell is built VIEW-ALIGNED: local +Z always points at
        the camera, which makes the grazing angle a pure function of latitude.
        The rim falloff is then baked into per-vertex alpha here, once, with
        no per-frame CPU cost (a per-vertex CPU Fresnel would be ~3.6k
        vertices per shielded ship, every frame).

        Because the shell is view-aligned it is also CAMERA- AND YAW-
        INDEPENDENT, so exactly one list per strength bucket is needed for the
        whole game. Keying it on ship yaw (as an earlier revision did) would
        allocate a fresh 3.2k-vertex list for every heading a ship turned
        through — an unbounded GL memory leak.

        Only the camera-facing hemisphere is emitted (see the geometry loop);
        the shell is additive and its rim lands at the shared silhouette, so
        the far half would only duplicate pixels at twice the cost.

        `bucket` (1..8) is the shield-strength level. Vertex colours in a
        display list are fixed, so strength cannot be applied at draw time —
        instead one list is cached per strength octant. That is 8 lists total
        built lazily, giving a real visual read of shield strength (and
        avoiding the alternative of emitting ~3.2k vertices per ship per
        frame in immediate mode).

        Per-quadrant state is NOT baked here: the sector of the bubble facing
        a given quadrant moves with the ship's heading AND the camera, so
        baking it would reintroduce the unbounded cache above. Quadrant
        damage is shown by the transient hit flash instead (see
        `_shield_quadrant_glow`).
        """
        bucket = max(1, min(8, int(bucket)))
        key = f"shield_shell:{bucket}:{detail}"
        cached = self.ship_lists.get(key)
        if cached is not None:
            return cached
        import OpenGL.GL as GL
        strength = bucket / 8.0
        # Colour comes from the FULL strength range; alpha does not. A field
        # that fades linearly to nothing spends its last, most urgent quarter
        # (red) below the visibility threshold, so the warning colour would
        # never actually be seen. The ramp supplies hue, and alpha is floored
        # so red stays legible right up to the bubble vanishing at zero.
        cr, cg, cb = shield_color(strength)
        _a_lo, _a_hi = 0.20, 0.65
        fade = _a_lo + (_a_hi - _a_lo) * strength
        # Base interior alpha. The camera-facing hemisphere contributes this
        # once; it is set so the bubble keeps the soft blue wash of the
        # reference art rather than reading as an empty outline. The limb term
        # dominates at the silhouette, which is where the eye reads the rim.
        BASE_A = 0.001
        lst = _gl.glGenLists(1)
        glNewList(lst, GL_COMPILE)
        GL.glPushAttrib(int(GL.GL_ENABLE_BIT))
        GL.glDisable(GL.GL_CULL_FACE)   # two-sided, like every other hull pass
        # The shell is additive and symmetric about the camera axis, so only
        # the camera-facing hemisphere is emitted. The rim glow sits exactly at
        # the silhouette (lat = 90 deg), which is shared by both hemispheres;
        # the far half would add identical pixels at twice the vertex cost.
        # Halving the geometry here is what makes the pass affordable in a
        # large battle (~150 shielded units).
        lons, lats = {"low": (20, 5), "medium": (30, 8), "high": (40, 10)}.get(detail, (40, 10))
        for i in range(lons):
            lon0 = 2 * math.pi * i / lons
            lon1 = 2 * math.pi * (i + 1) / lons

            def vert(lon, lat):
                return (math.sin(lat) * math.sin(lon),
                        math.sin(lat) * math.cos(lon),
                        math.cos(lat))

            def shade(lat, lon):
                graze = 1.0 - abs(math.cos(lat))
                a = (BASE_A + 0.18 * (graze ** 2.0)) * fade
                # Slight whitening toward the limb (a real field scatters
                # harder where the view grazes it) — but DELIBERATELY CAPPED.
                # An uncapped white mix drives the rim to pure white, which is
                # the brightest part of the bubble and therefore the part the
                # eye reads: the strength colour would be washed out precisely
                # where it matters. At 0.45 the limb keeps its hue while still
                # looking brighter than the body.
                t = 0.18 * (graze ** 3.0)
                glColor4f(cr + (1.0 - cr) * t, cg + (1.0 - cg) * t,
                          cb + (1.0 - cb) * t, min(1.0, a))

            # One quad strip per longitude column: adjacent cells share their
            # edge vertices, where two triangles would emit 6 vertices per cell
            # (4 unique) — 33% fewer vertices for identical pixels.
            glBegin(GL_QUAD_STRIP)
            for j in range(lats + 1):
                lat = math.pi * 0.5 * j / lats
                shade(lat, lon0)
                glVertex3f(*vert(lon0, lat))
                shade(lat, lon1)
                glVertex3f(*vert(lon1, lat))
            glEnd()
        GL.glPopAttrib()
        glEndList()
        self.ship_lists[key] = lst
        return lst

    def _camera_basis(self):
        """(right, up, toward_eye) unit vectors for the current camera."""
        right, up, fwd = self.camera.basis()
        toward_eye = (-fwd[0], -fwd[1], -fwd[2])
        return right, up, toward_eye

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
            faction, data_id = normalize_station_key(e.data_id, owner_faction(getattr(self, "state", None), e.owner))
            if faction != "imperial" or is_authored(f"{faction}:{data_id}"):
                r = self._station_visual_radius(e) * 1.08
        ppw = self._px_per_world((e.pos.x, e.pos.y, e.pos.z))
        if ppw > 0.0:
            want_r = SHIELD_MIN_PX * 0.5 / ppw
            if want_r > r:
                r = want_r
        return r

    def _shield_bubble(self, e, frac: float, cache=None) -> None:
        """Additive energy bubble scaled by remaining shield strength.

        Depth writes are off: the bubble must never occlude the ship inside
        it, and two additive translucent shells writing depth fight each
        other. It is drawn after the hull pass so the ship reads through it.
        """
        if frac <= 0.0:
            return
        # Readability floor (spec §35, same rule the hull pass applies to ship
        # scale): at tactical zoom a distant bubble shrinks until only its rim
        # is resolved and it degenerates back into the flat outline circle this
        # pass exists to replace. Grow it until the shell is at least
        # SHIELD_MIN_PX across so it still reads as a volume.
        if cache is not None:
            entry = cache.get(e.id)
            if entry is None:
                return
            r = entry["shield_radius"]
            pos = entry["pos"]
            ppw = entry["ppw_camera"]
            in_front = entry["in_front"]
        else:
            pos = (e.pos.x, e.pos.y, e.pos.z)
            ppw = self._px_per_world(pos)
            r = self._shield_radius(e)
            in_front = self._in_front(pos, r)
        if ppw > 0.0:
            want_r = SHIELD_MIN_PX * 0.5 / ppw
            if want_r > r:
                r = want_r
        if not in_front:
            return
        right, up, toward_eye = (cache["basis"][0], cache["basis"][1], cache["toward_eye"]) if cache else self._camera_basis()
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        # orient the shell so its baked +Z axis points at the camera
        _gl.glMultMatrixf([right[0], right[1], right[2], 0.0,
                           up[0], up[1], up[2], 0.0,
                           toward_eye[0], toward_eye[1], toward_eye[2], 0.0,
                           0.0, 0.0, 0.0, 1.0])
        glScalef(r, r, r)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)          # additive: pure emission
        glDepthMask(False)
        bucket = max(1, min(8, int(round(frac * 8.0))))
        # Pick a coarser shell for small on-screen bubbles; the rim still reads
        # at the same silhouette and the player gets the same strength cue.
        if cache is not None:
            entry = cache.get(e.id)
            apparent = entry.get("apparent", 0.0) if entry else 0.0
        else:
            apparent = self._px_per_world((e.pos.x, e.pos.y, e.pos.z)) * e.radius * 2.0
        if apparent < 20.0:
            detail = "low"
        elif apparent < 40.0:
            detail = "medium"
        else:
            detail = "high"
        glCallList(self._shield_shell_list(bucket, detail))
        glDepthMask(True)
        glDisable(GL_BLEND)
        glPopMatrix()

    def _shield_quadrant_glow(self, e, frac: float, q: str, strength: float):
        """Flash on the bubble facing the quadrant that just took a hit."""
        yaw = e.yaw
        s, c = math.sin(yaw), math.cos(yaw)
        r = self._shield_radius(e)
        # forward in model space is +Z (matches the renderer's +yaw rotation);
        # engine glow/trail use the negated pair for "behind"
        dirs = {
            "front": (s, 0.0, c),
            "rear": (-s, 0.0, -c),
            "left": (c, 0.0, -s),
            "right": (-c, 0.0, s),
        }
        d = dirs.get(q)
        if d is None:
            return
        p = (e.pos.x + d[0] * r * 0.92, e.pos.y + d[1] * r * 0.92,
             e.pos.z + d[2] * r * 0.92)
        # Flash in the field's own colour, pushed toward white so a hit reads as
        # a bright impact regardless of how depleted the bubble is.
        col = shield_color(max(0.0, min(1.0, frac)))
        self._draw_glow(p, r * 0.62,
                        (col[0] * 0.45 + 0.55, col[1] * 0.45 + 0.55,
                         col[2] * 0.45 + 0.55),
                        alpha=strength * 0.5 * frac, additive=True)

    def _px_per_world(self, pos, *, camera_depth=False) -> float:
        """Screen pixels per world unit at `pos` (0.0 if behind the camera)."""
        if not self._in_front(pos, 0.0):
            return 0.0
        scope = getattr(self, '_draw_view', None)
        if scope is None:
            eye = self.camera.eye_position()
        else:
            eye, (_, _, forward) = self._draw_view_geometry()
        if camera_depth:
            # Ship LOD must agree at equal camera depth, including off-axis hulls.
            if scope is None:
                _, _, forward = self.camera.basis()
            dist = sum((pos[i]-eye[i])*forward[i] for i in range(3))
        else:
            # Preserve the existing station/planet/general-effects appearance.
            dist = math.sqrt(sum((pos[i]-eye[i])**2 for i in range(3)))
        if dist <= 1e-6:
            return 0.0
        if scope is None:
            return self.camera.height / (
                2.0 * dist * math.tan(math.radians(self.camera.fov / 2)))
        if 'projection' not in scope:
            scope['projection'] = (self.camera.height,
                math.tan(math.radians(self.camera.fov / 2)))
        height, tangent = scope['projection']
        # Keep the live formula's exact multiplication/division order. The
        # older _px_per_world_cached's px_scale / dist is NOT equivalent.
        return height / (2.0 * dist * tangent)

    # ------------------------------------------------------------ planet shields
    def _draw_planet_shields(self, dt: float) -> None:
        """Translucent surface-shield field over a colonized world.

        An operational `planet_shield_generator` raises a real damage-absorbing
        field in the sim (its quadrant pools eat hits on the planet's surface
        hardware) but nothing was drawn for it — reported as "planet shields are
        not visible". The shell is the same view-aligned unit sphere the ship
        bubbles use, scaled to the world: additive, depth-tested, no depth
        writes, so it never hides the hardware inside it.
        """
        from render.planet_building_geometry import planet_shield_fields
        st = self.state
        import OpenGL.GL as GL
        fields = planet_shield_fields(st)
        if not fields:
            return
        drawn = False
        for e in known_entities(st, self.local_player):
            if not e.alive or not e.is_planet or e.data_id == "asteroid_field":
                continue
            generator, strength, radius = fields.get(e.id, (None, 0.0, 0.0))
            if generator is None or strength <= 0.0:
                continue
            # Detection of the generator gates the field, like every other
            # contact cue; a hidden world's shield is not a licence to see it.
            if not st.can_see(self.local_player, generator.id):
                continue
            if not drawn:
                GL.glPushAttrib(int(GL.GL_ENABLE_BIT) | int(GL.GL_CURRENT_BIT) |
                                int(GL.GL_LIGHTING_BIT))
                GL.glDisable(GL.GL_LIGHTING)     # shell carries its own baked light
                GL.glDisable(GL.GL_TEXTURE_2D)
                glEnable(GL_DEPTH_TEST)
                drawn = True
            self._planet_shield_dome(e, generator, radius, strength, dt)
        if drawn:
            GL.glPopAttrib()
        # bounded caches: a campaign can retire and recolonize many worlds
        if len(self._planet_shield_prev) > 64:
            live = {e.id for e in st.entities.values() if e.is_planet}
            for key in [k for k in self._planet_shield_prev if k not in live]:
                self._planet_shield_prev.pop(key, None)
                self._planet_shield_flash.pop(key, None)

    def _planet_shield_dome(self, planet, generator, radius: float,
                            strength: float, dt: float) -> None:
        """One additive shell above the world, pulsed while it absorbs."""
        total = generator.total_shield()
        old = self._planet_shield_prev.get(planet.id)
        if old is not None and total < old - 1e-6:
            self._planet_shield_flash[planet.id] = 1.0
        self._planet_shield_prev[planet.id] = total
        flash = self._planet_shield_flash.get(planet.id, 0.0)
        if flash > 0.0:
            flash = max(0.0, flash - dt * 3.0)
            self._planet_shield_flash[planet.id] = flash
        pos = (planet.pos.x, planet.pos.y, planet.pos.z)
        if not self._in_front(pos, radius):
            return
        right, up, toward_eye = self._camera_basis()
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        _gl.glMultMatrixf([right[0], right[1], right[2], 0.0,
                           up[0], up[1], up[2], 0.0,
                           toward_eye[0], toward_eye[1], toward_eye[2], 0.0,
                           0.0, 0.0, 0.0, 1.0])
        glScalef(radius, radius, radius)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)          # additive: pure emission
        glDepthMask(False)
        bucket = max(1, min(8, int(round(strength * 8.0))))
        # Strength is baked into the shared shell's vertex colours, so a hit is
        # shown by re-adding the emission (1..2 extra passes) rather than by
        # tinting at draw time, which a display list cannot do. The localized
        # contact itself is the curved `shield_hit` effect the sim spawns on the
        # surface hardware that absorbed the damage.
        for _ in range(1 + int(round(flash * 2.0))):
            glCallList(self._shield_shell_list(bucket))
        glDepthMask(True)
        glDisable(GL_BLEND)
        glPopMatrix()

    def _draw_shields(self, units, dt: float, cache=None) -> None:
        """Shield bubbles for every unit that has shields worth showing.

        Reads the four per-quadrant values the sim already tracks
        (front/rear/left/right) — previously only visible as four small bars
        in the side panel. Strength is the mean quadrant fraction, and a
        quadrant that loses shields flashes on that FACE of the bubble, so
        the mechanic is readable in the 3D view for the first time.
        """
        st = self.state
        import OpenGL.GL as GL
        prev = self._prev_shields
        flash = self._shield_flash
        GL.glPushAttrib(int(GL.GL_ENABLE_BIT) | int(GL.GL_CURRENT_BIT) |
                        int(GL.GL_LIGHTING_BIT))
        GL.glDisable(GL.GL_LIGHTING)      # the shell carries its own baked light
        GL.glDisable(GL.GL_TEXTURE_2D)
        glEnable(GL_DEPTH_TEST)
        for e in units:
            if not e.alive or e.is_planet:
                continue
            # Generator pools protect surface hardware only; an exterior bubble
            # would falsely advertise protection for orbiting ships/satellites.
            if e.planet_building_slot is not None:
                continue
            if e.max_shield_total() <= 0:
                continue
            quads = {q: e.shields.get(q, 0.0) for q in QUADRANTS}
            frac = (sum(quads.values()) / e.max_shield_total())
            if frac <= 0.001:
                flash.pop(e.id, None)
                prev[e.id] = quads
                continue
            # detect shield loss per quadrant -> raise a flash on that face
            old = prev.get(e.id)
            if old is not None:
                for q, v in quads.items():
                    if v < old.get(q, v) - 1e-6:
                        flash.setdefault(e.id, {})[q] = 1.0
            for q in list(flash.get(e.id, {})):
                f = flash[e.id][q] - dt * 3.0
                if f <= 0.0:
                    flash[e.id].pop(q, None)
                else:
                    flash[e.id][q] = f
            prev[e.id] = quads
            self._shield_bubble(e, frac, cache)
            # Damage-resolved shield_hit effects render localized curved contacts.
            # Never layer the old radius-sized additive quadrant billboard over them.
        # drop cache entries for units that no longer exist
        if len(prev) > 512:
            live = {e.id for e in st.entities.values()}
            for eid in [k for k in prev if k not in live]:
                prev.pop(eid, None)
                flash.pop(eid, None)
        glDisable(GL_DEPTH_TEST)
        GL.glPopAttrib()

    def _draw_selection_rings(self, selection: set, cache=None):
        if not selection:
            return
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        for eid in selection:
            e = self.state.known_entity(self.local_player, eid)
            if e is None or not e.alive:
                continue
            if e.planet_building_slot is not None:
                self._draw_surface_selection(e)
                continue
            p = self.state.players.get(e.owner)
            col = p.color if p else (1, 1, 1)
            # hull fraction coloring
            hf = e.hull_fraction()
            if hf < 0.35:
                col = (1.0, 0.25, 0.2)
            elif hf < 0.7:
                col = (1.0, 0.8, 0.25)
            glPushMatrix()
            glTranslatef(e.pos.x, e.pos.y, e.pos.z)
            # Ship circles live in the same XZ plane as their hull footprint.
            # Preserve the committed orientation for stations/planet markers.
            if e.is_station or not (e.is_ship or e.is_squadron):
                glRotatef(-90, 1, 0, 0)
            glColor4f(col[0], col[1], col[2], 0.9)
            glLineWidth(2.0)
            # A shielded unit draws its shield shell at radius * 1.35, which is
            # exactly where this ring used to sit — the two coincided and the
            # crisp outline cut across the soft bubble's rim. Keep the ring, but
            # tuck it inside the bubble so the two read as separate cues.
            shielded = (not e.is_planet) and e.max_shield_total() > 0 \
                and e.total_shield() > 0
            visual_radius = (cache.get(e.id, {}).get("shield_radius")
                             if (cache is not None and not e.is_station and (e.is_ship or e.is_squadron))
                             else cache.get(e.id, {}).get("visual_radius")
                             if (cache is not None and e.is_station)
                             else self._ship_size(e).radius
                             if (not e.is_station and (e.is_ship or e.is_squadron))
                             else self._station_visual_radius(e) if e.is_station else e.radius)
            r = visual_radius * (1.1 if shielded else (1.35 if not e.is_planet else 1.1))
            if not shielded:
                glBegin(GL_LINE_LOOP)
                for i in range(28):
                    a = i / 28 * 2 * math.pi
                    glVertex3f(math.sin(a) * r, 0, math.cos(a) * r)
                glEnd()
            glPopMatrix()
        # Health arcs removed: the flat outline ring and the two half-circle
        # arcs were unreadable clutter that the bubble now supersedes —
        # the bubble shows shield strength directly (colour ramp + fade), and
        # the side panel still shows exact hull/shield figures for the selected
        # unit. A selected shieldless unit keeps its outline ring as before.
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)

    def _draw_floating_texts(self):
        """Sim floating texts (e.g. build rejections) as screen-space labels.

        The renderer is the only place with a camera; project each text's
        world position to screen coords, collect them, and let the HUD blit
        them onto its overlay (2D, crisp fonts). HUD must have been wired
        with set_camera_ref() — otherwise skip silently.
        """
        # HUD consumes them via floating_texts_screen() (see hud.py); kept as
        # a no-op here so the sim's list never renders in GL.
        pass

    def floating_texts_screen(self) -> list:
        """Project live floating texts to [(x, y, text, rgb, alpha), ...]."""
        out = []
        for ft in self.state.floating_texts:
            if not self.state.is_position_visible(self.local_player, position(ft["pos"])):
                continue
            t = ft.get("t", 0.0)
            life = 2.2
            a = max(0.0, 1.0 - t / life)
            if a <= 0:
                continue
            pos = ft["pos"]
            get = pos.get if isinstance(pos, dict) else (lambda k, i=None: pos[i])
            sp = self.camera.world_to_screen(get("x", 0), get("y", 1), get("z", 2))
            if sp is None:
                continue
            col = ft.get("color", (1, 1, 1))
            rgb = (int(col[0] * 255) if col[0] <= 1 else int(col[0]),
                   int(col[1] * 255) if col[1] <= 1 else int(col[1]),
                   int(col[2] * 255) if col[2] <= 1 else int(col[2]))
            out.append((int(sp[0]), int(sp[1]), ft.get("text", ""), rgb, a))
        return out


PLANET_COLORS = {
    "temperate": (0.30, 0.60, 0.95),
    "industrial": (0.65, 0.55, 0.40),
    "agricultural": (0.45, 0.75, 0.45),
    "military": (0.70, 0.40, 0.40),
    "gas_giant": (0.80, 0.65, 0.50),
    "research": (0.60, 0.50, 0.85),
    "barren": (0.55, 0.55, 0.60),
    "trade": (0.85, 0.75, 0.50),
}


# The authored asteroid prop's per-role tint, relative to the instance's own rock colour: the field's
# palette variety still comes from `base`, and the roles only split light from shadow from mineral.
ASTEROID_ROLE_TINTS = (('base', 1.00), ('dark', 0.58), ('trim', 1.26),
                       ('accent', 0.90), ('lit', 1.38), ('cool', 1.02))


def rock_params(s, rng):
    """The RNG-drawn parameters of one asteroid, taken before either drawing path branches.

    Module level on purpose: it is pure RNG and arithmetic, so a guard can drive it without a GL
    context and assert that both paths consume the identical stream. The draw order and the draw
    count are the legacy ones exactly - three for the instance colour, one for the sub-rock count,
    then per sub-rock three jitters, one only for the first sub-rock's size, eight corner radii and
    six bulge radii - so the field's layout is unchanged by which path draws.
    """
    base = (0.52 + rng.uniform(-0.08, 0.08),
            0.48 + rng.uniform(-0.08, 0.06),
            0.42 + rng.uniform(-0.06, 0.06))
    m = rng.randint(2, 4)
    subs = []
    for k in range(m):
        jx = rng.uniform(-0.25, 0.25) * s
        jy = rng.uniform(-0.18, 0.18) * s
        jz = rng.uniform(-0.25, 0.25) * s
        ss = s * (0.55 if k else rng.uniform(0.6, 0.8))
        radii = [rng.uniform(0.75, 1.25) for _ in range(8)]
        radii += [rng.uniform(0.9, 1.3) for _ in range(6)]
        subs.append((jx, jy, jz, ss, radii))
    return base, subs


def field_placement(radius, rng):
    """One asteroid's placement, from the field's own seeded stream - the legacy sequence unchanged.

    Angle, radius, height, size, then the tumble phase as its own draw: six draws, in the order the
    field has always drawn them, and *one instance at a time* because the loop alternates this with
    the rock's own draws. Keeping it a pure function of `radius` and an RNG is what lets a guard prove
    that the layout is identical whichever drawing path the rock takes - the placement cannot see
    which one it is.
    """
    a = rng.uniform(0, 2 * math.pi)
    r = radius * (0.15 + 0.85 * math.sqrt(rng.random()))
    x = math.sin(a) * r
    z = math.cos(a) * r
    y = rng.uniform(-60, 60)
    s = rng.uniform(12, 46)
    return (x, y, z, s, rng.uniform(0.4, 1.6) + rng.uniform(0, 360))
