"""Probe the frozen ships tick-by-tick: why is yaw barely moving?"""
import sys, math
sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from test_gameplay import make_game, run_for  # noqa
from game.core.vectors import Vec3
from game.core import commands
from game.systems import stats

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

WATCH = []
run_for(gm, 2.0)
for e in st.entities.values():
    if e.id in fleet.member_ids and e.alive and e.pos.dist(target) > 2000:
        WATCH.append(e.id)
WATCH = sorted(WATCH)[-3:]
print("watching:", WATCH)

# step tick-by-tick and dump state every 10 ticks
for i in range(30 * 8):  # 8 s
    gm.step(1 / 30)
    if i % 10:
        continue
    for eid in WATCH:
        e = st.entity(eid)
        tp = e.order_target_pos
        if tp is None:
            continue
        to = Vec3(tp.x - e.pos.x, tp.y - e.pos.y, tp.z - e.pos.z)
        desired = math.degrees(math.atan2(to.x, to.z))
        yaw = math.degrees(e.yaw)
        diff = ((desired - yaw + 180) % 360) - 180
        print(f"t={i/30:5.1f} id={eid:3d} {e.data_id[:20]:20s} yaw={yaw:7.1f} "
              f"desired={desired:7.1f} diff={diff:7.1f} spd={e.vel.length():6.1f} "
              f"eff_spd={stats.effective_speed(st, e):6.1f} turn={stats.effective_turn_rate(st, e):6.1f} "
              f"jump={e.jump_charge:5.2f} hyp={e.ability_active.get('hyperspace_transit', 0):5.2f} "
              f"dist_dest={e.pos.dist(tp):7.0f}")