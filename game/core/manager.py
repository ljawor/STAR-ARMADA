"""GameManager — owns GameState and steps all systems in fixed order.

The tick pipeline is the multiplayer seam: identical state + identical commands =
identical results. No wall-clock reads inside the simulation; `dt` comes from the
driver (fixed-step in the live game, whatever the test chooses headless).
"""
from __future__ import annotations

import math

from ..data.store import DataStore
from ..core.state import GameState, PlayerState
from ..core.events import EventBus
from ..core.vectors import Vec3
from ..core.world import Fleet
from ..systems import (UnitFactory, MovementSystem, SeparationSystem, WeaponSystem,
                       ProjectileSystem, DamageSystem, AbilitySystem, EconomySystem,
                       TradingSystem,
                       ConstructionSystem, ResearchSystem, FormationSystem,
                       SquadronSystem, VictorySystem, MissionSystem, CommandHandler)
from ..ai import AIManager
from ..systems.visibility import VisibilitySystem


class GameManager:
    def __init__(self, state: GameState | None = None, mission_def: dict | None = None,
                 mods: list[str] | None = None):
        self.state = state or GameState()
        self.state.events = EventBus()
        DataStore.reset()
        self.ds = DataStore(mods=mods)

        # transient combat plumbing (not saved; rebuilt after load)
        self.state.damage_queue = []
        self.state.dead_ids = []

        # systems
        self.factory = UnitFactory(self.state)
        self.visibility = VisibilitySystem(self.state)
        self.state._visibility_system = self.visibility
        self.movement = MovementSystem(self.state)
        self.separation = SeparationSystem(self.state)
        self.weapons = WeaponSystem(self.state)
        self.projectiles = ProjectileSystem(self.state)
        self.damage = DamageSystem(self.state)
        self.abilities = AbilitySystem(self.state)
        self.economy = EconomySystem(self.state)
        self.trading = TradingSystem(self.state)
        self.construction = ConstructionSystem(self.state)
        self.construction.factory = self.factory
        # render/input reach the live validator through the state object
        self.state._construction_system = self.construction
        self.research = ResearchSystem(self.state)
        self.formations = FormationSystem(self.state)
        self.squadrons = SquadronSystem(self.state)
        self.victory = VictorySystem(self.state)
        self.mission = MissionSystem(self.state, mission_def)
        self.commands = CommandHandler(self.state, self.construction, self.research,
                                       self.formations, self.abilities)
        self.ai = AIManager(self.state)
        self.state.dmg_system = self.damage
        self._capacity_timer = 0.0
        self.visibility.update()

    # ------------------------------------------------------------------ setup
    def load_map(self, map_def: dict) -> None:
        """Populate state from a map JSON definition."""
        st = self.state
        st.map_info.name = map_def.get("id", "map")
        st.map_info.bounds = float(map_def.get("bounds", 24000))
        st.map_info.nebulas = map_def.get("nebulas", [])
        st.map_info.jump_points = map_def.get("jump_points", [])
        st.map_info.star = map_def.get("star", {})
        # neutral map features as entities (asteroid fields are entities so
        # mining validation can find them by data_id)
        for a in map_def.get("asteroid_fields", []):
            self.factory.spawn_planet({
                "id": a["id"], "name": a["id"].replace("_", " ").title(),
                "pos": a["pos"], "radius": a.get("radius", 1000),
                "type": "asteroid_field"})
        for g in map_def.get("gas_giants", []):
            self.factory.spawn_planet({
                "id": g["id"], "name": g["id"].replace("_", " ").title(),
                "pos": g["pos"], "radius": g.get("radius", 2000),
                "type": "gas_giant"})
        for pd in map_def.get("planets", []):
            self.factory.spawn_planet(pd)
        # players
        for pdef in map_def.get("players", []):
            p = PlayerState(
                id=pdef["slot"], faction=pdef.get("faction", "imperial"),
                is_ai=bool(pdef.get("is_ai", False)),
                ai_difficulty=pdef.get("ai_difficulty", "normal"),
                name=pdef.get("name", f"P{pdef['slot']}"),
                team=int(pdef.get("team", pdef["slot"])),
            )
            fac = self.ds.factions.get(p.faction)
            res = fac.starting_resources if fac else {}
            p.credits = float(res.get("credits", 8000))
            p.materials = float(res.get("materials", 4000))
            p.energy = float(res.get("energy", 2000))
            p.crew = float(res.get("crew", 4000))
            # per-player color: hue-shifted variant of the faction color so two
            # players of the SAME faction still read as distinct on the field
            base = tuple(fac.color if fac else (0.6, 0.6, 0.6))
            import colorsys
            hue_shift = [0.0, 0.42, 0.62, 0.2][p.id % 4]
            r_, g_, b_ = colorsys.rgb_to_hls(*base)
            p.color = colorsys.hls_to_rgb((r_ + hue_shift) % 1.0,
                                          min(0.62, max(0.45, 0.55 * (1.0 + 0.22 - 0.06 * p.id))),
                                          0.62)
            explicit_color = pdef.get("color")
            if (isinstance(explicit_color, (list, tuple)) and len(explicit_color) == 3
                    and all(type(c) in (int, float) and 0 <= c <= 1
                            and math.isfinite(c) for c in explicit_color)):
                p.color = tuple(explicit_color)
            st.players[p.id] = p
            self._spawn_start_units(p.id, pdef.get("start_units", {}),
                                    pdef.get("start", [0, 0, 0]))
        EconomySystem.recompute_command_capacity(st)

        self.visibility.update()

    def _spawn_start_units(self, player_id: int, start_units: dict, start_pos) -> None:
        st = self.state
        anchor = Vec3(*start_pos)
        # deploy ring faces AWAY from map center: starting positions sit near
        # map edges, so the inward ring used to drop units inside a planet's
        # keep-out bubble (ships then stalled at the rim)
        base_ang = math.atan2(anchor.x, anchor.z) if (abs(anchor.x) + abs(anchor.z)) > 1.0 else 0.0
        p = st.players.get(player_id)
        faction = p.faction if p else "imperial"
        ship_for = {
            "constructor": {"imperial": "imperial_constructor", "rebel": "rebel_constructor",
                             "confederacy": "confed_constructor",
                             "syndicate": "syndicate_constructor"},
            "colonizer": {"imperial": "imperial_colonizer", "rebel": "rebel_colonizer",
                           "confederacy": "confed_colonizer"},
            "squadron": {"imperial": "imperial_tie_squadron", "rebel": "rebel_x_squadron",
                          "confederacy": "confed_vulture_squadron",
                          "syndicate": "syndicate_raid_squadron"},
            "corvette": {"imperial": "imperial_corvette", "rebel": "rebel_corvette",
                          "confederacy": "confed_corvette",
                          "syndicate": "syndicate_corvette"},
            "frigate": {"imperial": "imperial_frigate", "rebel": "rebel_frigate",
                         "confederacy": "confed_frigate", "syndicate": "syndicate_frigate"},
            "cruiser": {"imperial": "imperial_cruiser", "rebel": "rebel_cruiser",
                         "confederacy": "confed_cruiser", "syndicate": "syndicate_cruiser"},
            "battleship": {"imperial": "imperial_battleship", "rebel": "rebel_battleship",
                            "confederacy": "confed_battleship"},
            "supercapital": {"imperial": "imperial_supercapital",
                              "rebel": "rebel_supercapital",
                              "confederacy": "confed_supercapital"},
        }
        ring = 0
        for kind, count in start_units.items():
            count = int(count)
            for _ in range(count):
                # start the arc pointing outward from map center, spread ±
                ang = base_ang + (ring - (sum(int(c) for c in start_units.values()) - 1) * 0.5) * 0.55
                pos = Vec3(anchor.x + math.sin(ang) * (900 + ring * 60), 0,
                           anchor.z + math.cos(ang) * (900 + ring * 60))
                ring += 1
                if kind == "command_station":
                    self.factory.spawn_station("command_station", player_id, anchor)
                elif kind in ("mining_station", "shipyard", "research_station",
                              "trade_station", "defense_platform",
                              "sensor_station", "fighter_platform",
                              "repair_dock", "energy_relay"):
                    self.factory.spawn_station(kind, player_id, pos)
                else:
                    sid = ship_for.get(kind, {}).get(faction)
                    if sid:
                        self.factory.spawn_ship(sid, player_id, pos, yaw=ang)

    @staticmethod
    def start_skirmish(map_def: dict, mission_def: dict | None = None,
                       mods: list[str] | None = None) -> "GameManager":
        gm = GameManager(mission_def=mission_def, mods=mods)
        gm.load_map(map_def)
        return gm

    @staticmethod
    def start_mission(map_def: dict, mission_def: dict,
                      mods: list[str] | None = None) -> "GameManager":
        """Campaign mission: loadout overrides, custom enemy, mission wiring.

        Player 0 gets the mission loadout (resources + start units); the map's
        slot-1 player is replaced by the mission's enemy force (faction, team,
        units). MissionSystem drives objectives + mission_complete/failed.
        """
        gm = GameManager(mission_def=mission_def, mods=mods)
        # map players: [human, enemy] — rewrite slot 1 from the mission enemy
        enemy = mission_def.get("enemy", {})
        map_players = [dict(p) for p in map_def.get("players", [])]
        if len(map_players) > 1 and enemy:
            map_players[1]["faction"] = enemy.get("faction", "syndicate")
            map_players[1]["team"] = int(enemy.get("team", 1))
            map_players[1]["is_ai"] = True
            map_players[1]["name"] = "Enemy"
            if enemy.get("start_units"):
                map_players[1]["start_units"] = dict(enemy["start_units"])
        # Do not explore using provisional map units replaced by the loadout.
        loadout = mission_def.get("loadout", {})
        if "start_units" in loadout and map_players:
            map_players[0]["start_units"] = {}
        mdef = dict(map_def, players=map_players)
        gm.load_map(mdef)
        # apply mission loadout to the human player (slot 0)
        loadout = mission_def.get("loadout", {})
        st = gm.state
        p0 = st.players.get(0)
        if p0 is not None:
            res = loadout.get("resources", {})
            p0.credits = float(res.get("credits", p0.credits))
            p0.materials = float(res.get("materials", p0.materials))
            p0.energy = float(res.get("energy", p0.energy))
            p0.crew = float(res.get("crew", p0.crew))
        # spawn loadout units: clear map start_units for player 0 by despawning
        # what load_map already created, then spawn the mission loadout
        spawn = loadout.get("start_units")
        if spawn is not None:
            for e in [e for e in st.entities.values()
                      if e.alive and e.owner == 0
                      and (e.is_ship or e.is_station or e.is_squadron)]:
                e.alive = False
            st.entities = {k: v for k, v in st.entities.items() if v.alive}
            start = map_players[0].get("start", [0, 0, 0])
            gm._spawn_start_units(0, spawn, start)
        EconomySystem.recompute_command_capacity(st)
        gm.visibility.update()
        return gm

    # ------------------------------------------------------------------ tick
    def step(self, dt: float) -> None:
        st = self.state
        if st.game_over:
            return
        st.tick += 1
        st.time += dt

        # 0. commands
        self.visibility.update()
        self.commands.consume()

        # 0.5 hyperspace jump charging (spec §17)
        self._update_jumps(dt)

        # 1. spatial grid
        st.grid.rebuild(st.entities)

        # 2-4. movement, separation, squadron behavior
        self.movement.update(dt)
        self.separation.update(dt)
        self.squadrons.update(dt)

        # 5. Remember post-movement coverage before combat can kill observers.
        # Live detection itself never depends on these exploration passes.
        self.visibility.update()
        self.weapons.update(dt)

        # 6. projectiles fly, queue impacts
        self.projectiles.update(dt)

        # 7. damage resolution (single writer)
        self.damage.update(dt)

        # 8. abilities
        self.abilities.update(dt)

        # 9. economy
        self.economy.update(dt)

        # 10. construction
        self.construction.update(dt)

        # 11. research
        self.research.update(dt)

        # 12. formations maintenance
        self.formations.update(dt)

        # 13. AI
        self.ai.update(dt)

        # 14. command capacity (1 Hz)
        self._capacity_timer += dt
        if self._capacity_timer >= 1.0:
            self._capacity_timer = 0.0
            EconomySystem.recompute_command_capacity(st)

        # 15. trading, victory & mission
        self.trading.update(dt)
        self.victory.update(dt)
        self.mission.update(dt)
        self.visibility.update()

        # 16. effects aging
        for fx in st.effects:
            fx["t"] += dt
        if st.effects:
            st.effects = [f for f in st.effects if f["t"] < 6.0]
        for ft in st.floating_texts:
            ft["t"] += dt
        if st.floating_texts:
            st.floating_texts = [f for f in st.floating_texts if f["t"] < 2.5]

    def _update_jumps(self, dt: float) -> None:
        from ..systems.jump import jump_destination, jump_footprint_valid, clear_jump_orders
        st = self.state
        for e in sorted(st.entities.values(), key=lambda e: e.id):
            if not e.alive or e.jump_charge <= 0:
                continue
            # Restored charges still require safe geometry and a real ship. Do
            # NOT recheck exploration: an earlier group arrival can reveal it.
            target = jump_destination(st, e.owner, e.jump_target, require_unexplored=False)
            if (not math.isfinite(e.jump_charge) or not e.is_ship or e.hull <= 0
                    or e.is_squadron or e.is_station or e.is_planet
                    or e.data_id not in self.ds.ships
                    or self.ds.ships[e.data_id].is_squadron or target is None
                    or not jump_footprint_valid(st, e.owner, target, e.radius,
                                                require_unexplored=False)):
                e.jump_charge = 0.0
                e.jump_target = None
                clear_jump_orders(e)
                continue
            e.jump_charge -= dt
            if e.jump_charge <= 0:
                e.pos.set(target)
                clear_jump_orders(e)
                e.jump_charge = 0.0
                e.jump_target = None
                st.spawn_effect("jump_arrive", e.pos.copy(), size=e.radius)
                st.float_text(e.pos, "HYPERSPACE EXIT", (0.6, 0.8, 1.0))
                st.events.publish("jump_complete", entity_id=e.id, owner=e.owner)

    # ------------------------------------------------------------------ queries
    def player_entities(self, player_id: int) -> list:
        return [e for e in self.state.entities.values()
                if e.alive and e.owner == player_id]