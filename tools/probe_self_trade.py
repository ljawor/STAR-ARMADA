"""Two of the player's own trade stations — does trading with themselves pay?

reward_owner = "destination", so a convoy delivered to the player's OWN other
station pays the same player cargo_credits. Measures the resulting credit
income with NO enemy involvement, i.e. whether two own stations are an
unbounded money loop, and compares against the stations' passive income.

Run: PYTHONPATH=. ./.venv/bin/python tools/probe_self_trade.py
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

print("trade_station data:")
sd = ds.stations["trade_station"]
print(f"  build_cost  = {getattr(sd, 'build_cost', '?')}")
print(f"  income      = {getattr(sd, 'income', '?')}")
print(f"  build_time  = {getattr(sd, 'build_time', '?')}")

P0 = st.players[0]
start = P0.credits
print(f"\nP0 credits at start = {start:,.0f}")

# control run: no trade stations at all
DT = 1 / 30.0


def measure(label, setup, seconds=180.0):
    global st, gm
    DataStore.reset()
    DataStore()
    gm = GameManager.start_skirmish(DataStore().maps["skirmish01"])
    st = gm.state
    P0 = st.players[0]
    P0.credits = 0.0          # isolate trading income from start income
    setup(gm, st)
    paid = {"n": 0, "cr": 0.0}

    def on_arrive(ev):
        paid["n"] += 1
        paid["cr"] += float(ev.data.get("cargo", 0.0))
    st.events.subscribe("convoy_arrived", on_arrive)
    for _ in range(int(seconds / DT)):
        gm.step(DT)
    convs = [e for e in st.entities.values()
             if e.alive and e.data_id == "trade_convoy"]
    print(f"\n[{label}] after {seconds:.0f}s")
    print(f"  P0 credits        = {st.players[0].credits:,.0f}")
    print(f"  credits/sec       = {st.players[0].credits / seconds:,.2f}")
    print(f"  convoys delivered = {paid['n']}  ({paid['cr']:,.0f}cr in cargo)")
    print(f"  convoys in flight = {len(convs)}")
    return st.players[0].credits / seconds


no_trade = measure("A: control, NO trade stations", lambda gm, st: None)
one = measure("B: ONE own trade station",
              lambda gm, st: gm.factory.spawn_station(
                  "trade_station", 0, Vec3(-3000, 0, -6000)))
two = measure("C: TWO own trade stations (self-trade!)",
              lambda gm, st: [
                  gm.factory.spawn_station("trade_station", 0,
                                           Vec3(-3000, 0, -6000)),
                  gm.factory.spawn_station("trade_station", 0,
                                           Vec3(3000, 0, -6000))])

print("\n=== summary (credits/sec, P0) ===")
print(f"  no stations : {no_trade:6.2f}")
print(f"  one station : {one:6.2f}")
print(f"  two (self)  : {two:6.2f}   <-- 2 own stations trading with each other")
print(f"\nself-trade delta over a 20-min match: "
      f"{(two - no_trade) * 1200:,.0f}cr")
print("PROBE_DONE")
