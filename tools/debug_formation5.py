"""Probe 4: instrument MovementSystem for the frozen ship, print every decision."""
import sys, math
sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from test_gameplay import make_game, run_for  # noqa
from game.core.vectors import Vec3
from game.core import commands
from game.systems import stats
from game.systems.movement import MovementSystem

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
print("frozen:", frozen)
e = st.entity(frozen)
ms = gm.movement

orig_update = ms.update
def traced_update(dt):
    ent = gm.state.entity(frozen)
    if ent is None or not ent.alive:
        return orig_update(dt)
    # replicate movement code with prints
    st = ms.state
    target_pos = None
    target_entity = None
    if ent.order_target_id is not None:
        target_entity = st.entity(ent.order_target_id)
        if target_entity is not None:
            target_pos = target_entity.pos
    if target_pos is None and ent.order_target_pos is not None:
        target_pos = ent.order_target_pos
    if target_pos is None:
        print(f"  t={st.time:6.2f} NO DEST  vel={ent.vel.length():6.2f}")
        return orig_update(dt)
    to_target = target_pos - ent.pos
    dist = to_target.length()
    desired_yaw = math.atan2(to_target.x, to_target.z)
    diff = ms._angle_diff(desired_yaw - ent.yaw)
    facing = Vec3(math.sin(ent.yaw), 0.0, math.cos(ent.yaw))
    alignment = facing.dot(to_target.normalized())
    eff = stats.effective_speed(st, ent)
    print(f"  t={st.time:6.2f} dest_type={'ent' if target_entity else 'pos'} "
          f"dist={dist:7.0f} y_err={to_target.y:6.1f} yaw={math.degrees(ent.yaw):7.1f} "
          f"desired_yaw={math.degrees(desired_yaw):7.1f} diff={math.degrees(diff):6.2f} "
          f"align={alignment:6.3f} eff={eff:6.1f} vel={ent.vel.length():6.2f} "
          f"vel_dir_align={facing.dot(ent.vel.normalized()) if ent.vel.length() > 1e-6 else 0:6.2f}")
    return orig_update(dt)

ms.update = traced_update
for _ in range(45):
    gm.step(1 / 30)