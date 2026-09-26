"""Debug why two attacking frigates never kill each other."""
from helpers import make_game
from game.core.vectors import Vec3
from game.core.commands import AttackCommand

gm = make_game(ai=False)
st = gm.state
fr0 = gm.factory.spawn_ship("imperial_frigate", 0, Vec3(-500, 0, 0))
fr1 = gm.factory.spawn_ship("imperial_frigate", 1, Vec3(500, 0, 0))
st.queue_command(AttackCommand(0, [fr0.id], fr1.id))
st.queue_command(AttackCommand(1, [fr1.id], fr0.id))
for i in range(60 * 30):
    gm.step(1 / 30)
    if i % 150 == 0:
        print(f"t={st.time:.1f} dist={fr0.pos.dist(fr1.pos):.0f} "
              f"fr0 hp={fr0.hull:.0f}/{fr0.max_hull:.0f} sh={fr0.total_shield():.0f} "
              f"fr1 hp={fr1.hull:.0f}/{fr1.max_hull:.0f} sh={fr1.total_shield():.0f} "
              f"order0={fr0.order_type} tgt0={fr0.current_target} "
              f"cd={ {k: round(v,2) for k,v in fr0.weapon_cooldowns.items()} } "
              f"proj={len(st.projectiles)}")
    if not fr0.alive or not fr1.alive:
        print("DEATH at", st.time)
        break