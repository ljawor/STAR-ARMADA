"""Probe 3: tick-by-tick trace of frozen ship through movement system."""
import sys, math
sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from test_gameplay import make_game, run_for  # noqa
from game.core.vectors import Vec3
from game.core import commands
from game.systems import movement as mv_mod

gm = make_game(ai=False)
st = gm.state
ships = [e.id for e in st.entities.values()
         if e.alive and e.owner == 0 and (e.is_ship or e.is_squadron)]
st.queue_command(commands.FleetCreateCommand(0, ships, "Alpha",
                                             commander="aggressive", formation="wedge"))
run_for(gm, 0.5)
fleet = next(iter(st.fleets.values()))
flagship = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
target = flagship.pos + Vec3(3000, 0, 0)
st.queue_command(commands.PlayerCommand("move", 0, unit_ids=tuple(fleet.member_ids),
                                        target_pos=(target.x, target.y, target.z)))

# run until frozen ship found
for _ in range(30 * 10):
    gm.step(1 / 30)

frozen = None
for e in st.entities.values():
    if e.id in fleet.member_ids and e.alive and e.vel.length() < 10:
        frozen = e.id
        break
print("frozen:", frozen)
e = st.entity(frozen)

# monkey-patch: trace velocity through each system in manager order
from game.core import manager
trace = [frozen]
orig_step = gm.step

def traced_step(dt):
    before = {i: (st.entity(i).pos.copy(), st.entity(i).vel.copy())
              for i in trace if st.entity(i)}
    orig_step(dt)
    for i in trace:
        ent = st.entity(i)
        if ent is None:
            continue
        b_pos, b_vel = before[i]
        ds_ = ent.pos - b_pos
        print(f"  tick: pos moved {ds_.length():7.3f}  vel {ent.vel.length():7.2f} "
              f"(was {b_vel.length():7.2f})")

gm.step = traced_step
for _ in range(30):
    gm.step(1 / 30)

# check what orders look like now
ent = st.entity(frozen)
print("\nfinal order:", ent.order_type, ent.order_target_id, ent.order_target_pos)
print("vel:", ent.vel.length(), "yaw deg:", math.degrees(ent.yaw))