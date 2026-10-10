"""EconomySystem — income, crew, command capacity, trade, repair docks, energy regen.

Runs every tick (income is small but continuous); command capacity is recomputed at
1 Hz by GameManager and cached on PlayerState.command_capacity.
"""
from __future__ import annotations

from ..data.store import DataStore
from . import stats


class EconomySystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    def update(self, dt: float) -> None:
        st = self.state
        eco = self.ds.rules.get("economy", {})
        planet_income = eco.get("planet_income", {})

        # zero accumulators
        for p in st.players.values():
            p.income_frame = {"credits": 0.0, "materials": 0.0, "energy": 0.0, "crew": 0.0}

        # --- station + planet income
        for e in st.entities.values():
            if not e.operational:
                continue
            # A COLONIZED planet is owned by its colonizer but has
            # `owner == -1` (planets are neutral terrain; colonising sets only
            # `colonized_by`). Reading `e.owner` here skipped every planet, so
            # the whole planet_income table was dead — no EN from gas giants
            # and no credits/crew from any other world.
            if e.is_planet:
                if e.colonized_by is None or e.colonized_by < 0:
                    continue
                owner = e.colonized_by
            else:
                owner = e.owner
                if owner < 0:
                    continue
            p = st.players.get(owner)
            if p is None:
                continue
            if e.is_planet:
                rates = dict(planet_income.get(e.data_id, {}))
                # planet_crew_bonus was declared in game_rules.json and never
                # read anywhere — agricultural/temperate worlds never paid the
                # extra crew they advertise. Fold it in here, which is the one
                # place a colony's output is computed.
                for res, bonus in eco.get("planet_crew_bonus", {}).items():
                    if res == e.data_id:
                        rates["crew"] = rates.get("crew", 0.0) + bonus
                for res, rate in rates.items():
                    p.income_frame[res] = p.income_frame.get(res, 0.0) + rate
            elif e.is_station:
                sd = self.ds.stations.get(e.data_id)
                if sd:
                    for res, rate in sd.income.items():
                        p.income_frame[res] = p.income_frame[res] + rate

        # --- AI difficulty income multiplier
        for p in st.players.values():
            if p.is_ai:
                mult = self.ds.rules.get("ai", {}).get("difficulty", {}).get(
                    p.ai_difficulty, {}).get("income_mult", 1.0)
                for k in p.income_frame:
                    p.income_frame[k] *= mult

        # --- apply
        for p in st.players.values():
            inc = p.income_frame
            p.credits += inc.get("credits", 0.0) * dt
            p.materials += inc.get("materials", 0.0) * dt
            p.energy += inc.get("energy", 0.0) * dt
            p.crew += inc.get("crew", 0.0) * dt

        # --- repair docks
        repair_cfg = eco.get("repair_dock_rate", 40), eco.get("repair_dock_range", 500)
        rate0, rng0 = repair_cfg
        for e in st.entities.values():
            if not e.operational or not e.is_station:
                continue
            sd = self.ds.stations.get(e.data_id)
            if not sd or sd.repair_rate <= 0:
                continue
            rate = sd.repair_rate * stats.effective_repair_rate(st, e.owner)
            for tid in st.grid.query_sphere(st.entities, e.pos, sd.radius + rng0):
                t = st.entity(tid)
                if t is None or t.owner != e.owner or t is e or t.is_planet:
                    continue
                from .crew import repair_life_support
                repair_life_support(t, rate * dt)
                if t.hull < t.max_hull:
                    t.hull = min(t.max_hull, t.hull + rate * dt)

        # --- hangar repair/reinforce for docked squadrons (handled in SquadronSystem)

    @staticmethod
    def recompute_command_capacity(state) -> None:
        """Called 1 Hz by GameManager. Writes PlayerState.command_capacity."""
        ds = DataStore.get()
        rules = ds.rules.get("sim", {})
        for p in state.players.values():
            cap = int(rules.get("command_capacity_base", 10))
            for e in state.entities.values():
                if e.operational and e.is_station and e.owner == p.id:
                    sd = ds.stations.get(e.data_id)
                    if sd:
                        cap += sd.command_capacity
            cap += int(stats.tech_bonus(state, p.id, "command_capacity_bonus"))
            eco = ds.rules.get("economy", {})
            for e in state.entities.values():
                if e.alive and e.is_planet and e.colonized_by == p.id:
                    cap += int(eco.get("planet_command_bonus", {}).get(e.data_id, 0))
            p.command_capacity = cap