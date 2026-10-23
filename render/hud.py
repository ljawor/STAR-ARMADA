"""HUD: professional fleet-command interface drawn as a 2D overlay.

Reads GameState only (never mutates sim). Renders panels to a pygame Surface,
uploads it as a GL texture and draws it as a fullscreen quad over the 3D scene.

Layout (spec §33/§34):
  top bar     Credits | Materials | Energy | Crew | Command Capacity | clock
  left        selected-unit information panel
  right       contextual build / research / production panel
  bottom-left event log
  bottom-right minimap

The HUD declares clickable buttons (rects + payload) that render/input.py
translates into queued PlayerCommands — the HUD itself queues nothing.
"""
from __future__ import annotations

import math
from contextlib import contextmanager

import pygame

from render import i18n

from OpenGL.GL import (
    glBegin, glBindTexture, glBlendFunc, glColor3f, glColor4f, glDisable,
    glEnable, glEnd, glPopMatrix, glPushMatrix, glTexCoord2f, glTexImage2D,
    glTexParameteri, glVertex2f, GL_BLEND, GL_CLAMP, GL_DEPTH_TEST,
    GL_MODELVIEW, GL_ONE_MINUS_SRC_ALPHA, GL_PROJECTION, GL_QUADS,
    GL_RGBA, GL_SRC_ALPHA, GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
    glMatrixMode, glLoadIdentity, glOrtho, glClear,
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
    GL_UNSIGNED_BYTE, GL_LINEAR,
)

from render.overlay_upload import OpRecorder, OverlayUploader, painter as _p
from game.core.entity import QUADRANTS
from render.fog import FogMask, known_entities
from game.data.store import DataStore

# ---------------------------------------------------------------- palette (blue-gray)
PANEL_BG = (14, 18, 28, 205)
PANEL_EDGE = (60, 80, 110, 220)
HEADER_BG = (22, 30, 46, 230)
TXT = (214, 224, 238)
TXT_DIM = (128, 142, 164)
ACCENT = (86, 140, 220)
COLLECTION = (89, 242, 204)     # render/renderer.py::_draw_collection_points (0.35, 0.95, 0.8)
WARN = (232, 168, 76)
BAD = (232, 92, 76)
GOOD = (110, 200, 120)
BAR_BG = (34, 44, 62, 255)
BAR_SHIELD = (84, 150, 220)
BAR_HULL = (110, 200, 120)
BAR_STRUCT = (150, 150, 160)
# stb's em-height includes ascent/descent padding; match visible pygame ink
# before applying the requested .75 panel transform (real-main pixel guard).
NATIVE_TEXT_EM_SCALE = 1.5
# The native em above is tuned for the 12/15/19/22 px panel labels. At the banner and status sizes
# Noto's cap height lands about 45% above the menlo bitmap those labels replaced, so the world HUD
# text is scaled back to the size it had on the overlay.
WORLD_HUD_TEXT_SCALE = 0.6
TRADE = (226, 196, 120)          # cargo / trade income readouts
RESEARCH = (168, 140, 255)       # research progress bars / readouts
DRAG_FILL = (86, 140, 220, 26)   # box-select rectangle (subtle tint)
DRAG_EDGE = (170, 215, 255, 200)

LOG_TYPES = ("unit_destroyed", "station_built", "research_complete",
             "planet_colonized", "construction_complete")


def ship_rank_panel_data(entity, store=None, experience=None):
    """Read-only rank readouts; combat power comes from shared sim helpers.

    Optional dependencies keep the panel model testable without SDL or GL.
    Defense multiplier is incoming damage, as defined by the sim API.
    """
    if not (entity.is_ship or entity.is_squadron):
        return None
    if store is None:
        store = DataStore.get()
    ship = store.ships.get(entity.data_id)
    if ship is None:
        return None
    if experience is None:
        from game.systems import experience
    rank = experience.rank_for(entity)
    cap = experience.max_rank(entity)
    if rank >= cap:
        xp_text = f"MAX RANK · XP {entity.xp:,.0f}"
    else:
        if hasattr(experience, "rank_info"):
            threshold = experience.rank_info(entity)["next_threshold"]
        else:
            # Compatibility for injected helpers exposing the original API.
            from game.systems.experience import DEFAULT_LEVELS
            levels = store.rules.get("experience", {}).get("levels", DEFAULT_LEVELS)
            threshold = levels[rank] * ship.veteran_xp / 100.0
        xp_text = f"XP {entity.xp:,.0f} / {threshold:,.0f} · NEXT RANK"
    return {
        "rank_text": f"RANK {rank}/{cap}",
        "xp_text": xp_text,
        "attack_text": f"ATTACK +{(experience.attack_multiplier(entity) - 1) * 100:.1f}%",
        "defense_text": f"DAMAGE REDUCTION {(1 - experience.defense_multiplier(entity)) * 100:.1f}%",
    }


def selected_ability_data(state, selection, local_player, store=None):
    """Read only own, live detected hulls; deduplicate capabilities, not ships."""
    store = store or DataStore.get()
    groups = {}
    for eid in sorted(set(selection)):
        e = state.entity(eid)
        if (e is None or not e.alive or e.owner != local_player
                or not state.can_see(local_player, eid)):
            continue
        sd = store.ships.get(e.data_id)
        for aid in sorted(set(sd.abilities if sd else [])):
            ad = store.abilities.get(aid)
            if ad is None:
                continue
            row = groups.setdefault(aid, {'ability_id': aid, 'count': 0,
                'unit_ids': [], 'cooldowns': [], 'low_energy': 0})
            row['count'] += 1
            cd = e.ability_cooldowns.get(aid, 0)
            if cd > 0:
                row['cooldowns'].append(cd)
            elif e.energy < ad.energy_cost:
                row['low_energy'] += 1
            else:
                row['unit_ids'].append(eid)
    return [groups[aid] for aid in sorted(groups)]


