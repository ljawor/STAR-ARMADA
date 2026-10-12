"""FormationSystem — fleet formation slots and assignment (spec §18).

Fleet flagship sits at slot 0; members get offset slots by formation pattern
(line/wedge/column/diamond/screen/escort). Ships steer toward their slot while the
fleet has a rally point; slots are recomputed on membership/formation change.
"""
from __future__ import annotations

from game.core import detmath as math  # deterministic sim math, never the platform libm
from ..core.vectors import Vec3
from ..data.store import DataStore


class FormationSystem:
    def __init__(self, state):
        self.state = state
        self.ds = DataStore.get()

    # ------------------------------------------------------------------ slots
    def fleet_flagship(self, fleet):
        st = self.state
        if fleet.flagship_id is not None:
            e = st.entity(fleet.flagship_id)
            if e is not None:
                return e
        # pick largest hull member
        best, best_hull = None, -1.0
        for mid in fleet.member_ids:
            e = st.entity(mid)
            if e is not None and e.max_hull > best_hull:
                best, best_hull = e, e.max_hull
        return best

    def compute_slots(self, fleet) -> dict:
        """Returns {entity_id: Vec3 offset from flagship}."""
        st = self.state
        ds = self.ds
        cfg = ds.rules.get("formations", {}).get(fleet.formation, {"spacing": 1.6, "depth": 2})
        spacing, depth = cfg.get("spacing", 1.6), cfg.get("depth", 2)
        members = [st.entity(mid) for mid in sorted(fleet.member_ids)]
        members = [m for m in members if m is not None]
        if not members:
            return {}
        # flagship first
        flagship = self.fleet_flagship(fleet)
        if flagship is None:
            return {}
        ordered = [flagship] + [m for m in members if m.id != flagship.id]
        # sort rest by hull descending so big ships get inner slots
        rest = sorted([m for m in ordered[1:]],
                      key=lambda m: -m.max_hull)
        ordered = [flagship] + rest

        offsets = {flagship.id: Vec3(0, 0, 0)}
        slot_index = 0
        # spacing scales with flagship radius (bigger fleets spread out)
        base = max(flagship.radius * spacing, 220.0)
        for m in rest:
            slot_index += 1
            ring = max(1, (slot_index + depth - 1) // depth)   # which ring
            pos_in_ring = (slot_index - 1) % depth
            n_ring = depth
            ang = (pos_in_ring / max(1, n_ring)) * 2 * math.pi + ring * 0.7
            if fleet.formation == "line":
                # two columns behind flagship
                side = -1 if slot_index % 2 == 0 else 1
                row = (slot_index + 1) // 2
                off = Vec3(side * base * 0.9, 0, -row * base * 1.1)
            elif fleet.formation == "wedge":
                side = -1 if slot_index % 2 == 0 else 1
                row = (slot_index + 1) // 2
                off = Vec3(side * row * base * 0.9, 0, -row * base * 0.9)
            elif fleet.formation == "column":
                off = Vec3(0, 0, -slot_index * base * 1.2)
            elif fleet.formation == "diamond":
                diag = [Vec3(base, 0, 0), Vec3(0, 0, base),
                        Vec3(-base, 0, 0), Vec3(0, 0, -base)]
                ring_i = (slot_index - 1) // 4
                k = (slot_index - 1) % 4
                off = diag[k] * (1 + ring_i)
            elif fleet.formation == "screen":
                # combat air patrol / picket screen around flagship
                ang = slot_index * (2 * math.pi / max(6, len(rest)))
                rr = base * 1.6
                off = Vec3(math.sin(ang) * rr, 0, math.cos(ang) * rr)
            else:  # escort
                ang = slot_index * 2.399   # golden-angle spread
                rr = base * (0.8 + 0.35 * (slot_index % 3))
                off = Vec3(math.sin(ang) * rr, 0, math.cos(ang) * rr)
            # ring spacing multiplier
            off = off * (1.0 + 0.25 * (ring - 1))
            offsets[m.id] = off
        return offsets

    # ------------------------------------------------------------------ orders
    def apply_fleet_move(self, fleet, target: Vec3) -> None:
        """Issue a formation move: flagship goes to target, members to slots.

        Re-issued at most every 3 seconds; otherwise a moving formation's offsets
        fight the flagship's motion and the whole formation crawls.
        """
        st = self.state
        now = st.time
        if getattr(fleet, "_last_move_issue", -999.0) + 3.0 > now:
            return
        fleet._last_move_issue = now
        offsets = self.compute_slots(fleet)
        flagship = self.fleet_flagship(fleet)
        if flagship is None:
            return
        yaw_hint = 0.0
        to_t = target - flagship.pos
        if to_t.length_sq() > 1.0:
            yaw_hint = math.atan2(to_t.x, to_t.z)
        for mid in fleet.member_ids:
            e = st.entity(mid)
            if e is None:
                continue
            off = offsets.get(mid, Vec3(0, 0, 0))
            # rotate offset by fleet heading
            s, c = math.sin(yaw_hint), math.cos(yaw_hint)
            wx = off.x * c + off.z * s
            wz = -off.x * s + off.z * c
            dest = Vec3(target.x + wx, target.y + off.y * 0.3, target.z + wz)
            e.order_type = "move"
            e.order_target_pos = dest
            e.order_target_id = None
        fleet.rally_point = target.to_dict()

    def update(self, dt: float) -> None:
        # formation maintenance: idle ships drift back to slot if leader moved
        # (kept light — slots are enforced on orders; drift correction at 2 Hz here)
        st = self.state
        if (st.tick % 15) != 0:
            return
        for fleet in st.fleets.values():
            if not fleet.member_ids or fleet.stance == "retreat":
                continue
            flagship = self.fleet_flagship(fleet)
            if flagship is None:
                continue
            rally = getattr(fleet, "rally_point", None)
            if not rally:
                continue
            # if flagship idle and far from rally, nothing to enforce
            if flagship.order_type == "idle" and flagship.pos.dist(
                    Vec3(*rally)) < 400:
                continue
            offsets = self.compute_slots(fleet)
            for mid in fleet.member_ids:
                e = st.entity(mid)
                if e is None or e.order_type != "idle" or e.current_target is not None:
                    continue
                off = offsets.get(mid)
                if off is None:
                    continue
                s, c = math.sin(flagship.yaw), math.cos(flagship.yaw)
                wx = off.x * c + off.z * s
                wz = -off.x * s + off.z * c
                dest = Vec3(flagship.pos.x + wx, flagship.pos.y + off.y * 0.3,
                            flagship.pos.z + wz)
                if e.pos.dist(dest) > 600:
                    e.order_type = "move"
                    e.order_target_pos = dest
                    e.order_target_id = None