"""Player commands.

All player intent enters the simulation as serialized command objects queued in
GameState.command_queue. The UI and (future) network layer only ever produce these;
GameManager consumes them at tick start. This is the multiplayer seam.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from .vectors import Vec3


@dataclass(slots=True)
class PlayerCommand:
    type: str
    player: int = 0
    # common payload (kept flat for easy serialization)
    unit_ids: tuple[int, ...] = ()
    target_pos: tuple[float, float, float] | None = None
    target_id: int | None = None
    station_kind: str | None = None
    ship_id: str | None = None
    tech_id: str | None = None
    ability_id: str | None = None
    formation: str | None = None
    stance: str | None = None
    name: str | None = None
    commander: str | None = None

    def to_dict(self) -> dict:
        d = {"type": self.type, "player": self.player}
        for k in ("target_id", "station_kind", "ship_id", "tech_id", "ability_id",
                  "formation", "stance", "name", "commander"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        if self.unit_ids:
            d["unit_ids"] = list(self.unit_ids)
        if self.target_pos is not None:
            d["target_pos"] = list(self.target_pos)
        return d

    @staticmethod
    def from_dict(d: dict) -> "PlayerCommand":
        kwargs = dict(d)
        if "unit_ids" in kwargs:
            kwargs["unit_ids"] = tuple(kwargs["unit_ids"])
        tp = kwargs.get("target_pos")
        if tp is not None:
            kwargs["target_pos"] = (tp[0], tp[1], tp[2])
        return PlayerCommand(**kwargs)


def _xyz(t):
    """Accept Vec3 (.x/.y/.z) or plain tuple/list — returns (x, y, z)."""
    if t is None:
        return None
    if hasattr(t, "x"):
        return (t.x, t.y, t.z)
    return (t[0], t[1], t[2])


def MoveCommand(player: int, unit_ids, target: Vec3) -> PlayerCommand:
    return PlayerCommand("move", player, unit_ids=tuple(unit_ids),
                         target_pos=_xyz(target))


def AttackCommand(player: int, unit_ids, target_id: int) -> PlayerCommand:
    return PlayerCommand("attack", player, unit_ids=tuple(unit_ids), target_id=target_id)


def AttackMoveCommand(player: int, unit_ids, target: Vec3) -> PlayerCommand:
    return PlayerCommand("attack_move", player, unit_ids=tuple(unit_ids),
                         target_pos=_xyz(target))


def StopCommand(player: int, unit_ids) -> PlayerCommand:
    return PlayerCommand("stop", player, unit_ids=tuple(unit_ids))


def HoldCommand(player: int, unit_ids) -> PlayerCommand:
    return PlayerCommand("hold", player, unit_ids=tuple(unit_ids))


def BuildStationCommand(player: int, builder_id: int, station_kind: str,
                        pos: Vec3) -> PlayerCommand:
    return PlayerCommand("build_station", player, unit_ids=(builder_id,),
                         station_kind=station_kind,
                         target_pos=_xyz(pos))


def BuildShipCommand(player: int, shipyard_id: int, ship_id: str,
                     count: int = 1) -> PlayerCommand:
    return PlayerCommand("build_ship", player, unit_ids=(shipyard_id,),
                         ship_id=ship_id, name=str(count))


def ColonizeCommand(player: int, colonizer_ids, planet_id: int) -> PlayerCommand:
    return PlayerCommand("colonize", player, unit_ids=tuple(colonizer_ids),
                         target_id=planet_id)


def ResearchCommand(player: int, station_id: int, tech_id: str) -> PlayerCommand:
    return PlayerCommand("research", player, unit_ids=(station_id,), tech_id=tech_id)


def AbilityCommand(player: int, unit_ids, ability_id: str,
                   target_id: int | None = None, target: Vec3 | None = None) -> PlayerCommand:
    tp = _xyz(target) if target else None
    return PlayerCommand("ability", player, unit_ids=tuple(unit_ids),
                         ability_id=ability_id, target_id=target_id, target_pos=tp)


def FleetCreateCommand(player: int, unit_ids, name: str, commander: str | None = None,
                       formation: str = "line") -> PlayerCommand:
    return PlayerCommand("fleet_create", player, unit_ids=tuple(unit_ids),
                         name=name, commander=commander, formation=formation)


def FleetSetStanceCommand(player: int, fleet_id: int, stance: str) -> PlayerCommand:
    return PlayerCommand("fleet_stance", player, target_id=fleet_id, stance=stance)


def JumpCommand(player: int, unit_ids, target: Vec3) -> PlayerCommand:
    return PlayerCommand("jump", player, unit_ids=tuple(unit_ids),
                         target_pos=_xyz(target))


COMMAND_TYPES = {
    "move", "attack", "attack_move", "stop", "hold", "build_station", "build_ship",
    "colonize", "research", "ability", "fleet_create", "fleet_stance", "jump",
}