"""W10: the same workload on both sides, so a frame time can mean something.

The W05 and W07 numbers measured the producer publishing into rings, or the window drawing whatever
happened to be in them. Neither is a frame rate: the first excludes drawing, the second excludes the
simulation and the HUD composition. This script builds one content set per size, publishes it through
the real `LiveSession` (which composes the HUD, the cues, the emissive batch and the fog mask), and
then draws the resulting rings through the real window on the same content. Both sides see the same
hulls, planets and HUD, at the same 1280x800.

    .venv/bin/python tools/render/bench_equal_workload.py --sizes 200,400,600 --frames 60

Every number is a median of measured samples with its p95 beside it. Nothing here is a claim about
the whole game: the simulation is not stepped (the fixture state is static), no audio runs, and the
numbers are local to this machine.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def trim(scene, ships: int):
    """Keep the fixture's stations, planets and the first `ships` ships."""
    state = scene.manager.state
    keep = []
    for entity in state.entities.values():
        if entity.is_ship and not entity.is_station and not entity.is_planet:
            keep.append(entity.id)
    keep.sort()
    for entity_id in keep[ships:]:
        state.entities.pop(entity_id, None)
    return state


def publish(scene, frames: int, directory: Path):
    from render_bridge.live import LiveSession
    state = scene.manager.state
    session = LiveSession(state, scene.manager.ds, directory=str(directory),
                          local_player=0, size=(1280, 800))
    visible = {e.id for e in state.entities.values() if e.alive}
    selection = set(sorted(visible)[:8])
    for _ in range(frames):
        session.publish(state, selection=selection, visible_ids=visible, dt=1 / 30,
                        paused=False, message="", fps=60.0)
    report = session.report()
    session.close()
    return report


def draw(directory: Path, frames: int, report_path: Path):
    binary = ROOT / "render_cpp" / "build-w02" / "armada_viewer"
    cmd = [str(binary), "--snapshot", str(ROOT / "assets/cpp/catalogue.snap"),
           "--assets", str(ROOT)]
    for name, flag in (("frame.ring", "--ring"), ("hud.ring", "--overlay-ring"),
                       ("emit.ring", "--emit-ring"), ("markers.ring", "--marker-ring"),
                       ("fog.ring", "--fog-ring"), ("planets.ring", "--planet-ring")):
        cmd += [flag, str(directory / name)]
    cmd += ["--tables", str(directory / "frame.ring.tables"), "--frames", str(frames),
            "--report", str(report_path)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"viewer failed ({done.returncode}):\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}")
    return json.loads(report_path.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="200,400,600")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--out", default=str(ROOT / "artifacts/cpp-renderer/w10/bench.json"))
    args = ap.parse_args()

    from game.graphics_benchmark import make_fixture
    rows = []
    for text in args.sizes.split(","):
        ships = int(text)
        scene = make_fixture("four-player-combat-v1")
        state = trim(scene, ships)
        directory = Path(tempfile.mkdtemp(prefix=f"bench-{ships}-"))
        producer = publish(scene, args.frames, directory)
        window = draw(directory, args.frames, directory / "report.json")
        rows.append({
            "ships": ships,
            "instances": window.get("instances"),
            "cues": window.get("cues", {}).get("markers"),
            "shields": window.get("shields", {}).get("shells"),
            "emissive_primitives": window.get("emissive", {}).get("primitives"),
            "triangles_per_pass": window.get("submitted_triangles_per_pass"),
            "draw_calls_median": statistics.median(window.get("draw_calls_samples") or [0]),
            "producer": {k: v for k, v in producer.get("cost", {}).items()},
            "window": {
                "wall_median_ms": window["wall_frame"]["median_ms"],
                "wall_p95_ms": window["wall_frame"]["p95_ms"],
                "wall_mean_ms": window["wall_frame"]["mean_ms"],
                "gpu_median_ms": window["gpu_frame"]["median_ms"],
                "gpu_p95_ms": window["gpu_frame"]["p95_ms"],
                "samples": window["wall_frame"]["samples"],
            },
        })
        print(json.dumps(rows[-1], indent=1))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "fixture": "four-player-combat-v1 trimmed to N ships; stations, planets, HUD and fog kept",
        "resolution": [1280, 800],
        "frames": args.frames,
        "simulation": "not stepped - static state, so this is draw cost, not a frame rate of the game",
        "rows": rows,
    }, indent=2) + "\n")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
