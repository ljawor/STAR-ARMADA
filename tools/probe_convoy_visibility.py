"""Why can't I see trade convoys after building two trade stations?

Reproduces the reported play: a player builds 2 trade stations and looks for
convoys. Measures, from a real skirmish:

  1. time from station completion to the FIRST convoy spawn
  2. how many convoys spawn / arrive over a few minutes
  3. how big a convoy actually is on screen at tactical and close zoom
     (px), i.e. whether a player could plausibly notice one
  4. whether the AI's own trade station can act as the other market

Run: PYTHONPATH=. ./.venv/bin/python tools/probe_convoy_visibility.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game.core.manager import GameManager                    # noqa: E402
from game.core.vectors import Vec3                           # noqa: E402
from game.data.store import DataStore                        # noqa: E402

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

TRADE_POS = [Vec3(-9000, 0, -4000), Vec3(9000, 0, -4000)]

print("=== player builds 2 trade stations (P0) ===")
for p in TRADE_POS:
    gm.factory.spawn_station("trade_station", 0, p)
    print(f"  station built at {p.x:+,.0f},{p.z:+,.0f}")

cfg = gm.trading.cfg
print(f"\nspawn_interval = {cfg['spawn_interval']}s   speed = {cfg['speed']} u/s")
leg = TRADE_POS[0].dist(TRADE_POS[1])
print(f"distance between the two stations = {leg:,.0f} u")
print(f"-> convoy one-way flight = {leg / float(cfg['speed']):,.0f}s "
      f"({leg / float(cfg['speed']) / 60:.1f} min)")

# --- what is on the map right after building?
stations = [e for e in st.entities.values()
            if e.alive and e.data_id == "trade_station"]
print(f"\ntrade stations on map: {len(stations)} "
      f"(owners: {sorted(e.owner for e in stations)})")
convs = [e for e in st.entities.values()
         if e.alive and e.data_id == "trade_convoy"]
print(f"convoys IMMEDIATELY after building: {len(convs)}  <-- this is what "
      f"the player sees if they look right away")

# --- run the sim and watch for the first spawn
DT = 1 / 30.0
first_spawn_t = None
arrived = 0
seen_ids: set[int] = set()
log: list[tuple[float, str]] = []


def on_spawn(ev):
    global first_spawn_t
    log.append((st.time, "spawn"))
    if first_spawn_t is None:
        first_spawn_t = st.time


def on_arrive(ev):
    global arrived
    log.append((st.time, "arrive"))
    arrived += 1


st.events.subscribe("convoy_spawned", on_spawn)
st.events.subscribe("convoy_arrived", on_arrive)

RUN = 240.0
steps = int(RUN / DT)
for i in range(steps):
    gm.step(DT)
    if i % int(20 / DT) == 0:
        live = [e for e in st.entities.values()
                if e.alive and e.data_id == "trade_convoy"]
        seen_ids.update(e.id for e in live)
        print(f"  t={st.time:6.1f}s  live convoys={len(live):3d}  "
              f"arrived={arrived:3d}")

print(f"\n=== after {RUN:.0f}s of play ({RUN/60:.1f} min sim) ===")
spawns = sum(1 for _, k in log if k == "spawn")
print(f"convoys spawned  : {spawns}")
print(f"convoys arrived  : {arrived}")
if first_spawn_t is None:
    print("FIRST SPAWN: NEVER  <-- trading is dead")
else:
    print(f"first convoy spawned at t={first_spawn_t:.1f}s "
          f"({first_spawn_t / 60:.2f} min) after the stations were built")

# --- how far apart are convoys in flight (are they on screen at all)?
live = [e for e in st.entities.values()
        if e.alive and e.data_id == "trade_convoy"]
if live:
    c = live[0]
    dest = st.entity(c.convoy_dest)
    print(f"\nsample convoy: pos=({c.pos.x:+,.0f},{c.pos.z:+,.0f}) "
          f"dest={dest.data_id if dest else None} "
          f"{c.pos.dist(dest.pos) if dest else 0:,.0f}u to go")
    print(f"  radius={c.radius}u  visual={ds.ship_visual('trade_convoy')}")
    for name, dist in (("tactical", 2600.0), ("close", 900.0), ("far", 6000.0)):
        px_per_world = 800.0 / dist      # approx vertical fov -> 800px tall
        print(f"  at {name:8s} zoom (dist {dist:,.0f}u): "
              f"{c.radius * 2 * px_per_world:.1f} px wide")

print("PROBE_DONE")
