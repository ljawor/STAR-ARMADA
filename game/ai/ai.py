"""AI — strategic (1 Hz) + tactical (5 Hz) layers (spec §20/§21/§45).

Strategic: economy (miners/constructors), expansion (colonize, build trade/mining),
research, fleet assembly up to command capacity, defense, attack decisions.
Tactical: per-unit combat micro — intercept, retreat damaged ships, focus targets.
"""
from __future__ import annotations

from ..core.commands import PlayerCommand
from ..core.vectors import Vec3
from ..data.store import DataStore


class AIPlayer:
    """One AI player's brain. Instances live in AIManager; all reads/writes go
    through GameState so AI is replayable/deterministic given the same inputs."""

    def __init__(self, state, player_id: int):
        self.state = state
        self.player_id = player_id
        self.ds = DataStore.get()
        self.decision_timer = 0.0
        self.tactical_timer = 0.0
        self.last_strategic = {}
        self.attack_fleet_id = None

    # ------------------------------------------------------------------ helpers
    def my_units(self, kind=None):
        st = self.state
        out = []
        for e in st.entities.values():
            if e.alive and e.owner == self.player_id:
                if e.is_station and "station" in (kind or ""):
                    out.append(e)
                elif e.is_ship or e.is_squadron:
                    if kind is None or "ship" in kind:
                        out.append(e)
                elif kind is None:
                    out.append(e)
        return out

    def my_stations(self, kind: str | None = None):
        st = self.state
        out = []
        for e in st.entities.values():
            if e.alive and e.is_station and e.owner == self.player_id:
                if kind is None or e.data_id == kind:
                    out.append(e)
        return out

    def my_constructors(self):
        return [e for e in self.my_units()
                if e.is_construction and not self._busy(e)]

    def home_station(self):
        stations = self.my_stations()
        return stations[0] if stations else None

    def _busy(self, e) -> bool:
        return bool(e.build_queue)

    def difficulty(self) -> dict:
        p = self.state.players.get(self.player_id)
        key = p.ai_difficulty if p else "normal"
        return self.ds.rules.get("ai", {}).get("difficulty", {}).get(key, {})

    # ------------------------------------------------------------------ strategic
    def strategic_tick(self, dt: float) -> None:
        st = self.state
        self.decision_timer -= dt
        if self.decision_timer > 0:
            return
        mult = self.difficulty().get("decision_mult", 1.0)
        self.decision_timer = self.ds.rules.get("ai", {}).get("strategic_interval", 1.0) / max(0.5, mult)

        p = st.players.get(self.player_id)
        if p is None:
            return
        home = self.home_station()
        if home is None:
            return

        # 1. economy: keep constructors alive and building
        self._ensure_economy(home)

        # 2. defense platforms when threatened
        self._ensure_defense(home)

        # 3. research
        self._maybe_research()

        # 4. ship production
        self._produce_fleet(home)

        # 5. expansion
        self._maybe_expand(home)

        # 6. attack decision
        self._decide_attack()

    def _ensure_economy(self, home) -> None:
        st = self.state
        ds = self.ds
        constructors = [e for e in self.my_units() if e.is_construction and
                        not e.is_planet and self._is_builder(e)]
        miners = self.my_stations("mining_station")
        trade = self.my_stations("trade_station")
        # count idle constructors with money
        p = st.players.get(self.player_id)
        idle = [c for c in constructors if not c.build_queue]
        # desired: miners >= desired_miners; then trade stations
        desired_miners = int(ds.rules.get("ai", {}).get("desired_miners", 4))
        if len(miners) < desired_miners and idle:
            site = self._find_asteroid_site(home)
            if site:
                self._queue_build(idle[0], "mining_station", site)
                return
        if len(trade) < 2 and p.credits > 4000 and idle:
            self._queue_build(idle[0], "trade_station", self._offset(home, 900))
            return
        # shipyard early
        if not self.my_stations("shipyard") and idle and p.credits > 2200:
            self._queue_build(idle[0], "shipyard", self._offset(home, 700))
            return
        if not self.my_stations("research_station") and idle and p.credits > 2400:
            self._queue_build(idle[0], "research_station", self._offset(home, -700))
            return
        # more constructors if rich
        shipyards = self.my_stations("shipyard")
        if len(constructors) < 2 and shipyards and p.credits > 2500:
            faction = p.faction
            sid = {
                "imperial": "imperial_constructor",
                "rebel": "rebel_constructor",
                "confederacy": "confed_constructor",
                "syndicate": "syndicate_constructor",
            }.get(faction)
            if sid:
                self._queue_ship(shipyards[0], sid, 1)

    def _is_builder(self, e) -> bool:
        sd = self.ds.ships.get(e.data_id)
        return bool(sd and sd.is_construction and not sd.can_colonize)

    def _find_asteroid_site(self, home):
        st = self.state
        # nearest asteroid field without too many of my mining stations nearby
        best, best_d = None, 1e18
        for e in st.entities.values():
            if not e.alive or e.data_id != "asteroid_field":
                continue
            near = sum(1 for m in self.my_stations("mining_station")
                       if m.pos.dist(e.pos) < 1800)
            if near >= 2:
                continue
            d = home.pos.dist_sq(e.pos)
            if d < best_d:
                best, best_d = e, d
        if best is None:
            return None
        import math
        ang = st.rng().uniform(0, 6.28)
        return Vec3(best.pos.x + math.sin(ang) * best.radius * 0.5, 0,
                    best.pos.z + math.cos(ang) * best.radius * 0.5)

    @staticmethod
    def _offset(anchor, dist: float) -> Vec3:
        import math
        ang = anchor.spawn_time * 1.7 % 6.28
        return Vec3(anchor.pos.x + math.sin(ang) * dist, 0,
                    anchor.pos.z + math.cos(ang) * dist)

    def _queue_build(self, builder, station_kind: str, pos: Vec3) -> None:
        st = self.state
        st.queue_command(PlayerCommand(
            "build_station", self.player_id, unit_ids=(builder.id,),
            station_kind=station_kind, target_pos=(pos.x, pos.y, pos.z)))

    def _queue_ship(self, shipyard, ship_id: str, count: int) -> None:
        st = self.state
        st.queue_command(PlayerCommand(
            "build_ship", self.player_id, unit_ids=(shipyard.id,),
            ship_id=ship_id, name=str(count)))

    def _ensure_defense(self, home) -> None:
        st = self.state
        p = st.players.get(self.player_id)
        # threatened? enemy within 2500 of home
        threatened = False
        for e in st.entities.values():
            if e.alive and e.owner >= 0 and st.is_enemy(self.player_id, e.owner) \
                    and (e.is_ship or e.is_squadron) \
                    and e.pos.dist(home.pos) < 2500:
                threatened = True
                break
        defenses = self.my_stations("defense_platform")
        idle = [c for c in self.my_units()
                if c.is_construction and not self._is_builder(c) and not c.build_queue]
        if threatened and len(defenses) < 3 and idle:
            import math
            ang = st.rng().uniform(0, 6.28)
            pos = Vec3(home.pos.x + math.sin(ang) * 500, 0,
                       home.pos.z + math.cos(ang) * 500)
            self._queue_build(idle[0], "defense_platform", pos)
        elif p.credits > 3000 and len(defenses) < 2 and idle:
            import math
            ang = st.rng().uniform(0, 6.28)
            pos = Vec3(home.pos.x + math.sin(ang) * 500, 0,
                       home.pos.z + math.cos(ang) * 500)
            self._queue_build(idle[0], "defense_platform", pos)

    def _maybe_research(self) -> None:
        st = self.state
        p = st.players.get(self.player_id)
        if p.researching:
            return
        stations = [s for s in self.my_stations()
                    if (self.ds.stations.get(s.data_id) is not None
                        and self.ds.stations[s.data_id].research)
                    and not s.build_queue]
        if not stations:
            return
        avail = sorted(_available_techs(st, self.player_id),
                       key=lambda x: self.ds.techs[x].tier)
        p = st.players.get(self.player_id)
        for tid in avail:
            t = self.ds.techs[tid]
            if (p.credits >= t.cost_credits and p.materials >= t.cost_materials
                    and p.energy >= t.cost_energy):
                st.queue_command(PlayerCommand("research", self.player_id,
                                               unit_ids=(stations[0].id,), tech_id=tid))
                return

    def _produce_fleet(self, home) -> None:
        st = self.state
        p = st.players.get(self.player_id)
        faction = p.faction
        shipyard = next((s for s in self.my_stations("shipyard")), None)
        fighter_plat = next((s for s in self.my_stations("fighter_platform")), None)
        cmd_station = home
        # current composition counts (AI keeps a balanced fleet, not spam)
        counts: dict = {}
        for e in self.my_units():
            if e.is_ship or e.is_squadron:
                counts[e.data_id] = counts.get(e.data_id, 0) + 1
        sq = {"imperial": "imperial_tie_squadron", "rebel": "rebel_x_squadron",
              "confederacy": "confed_vulture_squadron",
              "syndicate": "syndicate_raid_squadron"}[faction]
        cv = {"imperial": "imperial_corvette", "rebel": "rebel_corvette",
              "confederacy": "confed_corvette",
              "syndicate": "syndicate_corvette"}[faction]
        fr = {"imperial": "imperial_frigate", "rebel": "rebel_frigate",
              "confederacy": "confed_frigate", "syndicate": "syndicate_frigate"}[faction]
        cr = {"imperial": "imperial_cruiser", "rebel": "rebel_cruiser",
              "confederacy": "confed_cruiser", "syndicate": "syndicate_cruiser"}[faction]
        bs = {"imperial": "imperial_battleship", "rebel": "rebel_battleship",
              "confederacy": "confed_battleship"}.get(faction)
        plan = []
        if p.credits > 600 and counts.get(sq, 0) < 3:
            plan.append((fighter_plat or cmd_station, sq))
        elif p.credits > 1400 and counts.get(cv, 0) < 4:
            plan.append((shipyard or cmd_station, cv))
        elif p.credits > 3500 and counts.get(fr, 0) < 3:
            plan.append((shipyard or cmd_station, fr))
        elif p.credits > 9000 and counts.get(cr, 0) < 2:
            plan.append((shipyard or cmd_station, cr))
        elif bs and p.credits > 16000 and counts.get(bs, 0) < 1:
            plan.append((shipyard or cmd_station, bs))
        for station, ship_id in plan:
            if station is None:
                continue
            if len(station.build_queue) < 2:
                self._queue_ship(station, ship_id, 1)
                return  # one command per tick keeps queue fair

    def _maybe_expand(self, home) -> None:
        st = self.state
        p = st.players.get(self.player_id)
        ds = self.ds
        threshold = ds.rules.get("ai", {}).get("expand_credits", 4000)
        colonizer = next((e for e in self.my_units()
                          if e.is_construction and getattr(
                              self.ds.ships.get(e.data_id), "can_colonize", False)
                          and not e.build_queue), None)
        if colonizer is None:
            # build one
            shipyard = next((s for s in self.my_stations("shipyard")), None)
            faction = p.faction
            sid = {"imperial": "imperial_colonizer", "rebel": "rebel_colonizer",
                   "confederacy": "confed_colonizer"}.get(faction)
            if sid and shipyard and p.credits > 2000 and len(shipyard.build_queue) < 2:
                self._queue_ship(shipyard, sid, 1)
            return
        if p.credits < threshold:
            return
        # nearest uncolonized planet not too close to enemy
        target = None
        best_d = 1e18
        for e in st.entities.values():
            if not e.alive or not e.is_planet or e.colonized_by is not None:
                continue
            if e.data_id in ("gas_giant", "barren"):
                continue
            # skip planets near enemy stations
            near_enemy = any(en.alive and en.is_station and en.owner >= 0
                             and st.is_enemy(self.player_id, en.owner)
                             and en.pos.dist(e.pos) < 3000
                             for en in st.entities.values())
            if near_enemy:
                continue
            d = home.pos.dist_sq(e.pos)
            if d < best_d:
                target, best_d = e, d
        if target is not None:
            st.queue_command(PlayerCommand("colonize", self.player_id,
                                           unit_ids=(colonizer.id,),
                                           target_id=target.id))

    def _decide_attack(self) -> None:
        st = self.state
        p = st.players.get(self.player_id)
        courage = self.difficulty().get("courage",
                                        self.ds.rules.get("ai", {}).get("fleet_courage", 0.85))
        # my combat strength
        my_strength = sum(_unit_strength(self.ds, e) for e in self.my_units()
                          if (e.is_ship or e.is_squadron))
        # enemy strength near my known enemies
        enemy_strength = 0.0
        enemy_target = None
        for e in st.entities.values():
            if e.alive and e.owner >= 0 and st.is_enemy(self.player_id, e.owner):
                enemy_strength += _unit_strength(self.ds, e)
                if enemy_target is None or (e.is_station and not enemy_target.is_station):
                    enemy_target = e
        if my_strength := my_strength:
            pass
        if enemy_target is None:
            return
        if my_strength > enemy_strength * courage * 0.9:
            # assemble all combat ships into one fleet and attack
            combat = [e for e in self.my_units()
                      if (e.is_ship or e.is_squadron)
                      and not e.is_construction
                      and _unit_strength(self.ds, e) > 0]
            if len(combat) >= 4:
                if self.attack_fleet_missing():
                    st.queue_command(PlayerCommand(
                        "fleet_create", self.player_id,
                        unit_ids=tuple(e.id for e in combat),
                        name="Strike Fleet", commander="aggressive",
                        formation="wedge"))
                else:
                    fleet = st.fleets.get(self.attack_fleet_id)
                    if fleet is not None and fleet.stance != "retreat":
                        st.queue_command(PlayerCommand(
                            "move", self.player_id,
                            unit_ids=tuple(fleet.member_ids),
                            target_pos=(enemy_target.pos.x, enemy_target.pos.y,
                                        enemy_target.pos.z)))
        elif self._under_threat():
            # pull fleet home
            fleet = st.fleets.get(self.attack_fleet_id or 0)
            if fleet is not None:
                st.queue_command(PlayerCommand("fleet_stance", self.player_id,
                                               target_id=fleet.id, stance="retreat"))

    def attack_fleet_missing(self) -> bool:
        st = self.state
        fleet = st.fleets.get(self.attack_fleet_id or 0)
        if fleet is None or not fleet.member_ids:
            # find any of my fleets
            for f in st.fleets.values():
                if f.owner == self.player_id:
                    self.attack_fleet_id = f.id
                    return False
            return True
        return False

    @property
    def attack_fleet_id(self):
        return self.last_strategic.get("attack_fleet_id")

    @attack_fleet_id.setter
    def attack_fleet_id(self, v):
        self.last_strategic["attack_fleet_id"] = v

    def _under_threat(self) -> bool:
        st = self.state
        home = self.home_station()
        if home is None:
            return False
        for e in st.entities.values():
            if e.alive and e.owner >= 0 and st.is_enemy(self.player_id, e.owner) \
                    and (e.is_ship or e.is_squadron) and e.pos.dist(home.pos) < 2200:
                return True
        return False

    # ------------------------------------------------------------------ tactical
    def tactical_tick(self, dt: float) -> None:
        st = self.state
        self.tactical_timer -= dt
        if self.tactical_timer > 0:
            return
        self.tactical_timer = self.ds.rules.get("ai", {}).get("tactical_interval", 0.2)
        retreat_frac = self.ds.rules.get("ai", {}).get("retreat_hull_fraction", 0.28)
        home = self.home_station()
        for e in self.my_units():
            if not (e.is_ship or e.is_squadron):
                continue
            if e.is_construction:
                # constructors flee from enemies
                for tid in st.grid.query_sphere(st.entities, e.pos, 1200):
                    t = st.entity(tid)
                    if t and st.is_enemy(self.player_id, t.owner) and (t.is_ship or t.is_squadron):
                        if home is not None:
                            e.order_type = "move"
                            e.order_target_pos = home.pos.copy()
                            e.order_target_id = None
                        break
                continue
            # retreat badly damaged ships
            if e.hull_fraction() < retreat_frac and not e.is_squadron:
                if home is not None:
                    e.order_type = "move"
                    e.order_target_pos = home.pos.copy()
                    e.order_target_id = None
                    e.current_target = None
                continue
            # idle combat ships: acquire nearby targets (WeaponSystem handles firing;
            # here we move toward valid targets so idle units engage)
            if e.order_type == "idle" and not e.is_squadron:
                sd = self.ds.ships.get(e.data_id)
                scan = sd.sensor_range if sd is not None else 1500
                best, best_d = None, 1e18
                for tid in st.grid.query_sphere(st.entities, e.pos, scan):
                    t = st.entity(tid)
                    if t and st.is_enemy(self.player_id, t.owner) and not t.is_planet:
                        d = e.pos.dist_sq(t.pos)
                        if d < best_d:
                            best, best_d = t, d
                if best is not None:
                    e.order_type = "attack"
                    e.order_target_id = best.id
                    e.current_target = best.id


