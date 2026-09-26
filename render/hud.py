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

import pygame

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

from game.core.entity import QUADRANTS
from game.data.store import DataStore

# ---------------------------------------------------------------- palette (blue-gray)
PANEL_BG = (14, 18, 28, 205)
PANEL_EDGE = (60, 80, 110, 220)
HEADER_BG = (22, 30, 46, 230)
TXT = (214, 224, 238)
TXT_DIM = (128, 142, 164)
ACCENT = (86, 140, 220)
WARN = (232, 168, 76)
BAD = (232, 92, 76)
GOOD = (110, 200, 120)
BAR_BG = (34, 44, 62, 255)
BAR_SHIELD = (84, 150, 220)
BAR_HULL = (110, 200, 120)
BAR_STRUCT = (150, 150, 160)

LOG_TYPES = ("unit_destroyed", "station_built", "research_complete",
             "planet_colonized", "construction_complete")


class HUD:
    """Composited 2D overlay. Pure view: render(state, selection) -> GL quad."""

    def __init__(self, width: int, height: int, state):
        self.width = width
        self.height = height
        self.state = state
        self.ds = DataStore.get()
        pygame.font.init()
        self.font = pygame.font.SysFont("menlo,consolas,monaco", 15)
        self.font_big = pygame.font.SysFont("menlo,consolas,monaco", 19, bold=True)
        self.font_small = pygame.font.SysFont("menlo,consolas,monaco", 12)
        self.font_title = pygame.font.SysFont("helvetica,arial", 22, bold=True)
        self.overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self.tex = None
        self.buttons: list[dict] = []   # {"rect": Rect, "kind": str, "payload": dict}
        self.minimap_rect = None        # set each frame; input uses it
        self.selected_abilities: list = []
        # scrollable panels: kind -> scroll offset in rows
        self.scroll: dict = {"ships": 0, "techs": 0, "stations": 0}
        self._cur_panel = None          # set by _scrollable for row callbacks
        self._cur_player = None
        # placement mode: payload dict for build_station awaiting a click
        self.placement: dict | None = None
        # per-frame scrollable regions: list of (rect, key) for wheel routing
        self.scroll_rects: list = []

    # ------------------------------------------------------------------ frame
    def render(self, selection: set, hover_id: int | None,
               local_player: int, paused: bool, flash_msg: str = "",
               flash_left: float = 0.0, fps: float = 0.0) -> None:
        ov = self.overlay
        ov.fill((0, 0, 0, 0))
        self.scroll_rects = []          # rebuilt each frame
        self.buttons = []
        self._top_bar(local_player, paused)
        self._left_panel(selection, local_player)
        self._right_panel(selection, local_player)
        self._event_log(local_player)
        self._minimap(selection, local_player)
        self._placement_banner()
        if flash_msg and flash_left > 0.0:
            surf = self.font_big.render(flash_msg, True, WARN)
            r = surf.get_rect(center=(self.width // 2, self.height - 60))
            bg = r.inflate(24, 12)
            pygame.draw.rect(ov, PANEL_BG, bg, border_radius=6)
            pygame.draw.rect(ov, PANEL_EDGE, bg, 1, border_radius=6)
            ov.blit(surf, r)
        if fps > 0.0:
            self._label(self.width - 90, 40, f"{fps:0.0f} FPS", TXT_DIM,
                        self.font_small)
        self._upload()

    # ------------------------------------------------------------------ top bar
    def _top_bar(self, local_player: int, paused: bool) -> None:
        ov = self.overlay
        st = self.state
        p = st.players.get(local_player)
        rect = pygame.Rect(0, 0, self.width, 34)
        pygame.draw.rect(ov, HEADER_BG, rect)
        pygame.draw.line(ov, PANEL_EDGE, (0, 33), (self.width, 33), 1)

        if p is None:
            return
        x = 14
        cap_used = p.command_used(st.entities)
        cells = (
            ("CR", f"{p.credits:,.0f}", ACCENT),
            ("MT", f"{p.materials:,.0f}", (200, 170, 120)),
            ("EN", f"{p.energy:,.0f}", (150, 220, 240)),
            ("CRW", f"{p.crew:,.0f}", GOOD),
            ("CMD", f"{cap_used}/{p.command_capacity}",
             WARN if cap_used >= p.command_capacity else TXT),
        )
        for label, val, col in cells:
            surf = self.font.render(label, True, TXT_DIM)
            ov.blit(surf, (x, 9))
            x += surf.get_width() + 5
            surf = self.font_big.render(val, True, col)
            ov.blit(surf, (x, 7))
            x += surf.get_width() + 22

        t = st.time
        clock = f"{int(t // 60):02d}:{int(t % 60):02d}"
        surf = self.font_big.render(clock, True, TXT)
        ov.blit(surf, (self.width // 2 - surf.get_width() // 2, 7))

        if paused:
            surf = self.font_big.render("PAUSED", True, WARN)
            ov.blit(surf, (self.width - 200, 7))
        if st.game_over:
            w = st.winner
            col = GOOD if w == local_player else BAD
            name = st.players[w].name if w in st.players else f"team {w}"
            surf = self.font_title.render(f"VICTORY — {name}", True, col)
            rect = surf.get_rect(center=(self.width // 2, self.height // 2 - 40))
            bg = rect.inflate(30, 16)
            pygame.draw.rect(ov, PANEL_BG, bg, border_radius=6)
            pygame.draw.rect(ov, col, bg, 2, border_radius=6)
            ov.blit(surf, rect)
        if st.game_over:
            surf = self.font.render("press ESC to exit", True, TXT_DIM)
            ov.blit(surf, (self.width // 2 - surf.get_width() // 2,
                           self.height // 2 + 4))

    # ------------------------------------------------------------------ left panel
    def _left_panel(self, selection: set, local_player: int) -> None:
        ov = self.overlay
        st = self.state
        ents = [st.entity(eid) for eid in sorted(selection)]
        ents = [e for e in ents if e is not None]
        panel = pygame.Rect(10, 44, 320, 430)
        pygame.draw.rect(ov, PANEL_BG, panel, border_radius=8)
        pygame.draw.rect(ov, PANEL_EDGE, panel, 1, border_radius=8)
        if not ents:
            self._label(panel.x + 12, panel.y + 10, "NO SELECTION", TXT_DIM)
            self._label(panel.x + 12, panel.y + 34,
                        "left-click / drag to select ships", TXT_DIM)
            self._label(panel.x + 12, panel.y + 52,
                        "1-9 control groups · G fleet menu", TXT_DIM)
            return

        e = ents[0]
        sd = self.ds.ships.get(e.data_id)
        std = self.ds.stations.get(e.data_id) if sd is None else None
        name = self.ds.unit_name(e)
        if e.name_override:
            name = e.name_override
        cat = sd.category if sd else (std.id.replace("_", " ") if std else e.kind)
        self._label(panel.x + 12, panel.y + 8, name.upper(), TXT, self.font_big)
        fac = st.players[e.owner].name if e.owner in st.players else "Neutral"
        self._label(panel.x + 12, panel.y + 34, f"{cat.upper()} · {fac}", TXT_DIM)
        lv = f"  LV{e.level}" if e.level > 1 else ""
        self._label(panel.x + 12, panel.y + 52, f"LEVEL {e.level}{lv}", WARN
                    if e.level >= 4 else TXT_DIM)

        y = panel.y + 78
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
        for name_s, sys_st in list(e.systems.items())[:5]:
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
        # orders
        order = e.order_type.replace("_", " ").upper()
        if e.order_target_id is not None:
            tgt = st.entity(e.order_target_id)
            if tgt:
                order += f" → {self.ds.unit_name(tgt)}"
        self._label(panel.x + 12, y, f"ORDER: {order}", TXT_DIM)
        y += 20
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
            self._bar(panel.x + 12, y, 296, 10, done, ACCENT)
            self._label(panel.x + 12, y - 14, f"BUILDING {it_name.upper()}", TXT)
            y += 34
        # jump charge
        if e.jump_target is not None:
            self._label(panel.x + 12, y,
                        f"HYPERSPACE CHARGE {e.jump_charge:0.0f}", WARN)
            y += 20
        # abilities (clickable)
        for aid in getattr(sd, "abilities", []) if sd else []:
            ad = self.ds.abilities.get(aid)
            if ad is None:
                continue
            cd = e.ability_cooldowns.get(aid, 0.0)
            ready = cd <= 0 and e.energy >= ad.energy_cost
            rect = pygame.Rect(panel.x + 12, y, 296, 20)
            pygame.draw.rect(ov, (24, 32, 48, 255) if ready else (18, 22, 32, 255),
                             rect, border_radius=4)
            pygame.draw.rect(ov, ACCENT if ready else PANEL_EDGE, rect, 1,
                             border_radius=4)
            label = f"{ad.display_name}  [{cd:0.0f}s]" if cd > 0 else ad.display_name
            self._label(rect.x + 8, rect.y + 2, label,
                        TXT if ready else TXT_DIM)
            self.buttons.append({"rect": rect, "kind": "ability",
                                 "payload": {"unit_ids": sorted(selection),
                                             "ability_id": aid}})
            y += 24

    # ------------------------------------------------------------------ right panel
    def _right_panel(self, selection: set, local_player: int) -> None:
        ov = self.overlay
        st = self.state
        p = st.players.get(local_player)
        panel = pygame.Rect(self.width - 330, 44, 320, 430)
        pygame.draw.rect(ov, PANEL_BG, panel, border_radius=8)
        pygame.draw.rect(ov, PANEL_EDGE, panel, 1, border_radius=8)
        if p is None:
            return
        ents = [st.entity(eid) for eid in selection]
        ents = [e for e in ents if e is not None and e.owner == local_player]
        sel = ents[0] if ents else None

        y = panel.y + 10
        # constructor selected -> build stations (scrollable)
        if sel is not None and sel.is_construction:
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
            if std is not None and std.builds_ships:
                self._label(panel.x + 12, y, "SHIP PRODUCTION", ACCENT,
                            self.font_big)
                y += 28
                q = sel.build_queue
                for item in q[:3]:
                    self._label(panel.x + 12, y,
                                f"▸ {str(item.get('item', '')).upper()}", TXT_DIM)
                    y += 16
                if q:
                    y += 6
                items = [self.ds.ships.get(sid) for sid in std.builds_ships
                         if sid != "*" and self.ds.ships.get(sid) is not None]
                y = self._scrollable(panel, y, items, p, "ships",
                                     self._row_build_ship, sel)
            if std is not None and std.research:
                self._label(panel.x + 12, y, "RESEARCH", ACCENT, self.font_big)
                y += 28
                techs = [td for tid, td in self._techs()
                         if td.faction == p.faction]
                y = self._scrollable(panel, y, techs, p, "techs",
                                     self._row_research, sel)
        else:
            self._label(panel.x + 12, y, "FLEET COMMAND", ACCENT, self.font_big)
            y += 28
            self._label(panel.x + 12, y, "select a constructor or station", TXT_DIM)
            y += 20
            self._label(panel.x + 12, y, "B  build menu · R  research", TXT_DIM)
            y += 18
            self._label(panel.x + 12, y, "G  fleet formation & stance", TXT_DIM)
            y += 18
            self._label(panel.x + 12, y, "J  hyperspace jump", TXT_DIM)

    def _row_build_station(self, d, yy, payload) -> None:
        self._build_row(self._cur_panel, yy, d, self._cur_player, payload,
                        "build_station_place")

    def _row_build_ship(self, d, yy, payload) -> None:
        self._build_row(self._cur_panel, yy, d, self._cur_player, payload,
                        "build_ship")

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
        pygame.draw.rect(ov, col, rect, border_radius=4)
        pygame.draw.rect(ov, PANEL_EDGE if (done or locked) else
                         (ACCENT if afford else PANEL_EDGE), rect, 1,
                         border_radius=4)
        self._label(rect.x + 8, rect.y + 2, d.display_name, tcol)
        cost = f"{d.cost_credits:,.0f} cr · {d.cost_materials:,.0f} mt"
        self._label(rect.x + 8, rect.y + 18, cost, TXT_DIM, self.font_small)
        if not done and not locked and afford:
            self.buttons.append({"rect": rect, "kind": "research",
                                 "payload": {"station_id": payload["station_id"],
                                             "tech_id": d.id}})

    def _build_row(self, panel, y, d, p, payload, kind) -> int:
        """One buildable row: name, cost, affordability color. Returns next y."""
        ov = self.overlay
        rect = pygame.Rect(panel.x + 12, y, 296, 34)
        afford = (p.credits >= d.cost_credits and p.materials >= d.cost_materials
                  and p.energy >= d.cost_energy and p.crew >= d.crew_cost)
        pygame.draw.rect(ov, (24, 34, 52, 255) if afford else (18, 22, 32, 255),
                         rect, border_radius=4)
        pygame.draw.rect(ov, ACCENT if afford else PANEL_EDGE, rect, 1,
                         border_radius=4)
        self._label(rect.x + 8, rect.y + 2, d.display_name,
                    TXT if afford else TXT_DIM)
        cost = (f"{d.cost_credits:,.0f} cr · {d.cost_materials:,.0f} mt"
                f" · {getattr(d, 'command_cost', 0)} cmd")
        self._label(rect.x + 8, rect.y + 18, cost, TXT_DIM, self.font_small)
        if afford:
            self.buttons.append({"rect": rect, "kind": kind, "payload": payload})
        return y + 38

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
        visible_rows = clip.height // 38
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
        yy = y - off * 38
        for d in items:
            if yy > clip.bottom:
                break
            if yy + 34 >= clip.y:
                payload = {
                    "stations": lambda d=d: {"builder_id": sel.id,
                                             "station_kind": d.id},
                    "ships": lambda d=d: {"shipyard_id": sel.id,
                                          "ship_id": d.id},
                }[key]()
                draw_fn(d, yy, payload)
            yy += 38
        ov.set_clip(old)
        return panel.bottom

    def _techs(self):
        return list(getattr(self.ds, "techs", {}).items())

    # ------------------------------------------------------------------ event log
    def _event_log(self, local_player: int) -> None:
        ov = self.overlay
        log = [ev for ev in self.state.events.log if ev.type in LOG_TYPES]
        if not log:
            return
        x, y = 10, self.height - 210
        rect = pygame.Rect(x, y, 420, 196)
        pygame.draw.rect(ov, PANEL_BG, rect, border_radius=8)
        pygame.draw.rect(ov, PANEL_EDGE, rect, 1, border_radius=8)
        self._label(x + 10, y + 6, "INCOMING", TXT_DIM, self.font_small)
        yy = y + 24
        for ev in log[-9:]:
            d = ev.data
            line = self._event_text(ev, local_player)
            col = GOOD if d.get("owner", d.get("winner", -9)) == local_player \
                else TXT_DIM
            if ev.type == "unit_destroyed":
                col = BAD if d.get("owner") == local_player else TXT_DIM
            self._label(x + 10, yy, line, col, self.font_small)
            yy += 18

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
        if not self.placement:
            return
        ov = self.overlay
        name = str(self.placement.get("station_kind", "")).replace("_", " ")
        text = f"PLACE {name.upper()} — left-click to position · ESC/right-click to cancel"
        surf = self.font_big.render(text, True, WARN)
        r = surf.get_rect(center=(self.width // 2, 56))
        bg = r.inflate(26, 14)
        pygame.draw.rect(ov, (30, 24, 10, 225), bg, border_radius=6)
        pygame.draw.rect(ov, WARN, bg, 1, border_radius=6)
        ov.blit(surf, r)
        ghost = self.placement.get("ghost")
        if ghost:
            valid = ghost.get("valid", True)
            gx, gy = ghost["sx"], ghost["sy"]
            rad = ghost.get("radius", 120)
            col = GOOD if valid else BAD
            pygame.draw.circle(ov, (*col[:3], 90), (int(gx), int(gy)),
                               max(10, int(rad)), 2)
            pygame.draw.circle(ov, (*col[:3], 40), (int(gx), int(gy)),
                               max(10, int(rad)))
            pygame.draw.line(ov, col, (gx - 12, gy), (gx + 12, gy), 2)
            pygame.draw.line(ov, col, (gx, gy - 12), (gx, gy + 12), 2)

    # ------------------------------------------------------------------ minimap
    def _minimap(self, selection: set, local_player: int) -> None:
        ov = self.overlay
        st = self.state
        size = 210
        x, y = self.width - size - 12, self.height - size - 12
        rect = pygame.Rect(x, y, size, size)
        self.minimap_rect = rect
        pygame.draw.rect(ov, (8, 10, 16, 225), rect, border_radius=6)
        pygame.draw.rect(ov, PANEL_EDGE, rect, 1, border_radius=6)
        bounds = max(1.0, getattr(st.map_info, "bounds", 26000.0))
        half = bounds / 2.0
        cx, cy = rect.centerx, rect.centery

        def px(wx, wz):
            return int(cx + wx / half * (size / 2 - 4)), \
                   int(cy + wz / half * (size / 2 - 4))

        for e in st.entities.values():
            if not e.alive:
                continue
            mx, my = px(e.pos.x, e.pos.z)
            if e.is_planet:
                r = max(2, int(e.radius / half * (size / 2)))
                col = (70, 80, 100, 255)
                if e.colonized_by is not None:
                    col = self._owner_rgb(e.colonized_by)
                pygame.draw.circle(ov, col, (mx, my), r, 1 if e.colonized_by is None else 0)
            elif e.owner == -1:
                continue
            else:
                col = self._owner_rgb(e.owner)
                r = 4 if (e.is_station or e.kind == "supercapital") else 2
                if e.is_station:
                    pygame.draw.circle(ov, col, (mx, my), r)
                elif e.is_squadron:
                    pygame.draw.line(ov, col, (mx - r, my), (mx + r, my), 1)
                else:
                    pygame.draw.rect(ov, col, (mx - 2, my - 2, 4, 4))
        for eid in selection:
            e = st.entity(eid)
            if e is not None:
                mx, my = px(e.pos.x, e.pos.z)
                pygame.draw.circle(ov, (255, 255, 255), (mx, my), 5, 1)

    def set_camera_ref(self, camera) -> None:
        self.camera = camera

    def _owner_rgb(self, owner: int):
        p = self.state.players.get(owner)
        if p is None:
            return (150, 150, 150)
        c = p.color
        return (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))

    # ------------------------------------------------------------------ text/bar utils
    def _label(self, x, y, text, color=TXT, font=None):
        surf = (font or self.font).render(str(text), True, color)
        self.overlay.blit(surf, (x, y))

    def _bar(self, x, y, w, h, frac, color, label=None):
        frac = max(0.0, min(1.0, frac))
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.overlay, BAR_BG, rect)
        if frac > 0:
            pygame.draw.rect(self.overlay, color,
                             (x, y, max(2, int(w * frac)), h))
        pygame.draw.rect(self.overlay, (50, 62, 84), rect, 1)
        if label:
            surf = self.font_small.render(label, True, (200, 210, 225))
            self.overlay.blit(surf, (x + 4, y + (h - surf.get_height()) // 2))

    # ------------------------------------------------------------------ GL upload
    def _upload(self) -> None:
        if self.tex is None:
            self.tex = _gl.glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP)
        w, h = self.overlay.get_size()
        data = pygame.image.tostring(self.overlay, "RGBA", False)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA,
                     GL_UNSIGNED_BYTE, data)

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
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()


import OpenGL.GL as _gl  # noqa: E402  (kept at bottom to reuse glGenTextures)