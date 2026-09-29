"""Diagnostic: the station panel must show LIVE research progress.

Reported: "When researching we need to see the progress of research either
than : order: idle." The left panel showed only a blank ORDER line for a
station that was visibly busy researching, and the right panel listed the
running tech as if it were still startable.

Root cause: research state lives in Player.researching (per player, each job
pinned to the station that started it), and the HUD never read it. The
station's own order_type stays "idle" the whole time, so ORDER: rendered as
an empty string.

This drives the REAL ResearchSystem against the REAL HUD and checks the
rendered panel pixels. Run:
    PYTHONPATH=. ./.venv/bin/python tools/diag_research_progress.py [outdir]
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.core.manager import GameManager          # noqa: E402
from game.data.store import DataStore              # noqa: E402
from game.systems.research import ResearchSystem   # noqa: E402
from render.hud import HUD                          # noqa: E402
try:                                                # colour only exists post-fix
    from render.hud import RESEARCH
except ImportError:                                 # run against the old HUD too
    RESEARCH = (168, 140, 255)

FAILS = []


def check(cond, label, detail=""):
    tag = "ok  " if cond else "FAIL"
    if not cond:
        FAILS.append(label)
    print(f"[{tag}] {label}{(' — ' + detail) if detail else ''}")


def research_bar_pixels(surface, color, band, tol=10):
    """Count px in a horizontal band matching `color` (the progress bar)."""
    x0, y0, w, h = band
    sub = pygame.surfarray.array3d(surface)[x0:x0 + w, y0:y0 + h]
    c = np.array(color[:3])
    hit = (np.abs(sub.astype(int) - c).sum(axis=2) <= tol * 3)
    return int(hit.sum())


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "saves"
    os.makedirs(outdir, exist_ok=True)

    pygame.init()
    pygame.display.set_mode((1280, 800), pygame.DOUBLEBUF | pygame.OPENGL)
    for _ in range(5):
        pygame.event.pump()
        pygame.time.wait(20)

    DataStore.reset()
    ds = DataStore()
    gm = GameManager.start_skirmish(ds.maps["skirmish01"])
    st = gm.state

    # ---- find the human player's research station, else build one
    player = sorted(st.players)[0]
    station = None
    for e in st.entities.values():
        if e.alive and e.is_station and e.owner == player:
            sd = ds.stations.get(e.data_id)
            if sd is not None and sd.research:
                station = e
                break
    if station is None:
        for e in st.entities.values():
            if e.alive and e.is_station and e.owner == player:
                e.data_id = "research_station"
                station = e
                break
    check(station is not None, "A0. a research station exists to test")
    if station is None:
        return finish()

    rs = getattr(gm, "research", None) or ResearchSystem(st)
    tech_id = "imp_weapons_1"
    tech = ds.techs[tech_id]
    p = st.players[player]
    p.credits += 100000
    p.materials += 100000
    p.energy += 100000

    started = rs.start_research(player, station.id, tech_id)
    check(started, "A1. research started through the REAL ResearchSystem")
    check(tech_id in p.researching, "A2. job registered in Player.researching")

    hud = HUD(1280, 800, st)
    hud.render({station.id}, None, player, False, "", 0.0, 0.0)

    # ---- left panel: find the painted research band
    # left panel is pygame.Rect(10, 44, 320, 430); the research block sits at
    # panel.y+70 (title) then the bar at +86, 10px tall.
    band = (14, 130, 296, 12)
    px_empty = research_bar_pixels(hud.overlay, RESEARCH, band)
    check(px_empty < 20, "B0. no research bar before the job has progressed",
          f"{px_empty} px")

    # ---- advance the sim so progress is real
    for _ in range(60):          # 2 s at 30 Hz
        gm.step(1 / 30.0)
    left = p.researching[tech_id]["time_left"]
    check(left < tech.research_time, "C0. time_left actually decreased",
          f"{left:0.1f}s of {tech.research_time:0.0f}s")

    hud.render({station.id}, None, player, False, "", 0.0, 0.0)
    px_half = research_bar_pixels(hud.overlay, RESEARCH, band)
    frac = 1.0 - left / tech.research_time
    check(px_half > px_empty + 40,
          "B1. research progress bar PAINTS as the job runs",
          f"{px_empty} -> {px_half} px at {frac * 100:0.0f}%")

    # "RESEARCHING" must appear somewhere in the left panel text region
    texts = []
    orig = hud._label
    def spy(x, y, s, color=None, font=None):
        texts.append((str(s), x, y, tuple(color[:3]) if color else None))
        return orig(x, y, s, color, font)
    hud._label = spy
    hud.render({station.id}, None, player, False, "", 0.0, 0.0)
    hud._label = orig

    joined = " | ".join(t[0] for t in texts)
    check(any(t[0].startswith("ORDER: RESEARCHING") for t in texts),
          "B2. ORDER line names the research (was blank)", joined[:110])
    check(any("RESEARCHING" in t[0] and "%" not in t[0] for t in texts),
          "B3. left panel names the tech being researched")
    check(any("% ·" in t[0] and "remaining" in t[0] for t in texts),
          "B4. left panel shows % + seconds remaining")
    check(any("IN PROGRESS" in t[0] for t in texts),
          "B5. right panel lists the running tech as IN PROGRESS")

    # the running tech must not ALSO be offered as a startable row
    offered = [b for b in hud.buttons
               if b["kind"] == "research"
               and b["payload"].get("tech_id") == tech_id]
    check(not offered,
          "B6. the running tech is not re-offered as clickable",
          f"{len(offered)} buttons")

    # ---- another tech must still be startable while one runs
    offerable = [b["payload"].get("tech_id") for b in hud.buttons
                 if b["kind"] == "research"]
    check(len(offerable) > 0,
          "B7. other techs remain startable", f"{offerable}")

    # ---- save a frame for the eyeball check
    pygame.image.save(hud.overlay, os.path.join(outdir, "diag_research_panel.png"))
    print(f"saved {os.path.join(outdir, 'diag_research_panel.png')}")

    # ---- it must disappear when the station is not the one researching
    other_id = -1
    for e in st.entities.values():
        if e.is_station and e.id != station.id and e.owner == player:
            other_id = e.id
            break
    if other_id != -1:
        hud2_texts = []
        hud2 = HUD(1280, 800, st)
        orig2 = hud2._label
        def spy2(x, y, s, color=None, font=None):
            hud2_texts.append(str(s))
            return orig2(x, y, s, color, font)
        hud2._label = spy2
        hud2.render({other_id}, None, player, False, "", 0.0, 0.0)
        check(not any("ORDER: RESEARCHING" in t for t in hud2_texts),
              "B8. a DIFFERENT station does not claim the job")
    return finish()


def finish():
    if FAILS:
        print(f"\nRESEARCH_DIAG_FAIL ({len(FAILS)}): {FAILS}")
        sys.exit(1)
    print("\nRESEARCH_DIAG_OK")


if __name__ == "__main__":
    main()
