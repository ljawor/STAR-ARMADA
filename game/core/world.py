"""Ids, spatial grid, fleets, projectiles: core mutable state containers."""
from __future__ import annotations

from dataclasses import dataclass, field
from .vectors import Vec3


class IdGenerator:
    __slots__ = ("_next",)

    def __init__(self, start: int = 1) -> None:
        self._next = start

    def next(self) -> int:
        v = self._next
        self._next += 1
        return v

    def peek(self) -> int:
        return self._next

    def set_next(self, v: int) -> None:
        self._next = max(self._next, v)


@dataclass(slots=True)
class SpatialGrid:
    """Uniform grid for neighbor queries. Cell size in world units."""
    cell: float = 400.0
    cells: dict = field(default_factory=dict)   # (cx,cy,cz) -> set[int]

    def _key(self, x: float, y: float, z: float):
        c = self.cell
        return (int(x // c), int(y // c), int(z // c))

    def rebuild(self, entities: dict) -> None:
        self.cells.clear()
        for e in entities.values():
            if not e.alive:
                continue
            self.cells.setdefault(self._key(e.pos.x, e.pos.y, e.pos.z), set()).add(e.id)

    def query_sphere(self, entities: dict, pos: Vec3, radius: float) -> list[int]:
        out: list[int] = []
        c = self.cell
        x0, y0, z0 = self._key(pos.x - radius, pos.y - radius, pos.z - radius)
        x1, y1, z1 = self._key(pos.x + radius, pos.y + radius, pos.z + radius)
        r2 = radius * radius
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                for cz in range(z0, z1 + 1):
                    ids = self.cells.get((cx, cy, cz))
                    if not ids:
                        continue
                    for eid in ids:
                        e = entities.get(eid)
                        if e is not None and e.alive and e.pos.dist_sq(pos) <= r2:
                            out.append(eid)
        return out

    def query_point_cell(self, pos: Vec3) -> set[int]:
        return self.cells.get(self._key(pos.x, pos.y, pos.z), set())


@dataclass(slots=True)
class Fleet:
    id: int
    owner: int
    name: str
    commander: str | None = None          # aggressive|defensive|logistics|recon
    formation: str = "line"
    stance: str = "aggressive"            # aggressive|defensive|hold|retreat
    member_ids: set = field(default_factory=set)
    flagship_id: int | None = None
    xp: float = 0.0
    rally_point: tuple | None = None      # last formation-move destination
    _last_move_issue: float = -999.0      # last time formation orders were issued

    def to_dict(self) -> dict:
        return {
            "id": self.id, "owner": self.owner, "name": self.name,
            "commander": self.commander, "formation": self.formation,
            "stance": self.stance, "member_ids": sorted(self.member_ids),
            "flagship_id": self.flagship_id, "xp": round(self.xp, 2),
            "rally_point": list(self.rally_point) if self.rally_point else None,
        }

    @staticmethod
    def from_dict(d: dict) -> "Fleet":
        f = Fleet(d["id"], d["owner"], d["name"])
        f.commander = d.get("commander")
        f.formation = d.get("formation", "line")
        f.stance = d.get("stance", "aggressive")
        f.member_ids = set(d.get("member_ids", []))
        f.flagship_id = d.get("flagship_id")
        f.xp = d.get("xp", 0.0)
        rp = d.get("rally_point")
        f.rally_point = tuple(rp) if rp else None
        return f


@dataclass(slots=True)
class Projectile:
    id: int
    owner: int
    weapon_id: str
    pos: Vec3
    vel: Vec3
    target_id: int
    damage: float
    shield_mult: float
    armor_mult: float
    system_mult: float
    life: float
    is_beam: bool = False
    color: tuple = (1.0, 0.8, 0.3)
    size: float = 2.0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "owner": self.owner, "weapon_id": self.weapon_id,
            "pos": self.pos.to_dict(), "vel": self.vel.to_dict(),
            "target_id": self.target_id, "damage": round(self.damage, 2),
            "shield_mult": self.shield_mult, "armor_mult": self.armor_mult,
            "system_mult": self.system_mult, "life": round(self.life, 3),
            "is_beam": self.is_beam, "color": list(self.color), "size": self.size,
        }

    @staticmethod
    def from_dict(d: dict) -> "Projectile":
        return Projectile(
            id=d["id"], owner=d["owner"], weapon_id=d["weapon_id"],
            pos=Vec3.from_dict(d["pos"]), vel=Vec3.from_dict(d["vel"]),
            target_id=d["target_id"], damage=d["damage"],
            shield_mult=d["shield_mult"], armor_mult=d["armor_mult"],
            system_mult=d["system_mult"], life=d["life"],
            is_beam=d.get("is_beam", False),
            color=tuple(d.get("color", (1, 0.8, 0.3))),
            size=d.get("size", 2.0),
        )