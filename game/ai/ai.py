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
        # builder_id -> (station_kind, Vec3): a site the constructor is walking
        # to, because the sim refuses the build until it is within
        # `station_build_range`
        self._pending_site: dict = {}

    # ------------------------------------------------------------------ helpers
    def my_units(self, kind=None):
        st = self.state
        out = []
        for e in st.entities.values():
            if (e.operational and not e.boarding and e.boarding_party_id is None
                    and not e.crew_mission and e.owner == self.player_id
                    and not getattr(self.ds.ships.get(e.data_id), 'crew_capacity', 0)):
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
            if e.operational and e.is_station and e.owner == self.player_id:
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
        return (bool(e.build_queue) or e.id in self._pending_site
                or any(cmd.player == self.player_id and cmd.type == 'build_station'
                       and e.id in cmd.unit_ids for cmd in self.state.command_queue))

    def difficulty(self) -> dict:
        p = self.state.players.get(self.player_id)
        key = p.ai_difficulty if p else "normal"
        return self.ds.rules.get("ai", {}).get("difficulty", {}).get(key, {})

    # ------------------------------------------------------------------ strategic
    def strategic_tick(self, dt: float) -> None:
        st = self.state
        # deterministic cadence: derive from sim tick, not accumulated dt —
        # restores/replays restart timers at 0, which would shift the schedule
        interval_ticks = max(1, round(
            self.ds.rules.get("ai", {}).get("strategic_interval", 1.0)
            / max(0.5, self.difficulty().get("decision_mult", 1.0))
            * 30))
        if st.tick % interval_ticks != self.player_id % interval_ticks:
            return

        p = st.players.get(self.player_id)
        if p is None:
            return
        home = self.home_station()
        if home is None:
            return

        # 1. economy: keep constructors alive and building
        self._flush_pending_sites()
        self._ensure_crew_logistics(home)
        self._ensure_economy(home)

        # 2. defense platforms when threatened
        self._ensure_defense(home)

        # 3. research
        self._maybe_research()

        # 4. ship production
        self._produce_fleet(home)

        # 5. expansion
        clearing_colony = self._maybe_expand(home)

        # Colony defenders gate capture; general fleet movement must not replace
        # their attack orders later in the same strategic update.
        if not clearing_colony:
            self._decide_attack()

    def _count_stations(self, kind: str) -> int:
        """Stations of `kind` that exist, are being walked to, or are building.

        `my_stations()` only counts finished ones. Now that a constructor has to
        travel to its site, a station can be "owed" for a minute or more, so
        counting only finished stations made the AI re-queue the same need over
        and over (it built five mining stations against a desired four and
        never got as far as trade or research).
        """
        n = len(self.my_stations(kind))
        for _bid, (k, _pos) in self._pending_site.items():
            if k == kind:
                n += 1
        for e in self.my_units():
            if e.is_construction and e.build_queue:
                for it in e.build_queue:
                    if it.get("kind") == "station" and it.get("item") == kind:
                        n += 1
        n += sum(cmd.player == self.player_id and cmd.type == 'build_station'
                 and cmd.station_kind == kind for cmd in self.state.command_queue)
        return n

    def _ensure_economy(self, home) -> None:
        st = self.state
        ds = self.ds
        constructors = [e for e in self.my_units() if e.is_construction and
                        not e.is_planet and self._is_builder(e)]
        # count idle constructors with money
        p = st.players.get(self.player_id)
        # A constructor walking to a site it has already been assigned has an
        # empty build_queue, so it still looks idle. Re-tasking it every tick
        # meant it never arrived anywhere and no station ever got built.
        idle = sorted((c for c in constructors if not self._busy(c)),
                      key=lambda c: (c.pos.dist_sq(home.pos), c.id))
        # desired: miners >= desired_miners; then trade stations
        desired_miners = int(ds.rules.get("ai", {}).get("desired_miners", 4))
        if self._count_stations("mining_station") < desired_miners and idle:
            site = self._find_asteroid_site(home, idle[0])
            if site:
                self._queue_build(idle[0], "mining_station", site)
                return
        # shipyard early — keep this ahead of trade: a young AI that spends its
        # opening credits on a trade station can't build warships or more
        # constructors with two idle builders in the meantime
        if not self._count_stations("shipyard") and idle and p.credits > 2200:
            site = self._find_station_site("shipyard", 700, home, idle[0])
            if site is not None:
                self._queue_build(idle[0], "shipyard", site)
                return
        # ONE trade station, then research, THEN the second market. A legal
        # route needs two own/allied markets; build our pair without spending
        # the credits research needs on both markets at once.
        if self._count_stations("trade_station") < 1 and p.credits > 1500 and idle:
            site = self._find_station_site("trade_station", 900, home, idle[0])
            if site is not None:
                self._queue_build(idle[0], "trade_station", site)
                return
        if not self._count_stations("research_station") and idle and p.credits > 2400:
            site = self._find_station_site("research_station", 700, home, idle[0])
            if site is not None:
                self._queue_build(idle[0], "research_station", site)
                return
        # Energy relay: the ONLY station that produces EN, and EN is spent on
        # every warship and on research, so an AI that never builds one runs
        # its fleet into a hard floor (reported: "my EN is 10 and I can't build
        # anymore"). Cheap (650cr) but FAR (~7200u out by a gas giant), so the
        # trip monopolises whichever constructor takes it — queued ahead of
        # mining it starved the whole early economy. Queue it once the core
        # economy exists and a constructor can be spared.
        if (self._count_stations("energy_relay") == 0 and idle
                and p.credits > 900 and self._count_stations("research_station")):
            site = self._find_energy_relay_site(home, idle[0])
            if site is not None:
                self._queue_build(idle[0], "energy_relay", site)
                return
        if self._count_stations("trade_station") < 2 and p.credits > 1500 and idle:
            site = self._find_station_site("trade_station", 900, home, idle[0])
            if site is not None:
                self._queue_build(idle[0], "trade_station", site)
                return
        # more constructors if rich (command station builds engineering hulls)
        if len(constructors) < 2 and p.credits > 2500:
            faction = p.faction
            sid = {
                "imperial": "imperial_constructor",
                "rebel": "rebel_constructor",
                "confederacy": "confed_constructor",
                "syndicate": "syndicate_constructor",
            }.get(faction)
            cmd = next((s for s in self.my_stations("command_station")
                        if len(s.build_queue) < 2), None)
            if sid and cmd:
                self._queue_ship(cmd, sid, 1)

    def _is_builder(self, e) -> bool:
        sd = self.ds.ships.get(e.data_id)
        return bool(sd and sd.is_construction and not sd.can_colonize)

    def _find_asteroid_site(self, home, builder=None):
        st = self.state
        if builder is None:
            builder = next((c for c in self.my_units() if self._is_builder(c)), None)
        if builder is None:
            return None
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
        # Paid sites and unpaid travel intent now reserve footprints too. A
        # blocked random sample must not consume the whole economy decision.
        for i in range(16):
            angle = ang + i * 2 * math.pi / 16
            pos = Vec3(best.pos.x + math.sin(angle) * best.radius * 0.5, 0,
                       best.pos.z + math.cos(angle) * best.radius * 0.5)
            if self._site_available('mining_station', pos, builder):
                return pos
        return None

    @staticmethod
    def _offset(anchor, dist: float) -> Vec3:
        import math
        # deterministic per-anchor angle (stable across ticks, but varies by
        # station type) so retry attempts don't hammer one illegal site
        ang = (anchor.pos.x * 0.013 + anchor.pos.z * 0.007) % 6.28
        return Vec3(anchor.pos.x + math.sin(ang) * dist, 0,
                    anchor.pos.z + math.cos(ang) * dist)

    def _site_available(self, kind, pos, builder) -> bool:
        """Full physical legality plus our own unpaid intent reservations."""
        st = self.state
        cs = getattr(st, '_construction_system', None)
        if cs is None or not cs.check_site(kind, pos, builder)[0]:
            return False
        reservations = []
        for bid, (other_kind, other_pos) in self._pending_site.items():
            source = st.entity(bid)
            if (bid != builder.id and source is not None and source.operational
                    and source.owner == self.player_id and not source.build_queue):
                reservations.append((other_kind, other_pos))
        reservations.extend((cmd.station_kind, Vec3(*cmd.target_pos))
            for cmd in st.command_queue if cmd.player == self.player_id
            and cmd.type == 'build_station' and cmd.target_pos is not None)
        for other_kind, other_pos in reservations:
            other = self.ds.stations[other_kind]
            if pos.dist(other_pos) < cs.station_min_distance(kind, other_kind, other.radius, self.player_id):
                return False
        return True

    def _find_station_site(self, kind: str, dist: float, home, builder):
        """First LEGAL site for `kind` on a ring around `home`, else None.

        `_offset()` returns a single deterministic angle, which is fine until
        that one direction happens to be blocked — on skirmish01 it points
        straight at the planet Skarn, so every trade-station build the AI
        queued was rejected by check_site and silently went nowhere (the AI
        held enough credits for the whole match and still never built one).
        Sweep the ring and hand back the first site the sim's own validator
        accepts, so a green site always means the build will land.
        """
        import math
        ang0 = (home.pos.x * 0.013 + home.pos.z * 0.007) % 6.28
        # reuse the sim's own validator (exposed on the state for render/input)
        # so a site chosen here is guaranteed to be accepted by the build
        cs = getattr(self.state, "_construction_system", None)
        if cs is None:
            return None
        n = 16
        for i in range(n):
            ang = ang0 + (i / n) * 2 * math.pi
            for r in (dist, dist * 1.35, dist * 0.75):
                pos = Vec3(home.pos.x + math.sin(ang) * r, 0,
                           home.pos.z + math.cos(ang) * r)
                if self._site_available(kind, pos, builder):
                    return pos
        return None

    def _find_energy_relay_site(self, home, builder, max_dist: float = 9000.0):
        """A legal energy_relay site near a gas giant, else None.

        energy_relay is the only station that produces EN, and its placement
        window is a ring around a gas giant — far from `home`, so the generic
        ring sweep below would never find it. Sweep the gas giant itself and
        hand back the first site the sim's validator accepts.
        """
        import math
        from ..systems.construction import _body_clearance
        cs = getattr(self.state, "_construction_system", None)
        if cs is None:
            return None
        relay_r = self.ds.resolve_station("energy_relay").radius
        giants = [e for e in self.state.entities.values()
                  if e.alive and e.data_id == "gas_giant"]
        # nearest gas giant first
        giants.sort(key=lambda g: home.pos.dist_sq(g.pos))
        for gas in giants:
            if home.pos.dist(gas.pos) > max_dist:
                continue
            base = _body_clearance(gas, relay_r)
            for i in range(24):
                ang = (gas.pos.x * 0.013 + gas.pos.z * 0.007) % 6.28 + (i / 24) * 2 * math.pi
                for r in (base + 200, base + 700, base + 1400):
                    pos = Vec3(gas.pos.x + math.sin(ang) * r, 0,
                               gas.pos.z + math.cos(ang) * r)
                    ok, _reason = cs.check_site("energy_relay", pos, builder)
                    if ok:
                        return pos
        return None

    def _queue_build(self, builder, station_kind: str, pos: Vec3) -> None:
        """Queue a station build, walking the constructor into range first.

        The sim refuses a site beyond the builder's `station_build_range`, and
        the AI evaluates sites from the builder's CURRENT position — a
        constructor that is still mining or flying home would otherwise have
        every order bounced forever. So: in range, build; out of range, send it
        over and build next tick (the site itself was already validated, and
        `start_station` re-validates on arrival).
        """
        st = self.state
        cs = getattr(st, "_construction_system", None)
        if not self._site_available(station_kind, pos, builder):
            return
        if cs is not None and hasattr(cs, "too_far_to_build"):
            far, _d, _lim = cs.too_far_to_build(pos, builder)
            if far:
                st.queue_command(PlayerCommand(
                    "move", self.player_id, unit_ids=(builder.id,),
                    target_pos=(pos.x, pos.y, pos.z)))
                self._pending_site[builder.id] = (station_kind, pos)
                return
        st.queue_command(PlayerCommand(
            "build_station", self.player_id, unit_ids=(builder.id,),
            station_kind=station_kind, target_pos=(pos.x, pos.y, pos.z)))

    def _flush_pending_sites(self) -> None:
        """Build any station whose constructor has finished walking over.

        The site is held STABLE across ticks. Re-picking it every tick (which
        the finders do — asteroid sites are even randomised) sent the
        constructor after a target that moved each frame, so it never arrived
        and no station was ever built.
        """
        st = self.state
        cs = getattr(st, "_construction_system", None)
        for bid, (kind, pos) in list(self._pending_site.items()):
            b = st.entity(bid)
            if b is None or not b.operational or b.owner != self.player_id or not b.is_construction:
                del self._pending_site[bid]
                continue
            if b.build_queue:
                continue        # busy building something else
            if not self._site_available(kind, pos, b):
                # Release both the stale travel reservation and its economic
                # reserve; the next strategic pass can choose another legal site.
                del self._pending_site[bid]
                continue
            far = True
            if cs is not None and hasattr(cs, "too_far_to_build"):
                far, _d, _lim = cs.too_far_to_build(pos, b)
            if not far:
                # in range at last — place it (start_station re-validates)
                del self._pending_site[bid]
                st.queue_command(PlayerCommand(
                    "build_station", self.player_id, unit_ids=(b.id,),
                    station_kind=kind, target_pos=(pos.x, pos.y, pos.z)))
                continue
            # still out of range: is it actually heading for THIS site?
            tgt = b.order_target_pos
            heading = (b.order_type == "move" and tgt is not None
                       and abs(tgt.x - pos.x) < 1.0 and abs(tgt.z - pos.z) < 1.0)
            if not heading:
                # the order was never given or has been interrupted — re-issue
                # the same destination rather than abandoning the site
                st.queue_command(PlayerCommand(
                    "move", self.player_id, unit_ids=(b.id,),
                    target_pos=(pos.x, pos.y, pos.z)))

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
                    and st.can_see(self.player_id, e.id) \
                    and e.pos.dist(home.pos) < 2500:
                threatened = True
                break
        defenses = self.my_stations("defense_platform")
        idle = [c for c in self.my_units()
                if self._is_builder(c) and not self._busy(c)]
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
            # fighters: fighter platform preferred; shipyard also fields them
            station = fighter_plat or shipyard
            plan.append((station, sq))
        elif p.credits > 1400 and counts.get(cv, 0) < 4:
            plan.append((shipyard, cv))
        elif p.credits > 3500 and counts.get(fr, 0) < 3:
            plan.append((shipyard, fr))
        elif p.credits > 9000 and counts.get(cr, 0) < 2:
            plan.append((shipyard, cr))
        elif bs and p.credits > 16000 and counts.get(bs, 0) < 1:
            plan.append((shipyard, bs))
        # Preserve the next mining/research/relay/market gate and unpaid travel
        # sites before replacing expendable scouts or upgrading the fleet.
        reserve = self._infrastructure_reserve()
        budget = self._projected_budget()
        for station, ship_id in plan:
            if station is None:
                continue
            cost = st._construction_system.factory.ship_build_cost(ship_id)
            if any(budget[key] - cost.get(key, 0) < reserve[key] for key in budget):
                continue
            if len(station.build_queue) < 2:
                self._queue_ship(station, ship_id, 1)
                return  # one command per tick keeps queue fair

    def _infrastructure_reserve(self) -> dict[str, float]:
        """Protect unpaid travel sites and the next core economic gate."""
        factory = self.state._construction_system.factory
        reserve: dict[str, float] = dict.fromkeys(('credits', 'materials', 'energy', 'crew'), 0.0)
        for bid, (kind, _pos) in self._pending_site.items():
            builder = self.state.entity(bid)
            if builder is None or builder.owner != self.player_id or builder.build_queue:
                continue
            cost = factory.station_build_cost(kind)
            for key in reserve:
                reserve[key] += cost.get(key, 0)
        milestones = [('mining_station', int(self.ds.rules.get('ai', {}).get('desired_miners', 4)), 0),
                      ('shipyard', 1, 2201), ('trade_station', 1, 1501),
                      ('research_station', 1, 2401), ('energy_relay', 1, 901),
                      ('trade_station', 2, 1501)]
        for kind, count, gate in milestones:
            if self._count_stations(kind) < count:
                cost = factory.station_build_cost(kind)
                for key in reserve:
                    reserve[key] += max(cost.get(key, 0), gate if key == 'credits' else 0)
                break
        # A lone market must retain its route-completion gate even when an
        # earlier milestone (such as mining) is the next infrastructure need.
        # Count queued/pending markets too; their unpaid costs remain above.
        if self._count_stations('trade_station') == 1:
            reserve['credits'] = max(reserve['credits'], 1500.0,
                                     factory.station_build_cost('trade_station').get('credits', 0))
        # Unpaid orbital/surface investments carry their reserve into every
        # later hull purchase, not only the pass that queued the investment.
        if any(c.player == self.player_id and c.type in
               ('build_satellite', 'build_planet_building')
               for c in self.state.command_queue):
            reserve['credits'] = max(5000, reserve['credits'])
            reserve['materials'] = max(2500, reserve['materials'])
        return reserve

    def _colony_reserve(self):
        """Optional colony spending never consumes core infrastructure gates."""
        reserve = self._infrastructure_reserve()
        reserve['credits'] = max(5000, reserve['credits'])
        reserve['materials'] = max(2500, reserve['materials'])
        return reserve

    def _projected_budget(self):
        """Bank after this player's unconsumed paid commands (queues are paid)."""
        p = self.state.players[self.player_id]
        budget = {key: getattr(p, key) for key in ('credits', 'materials', 'energy', 'crew')}
        factory = self.state._construction_system.factory
        for cmd in self.state.command_queue:
            if cmd.player != self.player_id:
                continue
            count = 1
            if cmd.type == 'build_ship':
                cost = factory.ship_build_cost(cmd.ship_id)
                count = int(cmd.name) if cmd.name and cmd.name.isdigit() else 1
            elif cmd.type in ('build_station', 'build_satellite', 'build_planet_building'):
                cost = factory.station_build_cost(cmd.station_kind)
            elif cmd.type == 'research':
                tech = self.ds.techs[cmd.tech_id]
                cost = {key: getattr(tech, 'cost_' + key, 0) for key in budget}
            else:
                continue
            for key in budget:
                budget[key] -= cost.get(key, 0) * count
        return budget

    def _maybe_expand(self, home) -> bool | None:
        st = self.state
        p = st.players.get(self.player_id)
        ds = self.ds
        threshold = ds.rules.get("ai", {}).get("expand_credits", 4000)
        from ..systems.colonies import eligible_planet
        budget = self._projected_budget()
        has_colony = False
        for planet in sorted(st.entities.values(), key=lambda e: e.id):
            known = st.known_entity(self.player_id, planet.id)
            if not eligible_planet(planet) or known is None or known.colonized_by != self.player_id:
                continue
            has_colony = True
            roles = {e.data_id for e in self.my_stations() if e.planet_id == planet.id}
            roles.update(i['item'] for i in planet.build_queue if i.get('kind') == 'satellite')
            roles.update(c.station_kind for c in st.command_queue
                         if c.player == self.player_id and c.type == 'build_satellite'
                         and c.target_id == planet.id)
            for role in ('defense_satellite', 'attack_satellite'):
                cost = st._construction_system.factory.station_build_cost(role)
                reserve = self._colony_reserve()
                if (role not in roles and self.my_stations('mining_station')
                        and budget['materials'] > 2500
                        and all(budget[key] - cost[key] >= reserve[key] for key in budget)):
                    st.queue_command(PlayerCommand('build_satellite', self.player_id,
                        target_id=planet.id, station_kind=role))
                    for key in budget:
                        budget[key] -= cost[key]
        # One surface investment per pass, after orbital protection, without
        # consuming core infrastructure or earlier unconsumed command reserves.
        from ..systems.planet_buildings import building_slots, building_rules
        for planet in sorted(st.entities.values(), key=lambda e: e.id):
            known = st.known_entity(self.player_id, planet.id)
            if (not eligible_planet(planet) or known is None
                    or known.colonized_by != self.player_id):
                continue
            pending = [c for c in st.command_queue if c.player == self.player_id
                       and c.type == 'build_planet_building' and c.target_id == planet.id]
            if pending or len(building_slots(st, planet)) >= building_rules()['slot_cap']:
                continue
            roles = {e.data_id for e in self.my_stations() if e.planet_id == planet.id}
            roles.update(w['item'] for w in planet.build_queue if w.get('kind') == 'planet_building')
            role = next((r for r in ('planet_extractor', 'planet_trade_hub',
                                     'planet_shield_generator', 'planet_pulsar_cannon')
                         if r not in roles), None)
            if role is None or not self.my_stations('mining_station'):
                continue
            cost = st._construction_system.factory.station_build_cost(role)
            reserve = self._colony_reserve()
            if all(budget[k] - cost[k] >= reserve[k] for k in budget):
                st.queue_command(PlayerCommand('build_planet_building', self.player_id,
                    target_id=planet.id, station_kind=role))
                for key in budget:
                    budget[key] -= cost[key]
                break
        colonizer = next((e for e in self.my_units()
                          if e.is_construction and getattr(
                              self.ds.ships.get(e.data_id), "can_colonize", False)
                          and not e.build_queue), None)
        if colonizer is None:
            # build one
            shipyard = next((s for s in self.my_stations("command_station")), None)
            faction = p.faction
            sid = next((s.id for s in sorted(ds.ships.values(), key=lambda s: s.id)
                        if s.faction == faction and s.can_colonize), None)
            existing = any(getattr(ds.ships.get(e.data_id), 'can_colonize', False) for e in self.my_units())
            queued = (any(i.get('item') == sid for s in self.my_stations() for i in s.build_queue)
                      or any(c.player == self.player_id and c.type == 'build_ship' and c.ship_id == sid
                             for c in st.command_queue))
            cost = st._construction_system.factory.ship_build_cost(sid) if sid else {}
            reserve = self._colony_reserve() if has_colony else self._infrastructure_reserve()
            budget = self._projected_budget()
            if (sid and shipyard and not existing and not queued and p.credits > 2000
                    and len(shipyard.build_queue) < 2
                    and all(budget[key] - cost.get(key, 0) >= reserve[key] for key in budget)):
                self._queue_ship(shipyard, sid, 1)
            return
        target = self._pick_colony_target(home)
        if target is not None:
            defenders = [e for e in st.entities.values() if e.alive and e.planet_id == target.id
                         and e.data_id in ('defense_satellite', 'attack_satellite')
                         and st.is_enemy(self.player_id, e.owner) and st.can_see(self.player_id, e.id)]
            if defenders:
                defender = min(defenders, key=lambda e: e.id)
                fighters = [e.id for e in self.my_units() if e.is_ship and not e.is_construction
                            and not e.is_squadron and getattr(ds.ships.get(e.data_id), 'weapons', [])]
                if fighters:
                    st.queue_command(PlayerCommand('attack', self.player_id,
                        unit_ids=tuple(sorted(fighters)), target_id=defender.id))
                    return True
                return False
            if p.credits < threshold:
                return
            st.queue_command(PlayerCommand("colonize", self.player_id,
                                           unit_ids=(colonizer.id,),
                                           target_id=target.id))

    def _pick_colony_target(self, home):
        """Public static geometry and last observed ownership only."""
        st = self.state
        target = None
        best_d = 1e18
        from ..systems.colonies import eligible_planet
        for e in st.entities.values():
            if not eligible_planet(e):
                continue
            # Map geometry/type is public; ownership is only current sensor
            # intel or the last observed snapshot. Undiscovered is unknown,
            # not a license to inspect the live planet's colonized_by.
            known = st.known_entity(self.player_id, e.id)
            if known is not None and (known.colonized_by in st.allied_player_ids(self.player_id)
                                      or known.owner in st.allied_player_ids(self.player_id)):
                continue
            # skip planets near enemy stations
            near_enemy = any(en.alive and en.is_station and en.planet_id != e.id and en.owner >= 0
                             and st.is_enemy(self.player_id, en.owner)
                             and st.can_see(self.player_id, en.id)
                             and en.pos.dist(e.pos) < 3000
                             for en in st.entities.values())
            if near_enemy:
                continue
            d = home.pos.dist_sq(e.pos)
            if d < best_d:
                target, best_d = e, d
        return target

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
            if (e.alive and e.owner >= 0 and st.is_enemy(self.player_id, e.owner)
                    and st.can_see(self.player_id, e.id)):
                enemy_strength += _unit_strength(self.ds, e)
                if enemy_target is None or (e.is_station and not enemy_target.is_station):
                    enemy_target = e
        if my_strength := my_strength:
            pass
        if enemy_target is None:
            self._scout_unknown()
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

    def _scout_unknown(self) -> None:
        """Explore public map waypoints, never an unseen entity's coordinates."""
        st = self.state
        home = self.home_station()
        if home is None:
            return
        # One active map scout is enough. Dispatching another idle ship each
        # strategic tick empties the home defense and sends the whole fleet
        # abroad before economy/research infrastructure is established.
        if any(e.order_type == "attack_move" for e in self.my_units()
               if (e.is_ship or e.is_squadron) and not e.is_construction):
            return
        scouts = [e for e in self.my_units()
                  if (e.is_ship or e.is_squadron) and not e.is_construction
                  and e.order_type == "idle" and _unit_strength(self.ds, e) > 0]
        if not scouts:
            return
        # Mirror of our own spawn is a map guess, not enemy-base intel. Then
        # visit public jump points; cadence comes from persisted simulation tick.
        guesses = [Vec3(-home.pos.x, home.pos.y, -home.pos.z)]
        guesses += [Vec3(*point["pos"]) for point in st.map_info.jump_points]
        guesses = [pos for pos in guesses if pos.dist(home.pos) > 1000]
        if not guesses:
            return
        destination = guesses[(st.tick // 1800) % len(guesses)]
        scout = max(scouts, key=lambda e: (self.ds.ships[e.data_id].speed, -e.id))
        st.queue_command(PlayerCommand(
            "attack_move", self.player_id, unit_ids=(scout.id,),
            target_pos=(destination.x, destination.y, destination.z)))

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
                    and st.can_see(self.player_id, e.id) \
                    and (e.is_ship or e.is_squadron) and e.pos.dist(home.pos) < 2200:
                return True
        return False

    def _ensure_crew_logistics(self, home):
        recovery = self.state._crew_recovery_system
        from ..systems.crew_recovery import recovery_rules
        cfg = recovery_rules()
        needs_repair = any(e.alive and e.owner == self.player_id
                           and e.subsystem_fraction('life_support') < cfg['ai_support_retreat']
                           for e in self.state.entities.values() if e.is_ship or e.is_station)
        if needs_repair and self._count_stations('repair_dock') == 0:
            builders = sorted((c for c in self.my_constructors()
                               if c.id not in self._pending_site
                               and 'repair_dock' in self.ds.ships[c.data_id].can_build_stations),
                              key=lambda c: (c.pos.dist_sq(home.pos), c.id))
            for builder in builders:
                pos = self._find_station_site('repair_dock', 450, home, builder)
                if pos is not None:
                    self._queue_build(builder, 'repair_dock', pos)
                    break
        stranded = [e for e in self.state.entities.values() if e.alive and e.owner == self.player_id
                    and not e.boarding and (e.is_ship or e.is_station)
                    and e.crew < e.max_crew and recovery.base_for(e) is None
                    and e.subsystem_fraction('life_support') >= cfg['support_threshold']]
        if not stranded:
            return
        p = self.state.players[self.player_id]
        # A remote derelict cannot move or recruit itself. Count it only when
        # the authoritative automatic recruitment path can restart its crew.
        if any(e.alive and e.owner == self.player_id and recovery.capacity(e)
               and (e.operational or (
                   not e.boarding and e.crew < e.max_crew
                   and e.subsystem_fraction('life_support') >= cfg['support_threshold']
                   and recovery.base_for(e) is not None
                   and p.crew >= 1 and p.credits >= cfg['credits_per_crew']))
               for e in self.state.entities.values()):
            return
        if any(self.ds.ships.get(q.get('item')) and self.ds.ships[q['item']].crew_capacity
               for e in self.my_stations() for q in e.build_queue):
            return
        transports = sorted(s.id for s in self.ds.ships.values()
                            if s.faction == self.state.players[self.player_id].faction and s.crew_capacity)
        for yard in sorted(self.my_stations('shipyard'), key=lambda e: e.id):
            if transports and not yard.build_queue:
                self._queue_ship(yard, transports[0], 1)
                return

    def _crew_recovery(self, e):
        from ..systems.crew_recovery import recovery_rules
        from ..systems.stats import staffing_fraction
        from ..core.commands import PlayerCommand
        cfg = recovery_rules()
        recovery = self.state._crew_recovery_system
        # Failing support takes precedence over loading/delivery, and a fallback
        # recovery destination is reconsidered when usable repairs appear.
        # Preserve actual repair missions through their completion threshold.
        if e.crew_mission and (
                e.subsystem_fraction('life_support') >= cfg['ai_support_retreat']
                or (e.crew_mission.get('phase') == 'recover'
                    and recovery.repairs_support(self.state.entity(e.crew_mission.get('target')), e))):
            return True
        if not e.is_ship or e.is_squadron:
            return False
        # Idle transports need their operating complement before field work;
        # healthy active missions above remain authoritative until completion.
        if (recovery.capacity(e)
                and e.subsystem_fraction('life_support') >= cfg['ai_support_retreat']
                and staffing_fraction(e) >= cfg['ai_staffing_retreat']):
            targets = [t for t in self.state.entities.values()
                       if t.alive and t.owner == e.owner and t is not e and not t.boarding
                       and (t.is_ship or t.is_station or t.is_squadron)
                       and t.crew < t.max_crew and recovery.base_for(t) is None
                       and t.subsystem_fraction('life_support') >= cfg['support_threshold']]
            target = min(targets, key=lambda t: (t.crew > 0, e.pos.dist_sq(t.pos), t.id), default=None)
            if target is not None and e.crew_cargo > 0:
                self.state.queue_command(PlayerCommand('crew_deliver', e.owner, unit_ids=(e.id,), target_id=target.id))
                return True
            if target is not None and recovery.base_for(e) is not None:
                self.state.queue_command(PlayerCommand('crew_load', e.owner, unit_ids=(e.id,)))
                return True
            if target is None:
                return True  # unarmed logistics hardware never scouts or attacks
        if (e.subsystem_fraction('life_support') >= cfg['ai_support_retreat']
                and staffing_fraction(e) >= cfg['ai_staffing_retreat'] and not recovery.capacity(e)):
            return False
        bases = [b for b in self.state.entities.values() if b.operational and b.is_station
                 and b.owner in self.state.allied_player_ids(e.owner)
                 and b.data_id in cfg['base_types']]
        if e.subsystem_fraction('life_support') < cfg['ai_support_retreat']:
            docks = [b for b in bases if recovery.repairs_support(b, e)]
            if docks:
                bases = docks
        base = min(bases, key=lambda b: (e.pos.dist_sq(b.pos), b.id), default=None)
        if (base is not None and not (e.crew_mission.get('phase') == 'recover'
                                      and e.crew_mission.get('target') == base.id)):
            self.state.queue_command(PlayerCommand('crew_recover', e.owner,
                                                   unit_ids=(e.id,), target_id=base.id))
        return True

    # ------------------------------------------------------------------ tactical
    def tactical_tick(self, dt: float) -> None:
        st = self.state
        # deterministic cadence (tick-derived, offset by player to spread load)
        interval_ticks = max(1, round(
            self.ds.rules.get("ai", {}).get("tactical_interval", 0.2) * 30))
        if st.tick % interval_ticks != (self.player_id + 3) % interval_ticks:
            return
        retreat_frac = self.ds.rules.get("ai", {}).get("retreat_hull_fraction", 0.28)
        home = self.home_station()
        for e in sorted(st.entities.values(), key=lambda e: e.id):
            if e.owner != self.player_id or not e.operational or e.boarding or e.boarding_party_id is not None:
                continue
            if self._crew_recovery(e):
                continue
            from ..systems.boarding import boarding_capable, boarding_reason, boarding_rules
            from ..systems.crew_recovery import recovery_rules
            from ..core.commands import PlayerCommand
            if boarding_capable(e) and e.boarding_party_id is None:
                party = min(e.crew - 1, max(1, int(e.crew * boarding_rules()['party_fraction'])))
                # Detection must precede reading live enemy crew/support/position.
                candidates = [t for t in sorted(st.entities.values(), key=lambda t: t.id)
                              if st.is_enemy(e.owner, t.owner) and st.can_see(e.owner, t.id)
                              and not boarding_reason(st, e, t)
                              and party >= max(1, t.crew) * recovery_rules()['ai_board_ratio']
                              and not any(c.alive
                                          and (c.owner in st.allied_player_ids(e.owner)
                                               or st.can_see(e.owner, c.id))
                                          and c.boarding.get('target') == t.id
                                          for c in st.entities.values())]
                if candidates:
                    target = min(candidates, key=lambda t: (e.pos.dist_sq(t.pos), t.id))
                    st.queue_command(PlayerCommand('board', e.owner, unit_ids=(e.id,), target_id=target.id))
                    continue
            if not (e.is_ship or e.is_squadron):
                continue
            if e.is_construction:
                # constructors flee from enemies
                for tid in st.grid.query_sphere(st.entities, e.pos, 1200):
                    t = st.entity(tid)
                    if (t and st.is_enemy(self.player_id, t.owner)
                            and st.can_see(self.player_id, t.id)
                            and (t.is_ship or t.is_squadron)):
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
                    if (t and st.is_enemy(self.player_id, t.owner) and not t.is_planet
                            and st.can_see(self.player_id, t.id)):
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