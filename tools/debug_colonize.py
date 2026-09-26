"""Debug: colonization and full-loop assault traces."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import make_game, run_for
from game.core.vectors import Vec3

gm = make_game(ai=False)
st = gm.state
col = gm.factory.spawn_ship("imperial_colonizer", 0, Vec3(0, 0, 0))
planet = next(e for e in st.entities.values() if e.is_planet and e.data_id == "temperate")
ok = gm.construction.start_colonize(col.id, planet.id, 0)
print("start_colonize ok:", ok, "queue:", col.build_queue)
for i in range(60 * 60):
    gm.step(1 / 30)
    if i % 300 == 0:
        print(f"t={st.time:.0f} colonizer alive={col.alive} q={col.build_queue} "
              f"dist={col.pos.dist(planet.pos):.0f} colonized={planet.colonized_by}")
    if planet.colonized_by is not None:
        print("COLONIZED at", st.time)
        break