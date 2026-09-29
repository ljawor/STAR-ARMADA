"""End-to-end: build 2 trade stations THE PLAYER'S WAY, then look for convoys.

Uses the real construction queue + commands (not instant spawn_station), then
reports convoys in play — answering "I built 2 trade stations, where are the
convoys?" with the true in-game timing.

Run: PYTHONPATH=. ./.venv/bin/python tools/probe_build_traders.py
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

P0 = st.players[0]
P0.credits = 50000.0                      # afford two stations
print(f"trade_station cost/build_time: ")
sd = ds.stations["trade_station"]
print(f"  build_cost={getattr(sd,'build_cost','?')} "
      f"build_time={getattr(sd,'build_time','?')}s")

# find a legal site via the sim's own validator (same one the ghost uses)
builder = next(e for e in st.entities.values()
               if e.alive and e.is_construction and e.owner == 0)
print(f"\nbuilder = {builder.data_id} id={builder.id} at "
      f"({builder.pos.x:+,.0f},{builder.pos.z:+,.0f})")

sites = []
for ang in range(0, 360, 10):
    import math
    p = builder.pos + Vec3(math.cos(math.radians(ang)) * 2200.0, 0.0,
                           math.sin(math.radians(ang)) * 2200.0)
    ok, why = st._construction_system.check_site("trade_station", p, builder)
    sites.append((ok, why, p))
legal = [s for s in sites if s[0]]
print(f"legal sites around the builder: {len(legal)}/36 "
      f"(reasons: {sorted({w for ok, w, _ in sites if not ok})[:3]})")

# queue both stations exactly as a player build command would
DT = 1 / 30.0
from game.core.commands import BuildStationCommand             # noqa: E402

for ok, why, p in legal[:2]:
    cmd = BuildStationCommand(0, builder.id, "trade_station", p)
    st.command_queue.append(cmd)
    print(f"  queued trade_station at ({p.x:+,.0f},{p.z:+,.0f})")

built_at = None
first_convoy = None

def on_station(ev):
    global built_at
    if ev.data.get("station") == "trade_station" and built_at is None:
        built_at = st.time

def on_convoy(ev):
    global first_convoy
    if first_convoy is None:
        first_convoy = st.time

st.events.subscribe("station_built", on_station)
st.events.subscribe("convoy_spawned", on_convoy)

RUN = 300.0
for i in range(int(RUN / DT)):
    gm.step(DT)
    if i % int(30 / DT) == 0:
        stations = [e for e in st.entities.values()
                    if e.alive and e.data_id == "trade_station"]
        convs = [e for e in st.entities.values()
                 if e.alive and e.data_id == "trade_convoy"]
        note = ""
        if not stations:
            note = " (no stations yet)"
        elif len(stations) < 2:
            note = " (1 station -> trading needs 2)"
        print(f"  t={st.time:6.1f}s  trade_stations={len(stations)}  "
              f"convoys={len(convs):2d}{note}")

print(f"\n=== result ===")
print(f"first station completed  : t={built_at if built_at is None else f'{built_at:.1f}s'}")
print(f"first convoy spawned     : t={first_convoy if first_convoy is None else f'{first_convoy:.1f}s'}")
if built_at is not None and first_convoy is not None:
    print(f"delay from station to first convoy: {first_convoy - built_at:.1f}s")
print("PROBE_DONE")
