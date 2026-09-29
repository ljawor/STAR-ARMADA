"""Research-station UI: the station panel must show LIVE research progress.

Reported in play: "When researching we need to see the progress of research
either than : order: idle." A station running a tech showed a BLANK order line
and no progress anywhere.

Root cause: research state lives in Player.researching (per player, each job
pinned to the station that started it) and the HUD never read it. The
station's own order_type is "idle" the entire time the tech runs, so
ORDER: rendered as an empty string.

Testability note: HUD's panel drawing is pure pygame on a Surface, so it IS
testable headlessly. HUD.render() is NOT — it finishes by calling _upload(),
which binds a GL texture; with no GL context that call blocks forever
(measured: hangs inside render/hud.py:_upload -> OpenGL/platform/
baseplatform.py:487). So call the panel methods directly here. The
GL/pixel-level end-to-end check lives in tools/diag_research_progress.py.
"""
from __future__ import annotations

import unittest

import numpy as np
import pygame

from helpers import make_game, run_for
from render.hud import HUD
try:                        # colour constant only exists post-fix, so that this
    from render.hud import RESEARCH    # suite can still be run against the OLD
except ImportError:         # hud.py and fail on BEHAVIOUR, not on import
    RESEARCH = (168, 140, 255)

# left panel is Rect(10, 44, 320, 430); the research block starts at panel.y+70
# with the progress bar 16px below that, 10px tall.
LEFT_BAR_BAND = (14, 130, 296, 12)


def _research_station(gm, player):
    """Build a REAL research station for `player` and return it.

    skirmish01 starts with command_station + shipyard only, so spawn the
    station through the factory exactly as the sim would build it.
    """
    st = gm.state
    for e in st.entities.values():
        if e.alive and e.is_station and e.owner == player:
            gm.factory.spawn_station("research_station", player, e.pos.copy())
            break
    return next((e for e in st.entities.values()
                 if e.alive and e.data_id == "research_station"
                 and e.owner == player), None)


def _draw_panels(hud, selection, player):
    """One frame of panel drawing, skipping render()'s GL texture upload."""
    hud.overlay.fill((0, 0, 0, 0))
    hud.scroll_rects = []
    hud.buttons = []
    hud.scroll = {"ships": 0, "techs": 0, "stations": 0}
    hud._left_panel(selection, player)
    hud._right_panel(selection, player)


def _panel_texts(hud, selection, player):
    """Draw the panels and record every string painted."""
    seen = []
    orig = hud._label

    def spy(x, y, s, color=None, font=None):
        seen.append(str(s))
        return orig(x, y, s, color, font)

    hud._label = spy
    try:
        _draw_panels(hud, selection, player)
    finally:
        hud._label = orig
    return seen


def _research_px(hud):
    """Progress-bar pixels painted in the left panel's research band."""
    x0, y0, w, h = LEFT_BAR_BAND
    sub = pygame.surfarray.array3d(hud.overlay)[x0:x0 + w, y0:y0 + h]
    hit = (np.abs(sub.astype(int) - np.array(RESEARCH[:3])).sum(axis=2) <= 30)
    return int(hit.sum())


class TestStationPanelShowsResearch(unittest.TestCase):
    def setUp(self):
        pygame.font.init()

    def _started(self, seconds: float = 2.0):
        """A game with a research station mid-research; returns (gm, st, p, id)."""
        gm = make_game(ai=False)
        st = gm.state
        player = sorted(st.players)[0]
        station = _research_station(gm, player)
        assert station is not None, "could not spawn a research station"

        p = st.players[player]
        p.credits = p.materials = p.energy = 1_000_000
        p.researched.clear()
        self.assertTrue(gm.research.start_research(player, station.id,
                                                  "imp_weapons_1"),
                        "could not start research through the sim")
        run_for(gm, seconds)
        return gm, st, player, station.id

    def test_order_line_is_not_blank_while_researching(self):
        _gm, st, player, sid = self._started()
        hud = HUD(1280, 800, st)
        texts = _panel_texts(hud, {sid}, player)

        orders = [t for t in texts if t.startswith("ORDER:")]
        self.assertEqual(len(orders), 1, f"expected one ORDER row, got {orders}")
        self.assertEqual(orders[0], "ORDER: RESEARCHING",
                         "a researching station must not read ORDER: IDLE")
        self.assertTrue(any("RESEARCHING" in t and "%" not in t for t in texts),
                        "panel never names the tech being researched")
        self.assertTrue(any("% ·" in t and "remaining" in t for t in texts),
                        "panel never shows % / seconds remaining")

    def test_progress_bar_paints_and_tracks_the_job(self):
        gm, st, player, sid = self._started(seconds=0.0)
        hud = HUD(1280, 800, st)
        _draw_panels(hud, {sid}, player)
        before = _research_px(hud)

        run_for(gm, 5.0)
        _draw_panels(hud, {sid}, player)
        after = _research_px(hud)

        self.assertGreater(after, before + 40,
                           f"progress bar did not grow: {before} -> {after} px")

    def test_running_tech_is_not_also_offered_as_clickable(self):
        _gm, st, player, sid = self._started()
        hud = HUD(1280, 800, st)
        _draw_panels(hud, {sid}, player)

        offered = [b for b in hud.buttons
                   if b["kind"] == "research"
                   and b["payload"].get("tech_id") == "imp_weapons_1"]
        self.assertEqual(offered, [],
                         "the running tech is re-offered; clicking would be a no-op")
        self.assertTrue([b for b in hud.buttons if b["kind"] == "research"],
                        "no other tech is startable while one runs")

    def test_other_station_does_not_claim_the_job(self):
        _gm, st, player, sid = self._started()
        other = next((e for e in st.entities.values()
                      if e.is_station and e.owner == player and e.id != sid), None)
        if other is None:
            self.skipTest("start state has only one station")

        hud = HUD(1280, 800, st)
        texts = _panel_texts(hud, {other.id}, player)
        self.assertFalse(any(t == "ORDER: RESEARCHING" for t in texts),
                         "an unrelated station claims the research job")


if __name__ == "__main__":
    unittest.main()
