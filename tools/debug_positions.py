"""Trace ship positions during approach."""
from helpers import make_game
from game.core.vectors import Vec3
from game.core.commands import AttackCommand

gm = make_game(ai=False)
st = gm.state
fr0 = gm.factory.spawn_ship("imperial_frigate", 0, Vec3(-500, 0, 0))
fr1 = gm.factory.spawn_ship("imperial_frigate", 1, Vec3(500, 0, 0))
st.queue_command(AttackCommand(0, [fr0.id], fr1.id))
st.queue_command(AttackCommand(1, [fr1.id], fr0.id))
for i in range(60 * 12):
    gm.step(1 / 30)
    if i % 20 == 0:
        v0 = fr0.vel.length()
        v1 = fr1.vel.length()
        print(f"t={st.time:5.1f} d={fr0.pos.dist(fr1.pos):6.0f} "
              f"p0=({fr0.pos.x:7.0f},{fr0.pos.z:7.0f}) v0={v0:5.1f} yaw0={fr0.yaw:5.2f} "
              f"p1=({fr1.pos.x:7.0f},{fr1.pos.z:7.0f}) v1={v1:5.1f} yaw1={fr1.yaw:5.2f}")