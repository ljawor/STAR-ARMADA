"""3D vector math.

Simulation uses plain floats and tuples for full serialization/determinism;
no external math dependency. Small helper class keeps call sites readable.
"""
from __future__ import annotations

from game.core import detmath as math  # deterministic sim math, never the platform libm
from dataclasses import dataclass, field


@dataclass(slots=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    # --- construction helpers -------------------------------------------------
    @staticmethod
    def from_polar(yaw: float, pitch: float = 0.0) -> "Vec3":
        cp = math.cos(pitch)
        return Vec3(math.sin(yaw) * cp, math.sin(pitch), math.cos(yaw) * cp)

    def copy(self) -> "Vec3":
        return Vec3(self.x, self.y, self.z)

    def to_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def from_tuple(self, t: tuple[float, float, float]) -> None:
        self.x, self.y, self.z = t

    # --- arithmetic (in place where hot) --------------------------------------
    def __add__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    __rmul__ = __mul__

    def __truediv__(self, s: float) -> "Vec3":
        return Vec3(self.x / s, self.y / s, self.z / s)

    def add_scaled(self, o: "Vec3", s: float) -> None:
        self.x += o.x * s
        self.y += o.y * s
        self.z += o.z * s

    def set_scaled(self, o: "Vec3", s: float) -> None:
        self.x = o.x * s
        self.y = o.y * s
        self.z = o.z * s

    def set(self, o: "Vec3") -> None:
        self.x = o.x
        self.y = o.y
        self.z = o.z

    # --- measures --------------------------------------------------------------
    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    def dist(self, o: "Vec3") -> float:
        return math.sqrt((self.x - o.x) * (self.x - o.x) + (self.y - o.y) * (self.y - o.y)
                  + (self.z - o.z) * (self.z - o.z))

    def dist_sq(self, o: "Vec3") -> float:
        return ((self.x - o.x) * (self.x - o.x) + (self.y - o.y) * (self.y - o.y)
                + (self.z - o.z) * (self.z - o.z))

    def normalized(self) -> "Vec3":
        n = self.length()
        if n < 1e-9:
            return Vec3(0, 0, 1)
        return Vec3(self.x / n, self.y / n, self.z / n)

    def normalize(self) -> None:
        n = self.length()
        if n > 1e-9:
            self.x /= n
            self.y /= n
            self.z /= n

    def dot(self, o: "Vec3") -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o: "Vec3") -> "Vec3":
        return Vec3(
            self.y * o.z - self.z * o.y,
            self.z * o.x - self.x * o.z,
            self.x * o.y - self.y * o.x,
        )

    def lerp(self, o: "Vec3", t: float) -> "Vec3":
        return Vec3(
            self.x + (o.x - self.x) * t,
            self.y + (o.y - self.y) * t,
            self.z + (o.z - self.z) * t,
        )

    def to_dict(self, precise: bool = False):
        if precise:
            return [self.x, self.y, self.z]
        return [round(self.x, 4), round(self.y, 4), round(self.z, 4)]

    @staticmethod
    def from_dict(d):
        return Vec3(d[0], d[1], d[2])