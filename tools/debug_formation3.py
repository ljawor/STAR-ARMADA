"""Probe 2: dump full order state + nearby entities for the frozen ship."""
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

run_for(gm, 6.0)
for e in st.entities.values():
    if e.id in fleet.member_ids and e.alive and e.vel.length() < 10:
        print(f"\n=== FROZEN id={e.id} {e.data_id}")
        print(f"    order_type={e.order_type!r} order_target_id={e.order_target_id} "
              f"order_target_pos={e.order_target_pos}")
        print(f"    current_target={e.current_target} fleet_id={e.fleet_id} "
              f"jump_charge={e.jump_charge} stance={getattr(e, 'stance', None)}")
        t = st.entity(e.order_target_id) if e.order_target_id is not None else None
        if t is not None:
            print(f"    target entity: {t.data_id} dist={e.pos.dist(t.pos):0.0f} "
                  f"radius={t.radius} standoff={t.radius + e.radius * 2.2 + 30:0.0f}")
        if e.order_target_pos is not None:
            print(f"    dist to order_target_pos: {e.pos.dist(e.order_target_pos):0.0f}")
        # nearest 3 entities
        near = sorted((st.entity(o) for o in st.entities
                       if o != e.id and st.entity(o) and st.entity(o).alive
                       and not st.entity(o).is_planet),
                      key=lambda x: e.pos.dist(x.pos))[:3]
        for n in near:
            print(f"    near: id={n.id:3d} {n.data_id[:24]:24s} dist={e.pos.dist(n.pos):7.0f} "
                  f"r={n.radius:5.0f} vel={n.vel.length():6.1f}")
        # who re-issues orders? check fleet rally + offsets
        fl = st.fleets.get(e.fleet_id)
        if fl is not None:
            print(f"    fleet rally={fl.rally_point} members={len(fl.member_ids)}")
        break