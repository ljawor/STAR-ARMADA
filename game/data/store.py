"""DataStore — loads and validates all JSON assets, resolves ids at runtime.

Asset search order: assets/data (built-in) then mods/<name>/data (overrides by
filename). Validation is strict: unknown weapon/ability/tech references raise at
load time, not mid-battle.
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _find_assets_dir() -> str:
    env = os.environ.get("STAR_ARMADA_DATA")
    if env and os.path.isdir(env):
        return env
    # frozen (PyInstaller) build: assets live under sys._MEIPASS/assets
    if hasattr(sys, "_MEIPASS"):
        frozen = os.path.join(sys._MEIPASS, "assets", "data")
        if os.path.isdir(frozen):
            return frozen
    return os.path.join(ROOT, "assets", "data")


@dataclass(slots=True)
class WeaponData:
    id: str
    display_name: str
    type: str
    damage: float
    range: float
    reload: float
    projectile_speed: float
    accuracy: float
    shield_mult: float
    armor_mult: float
    system_mult: float
    energy_cost: float = 0.0
    hardpoint: str = "front"          # front|rear|left|right|all
    color: tuple = (1.0, 0.8, 0.3)
    size: float = 2.0
    is_beam: bool = False
    targets: str = "all"              # all|fighters|capital|station


@dataclass(slots=True)
class ShipData:
    id: str
    display_name: str
    faction: str
    category: str                     # fighter_squadron|corvette|frigate|cruiser|battleship|supercapital|construction
    cost_credits: float
    cost_materials: float
    cost_energy: float
    crew_cost: float
    command_cost: int
    build_time: float
    hull: float
    shield_quad: float
    shield_regen: float
    speed: float
    turn_rate: float
    radius: float
    sensor_range: float
    weapons: list = field(default_factory=list)          # list of {weapon, count, arcs}
    abilities: list = field(default_factory=list)
    systems: dict = field(default_factory=dict)          # name -> max hp
    hangar_capacity: int = 0
    is_squadron: bool = False
    squadron_size: int = 0
    is_construction: bool = False
    can_build_stations: list = field(default_factory=list)
    can_colonize: bool = False
    veteran_xp: float = 100.0
    max_rank: int = 5


@dataclass(slots=True)
class StationData:
    id: str
    display_name: str
    cost_credits: float
    cost_materials: float
    cost_energy: float
    crew_cost: float
    build_time: float
    hull: float
    shield_quad: float
    shield_regen: float
    radius: float
    sensor_range: float
    weapons: list = field(default_factory=list)
    abilities: list = field(default_factory=list)
    systems: dict = field(default_factory=dict)
    # economy / function
    income: dict = field(default_factory=dict)            # resource -> per second
    builds_ships: list = field(default_factory=list)      # ship ids or ["*"]
    research: bool = False
    storage: dict = field(default_factory=dict)           # resource -> cap bonus
    command_capacity: int = 0
    requires_range: dict | None = None                    # {"asteroid": 900} etc
    repair_rate: float = 0.0
    fighter_capacity: int = 0
    build_role: str = ""          # "" all · "warships" excludes engineering hulls


@dataclass(slots=True)
class AbilityData:
    id: str
    display_name: str
    cooldown: float
    energy_cost: float
    duration: float
    radius: float = 0.0
    effects: dict = field(default_factory=dict)
    description: str = ""


@dataclass(slots=True)
class TechData:
    id: str
    display_name: str
    faction: str
    branch: str
    tier: int
    cost_credits: float
    cost_materials: float
    cost_energy: float
    research_time: float
    requires: list = field(default_factory=list)
    effects: dict = field(default_factory=dict)
    description: str = ""


@dataclass(slots=True)
class FactionData:
    id: str
    display_name: str
    color: tuple
    starting_resources: dict = field(default_factory=dict)
    command_base: int = 20
    traits: list = field(default_factory=list)
    playable: bool = True


def _color(v, default):
    try:
        return tuple(float(x) for x in v)
    except Exception:
        return default


class DataStore:
    _instance: "DataStore | None" = None

    def __init__(self, assets_dir: str | None = None, mods: list[str] | None = None):
        self.assets_dir = assets_dir or _find_assets_dir()
        self.weapons: dict[str, WeaponData] = {}
        self.ships: dict[str, ShipData] = {}
        self.stations: dict[str, StationData] = {}
        self.abilities: dict[str, AbilityData] = {}
        self.techs: dict[str, TechData] = {}
        self.factions: dict[str, FactionData] = {}
        self.maps: dict[str, dict] = {}
        self.rules: dict = {}
        self.campaign: dict = {}
        self.mod_files: dict[str, str] = {}      # relative path -> file content (mod loader)
        self._load_all(mods or [])
        DataStore._instance = self

    # ------------------------------------------------------------- access
    @classmethod
    def get(cls) -> "DataStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def resolve_weapon(self, wid: str) -> WeaponData:
        w = self.weapons.get(wid)
        if w is None:
            raise KeyError(f"Unknown weapon id '{wid}'")
        return w

    def resolve_ship(self, sid: str) -> ShipData:
        s = self.ships.get(sid)
        if s is None:
            raise KeyError(f"Unknown ship id '{sid}'")
        return s

    def resolve_station(self, sid: str) -> StationData:
        s = self.stations.get(sid)
        if s is None:
            raise KeyError(f"Unknown station id '{sid}'")
        return s

    def resolve_ability(self, aid: str) -> AbilityData:
        a = self.abilities.get(aid)
        if a is None:
            raise KeyError(f"Unknown ability id '{aid}'")
        return a

    def resolve_tech(self, tid: str) -> TechData:
        t = self.techs.get(tid)
        if t is None:
            raise KeyError(f"Unknown tech id '{tid}'")
        return t

    def command_cost(self, e) -> int:
        """Command points this unit consumes (0 if it has no ship data).

        Must stay total: trade_convoy is a simulated ship with deliberately no
        ShipData entry (TradingSystem mints it directly), and this is reached
        from the HUD's command-capacity readout on every frame. An unguarded
        resolve_ship() here crashed the game the moment a convoy existed.
        """
        if e.is_squadron or e.is_ship:
            s = self.ships.get(e.data_id)
            return s.command_cost if s is not None else 0
        return 0

    def unit_name(self, e) -> str:
        if e.name_override:
            return e.name_override
        try:
            if e.is_station:
                return self.resolve_station(e.data_id).display_name
            if e.is_ship or e.is_squadron:
                return self.resolve_ship(e.data_id).display_name
            if e.is_planet:
                return e.data_id.replace("_", " ").title()
        except KeyError:
            pass
        return e.data_id.replace("_", " ").title()

    def ship_visual(self, data_id: str) -> dict:
        """Renderer hint: procedural shape description per ship category."""
        if data_id == "trade_convoy":
            return {"shape": "box", "scale": 0.7}   # cargo container hull
        s = self.ships.get(data_id)
        if not s:
            return {"shape": "box", "scale": 1.0}
        shapes = {
            "fighter_squadron": {"shape": "wedge", "scale": 0.45},
            "corvette": {"shape": "needle", "scale": 0.7},
            "frigate": {"shape": "needle", "scale": 1.0},
            "cruiser": {"shape": "cruiser", "scale": 1.6},
            "battleship": {"shape": "dagger", "scale": 2.4},
            "supercapital": {"shape": "dagger", "scale": 4.2},
            "construction": {"shape": "box", "scale": 0.8},
        }
        return shapes.get(s.category, {"shape": "needle", "scale": 1.0})

    # ------------------------------------------------------------- loading
    def _read(self, relpath: str) -> dict:
        path = os.path.join(self.assets_dir, relpath)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_all(self, mods: list[str]) -> None:
        self.rules = self._read("game_rules.json")
        self._load_weapons()
        self._load_abilities()
        self._load_factions()
        self._load_ships()
        self._load_stations()
        self._load_tech()
        self._load_maps()
        self._load_campaign()
        for mod in mods:
            self._load_mod(mod)
        self._validate()

    def _load_weapons(self) -> None:
        for wid, w in self._read("weapons/weapons.json")["weapons"].items():
            self.weapons[wid] = WeaponData(
                id=wid, display_name=w["name"], type=w["type"],
                damage=float(w["damage"]), range=float(w["range"]),
                reload=float(w["reload"]), projectile_speed=float(w.get("projectile_speed", 800)),
                accuracy=float(w.get("accuracy", 0.85)),
                shield_mult=float(w.get("shield_mult", 1.0)),
                armor_mult=float(w.get("armor_mult", 1.0)),
                system_mult=float(w.get("system_mult", 0.5)),
                energy_cost=float(w.get("energy_cost", 0.0)),
                hardpoint=w.get("hardpoint", "front"),
                color=_color(w.get("color"), (1.0, 0.8, 0.3)),
                size=float(w.get("size", 2.0)),
                is_beam=bool(w.get("is_beam", False)),
                targets=w.get("targets", "all"),
            )

    def _load_abilities(self) -> None:
        for aid, a in self._read("abilities/abilities.json")["abilities"].items():
            self.abilities[aid] = AbilityData(
                id=aid, display_name=a["name"], cooldown=float(a["cooldown"]),
                energy_cost=float(a.get("energy_cost", 0)),
                duration=float(a.get("duration", 0)),
                radius=float(a.get("radius", 0)),
                effects=a.get("effects", {}), description=a.get("description", ""))

    def _load_factions(self) -> None:
        for fid, f in self._read("factions/factions.json")["factions"].items():
            self.factions[fid] = FactionData(
                id=fid, display_name=f["name"],
                color=_color(f.get("color"), (0.5, 0.5, 0.5)),
                starting_resources=f.get("starting_resources", {}),
                command_base=int(f.get("command_base", 20)),
                traits=f.get("traits", []),
                playable=bool(f.get("playable", True)))

    def _load_ships(self) -> None:
        for fname in ("imperial.json", "rebel.json", "confederacy.json", "syndicate.json"):
            rel = os.path.join("ships", fname)
            path = os.path.join(self.assets_dir, rel)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sid, s in data["ships"].items():
                self.ships[sid] = ShipData(
                    id=sid, display_name=s["name"], faction=s["faction"],
                    category=s["category"],
                    cost_credits=float(s["cost"]["credits"]),
                    cost_materials=float(s["cost"].get("materials", 0)),
                    cost_energy=float(s["cost"].get("energy", 0)),
                    crew_cost=float(s.get("crew_cost", 0)),
                    command_cost=int(s.get("command_cost", 1)),
                    build_time=float(s.get("build_time", 10)),
                    hull=float(s["hull"]), shield_quad=float(s.get("shield_quad", 0)),
                    shield_regen=float(s.get("shield_regen", 0)),
                    speed=float(s.get("speed", 20)), turn_rate=float(s.get("turn_rate", 10)),
                    radius=float(s.get("radius", 20)),
                    sensor_range=float(s.get("sensor_range", 1200)),
                    weapons=list(s.get("weapons", [])),
                    abilities=list(s.get("abilities", [])),
                    systems=dict(s.get("systems", {})),
                    hangar_capacity=int(s.get("hangar_capacity", 0)),
                    is_squadron=bool(s.get("is_squadron", False)),
                    squadron_size=int(s.get("squadron_size", 0)),
                    is_construction=bool(s.get("is_construction", False)),
                    can_build_stations=list(s.get("can_build_stations", [])),
                    can_colonize=bool(s.get("can_colonize", False)),
                    veteran_xp=float(s.get("veteran_xp", 100)),
                    max_rank=s.get("max_rank", 5),
                )

    def _load_stations(self) -> None:
        for sid, s in self._read("stations/stations.json")["stations"].items():
            self.stations[sid] = StationData(
                id=sid, display_name=s["name"],
                cost_credits=float(s["cost"]["credits"]),
                cost_materials=float(s["cost"].get("materials", 0)),
                cost_energy=float(s["cost"].get("energy", 0)),
                crew_cost=float(s.get("crew_cost", 0)),
                build_time=float(s.get("build_time", 20)),
                hull=float(s["hull"]), shield_quad=float(s.get("shield_quad", 0)),
                shield_regen=float(s.get("shield_regen", 0)),
                radius=float(s.get("radius", 60)),
                sensor_range=float(s.get("sensor_range", 1500)),
                weapons=list(s.get("weapons", [])),
                abilities=list(s.get("abilities", [])),
                systems=dict(s.get("systems", {})),
                income=dict(s.get("income", {})),
                builds_ships=list(s.get("builds_ships", [])),
                research=bool(s.get("research", False)),
                storage=dict(s.get("storage", {})),
                command_capacity=int(s.get("command_capacity", 0)),
                requires_range=dict(s.get("requires_range") or {}),
                repair_rate=float(s.get("repair_rate", 0)),
                fighter_capacity=int(s.get("fighter_capacity", 0)),
                build_role=str(s.get("build_role", "")))

    def _load_tech(self) -> None:
        for tid, t in self._read("technology/technology.json")["technologies"].items():
            self.techs[tid] = TechData(
                id=tid, display_name=t["name"], faction=t["faction"],
                branch=t["branch"], tier=int(t["tier"]),
                cost_credits=float(t["cost"].get("credits", 0)),
                cost_materials=float(t["cost"].get("materials", 0)),
                cost_energy=float(t["cost"].get("energy", 0)),
                research_time=float(t["research_time"]),
                requires=list(t.get("requires", [])),
                effects=dict(t.get("effects", {})),
                description=t.get("description", ""))

    def _load_maps(self) -> None:
        maps_dir = os.path.join(self.assets_dir, "maps")
        if os.path.isdir(maps_dir):
            for fn in sorted(os.listdir(maps_dir)):
                if fn.endswith(".json"):
                    with open(os.path.join(maps_dir, fn), encoding="utf-8") as f:
                        m = json.load(f)
                    self.maps[m.get("id", fn[:-5])] = m

    def _load_campaign(self) -> None:
        path = os.path.join(self.assets_dir, "campaign", "campaign.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.campaign = json.load(f)

    def _load_mod(self, mod_name: str) -> None:
        """Mod folders: mods/<name>/data/** overrides by relative path; also raw files."""
        mod_dir = os.path.join(ROOT, "mods", mod_name)
        data_dir = os.path.join(mod_dir, "data")
        if not os.path.isdir(mod_dir):
            raise FileNotFoundError(f"Mod not found: {mod_dir}")
        # re-run loads with overridden dir for files present in the mod
        if os.path.isdir(data_dir):
            saved = self.assets_dir
            try:
                self.assets_dir = data_dir
                for rel, loader in (
                    ("weapons/weapons.json", self._load_weapons),
                    ("abilities/abilities.json", self._load_abilities),
                    ("factions/factions.json", self._load_factions),
                    ("ships/imperial.json", None), ("ships/rebel.json", None),
                    ("ships/confederacy.json", None), ("ships/syndicate.json", None),
                    ("stations/stations.json", self._load_stations),
                    ("technology/technology.json", self._load_tech),
                    ("game_rules.json", None),
                ):
                    p = os.path.join(data_dir, rel)
                    if os.path.exists(p):
                        if loader is not None:
                            loader()
                        elif rel.startswith("ships/"):
                            self._load_ship_file(p)
                        else:
                            with open(p, encoding="utf-8") as f:
                                self.rules = json.load(f)
            finally:
                self.assets_dir = saved
        for root, _dirs, files in os.walk(mod_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, mod_dir)
                try:
                    with open(full, encoding="utf-8") as f:
                        self.mod_files[rel] = f.read()
                except Exception:
                    pass
        # re-validate after mod merge
        self._validate()

    def _load_ship_file(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for sid, s in data["ships"].items():
            self.ships[sid] = ShipData(
                id=sid, display_name=s["name"], faction=s["faction"],
                category=s["category"],
                cost_credits=float(s["cost"]["credits"]),
                cost_materials=float(s["cost"].get("materials", 0)),
                cost_energy=float(s["cost"].get("energy", 0)),
                crew_cost=float(s.get("crew_cost", 0)),
                command_cost=int(s.get("command_cost", 1)),
                build_time=float(s.get("build_time", 10)),
                hull=float(s["hull"]), shield_quad=float(s.get("shield_quad", 0)),
                shield_regen=float(s.get("shield_regen", 0)),
                speed=float(s.get("speed", 20)), turn_rate=float(s.get("turn_rate", 10)),
                radius=float(s.get("radius", 20)),
                sensor_range=float(s.get("sensor_range", 1200)),
                weapons=list(s.get("weapons", [])),
                abilities=list(s.get("abilities", [])),
                systems=dict(s.get("systems", {})),
                hangar_capacity=int(s.get("hangar_capacity", 0)),
                is_squadron=bool(s.get("is_squadron", False)),
                squadron_size=int(s.get("squadron_size", 0)),
                is_construction=bool(s.get("is_construction", False)),
                can_build_stations=list(s.get("can_build_stations", [])),
                can_colonize=bool(s.get("can_colonize", False)),
                veteran_xp=float(s.get("veteran_xp", 100)),
                max_rank=s.get("max_rank", 5))

    # ------------------------------------------------------------- validation
    def _validate(self) -> None:
        cfg = self.rules.get("experience", {})
        levels = cfg.get("levels", [0, 120, 320, 700, 1400])
        def finite_number(value):
            return type(value) in (int, float) and math.isfinite(value)
        if (not isinstance(levels, list) or not levels
                or any(not finite_number(v) or v < 0 for v in levels)
                or levels[0] != 0 or any(a >= b for a, b in zip(levels, levels[1:]))):
            raise ValueError("experience levels must start at zero and strictly increase")
        cap = cfg.get("max_effective_level", 5)
        if type(cap) is not int or not 1 <= cap <= 5:
            raise ValueError("experience max_effective_level must be an integer from 1 to 5")
        for key, default in (("xp_per_damage", .01), ("xp_per_kill_fraction", .12)):
            value = cfg.get(key, default)
            if not finite_number(value) or value < 0:
                raise ValueError(f"experience {key} must be finite and nonnegative")
        bonuses = cfg.get("per_level", {})
        for key in ("attack_bonus", "defense_bonus"):
            value = bonuses.get(key, .05)
            if (not finite_number(value) or value < 0
                    or (key == "defense_bonus" and value > .25)):
                raise ValueError(f"experience {key} is outside its valid range")
        for sid, s in self.ships.items():
            if type(s.max_rank) is not int or not 1 <= s.max_rank <= 5:
                raise ValueError(f"Ship '{sid}' max_rank must be an integer from 1 to 5")
            if not finite_number(s.veteran_xp) or s.veteran_xp <= 0:
                raise ValueError(f"Ship '{sid}' veteran_xp must be finite and positive")
            for wref in s.weapons:
                wid = wref["weapon"] if isinstance(wref, dict) else wref
                if wid not in self.weapons:
                    raise ValueError(f"Ship '{sid}' references unknown weapon '{wid}'")
            for aid in s.abilities:
                if aid not in self.abilities:
                    raise ValueError(f"Ship '{sid}' references unknown ability '{aid}'")
        for sid, st in self.stations.items():
            for wref in st.weapons:
                wid = wref["weapon"] if isinstance(wref, dict) else wref
                if wid not in self.weapons:
                    raise ValueError(f"Station '{sid}' references unknown weapon '{wid}'")
            for aid in st.abilities:
                if aid not in self.abilities:
                    raise ValueError(f"Station '{sid}' references unknown ability '{aid}'")
        for tid, t in self.techs.items():
            for req in t.requires:
                if req not in self.techs:
                    raise ValueError(f"Tech '{tid}' requires unknown tech '{req}'")
        for fid, f in self.factions.items():
            for sid in f.traits:
                pass  # traits are free-form tags
        if "imperial" not in self.factions:
            raise ValueError("Core faction 'imperial' missing")