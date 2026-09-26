"""Main renderer: draws the world from GameState (pure view — never mutates sim).

Immediate-mode modern-ish GL (fixed pipeline for prototype clarity). Ship meshes
are cached display lists per (shape, owner-color) template; effects are pooled
quads; scale LOD keeps distant fleets readable.
"""
from __future__ import annotations

import math
import random

import pygame

from OpenGL.GL import (
    glBegin, glBlendFunc, glCallList, glColor3f, glColor4f, glDepthMask,
    glDisable, glEnable, glEnd, glEndList, glFlush, glLineWidth, glMatrixMode,
    glNewList, glPopAttrib, glPopMatrix, glPushMatrix, glRotatef, glScalef,
    glTranslatef, glVertex3f, GL_BLEND, GL_COMPILE, GL_CURRENT_BIT, GL_DEPTH_TEST,
    GL_LINE_LOOP, GL_LINE_STRIP, GL_LINES, GL_MODELVIEW, GL_ONE_MINUS_SRC_ALPHA,
    GL_POINTS, GL_QUADS, GL_SRC_ALPHA, GL_TRANSFORM_BIT, GL_TRIANGLES, GL_TRIANGLE_FAN,
)
import OpenGL.GL as _gl

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

    # ------------------------------------------------------------------ per frame
    def draw(self, dt: float, selection: set, hover_id: int | None = None) -> None:
        self.time += dt
        st = self.state
        glMatrixMode(GL_MODELVIEW)
        self.camera.apply()
        self._draw_starfield()
        self._draw_nebulas()
        self._draw_star()
        self._draw_jump_points()
        self._draw_planets()
        self._draw_effects()
        self._draw_projectiles()
        self._draw_ships(selection)
        self._draw_selection_rings(selection)
        self._draw_floating_texts()
        glFlush()

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
            color = n.get("color", [0.4, 0.2, 0.55])
            self._draw_billboard_blob(n["pos"], n["radius"], color, alpha=0.16)
        glDepthMask(True)
        glDisable(GL_BLEND)

    def _draw_star(self):
        star = self.state.map_info.star
        if not star:
            return
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(False)
        self._draw_billboard_blob(star["pos"], star.get("size", 2000),
                                  star.get("color", [1, 0.9, 0.6]), alpha=0.9)
        self._draw_billboard_blob(star["pos"], star.get("size", 2000) * 1.8,
                                  star.get("color", [1, 0.9, 0.6]), alpha=0.25)
        glDepthMask(True)
        glDisable(GL_BLEND)

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

    def _draw_billboard_blob(self, pos, radius, color, alpha):
        """Camera-facing circle on the battlefield plane (cheap volumetric look)."""
        glPushMatrix()
        glTranslatef(pos[0], pos[1], pos[2])
        glColor4f(color[0], color[1], color[2], alpha)
        glBegin(GL_TRIANGLE_FAN)
        glVertex3f(0, 0, 0)
        segments = 28
        for i in range(segments + 1):
            a = i / segments * 2 * math.pi
            glVertex3f(math.sin(a) * radius, 0, math.cos(a) * radius)
        glEnd()
        glPopMatrix()

    # ------------------------------------------------------------------ planets
    def _draw_planets(self):
        for e in self.state.entities.values():
            if not e.alive or not e.is_planet:
                continue
            kind = e.data_id
            if kind == "asteroid_field":
                self._draw_asteroid_field(e)
                continue
            color = PLANET_COLORS.get(kind, (0.55, 0.55, 0.6))
            glPushMatrix()
            glTranslatef(e.pos.x, e.pos.y, e.pos.z)
            glEnable(GL_DEPTH_TEST)
            # sphere
            glColor3f(*color)
            self._draw_sphere(e.radius, 20, 14)
            # owner ring
            if e.colonized_by is not None and e.colonized_by >= 0:
                p = self.state.players.get(e.colonized_by)
                if p:
                    glRotatef(-90, 1, 0, 0)
                    glColor3f(*p.color)
                    glLineWidth(3.0)
                    glBegin(GL_LINE_LOOP)
                    r = e.radius + 120
                    for i in range(40):
                        a = i / 40 * 2 * math.pi
                        glVertex3f(math.sin(a) * r, 0, math.cos(a) * r)
                    glEnd()
            glPopMatrix()

    def _draw_asteroid_field(self, e):
        rng = random.Random(int(e.pos.x) % 9973)
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        glColor3f(0.45, 0.42, 0.38)
        n = 46
        for i in range(n):
            a = rng.uniform(0, 2 * math.pi)
            r = e.radius * (0.15 + 0.85 * math.sqrt(rng.random()))
            x = math.sin(a) * r
            z = math.cos(a) * r
            y = rng.uniform(-60, 60)
            s = rng.uniform(12, 46)
            glPushMatrix()
            glTranslatef(x, y, z)
            glRotatef(rng.uniform(0, 360), 0.3, 0.7, 0.2)
            self._draw_box(s, s * 0.6, s)
            glPopMatrix()
        glPopMatrix()

    def _draw_sphere(self, radius, lons=16, lats=10):
        lst = self._sphere_list(radius)
        glCallList(lst)

    def _sphere_list(self, radius):
        key = round(radius)
        if key in self.ship_lists:
            return self.ship_lists[key]
        lst = _gl.glGenLists(1)
        glNewList(lst, GL_COMPILE)
        lons, lats = 18, 10
        for i in range(lons):
            lon0 = 2 * math.pi * i / lons
            lon1 = 2 * math.pi * (i + 1) / lons
            glBegin(GL_QUADS)
            for j in range(lats):
                lat0 = math.pi * j / lats - math.pi / 2
                lat1 = math.pi * (j + 1) / lats - math.pi / 2
                for lon, lat in ((lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1)):
                    x = radius * math.cos(lat) * math.sin(lon)
                    y = radius * math.sin(lat)
                    z = radius * math.cos(lat) * math.cos(lon)
                    shade = 0.75 + 0.25 * math.cos(lat)
                    glColor3f(shade, shade, shade)
                    glVertex3f(x, y, z)
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
            if e.is_ship or e.is_squadron:
                self._draw_ship(e)
            elif e.is_station:
                self._draw_station(e)

    def _owner_color(self, owner: int):
        p = self.state.players.get(owner)
        if p is None:
            return (0.6, 0.6, 0.6)
        return p.color

    def _draw_ship(self, e: Entity):
        ds = self.ds
        sd = ds.ships.get(e.data_id)
        if sd is None:
            return
        vis = ds.ship_visual(e.data_id)
        color = self._owner_color(e.owner)
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        glRotatef(math.degrees(-e.yaw), 0, 1, 0)
        # engine glow behind ship
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
        glScalef(scale, scale, scale)
        glColor3f(*color)
        glCallList(lst)
        glPopMatrix()

    def _ship_display_list(self, shape: str) -> int:
        if shape in self.ship_lists:
            return self.ship_lists[shape]
        lst = _gl.glGenLists(1)
        glNewList(lst, GL_COMPILE)
        # unit-scale procedural hulls (scaled per ship at draw time)
        if shape == "wedge":            # fighter
            glBegin(GL_TRIANGLES)
            glVertex3f(0, 0, 26); glVertex3f(-10, 0, -12); glVertex3f(10, 0, -12)
            glVertex3f(0, 3, 10); glVertex3f(10, 3, -12); glVertex3f(-10, 3, -12)
            glEnd()
            glBegin(GL_QUADS)
            glVertex3f(-10, 0, -12); glVertex3f(-24, 0, -20); glVertex3f(-24, 2, -20); glVertex3f(-10, 2, -12)
            glVertex3f(10, 0, -12); glVertex3f(24, 0, -20); glVertex3f(24, 2, -20); glVertex3f(10, 2, -12)
            glEnd()
        elif shape == "needle":         # corvette/frigate
            glBegin(GL_TRIANGLES)
            glVertex3f(0, 0, 46); glVertex3f(-9, 0, 10); glVertex3f(9, 0, 10)
            glEnd()
            glBegin(GL_QUADS)
            glVertex3f(-9, 0, 10); glVertex3f(-13, 0, -30); glVertex3f(13, 0, -30); glVertex3f(9, 0, 10)
            glVertex3f(-9, 4, 10); glVertex3f(-13, 4, -30); glVertex3f(13, 4, -30); glVertex3f(9, 4, 10)
            # sides
            glVertex3f(-9, 0, 10); glVertex3f(-13, 0, -30); glVertex3f(-13, 4, -30); glVertex3f(-9, 4, 10)
            glVertex3f(9, 0, 10); glVertex3f(13, 0, -30); glVertex3f(13, 4, -30); glVertex3f(9, 4, 10)
            glEnd()
            # bridge
            glBegin(GL_TRIANGLES)
            glVertex3f(0, 12, -8); glVertex3f(-8, 2, -20); glVertex3f(8, 2, -20)
            glEnd()
        elif shape == "cruiser":
            glBegin(GL_QUADS)
            # long hull
            glVertex3f(-12, 0, 60); glVertex3f(-18, 0, -40); glVertex3f(18, 0, -40); glVertex3f(12, 0, 60)
            glVertex3f(-12, 8, 60); glVertex3f(-18, 8, -40); glVertex3f(18, 8, -40); glVertex3f(12, 8, 60)
            glVertex3f(-12, 0, 60); glVertex3f(-18, 0, -40); glVertex3f(-18, 8, -40); glVertex3f(-12, 8, 60)
            glVertex3f(12, 0, 60); glVertex3f(18, 0, -40); glVertex3f(18, 8, -40); glVertex3f(12, 8, 60)
            glEnd()
            glBegin(GL_TRIANGLES)
            glVertex3f(0, 0, 90); glVertex3f(-12, 0, 60); glVertex3f(12, 0, 60)
            glVertex3f(0, 0, 90); glVertex3f(12, 8, 60); glVertex3f(-12, 8, 60)
            # superstructure
            glVertex3f(0, 26, -12); glVertex3f(-14, 6, -36); glVertex3f(14, 6, -36)
            glEnd()
        elif shape == "dagger":         # battleship / supercapital
            glBegin(GL_QUADS)
            glVertex3f(-16, 0, 90); glVertex3f(-26, 0, -70); glVertex3f(26, 0, -70); glVertex3f(16, 0, 90)
            glVertex3f(-16, 12, 90); glVertex3f(-26, 12, -70); glVertex3f(26, 12, -70); glVertex3f(16, 12, 90)
            glVertex3f(-16, 0, 90); glVertex3f(-26, 0, -70); glVertex3f(-26, 12, -70); glVertex3f(-16, 12, 90)
            glVertex3f(16, 0, 90); glVertex3f(26, 0, -70); glVertex3f(26, 12, -70); glVertex3f(16, 12, 90)
            glEnd()
            glBegin(GL_TRIANGLES)
            glVertex3f(0, 0, 130); glVertex3f(-16, 0, 90); glVertex3f(16, 0, 90)
            glVertex3f(0, 0, 130); glVertex3f(16, 12, 90); glVertex3f(-16, 12, 90)
            # command tower
            glVertex3f(0, 44, -20); glVertex3f(-18, 10, -60); glVertex3f(18, 10, -60)
            glEnd()
        else:                            # box (construction/stations)
            self._draw_box(24, 12, 34)
        glEndList()
        self.ship_lists[shape] = lst
        return lst

    def _draw_station(self, e: Entity):
        color = self._owner_color(e.owner)
        sd = self.ds.stations.get(e.data_id)
        if sd is None:
            return
        glPushMatrix()
        glTranslatef(e.pos.x, e.pos.y, e.pos.z)
        glRotatef(self.time * 3.0, 0, 1, 0)
        r = e.radius
        if e.data_id == "command_station":
            # central core + ring + 4 spokes
            glPushMatrix()
            glRotatef(-90, 1, 0, 0)
            glColor3f(*color)
            self._draw_sphere(r * 0.35, 14, 8)
            glPopMatrix()
            glLineWidth(4.0)
            glBegin(GL_LINE_LOOP)
            for i in range(36):
                a = i / 36 * 2 * math.pi
                glVertex3f(math.sin(a) * r, 0, math.cos(a) * r)
            glEnd()
            glBegin(GL_LINES)
            for i in range(4):
                a = i / 4 * 2 * math.pi
                glVertex3f(0, 0, 0)
                glVertex3f(math.sin(a) * r, 0, math.cos(a) * r)
            glEnd()
        else:
            # generic station: stacked boxes + ring
            glColor3f(*color)
            glPushMatrix()
            self._draw_box(r * 0.9, r * 0.5, r * 0.9)
            glPopMatrix()
            glPushMatrix()
            glRotatef(90, 1, 0, 0)
            glPushMatrix()
            glScalef(1, 1, 0.3)
            self._draw_box(r * 1.4, r * 0.3, r * 1.4)
            glPopMatrix()
            glPopMatrix()
            glLineWidth(2.5)
            glColor3f(color[0] * 0.7, color[1] * 0.7, color[2] * 0.7)
            glBegin(GL_LINE_LOOP)
            for i in range(30):
                a = i / 30 * 2 * math.pi
                glVertex3f(math.sin(a) * r * 1.2, 0, math.cos(a) * r * 1.2)
            glEnd()
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
                glColor4f(1.0, 0.6 * a + 0.3, 0.2 * a, a * 0.8)
                self._flat_ring(pos, r)
            elif kind in ("impact", "hull_hit"):
                a = max(0.0, 1.0 - t / 0.35)
                if a <= 0:
                    continue
                glColor4f(color[0], color[1], color[2], a)
                self._flat_ring(pos, 10 + 30 * (1 - a))
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
            elif kind in ("jump_charge", "jump_arrive"):
                a = max(0.0, 1.0 - t / 1.0)
                glColor4f(0.5, 0.7, 1.0, a * 0.7)
                self._flat_ring(pos, 60 + 160 * (1 - a))
            elif kind == "fire":
                a = max(0.0, 1.0 - t / 2.0)
                glColor4f(1.0, 0.5, 0.2, a * 0.5)
                self._flat_ring(pos, fx.get("size", 40) * 1.4)
            elif kind == "muzzle":
                a = max(0.0, 1.0 - t / 0.15)
                if a > 0:
                    glColor4f(color[0], color[1], color[2], a * 0.8)
                    self._flat_ring(pos, 14)
            elif kind == "shield_down":
                a = max(0.0, 1.0 - t / 0.6)
                glColor4f(0.5, 0.8, 1.0, a * 0.8)
                self._flat_ring(pos, 80)
            elif kind == "emp":
                a = max(0.0, 1.0 - t / 0.8)
                glColor4f(0.6, 0.4, 1.0, a * 0.7)
                self._flat_ring(pos, 50 + 120 * (1 - a))
        glDepthMask(True)
        glDisable(GL_BLEND)

    def _flat_ring(self, pos, radius):
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
        # rendered by UI layer (2D), not here
        pass


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