"""Main renderer: draws the world from GameState (pure view — never mutates sim).

Immediate-mode modern-ish GL (fixed pipeline for prototype clarity). Ship meshes
are cached display lists per (shape, owner-color) template; effects are pooled
quads; scale LOD keeps distant fleets readable.
"""
from __future__ import annotations

import math
import os
import random

import pygame

from OpenGL.GL import (
    glBegin, glBlendFunc, glClear, glCallList, glColor3f, glColor4f,
    glDepthMask, glDisable, glEnable, glEnd, glEndList, glFlush, glLineWidth,
    glMatrixMode, glNewList, glNormal3f, glPopAttrib, glPopMatrix,
    glPushMatrix, glRotatef, glScalef, glTexCoord2f, glTranslatef, glVertex3f,
    glBindTexture, GL_BLEND, GL_CULL_FACE, GL_COLOR_BUFFER_BIT, GL_COMPILE,
    GL_CURRENT_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_LINE_LOOP,
    GL_LINE_STRIP, GL_LINES, GL_MODELVIEW, GL_ONE, GL_ONE_MINUS_SRC_ALPHA,
    GL_POINTS, GL_QUADS, GL_SRC_ALPHA, GL_TEXTURE_2D, GL_TRANSFORM_BIT,
    GL_TRIANGLES, GL_TRIANGLE_FAN,
)
import OpenGL.GL as _gl

from render.camera import cross3, normalize3
from render import textures as tex

