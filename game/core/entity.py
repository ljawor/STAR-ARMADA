"""Entity model.

One dataclass covers ships, stations, squadrons and construction ships; role flags
(``is_ship``/``is_station``/``is_squadron``/``is_construction``) select behavior.
Composition keeps save/load flat and modding simple.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .vectors import Vec3

QUADRANTS = ("front", "rear", "left", "right")
SUBSYSTEMS = ("engines", "weapons", "sensors", "shield_gen", "hangar", "life_support")


@dataclass(slots=True)
class SubsystemState:
    hp: float
    max_hp: float


@dataclass(slots=True)
class Entity:
    id: int
    kind: str                       # "ship" | "station" | "squadron" | "planet" | ...
    owner: int                      # player id, -1 neutral
    data_id: str                    # id in DataStore (ship_id / station_id / planet type)
    pos: Vec3 = field(default_factory=Vec3)
    vel: Vec3 = field(default_factory=Vec3)
    yaw: float = 0.0                # facing around Y axis
    radius: float = 20.0

    # role flags
    is_ship: bool = False
    is_station: bool = False
    is_squadron: bool = False
    is_construction: bool = False
    is_planet: bool = False

    # combat
    hull: float = 100.0
    max_hull: float = 100.0
    shields: dict = field(default_factory=lambda: {q: 0.0 for q in QUADRANTS})
    max_shield_quad: float = 0.0
    shield_regen: float = 0.0
    last_hit_time: float = -999.0
    systems: dict = field(default_factory=dict)       # name -> SubsystemState
    alive: bool = True
    xp: float = 0.0
    level: int = 1
    # #77: paid refit level of a station hull (1 = as built). Belongs to the hull,
    # not the owner, so a captured station keeps what was paid for it.
    upgrade_level: int = 1

    # Onboard complement is distinct from the player's unassigned crew pool.
    crew: int = 1
    max_crew: int = 1
    crew_loss_accumulator: float = 0.0
    crew_damage_accumulator: float = 0.0  # actual hull HP toward next casualty
    recruitment_progress: float = 0.0
    crew_cargo: int = 0
    cargo_loss_accumulator: float = 0.0
    crew_mission: dict = field(default_factory=dict)
    boarding: dict = field(default_factory=dict)  # physical craft's persisted mission
    boarding_party_id: int | None = None  # source's active craft; O(1) combat gate

    # orders
    order_type: str = "idle"        # idle|move|attack|attack_move|hold|follow|patrol
    order_target_pos: Vec3 | None = None
    order_target_id: int | None = None
    patrol_a: Vec3 | None = None
    patrol_b: Vec3 | None = None

    # combat runtime
    weapon_cooldowns: dict = field(default_factory=dict)   # weapon idx -> seconds
    current_target: int | None = None
    abandoned_attack_target: int | None = None  # new human order on a derelict only
    retarget_cooldown: float = 0.0

    # abilities (runtime state)
    ability_cooldowns: dict = field(default_factory=dict)  # ability_id -> seconds ready
    ability_active: dict = field(default_factory=dict)     # ability_id -> seconds left
    energy: float = 100.0
    max_energy: float = 100.0

    # economy / construction
    build_queue: list = field(default_factory=list)        # [{"item":..., "time_left":...}]
    colonized_by: int | None = None
    planet_id: int | None = None  # persistent satellite attachment
    satellite_slot: int | None = None
    satellite_orbit_phase: float | None = None
    planet_building_slot: int | None = None
    # #57: slot -> sim time at which the rebuild penalty on a destroyed
    # satellite's slot expires. Site state on the planet, never render state.
    satellite_locks: dict[int, float] = field(default_factory=dict)

    # trading (§26): cargo convoys
    cargo_credits: float = 0.0
    convoy_source: int | None = None  # unknown legacy source cannot authorize trade
    convoy_dest: int | None = None

    # squadrons
    fighter_count: int = 0
    max_fighters: int = 0
    hangar_id: int | None = None       # carrier/station id for reinforce/landing
    launched_from: int | None = None

    # fleets
    fleet_id: int | None = None
    formation_slot: int = 0

    # hyperspace
    jump_charge: float = 0.0           # seconds accumulated toward jump prep
    jump_target: Vec3 | None = None
    # #92 transit phase: after charge expires the hull rides hyperspace along
    # the straight origin→exit corridor. jump_target stays the reserved exit
    # until arrival; jump_charge becomes the seconds left in transit.
    jump_origin: Vec3 | None = None
    jump_travelling: bool = False
    jump_transit_total: float = 0.0

    @property
    def in_jump(self) -> bool:
        """Any hyperspace phase: prep, staged charge or transit."""
        return self.jump_charge > 0 or self.jump_target is not None

    # misc
    name_override: str | None = None
    spawn_time: float = 0.0
    sensor_range: float = 0.0             # base sensor range (from ship/station data)
    _last_damage_state: int = -1

    # ------------------------------------------------------------------ helpers
    @property
    def operational(self) -> bool:
        """Abandoned units remain alive physical hulls, not functional assets."""
        return self.alive and (self.is_planet or self.crew > 0)

    @property
    def is_combat_unit(self) -> bool:
        return (self.is_ship or self.is_squadron or self.is_station) and self.owner >= 0

    def hull_fraction(self) -> float:
        return self.hull / self.max_hull if self.max_hull > 0 else 0.0

    def damage_state(self) -> int:
        """0=pristine 1=light 2=moderate 3=heavy 4=critical (renderer hook)."""
        f = self.hull_fraction()
        if f > 0.9:
            return 0
        if f > 0.7:
            return 1
        if f > 0.5:
            return 2
        if f > 0.3:
            return 3
        return 4

    def subsystem_hp(self, name: str) -> float:
        s = self.systems.get(name)
        return s.hp if s else 0.0

    def subsystem_fraction(self, name: str) -> float:
        s = self.systems.get(name)
        if not s or s.max_hp <= 0:
            return 1.0
        return s.hp / s.max_hp

    def speed_multiplier(self) -> float:
        return 0.25 + 0.75 * max(0.0, self.subsystem_fraction("engines"))

    def damage_multiplier(self) -> float:
        return 0.3 + 0.7 * max(0.0, self.subsystem_fraction("weapons"))

    def sensor_multiplier(self) -> float:
        return 0.25 + 0.75 * max(0.0, self.subsystem_fraction("sensors"))

    def hangar_multiplier(self) -> float:
        return max(0.0, self.subsystem_fraction("hangar"))

    def total_shield(self) -> float:
        return sum(self.shields.values())

    def max_shield_total(self) -> float:
        return self.max_shield_quad * 4

    def alive_shield_quads(self) -> int:
        return sum(1 for v in self.shields.values() if v > 0.0)