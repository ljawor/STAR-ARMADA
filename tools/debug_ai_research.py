"""Debug AI research path."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import make_game, run_for
from game.ai.ai import AIPlayer

gm = make_game()
st = gm.state
ai = AIPlayer(st, 1)
run_for(gm, 240)
stations = [(e.id, e.data_id) for e in st.entities.values() if e.is_station and e.owner == 1]
print("AI stations:", stations)
labs = [e for e in st.entities.values() if e.is_station and e.owner == 1
        and gm.ds.stations[e.data_id].research]
print("labs:", labs, "queues:", [(l.build_queue) for l in labs])
p1 = st.players[1]
print("researched:", p1.researched, "researching:", p1.researching)
avail = ai._maybe_research()
print("avail after call:", avail)
print("P1 credits:", p1.credits)