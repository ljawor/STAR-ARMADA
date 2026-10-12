"""Tactical camera: pan / rotate / zoom from fighter scale to tactical overview."""
from __future__ import annotations

import math

import pygame

from OpenGL.GL import (
    glMatrixMode, glLoadIdentity, glGetFloatv,
    GL_MODELVIEW, GL_PROJECTION, GL_MODELVIEW_MATRIX, GL_PROJECTION_MATRIX,
)
from OpenGL.GLU import gluPerspective as _gluPerspective, gluLookAt


class Camera:
    """Orbit-style tactical camera around a target point on the battlefield plane."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.target = [0.0, 0.0, 0.0]
        self.distance = 3000.0
        self.yaw = 45.0        # degrees
        self.pitch = 55.0      # degrees (90 = top-down)
        self.fov = 55.0
        self.near = 20.0
        self.far = 60000.0
        self.follow_id = None
        self.zoom_limits = (180.0, 22000.0)
        self._view = None
        self._proj = None
        self._scene = None
        self._scene_player = lambda: 0
        self._station_angle = lambda: 0.
        self._camera_boxes = ()
        self._safe_cache = None
        self._scene_geometry_key = None

    def bind_scene(self, state, player, station_angle=None):
        """Bind view-only geometry; player/animation getters stay current."""
        if state is not self._scene:
            self._station_angle = lambda: 0.
        self._camera_boxes = ()
        self._safe_cache = self._scene_geometry_key = None
        self._scene, self._scene_player = state, player
        if station_angle is not None:
            self._station_angle = station_angle
        self.refresh_scene()

    def refresh_scene(self):
        if self._scene is not None:
            from render.camera_geometry import scene_boxes, camera_ray
            requested = self._requested_eye()
            ray = camera_ray(self.target, requested, self.near, self.fov,
                             self.width / max(1, self.height), self.height)
            player, angle = self._scene_player(), self._station_angle()
            attached = {e.id: e for e in self._scene.entities.values()
                        if e.is_station and (e.planet_building_slot is not None
                                             or e.satellite_slot is not None)}
            scene = self._scene
            if attached:
                # Leave legacy/ship geometry and its pre-visibility broad phase
                # untouched; attached hardware uses the renderer's full frame.
                from types import SimpleNamespace
                scene = SimpleNamespace(
                    entities={i: e for i, e in scene.entities.items() if i not in attached},
                    players=scene.players, known_entity=scene.known_entity,
                    can_see=scene.can_see)
            boxes = scene_boxes(scene, player, angle, ray)
            if attached:
                from render.planet_building_geometry import station_camera_box
                from render.camera_geometry import box_interval
                from game.data.store import DataStore
                extra = []
                for e in attached.values():
                    if not e.alive or DataStore.get().stations.get(e.data_id) is None:
                        continue
                    box = station_camera_box(self._scene, e, angle)
                    if ray is not None and box_interval(*ray[:2], box, ray[2]) is None:
                        continue
                    if self._scene.can_see(player, e.id):
                        extra.append(box)
                boxes += tuple(extra)
            self._scene_geometry_key = self._geometry_key(requested)
            if boxes != self._camera_boxes:
                self._camera_boxes = boxes
                self._safe_cache = None

    # ------------------------------------------------------------------ setup
    def apply(self, width: int | None = None, height: int | None = None) -> None:
        if width:
            self.width = width
        if height:
            self.height = height
        self.refresh_scene()
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = self.width / max(1, self.height)
        _gluPerspective(self.fov, aspect, self.near, self.far)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        eye = self.eye_position()
        cx, cy, cz = self.target
        _, up, _ = self.basis()
        gluLookAt(eye[0], eye[1], eye[2], cx, cy, cz, *up)
        self._proj = glGetFloatv(GL_PROJECTION_MATRIX)
        self._view = glGetFloatv(GL_MODELVIEW_MATRIX)

    def _requested_eye(self):
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        cx, cy, cz = self.target
        d = self.distance
        ex = cx + d * math.cos(pitch) * math.sin(yaw)
        ey = cy + d * math.sin(pitch)
        ez = cz + d * math.cos(pitch) * math.cos(yaw)
        return (ex, max(ey, 60.0), ez)

    def _geometry_key(self, requested):
        return (tuple(self.target), requested, self.near, self.fov, self.width, self.height)

    def eye_position(self):
        requested = self._requested_eye()
        key = self._geometry_key(requested)
        if self._scene is not None and key != self._scene_geometry_key:
            self.refresh_scene()
        if self._safe_cache is None or self._safe_cache[0] != key:
            from render.camera_geometry import safe_eye
            eye = safe_eye(self.target, requested, self._camera_boxes,
                           self.near, self.fov, self.width / max(1, self.height), self.height)
            self._safe_cache = (key, eye)
        return self._safe_cache[1]

    def basis(self):
        """The gluLookAt basis, including the low-pitch altitude floor."""
        eye = self.eye_position()
        fwd = normalize3(tuple(self.target[i] - eye[i] for i in range(3)))
        yaw = math.radians(self.yaw)
        right = (math.cos(yaw), 0., -math.sin(yaw))
        up = normalize3(cross3(right, fwd))
        return right, up, fwd

    # ------------------------------------------------------------------ input
    def pan(self, dx: float, dy: float) -> None:
        """Pan in camera-relative plane; dx/dy in pixels."""
        scale = self.distance * 0.0016
        yaw = math.radians(self.yaw)
        # right vector on XZ plane
        rx = math.cos(yaw)
        rz = -math.sin(yaw)
        # forward (screen up) vector on XZ plane
        fx = -math.sin(yaw)
        fz = -math.cos(yaw)
        # +dx pans the view right, +dy pans it down the screen: the world
        # scrolls the other way, which is what the arrow/WASD keys promise.
        # (#48: both axes were sign-flipped, so every key panned backwards.)
        self.target[0] += (dx * rx - dy * fx) * scale
        self.target[2] += (dx * rz - dy * fz) * scale
        self.clamp_target()

    def rotate(self, dyaw: float, dpitch: float) -> None:
        self.yaw = (self.yaw + dyaw) % 360.0
        self.pitch = max(8.0, min(89.0, self.pitch + dpitch))

    def zoom(self, factor: float) -> None:
        self.distance = max(self.zoom_limits[0], min(self.zoom_limits[1],
                                                     self.distance * factor))

    def clamp_target(self) -> None:
        b = 26000.0
        self.target[0] = max(-b, min(b, self.target[0]))
        self.target[2] = max(-b, min(b, self.target[2]))

    # ------------------------------------------------------------------ picking
    def screen_to_world(self, mx: float, my: float, plane_y: float = 0.0):
        """Unproject a screen point onto the y=plane_y battlefield plane.

        Returns (wx, wy, wz) or None when the ray points away from the plane.
        Uses the analytic ray from eye through pixel.
        """
        if self._proj is None or self._view is None:
            self.apply()
        eye = self.eye_position()
        # ray direction through pixel center (NDC)
        ndc_x = (mx / self.width) * 2.0 - 1.0
        ndc_y = 1.0 - (my / self.height) * 2.0
        tan_fov = math.tan(math.radians(self.fov) / 2.0)
        aspect = self.width / max(1, self.height)
        # camera basis
        right, up, fwd = self.basis()
        # note: screen up in world = camera up
        dir = normalize3([
            fwd[0] + right[0] * ndc_x * tan_fov * aspect + up[0] * ndc_y * tan_fov,
            fwd[1] + right[1] * ndc_x * tan_fov * aspect + up[1] * ndc_y * tan_fov,
            fwd[2] + right[2] * ndc_x * tan_fov * aspect + up[2] * ndc_y * tan_fov,
        ])
        if abs(dir[1]) < 1e-6:
            return None
        t = (plane_y - eye[1]) / dir[1]
        if t <= 0:
            return None
        return (eye[0] + dir[0] * t, plane_y, eye[2] + dir[2] * t)

    def world_to_screen(self, x: float, y: float, z: float):
        """Analytic projection (no GL matrix reads). (sx, sy) or None if behind/off."""
        eye = self.eye_position()
        right, up, fwd = self.basis()
        vx, vy, vz = x - eye[0], y - eye[1], z - eye[2]
        depth = vx * fwd[0] + vy * fwd[1] + vz * fwd[2]
        if depth <= 1.0:
            return None
        tan_fov = math.tan(math.radians(self.fov) / 2.0)
        aspect = self.width / max(1, self.height)
        nx = (vx * right[0] + vy * right[1] + vz * right[2]) / (depth * tan_fov * aspect)
        ny = (vx * up[0] + vy * up[1] + vz * up[2]) / (depth * tan_fov)
        if abs(nx) > 3.0 or abs(ny) > 3.0:
            return None
        sx = (nx + 1.0) * 0.5 * self.width
        sy = (1.0 - (ny + 1.0) * 0.5) * self.height
        return (sx, sy)


# ----------------------------------------------------------------- small helpers
def cross3(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def normalize3(v):
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if n < 1e-9:
        return (0.0, 0.0, 1.0)
    return (v[0] / n, v[1] / n, v[2] / n)