from game.core.entity import Entity
from game.core.vectors import Vec3
from game.data.store import DataStore

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
        self.state = state
        self.camera = camera
        self.ds = DataStore.get()
        self.starfield = make_starfield()
        self.ship_lists: dict = {}       # (shape, scale, colorkey) -> display list id
        self._star_list = None
        self.time = 0.0
        # debug isolation: STAR_ARMADA_SKIP=nebulas,star,planets,ships,... skips passes
        self.skip = {s for s in os.environ.get("STAR_ARMADA_SKIP", "").split(",") if s}
        self._planet_tex_cache: dict = {}   # data_id -> GL texture id
        self._star_tex = None
        self._nebula_tex = None
        # unit sphere with UVs (unit radius, scaled at draw time)
        self._unit_sphere_tex = self._build_textured_sphere_list()

    # ------------------------------------------------------------------ per frame
    def draw(self, dt: float, selection: set, hover_id: int | None = None) -> None:
        self.time += dt
        st = self.state
        glMatrixMode(GL_MODELVIEW)
        self.camera.apply()
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
        if "effects" not in self.skip:
            self._draw_effects()
        if "projectiles" not in self.skip:
            self._draw_projectiles()
        if "ships" not in self.skip:
            self._draw_ships(selection)
        if "sites" not in self.skip:
            self._draw_construction_sites()
        if "rings" not in self.skip:
            self._draw_selection_rings(selection)
        glFlush()

    def _draw_construction_sites(self):
        """Wireframe scaffold + progress ring at each queued station site.

        The station entity only exists once construction completes; this makes
        the pending build visible (and selectable via the minimap/panel).
        """
        st = self.state
        for e in st.entities.values():
            if not e.alive or not e.is_construction:
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
            import OpenGL.GL as GL
            GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_LIGHTING_BIT |
                            GL.GL_CURRENT_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glDisable(GL.GL_LIGHTING)
            glDisable(GL_DEPTH_TEST)
            glLineWidth(2.0)
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
        """
        import OpenGL.GL as GL
        star = self.state.map_info.star
        sp = star.get("pos", [0, -3000, 0]) if star else [0, -3000, 0]
        GL.glEnable(GL.GL_LIGHT0)
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, (sp[0], max(sp[1], 2000.0), sp[2], 1.0))
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, (0.85, 0.8, 0.72, 1.0))
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, (0.0, 0.0, 0.0, 1.0))
        GL.glLightModelfv(GL.GL_LIGHT_MODEL_AMBIENT, (0.34, 0.37, 0.44, 1.0))
        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
        GL.glEnable(GL.GL_LIGHTING)
        GL.glShadeModel(GL.GL_SMOOTH)

    def _in_front(self, pos, radius: float) -> bool:
        """False when the object's center is behind/at the eye plane.

        Triangle fans crossing the near plane project with mirrored winding
        and smear giant shapes across the screen — this guard prevents that.
        """
        cam = self.camera
        eye = cam.eye_position()
        yaw = math.radians(cam.yaw)
        pitch = math.radians(cam.pitch)
        fwd = (-math.cos(pitch) * math.sin(yaw), -math.sin(pitch),
               -math.cos(pitch) * math.cos(yaw))
        depth = ((pos[0] if hasattr(pos, "__len__") else pos.x) - eye[0]) * fwd[0] \
            + ((pos[1] if hasattr(pos, "__len__") else pos.y) - eye[1]) * fwd[1] \
            + ((pos[2] if hasattr(pos, "__len__") else pos.z) - eye[2]) * fwd[2]
        return depth > radius

    # ------------------------------------------------------------------ background
    def _draw_starfield(self):
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

    def _draw_nebulas(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        for n in self.state.map_info.nebulas:
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
        cam = self.camera
        yaw = math.radians(cam.yaw)
        pitch = math.radians(cam.pitch)
        right = (math.cos(yaw), 0.0, -math.sin(yaw))
        fwd = (-math.cos(pitch) * math.sin(yaw), -math.sin(pitch),
               -math.cos(pitch) * math.cos(yaw))
        # screen-up in world space (right x fwd, ~unit for any pitch)
        up = normalize3(cross3(right, fwd))
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
        yaw = math.radians(cam.yaw)
        pitch = math.radians(cam.pitch)
        fwd = (-math.cos(pitch) * math.sin(yaw), -math.sin(pitch),
               -math.cos(pitch) * math.cos(yaw))
        right = (math.cos(yaw), 0.0, -math.sin(yaw))
        # screen-up in world space
        up = normalize3(cross3(right, fwd))
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
    def _draw_planets(self):
        for e in self.state.entities.values():
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
            surf = tex.planet_texture(kind, seed=abs(hash(e.name_override or kind)) % 1000)
            key = f"ptex_{kind}"
            if key not in self._planet_tex_cache:
                self._planet_tex_cache[key] = tex.surface_to_texture(surf)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self._planet_tex_cache[key])
            glEnable(GL_CULL_FACE)
            glColor3f(1, 1, 1)
            glPushMatrix()
            glScalef(e.radius, e.radius, e.radius)
            glCallList(self._unit_sphere_tex)
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

    def _build_textured_sphere_list(self, lons=24, lats=14):
        """Unit-radius UV sphere display list (scaled per planet at draw)."""
        lst = _gl.glGenLists(1)
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
                    for v, (u, w_) in zip(tri, uvs):
                        nn = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
                        glNormal3f(v[0] / nn, v[1] / nn, v[2] / nn)
                        glTexCoord2f(u, w_)
                        glVertex3f(*v)
                    glEnd()
        glEndList()
        return lst

    def _draw_asteroid_field(self, e):
        """Irregular lit rock clusters: 3-5 lumpy sub-rocks per asteroid,
        facet-shaded with a warm gray-brown palette, slow tumble."""
        rng = random.Random(int(e.pos.x) % 9973)
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        spin = self.time * 0.15
        n = 40
        for i in range(n):
            a = rng.uniform(0, 2 * math.pi)
            r = e.radius * (0.15 + 0.85 * math.sqrt(rng.random()))
            x = math.sin(a) * r
            z = math.cos(a) * r
            y = rng.uniform(-60, 60)
            s = rng.uniform(12, 46)
            glPushMatrix()
            glTranslatef(x, y, z)
            # slow tumble (deterministic per asteroid)
            glRotatef(spin * rng.uniform(0.4, 1.6) + rng.uniform(0, 360),
                      0.3, 0.7, 0.2)
            self._draw_rock(s, rng)
            glPopMatrix()
        glPopMatrix()

    def _draw_rock(self, s: float, rng):
        """One asteroid: 3-5 overlapping lit sub-rocks with irregular
        vertex-jittered facets. Palette: warm rock gray-brown, top lighter
        via lighting; no flat unlit quads."""
        base = (0.52 + rng.uniform(-0.08, 0.08),
                0.48 + rng.uniform(-0.08, 0.06),
                0.42 + rng.uniform(-0.06, 0.06))
        m = rng.randint(2, 4)          # sub-rock count
        for k in range(m):
            # deterministic jitter per sub-rock
            jx = rng.uniform(-0.25, 0.25) * s
            jy = rng.uniform(-0.18, 0.18) * s
            jz = rng.uniform(-0.25, 0.25) * s
            ss = s * (0.55 if k else rng.uniform(0.6, 0.8))
            shade = 1.0 - 0.16 * k / max(1, m - 1)
            glColor3f(base[0] * shade, base[1] * shade, base[2] * shade)
            self._rock_facets(ss, rng, jx, jy, jz)

    def _rock_facets(self, s: float, rng, jx: float, jy: float, jz: float):
        """Faceted lump: an icosphere-ish hull via 8 corner + 6 face bulge
        points, jittered, emitted as GL_TRIANGLES with per-face normals."""
        # 8 corners of a cube, jittered radially (deterministic from rng)
        c = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    rr = s * 0.5 * rng.uniform(0.75, 1.25)
                    c.append((sx * rr * 0.72 + jx, sy * rr * 0.6 + jy,
                              sz * rr * 0.72 + jz))
        # 6 face-bulge points for a lumpy silhouette
        f = []
        for dx, dy, dz in ((0, 0, 1), (0, 0, -1), (0, 1, 0),
                           (0, -1, 0), (1, 0, 0), (-1, 0, 0)):
            rr = s * 0.5 * rng.uniform(0.9, 1.3)
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
    def _draw_ships(self, selection: set):
        st = self.state
        for e in st.entities.values():
            if not e.alive:
                continue
            if e.is_planet:
                continue
            if (e.is_ship and "ships" not in self.skip) or \
                    (e.is_squadron and "squadrons" not in self.skip):
                self._draw_ship(e)
            elif e.is_station and "stations" not in self.skip:
                self._draw_station(e)

    def _owner_color(self, owner: int):
        p = self.state.players.get(owner)
        if p is None:
            return (0.6, 0.6, 0.6)
        return p.color

    def _out_tri(self, a, b, c, ref=(0.0, 0.0, 0.0)):
        """Emit one triangle with an outward-facing normal.

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
        glVertex3f(*a)
        glVertex3f(*b)
        glVertex3f(*c)

    def _lit_box(self, sx, sy, sz, cx=0.0, cy=0.0, cz=0.0):
        """Axis-aligned box with per-face outward normals (caller color)."""
        hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
        x0, x1 = cx - hx, cx + hx
        y0, y1 = cy - hy, cy + hy
        z0, z1 = cz - hz, cz + hz
        ref = (cx, cy, cz)
        glBegin(GL_TRIANGLES)          # REQUIRED: _out_tri only emits vertices
        for quad in (((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),
                     ((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)),
                     ((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)),
                     ((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)),
                     ((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)),
                     ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))):
            a, b, c, d = quad
            self._out_tri(a, b, c, ref)
            self._out_tri(a, c, d, ref)
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

    def _draw_ship(self, e: Entity):
        ds = self.ds
        sd = ds.ships.get(e.data_id)
        if sd is None:
            return
        vis = ds.ship_visual(e.data_id)
        color = self._owner_color(e.owner)
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        # sim facing is (sin(yaw), 0, cos(yaw)); +yaw in GL's right-handed Y
        # rotation matches it exactly (negative sign mirrored the ships —
        # nose trailed while moving sideways/backwards)
        glRotatef(math.degrees(e.yaw), 0, 1, 0)
        # engine trail behind ship (keeps motion readable)
        spd = e.vel.length()
        if spd > 2:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(False)
            glColor4f(0.4, 0.7, 1.0, min(0.55, spd / 400.0))
            glBegin(GL_TRIANGLES)
            L = vis["scale"] * e.radius * (2.2 + spd / 120.0)
            glVertex3f(0, 0, -L)
            glVertex3f(-e.radius * 0.35, 0, 0)
            glVertex3f(e.radius * 0.35, 0, 0)
            glEnd()
            glDepthMask(True)
            glDisable(GL_BLEND)
        # hull display list
        lst = self._ship_display_list(vis["shape"])
        scale = vis["scale"] * max(1.0, e.radius / 40.0)
        # LOD: enforce minimum screen-space size so ships stay visible/clickable
        # at tactical zoom (spec §35 readability).
        sp = self.camera.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
        if sp is not None:
            eye = self.camera.eye_position()
            dist = math.sqrt((e.pos.x - eye[0]) ** 2 + (e.pos.y - eye[1]) ** 2
                             + (e.pos.z - eye[2]) ** 2)
            px_per_world = self.camera.height / (
                2.0 * dist * math.tan(math.radians(self.camera.fov / 2)))
            # shape half-extent ~ 26 world units * scale; want >= 7 px on screen
            want_scale = 7.0 / max(0.01, 26.0 * px_per_world)
            scale = max(scale, want_scale)
        glScalef(scale, scale, scale)
        glColor3f(*color)
        glCallList(lst)
        glPopMatrix()
        # engine glow: additive billboard at the ship's tail (world space)
        if spd > 8:
            L = vis["scale"] * e.radius * 1.1
            rear = (e.pos.x - L * math.sin(e.yaw),
                    e.pos.y,
                    e.pos.z - L * math.cos(e.yaw))
            if self._in_front(rear, 14.0):
                glEnable(GL_BLEND)
                glDepthMask(False)
                self._draw_glow(rear, 10.0 + 6.0 * min(1.0, spd / 300.0),
                                (0.45, 0.75, 1.0), alpha=0.55, additive=True)
                glDepthMask(True)
                glDisable(GL_BLEND)

    def _ship_display_list(self, shape: str) -> int:
        """Multi-part lit hulls. No baked colors — caller color + lighting
        shade the geometry (tops bright, sides dark, reads as 3D)."""
        if shape in self.ship_lists:
            return self.ship_lists[shape]
        lst = _gl.glGenLists(1)
        glNewList(lst, GL_COMPILE)
        # two-sided: winding of emitted faces must not depend on cull state
        import OpenGL.GL as GL
        GL.glPushAttrib(GL.GL_ENABLE_BIT)
        GL.glDisable(GL.GL_CULL_FACE)
        if shape == "wedge":
            # fighter: fuselage + canopy + swept wings + tail fin + cannons
            self._lit_box(14, 6, 40, cy=3)
            self._out_pyr((0, 4, 34), ((-7, 1, 16), (7, 1, 16),
                                       (7, 6, 16), (-7, 6, 16)))
            self._lit_box(34, 1.6, 16, cx=18, cy=4, cz=-4)   # right wing
            self._lit_box(34, 1.6, 16, cx=-18, cy=4, cz=-4)  # left wing
            self._lit_box(2.5, 12, 14, cy=9, cz=-12)         # tail fin
            # wingtip cannons + engine nozzles
            self._lit_box(3, 3, 12, cx=34, cy=4, cz=4)
            self._lit_box(3, 3, 12, cx=-34, cy=4, cz=4)
            self._lit_box(4, 4, 3, cz=-20.5)
            self._lit_box(3, 2, 2, cy=6.5, cz=-20.5)
        elif shape == "needle":
            # corvette/frigate: nose + hull + bridge + engines + turrets
            self._out_pyr((0, 3, 50), ((-8, 0, 14), (8, 0, 14),
                                       (8, 6, 14), (-8, 6, 14)))
            self._lit_box(24, 10, 44, cz=-8)
            self._lit_box(12, 7, 16, cy=7, cz=-14)           # bridge
            self._lit_box(18, 4, 8, cz=-32)                  # engine block
            # twin engine nozzles
            self._lit_box(6, 6, 4, cx=-5, cy=-1, cz=-36)
            self._lit_box(6, 6, 4, cx=5, cy=-1, cz=-36)
            # dorsal turret + sensor mast
            self._lit_box(5, 5, 5, cy=6, cz=4)
            self._lit_box(7, 3, 3, cy=8, cz=4)
            self._lit_box(1.2, 10, 1.2, cy=12, cz=-18)       # antenna
            # side sponsons (gun pods)
            self._lit_box(4, 4, 14, cx=13.5, cy=-2, cz=-6)
            self._lit_box(4, 4, 14, cx=-13.5, cy=-2, cz=-6)
        elif shape == "cruiser":
            # heavy hull + bow + command tower + nacelles + engines + broadside
            self._lit_box(30, 14, 100, cz=-8)
            self._out_pyr((0, 5, 78), ((-13, 0, 40), (13, 0, 40),
                                       (13, 12, 40), (-13, 12, 40)))
            self._lit_box(18, 13, 28, cy=12, cz=-18)         # command tower
            self._lit_box(8, 6, 44, cx=20, cz=-26)           # right nacelle
            self._lit_box(8, 6, 44, cx=-20, cz=-26)          # left nacelle
            self._lit_box(22, 7, 10, cz=-56)                 # engine block
            # triple engine nozzles
            self._lit_box(6, 6, 5, cx=-7, cy=-2, cz=-61)
            self._lit_box(6, 6, 5, cx=0, cy=-2, cz=-61)
            self._lit_box(6, 6, 5, cx=7, cy=-2, cz=-61)
            # command tower windows band + top comm dome (inline tristrip)
            self._lit_box(14, 2, 6, cy=16, cz=-18)
            self._dome(4.5, 10, 7)
            # broadside turret rows (3 per side)
            for cz_ in (18, -2, -22):
                self._lit_box(6, 5, 6, cx=16, cy=5, cz=cz_)
                self._lit_box(6, 5, 6, cx=-16, cy=5, cz=cz_)
            # spinal cannon
            self._lit_box(4, 4, 26, cy=8, cz=58)
            self._out_pyr((0, 8, 92), ((-2.5, 6.5, 66), (2.5, 6.5, 66),
                                       (2.5, 9.5, 66), (-2.5, 9.5, 66)))
        elif shape == "dagger":
            # battleship: long dagger hull + tower + spines + heavy battery
            self._lit_box(38, 20, 150)
            self._out_pyr((0, 6, 108), ((-16, 0, 72), (16, 0, 72),
                                        (16, 16, 72), (-16, 16, 72)))
            self._lit_box(20, 24, 32, cy=20, cz=-34)         # command tower
            self._lit_box(4, 18, 18, cy=14, cz=28)           # dorsal spine
            self._lit_box(30, 10, 12, cz=-70)                # engine block
            # quad engine nozzles
            for cx_ in (-11, -4, 4, 11):
                self._lit_box(5.5, 5.5, 5, cx=cx_, cy=-4, cz=-76)
            # tower detail: windows + flag mast
            self._lit_box(16, 3, 8, cy=30, cz=-34)
            self._lit_box(1.5, 12, 1.5, cy=40, cz=-34)
            # heavy turret bank (4 turrets on the spine)
            for cz_ in (48, 24, -6, -52):
                self._lit_box(9, 7, 9, cy=12, cz=cz_)
                self._lit_box(3.5, 3.5, 10, cy=14, cz=cz_ + 7)
            # side armor sponsons
            for cz_ in (30, -30):
                self._lit_box(6, 8, 30, cx=21, cy=-3, cz=cz_)
                self._lit_box(6, 8, 30, cx=-21, cy=-3, cz=cz_)
        else:
            # construction/generic: cargo box + cab + skids + crane arm
            self._lit_box(26, 14, 36, cy=2)
            self._lit_box(12, 8, 10, cy=11, cz=12)
            self._lit_box(30, 3, 8, cy=-7, cz=-10)
            self._lit_box(30, 3, 8, cy=-7, cz=12)
            # cargo pods + crane mast
            self._lit_box(8, 8, 8, cx=8, cy=-8, cz=16)
            self._lit_box(8, 8, 8, cx=-8, cy=-8, cz=16)
            self._lit_box(2.5, 14, 2.5, cx=-12, cy=16, cz=-8)
            self._lit_box(14, 2, 2.5, cx=-5, cy=22, cz=-8)
            # engine nozzles
            self._lit_box(5, 5, 3, cz=-18.5)
            self._lit_box(4, 3, 2, cy=7, cz=18.5)
        GL.glPopAttrib()
        glEndList()
        self.ship_lists[shape] = lst
        return lst

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
        color = self._owner_color(e.owner)
        sd = self.ds.stations.get(e.data_id)
        if sd is None:
            return
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        glRotatef(self.time * 3.0, 0, 1, 0)
        r = e.radius
        dark = (color[0] * 0.55, color[1] * 0.55, color[2] * 0.55)
        if e.data_id == "command_station":
            # solid core sphere + rotating ring + 4 spoke girders + docking arms
            glPushMatrix()
            glRotatef(-90, 1, 0, 0)
            glColor3f(*color)
            self._draw_sphere(r * 0.42, 18, 12)
            glPopMatrix()
            glColor3f(*dark)
            self._station_ring(r, 36)
            # 4 spoke girders (chunky lit boxes)
            glColor3f(*color)
            for i in range(4):
                glPushMatrix()
                glRotatef(-i * 90.0, 0, 1, 0)
                self._lit_box(r * 1.9, r * 0.09, r * 0.09)
                glPopMatrix()
            # docking arms: two opposing pylons with pad boxes
            for sgn in (-1, 1):
                glPushMatrix()
                glRotatef(90 if sgn > 0 else -90, 0, 1, 0)
                self._lit_box(r * 0.9, r * 0.16, r * 0.16, cx=r * 1.2)
                self._lit_box(r * 0.3, r * 0.18, r * 0.6, cx=r * 1.65)
                glPopMatrix()
            # top + bottom sensor spires
            self._lit_box(r * 0.1, r * 0.45, r * 0.1, cy=r * 0.55)
            self._lit_box(r * 0.1, r * 0.45, r * 0.1, cy=-r * 0.55)
            # ring habitation pods (8 around the ring)
            for i in range(8):
                a = i / 8 * 2 * math.pi
                px_, pz_ = math.sin(a) * r, math.cos(a) * r
                self._lit_box(r * 0.16, r * 0.12, r * 0.3,
                              cx=px_, cy=0.0, cz=pz_)
            # defense turret studs on the equator
            for i in range(4):
                a = (i / 4 + 0.125) * 2 * math.pi
                px_, pz_ = math.sin(a) * r, math.cos(a) * r
                self._lit_box(r * 0.08, r * 0.16, r * 0.08,
                              cx=px_, cy=r * 0.12, cz=pz_)
        elif e.data_id == "shipyard":
            # shipyard: massive gantry frame + build cradles + core
            glColor3f(*color)
            self._lit_box(r * 0.55, r * 0.85, r * 1.15, cy=r * 0.15)
            glColor3f(*dark)
            self._lit_box(r * 1.6, r * 0.16, r * 0.16, cy=r * 0.8)
            self._lit_box(r * 0.16, r * 0.85, r * 0.16, cx=r * 0.72, cy=r * 0.38)
            self._lit_box(r * 0.16, r * 0.85, r * 0.16, cx=-r * 0.72, cy=r * 0.38)
            glColor3f(*color)
            self._lit_box(r * 0.75, r * 0.28, r * 0.55, cy=-r * 0.35, cz=r * 0.6)
            glPushMatrix()
            glRotatef(-90, 1, 0, 0)
            self._draw_sphere(r * 0.24, 14, 9)
            glPopMatrix()
            # two open build cradles at the sides (ship under construction)
            glColor3f(*dark)
            for sgn in (-1, 1):
                self._lit_box(r * 0.1, r * 0.5, r * 0.9,
                              cx=sgn * r * 0.95, cy=r * 0.1)
                self._lit_box(r * 0.4, r * 0.1, r * 0.7,
                              cx=sgn * r * 0.95, cy=r * 0.38)
            # greeble plates on the main block
            glColor3f(*color)
            self._lit_box(r * 0.62, r * 0.12, r * 0.4, cy=r * 0.62, cz=-r * 0.3)
            self._lit_box(r * 0.2, r * 0.3, r * 0.2, cy=r * 0.72, cz=r * 0.45)
        elif e.data_id == "fighter_platform":
            # fighter platform: flat landing deck + control tower + supports
            glColor3f(*color)
            self._lit_box(r * 1.6, r * 0.12, r * 1.6, cy=r * 0.25)
            self._lit_box(r * 0.4, r * 0.7, r * 0.4, cy=r * 0.65, cz=-r * 0.55)
            glColor3f(*dark)
            self._lit_box(r * 0.8, r * 0.14, r * 0.8, cy=-r * 0.05, cz=r * 0.55)
            for sx in (-1, 1):
                for sz in (-1, 1):
                    self._lit_box(r * 0.12, r * 0.45, r * 0.12,
                                  cx=sx * r * 0.65, cy=r * 0.02, cz=sz * r * 0.65)
        else:
            # per-type detail for mining / sensor / trade / defense / repair /
            # energy relay — each reads differently at a glance
            did = e.data_id
            if did == "mining_station":
                # ore-processing plant: squat refinery block, drill mast
                # into the rock, ore silos, conveyor arms
                glColor3f(*color)
                self._lit_box(r * 1.1, r * 0.55, r * 0.9, cy=r * 0.1)
                glColor3f(*dark)
                # drill mast + cutter head
                self._lit_box(r * 0.14, r * 0.9, r * 0.14, cy=-r * 0.45)
                self._lit_box(r * 0.34, r * 0.18, r * 0.34, cy=-r * 0.9)
                glColor3f(*color)
                # twin ore silos + top frame
                self._lit_box(r * 0.3, r * 0.6, r * 0.3, cx=r * 0.55, cy=r * 0.5)
                self._lit_box(r * 0.3, r * 0.6, r * 0.3, cx=-r * 0.55, cy=r * 0.5)
                glColor3f(*dark)
                self._lit_box(r * 1.2, r * 0.1, r * 0.12, cy=r * 0.85)
                # conveyor arms to silos
                self._lit_box(r * 0.5, r * 0.08, r * 0.2, cx=r * 0.4, cy=r * 0.35)
                self._lit_box(r * 0.5, r * 0.08, r * 0.2, cx=-r * 0.4, cy=r * 0.35)
                # greeble plates
                glColor3f(*color)
                self._lit_box(r * 0.7, r * 0.1, r * 0.3, cy=r * 0.42, cz=r * 0.25)
                self._lit_box(r * 0.4, r * 0.08, r * 0.4, cy=r * 0.42, cz=-r * 0.3)
            elif did == "sensor_station":
                # listening post: slim pylon + huge phased-array dish + fins
                glColor3f(*dark)
                self._lit_box(r * 0.28, r * 1.5, r * 0.28, cy=r * 0.2)
                glColor3f(*color)
                glPushMatrix()
                glTranslatef(0.0, r * 1.05, 0.0)
                glRotatef(self.time * 8.0, 0, 1, 0)
                glRotatef(28, 1, 0, 0)
                self._dome(r * 0.95, 14, 6)      # dish (concave reads via rim)
                self._lit_box(r * 0.16, r * 0.16, r * 0.5, cz=r * 0.75)
                glPopMatrix()
                glColor3f(*dark)
                self._lit_box(r * 1.3, r * 0.1, r * 0.3, cy=-r * 0.35)
                self._lit_box(r * 0.1, r * 0.5, r * 0.9, cy=r * 0.3)
                glColor3f(*color)
                # comm blister
                glPushMatrix()
                glTranslatef(0.0, -r * 0.15, r * 0.2)
                self._dome(r * 0.3, 10, 6)
                glPopMatrix()
            elif did == "trade_station":
                # commerce hub: wide stacked decks + docking spokes + beacon
                glColor3f(*color)
                self._lit_box(r * 1.35, r * 0.28, r * 1.35, cy=r * 0.15)
                glColor3f(*dark)
                self._lit_box(r * 0.95, r * 0.3, r * 0.95, cy=r * 0.5)
                glColor3f(*color)
                self._lit_box(r * 0.5, r * 0.3, r * 0.5, cy=r * 0.85)
                # four docking spokes with pad boxes
                glColor3f(*dark)
                for i in range(4):
                    glPushMatrix()
                    glRotatef(-i * 90.0, 0, 1, 0)
                    self._lit_box(r * 0.85, r * 0.08, r * 0.08, cx=r * 1.05)
                    self._lit_box(r * 0.2, r * 0.14, r * 0.4, cx=r * 1.45)
                    glPopMatrix()
                # beacon spire (blinks via time-modulated glow below)
                glColor3f(*color)
                self._lit_box(r * 0.06, r * 0.5, r * 0.06, cy=r * 1.25)
            elif did == "defense_platform":
                # gun fortress: armored core + 4 turret barbettes + missile box
                glColor3f(*dark)
                self._lit_box(r * 0.9, r * 0.5, r * 0.9)
                glColor3f(*color)
                self._lit_box(r * 0.55, r * 0.35, r * 0.55, cy=r * 0.4)
                # 4 heavy barbettes with barrels
                for i in range(4):
                    glPushMatrix()
                    glRotatef(-i * 90.0, 0, 1, 0)
                    self._lit_box(r * 0.22, r * 0.2, r * 0.22,
                                  cx=r * 0.5, cy=r * 0.3)
                    self._lit_box(r * 0.07, r * 0.07, r * 0.55,
                                  cx=r * 0.5, cy=r * 0.34, cz=r * 0.3)
                    glPopMatrix()
                # missile battery block + armor skirt
                glColor3f(*dark)
                self._lit_box(r * 0.45, r * 0.25, r * 0.3, cy=r * 0.62, cz=-r * 0.2)
                self._lit_box(r * 1.3, r * 0.12, r * 1.3, cy=-r * 0.3)
            elif did == "repair_dock":
                # open-frame dry dock: cradle claws + gantry + welding arms
                glColor3f(*dark)
                self._lit_box(r * 0.3, r * 0.7, r * 1.3, cy=r * 0.2)   # spine
                glColor3f(*color)
                for sgn in (-1, 1):
                    # cradle claws (angled boxes)
                    glPushMatrix()
                    glTranslatef(sgn * r * 0.75, 0.0, 0.0)
                    glRotatef(sgn * 28, 1, 0, 0)
                    self._lit_box(r * 0.14, r * 1.0, r * 0.2)
                    glPopMatrix()
                self._lit_box(r * 1.4, r * 0.12, r * 0.12, cy=r * 0.75)
                glColor3f(*dark)
                self._lit_box(r * 0.2, r * 0.3, r * 0.2, cy=r * 0.9, cz=r * 0.4)
            elif did == "energy_relay":
                # reactor cluster: core sphere + collector vanes + coils
                glPushMatrix()
                glRotatef(-90, 1, 0, 0)
                glColor3f(*color)
                self._draw_sphere(r * 0.45, 16, 10)
                glPopMatrix()
                glColor3f(*dark)
                for i in range(3):
                    glPushMatrix()
                    glRotatef(-i * 120.0, 0, 1, 0)
                    self._lit_box(r * 0.08, r * 0.9, r * 0.35, cy=r * 0.2)
                    glPopMatrix()
                glColor3f(*color)
                # ring of coils
                for i in range(6):
                    a = i / 6 * 2 * math.pi
                    self._lit_box(r * 0.16, r * 0.3, r * 0.16,
                                  cx=math.sin(a) * r * 0.85,
                                  cy=-r * 0.2,
                                  cz=math.cos(a) * r * 0.85)
                self._lit_box(r * 0.1, r * 0.8, r * 0.1, cy=r * 0.7)
            else:
                # generic platform: two stacked lit boxes + solid ring + pylon
                glColor3f(*color)
                self._lit_box(r * 1.0, r * 0.6, r * 1.0, cy=r * 0.1)
                self._lit_box(r * 0.65, r * 0.35, r * 0.65, cy=r * 0.6)
                glColor3f(*dark)
                self._station_ring(r * 1.1, 30)
                glColor3f(*color)
                self._lit_box(r * 0.12, r * 0.55, r * 0.12, cy=r * 0.8)
        # construction progress ring
        if e.build_queue:
            item = e.build_queue[0]
            frac = 1.0 - max(0.0, item.get("time_left", 0)) / max(0.1, item.get("total", 1))
            glDisable(GL_DEPTH_TEST)
            glColor3f(0.4, 1.0, 0.5)
            glLineWidth(3.0)
            glBegin(GL_LINE_STRIP)
            rr = r * 1.5
            for i in range(int(40 * min(1.0, frac)) + 1):
                a = i / 40 * 2 * math.pi
                glVertex3f(math.sin(a) * rr, r * 0.8, math.cos(a) * rr)
            glEnd()
            glEnable(GL_DEPTH_TEST)
        glPopMatrix()

    # ------------------------------------------------------------------ projectiles
    def _draw_projectiles(self):
        st = self.state
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        glBegin(GL_POINTS)
        for p in st.projectiles.values():
            glColor4f(p.color[0], p.color[1], p.color[2], 0.95)
            _gl.glVertex3f(p.pos.x, p.pos.y, p.pos.z)
        glEnd()
        glDepthMask(True)
        glDisable(GL_BLEND)

    # ------------------------------------------------------------------ effects
    def _draw_effects(self):
        st = self.state
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        for fx in st.effects[:400]:
            kind = fx["kind"]
            t = fx.get("t", 0.0)
            pos = fx["pos"]
            color = fx.get("color", [1, 1, 1])
            if kind == "explosion":
                life = 1.2
                a = max(0.0, 1.0 - t / life)
                if a <= 0:
                    continue
                r = 30 + (fx.get("size", 40) * (0.3 + 2.2 * (1.0 - a)))
                # billboard fireball core + expanding billboard ring
                self._draw_glow(pos, r * 0.8, (1.0, 0.55, 0.2),
                                alpha=a * 0.85, additive=True)
                self._bb_ring(pos, r, (1.0, 0.5, 0.18, a * 0.7), 3.0)
            elif kind == "explosion_small":
                a = max(0.0, 1.0 - t / 0.5)
                if a <= 0:
                    continue
                self._draw_glow(pos, 18 + 40 * (1 - a), (1.0, 0.6, 0.25),
                                alpha=a * 0.7, additive=True)
            elif kind in ("impact", "hull_hit"):
                a = max(0.0, 1.0 - t / 0.35)
                if a <= 0:
                    continue
                # camera-facing spark, not a ground disc
                self._draw_glow(pos, 8 + 16 * (1 - a), color,
                                alpha=a * 0.9, additive=True)
            elif kind == "beam":
                a = max(0.0, 1.0 - t / 0.25)
                if a <= 0 or "target_pos" not in fx:
                    continue
                glColor4f(color[0], color[1], color[2], a)
                glLineWidth(2.5)
                glBegin(GL_LINES)
                glVertex3f(pos[0], pos[1], pos[2])
                glVertex3f(*fx["target_pos"])
                glEnd()
                # glow at both ends of the beam
                self._draw_glow(pos, 10, color, alpha=a * 0.8, additive=True)
                self._draw_glow(fx["target_pos"], 14, color,
                                alpha=a * 0.9, additive=True)
            elif kind in ("jump_charge", "jump_arrive"):
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

    def _bb_ring(self, pos, radius, color4, width=2.0):
        """Camera-facing ring billboard (billboard-plane line loop)."""
        if radius <= 0 or not self._in_front(pos, radius):
            return
        cam = self.camera
        yaw = math.radians(cam.yaw)
        pitch = math.radians(cam.pitch)
        right = (math.cos(yaw), 0.0, -math.sin(yaw))
        fwd = (-math.cos(pitch) * math.sin(yaw), -math.sin(pitch),
               -math.cos(pitch) * math.cos(yaw))
        up = normalize3(cross3(right, fwd))
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
    def _draw_selection_rings(self, selection: set):
        if not selection:
            return
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        for eid in selection:
            e = self.state.entities.get(eid)
            if e is None or not e.alive:
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
            glRotatef(-90, 1, 0, 0)
            glColor4f(col[0], col[1], col[2], 0.9)
            glLineWidth(2.0)
            r = e.radius * (1.35 if not e.is_planet else 1.1)
            glBegin(GL_LINE_LOOP)
            for i in range(28):
                a = i / 28 * 2 * math.pi
                glVertex3f(math.sin(a) * r, 0, math.cos(a) * r)
            glEnd()
            glPopMatrix()
        # health arcs for damaged selected units
        for eid in selection:
            e = self.state.entities.get(eid)
            if e is None or not e.alive or e.is_planet:
                continue
            self._draw_health_arc(e)
        glEnable(GL_DEPTH_TEST)
        glDisable(GL_BLEND)

    def _draw_health_arc(self, e: Entity):
        """Arc showing shield (outer) and hull (inner) fractions above the unit."""
        frac_h = max(0.0, e.hull_fraction())
        frac_s = (e.total_shield() / e.max_shield_total()) if e.max_shield_total() > 0 else 0.0
        r = e.radius * 1.6
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y + e.radius * 0.5 + 30, e.pos.z)
        glRotatef(-90, 1, 0, 0)
        glLineWidth(3.0)
        # hull arc
        glBegin(GL_LINE_STRIP)
        for i in range(int(24 * frac_h) + 1):
            a = math.pi * (i / 24)          # half circle
            glVertex3f(math.cos(a) * r, 0, math.sin(a) * r)
        glColor3f(0.3, 1.0, 0.4)
        glEnd()
        # shield arc (blue, outer)
        if frac_s > 0:
            r2 = r * 1.25
            glBegin(GL_LINE_STRIP)
            glColor3f(0.4, 0.7, 1.0)
            for i in range(int(24 * frac_s) + 1):
                a = math.pi * (i / 24)
                glVertex3f(math.cos(a) * r2, 0, math.sin(a) * r2)
            glEnd()
        glPopMatrix()

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