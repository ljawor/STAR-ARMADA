"""Debug script: run inside project venv. Traces AI build failure."""
from game.core.manager import GameManager
from game.ai.ai import AIPlayer
from game.data.store import DataStore
import json

map_def = json.load(open('assets/data/maps/skirmish01.json'))
gm = GameManager.start_skirmish(map_def)
st = gm.state
ai = AIPlayer(st, 1)
home = ai.home_station()
cons = [e for e in ai.my_units() if e.is_construction and ai._is_builder(e)]
site = ai._find_asteroid_site(home)
p = st.players[1]

ds = DataStore.get()
sd = ds.resolve_station("mining_station")
unit = ds.resolve_ship(cons[0].data_id)
print("can_build_stations:", unit.can_build_stations)
cost = gm.construction.factory.station_build_cost("mining_station")
print("cost:", cost)
print("can_pay:", gm.construction.can_pay(1, cost))
print("builder is_construction:", cons[0].is_construction, "station_id ok")

# check placement validation manually
b = st.map_info.bounds
print("in bounds:", abs(site.x) <= b)
for e in st.entities.values():
    if not e.alive:
        continue
    if e.is_planet and site.dist(e.pos) < e.radius + sd.radius + 100:
        print("PLANET BLOCK:", e.data_id, e.radius, sd.radius, site.dist(e.pos))
    if e.is_station and e.pos.dist(site) < (e.radius + sd.radius) * 1.6:
        print("STATION BLOCK:", e.data_id, site.dist(e.pos), (e.radius + sd.radius) * 1.6)
req = sd.requires_range or {}
print("requires:", req)
for req_kind, rng in req.items():
    ok = False
    for e in st.entities.values():
        if e.alive and e.data_id == req_kind and site.dist(e.pos) <= rng:
            ok = True
            break
    print(f"require {req_kind} rng {rng}: {ok}")