"""ConstructionSystem — station construction by constructor ships, ship building at
shipyards/fighter platforms/command stations, colonization of planets.

Construction costs are paid up front; time passes on the builder's queue; can be
cancelled (refund 50%). Constructor ships must be in range of a valid site
(mining near asteroids, energy relay near gas giants).
"""
from __future__ import annotations

from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..core.vectors import Vec3
from ..data import balance
from ..data.store import DataStore
from . import stats
from . import upgrades
from .unit_factory import UnitFactory
from .colonies import colony_rules


def _body_clearance(body, station_radius: float) -> float:
    """Minimum distance from a body's centre a station of `station_radius` may sit.

    Mirrors the planet-spacing rule in ``check_site`` (``< (body.radius +
    station.radius) * 1.6``) and adds a small margin, so a placement window
    derived from this value can never land inside the exclusion zone. Sharing the
    term is the point: when the two were written independently they contradicted
    each other and the station became unbuildable.
    """
    return (body.radius + station_radius) * 1.6 + 50.0


def type_can_build_ship(ds, station_id: str, faction: str, ship_id: str) -> bool:
    """Catalogue gate for a station *type* and a faction: the ship gate without a level.

    `ConstructionSystem.station_can_build_ship` is this predicate plus the player's
    per-level build gate (#106); the HUD rows and the balance screen ask this one, so no
    surface can offer a hull the simulation would refuse, or hide one it would accept.
    """
    sd = ds.stations.get(station_id)
    shd = ds.ships.get(ship_id)
    if sd is None or shd is None or not getattr(sd, 'builds_ships', None):
        return False
    if shd.faction != faction:
        return False
    if shd.can_colonize and station_id != "command_station":
        return False
    if ship_id in sd.builds_ships:
        return True
    if "*" not in sd.builds_ships:
        return False
    if sd.build_role == "warships" and shd.category == "construction":
        # shipyards build the fleet; engineering hulls come from the command station
        # (which cannot build warships)
        return False
    return True


def buildable_ship_ids(ds, station_id: str, faction: str) -> list[str]:
    """Hulls this station type may lay down for a faction at *some* level, in panel order.

    `["*"]` expands to the whole catalogue (sorted, as the shipyard panel lists it); an
    explicit list keeps its declared order.
    """
    sd = ds.stations.get(station_id)
    if sd is None or not getattr(sd, 'builds_ships', None):
        return []
    candidates = sorted(ds.ships) if "*" in sd.builds_ships else list(sd.builds_ships)
    return [sid for sid in candidates if type_can_build_ship(ds, station_id, faction, sid)]


def required_level(ds, station_id: str, ship_id: str) -> int:
    """Minimum refit level a station type needs before it may lay this hull down."""
    return balance.build_level(ds.rules, station_id, ship_id)


class ConstructionSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()
        self.factory: UnitFactory | None = None  # injected by GameManager

    # ------------------------------------------------------------------ validation
    def can_pay(self, player_id: int, cost: dict) -> bool:
        p = self.state.players.get(player_id)
        if p is None:
            return False
        return (p.credits >= cost.get("credits", 0)
                and p.materials >= cost.get("materials", 0)
                and p.energy >= cost.get("energy", 0)
                and p.crew >= cost.get("crew", 0))

    def pay(self, player_id: int, cost: dict) -> None:
        p = self.state.players.get(player_id)
        p.credits -= cost.get("credits", 0)
        p.materials -= cost.get("materials", 0)
        p.energy -= cost.get("energy", 0)
        p.crew -= cost.get("crew", 0)
        st = self.state.stats.setdefault(str(player_id), {"kills": 0, "losses": 0})
        st["credits_spent"] = st.get("credits_spent", 0) + cost.get("credits", 0)

    def refund(self, player_id: int, cost: dict, fraction: float = 0.5) -> None:
        p = self.state.players.get(player_id)
        if p is None:
            return
        p.credits += cost.get("credits", 0) * fraction
        p.materials += cost.get("materials", 0) * fraction
        p.energy += cost.get("energy", 0) * fraction
        p.crew += cost.get("crew", 0) * fraction

    def command_available(self, player_id: int, cmd_cost: int) -> bool:
        p = self.state.players.get(player_id)
        if p is None:
            return False
        used = p.command_used(self.state.entities)
        return used + cmd_cost <= p.command_capacity

    # ------------------------------------------------------------------ station build
    def build_range(self) -> float:
        """How far from the builder a station may be sited."""
        return float(self.ds.rules.get("economy", {}).get("station_build_range", 1200))

    def too_far_to_build(self, pos, builder) -> tuple[bool, float, float]:
        """(too_far, distance, limit) — the builder must be able to reach the site.

        This is deliberately NOT part of ``check_site``. That function answers
        "is this ground legal", and the AI's site finders use it to pick a site
        before the builder has moved there — adding proximity would make the
        relay (which lives out by a gas giant, sometimes 7000u from home)
        unfindable. Proximity is a property of the ORDER, so it is enforced
        where the order is issued.
        """
        x, y, z = (pos.x, pos.y, pos.z) if hasattr(pos, "x") else (pos[0], pos[1], pos[2])
        lim = self.build_range()
        d = math.dist((x, y, z), (builder.pos.x, builder.pos.y, builder.pos.z))
        return d > lim, d, lim

    def start_station(self, builder_id: int, station_id: str, pos: Vec3,
                      player_id: int) -> bool:
        st = self.state
        builder = st.entity(builder_id)
        if (builder is None or not builder.operational or builder.owner != player_id
                or not builder.is_ship or not builder.is_construction):
            return False
        unit = self.ds.ships.get(builder.data_id)
        if unit is None or unit.can_colonize or station_id in ('defense_satellite', 'attack_satellite',
                'planet_extractor', 'planet_trade_hub', 'planet_shield_generator', 'planet_pulsar_cannon'):
            return False
        # The builder has to actually be able to PLACE the thing — otherwise a
        # player can order a station on the far side of the map and the
        # constructor silently flies there and builds it.
        far, d, lim = self.too_far_to_build(pos, builder)
        if far:
            st.float_text(builder.pos,
                          f"Constructor is {d - lim:,.0f}u out of range "
                          f"({d:,.0f}u, max {lim:,.0f}u)",
                          (1, 0.5, 0.4))
            return False
        ok, reason = self.check_site(station_id, pos, builder)
        if not ok:
            # Rejection remains authoritative, but feedback must not name a
            # hidden obstruction. Re-evaluate only the player's known site.
            preview_ok, preview_reason = self.check_site(
                station_id, pos, builder, viewer=player_id)
            reason = "site unavailable" if preview_ok else preview_reason
            st.float_text(builder.pos, f"Cannot build: {reason}", (1, 0.5, 0.4))
            return False
        sd = self.ds.resolve_station(station_id)
        cost = self.factory.station_build_cost(station_id)
        if not self.command_available(player_id, sd.command_cost):
            st.float_text(builder.pos, "Command capacity reached", (1, 0.6, 0.4))
            return False
        if not self.can_pay(player_id, cost):
            missing = self.missing_resources(player_id, cost)
            st.float_text(builder.pos, f"Insufficient resources: {missing}",
                          (1, 0.6, 0.4))
            return False
        self.pay(player_id, cost)
        build_time = sd.build_time / max(0.1, stats.effective_build_speed(st, player_id))
        builder.build_queue.append({
            "kind": "station", "item": station_id, "time_left": build_time,
            "total": build_time, "pos": [pos.x, pos.y, pos.z], "status": "paid",
        })
        # move builder to site
        builder.order_type = "move"
        builder.order_target_pos = pos.copy()
        builder.order_target_id = None
        return True

    def missing_resources(self, player_id: int, cost: dict) -> str:
        """Human-readable list of what the player is short of."""
        p = self.state.players.get(player_id)
        if p is None:
            return "no player"
        parts = []
        if p.credits < cost.get("credits", 0):
            parts.append(f"credits ({p.credits:0.0f}/{cost.get('credits', 0):0.0f})")
        if p.materials < cost.get("materials", 0):
            parts.append(f"materials ({p.materials:0.0f}/{cost.get('materials', 0):0.0f})")
        if p.energy < cost.get("energy", 0):
            parts.append(f"energy ({p.energy:0.0f}/{cost.get('energy', 0):0.0f})")
        if p.crew < cost.get("crew", 0):
            parts.append(f"crew ({p.crew:0.0f}/{cost.get('crew', 0):0.0f})")
        return ", ".join(parts) if parts else "unknown"

    # ---------------------------------------------------------- site validation
    def station_min_distance(self, station_id, other_id, other_radius, player_id,
                             other_owner=None) -> float:
        """Shared center-distance rule for live hardware and paid sites."""
        radius = self.ds.resolve_station(station_id).radius
        minimum = (radius + other_radius) * 1.6
        economy = self.ds.rules.get('economy', {})
        if station_id == other_id == 'trade_station':
            minimum = max(minimum, float(economy.get('trade_station_min_distance', 1500)))
        if (other_id == 'command_station' and other_owner is not None
                and self.state.is_enemy(player_id, other_owner)):
            minimum = max(minimum, float(economy.get('enemy_command_build_min_distance', 3000)))
        return minimum

    def _check_station_spacing(self, station_id, pos, player_id, *, viewer=None,
                               ignore_work=None, ignore_entity=None) -> tuple[bool, str]:
        st = self.state
        coords = (pos.x, pos.y, pos.z) if hasattr(pos, 'x') else pos
        if not all(math.isfinite(v) for v in coords):
            return False, 'invalid site coordinates'
        if abs(coords[0]) > st.map_info.bounds or abs(coords[2]) > st.map_info.bounds:
            return False, 'outside the map bounds'
        for e in st.entities.values():
            if not e.alive or e is ignore_entity:
                continue
            if e.is_station and (viewer is None or st.can_see(viewer, e.id)):
                minimum = self.station_min_distance(station_id, e.data_id, e.radius, player_id, e.owner)
                distance = math.dist(coords, (e.pos.x, e.pos.y, e.pos.z))
                if e.satellite_slot is not None and e.planet_id is not None:
                    from .satellite_orbits import orbit_geometry, ring_distance
                    parent = st.entity(e.planet_id)
                    if parent is not None:
                        plan = orbit_geometry(st, parent, e.radius, e.satellite_slot)
                        if plan is not None:
                            distance = min(distance, ring_distance(parent.pos, *plan, Vec3(*coords)))
                if distance < minimum:
                    if e.data_id == 'command_station' and st.is_enemy(player_id, e.owner):
                        return False, 'too close to hostile command station'
                    return False, f"too close to {e.data_id.replace('_', ' ')}"
            # Placement shares allied paid reservations, not arbitrary detected
            # production details. Planet terrain owner remains neutral: control
            # AND the paid source must authorize this particular reservation.
            queue_owner = e.colonized_by if e.is_planet else e.owner
            allies = st.allied_player_ids(viewer) if viewer is not None else None
            if allies is not None and queue_owner not in allies:
                continue
            for work in e.build_queue:
                if (allies is not None and e.is_planet
                        and (work.get('source_owner') != queue_owner
                             or work.get('source_owner') not in allies)):
                    continue
                if (work is ignore_work or work.get('kind') not in ('station', 'satellite')
                        or work.get('status') != 'paid' or work.get('pos') is None):
                    continue
                other = self.ds.stations.get(work.get('item'))
                if other is None:
                    continue
                # Only live command centers impose territorial exclusion;
                # queued hardware reserves its physical footprint/market spacing.
                minimum = self.station_min_distance(station_id, other.id, other.radius, player_id)
                distance = math.dist(coords, work['pos'])
                if work['kind'] == 'satellite' and e.is_planet and type(work.get('slot')) is int:
                    from .satellite_orbits import orbit_geometry, ring_distance
                    plan = orbit_geometry(st, e, other.radius, work['slot'])
                    if plan is not None:
                        distance = min(distance, ring_distance(e.pos, *plan, Vec3(*coords)))
                if distance < minimum:
                    return False, f"too close to {other.id.replace('_', ' ')} site"
        return True, ''

    def check_site(self, station_id: str, pos, builder, *,
                   viewer: int | None = None) -> tuple[bool, str]:
        """Return (ok, reason) for a tuple or Vec3 site.

        The default is authoritative ground validation, without builder range
        (AI site finders validate before travelling). Explicit ``viewer`` mode
        is a knowledge-limited placement preview: range is checked first, and
        a green ghost is not a guarantee that the real build will succeed.
        """
        x, y, z = (pos.x, pos.y, pos.z) if hasattr(pos, 'x') else pos
        if not all(math.isfinite(v) for v in (x, y, z)):
            return False, 'invalid site coordinates'
        if viewer is not None:
            far, d, lim = self.too_far_to_build(pos, builder)
            if far:
                return False, (f"constructor {d - lim:,.0f}u out of range "
                               f"({d:,.0f}u, max {lim:,.0f}u)")
        st = self.state
        sd = self.ds.resolve_station(station_id)
        x, y, z = (pos.x, pos.y, pos.z) if hasattr(pos, "x") else (
            pos[0], pos[1], pos[2])
        # map bounds
        b = st.map_info.bounds
        if abs(x) > b or abs(z) > b:
            return False, "outside the map bounds"
        # spacing vs planets and other stations
        # Preview obstructions must be currently detected, never charted/stale.
        # Default callers (AI and sim) retain the complete physical entity list.
        for e in st.entities.values():
            if not e.alive:
                continue
            if viewer is not None and not st.can_see(viewer, e.id):
                continue
            if e.is_planet and e.data_id == "asteroid_field":
                continue        # building inside asteroid fields is the point
            if e.is_planet:
                if math.dist((x, y, z), (e.pos.x, e.pos.y, e.pos.z)) < \
                        e.radius + sd.radius + 100:
                    return False, f"too close to planet {e.name_override or e.data_id}"
        ok, reason = self._check_station_spacing(station_id, pos, builder.owner, viewer=viewer)
        if not ok:
            return ok, reason
        # requires_range: some stations must be near a specific body.
        # The window has to be measured from the body's ACTUAL radius, because
        # the planet-spacing rule above keeps stations ~1.6-2.4x the body
        # radius away from its centre. energy_relay's flat 1100u sat entirely
        # inside that exclusion zone (gas giants are r2200 -> nearest legal
        # spot 2355u), so the station could not be built anywhere at all.
        for req_kind, rng in (sd.requires_range or {}).items():
            ok = False
            for e in st.entities.values():
                if not (e.alive and e.data_id == req_kind):
                    continue
                clear = _body_clearance(e, sd.radius) if req_kind != "asteroid_field" else 0.0
                if math.dist((x, y, z), (e.pos.x, e.pos.y, e.pos.z)) <= clear + rng:
                    ok = True
                    break
            if not ok:
                return False, f"must be within {rng:0.0f}u of {req_kind.replace('_', ' ')}"
        # can the builder legally build this station type?
        # .get() not resolve_ship(): the ``unit is not None`` test below was
        # dead code because resolve_ship RAISES on an unknown id, so this
        # crashed for any builder without ship data (e.g. a station).
        unit = self.ds.ships.get(builder.data_id)
        if unit is not None and station_id not in unit.can_build_stations:
            return False, f"{unit.display_name} cannot build this station"
        return True, ""

    # ------------------------------------------------------------------ ship build
    def station_can_build_ship(self, station, ship_id: str) -> bool:
        """Catalogue gate plus the player's per-level build gate (#106).

        The level gate lives here rather than at the call sites because every route into a
        shipyard queue already funnels through this predicate: the panel rows, the AI's
        `build_ship` intent and the human command seam. A gate enforced anywhere else would
        be a gate the AI walks around.
        """
        player = self.state.players.get(station.owner)
        if player is None or not type_can_build_ship(self.ds, station.data_id,
                                                   player.faction, ship_id):
            return False
        return (upgrades.station_level(station)
                >= required_level(self.ds, station.data_id, ship_id))

    def start_ship(self, station_id: int, ship_id: str, player_id: int,
                   count: int = 1) -> int:
        """Queue `count` ships; returns number queued."""
        st = self.state
        station = st.entity(station_id)
        if station is None or not station.operational or not station.is_station or station.owner != player_id:
            return 0
        sd = self.ds.resolve_ship(ship_id)
        if not self.station_can_build_ship(station, ship_id):
            st.float_text(station.pos, "Cannot build here", (1, 0.6, 0.4))
            return 0
        queued = 0
        for _ in range(count):
            cost = self.factory.ship_build_cost(ship_id)
            if not self.can_pay(player_id, cost):
                if queued == 0:
                    st.float_text(station.pos, "Insufficient resources", (1, 0.6, 0.4))
                break
            if not self.command_available(player_id, sd.command_cost):
                if queued == 0:
                    st.float_text(station.pos, "Command capacity reached", (1, 0.6, 0.4))
                break
            self.pay(player_id, cost)
            build_time = sd.build_time / max(0.1, stats.effective_build_speed(st, player_id))
            station.build_queue.append({
                "kind": "ship", "item": ship_id, "time_left": build_time,
                "total": build_time, "status": "paid",
            })
            queued += 1
        return queued

    # ------------------------------------------------------------------ cancels
    def cancel_build(self, target_id, player_id: int, index: int = 0) -> bool:
        """Cancel one queued item and pay back half of what it cost (#94).

        `target_id` is whatever holds the queue: a station or constructor cancels
        from its own queue (ships, stations), a colony planet from the paid
        surface/satellite queue it owns — a planet queue reserves a build site or
        orbit slot, so dropping the item releases that reservation with it.
        Refund is `refund()`'s 50%: the other half pays for work already done, and
        command capacity needs no bookkeeping because usage/reservations are
        derived from the live queues. Colonisation is a standing fleet order with
        no resource cost, not paid construction, so re-ordering the ship remains
        the way to stop it.
        """
        st = self.state
        builder = st.entity(target_id) if type(target_id) is int else None
        if builder is None or not builder.alive:
            return False
        if builder.is_planet:
            if builder.colonized_by != player_id:
                return False
            allowed = ('planet_building', 'satellite')
        else:
            if builder.owner != player_id or not builder.operational:
                return False
            allowed = ('ship', 'station', 'satellite', 'station_upgrade')
        queue = builder.build_queue
        if type(index) is not int or not 0 <= index < len(queue):
            return False
        item = queue[index]
        kind = item.get('kind')
        if kind not in allowed:
            st.float_text(builder.pos, 'Cannot cancel this order', (1, 0.6, 0.4))
            return False
        queue.pop(index)
        cost = self._queued_cost(item)
        if cost:
            self.refund(player_id, cost)
        st.float_text(builder.pos, f'Cancelled {item.get("item", "")} · 50% refunded',
                      (1, 0.85, 0.4))
        st.events.publish('build_cancelled', entity_id=builder.id, kind=kind,
                          item=item.get('item'), owner=player_id, index=index)
        return True

    def _queued_cost(self, item: dict) -> dict:
        """Catalogue cost paid when `item` was queued; empty for costless work.

        A refit's price depends on the station's target level and its catalogue cost,
        which the catalogue alone cannot reproduce, so the item carries the exact
        bill that was paid and that is what comes back.
        """
        stored = item.get('cost')
        if isinstance(stored, dict):
            return dict(stored)
        data_id = item.get('item')
        if not data_id:
            return {}
        kind = item.get('kind')
        if kind == 'ship':
            return self.factory.ship_build_cost(data_id)
        if kind in ('station', 'satellite', 'planet_building'):
            return self.factory.station_build_cost(data_id)
        return {}

    # ------------------------------------------------------------------ upgrades
    def start_upgrade(self, station_id, player_id: int) -> bool:
        """Buy the next refit level of an owned station (#77).

        Paid up front and queued on the station's own build queue, so a refit orders
        itself behind any hull already building there. The station keeps operating
        for the whole refit — it is work inside a live hull, not a new one — and the
        timer is fixed at purchase (like satellite and surface work), so an
        under-crewed station cannot stall its own refit forever.
        """
        from .upgrades import eligible, queued_refit, station_level, upgrade_cost, upgrade_time
        st = self.state
        station = st.entity(station_id) if type(station_id) is int else None
        if station is None or not station.alive or not station.operational:
            return False
        if station.owner != player_id or not eligible(station, self.ds):
            return False
        if queued_refit(station) is not None:
            st.float_text(station.pos, 'Refit already in progress', (1, 0.6, 0.4))
            return False
        cost = upgrade_cost(station, self.ds)
        seconds = upgrade_time(station, self.ds)
        if cost is None or seconds is None:
            st.float_text(station.pos, 'Already at maximum level', (1, 0.6, 0.4))
            return False
        if not self.can_pay(player_id, cost):
            missing = self.missing_resources(player_id, cost)
            st.float_text(station.pos, f'Insufficient resources: {missing}', (1, 0.6, 0.4))
            return False
        target = station_level(station) + 1
        self.pay(player_id, cost)
        station.build_queue.append({
            'kind': 'station_upgrade', 'item': station.data_id, 'level': target,
            'time_left': seconds, 'total': seconds, 'status': 'paid',
            'source_owner': player_id, 'cost': dict(cost),
        })
        st.float_text(station.pos, f'Refit ordered · level {target}', (0.7, 0.9, 1))
        st.events.publish('station_upgrade_started', entity_id=station.id,
                          station=station.data_id, owner=player_id, level=target)
        return True

    # ------------------------------------------------------------------ satellites
    def satellite_slots(self, planet):
        """Slots a new satellite cannot use: live, paid, or under the #57 penalty."""
        from .colonies import locked_satellite_slots
        live = {e.satellite_slot for e in self.state.entities.values()
                if e.alive and e.planet_id == planet.id and e.satellite_slot is not None}
        return (live | {i['slot'] for i in planet.build_queue if i.get('kind') == 'satellite'}
                | locked_satellite_slots(self.state, planet))

    def satellite_site(self, planet, station_id, slot):
        cap = colony_rules()['satellite_cap']
        from .satellite_orbits import orbit_position
        sd = self.ds.stations[station_id]
        return orbit_position(planet, sd.radius, slot * 2 * math.pi / cap, slot, state=self.state)

    def satellite_ring_available(self, planet, station_id, slot, player_id, *, ignore_work=None):
        """Reserve a complete terrain-certified orbit, not just its build phase."""
        from .satellite_orbits import orbit_geometry, ring_distance, rings_clear
        sd = self.ds.stations[station_id]
        plan = orbit_geometry(self.state, planet, sd.radius, slot)
        if plan is None:
            return False
        radius, node, inclination = plan
        for other in self.state.entities.values():
            if not other.alive:
                continue
            if other.is_station:
                minimum = self.station_min_distance(station_id, other.data_id, other.radius,
                                                    player_id, other.owner)
                if ring_distance(planet.pos, radius, node, inclination, other.pos) < minimum:
                    return False
                if other.satellite_slot is not None and other.planet_id is not None:
                    parent = self.state.entity(other.planet_id)
                    other_plan = (orbit_geometry(self.state, parent, other.radius, other.satellite_slot)
                                  if parent is not None else None)
                    if other_plan is None or not rings_clear(planet.pos, plan, parent.pos, other_plan, minimum):
                        return False
            for work in other.build_queue:
                if (work is ignore_work or work.get('kind') not in ('station', 'satellite')
                        or work.get('status') != 'paid' or work.get('pos') is None):
                    continue
                data = self.ds.stations[work['item']]
                minimum = self.station_min_distance(station_id, data.id, data.radius, player_id)
                if ring_distance(planet.pos, radius, node, inclination, Vec3(*work['pos'])) < minimum:
                    return False
                if work['kind'] == 'satellite':
                    other_plan = (orbit_geometry(self.state, other, data.radius, work['slot'])
                                  if other.is_planet and type(work.get('slot')) is int else None)
                    if other_plan is None or not rings_clear(planet.pos, plan, other.pos, other_plan, minimum):
                        return False
        return True

    def satellite_birth_available(self, station_id, pos):
        """Mobile hulls reserve today's birth footprint, not their future paths."""
        radius = self.ds.stations[station_id].radius
        return all(not e.alive or not (e.is_ship or e.is_squadron)
                   or pos.dist(e.pos) >= (radius + e.radius) * 1.6
                   for e in self.state.entities.values())

    def start_satellite(self, planet_id, station_id, player_id):
        from .colonies import eligible_planet
        planet = self.state.entity(planet_id)
        if (not eligible_planet(planet) or planet.colonized_by != player_id
                or station_id not in ('defense_satellite', 'attack_satellite')):
            return False
        used = self.satellite_slots(planet)
        cap = colony_rules()['satellite_cap']
        sd = self.ds.stations[station_id]
        if not self.command_available(player_id, sd.command_cost):
            self.state.float_text(planet.pos, "Command capacity reached", (1, 0.6, 0.4))
            return False
        # Search free slots in stable order, including paid site reservations.
        for slot in range(cap):
            if slot in used:
                continue
            pos = self.satellite_site(planet, station_id, slot)
            if pos is None or not self.satellite_ring_available(planet, station_id, slot, player_id):
                continue
            if not self.satellite_birth_available(station_id, pos):
                continue
            if not self._check_station_spacing(station_id, pos, player_id)[0]:
                continue
            blocked = False
            for e in self.state.entities.values():
                if e.alive and e.is_planet and e is not planet and e.data_id != 'asteroid_field':
                    if pos.dist(e.pos) < (e.radius + sd.radius) * 1.6:
                        blocked = True
                        break
            if not blocked:
                break
        else:
            return False
        cost = self.factory.station_build_cost(station_id)
        if not self.can_pay(player_id, cost):
            return False
        self.pay(player_id, cost)
        planet.build_queue.append(dict(kind='satellite', item=station_id,
            time_left=sd.build_time, total=sd.build_time, status='paid',
            source_owner=player_id, slot=slot, pos=pos.to_dict(precise=True)))
        return True

    # ------------------------------------------------------------------ colonize
    def start_colonize(self, colonizer_id: int, planet_id: int, player_id: int) -> bool:
        st = self.state
        unit = st.entity(colonizer_id)
        planet = st.entity(planet_id)
        from .colonies import eligible_planet
        if (unit is None or not unit.operational or unit.owner != player_id
                or not unit.is_ship):
            return False
        ud = self.ds.ships.get(unit.data_id)
        if ud is None or not ud.can_colonize or unit.jump_charge > 0 \
                or unit.jump_target is not None or unit.jump_travelling:
            return False
        # A new control intent replaces the old mission even if its target is
        # rejected. Authorize the source first: foreign/incapable units retain jobs.
        if any(work.get('kind') == 'colonize' for work in unit.build_queue):
            from .jump import clear_jump_orders
            unit.build_queue[:] = [work for work in unit.build_queue if work.get('kind') != 'colonize']
            clear_jump_orders(unit)
        if not eligible_planet(planet):
            return False
        if planet.colonized_by is not None and not st.is_enemy(player_id, planet.colonized_by):
            return False
        from .colonies import defending_satellites
        if planet.colonized_by is not None and defending_satellites(st, planet):
            return False
        from .jump import clear_jump_orders, detach_jumpers
        detach_jumpers(st, [unit])
        clear_jump_orders(unit)
        unit.build_queue.clear()
        if unit.pos.dist(planet.pos) > planet.radius + colony_rules()['approach_range']:
            # move there first; colonization completes on arrival via queue
            unit.order_type = "move"
            unit.order_target_id = None
            radial = (unit.pos - planet.pos).normalized()
            unit.order_target_pos = planet.pos + radial * (planet.radius + colony_rules()['approach_range'] * .65)
            unit.build_queue.append({
                "kind": "colonize", "item": str(planet_id), "time_left": colony_rules()["control_seconds"],
                "total": colony_rules()["control_seconds"], "planet_id": planet_id, "status": "traveling",
                "source_owner": player_id, "target_owner": planet.colonized_by,
            })
            return True
        # in range: start timer
        unit.build_queue.append({
            "kind": "colonize", "item": str(planet_id), "time_left": colony_rules()["control_seconds"],
            "total": colony_rules()["control_seconds"], "planet_id": planet_id, "status": "paid",
            "source_owner": player_id, "target_owner": planet.colonized_by,
        })
        return True

    # ------------------------------------------------------------------ tick queues
    def update(self, dt: float) -> None:
        st = self.state
        # Expired satellite rebuild penalties are swept here, on tick, so nothing
        # render-side ever has to mutate simulation state to keep them tidy (#57).
        from .colonies import prune_satellite_locks
        prune_satellite_locks(st)
        done_events = []
        for e in sorted(st.entities.values(), key=lambda e: e.id):
            if not e.build_queue:
                continue
            item = e.build_queue[0]
            if item.get('kind') == 'colonize':
                from .colonies import eligible_planet
                planet = st.entity(item['planet_id'])
                if (not e.operational or e.owner != item.get('source_owner', e.owner)
                        or not eligible_planet(planet)
                        or planet.colonized_by != item.get('target_owner')
                        or (planet.colonized_by is not None and not st.is_enemy(e.owner, planet.colonized_by))
                        or e.jump_charge > 0 or e.jump_target is not None):
                    e.build_queue.pop(0)
                    continue
                from .colonies import defending_satellites
                if defending_satellites(st, planet):
                    item.update(time_left=colony_rules()['control_seconds'], total=colony_rules()['control_seconds'], status='blocked')
                    continue
                if e.pos.dist(planet.pos) > planet.radius + colony_rules()['approach_range']:
                    item.update(time_left=colony_rules()['control_seconds'], total=colony_rules()['control_seconds'], status='traveling')
                    continue
                item['status'] = 'paid'
                e.order_type = 'hold'
                e.order_target_pos = None
                e.order_target_id = None
                e.vel = Vec3()
                item['time_left'] = item['time_left'] - dt
                if item['time_left'] <= 0:
                    e.build_queue.pop(0)
                    done_events.append((e, item))
                continue
            if not e.operational:
                continue
            speed = 1.0
            if item.get("kind") == "ship" and e.is_station:
                speed = stats.effective_build_speed(st, e.owner, e)
            elif e.is_construction:
                speed = stats.effective_build_speed(st, e.owner, e)
            item["time_left"] -= dt * speed
            if item["time_left"] <= 0:
                e.build_queue.pop(0)
                done_events.append((e, item))
        for e, item in done_events:
            self._complete(e, item)

    def _complete(self, builder, item: dict) -> None:
        st = self.state
        kind = item.get("kind")
        if kind in ('station', 'satellite'):
            owner = item['source_owner'] if kind == 'satellite' else builder.owner
            # Paid work is consumed at completion. A newly hostile center or
            # occupied site cancels the placement without refund (like capture
            # invalidation); existing stations and ship production are untouched.
            if not self._check_station_spacing(item['item'], item['pos'], owner,
                                                ignore_work=item)[0]:
                st.float_text(builder.pos, 'Cannot build: site unavailable', (1, .5, .4))
                return
        if kind == 'planet_building':
            from .planet_buildings import planet_building_site
            from .colonies import eligible_planet
            if not eligible_planet(builder) or builder.colonized_by != item['source_owner']:
                return
            pos, normal = planet_building_site(builder, item['slot'])
            if not self._check_station_spacing(item['item'], pos, builder.colonized_by,
                                               ignore_work=item)[0]:
                st.float_text(builder.pos, 'Cannot build: site unavailable', (1, .5, .4))
                return
            building = self.factory.spawn_station(item['item'], builder.colonized_by, pos)
            building.planet_id = builder.id
            building.planet_building_slot = item['slot']
            st.events.publish('station_built', entity_id=building.id, station=building.data_id, owner=building.owner)
        elif kind == 'satellite':
            from .colonies import eligible_planet
            if not eligible_planet(builder) or builder.colonized_by != item['source_owner']:
                return
            if not self.satellite_birth_available(item['item'], Vec3(*item['pos'])):
                # Transient mobile occupancy delays delivery, never destroys or
                # refunds paid work. Keep the exact site/slot and reservation.
                item['time_left'] = 0.
                builder.build_queue.insert(0, item)
                return
            if not self.satellite_ring_available(builder, item['item'], item['slot'],
                                                 item['source_owner'], ignore_work=item):
                st.float_text(builder.pos, 'Cannot build: orbit unavailable', (1, .5, .4))
                return
            satellite = self.factory.spawn_station(item['item'], builder.colonized_by, Vec3(*item['pos']))
            satellite.planet_id = builder.id
            satellite.satellite_slot = item['slot']
            satellite.satellite_orbit_phase = item['slot'] * 2 * math.pi / colony_rules()['satellite_cap']
            st.events.publish('station_built', entity_id=satellite.id, station=satellite.data_id, owner=satellite.owner)
        elif kind == "station":
            pos = Vec3(*item["pos"])
            station = self.factory.spawn_station(item["item"], builder.owner, pos)
            st.float_text(pos, "Station complete", (0.6, 1, 0.6))
            st.events.publish("station_built", entity_id=station.id,
                              station=item["item"], owner=builder.owner)
        elif kind == "ship":
            ship_id = item["item"]
            sd = self.ds.resolve_ship(ship_id)
            offset = Vec3(
                st.rng().uniform(-1, 1) * (builder.radius + 80),
                st.rng().uniform(-0.2, 0.2) * 60,
                st.rng().uniform(-1, 1) * (builder.radius + 80),
            )
            spawn_pos = builder.pos + offset
            ship = self.factory.spawn_ship(ship_id, builder.owner, spawn_pos,
                                           yaw=st.rng().uniform(0, 6.28))
            # Sample at completion, not queue time. Keep the normal seeded birth
            # position; movement (including avoidance) takes the hull to the point.
            if builder.is_station and builder.collection_point is not None:
                ship.order_type = "move"
                ship.order_target_pos = builder.collection_point.copy()
                ship.order_target_id = None
            st.float_text(ship.pos, sd.display_name, (0.7, 0.9, 1))
            st.events.publish("ship_built", entity_id=ship.id, ship=ship_id,
                              owner=builder.owner)
        elif kind == "station_upgrade":
            # #77: refit work completes on the station itself. Capacity fields are
            # raised here, once, because damage/repair/AI/digest read them directly.
            from .upgrades import apply_level
            if builder.is_station and builder.alive:
                apply_level(st, builder, item)
        elif kind == "colonize":
            planet = st.entity(int(item["planet_id"]))
            from .colonies import eligible_planet, defending_satellites
            if (not eligible_planet(planet) or not builder.operational
                    or defending_satellites(st, planet)
                    or builder.pos.dist(planet.pos) > planet.radius + colony_rules()['approach_range']
                    or builder.owner != item.get('source_owner', builder.owner)
                    or planet.colonized_by != item.get('target_owner')
                    or (planet.colonized_by is not None and not st.is_enemy(builder.owner, planet.colonized_by))):
                return
            if planet is not None:
                from .jump import clear_jump_orders, detach_jumpers
                previous_owner = planet.colonized_by
                planet.build_queue.clear()  # paid work is lost, never refunded
                clear_jump_orders(planet)
                planet.jump_charge = 0
                planet.jump_target = None
                planet.ability_active.clear()
                planet.ability_cooldowns.clear()
                planet.colonized_by = builder.owner
                from .planet_buildings import transfer_buildings
                transfer_buildings(st, planet, builder.owner)
                for dependent in sorted(st.entities.values(), key=lambda e: e.id):
                    if dependent is builder:
                        continue
                    if dependent.order_target_id in (planet.id, builder.id):
                        clear_jump_orders(dependent)
                    if dependent.current_target in (planet.id, builder.id):
                        dependent.current_target = None
                    for field in ('hangar_id', 'launched_from', 'convoy_source', 'convoy_dest'):
                        if getattr(dependent, field) in (planet.id, builder.id):
                            setattr(dependent, field, None)
                    dependent.build_queue[:] = [work for work in dependent.build_queue
                        if not (work.get('kind') == 'colonize' and work.get('planet_id') == planet.id)]
                detach_jumpers(st, [builder])
                st.events.publish('planet_captured' if previous_owner is not None else 'planet_settled',
                    planet_id=planet.id, owner=builder.owner, previous_owner=previous_owner)
                st.float_text(planet.pos, "Planet colonized", (0.6, 1, 0.6))
                st.events.publish("planet_colonized", planet_id=planet.id,
                                  owner=builder.owner)
            # colonizer is consumed
            if builder.alive:
                builder.alive = False
                st.dead_ids.append(builder.id)
                st.spawn_effect("explosion_small", builder.pos.copy())