"""Extended AI trace: 6 minutes, watching lab construction + research."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import make_game, run_for

gm = make_game()
st = gm.state
for i in range(60 * 360):
    gm.step(1 / 30)
    if i % 1800 == 0 and i > 0:
        stations = [e.data_id for e in st.entities.values() if e.is_station and e.owner == 1]
        ships = sum(1 for e in st.entities.values()
                    if e.alive and e.owner == 1 and (e.is_ship or e.is_squadron))
        p1 = st.players[1]
        print(f"t={st.time:.0f} stations={stations} ships={ships} "
              f"cr={p1.credits:.0f} researched={p1.researched} researching={list(p1.researching)}")
p1 = st.players[1]
print("FINAL researched:", p1.researched, "researching:", list(p1.researching))