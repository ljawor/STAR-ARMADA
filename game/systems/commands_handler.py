"""CommandHandler — consumes PlayerCommands and applies them to state.

The ONLY path from UI/AI intent to world mutation that isn't a system tick.
Keeps the multiplayer seam: commands are data, applied in fixed order.
"""
from __future__ import annotations

from ..core.commands import PlayerCommand
from ..core.vectors import Vec3
from ..data.store import DataStore


class CommandHandler:
    def __init__(self, state, construction, research, formations, abilities):
        self.state = state
        self.construction = construction
        self.research = research
        self.formations = formations
        self.abilities = abilities
        self.ds = DataStore.get()

    def consume(self) -> None:
        st = self.state
        queue, st.command_queue = st.command_queue, []
        for cmd in queue:
            self._apply(cmd)
        # Trading updates after movement; repair legacy hostile endpoints here
        # even on ticks without commands, before movement can read them.
        from .trading import TradingSystem
        TradingSystem.validate_routes(st)

    # ------------------------------------------------------------------ dispatch
    def _apply(self, cmd: PlayerCommand) -> None:
        st = self.state
        t = cmd.type
        fn = getattr(self, "_do_" + t, None)
        if fn is None:
            return
        fn(cmd)

    def _units(self, cmd: PlayerCommand):
        st = self.state
        return [st.entity(uid) for uid in cmd.unit_ids
                if st.entity(uid) is not None
                and st.entity(uid).owner == cmd.player]

    def _do_move(self, cmd: PlayerCommand) -> None:
        pos = Vec3(*cmd.target_pos)
        # fleet-aware: if selection belongs to one fleet, move in formation
        fleet = self._selection_fleet(cmd)
        if fleet is not None:
            self.formations.apply_fleet_move(fleet, pos)
            return
        n = 0
        for e in self._units(cmd):
            if e.is_station or e.is_planet:
                continue
            # spread destinations for large groups
            if len(cmd.unit_ids) > 1:
                import math
                ring = n // 6
                k = n % 6
                ang = k * (math.pi / 3) + ring * 0.5
                spread = 150 + ring * 220
                dest = Vec3(pos.x + math.sin(ang) * spread,
                            pos.y, pos.z + math.cos(ang) * spread)
            else:
                dest = pos
            e.order_type = "move"
            e.order_target_pos = dest
            e.order_target_id = None
            n += 1

    def _do_trade_route(self, cmd: PlayerCommand) -> None:
        from .trading import TradingSystem
        st = self.state
        dest = st.entity(cmd.target_id) if cmd.target_id is not None else None
        if dest is None or not TradingSystem.valid_market(st, cmd.player, dest):
            return
        for e in self._units(cmd):
            if not e.alive or not e.is_ship or e.data_id != "trade_convoy":
                continue
            if not TradingSystem.valid_destination(st, e, dest):
                continue
            e.convoy_dest = dest.id
            e.order_target_id = dest.id
            e.order_target_pos = None
            e.order_type = "move"
            # Validation now sees a consistent endpoint; discard old heading
            # and momentum here, before the first redirected movement tick.
            import math
            e.vel = Vec3()
            direction = dest.pos - e.pos
            e.yaw = math.atan2(direction.x, direction.z)

    def _do_attack(self, cmd: PlayerCommand) -> None:
        st = self.state
        target = st.entity(cmd.target_id or 0)
        if (target is None or not st.is_enemy(cmd.player, target.owner)
                or not st.can_see(cmd.player, target.id)):
            return
        for e in self._units(cmd):
            if e.is_station or e.is_planet:
                continue
            e.order_type = "attack"
            e.order_target_id = target.id
            e.current_target = target.id

    def _do_attack_move(self, cmd: PlayerCommand) -> None:
        pos = Vec3(*cmd.target_pos)
        for e in self._units(cmd):
            if e.is_station or e.is_planet:
                continue
            e.order_type = "attack_move"
            e.order_target_pos = pos
            e.order_target_id = None

    def _do_stop(self, cmd: PlayerCommand) -> None:
        for e in self._units(cmd):
            if e.is_station or e.is_planet:
                continue
            e.order_type = "idle"
            e.order_target_pos = None
            e.order_target_id = None
            e.current_target = None

    def _do_hold(self, cmd: PlayerCommand) -> None:
        for e in self._units(cmd):
            if e.is_station or e.is_planet:
                continue
            e.order_type = "hold"
            e.order_target_pos = None
            e.order_target_id = None

    def _do_build_station(self, cmd: PlayerCommand) -> None:
        if not cmd.unit_ids:
            return
        self.construction.start_station(
            cmd.unit_ids[0], cmd.station_kind, Vec3(*cmd.target_pos), cmd.player)

    def _do_build_ship(self, cmd: PlayerCommand) -> None:
        if not cmd.unit_ids:
            return
        count = int(cmd.name) if cmd.name and cmd.name.isdigit() else 1
        self.construction.start_ship(cmd.unit_ids[0], cmd.ship_id, cmd.player, count)

    def _do_colonize(self, cmd: PlayerCommand) -> None:
        for uid in cmd.unit_ids:
            self.construction.start_colonize(uid, cmd.target_id, cmd.player)

    def _do_research(self, cmd: PlayerCommand) -> None:
        if not cmd.unit_ids:
            return
        self.research.start_research(cmd.player, cmd.unit_ids[0], cmd.tech_id)

    def _do_ability(self, cmd: PlayerCommand) -> None:
        tp = Vec3(*cmd.target_pos) if cmd.target_pos else None
        for e in self._units(cmd):
            self.abilities.activate(e, cmd.ability_id, cmd.target_id, tp)

    def _do_fleet_create(self, cmd: PlayerCommand) -> None:
        st = self.state
        units = self._units(cmd)
        if len(units) < 1:
            return
        # remove members from old fleets; delete fleets left empty
        for u in units:
            old = st.fleets.get(u.fleet_id) if u.fleet_id is not None else None
            if old is not None:
                old.member_ids.discard(u.id)
                if not old.member_ids:
                    del st.fleets[old.id]
            u.fleet_id = None
        fleet_id = st.next_fleet_id
        st.next_fleet_id += 1
        from ..core.world import Fleet
        fleet = Fleet(fleet_id, cmd.player, cmd.name or f"Fleet {fleet_id}")
        fleet.commander = cmd.commander
        fleet.formation = cmd.formation or "line"
        flagship = max(units, key=lambda u: u.max_hull)
        fleet.flagship_id = flagship.id
        for u in units:
            if u.is_station or u.is_planet:
                continue
            u.fleet_id = fleet_id
            fleet.member_ids.add(u.id)
        st.fleets[fleet_id] = fleet
        st.events.publish("fleet_created", fleet_id=fleet_id, owner=cmd.player)

    def _do_fleet_stance(self, cmd: PlayerCommand) -> None:
        fleet = self.state.fleets.get(cmd.target_id or 0)
        if fleet is None or fleet.owner != cmd.player:
            return
        fleet.stance = cmd.stance or "aggressive"
        if fleet.stance == "retreat":
            # rally at home station
            st = self.state
            home = None
            for e in st.entities.values():
                if e.alive and e.is_station and e.owner == cmd.player:
                    home = e.pos.copy()
                    break
            if home is not None:
                self.formations.apply_fleet_move(fleet, home)

    def _do_jump(self, cmd: PlayerCommand) -> None:
        """Hyperspace jump (spec §17): prep time by size, then instant relocation."""
        st = self.state
        ds = self.ds
        from .jump import jump_destination, plan_jump_exits, clear_jump_orders, detach_jumpers
        target = jump_destination(st, cmd.player, cmd.target_pos)
        if target is None:
            return
        rules = ds.rules.get("hyperspace", {})
        prep_per_cp = rules.get("prep_seconds_per_command_point", 1.2)
        min_prep = rules.get("min_prep_seconds", 3.0)
        eligible = []
        for e in {e.id: e for e in self._units(cmd)}.values():
            if (not e.alive or e.hull <= 0 or not e.is_ship
                    or e.is_station or e.is_planet or e.is_squadron):
                continue
            if (e.jump_charge > 0 or e.jump_target is not None
                    or e.ability_cooldowns.get("_jump_cd", 0) > 0):
                continue
            sd = ds.ships.get(e.data_id)
            if sd is not None and not sd.is_squadron:
                eligible.append(e)
        exits = plan_jump_exits(st, cmd.player, eligible, target)
        if exits is None:
            return
        # Planning is atomic: never change fleet membership on rejection.
        detach_jumpers(st, [e for e, _ in exits])
        for e, destination in exits:
            sd = ds.ships[e.data_id]
            prep = max(min_prep, sd.command_cost * prep_per_cp)
            clear_jump_orders(e)
            e.jump_target = destination
            e.jump_charge = prep
            e.ability_cooldowns["_jump_cd"] = rules.get("cooldown_after_jump", 20.0)
            st.spawn_effect("jump_charge", e.pos.copy())
        # charge is processed in GameManager tick (jump_system inline)

    def _selection_fleet(self, cmd: PlayerCommand):
        st = self.state
        fleets = {}
        for uid in cmd.unit_ids:
            e = st.entity(uid)
            if e is not None and e.fleet_id is not None:
                f = st.fleets.get(e.fleet_id)
                if f is not None and f.owner == cmd.player:
                    fleets[e.fleet_id] = f
        # if all selected units are in one fleet, use formation move
        if len(fleets) == 1:
            fleet = next(iter(fleets.values()))
            if fleet.member_ids <= set(cmd.unit_ids):
                return fleet
        return None