class AIManager:
    def __init__(self, state):
        self.state = state
        self.ais: dict[int, AIPlayer] = {}

    def ensure(self) -> None:
        for pid, p in self.state.players.items():
            if p.is_ai and pid not in self.ais:
                self.ais[pid] = AIPlayer(self.state, pid)

    def update(self, dt: float) -> None:
        self.ensure()
        for ai in self.ais.values():
            ai.strategic_tick(dt)
            ai.tactical_tick(dt)


# --------------------------------------------------------------------- helpers
def _unit_strength(ds, e) -> float:
    if e.is_squadron:
        sd = ds.ships.get(e.data_id)
        if sd is None:
            return 0.0
        return (e.hull_fraction() * (e.fighter_count / max(1, e.max_fighters))
                * (sd.hull + sd.shield_quad * 4) * 0.001)
    if e.is_ship:
        sd = ds.ships.get(e.data_id)
        if sd is None:
            return 0.0
        return (e.hull_fraction() * (sd.hull + sd.shield_quad * 4) * 0.001)
    if e.is_station:
        sd = ds.stations.get(e.data_id)
        if sd is None:
            return 0.0
        return (e.hull_fraction() * (sd.hull + sd.shield_quad * 4) * 0.0006)
    return 0.0


def _available_techs(state, player_id: int) -> list:
    """Local copy of ResearchSystem.available_techs to avoid a circular import."""
    ds = DataStore.get()
    p = state.players.get(player_id)
    if p is None:
        return []
    out = []
    for tid, t in ds.techs.items():
        if t.faction != p.faction:
            continue
        if tid in p.researched or tid in p.researching:
            continue
        if all(r in p.researched for r in t.requires):
            out.append(tid)
    return out