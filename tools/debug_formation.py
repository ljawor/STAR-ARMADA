"""Debug the formation test stall: run the exact test scenario, print per-ship state."""
import sys, math
sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from test_gameplay import make_game, run_for  # noqa
from game.core.vectors import Vec3
from game.core.commands import PlayerCommand

gm = make_game(ai=False)
st = gm.state
ships = [e.id for e in st.entities.values()
         if e.alive and e.owner == 0 and (e.is_ship or e.is_squadron)]
st.queue_command(type("F", (), {})() if False else
                 __import__("game.core.commands", fromlist=["FleetCreateCommand"]).FleetCreateCommand(
                     0, ships, "Alpha", commander="aggressive", formation="wedge"))
run_for(gm, 0.5)
fleet = next(iter(st.fleets.values()))
flagship = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
target = flagship.pos + Vec3(3000, 0, 0)
st.queue_command(PlayerCommand("move", 0, unit_ids=tuple(fleet.member_ids),
                               target_pos=(target.x, target.y, target.z)))

# track per-tick state of the two worst ships every 5 s
for step in range(6):
    run_for(gm, 5)
    rows = []
    for e in st.entities.values():
        if e.id in fleet.member_ids and e.alive:
            d = e.pos.dist(target)
            rows.append((d, e.data_id, e.id,
                         round(math.degrees(e.yaw), 0),
                         round(e.vel.length(), 1),
                         e.order_type,
                         None if e.order_target_pos is None else
                         round(e.pos.dist(e.order_target_pos), 0)))
    rows.sort(reverse=True)
    avg = sum(r[0] for r in rows) / len(rows)
    print(f"--- t={5*(step+1):.0f}s avg_dist={avg:0.0f}")
    for d, did, eid, yaw, spd, ot, od in rows[:4]:
        print(f"   dist={d:7.0f} {did:26s} id={eid:3d} yaw={yaw:5.0f} spd={spd:6.1f} "
              f"order={ot:6s} to_dest={od}")