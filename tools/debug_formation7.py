"""Probe 6: instrument SeparationSystem for frozen ship; find the pusher."""
import sys, math
sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from test_gameplay import make_game, run_for  # noqa
from game.core.vectors import Vec3
from game.core import commands

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
run_for(gm, 8.0)

frozen = next((e.id for e in st.entities.values()
               if e.id in fleet.member_ids and e.alive and e.vel.length() < 10), None)
e = st.entity(frozen)
print(f"frozen={frozen} pos={e.pos.x:0.0f},{e.pos.y:0.0f},{e.pos.z:0.0f}")

sep = gm.separation
orig = sep.update
def traced(dt):
    orig(dt)
    ent = gm.state.entity(frozen)
    # which planets overlap?
    for p in gm.state.entities.values():
        if p.alive and p.is_planet and p.data_id != "asteroid_field":
            d = ent.pos.dist(p.pos)
            rr = p.radius + ent.radius + 40
            if d < rr + 200:
                print(f"    planet {p.data_id} pos=({p.pos.x:0.0f},{p.pos.y:0.0f},{p.pos.z:0.0f}) "
                      f"d={d:0.0f} rr={rr:0.0f} OVERLAP={d < rr}")
    print(f"    after sep: vel={ent.vel.length():6.2f}")
sep.update = traced
for _ in range(3):
    gm.step(1 / 30)
    ent = gm.state.entity(frozen)
    print(f"  pos=({ent.pos.x:0.1f},{ent.pos.y:0.1f},{ent.pos.z:0.1f}) "
          f"vel=({ent.vel.x:6.2f},{ent.vel.y:6.2f},{ent.vel.z:6.2f}) "
          f"yaw={math.degrees(ent.yaw):6.1f}")