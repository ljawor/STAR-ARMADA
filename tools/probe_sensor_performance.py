"""Reproducible isolated sensor/combat benchmark; never alters the working tree.

Run: PYTHONPATH=. .venv/bin/python tools/probe_sensor_performance.py
Each implementation runs in a fresh subprocess with identical 200-corvette
combat setup. The temporary pre-fog control removes live visibility gates and
exploration, not combat/movement/AI work. The eager reference reproduces the
original all-source aggregation. Timings exclude setup and instrumentation;
separate cProfile ticks report source-build/effective-range call counts.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install_reference(mode):
    from game.core.state import GameState
    from game.systems.visibility import VisibilitySystem
    if mode == "control":
        # An isolated, temporary pre-fog implementation in this child process.
        GameState.can_see = lambda st, pid, eid: pid in st.players and st.entity(eid) is not None
        GameState.is_position_visible = lambda st, pid, pos: pid in st.players
        VisibilitySystem.update = lambda self, dt=0: None
    elif mode == "eager":
        def sources(st, pid):
            from game.systems.stats import effective_sensor_range
            allies = st.allied_player_ids(pid)
            result = []
            for e in sorted(st.entities.values(), key=lambda e: e.id):
                if e.alive and e.owner in allies and (e.is_ship or e.is_station or e.is_squadron):
                    radius = effective_sensor_range(st, e)
                    if radius > 0:
                        result.append((e, radius))
            return result
        def visible(st, pid, pos):
            return any((e.pos.x-pos.x)**2 + (e.pos.y-pos.y)**2 + (e.pos.z-pos.z)**2
                       <= radius**2 for e, radius in st.sensor_sources(pid))
        def can_see(st, pid, eid):
            e = st.entity(eid)
            if pid not in st.players or e is None:
                return False
            return ((not e.is_planet and e.owner in st.allied_player_ids(pid))
                    or visible(st, pid, e.pos))
        GameState.sensor_sources = sources
        GameState.is_position_visible = visible
        GameState.can_see = can_see


def make_combat(units):
    from game.core.manager import GameManager
    from game.core.state import PlayerState
    from game.core.vectors import Vec3
    gm = GameManager()
    st = gm.state
    st.players = {0: PlayerState(0, team=0), 1: PlayerState(1, team=1)}
    st.map_info.nebulas = []
    for i in range(units):
        owner = i % 2
        index = i // 2
        e = gm.factory.spawn_ship("imperial_corvette", owner,
                                  Vec3(-300 if owner == 0 else 300, 0,
                                       (index % 20 - 10) * 65 + (index // 20) * 7),
                                  yaw=1.5707963267948966 if owner == 0 else -1.5707963267948966)
        e.order_type = "hold"
    # Keep annihilation victory from turning later samples into no-op steps.
    for owner in (0, 1):
        station = gm.factory.spawn_station("command_station", owner,
                                           Vec3(-10000 if owner == 0 else 10000, 0, 0))
        station.sensor_range = 0
    st.grid.rebuild(st.entities)
    gm.visibility.update()  # Initial map exploration is setup, not a combat tick.
    return gm


def child(args):
    from game.net.replay import state_checksum
    install_reference(args.mode)
    gm = make_combat(args.units)
    samples = []
    for _ in range(args.ticks):
        start = time.perf_counter_ns()
        gm.step(1 / 30)
        samples.append((time.perf_counter_ns() - start) / 1e6)
    assert gm.state.tick == args.ticks and not gm.state.game_over, "Benchmark stopped early"
    combat = gm.state.to_dict(precise=True)
    for field in ("explored_cells", "discovered_planets"):
        combat.pop(field, None)
    import hashlib
    checksum = hashlib.sha256(json.dumps(combat, sort_keys=True).encode()).hexdigest()
    # Count separately, from the same initial scenario, without timing the profiler.
    counted = make_combat(args.units)
    counted.state._sensor_queries = None  # Include first range fills in call counts.
    profile = cProfile.Profile()
    profile.enable()
    for _ in range(10):
        counted.step(1 / 30)
    profile.disable()
    calls = {}
    for entry in profile.getstats():
        code = entry.code
        if hasattr(code, "co_name") and code.co_name in ("sensor_sources", "sources", "effective_sensor_range"):
            calls[code.co_name] = calls.get(code.co_name, 0) + entry.callcount
    print(json.dumps({"mode": args.mode, "units": args.units, "ticks": args.ticks,
                      "mean_ms": statistics.mean(samples), "median_ms": statistics.median(samples),
                      "p95_ms": sorted(samples)[max(0, int(len(samples) * .95) - 1)],
                      "max_ms": max(samples), "combat_checksum": checksum,
                      "profile_ticks": 10, "calls": calls,
                      "alive": sum(e.alive for e in gm.state.entities.values()),
                      "executed_ticks": gm.state.tick, "game_over": gm.state.game_over}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=int, default=200)
    parser.add_argument("--ticks", type=int, default=60)
    parser.add_argument("--mode", choices=("optimized", "eager", "control"))
    args = parser.parse_args()
    if args.mode:
        child(args)
        return
    results = []
    for mode in ("control", "eager", "optimized"):
        command = [sys.executable, str(Path(__file__).resolve()), "--mode", mode,
                   "--units", str(args.units), "--ticks", str(args.ticks)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        row = json.loads(result.stdout)
        results.append(row)
        print(json.dumps(row), flush=True)
    assert len({r["combat_checksum"] for r in results}) == 1, "Combat behavior diverged"
    print("COMBAT_CHECKSUMS_MATCH")
    print(f"optimized/control mean ratio: {results[2]['mean_ms'] / results[0]['mean_ms']:.3f}")
    print(f"eager/optimized mean ratio: {results[1]['mean_ms'] / results[2]['mean_ms']:.3f}")


if __name__ == "__main__":
    main()
