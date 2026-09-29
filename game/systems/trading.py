"""TradingSystem — trade convoys + raiding (spec §26).

Every interval, each owner with a trade_station spawns a convoy (a utility
hull with cargo) bound for the nearest OTHER trade station. On arrival the
(reward_owner) player is paid the cargo credits; when a convoy is destroyed
by an enemy, the killer loots loot_fraction of the cargo. Convoys are regular
entities (kind "ship", data_id "trade_convoy") so they render, save and are
targetable for free.

Rules config (game_rules.json economy.trading):
  spawn_interval, cargo_credits, loot_fraction, speed, hull, reward_owner
  ("destination" pays the receiver; "source" pays the sender)
"""
from __future__ import annotations

import math

from ..data.store import DataStore
from ..core.vectors import Vec3


class TradingSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()
        eco = self.ds.rules.get("economy", {})
        self.cfg = dict(eco.get("trading", {
            "spawn_interval": 45.0, "cargo_credits": 150.0,
            "loot_fraction": 0.5, "speed": 55.0, "hull": 250.0,
            "reward_owner": "destination",
        }))
        self._timer = 0.0
        state.events.subscribe("unit_destroyed", self._on_unit_destroyed)

    # ------------------------------------------------------------------ spawn
    def _trade_stations(self) -> list:
        return [e for e in self.state.entities.values()
                if e.alive and e.is_station and e.data_id == "trade_station"]

    def _destinations_for(self, src) -> list:
        """Markets `src` can ship to: every OTHER trade station.

        A route needs two ends, so a lone trade station has nowhere to send a
        convoy (see the gate in _spawn_convoys). Trade stations only — routing
        to the owner's own command station would let a player pay themselves
        cargo_credits every interval, an unbounded money loop.
        """
        return [d for d in self._trade_stations() if d.id != src.id]

    def _spawn_convoys(self) -> None:
        st = self.state
        stations = self._trade_stations()
        # NOTE: deliberate gate — trade needs TWO markets. This used to be
        # silently unsatisfiable in practice (the AI only built a station
        # above 4000cr, which it holds for ~1.7% of a match), so trading
        # never ran in a real game. The AI gate and the campaign data were
        # fixed alongside this.
        if len(stations) < 2:
            return
        for src in stations:
            dests = self._destinations_for(src)
            if not dests:
                continue
            dest = min(dests, key=lambda d: src.pos.dist(d.pos))
            cargo = float(self.cfg.get("cargo_credits", 150.0))
            hull = float(self.cfg.get("hull", 250.0))
            e = self._make_convoy(src, dest, cargo, hull)
            st.events.publish("convoy_spawned", entity_id=e.id,
                              owner=src.owner, dest=dest.id,
                              cargo=cargo)

    def _make_convoy(self, src, dest, cargo: float, hull: float):
        from ..core.entity import Entity
        st = self.state
        e = Entity(
            id=st.next_entity_id, kind="ship", owner=src.owner,
            data_id="trade_convoy", pos=src.pos.copy(),
        )
        st.next_entity_id += 1
        st.add_entity(e)
        e.is_ship = True
        e.hull = hull
        e.max_hull = hull
        e.radius = 18.0
        e.cargo_credits = cargo
        e.convoy_dest = dest.id
        e.spawn_time = st.time
        e.name_override = "Trade Convoy"
        # MovementSystem drives integration: convoy "moves" toward the
        # destination every tick (TradingSystem sets the heading/vel too)
        e.order_type = "move"
        e.order_target_id = dest.id
        return e

    # ----------------------------------------------------------------- events
    def _on_unit_destroyed(self, ev) -> None:
        if ev.data.get("data_id") != "trade_convoy":
            return
        st = self.state
        # the killed entity is already purged when this fires — the kill
        # event carries the cargo snapshot
        cargo = float(ev.data.get("cargo_credits", 0.0))
        killer_owner = ev.data.get("killer_owner", -1)
        # the convoy's own owner is the kill event's victim owner
        convoy_owner = ev.data.get("owner", -1)
        loot = cargo * float(self.cfg.get("loot_fraction", 0.5))
        p = st.players.get(killer_owner)
        raid_pos = Vec3.from_dict(ev.data.get("pos") or [0.0, 0.0, 0.0])
        if p is not None and loot > 0:
            p.credits += loot
            st.float_text(raid_pos, f"+{loot:0.0f}cr raided", (1, 0.85, 0.4))
        # publish even when the looter is unresolved so an escort objective can
        # still fail the mission when the cargo is lost to an enemy
        if killer_owner != convoy_owner:
            st.events.publish("convoy_raided", entity_id=ev.data.get("entity_id"),
                              looter=killer_owner, loot=loot,
                              convoy_owner=convoy_owner, cargo=cargo)

    # ----------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        st = self.state
        self._timer += dt
        if self._timer >= float(self.cfg.get("spawn_interval", 45.0)):
            self._timer = 0.0
            self._spawn_convoys()
        pay_destination = \
            self.cfg.get("reward_owner", "destination") == "destination"
        for e in list(st.entities.values()):
            if not e.alive or e.data_id != "trade_convoy":
                continue
            dest = st.entity(e.convoy_dest if e.convoy_dest is not None else -1)
            if dest is None or not dest.alive:
                # destination lost: re-target the nearest other trade station
                alts = self._destinations_for(e)
                if not alts:
                    continue
                dest = min(alts, key=lambda s: e.pos.dist(s.pos))
                e.convoy_dest = dest.id
            d = dest.pos - e.pos
            dist = d.length()
            if dist <= dest.radius + 120:
                convoy_owner = e.owner
                paid = dest.owner if pay_destination else convoy_owner
                p = st.players.get(paid)
                if p is not None and e.cargo_credits > 0:
                    p.credits += e.cargo_credits
                    st.float_text(e.pos,
                                  f"+{e.cargo_credits:0.0f}cr delivered",
                                  (0.6, 1, 0.6))
                    st.events.publish("convoy_arrived", entity_id=e.id,
                                      owner=paid, convoy_owner=convoy_owner,
                                      dest=dest.id, cargo=e.cargo_credits)
                elif p is not None:
                    st.events.publish("convoy_arrived", entity_id=e.id,
                                      owner=paid, convoy_owner=convoy_owner,
                                      dest=dest.id, cargo=0.0)
                e.alive = False
                st.dead_ids.append(e.id)
                continue
            # movement drives the convoy (order_target set at spawn); do NOT
            # write vel here — it would overwrite movement's accel each tick
            # and cap the convoy at a crawl (found via probe)
            d = dest.pos - e.pos
            e.yaw = math.atan2(d.x, d.z)