class HUD:
    """Composited 2D overlay. Pure view: render(state, selection) -> GL quad."""

    def __init__(self, width: int, height: int, state):
        self.width = width
        self.height = height
        self.state = state
        self.fog = FogMask()
        self.ds = DataStore.get()
        pygame.font.init()
        self.font = pygame.font.SysFont("menlo,consolas,monaco", 15)
        self.font_big = pygame.font.SysFont("menlo,consolas,monaco", 19, bold=True)
        self.font_small = pygame.font.SysFont("menlo,consolas,monaco", 12)
        self.font_title = pygame.font.SysFont("helvetica,arial", 22, bold=True)
        self.overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self.recorder = OpRecorder()
        self.uploader = OverlayUploader()
        self.tex = None
        self.native_top_bar = False  # LiveSession owns the native presentation boundary.
        self.native_panels = False  # Activated only after native transport initialization.
        self._vector_capture = None
        self.minimized = {'left': False, 'right': False, 'mission': False}
        self.buttons: list[dict] = []   # {"rect": Rect, "kind": str, "payload": dict}
        self.minimap_rect = None        # set each frame; input uses it
        self.blocked_rects: list = []   # opaque HUD geometry for ground picking
        self.selected_abilities: list = []
        # scrollable panels: kind -> scroll offset in rows
        self.planet_page = 'surface'
        self.scroll: dict = {"ships": 0, "techs": 0, "stations": 0}
        self._cur_panel = None          # set by _scrollable for row callbacks
        self._cur_player = None
        # placement mode: payload dict for build_station awaiting a click
        self.placement: dict | None = None
        self.jump_prompt: bool = False
        self.ability_prompt: str = ""
        self.fleet_panel: bool = False
        self.fleet_formation: str = "line"
        self.fleet_commander: str | None = None
        # sim floating texts projected to screen (set per-frame by main loop)
        self.floating_texts: list = []
        self.drag_box = None            # (start, cur) screen corners while dragging
        # per-frame scrollable regions: list of (rect, key) for wheel routing
        self.scroll_rects: list = []
        self.scroll_panels: dict = {}
        # mission state snapshot (set by main loop when a campaign is active)
        self.mission_progress: list | None = None   # progress_text() rows
        self.mission_name: str | None = None
        self.mission_done: bool = False
        self.mission_failed: bool = False

    def close(self) -> None:
        """Release the overlay texture before the current GL context is lost."""
        uploader = getattr(self, "uploader", None)
        if uploader is not None:
            uploader.release()
            self.tex = uploader.tex
            return
        # A HUD built without __init__ (tests, or a view reused across contexts) still owns a
        # texture id; releasing it must stay idempotent.
        if self.tex is not None:
            from OpenGL import GL
            GL.glDeleteTextures([self.tex])
            self.tex = None

    def _draw_collapsible(self, key, title, draw):
        if self.native_panels and key in ('left', 'right') and _p.native_sink is None:
            from render_bridge.vector_hud import Sink
            source = 10 if key == 'left' else self.width - 330
            target = 10 if key == 'left' else self.width - 250
            sink = Sink(self._native_capture(), (source, 44, 320, self.height - 44),
                        source_x=source, target_x=target, scale=.75)
            start, blocked, scroll = len(self.buttons), len(self.blocked_rects), len(self.scroll_rects)
            previous = _p.native_sink
            _p.native_sink = sink
            try:
                self._draw_collapsible(key, title, draw)
            finally:
                _p.native_sink = previous
                for button in self.buttons[start:]:
                    button['rect'] = pygame.Rect(sink.rect(button['rect']))
                    button['panel'] = key
                self.blocked_rects[blocked:] = [pygame.Rect(sink.rect(r)) for r in self.blocked_rects[blocked:]]
                self.scroll_rects[scroll:] = [(pygame.Rect(sink.rect(r)), k) for r, k in self.scroll_rects[scroll:]]
            return
        self._draw_collapsible_content(key, title, draw)

    def _native_capture(self):
        from render_bridge.vector_hud import Capture
        if self._vector_capture is None or (self._vector_capture.width, self._vector_capture.height) != (self.width, self.height):
            self._vector_capture = Capture(self.width, self.height)
        return self._vector_capture

    def native_vector_model(self):
        """Return an independent complete display snapshot, including inactive clears."""
        return self._native_capture().snapshot(self.native_panels)

    @contextmanager
    def _native_layer(self):
        """Draw this element in C++ when the native side HUD is live.

        The panels, minimap and notifications already render as vector ops with the bundled
        Noto Sans atlas. World-anchored HUD text (placement banner and ghost, construction
        ring and percentage, floating sim messages) was still rasterized with the pygame
        Menlo bitmap font, which is what made those elements read as 640x480 next to the
        vector ones. A full-screen identity sink puts them in the same layer, so they share
        the native glyphs, the native line weights and the display resolution.
        """
        if not self.native_panels or _p.native_sink is not None:
            yield False
            return
        from render_bridge.vector_hud import Sink
        previous = _p.native_sink
        _p.native_sink = Sink(self._native_capture(), (0, 0, self.width, self.height))
        try:
            yield True
        finally:
            _p.native_sink = previous

    def _native_text_size(self, font) -> float:
        """The native em size that matches one of the HUD's pygame fonts."""
        return (12 if font is self.font_small else 19 if font is self.font_big
                else 22 if font is self.font_title else 15) * NATIVE_TEXT_EM_SCALE

    def _screen_text(self, rect, text, color, font, scale: float = 1.0) -> None:
        """Text centred in `rect`, in the native layer when it is open.

        `rect` is measured with pygame (a font measurement, not a rasterization) so the
        background plate around the text keeps the size it had before the move to C++.
        `scale` shrinks both paths alike, so the world labels keep the size they had on
        the overlay now that they are drawn with the larger native em.
        """
        r = pygame.Rect(rect)
        if _p.native_sink is not None:
            _p.native_sink.text(self.overlay, r.x, r.y, str(text), color,
                                self._native_text_size(font) * scale, r.width, r.height,
                                fit='center')
            return
        surf = font.render(str(text), True, color)
        if scale != 1.0:
            surf = pygame.transform.smoothscale(surf, (max(1, r.width), max(1, r.height)))
        _p.blit_text(self.overlay, surf, surf.get_rect(center=r.center), str(text), color,
                     (id(font), scale))

    def _text_box(self, text, font, scale: float = 1.0) -> pygame.Rect:
        """The box a rasterized label would occupy, so layout is identical in both layers."""
        w, h = font.size(str(text))
        return pygame.Rect(0, 0, max(1, int(round(w * scale))), max(1, int(round(h * scale))))

    def _draw_collapsible_content(self, key, title, draw):
        """Separate control rail; minimized panels occupy only their restore tab."""
        w = min(380, self.width - 680) if key == 'mission' else 320
        x = ((self.width - w) // 2 if key == 'mission'
             else (10 if key == 'left' else self.width - 330))
        rail = pygame.Rect(x, 44, w, 28)
        if self.minimized[key]:
            rail.width = self.font_small.size(title + '  +')[0] + 24
            if key == 'right': rail.right = self.width - 10
            if key == 'mission': rail.centerx = self.width // 2
            self.blocked_rects.append(rail)
            self._fleet_button(rail, title + '  +', 'hud_panel',
                               {'panel': key, 'minimized': False})
            return
        start = len(self.buttons)
        rect_start = len(self.blocked_rects)
        scroll_start = len(self.scroll_rects)
        draw()
        for _, scroll_key in self.scroll_rects[scroll_start:]:
            self.scroll_panels[scroll_key] = key
        if len(self.blocked_rects) > rect_start:
            self.blocked_rects[rect_start] = self.blocked_rects[rect_start].union(rail)
        else:
            self.blocked_rects.append(rail)
        _p.rect(self.overlay, HEADER_BG, rail, border_radius=5)
        self._label(x + 12, rail.y + 6, title, TXT_DIM, self.font_small)
        self._fleet_button(pygame.Rect(rail.right - 94, rail.y + 3, 88, 22),
                           'Minimize', 'hud_panel', {'panel': key, 'minimized': True})
        for button in self.buttons[start:]:
            button['panel'] = key

    def _left_panel(self, selection, local_player):
        self._draw_collapsible('left', 'SELECTION',
                              lambda: self._left_panel_content(selection, local_player))

    def _right_panel(self, selection, local_player):
        self._draw_collapsible('right', 'ACTIONS / BUILD',
                              lambda: self._right_panel_content(selection, local_player))

    def _mission_panel(self, local_player):
        if self.mission_progress:
            self._draw_collapsible('mission', 'MISSION TASKS',
                                  lambda: self._mission_panel_content(local_player))

    def _mission_panel_content(self, local_player: int) -> None:
        """Objectives card (top-center) while a campaign mission runs."""
        if not self.mission_progress:
            return
        ov = self.overlay
        rows = self.mission_progress
        # Reserve the same side columns as the inspectors/action controls.
        w = min(380, self.width - 680)
        x = (self.width - w) // 2
        y = 74
        state_col = (120, 200, 140) if self.mission_done else \
            ((220, 120, 110) if self.mission_failed else (150, 175, 220))
        title = self.mission_name or "MISSION"
        # Measure every line before painting so wrapped rows grow the card.
        blocks = [(title, self.font_big, state_col)]
        for row in rows:
            col = (140, 220, 150) if row.startswith("[x]") else (200, 214, 240)
            blocks.append((row, self.font_small, col))
        if self.mission_done or self.mission_failed:
            tag = "MISSION COMPLETE — press ESC" if self.mission_done \
                else "MISSION FAILED — press ESC"
            blocks.append((tag, self.font_big, state_col))
        lines = []
        yy = y + 8
        for text, font, col in blocks:
            line = ''
            wrapped = []
            for word in text.split():
                candidate = (line + ' ' + word).strip()
                if line and font.size(candidate)[0] > w - 28:
                    wrapped.append(line)
                    line = word
                else:
                    line = candidate
                # A mod objective/title may have no spaces. Split by measured
                # glyph width, not character count, and retain every character.
                while font.size(line)[0] > w - 28:
                    cut = 1
                    while cut < len(line) and font.size(line[:cut + 1])[0] <= w - 28:
                        cut += 1
                    wrapped.append(line[:cut])
                    line = line[cut:]
            if line:
                wrapped.append(line)
            for line in wrapped:
                surf = font.render(line, True, col)
                lines.append((surf, yy))
                yy += max(font.get_linesize(), surf.get_height()) + 2
            yy += 6
        h = yy - y + 2
        self.blocked_rects.append(pygame.Rect(x, y, w, h))
        _p.rect(ov, PANEL_BG, (x, y, w, h), border_radius=8)
        _p.rect(ov, PANEL_EDGE, (x, y, w, h), 1, border_radius=8)
        for surf, yy in lines:
            _p.blit(ov, surf, (x + 14, yy))

    # ------------------------------------------------------------------ frame
    def render(self, selection: set, hover_id: int | None,
               local_player: int, paused: bool, flash_msg: str = "",
               flash_left: float = 0.0, fps: float = 0.0) -> None:
        """Paint the overlay and upload what changed to the GPU (the legacy window's path)."""
        self.compose(selection, hover_id, local_player, paused, flash_msg, flash_left, fps)
        self._upload()

    def compose(self, selection: set, hover_id: int | None,
                local_player: int, paused: bool, flash_msg: str = "",
                flash_left: float = 0.0, fps: float = 0.0) -> None:
        """Paint the overlay into `self.overlay` and record it. No GL at all.

        This is the seam the bridge uses: the recorder then knows which rects changed, and
        `OverlayUploader` (or `render_bridge/overlay.py` for the C++ viewer) sends those.
        """
        from game.systems.visibility import presentation_sensor_batch
        with presentation_sensor_batch(self.state):
            self._render_read_only(selection, hover_id, local_player, paused,
                                   flash_msg, flash_left, fps)

    def _render_read_only(self, selection: set, hover_id: int | None,
                          local_player: int, paused: bool, flash_msg: str = "",
                          flash_left: float = 0.0, fps: float = 0.0) -> None:
        self.local_player = local_player
        selection = {eid for eid in selection if self.state.can_see(local_player, eid)}
        ov = self.overlay
        _p.recorder = self.recorder
        self._vector_capture = None
        self.recorder.begin(ov)
        _p.fill(ov, (0, 0, 0, 0))
        self.scroll_rects = []          # rebuilt each frame
        self.buttons = []
        self.blocked_rects = []
        self._top_bar(local_player, paused)
        self._left_panel(selection, local_player)
        self._right_panel(selection, local_player)
        self._event_log(local_player)
        self._minimap(selection, local_player)
        self._mission_panel(local_player)
        self._draw_floating_texts()
        self._draw_drag_box()
        self._placement_banner()
        self._construction_progress()
        if self.jump_prompt or self.ability_prompt:
            text = self.ability_prompt or "JUMP: click destination on ground or minimap | Esc / right-click cancel"
            prompt = self.font.render(text, True, WARN)
            rect = prompt.get_rect(center=(self.width // 2, self.height - 96))
            self.blocked_rects.append(rect.inflate(20, 12))
            _p.rect(ov, PANEL_BG, rect.inflate(20, 12), border_radius=6)
            _p.blit(ov, prompt, rect)
        self._flash_message(flash_msg, flash_left)
        if fps > 0.0 and not self.native_top_bar:
            self._label(self.width - 90, 40, f"{fps:0.0f} FPS", TXT_DIM,
                        self.font_small)
        self.recorder.finish()

    def _flash_message(self, flash_msg: str, flash_left: float) -> None:
        """Caller-owned text/lifetime, captured before rasterization in native mode."""
        if not flash_msg or not flash_left > 0.0:
            return
        ov = self.overlay
        center = (self.width // 2, self.height - 60)
        if not self.native_panels:
            surf = self.font_big.render(flash_msg, True, WARN)
            r = surf.get_rect(center=center)
            bg = r.inflate(24, 12)
            self.blocked_rects.append(bg)
            _p.rect(ov, PANEL_BG, bg, border_radius=6)
            _p.rect(ov, PANEL_EDGE, bg, 1, border_radius=6)
            _p.blit(ov, surf, r)
            return
        from render_bridge.vector_hud import Sink
        # Match the old measured surface/card, not a rasterized intermediate.
        # Preserve legacy overflow geometry; the existing surface clip bounds it.
        width = self.font_big.size(flash_msg)[0]
        r = pygame.Rect(0, 0, width, self.font_big.get_height())
        r.center = center
        bg = r.inflate(24, 12)
        sink = Sink(self._native_capture(), bg, source_x=center[0], target_x=center[0],
                    source_y=center[1], target_y=center[1], scale=.75)
        previous = _p.native_sink
        _p.native_sink = sink
        try:
            self.blocked_rects.append(pygame.Rect(sink.rect(bg)))
            _p.rect(ov, PANEL_BG, bg, border_radius=6)
            _p.rect(ov, PANEL_EDGE, bg, 1, border_radius=6)
            # Native font ink is centred by the consumer within the old glyph box.
            sink.text(ov, r.x, r.y, flash_msg, WARN, 19 * NATIVE_TEXT_EM_SCALE,
                      r.width, r.height, fit='center')
        finally:
            _p.native_sink = previous

    # ------------------------------------------------------------------ top bar
    def _top_bar(self, local_player: int, paused: bool) -> None:
        if self.native_top_bar:
            # Keep input occlusion in the unchanged logical HUD coordinates.
            self.blocked_rects.append(pygame.Rect(0, 0, self.width, 34))
        else:
            self._legacy_top_bar(local_player, paused)
        self._game_over_banner(local_player)

    def _legacy_top_bar(self, local_player: int, paused: bool) -> None:
        ov = self.overlay
        st = self.state
        p = st.players.get(local_player)
        rect = pygame.Rect(0, 0, self.width, 34)
        self.blocked_rects.append(rect)
        _p.rect(ov, HEADER_BG, rect)
        _p.line(ov, PANEL_EDGE, (0, 33), (self.width, 33), 1)

        if p is None:
            return
        x = 14
        cap_used = p.command_used(st.entities)
        # Show each resource's income alongside it. EN was a black box in play:
        # the number never moved and nothing said why — the top bar was the only
        # place it appeared, with no rate. The rate is what makes "I have no EN"
        # legible as "I own no gas giant and no energy relay".
        inc = getattr(p, "income_frame", {}) or {}
        cells = (
            ("CR", f"{p.credits:,.0f}", ACCENT, inc.get("credits", 0.0)),
            ("MT", f"{p.materials:,.0f}", (200, 170, 120), inc.get("materials", 0.0)),
            ("EN", f"{p.energy:,.0f}", (150, 220, 240), inc.get("energy", 0.0)),
            ("CRW", f"{p.crew:,.0f}", GOOD, inc.get("crew", 0.0)),
            ("CMD", f"{cap_used}/{p.command_capacity}",
             WARN if cap_used >= p.command_capacity else TXT, None),
        )
        for label, val, col, rate in cells:
            surf = self.font.render(label, True, TXT_DIM)
            _p.blit(ov, surf, (x, 9))
            x += surf.get_width() + 5
            surf = self.font_big.render(val, True, col)
            _p.blit(ov, surf, (x, 7))
            x += surf.get_width() + 4
            if rate is not None:
                # a genuinely zero rate is the interesting case — say so in the
                # warning colour instead of hiding it
                if abs(rate) < 1e-9:
                    rtext, rcol = "0/s", BAD
                else:
                    rtext, rcol = f"{rate:0.1f}/s", TXT_DIM
                rsurf = self.font.render(rtext, True, rcol)
                _p.blit(ov, rsurf, (x, 14))
                x += rsurf.get_width() + 14
            else:
                x += 18

        t = st.time
        clock = f"{int(t // 60):02d}:{int(t % 60):02d}"
        # Right-aligned, not centred: the resource row now carries an income
        # rate per resource and reaches ~800px in the late game, which ran
        # straight through a centred clock. PAUSED sits at width-200 and still
        # clears this.
        surf = self.font_big.render(clock, True, TXT)
        _p.blit(ov, surf, (self.width - surf.get_width() - 14, 7))

        if paused:
            surf = self.font_big.render(i18n.t("PAUSED"), True, WARN)
            _p.blit(ov, surf, (self.width - 200, 7))

    def _game_over_banner(self, local_player: int) -> None:
        # The centred outcome banner is not part of this top-strip migration.
        st, ov = self.state, self.overlay
        if st.game_over:
            w = st.winner
            won = w in st.allied_player_ids(local_player)
            col = TXT_DIM if w is None else (GOOD if won else BAD)
            name = st.players[w].name if w in st.players else f"team {w}"
            title = i18n.t("DRAW") if w is None else i18n.t(
                '{outcome} — {name}',
                outcome=i18n.t('VICTORY' if won else 'DEFEAT'), name=name)
            surf = self.font_title.render(title, True, col)
            rect = surf.get_rect(center=(self.width // 2, self.height // 2 - 40))
            bg = rect.inflate(30, 16)
            _p.rect(ov, PANEL_BG, bg, border_radius=6)
            _p.rect(ov, col, bg, 2, border_radius=6)
            _p.blit(ov, surf, rect)
        if st.game_over:
            surf = self.font.render(i18n.t("press ESC to exit"), True, TXT_DIM)
            _p.blit(ov, surf, (self.width // 2 - surf.get_width() // 2,
                           self.height // 2 + 4))

    # ------------------------------------------------------------------ trade
    def _trade_line(self, e) -> str:
        """One-line trade status for a convoy or a market (station or hub)."""
        st = self.state
        if e.data_id == "trade_convoy":
            dest = st.known_entity(getattr(self, "local_player", 0), e.convoy_dest if e.convoy_dest is not None else -1)
            where = dest.owner if dest is not None else None
            who = st.players[where].name if where in st.players else "?"
            tgt = f"→ {who}" if dest is not None else "→ no market"
            return f"CARGO {e.cargo_credits:0.0f}cr  {tgt}"
        # market (trade station / surface trade hub): income + outbound convoys
        rate = self.ds.stations.get(e.data_id)
        inc = 0.0
        if rate is not None and isinstance(rate.income, dict):
            inc = float(rate.income.get("credits", 0.0))
        out = sum(1 for c in st.entities.values()
                  if c.alive and c.data_id == "trade_convoy" and c.owner == e.owner
                  and st.can_see(getattr(self, "local_player", 0), c.id))
        # Same source of truth as the spawn gate: a second market must be a real
        # operational market the player can currently see.
        from game.systems.trading import TradingSystem
        markets = sum(1 for s in TradingSystem.markets(st)
                      if st.can_see(getattr(self, "local_player", 0), s.id))
        if markets < 2:
            return f"INCOME {inc:0.1f}cr/s · NEEDS A SECOND MARKET"
        return f"INCOME {inc:0.1f}cr/s · {out} CONVOY{'S' if out != 1 else ''} OUT"

    # ------------------------------------------------------------------ research
    def _station_research(self, station_id: int, owner: int):
        """In-progress research assigned to ONE station, or None.

        Returns (tech_data, time_left, total). Players research per-player
        (Player.researching), but each job is pinned to the station that
        started it — so a station panel must filter by station_id, not just
        by owner, or two research stations would both claim the same job.
        """
        p = self.state.players.get(owner)
        if p is None:
            return None
        for tid, info in getattr(p, "researching", {}).items():
            if int(info.get("station_id", -1)) != int(station_id):
                continue
            td = self.ds.techs.get(tid)
            if td is None:
                continue
            total = max(0.1, float(info.get("total", td.research_time)))
            left = max(0.0, float(info.get("time_left", total)))
            return td, left, total
        return None

    # ------------------------------------------------------------------ left panel
    def _left_panel_content(self, selection: set, local_player: int) -> None:
        ov = self.overlay
        st = self.state
        ents = [st.known_entity(local_player, eid) for eid in sorted(selection)]
        ents = [e for e in ents if e is not None and e.alive
                and st.can_see(local_player, e.id)]
        if len(ents) > 1:
            self._selection_panel(ents, local_player)
            return
        # Idle help is a card, not a full-height inspector hiding the world.
        recovery_extra = bool(ents and (ents[0].order_type in ('repair', 'explore') or ents[0].crew_mission or ents[0].crew < ents[0].max_crew
                              or getattr(self.ds.ships.get(ents[0].data_id), 'crew_capacity', 0)))
        panel = pygame.Rect(10, 72, 320, (min(650, self.height - 145) if recovery_extra
                            else min(540, self.height - 260)) if ents else 84)
        self.blocked_rects.append(panel)
        _p.rect(ov, PANEL_BG, panel, border_radius=8)
        _p.rect(ov, PANEL_EDGE, panel, 1, border_radius=8)
        if not ents:
            self._label(panel.x + 12, panel.y + 10, "NO SELECTION", TXT_DIM)
            self._label(panel.x + 12, panel.y + 34,
                        "left-click / drag to select ships", TXT_DIM)
            self._label(panel.x + 12, panel.y + 52,
                        "1-9 control groups · F fleet menu", TXT_DIM)
            return

        e = ents[0]
        if e.is_planet:
            from game.systems.colonies import eligible_planet
            self._label(panel.x + 12, panel.y + 8, self._fit_text(self.ds.unit_name(e).upper(), 296, self.font_big), TXT, self.font_big)
            owner = st.players.get(e.colonized_by) if eligible_planet(e) else None
            self._label(panel.x + 12, panel.y + 40, self._fit_text('COLONY OWNER: ' + (owner.name if owner else 'Uncolonized'), 296), TXT)
            self._label(panel.x + 12, panel.y + 62, e.data_id.upper(), TXT_DIM)
            rates = dict(self.ds.rules.get('economy', {}).get('planet_income', {}).get(e.data_id, {})) if eligible_planet(e) else {}
            rates['crew'] = rates.get('crew', 0) + self.ds.rules.get('economy', {}).get('planet_crew_bonus', {}).get(e.data_id, 0)
            y = panel.y + 92
            self._label(panel.x + 12, y, 'BASE COLONY / SECOND', ACCENT)
            for resource in ('credits', 'materials', 'energy', 'crew'):
                y += 20
                self._label(panel.x + 12, y, f"{resource}: {rates.get(resource, 0):g}", TXT_DIM)
            if e.colonized_by == local_player:
                from game.systems.planet_buildings import building_income
                bonus = building_income(st, e)
                y += 26
                self._label(panel.x + 12, y, 'SURFACE BONUS / SECOND', ACCENT)
                for resource in ('credits', 'materials', 'energy', 'crew'):
                    y += 20
                    self._label(panel.x + 12, y, f"{resource}: +{bonus.get(resource, 0):g}", TXT_DIM)
            y += 24
            y = self._wrapped_labels(panel.x + 12, y, 'Gas and terrain cannot be colonized.' if not eligible_planet(e) else 'Right-click with colony ship to settle/capture.', 296)
            if e.colonized_by == local_player and e.build_queue:
                item = e.build_queue[0]
                self._label(panel.x + 12, y + 24, self._fit_text('BUILDING ' + item['item'].replace('_', ' ').upper(), 296, self.font_small), TXT, self.font_small)
                self._bar(panel.x + 12, y + 44, 296, 10, 1 - item['time_left'] / max(.1, item['total']), ACCENT)
            return
        sd = self.ds.ships.get(e.data_id)
        std = self.ds.stations.get(e.data_id) if sd is None else None
        name = self.ds.unit_name(e)
        if e.name_override:
            name = e.name_override
        cat = sd.category if sd else (std.id.replace("_", " ") if std else e.kind)
        self._label(panel.x + 12, panel.y + 8, self._fit_text(name.upper(), 296, self.font_big), TXT, self.font_big)
        fac = st.players[e.owner].name if e.owner in st.players else "Neutral"
        self._label(panel.x + 12, panel.y + 34, self._fit_text(f"{cat.upper()} · {fac}", 296), TXT_DIM)
        rank_data = ship_rank_panel_data(e, self.ds)
        y = panel.y + 52
        if rank_data is not None:
            self._label(panel.x + 12, y, rank_data["rank_text"], WARN)
            y += 20
            for key in ("xp_text", "attack_text", "defense_text"):
                self._label(panel.x + 12, y, rank_data[key], TXT_DIM,
                            self.font_small)
                y += 16
        else:
            self._label(panel.x + 12, y, f"LEVEL {e.level}", TXT_DIM)
            y += 18
        # Flow the cursor: rank/XP rows must not run underneath hull bars.
        if e.data_id in ("trade_convoy", "trade_station", "planet_trade_hub"):
            self._label(panel.x + 12, y, self._trade_line(e), TRADE,
                        self.font_small)
            y += 18
        elif e.is_station:
            # research stations: the panel showed nothing while a tech was
            # being researched (reported: "we need to see the progress of
            # research ... order: idle" - ORDER went blank because the
            # station's own order_type is idle the whole time). Show the live
            # job: which tech, a progress bar and the seconds remaining.
            job = self._station_research(e.id, e.owner)
            if job is None:
                y += 8
            else:
                td, left, total = job
                self._label(panel.x + 12, y, f"RESEARCHING {td.display_name.upper()}",
                            RESEARCH, self.font_small)
                y += 16
                self._bar(panel.x + 12, y, 296, 10, 1.0 - left / total, RESEARCH)
                pct = int(round((1.0 - left / total) * 100))
                self._label(panel.x + 12, y + 12,
                            f"{pct}% · {left:0.0f}s remaining", TXT_DIM,
                            self.font_small)
                y += 30
        else:
            y += 8
        # hull
        frac = max(0.0, e.hull / max(1.0, e.max_hull))
        self._bar(panel.x + 12, y, 296, 14, frac, BAR_HULL, "HULL")
        y += 22
        # shields: 4 quadrant bars
        quad_h = max(1.0, e.max_shield_quad)
        for i, q in enumerate(QUADRANTS):
            cur = e.shields.get(q, 0.0)
            self._bar(panel.x + 12 + (i % 2) * 150, y + (i // 2) * 18,
                      142, 11, cur / quad_h, BAR_SHIELD, q[:2].upper())
        y += 48
        # systems
        if not e.is_planet:
            status = ' · ABANDONED' if e.crew <= 0 else ''
            self._label(panel.x + 12, y, f'CREW {e.crew}/{e.max_crew}{status}',
                        BAD if e.crew <= 0 else TXT_DIM, self.font_small)
            y += 18
        recovery = st._crew_recovery_system
        if recovery and not e.is_planet:
            from game.systems.stats import staffing_fraction
            self._label(panel.x + 12, y, f'STAFF {staffing_fraction(e):.0%} · operating complement', TXT_DIM, self.font_small)
            y += 16
            capacity = recovery.capacity(e)
            if capacity or e.crew_cargo:
                self._label(panel.x + 12, y, f'CARGO {e.crew_cargo}/{capacity} · passengers', GOOD, self.font_small)
                y += 16
            if e.owner == local_player and (e.crew_mission or e.crew < e.max_crew):
                text, reason = recovery.status(e)
                self._label(panel.x + 12, y, self._fit_text(text, 296, self.font_small), WARN, self.font_small)
                y += 16
                self._label(panel.x + 12, y, self._fit_text(reason, 296, self.font_small), TXT_DIM, self.font_small)
                y += 16
        parties = [c for c in st.entities.values() if c.alive and c.boarding
                   and st.can_see(local_player, c.id)
                   and (c.id == e.id or c.boarding['source'] == e.id or c.boarding['target'] == e.id)]
        if parties:
            party = min(parties, key=lambda c: c.id)
            info = party.boarding
            self._label(panel.x + 12, y,
                        f"BOARDING {info['phase'].upper()} {min(1, info['progress']):.0%} · {party.crew} crew",
                        WARN, self.font_small)
            y += 16
        for name_s, sys_st in e.systems.items():
            sf = sys_st.hp / max(1.0, sys_st.max_hp)
            col = GOOD if sf > 0.7 else (WARN if sf > 0.35 else BAD)
            self._bar(panel.x + 12, y, 240, 8, sf, col)
            self._label(panel.x + 256, y - 2, name_s[:5].upper(), TXT_DIM,
                        self.font_small)
            y += 13
        y += 6
        # energy
        ef = e.energy / max(1.0, e.max_energy)
        self._bar(panel.x + 12, y, 296, 8, ef, (150, 220, 240))
        y += 18
        from game.systems.stats import effective_sensor_range
        self._label(panel.x + 12, y, f"SENSORS {effective_sensor_range(st, e):,.0f}u", TXT_DIM)
        y += 20
        # orders
        order = e.order_type.replace("_", " ").upper() or "IDLE"
        if e.order_target_id is not None:
            tgt = st.known_entity(local_player, e.order_target_id)
            if tgt:
                order += f" → {self.ds.unit_name(tgt)}"
        # a station whose own order is idle can still be busy researching; the
        # panel read "ORDER: " (blank) while a tech was clearly running, which
        # is what made the research state look missing entirely.
        if e.is_station and self._station_research(e.id, e.owner) is not None:
            order = "RESEARCHING"
        self._label(panel.x + 12, y, self._fit_text(f"ORDER: {order}", 296),
                    RESEARCH if order == "RESEARCHING" else TXT_DIM)
        y += 20
        if e.order_type == 'repair' and e.owner == local_player:
            from game.systems.repairs import repair_rules, missing_hp
            from game.systems.stats import effective_repair_rate
            target = st.known_entity(local_player, e.order_target_id)
            cfg = repair_rules()
            rate = cfg['hp_per_second'] * effective_repair_rate(st, e.owner, e)
            if target is not None and target.owner == local_player:
                missing = missing_hp(target)
                total = target.max_hull + sum(s.max_hp for s in target.systems.values())
                self._label(panel.x + 12, y, f'{missing:,.1f} HP missing · hull + systems', WARN, self.font_small)
                y += 16
                self._bar(panel.x + 12, y, 296, 8, 1 - missing / max(1, total), GOOD)
                y += 14
                p = st.players.get(local_player)
                status = 'APPROACHING' if e.order_target_pos is not None else ('WAITING FOR CR / MT' if p and (p.credits <= 0 or p.materials <= 0) else 'REPAIRING')
                self._label(panel.x + 12, y, status + ' · no crew restored', TXT_DIM, self.font_small)
                y += 16
            y = self._wrapped_labels(panel.x + 12, y,
                f"{rate:g} HP/s · {cfg['credits_per_hp']:g} CR/HP · {cfg['materials_per_hp']:g} MT/HP", 296)
        elif e.order_type == 'explore' and e.owner == local_player:
            target = e.order_target_pos
            text = f'SURVEY → {target.x:,.0f}, {target.z:,.0f}' if target else 'SURVEY · waiting for a safe route'
            self._label(panel.x + 12, y, text, WARN, self.font_small)
            y += 16
            y = self._wrapped_labels(panel.x + 12, y, 'Auto patrol · avoid detected enemies · no combat', 296)
        # squadron count
        if e.is_squadron:
            self._label(panel.x + 12, y,
                        f"FIGHTERS {e.fighter_count}/{e.max_fighters}",
                        GOOD if e.fighter_count < e.max_fighters else TXT)
            y += 20
        # build queue
        if e.build_queue:
            item = e.build_queue[0]
            it_name = item.get("item", "")
            done = 1.0 - item.get("time_left", 0) / max(0.1, item.get("total", 1))
            if item.get('kind') == 'colonize':
                phase = 'CAPTURING' if item.get('target_owner') is not None else 'COLONIZING'
                it_name = f"{phase} {item.get('status', '').upper()} · {item['time_left']:.1f}s"
            else:
                it_name = 'BUILDING ' + it_name.upper()
            self._label(panel.x + 12, y, self._fit_text(it_name, 296, self.font_small), TXT,
                        self.font_small)
            y += 18
            self._bar(panel.x + 12, y, 296, 10, done, ACCENT)
            y += 18
        # jump charge / transit
        if e.jump_travelling:
            self._label(panel.x + 12, y,
                        f"HYPERSPACE TRANSIT {e.jump_charge:0.0f}s", WARN)
            y += 20
        elif e.jump_target is not None:
            self._label(panel.x + 12, y,
                        f"HYPERSPACE CHARGE {e.jump_charge:0.0f}", WARN)
            y += 20
        # Own capabilities only, paged inside the inspector.
        self._ability_rows(panel, y, ents, local_player)

    def _selection_panel(self, ents, local_player):
        panel = pygame.Rect(10, 72, 320, min(430, self.height - 270))
        self.blocked_rects.append(panel)
        _p.rect(self.overlay, PANEL_BG, panel, border_radius=8)
        _p.rect(self.overlay, PANEL_EDGE, panel, 1, border_radius=8)
        self._label(panel.x + 12, panel.y + 8,
                    f"SELECTED UNITS · {len(ents)}", TXT, self.font_big)
        y = panel.y + 58
        groups = selected_ability_data(self.state, [e.id for e in ents], local_player, self.ds)
        reserve = min(160, len(groups) * 40 + 24) if groups else 0
        rows = max(1, (panel.bottom - y - reserve - 10) // 38)
        off = max(0, min(self.scroll.get('selection', 0), max(0, len(ents) - rows)))
        self.scroll['selection'] = off
        self.visible_selection_ids = [e.id for e in ents[off:off + rows]]
        self.scroll_rects.append((pygame.Rect(panel.x, panel.y + 38, panel.width, rows * 38 + 20), 'selection'))
        self._label(panel.x + 12, panel.y + 36,
                    f"Units {off + 1}-{min(off + rows, len(ents))}/{len(ents)} · wheel", TXT_DIM, self.font_small)
        self._page_controls(panel, panel.y + 34, "selection", rows, off, len(ents))
        for e in ents[off:off + rows]:
            name = e.name_override or self.ds.unit_name(e)
            self._label(panel.x + 12, y, self._fleet_text(name, 296), TXT,
                        self.font_small)
            rank = ship_rank_panel_data(e, self.ds)
            status = rank["rank_text"] if rank else e.kind.upper()
            if e.is_squadron:
                status += f" · {e.fighter_count}/{e.max_fighters} fighters"
            status += f" · HULL {e.hull / max(1, e.max_hull):.0%}"
            self._label(panel.x + 12, y + 16, status, TXT_DIM, self.font_small)
            y += 38
        self._ability_rows(panel, y, ents, local_player)

    def _page_controls(self, panel, y, key, capacity, off, count):
        if count <= capacity:
            return
        for x, text, delta, enabled in ((panel.right - 60, "▲", -capacity, off > 0),
                                      (panel.right - 34, "▼", capacity, off + capacity < count)):
            rect = pygame.Rect(x, y, 22, 18)
            _p.rect(self.overlay, BAR_BG, rect, border_radius=3)
            self._label(x + 5, y + 1, text, ACCENT if enabled else TXT_DIM, self.font_small)
            if enabled:
                self.buttons.append({"rect": rect, "kind": "hud_scroll",
                    "payload": {"key": key, "delta": delta}})

    def _ability_rows(self, panel, y, ents, local_player):
        groups = selected_ability_data(self.state, [e.id for e in ents], local_player, self.ds)
        y += 20
        capacity = max(0, (panel.bottom - y - 8) // 40)
        off = max(0, min(self.scroll.get('abilities', 0), max(0, len(groups) - capacity)))
        self.scroll['abilities'] = off
        if groups and capacity:
            self.scroll_rects.append((pygame.Rect(panel.x, y - 20, panel.width, panel.bottom - y + 20), 'abilities'))
            self._label(panel.x + 12, y - 18,
                        f"Abilities {off + 1}-{min(off + capacity, len(groups))}/{len(groups)}", TXT_DIM, self.font_small)
            self._page_controls(panel, y - 20, "abilities", capacity, off, len(groups))
        for row in groups[off:off + capacity]:
            ad = self.ds.abilities[row['ability_id']]
            rect = pygame.Rect(panel.x + 12, y, 296, 36)
            _p.rect(self.overlay, BAR_BG, rect, border_radius=4)
            self._label(rect.x + 8, y + 2, self._fleet_text(ad.display_name, 280), TXT,
                        self.font_small)
            cooldowns = row['cooldowns']
            status = f"{len(row['unit_ids'])}/{row['count']} ready"
            if cooldowns:
                status += f" · {len(cooldowns)} CD {min(cooldowns):.0f}-{max(cooldowns):.0f}s"
            if row['low_energy']:
                status += f" · {row['low_energy']} low EN"
            self._label(rect.x + 8, y + 18, status, TXT_DIM, self.font_small)
            if row['unit_ids']:
                self.buttons.append({'rect': rect, 'kind': 'ability', 'payload': {
                    'ability_id': row['ability_id'], 'unit_ids': row['unit_ids']}})
            y += 40

    def _planet_menu(self, planet, local_player):
        from game.systems.colonies import eligible_planet, satellite_lock_remaining
        from game.systems.planet_buildings import BUILDING_TYPES, building_rules, building_slots
        panel = pygame.Rect(self.width - 330, 72, 320, self.height - 308)
        self.blocked_rects.append(panel)
        _p.rect(self.overlay, PANEL_BG, panel, border_radius=8)
        _p.rect(self.overlay, PANEL_EDGE, panel, 1, border_radius=8)
        x, y = panel.x + 12, panel.y + 10
        self._label(x, y, 'COLONY HARDWARE', ACCENT, self.font_big)
        y += 30
        if not eligible_planet(planet) or planet.colonized_by != local_player:
            self._label(x, y, 'Requires your non-gas colony', TXT_DIM)
            return
        cap = building_rules()['slot_cap']
        slots = building_slots(self.state, planet)
        orbit_cap = int(self.ds.rules.get('colonies', {}).get('satellite_cap', 6))
        orbit_slots = self.state._construction_system.satellite_slots(planet)
        self._label(x, y, f'SURFACE {len(slots)}/{cap} · ORBIT {len(orbit_slots)}/{orbit_cap}', TXT_DIM)
        y += 22
        for i, (page, text) in enumerate((('surface', 'Surface buildings'), ('orbit', 'Orbital satellites'))):
            self._fleet_button(pygame.Rect(x + i * 152, y, 144, 26), text,
                               'hud_planet_page', {'page': page}, self.planet_page == page)
        y += 34
        surface = self.planet_page == 'surface'
        occupied = slots if surface else orbit_slots
        self._label(x, y, 'Paid queue reserves · wreck locks site 3 min' if not surface
                    else 'Paid queue reserves slots · first free', TXT_DIM, self.font_small)
        y += 20
        for slot in range(cap if surface else orbit_cap):
            status = 'FREE'
            entity = next((e for e in self.state.entities.values() if e.alive and e.planet_id == planet.id
                           and (e.planet_building_slot if surface else e.satellite_slot) == slot), None)
            queued = next((q for q in planet.build_queue if q.get('kind') == ('planet_building' if surface else 'satellite')
                           and q.get('slot') == slot), None)
            remaining = 0.0 if surface else satellite_lock_remaining(self.state, planet, slot)
            if entity is not None: status = self.ds.unit_name(entity)
            elif queued is not None: status = f"PAID {queued['time_left']:.0f}s ✕"
            elif remaining > 0.0: status = f"REBUILD {remaining / 60:.1f}m"
            elif slot in occupied: status = 'RESERVED'
            colour = GOOD
            if remaining > 0.0: colour = ACCENT
            elif slot in occupied: colour = WARN
            cell_x, cell_y = x + (slot % 3) * 100, y + (slot // 3) * 18
            if queued is not None:
                colour = WARN
            self._label(cell_x, cell_y,
                        self._fit_text(f'{slot + 1}: {status}', 96, self.font_small),
                        colour, self.font_small)
            if queued is not None:
                self.buttons.append({'rect': pygame.Rect(cell_x, cell_y, 96, 16),
                                     'kind': 'cancel_build',
                                     'payload': {'target_id': planet.id,
                                                 'page': 'surface' if surface else 'orbit',
                                                 'index': planet.build_queue.index(queued)}})
        y += 42
        if any(q.get('kind') in ('planet_building', 'satellite') for q in planet.build_queue):
            self._label(x, y, '✕ cancels paid work · 50% refunded', ACCENT, self.font_small)
            y += 16
        else:
            y += 4
        descriptions = {
            'planet_extractor': 'Adds colony resource output.',
            'planet_trade_hub': 'Adds credit income; basic colony income remains.',
            'planet_shield_generator': 'Shields surface buildings only; not ships or satellites.',
            'planet_pulsar_cannon': 'Long-range anti-ship pulsar; not anti-fighter defense.',
            'defense_satellite': 'Intercepts missiles and enemy fighters.',
            'attack_satellite': 'Engages enemy ships; clear before capture.',
        }
        items = BUILDING_TYPES if surface else ('defense_satellite', 'attack_satellite')
        key = 'planet_buildings' if surface else 'planet_satellites'
        capacity = max(1, (panel.bottom - y - 34) // 104)
        off = max(0, min(self.scroll.get(key, 0), max(0, len(items) - capacity)))
        self.scroll[key] = off
        self._label(x, y, f'Build {off + 1}-{min(off + capacity, len(items))}/{len(items)} · wheel', TXT_DIM, self.font_small)
        self._page_controls(panel, y - 2, key, capacity, off, len(items))
        y += 24
        self.scroll_rects.append((pygame.Rect(panel.x + 4, y, panel.width - 8, panel.bottom - y - 4), key))
        for role in items[off:off + capacity]:
            data = self.ds.stations[role]
            payload = {'planet_id': planet.id, 'station_kind': role}
            next_y = self._build_row(panel, y, data, self.state.players[local_player], payload,
                                     'build_planet_building' if surface else 'build_satellite')
            if len(occupied) >= (cap if surface else orbit_cap):
                self.buttons[:] = [b for b in self.buttons if b.get('payload') != payload]
            self._wrapped_labels(x, next_y, descriptions[role], 296)
            y += 104

    # ------------------------------------------------------------------ right panel
    def _right_panel_content(self, selection: set, local_player: int) -> None:
        if self.fleet_panel:
            self._fleet_panel(selection, local_player)
            return
        ov = self.overlay
        st = self.state
        p = st.players.get(local_player)
        if p is None:
            return
        ents = [st.known_entity(local_player, eid) for eid in sorted(selection)]
        planet = next((e for e in ents if e is not None and e.is_planet), None)
        if planet is not None:
            self._planet_menu(planet, local_player)
            return
        ents = [e for e in ents if e is not None and e.owner == local_player]
        sel = ents[0] if ents else None
        contextual = sel is not None and (sel.is_construction or sel.is_station)
        from game.systems.boarding import boarding_capable
        has_boarders = any(boarding_capable(e) for e in ents)
        recovery = st._crew_recovery_system
        transports = [e for e in ents if recovery and recovery.capacity(e) and e.operational]
        from game.systems.repairs import builder_capable, repair_rules
        from game.systems.exploration import exploration_capable
        builders = [e for e in ents if builder_capable(st, e) and e.jump_charge <= 0 and e.jump_target is None]
        scouts = [e for e in ents if e.operational and exploration_capable(e)]
        boarders = [e for e in ents if boarding_capable(e)]
        support_extra = (90 if builders else 0) + (64 if scouts else 0) + (112 if boarders else 0)
        panel = pygame.Rect(self.width - 330, 72, 320,
                            min(self.height - 270, (430 if contextual else (260 if transports else 124)) + support_extra))
        if sel is not None and sel.is_station:
            # The minimap starts at height - 222; leave a visible gap below actions.
            panel.height = min(panel.height, self.height - 230 - panel.y)
        self.blocked_rects.append(panel)
        _p.rect(ov, PANEL_BG, panel, border_radius=8)
        _p.rect(ov, PANEL_EDGE, panel, 1, border_radius=8)

        y = panel.y + 10
        if scouts:
            self._fleet_button(pygame.Rect(panel.x + 12, y, 296, 26),
                               'Explore map · automatic fighter patrol', 'explore', {'unit_ids': [e.id for e in scouts]})
            y += 30
            y = self._wrapped_labels(panel.x + 12, y, 'Auto patrol: avoid detected enemies · no combat · Backspace to stop.', 296) + 6
        if builders:
            self._fleet_button(pygame.Rect(panel.x + 12, y, 296, 26),
                               'Repair owned hull / systems', 'repair', {'unit_ids': [e.id for e in builders]})
            y += 30
            cfg = repair_rules()
            y = self._wrapped_labels(panel.x + 12, y,
                f"{cfg['hp_per_second']:g} base HP/s · {cfg['credits_per_hp']:g} CR/HP · {cfg['materials_per_hp']:g} MT/HP. Hull + systems; no crew. Backspace to stop.", 296) + 6
        if boarders:
            self._fleet_button(pygame.Rect(panel.x + 12, y, 296, 26),
                               f'B  Board enemy hull · {len(boarders)} capable', 'board', {})
            y += 30
            from game.systems.boarding import boarding_rules
            y = self._wrapped_labels(panel.x + 12, y,
                f"Detected enemy · all shields down · within {boarding_rules()['range']:g}u hull reach. No disabled system required. Capture restores life support to at least 10%; no satellites.", 296) + 6
        # constructor selected -> build stations (scrollable)
        colony = self.ds.ships.get(sel.data_id) if sel is not None else None
        if colony is not None and colony.can_colonize:
            self._label(panel.x + 12, y, 'COLONY SHIP', ACCENT, self.font_big)
            y += 32
            from game.systems.colonies import colony_rules
            control_seconds = colony_rules()['control_seconds']
            for text in ('Right-click a non-gas planet.', 'Neutral: colonize · Enemy: capture',
                         'Destroy ALL defending satellites first.', f'Approach then {control_seconds:g} seconds uninterrupted.',
                         'Ship consumed only on success.', 'No additional resource or crew fee.'):
                y = self._wrapped_labels(panel.x + 12, y, text, 296) + 6
        elif sel is not None and sel.is_construction:
            self._label(panel.x + 12, y, "ORBITAL CONSTRUCTION", ACCENT,
                        self.font_big)
            y += 28
            sd = self.ds.ships.get(sel.data_id)
            items = [self.ds.stations.get(sid)
                     for sid in getattr(sd, "can_build_stations", [])
                     if self.ds.stations.get(sid) is not None]
            y = self._scrollable(panel, y, items, p, "stations",
                                 self._row_build_station, sel)
        elif sel is not None and sel.is_station:
            std = self.ds.stations.get(sel.data_id)
            y = self._station_details(panel, y, sel, p, bool(std and std.builds_ships))
            if std is not None and std.builds_ships:
                self._label(panel.x + 12, y, "SHIP PRODUCTION", ACCENT,
                            self.font_big)
                y += 28
                q = sel.build_queue
                for index, item in enumerate(q[:3]):
                    row = pygame.Rect(panel.x + 12, y - 1, 296, 18)
                    self._label(row.x, row.y + 1,
                                self._fit_text(f"▸ {str(item.get('item', '')).upper()}", 190),
                                TXT_DIM, self.font_small)
                    self._label(row.x + 192, row.y + 1,
                                f"{max(0.0, float(item.get('time_left', 0.0))):.0f}s",
                                TXT_DIM, self.font_small)
                    if item.get('kind') in ('ship', 'station', 'satellite'):
                        button = pygame.Rect(row.right - 62, row.y, 62, 18)
                        _p.rect(self.overlay, BAR_BG, button, border_radius=3)
                        _p.rect(self.overlay, ACCENT, button, 1, border_radius=3)
                        self._label(button.x + 6, button.y + 1, "✕ Cancel", TXT,
                                    self.font_small)
                        self.buttons.append({"rect": button, "kind": "cancel_build",
                                             "payload": {"target_id": sel.id, "index": index}})
                    y += 20
                if q:
                    y += 6
                items = self._shipyard_items(sel, std)
                y = self._scrollable(panel, y, items, p, "ships",
                                     self._row_build_ship, sel)
            if sel.data_id == 'repair_dock':
                self._label(panel.x + 12, y, 'REPAIR DOCK', ACCENT, self.font_big)
                y += 28
                y = self._wrapped_labels(panel.x + 12, y, 'Automatic equipment repair: ships / fighters only; not stations. Does not restore crew.', 296)
            if std is not None and std.research:
                self._label(panel.x + 12, y, "RESEARCH", ACCENT, self.font_big)
                y += 28
                # in-progress first: a running tech must show its progress and
                # must NOT also sit in the available list below (it would look
                # unstarted and re-clickable).
                running = getattr(p, "researching", {}) or {}
                for tid, info in running.items():
                    td = self.ds.techs.get(tid)
                    if td is None or td.faction != p.faction:
                        continue
                    total = max(0.1, float(info.get("total", td.research_time)))
                    left = max(0.0, float(info.get("time_left", total)))
                    self._label(panel.x + 12, y,
                                f"IN PROGRESS · {td.display_name.upper()}",
                                RESEARCH, self.font_small)
                    y += 16
                    self._bar(panel.x + 12, y, 296, 12, 1.0 - left / total,
                              RESEARCH)
                    pct = int(round((1.0 - left / total) * 100))
                    self._label(panel.x + 12, y + 14,
                                f"{pct}% · {left:0.0f}s remaining", TXT_DIM,
                                self.font_small)
                    y += 32
                if running:
                    y += 4
                techs = [td for tid, td in self._techs()
                         if td.faction == p.faction and tid not in running]
                y = self._scrollable(panel, y, techs, p, "techs",
                                     self._row_research, sel)
        else:
            self._label(panel.x + 12, y, "FLEET COMMAND", ACCENT, self.font_big)
            y += 28
            self._label(panel.x + 12, y, "select a constructor or station", TXT_DIM)
            y += 20
            self._label(panel.x + 12, y, "build / research: select a station", TXT_DIM, self.font_small)
            y += 18
            self._label(panel.x + 12, y, "F  fleet formation & commander", TXT_DIM)
            y += 18
            self._label(panel.x + 12, y, "J  hyperspace jump", TXT_DIM)

        if transports and not contextual:
            y += 24
            for label, kind in [('L  Load passengers at friendly base', 'crew_load'),
                                ('R  Deliver crew to owned hull', 'crew_deliver'),
                                ('Cancel crew order · keep passengers', 'crew_cancel')]:
                rect = pygame.Rect(panel.x + 12, y, 296, 26)
                _p.rect(ov, BAR_BG, rect, border_radius=4)
                self._label(rect.x + 8, rect.y + 4, label, TXT, self.font_small)
                self.buttons.append({'rect': rect, 'kind': kind, 'payload': {}})
                y += 30

    def _fleet_panel(self, selection: set, local_player: int) -> None:
        """Fleet intent controls; eligibility is re-read on every drawn frame."""
        panel = pygame.Rect(self.width - 330, 72, 320, 430)
        self.blocked_rects.append(panel)
        _p.rect(self.overlay, PANEL_BG, panel, border_radius=8)
        _p.rect(self.overlay, PANEL_EDGE, panel, 1, border_radius=8)
        ships = [e for eid in sorted(selection)
                 if (e := self.state.entity(eid)) is not None
                 and e.alive and e.owner == local_player and e.is_ship]
        x, y = panel.x + 12, panel.y + 10
        self._label(x, y, "CREATE FLEET", ACCENT, self.font_big)
        y += 28
        self._label(x, y, f"{len(ships)} selected own ships", TXT)
        y += 22
        for ship in ships[:2]:
            name = ship.name_override or self.ds.unit_name(ship)
            self._label(x, y, self._fleet_text(name, 296), TXT_DIM, self.font_small)
            y += 16
        if len(ships) > 2:
            self._label(x, y, f"+ {len(ships) - 2} more ships", TXT_DIM, self.font_small)
            y += 16
        if not ships:
            self._label(x, y, "Select alive ships you own to create a fleet.", WARN,
                        self.font_small)
            y += 16
        y += 8
        for title, kind, field, keys, selected in (
                ("FORMATION", "fleet_formation", "formation",
                 list(self.ds.rules.get("formations", {})), self.fleet_formation),
                ("COMMANDER", "fleet_commander", "commander",
                 [None] + list(self.ds.rules.get("commanders", {})), self.fleet_commander)):
            self._label(x, y, title, TXT_DIM, self.font_small)
            y += 20
            for i, key in enumerate(keys):
                rect = pygame.Rect(x + (i % 2) * 152, y + (i // 2) * 26, 144, 22)
                label = "None" if key is None else str(key).replace("_", " ").title()
                self._fleet_button(rect, label, kind, {field: key}, key == selected)
            y += ((len(keys) + 1) // 2) * 26 + 10
        rect = pygame.Rect(x, panel.bottom - 40, 198, 28)
        if ships:
            self._fleet_button(rect, "Create fleet", "fleet_create", {
                "unit_ids": [e.id for e in ships],
                "formation": self.fleet_formation,
                "commander": self.fleet_commander,
            })
        else:
            _p.rect(self.overlay, BAR_BG, rect, border_radius=4)
            self._label(rect.x + 8, rect.y + 6, "Create fleet (no ships)", TXT_DIM,
                        self.font_small)
        self._fleet_button(pygame.Rect(x + 206, rect.y, 90, 28), "Close",
                           "fleet_close", {})

    def _wrapped_labels(self, x, y, text, width):
        """Flow complete help text within a panel's content width.

        The string is translated *before* it is wrapped: a wrapped fragment ("As built ·
        buy a level to raise hull,") is not a catalogue key, so a per-line lookup would
        fall back to English for exactly the long sentences a player has to read.
        """
        line = ''
        for word in i18n.t(text).split():
            candidate = (line + ' ' + word).strip()
            if line and self.font_small.size(candidate)[0] > width:
                if _p.native_sink is not None:
                    from render_bridge.vector_hud import BoundedText
                    line = BoundedText(line, width)
                self._label(x, y, line, TXT_DIM, self.font_small, translate=False)
                y += self.font_small.get_linesize()
                line = word
            else:
                line = candidate
        if line:
            self._label(x, y, self._fit_text(line, width, self.font_small), TXT_DIM,
                        self.font_small, translate=False)
            y += self.font_small.get_linesize()
        return y

    def _fit_text(self, text, width, font=None):
        if _p.native_sink is not None:
            from render_bridge.vector_hud import BoundedText
            return BoundedText(i18n.t(text), width)
        font = font or self.font
        if font.size(text)[0] <= width:
            return text
        while text and font.size(text + "…")[0] > width:
            text = text[:-1]
        return text + "…"

    def _fleet_text(self, text: str, width: int) -> str:
        """Fit data-driven names without painting over adjacent controls."""
        if _p.native_sink is not None:
            from render_bridge.vector_hud import BoundedText
            return BoundedText(i18n.t(text), width)
        if self.font_small.size(text)[0] <= width:
            return text
        while text and self.font_small.size(text + "…")[0] > width:
            text = text[:-1]
        return text + "…"

    def _fleet_button(self, rect, label, kind, payload, selected=False) -> None:
        _p.rect(self.overlay, (24, 34, 52, 255), rect, border_radius=4)
        _p.rect(self.overlay, ACCENT if selected else PANEL_EDGE,
                         rect, 1, border_radius=4)
        label = ("▸ " if selected else "") + label
        self._label(rect.x + 8, rect.y + (rect.height - self.font_small.get_height()) // 2,
                    self._fleet_text(label, rect.width - 16),
                    ACCENT if selected else TXT, self.font_small)
        self.buttons.append({"rect": rect, "kind": kind, "payload": payload})

    def _row_build_station(self, d, yy, payload) -> None:
        self._build_row(self._cur_panel, yy, d, self._cur_player, payload,
                        "build_station_place")

    def _station_details(self, panel, y, sel, player, production) -> int:
        """Let long collection/refit readouts scroll, never starve the ship list.

        Measure with the real fonts/wrapping (including translated upgrade effects).
        Reserve two ship rows and the current queue before assigning header space.
        Only fully visible controls participate in hit testing.
        """
        def draw(top):
            from game.systems.collection_points import collection_capable
            if collection_capable(sel):
                self._label(panel.x + 12, top, 'COLLECTION POINT', ACCENT, self.font_small)
                top += 18
                self._label(panel.x + 12, top, 'Right-click space to set destination.', TXT_DIM, self.font_small)
                top += 18
                point = sel.collection_point
                status = ('Not set · new units remain nearby' if point is None else
                          f'X {point.x:.0f}  Y {point.y:.0f}  Z {point.z:.0f}')
                self._label(panel.x + 12, top, status, TXT_DIM, self.font_small)
                top += 18
                if point is not None:
                    self._fleet_button(pygame.Rect(panel.x + 12, top, 296, 24),
                                       'Clear collection point', 'collection_clear', {'target_id': sel.id})
                    top += 28
            return self._refit_block(panel, top, sel, player)

        if not production:
            return draw(y)
        old_clip = self.overlay.get_clip()
        start = len(self.buttons)
        self.overlay.set_clip(pygame.Rect(0, 0, 0, 0))
        try:
            bottom = draw(y)
            control_tops = [b['rect'].top - y for b in self.buttons[start:]]
        finally:
            self.overlay.set_clip(old_clip)
            del self.buttons[start:]
        queue_height = min(3, len(sel.build_queue)) * 20 + (6 if sel.build_queue else 0)
        height = min(bottom - y, panel.bottom - y - 28 - queue_height - 108 - 8)
        if height >= bottom - y:
            return draw(y)
        viewport = pygame.Rect(panel.x + 4, y, panel.width - 8, max(28, height))
        key = 'station_details'
        overflow = bottom - y - viewport.height
        # Keep readable text steps, but also stop at every measured control's top.
        # An 18px-only grid can skip a 20/24px button in the minimum 28px viewport.
        # Clamping a final control to overflow still exposes it fully at the end.
        offsets = sorted({*range(0, overflow, 18), overflow,
                          *(max(0, min(top, overflow)) for top in control_tops)})
        maximum = len(offsets) - 1
        self.scroll[key] = max(0, min(self.scroll.get(key, 0), maximum))
        offset = offsets[self.scroll[key]]
        self.scroll_rects.append((viewport, key))
        self.overlay.set_clip(old_clip.clip(viewport))
        try:
            draw(y - offset)
        finally:
            self.overlay.set_clip(old_clip)
        for button in self.buttons[start:]:
            if not viewport.contains(button['rect']):
                # A clipped affordance must not look clickable when its hit box
                # is intentionally absent; wheel it fully into view instead.
                _p.fill(self.overlay, PANEL_BG, button['rect'].clip(viewport))
        self.buttons[start:] = [b for b in self.buttons[start:] if viewport.contains(b['rect'])]
        if offset:
            self._label(panel.x + 2, y, '▲', TXT_DIM, self.font_small)
        if offset < bottom - y - viewport.height:
            self._label(panel.x + 2, viewport.bottom - 14, '▼', TXT_DIM, self.font_small)
        return viewport.bottom

    def _refit_block(self, panel, y, sel, player) -> int:
        """Refit level, its accumulated effects and the button that buys the next (#77).

        Only yard-built stations get this block: planet buildings and satellites are
        out of scope, and `upgrades.eligible` is the same predicate the simulation
        applies, so the panel never offers a row the sim would refuse. A pending
        refit shows its own timer and cancel affordance instead of the button, so a
        station that builds no ships can still stop the work it paid for.
        """
        from game.systems.upgrades import (bonus_table, eligible, queued_refit,
                                           station_level, upgrade_cost, upgrade_time)
        # `_right_panel_content` has already dropped anything this player does not own,
        # so ownership is not re-checked here; `eligible` keeps planet-built hardware
        # out of the block, because an extractor *is* yours.
        if not eligible(sel, self.ds):
            return y
        level = station_level(sel)
        table = bonus_table(sel, self.ds)
        self._label(panel.x + 12, y,
                    i18n.t('REFIT · LEVEL {level}/{max}', level=level,
                           max=table['max_level']), ACCENT, self.font_big,
                    translate=False)
        y += 26
        effects = []
        for key, text in (('hull_bonus', 'hull'), ('shield_bonus', 'shields'),
                          ('shield_regen_bonus', 'regen'), ('damage_bonus', 'damage'),
                          ('production_bonus', 'output'), ('convoy_cargo_bonus', 'cargo')):
            if table[key]:
                # Both the unit word and the whole line go through the pack: the line is
                # assembled here, so a lookup of the finished string would always miss.
                effects.append(i18n.t('{label} +{percent}%', label=i18n.t(text),
                                      percent=f"{table[key] * 100:.0f}"))
        if table['extra_shots']:
            effects.append(i18n.t("+{count} shot/mount", count=table['extra_shots']))
        if table['extra_convoys']:
            effects.append(i18n.t("+{count} convoy", count=table['extra_convoys']))
        y = self._wrapped_labels(panel.x + 12, y,
                                 ' · '.join(effects) if effects else
                                 'As built · buy a level to raise hull, shields and output.',
                                 296) + 6
        pending = queued_refit(sel)
        if pending is not None:
            index = sel.build_queue.index(pending)
            left = max(0.0, float(pending.get('time_left', 0.0)))
            self._label(panel.x + 12, y + 1, f"REFIT IN PROGRESS · {left:.0f}s",
                        TXT_DIM, self.font_small)
            button = pygame.Rect(panel.right - 74, y, 62, 18)
            _p.rect(self.overlay, BAR_BG, button, border_radius=3)
            _p.rect(self.overlay, ACCENT, button, 1, border_radius=3)
            self._label(button.x + 6, button.y + 1, "✕ Cancel", TXT, self.font_small)
            self.buttons.append({"rect": button, "kind": "cancel_build",
                                 "payload": {"target_id": sel.id, "index": index}})
            return y + 22
        cost = upgrade_cost(sel, self.ds)
        seconds = upgrade_time(sel, self.ds)
        if cost is None or seconds is None:
            self._label(panel.x + 12, y, 'MAXIMUM LEVEL', TXT_DIM, self.font_small)
            return y + 20
        button = pygame.Rect(panel.x + 12, y, 296, 20)
        _p.rect(self.overlay, BAR_BG, button, border_radius=3)
        _p.rect(self.overlay, ACCENT, button, 1, border_radius=3)
        self._label(button.x + 8, button.y + 3,
                    i18n.t('▲ Refit to level {level}', level=level + 1), TXT,
                    self.font_small, translate=False)
        self.buttons.append({"rect": button, "kind": "upgrade_station",
                             "payload": {"target_id": sel.id}})
        y += 22
        affordable = (player.credits >= cost['credits']
                      and player.materials >= cost['materials']
                      and player.energy >= cost['energy'])
        self._label(panel.x + 12, y,
                    i18n.t('{credits} cr · {materials} mt · {energy} EN · {time}s',
                           credits=f"{cost['credits']:,.0f}",
                           materials=f"{cost['materials']:,.0f}",
                           energy=f"{cost['energy']:,.0f}", time=f"{seconds:.0f}"),
                    TXT if affordable else WARN, self.font_small, translate=False)
        return y + 20

    def _shipyard_items(self, station, std) -> list:
        """Buildable-ship rows for a station panel.

        builds_ships lists ship ids; ["*"] expands to the full catalogue minus
        engineering hulls when the station's build_role is "warships" — the
        catalogue half of ConstructionSystem.station_can_build_ship(), asked here
        without its level half. A hull the player gated behind a refit level (#106)
        therefore stays in the list and is drawn locked with its level: the gate is
        a price on the row, not a reason to hide a hull from the panel that would
        happily accept it one refit from now.
        """
        from game.systems import construction
        player = self.state.players.get(getattr(station, "owner", None))
        faction = getattr(player, "faction", None)
        if faction is None:
            # Nobody to judge the catalogue against (a hulk, a bare fixture): fall
            # back to the declared list so the panel still draws something.
            ids = sorted(self.ds.ships) if "*" in std.builds_ships else list(std.builds_ships)
            return [self.ds.ships[sid] for sid in ids if sid in self.ds.ships]
        out = []
        for sid in construction.buildable_ship_ids(self.ds, station.data_id, faction):
            sd = self.ds.ships.get(sid)
            if sd is not None:
                out.append(sd)
        return out

    def _row_build_ship(self, d, yy, payload) -> None:
        """One hull; one behind a refit level states the level instead of hiding."""
        from game.systems import construction, upgrades
        station = self.state.entity(payload.get("shipyard_id"))
        gated = 0
        if station is not None and station.owner == getattr(self._cur_player, "id", -1):
            need = construction.required_level(self.ds, station.data_id, d.id)
            if need > upgrades.station_level(station):
                gated = need
        self._build_row(self._cur_panel, yy, d, self._cur_player, payload,
                        "build_ship", gated=gated)

    def _row_research(self, d, yy, payload) -> None:
        """d = TechData; payload carries station_id."""
        panel, p = self._cur_panel, self._cur_player
        ov = self.overlay
        rect = pygame.Rect(panel.x + 12, yy, 296, 34)
        done = d.id in p.researched
        locked = any(r not in p.researched for r in d.requires)
        afford = (p.credits >= d.cost_credits
                  and p.materials >= d.cost_materials
                  and p.energy >= d.cost_energy)
        col = (18, 22, 32, 255)
        tcol = TXT_DIM
        if done:
            tcol = GOOD
        elif locked:
            tcol = (90, 100, 116)
        elif afford:
            col = (24, 34, 52, 255)
            tcol = TXT
        _p.rect(ov, col, rect, border_radius=4)
        _p.rect(ov, PANEL_EDGE if (done or locked) else
                         (ACCENT if afford else PANEL_EDGE), rect, 1,
                         border_radius=4)
        self._label(rect.x + 8, rect.y + 2, d.display_name, tcol)
        cost = i18n.t('{credits} cr · {materials} mt',
                      credits=f"{d.cost_credits:,.0f}",
                      materials=f"{d.cost_materials:,.0f}")
        self._label(rect.x + 8, rect.y + 18, cost, TXT_DIM, self.font_small,
                    translate=False)
        if not done and not locked and afford:
            self.buttons.append({"rect": rect, "kind": "research",
                                 "payload": {"station_id": payload["station_id"],
                                             "tech_id": d.id}})

    def _build_row(self, panel, y, d, p, payload, kind, gated: int = 0) -> int:
        """One buildable row: name, cost, affordability color. Returns next y.

        `gated` is the refit level the hull needs and the station has not reached
        (#106). Such a row is drawn like an unaffordable one — dim name, no button —
        but says why on its staffing line, because a gate the player configured has
        to be readable at the moment it bites.
        """
        ov = self.overlay
        rect = pygame.Rect(panel.x + 12, y, 296, 50)
        afford = (not gated) and (
            p.credits >= d.cost_credits and p.materials >= d.cost_materials
            and p.energy >= d.cost_energy and p.crew >= d.crew_cost)
        _p.rect(ov, (24, 34, 52, 255) if afford else (18, 22, 32, 255),
                         rect, border_radius=4)
        _p.rect(ov, ACCENT if afford else PANEL_EDGE, rect, 1,
                         border_radius=4)
        self._label(rect.x + 8, rect.y + 2, self._fit_text(d.display_name, 280),
                    TXT if afford else TXT_DIM)
        cost = i18n.t('{credits} cr · {materials} mt · {energy} EN',
                      credits=f"{d.cost_credits:,.0f}",
                      materials=f"{d.cost_materials:,.0f}",
                      energy=f"{d.cost_energy:,.0f}")
        self._label(rect.x + 8, rect.y + 18, self._fit_text(cost, 280, self.font_small),
                    TXT_DIM, self.font_small, translate=False)
        staffing = i18n.t('{crew} crew · {command} cmd · {time}s',
                          crew=f"{d.crew_cost:,.0f}",
                          command=f"{getattr(d, 'command_cost', 0)}",
                          time=f"{d.build_time:g}")
        if gated:
            self._label(rect.x + 8, rect.y + 34,
                        self._fit_text(i18n.t('Refit level {level} required',
                                             level=gated), 280, self.font_small),
                        WARN, self.font_small)
        else:
            self._label(rect.x + 8, rect.y + 34,
                        self._fit_text(staffing, 280, self.font_small), TXT_DIM,
                        self.font_small, translate=False)
        if afford:
            self.buttons.append({"rect": rect, "kind": kind, "payload": payload})
        return y + 54

    # ------------------------------------------------------------- scrollable lists
    def _scrollable(self, panel, y, items, p, key, draw_fn, sel) -> int:
        """Clip-scroll a list of buildable items inside the right panel.

        draw_fn(d, yy, payload) renders one row; payload carries the selected
        builder/shipyard id. Wheel over the panel scrolls (input.py).
        """
        self._cur_panel, self._cur_player = panel, p
        ov = self.overlay
        clip = pygame.Rect(panel.x + 4, y, panel.width - 8,
                           panel.bottom - y - 8)
        if clip.height <= 40:
            return panel.bottom
        self.scroll_rects.append((clip, key))   # wheel routing (input.py)
        row_height = 38 if key == 'techs' else 54
        visible_rows = clip.height // row_height
        if key not in self.scroll:              # unknown list kind: no scroll
            self.scroll[key] = 0
        self.scroll[key] = max(0, min(self.scroll[key],
                                      max(0, len(items) - visible_rows)))
        off = self.scroll[key]
        # scroll hint arrows
        if off > 0:
            self._label(panel.centerx - 6, y - 1, "▲", TXT_DIM, self.font_small)
        if off + visible_rows < len(items):
            self._label(panel.centerx - 6, clip.bottom - 12, "▼", TXT_DIM,
                        self.font_small)
        # clip rendering
        old = ov.get_clip()
        ov.set_clip(clip)
        yy = y
        for d in items[off:off + visible_rows]:
            payload = {
                "stations": lambda d=d: {"builder_id": sel.id,
                                         "station_kind": d.id},
                "ships": lambda d=d: {"shipyard_id": sel.id,
                                      "ship_id": d.id},
                "techs": lambda d=d: {"station_id": sel.id},
            }.get(key, lambda d=d: {})()
            draw_fn(d, yy, payload)
            yy += row_height
        ov.set_clip(old)
        return panel.bottom

    def _techs(self):
        return list(getattr(self.ds, "techs", {}).items())

    # ------------------------------------------------------------------ event log
    def _event_log(self, local_player: int) -> None:
        ov = self.overlay
        # Global enemy research/build/destruction events are not intelligence.
        log = [ev for ev in self.state.events.log if ev.type in LOG_TYPES
               and ev.data.get("owner") == local_player]
        if not log:
            return
        rows = log[-9:]
        height = 34 + 18 * len(rows)
        x, y = 10, self.height - 14 - height
        rect = pygame.Rect(x, y, 320 if self.native_panels else 420, height)
        previous = _p.native_sink
        sink = None
        if self.native_panels:
            from render_bridge.vector_hud import Sink
            # Same 240px width/left edge as SELECTION; preserve the bottom gap.
            sink = Sink(self._native_capture(), rect, source_x=x, target_x=x,
                        source_y=rect.bottom, target_y=rect.bottom, scale=.75)
            _p.native_sink = sink
        self.blocked_rects.append(pygame.Rect(sink.rect(rect)) if sink else rect)
        try:
            _p.rect(ov, PANEL_BG, rect, border_radius=8)
            _p.rect(ov, PANEL_EDGE, rect, 1, border_radius=8)
            self._label(x + 10, y + 6, "INCOMING", TXT_DIM, self.font_small)
            yy = y + 24
            for ev in rows:
                d = ev.data
                line = self._event_text(ev, local_player)
                col = GOOD if d.get("owner", d.get("winner", -9)) == local_player \
                    else TXT_DIM
                if ev.type == "unit_destroyed":
                    col = BAD if d.get("owner") == local_player else TXT_DIM
                if sink:
                    line = self._fit_text(line, rect.width - 20, self.font_small)
                self._label(x + 10, yy, line, col, self.font_small)
                yy += 18
        finally:
            _p.native_sink = previous

    @staticmethod
    def _event_text(ev, local_player: int) -> str:
        d = ev.data
        t = ev.type
        if t == "unit_destroyed":
            return f"✕ {d.get('unit', 'unit')} lost ({d.get('faction', '?')})"
        if t == "station_built":
            return f"△ {d.get('station', 'station')} online"
        if t == "construction_complete":
            return f"△ {d.get('station', 'structure')} complete"
        if t == "research_complete":
            return f"✦ research: {d.get('tech', '?')}"
        if t == "planet_colonized":
            return f"◉ planet {d.get('planet', '?')} colonized"
        return t

    # ------------------------------------------------------------- placement mode
    def _placement_banner(self) -> None:
        placement = self.placement
        if not placement:
            return
        with self._native_layer():
            self._placement_content(placement)

    def _placement_content(self, placement: dict) -> None:
        ov = self.overlay
        name = str(placement.get("station_kind", "")).replace("_", " ")
        text = f"PLACE {name.upper()} — left-click to position · ESC/right-click to cancel"
        r = self._text_box(text, self.font_big, WORLD_HUD_TEXT_SCALE)
        r.center = (self.width // 2, 56)
        bg = r.inflate(int(26 * WORLD_HUD_TEXT_SCALE), int(14 * WORLD_HUD_TEXT_SCALE))
        _p.rect(ov, (30, 24, 10, 225), bg, border_radius=6)
        _p.rect(ov, WARN, bg, 1, border_radius=6)
        self._screen_text(r, text, WARN, self.font_big, WORLD_HUD_TEXT_SCALE)
        ghost = placement.get("ghost")
        if ghost:
            valid = ghost.get("valid", True)
            gx, gy = ghost["sx"], ghost["sy"]
            rad = max(10, int(ghost.get("radius", 120)))
            col = GOOD if valid else BAD
            _p.circle(ov, (*col[:3], 90), (int(gx), int(gy)), rad, 1)
            _p.circle(ov, (*col[:3], 40), (int(gx), int(gy)), rad)
            _p.line(ov, col, (gx - 12, gy), (gx + 12, gy), 1)
            _p.line(ov, col, (gx, gy - 12), (gx, gy + 12), 1)
            # reason line: WHY the ghost is red (same validator as the sim)
            reason = ghost.get("reason", "")
            if not valid and reason:
                text = f"✕ {reason}"
                r = self._text_box(text, self.font_small, WORLD_HUD_TEXT_SCALE)
                r.midbottom = (gx, gy - rad - 8)
                bg = r.inflate(int(12 * WORLD_HUD_TEXT_SCALE), int(6 * WORLD_HUD_TEXT_SCALE))
                _p.rect(ov, (28, 12, 10, 220), bg, border_radius=4)
                _p.rect(ov, BAD, bg, 1, border_radius=4)
                self._screen_text(r, text, BAD, self.font_small, WORLD_HUD_TEXT_SCALE)
            elif valid:
                text = f"✓ place {placement.get('station_kind', '').replace('_', ' ')}"
                r = self._text_box(text, self.font_small, WORLD_HUD_TEXT_SCALE)
                r.midbottom = (gx, gy - rad - 8)
                self._screen_text(r, text, GOOD, self.font_small, WORLD_HUD_TEXT_SCALE)

    # ------------------------------------------------- construction progress
    def _construction_progress(self) -> None:
        """A ring at each site being built, filling clockwise as the work completes.

        The placement disc already answers *where*; once the order is paid for this answers *how far*,
        around the same circle, so a station that is still translucent reads as work in progress rather
        than as a model that failed to finish. The radius is projected from the site so the ring sits on
        the ground under the hull at any zoom, unlike the disc, which is drawn at a fixed pixel size to
        stay readable while the cursor moves.
        """
        camera = getattr(self, "camera", None)
        if camera is None:
            return
        with self._native_layer():
            self._construction_progress_content(camera)

    def _construction_progress_content(self, camera) -> None:
        ov = self.overlay
        for builder in sorted(self.state.entities.values(), key=lambda e: e.id):
            if (not builder.alive or not builder.is_construction
                    or builder.owner != self.local_player or not builder.build_queue):
                continue
            item = builder.build_queue[0]
            if item.get("kind") != "station" or not item.get("pos"):
                continue
            data = self.ds.stations.get(item.get("item"))
            if data is None:
                continue
            pos = item["pos"]
            if isinstance(pos, dict):
                x, y, z = pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)
            else:
                x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
            centre = camera.world_to_screen(x, y, z)
            if centre is None:
                continue
            cx, cy = centre
            radius = max(8.0, float(getattr(data, "radius", 90.0)))
            radius_px = radius  # fallback: the same fixed pixel size the placement disc uses
            try:
                right = camera.basis()[0]
                edge = camera.world_to_screen(x + right[0] * radius, y + right[1] * radius,
                                              z + right[2] * radius)
            except (AttributeError, IndexError, TypeError):
                edge = None
            if edge is not None:
                radius_px = math.hypot(edge[0] - cx, edge[1] - cy)
            radius_px = max(9.0, min(360.0, radius_px))
            total = max(1e-6, float(item.get("total", 1.0)))
            fraction = min(1.0, max(0.0, 1.0 - float(item.get("time_left", 0.0)) / total))
            # Green, like the placement check: the arc answers "is this progressing", and a player's own
            # colour is a 0..1 float triple that would clamp to black in a 0..255 painter.
            _p.circle(ov, (*GOOD, 70), (int(cx), int(cy)), int(radius_px), 1)
            if _p.native_sink is not None:
                _p.polygon(ov, (*GOOD, 240), self._arc_band((cx, cy), radius_px, fraction))
            else:
                # Legacy overlay: short chords rather than pygame.draw.arc, because every overlay
                # op goes through the recorder and an arc is not one of its primitives.
                steps = max(1, int(48 * fraction))
                sweep = math.tau * fraction
                prev = (cx + radius_px * math.cos(-math.pi / 2),
                        cy + radius_px * math.sin(-math.pi / 2))
                for i in range(1, steps + 1):
                    angle = -math.pi / 2 + sweep * i / steps
                    point = (cx + radius_px * math.cos(angle), cy + radius_px * math.sin(angle))
                    _p.line(ov, (*GOOD, 240), prev, point, 2)
                    prev = point
            label = f"{int(round(fraction * 100))}%"
            r = self._text_box(label, self.font_small, WORLD_HUD_TEXT_SCALE)
            r.midtop = (int(cx), int(cy + radius_px) + 4)
            self._screen_text(r, label, GOOD, self.font_small, WORLD_HUD_TEXT_SCALE)

    @staticmethod
    def _arc_band(centre, radius: float, fraction: float, band: float = 3.0) -> list:
        """One polygon for the completed arc: the native layer has no arc primitive.

        Outer rim forwards, inner rim back, which leaves a simple annulus even-odd fills
        correctly. Point budget is 2 * (120 + 1), inside the renderer's 256-point limit.
        """
        fraction = max(0.0, min(1.0, fraction))
        steps = max(2, min(120, int(round(96 * max(fraction, 0.02)))))
        sweep = math.tau * fraction
        inner = max(0.0, radius - band)
        cx, cy = centre
        outer_pts, inner_pts = [], []
        for i in range(steps + 1):
            angle = -math.pi / 2 + sweep * i / steps
            ca, sa = math.cos(angle), math.sin(angle)
            outer_pts.append((cx + radius * ca, cy + radius * sa))
            inner_pts.append((cx + inner * ca, cy + inner * sa))
        return outer_pts + inner_pts[::-1]

    # ------------------------------------------------------------------ minimap
    def _draw_floating_texts(self) -> None:
        """Sim rejection/status messages as floating labels above the world."""
        with self._native_layer():
            self._draw_floating_texts_content()

    def _draw_floating_texts_content(self) -> None:
        ov = self.overlay
        for x, y, text, rgb, alpha in getattr(self, "floating_texts", []):
            if not text:
                continue
            r = self._text_box(text, self.font_small, WORLD_HUD_TEXT_SCALE)
            r.midtop = (x, y)
            bg = r.inflate(int(10 * WORLD_HUD_TEXT_SCALE), int(4 * WORLD_HUD_TEXT_SCALE))
            _p.rect(ov, (10, 12, 18, int(200 * alpha)), bg, border_radius=4)
            self._screen_text(r, text, rgb, self.font_small, WORLD_HUD_TEXT_SCALE)

    def _minimap(self, selection: set, local_player: int) -> None:
        if self.native_panels and _p.native_sink is None:
            from render_bridge.vector_hud import Sink
            previous = _p.native_sink
            _p.native_sink = Sink(self._native_capture(), (self.width - 222, self.height - 222, 210, 210))
            try:
                self._minimap_content(selection, local_player)
            finally:
                _p.native_sink = previous
            return
        self._minimap_content(selection, local_player)

    def _minimap_content(self, selection: set, local_player: int) -> None:
        ov = self.overlay
        st = self.state
        size = 210
        x, y = self.width - size - 12, self.height - size - 12
        rect = pygame.Rect(x, y, size, size)
        self.minimap_rect = rect
        _p.rect(ov, (8, 10, 16, 225), rect, border_radius=6)
        _p.rect(ov, PANEL_EDGE, rect, 1, border_radius=6)
        bounds = max(1.0, getattr(st.map_info, "bounds", 26000.0))
        half = bounds / 2.0
        cx, cy = rect.centerx, rect.centery

        def px(wx, wz):
            return int(cx + wx / half * (size / 2 - 4)), \
                   int(cy + wz / half * (size / 2 - 4))

        # Reuse the small cached cell mask, rather than scanning screen pixels.
        if _p.native_sink is not None:
            _p.native_sink.fog_mask(ov, st, local_player, (x + 4, y + 4, size - 8, size - 8))
        else:
            fog = self.fog.surface(st, local_player)
            _p.blit(ov, pygame.transform.scale(fog, (size - 8, size - 8)), (x + 4, y + 4))
        for e in known_entities(st, local_player):
            if not e.alive:
                continue
            mx, my = px(e.pos.x, e.pos.z)
            if e.is_planet:
                r = max(2, int(e.radius / half * (size / 2)))
                col = (70, 80, 100, 255)
                if e.colonized_by is not None:
                    col = self._owner_rgb(e.colonized_by)
                if not st.can_see(local_player, e.id):
                    col = tuple(int(c * .42) for c in col[:3])
                _p.circle(ov, col, (mx, my), r, 1 if e.colonized_by is None else 0)
            elif e.owner == -1:
                continue
            else:
                col = self._owner_rgb(e.owner)
                r = 4 if (e.is_station or e.kind == "supercapital") else 2
                if e.is_station:
                    _p.circle(ov, col, (mx, my), r)
                elif e.is_squadron:
                    _p.line(ov, col, (mx - r, my), (mx + r, my), 1)
                else:
                    _p.rect(ov, col, (mx - 2, my - 2, 4, 4))
        # Destinations where completed units leave for. On the map the cue is a diamond alone;
        # here the tether to its station is a single line, which is what makes the pair legible
        # without hunting the station panel (issue #161).
        from game.systems.collection_points import collection_capable
        for e in known_entities(st, local_player):
            point = getattr(e, 'collection_point', None)
            if point is None or not e.alive or not collection_capable(e):
                continue
            if e.owner != local_player or e.id not in selection:
                continue
            sx, sy = px(e.pos.x, e.pos.z)
            mx, my = px(point.x, point.z)
            _p.line(ov, tuple(int(c * .55) for c in COLLECTION) + (255,), (sx, sy), (mx, my), 1)
            _p.polygon(ov, COLLECTION + (255,), [(mx, my - 4), (mx + 4, my), (mx, my + 4),
                                                 (mx - 4, my)], 1)
        for eid in selection:
            e = st.known_entity(local_player, eid)
            if e is not None:
                mx, my = px(e.pos.x, e.pos.z)
                _p.circle(ov, (255, 255, 255), (mx, my), 5, 1)

    def set_camera_ref(self, camera) -> None:
        self.camera = camera

    def set_floating_texts(self, texts: list) -> None:
        """Screen-projected sim messages (from renderer.floating_texts_screen)."""
        self.floating_texts = texts

    def set_drag_box(self, start, cur) -> None:
        """Live box-select rectangle in screen space (None while not dragging)."""
        self.drag_box = (start, cur)

    def _draw_drag_box(self) -> None:
        """Draw the box-select rectangle between the two screen corners.

        Left-drag always selected correctly, but nothing ever DREW the box, so
        the drag looked like it was doing nothing.
        """
        box = getattr(self, "drag_box", None)
        if not box:
            return
        start, cur = box
        # check the corners BEFORE unpacking: main.py calls set_drag_box(None,
        # None) every frame while not dragging, which is truthy as a tuple
        if start is None or cur is None:
            return
        x0, y0 = start
        x1, y1 = cur
        if abs(x1 - x0) < 2 and abs(y1 - y0) < 2:
            return
        ov = self.overlay
        rect = pygame.Rect(min(x0, x1), min(y0, y1),
                           abs(x1 - x0), abs(y1 - y0))
        _p.rect(ov, DRAG_FILL, rect)
        _p.rect(ov, DRAG_EDGE, rect, 1)

    def _owner_rgb(self, owner: int):
        p = self.state.players.get(owner)
        if p is None:
            return (150, 150, 150)
        c = p.color
        return (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))

    # ------------------------------------------------------------------ text/bar utils
    def _label(self, x, y, text, color=TXT, font=None, translate=True):
        # Drawing edge (#93): panel headings and values funnel through here, including
        # data names (ship / station / tech display names). `translate=False` is for
        # callers that already hold a translated string: a wrapped line is not a msgid,
        # so looking it up again could only ever miss.
        shown = str(i18n.t(text) if translate else text)
        font = font or self.font
        if _p.native_sink is not None:
            width = getattr(text, 'width', max(0, _p.native_sink.scope.right - x - 8))
            _p.native_sink.text(self.overlay, x, y, shown, color, self._native_text_size(font),
                                width, font.get_linesize())
            return
        surf = font.render(shown, True, color)
        _p.blit_text(self.overlay, surf, (x, y), shown, color, id(font))

    def _bar(self, x, y, w, h, frac, color, label=None):
        frac = max(0.0, min(1.0, frac))
        rect = pygame.Rect(x, y, w, h)
        _p.rect(self.overlay, BAR_BG, rect)
        if frac > 0:
            _p.rect(self.overlay, color,
                             (x, y, max(2, int(w * frac)), h))
        _p.rect(self.overlay, (50, 62, 84), rect, 1)
        if label:
            if _p.native_sink is not None:
                # Native text positions anchor measured ink, not a padded
                # pygame glyph surface. Keep that ink box inside the bar.
                _p.native_sink.text(self.overlay, x + 4, y,
                                    label, (200, 210, 225), 12 * NATIVE_TEXT_EM_SCALE, max(0, w - 8), h)
                return
            surf = self.font_small.render(label, True, (200, 210, 225))
            _p.blit_text(self.overlay, surf, (x + 4, y + (h - surf.get_height()) // 2),
                         label, (200, 210, 225), id(self.font_small))

    # ------------------------------------------------------------------ GL upload
    def resize(self, width: int, height: int) -> None:
        """Re-layout for a new window size (fullscreen toggle)."""
        self.width = width
        self.height = height
        self.overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self.uploader.release()
        self.uploader.full_pending = True
        self.recorder.invalidate()
        self.minimap_rect = None
        self.buttons.clear()
        self.scroll_rects.clear()
        self.blocked_rects.clear()

    def _upload(self) -> None:
        # Only the rects whose paint calls changed since the previous frame go to the GPU; the
        # recorder proves the rest produced identical pixels (render/overlay_upload.py).
        self.uploader.upload(self.overlay, self.recorder.take_dirty())
        self.tex = self.uploader.tex
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)

    def draw_gl(self) -> None:
        """Blit the overlay as a fullscreen quad (ortho pass)."""
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        # NOTE: no glClear here — the world was already rendered this frame;
        # clearing would erase the 3D scene under the overlay.
        # HUD texels are display colours, not lit hull material. Leaving world
        # lighting enabled modulates every label by the last geometry normal.
        was_lit = _gl.glIsEnabled(_gl.GL_LIGHTING)
        glDisable(_gl.GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1, 1, 1, 1)
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(self.width, 0)
        glTexCoord2f(1, 1); glVertex2f(self.width, self.height)
        glTexCoord2f(0, 1); glVertex2f(0, self.height)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)
        if was_lit:
            glEnable(_gl.GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()


import OpenGL.GL as _gl  # noqa: E402  (kept at bottom to reuse glGenTextures)