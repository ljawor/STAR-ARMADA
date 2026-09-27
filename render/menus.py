"""Menu stack: starting screen, main menu, settings, campaign briefing.

Pure view — no simulation. Rendered as an SDL surface composited to a GL
quad over a starfield backdrop, same pipeline as HUD.draw_gl(). Own event
pump; main.py swaps stacks on MenuResult transitions.

Persisted settings (saves/settings.json): music/sfx volume, fullscreen,
camera pan speed, autosave toggle.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np
import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(ROOT, "saves", "settings.json")

DEFAULT_SETTINGS = {
    "music_volume": 0.6,
    "sfx_volume": 0.8,
    "fullscreen": False,
    "pan_speed": 1.0,
    "autosave": True,
}


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH) as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict) -> None:
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


class MenuResult:
    """Outcomes the main loop reacts to."""
    NONE = "none"
    START_SKIRMISH = "start_skirmish"
    START_MISSION = "start_mission"     # payload: mission def dict
    EXIT = "exit"


class MenuStack:
    """State machine: splash -> main menu / settings / campaign / briefing."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.screen = "splash"
        self.t = 0.0
        self.result = MenuResult.NONE
        self.result_payload = None
        self.settings = load_settings()
        self._dirty_settings = False
        self._music_preview = False

        pygame.font.init()
        self.font_title = pygame.font.SysFont("helvetica,arial", 64, bold=True)
        self.font_big = pygame.font.SysFont("helvetica,arial", 30, bold=True)
        self.font_med = pygame.font.SysFont("menlo,consolas,monaco", 20)
        self.font_small = pygame.font.SysFont("menlo,consolas,monaco", 15)

        # starfield backdrop (2 parallax layers, drifting)
        rng = np.random.RandomState(42)
        n = 420
        self.stars = np.empty((n, 4), dtype=np.float32)
        self.stars[:, 0] = rng.rand(n) * width          # x
        self.stars[:, 1] = rng.rand(n) * height         # y
        self.stars[:, 2] = 0.25 + rng.rand(n) * 0.75    # depth (speed+alpha)
        self.stars[:, 3] = rng.rand(n)

        self._surface = pygame.Surface((width, height))
        self.overlay_tex = None
        self.buttons: list = []             # current-frame click targets
        self.campaign = self._load_campaign()
        self.selected_mission = 0
        self.mission_index = 0

    # ------------------------------------------------------------- campaign
    def _load_campaign(self) -> dict:
        path = os.path.join(ROOT, "assets", "data", "campaign", "campaign.json")
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"campaign": "Campaign", "missions": []}

    # ------------------------------------------------------------ GL upload
    def draw_gl(self) -> None:
        """Composite the menu surface as a fullscreen GL quad (HUD pattern)."""
        from OpenGL.GL import (glBegin, glBindTexture, glBlendFunc, glColor4f,
                               glDisable, glEnable, glEnd, glMatrixMode,
                               glOrtho, glPopMatrix, glPushMatrix,
                               glLoadIdentity, glTexCoord2f, glTexImage2D,
                               glTexParameteri, glVertex2f, GL_BLEND,
                               GL_DEPTH_TEST, GL_LINEAR, GL_MODELVIEW,
                               GL_ONE_MINUS_SRC_ALPHA, GL_PROJECTION,
                               GL_QUADS, GL_SRC_ALPHA, GL_RGB,
                               GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER,
                               GL_TEXTURE_MIN_FILTER, GL_UNSIGNED_BYTE)
        surf = self._surface
        if self.overlay_tex is None:
            self.overlay_tex = glGenTextures_proxy()
        data = pygame.image.tobytes(surf, "RGB")
        glBindTexture(GL_TEXTURE_2D, self.overlay_tex)
        # filter params REQUIRED on every upload: without them the texture is
        # incomplete and the quad samples white (found via probe bisect)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, surf.get_width(),
                     surf.get_height(), 0, GL_RGB, GL_UNSIGNED_BYTE, data)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1, 1, 1, 1)
        glBegin(GL_QUADS)
        # HUD-matching mapping: t=0 at TOP of the ortho quad (screen-space y
        # grows downward; glOrtho(0,w, h,0) + t=0-top = upright, unmirrored)
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

    # ------------------------------------------------------------- backdrop
    def _draw_backdrop(self) -> None:
        s = self._surface
        s.fill((4, 5, 12))
        # nebula glow blobs (static, cheap)
        for cx, cy, r, col in ((self.width * 0.18, self.height * 0.3, 260, (16, 10, 34)),
                               (self.width * 0.82, self.height * 0.75, 320, (10, 18, 38)),
                               (self.width * 0.6, self.height * 0.15, 180, (24, 12, 30))):
            glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            for i in range(5):
                rr = r * (1.0 - i * 0.18)
                a = 26 + i * 12
                pygame.draw.circle(glow, (*col, a), (r, r), rr)
            s.blit(glow, (cx - r, cy - r))
        # drifting parallax stars
        for star in self.stars:
            star[1] += star[2] * 0.35
            if star[1] > self.height:
                star[1] = 0.0
            b = 90 + int(star[3] * 130)
            sz = 1 if star[2] < 0.7 else 2
            s.fill((b, b, min(255, b + 20)),
                   (int(star[0]), int(star[1]), sz, sz))

    def _panel(self, rect, alpha=200) -> None:
        pygame.draw.rect(self._surface, (10, 14, 26, alpha), rect,
                         border_radius=10)
        pygame.draw.rect(self._surface, (70, 90, 140), rect, 1,
                         border_radius=10)

    def _button(self, rect, label, action, payload=None, hot=False) -> None:
        self.buttons.append({"rect": rect, "action": action,
                             "payload": payload})
        col = (52, 76, 128) if hot else (30, 42, 70)
        pygame.draw.rect(self._surface, col, rect, border_radius=6)
        pygame.draw.rect(self._surface, (120, 150, 210) if hot else (70, 90, 140),
                         rect, 1, border_radius=6)
        f = self.font_med
        surf = f.render(label, True, (220, 230, 255) if hot else (170, 185, 220))
        self._surface.blit(surf, surf.get_rect(center=rect.center))

    def _title(self, text, font, y, col=(235, 240, 255)) -> None:
        surf = font.render(text, True, col)
        self._surface.blit(surf, surf.get_rect(centerx=self.width // 2, y=y))

    # ----------------------------------------------------------- main draw
    def render(self, dt: float) -> None:
        self.t += dt
        self.buttons = []
        self._draw_backdrop()
        if self.screen == "splash":
            self._screen_splash()
        elif self.screen == "main":
            self._screen_main()
        elif self.screen == "settings":
            self._screen_settings()
        elif self.screen == "campaign":
            self._screen_campaign()
        elif self.screen == "briefing":
            self._screen_briefing()

    # --------------------------------------------------------------- screens
    def _screen_splash(self) -> None:
        self._title("STAR", self.font_title, self.height * 0.22)
        self._title("ARMADA", self.font_title, self.height * 0.22 + 74)
        sub = self.font_med.render("FLEET COMMAND", True, (140, 165, 220))
        self._surface.blit(sub, sub.get_rect(centerx=self.width // 2,
                                             y=self.height * 0.22 + 150))
        pulse = 0.55 + 0.45 * math.sin(self.t * 2.2)
        hint = self.font_small.render("click anywhere to begin", True,
                                      (int(150 * pulse + 60), 170, 220))
        self._surface.blit(hint, hint.get_rect(centerx=self.width // 2,
                                               y=self.height * 0.72))
        self.buttons.append({"rect": pygame.Rect(0, 0, self.width, self.height),
                             "action": "goto_main", "payload": None})

    def _screen_main(self) -> None:
        self._title("STAR ARMADA", self.font_title, self.height * 0.14)
        sub = self.font_small.render("Fleet Command — Outer Armada Campaign",
                                     True, (130, 150, 200))
        self._surface.blit(sub, sub.get_rect(centerx=self.width // 2,
                                             y=self.height * 0.14 + 80))
        bw, bh = 340, 52
        x = self.width // 2 - bw // 2
        y0 = self.height * 0.32
        mouse = pygame.mouse.get_pos()
        for i, (label, action) in enumerate((
                ("SKIRMISH", "start_skirmish"),
                ("CAMPAIGN", "goto_campaign"),
                ("SETTINGS", "goto_settings"),
                ("QUIT", "exit"))):
            r = pygame.Rect(x, y0 + i * (bh + 14), bw, bh)
            self._button(r, label, action, hot=r.collidepoint(mouse))

    def _screen_settings(self) -> None:
        self._title("SETTINGS", self.font_big, self.height * 0.08)
        mouse = pygame.mouse.get_pos()
        y0 = self.height * 0.22
        row_h = 64
        bw, bh = 200, 40

        def slider(y, label, key):
            r = pygame.Rect(self.width // 2 - 220, y, 440, 26)
            pygame.draw.rect(self._surface, (22, 30, 50), r, border_radius=4)
            frac = float(self.settings.get(key, 0.7))
            fill = pygame.Rect(r.x, r.y, int(r.w * frac), r.h)
            pygame.draw.rect(self._surface, (70, 110, 190), fill,
                             border_radius=4)
            pygame.draw.rect(self._surface, (90, 120, 180), r, 1,
                             border_radius=4)
            lab = self.font_small.render(label, True, (200, 215, 245))
            self._surface.blit(lab, (r.x, y - 24))
            val = self.font_small.render(f"{int(frac * 100)}%", True,
                                         (150, 175, 220))
            self._surface.blit(val, (r.right + 8, y + 2))
            self.buttons.append({"rect": r, "action": "slider",
                                 "payload": {"key": key, "rect": r}})

        slider(y0, "Music volume", "music_volume")
        slider(y0 + row_h, "SFX volume", "sfx_volume")

        # toggles
        def toggle(y, label, key):
            on = bool(self.settings.get(key))
            r = pygame.Rect(self.width // 2 - 220, y, bw, bh)
            self._button(r, f"{label}: {'ON' if on else 'OFF'}",
                         "toggle", {"key": key},
                         hot=r.collidepoint(mouse))

        toggle(y0 + 2 * row_h, "Fullscreen", "fullscreen")
        toggle(y0 + 2 * row_h + 54, "Autosave", "autosave")

        # pan speed slider too
        slider(y0 + 2 * row_h + 108 + 24, "Camera pan speed", "pan_speed")

        back = pygame.Rect(self.width // 2 - 110, self.height - 90, 220, 48)
        self._button(back, "BACK", "goto_main", hot=back.collidepoint(mouse))

    def _screen_campaign(self) -> None:
        self._title(self.campaign.get("campaign", "CAMPAIGN"),
                    self.font_big, self.height * 0.08)
        missions = self.campaign.get("missions", [])
        mouse = pygame.mouse.get_pos()
        y0 = self.height * 0.20
        if not missions:
            t = self.font_med.render("No missions defined.", True,
                                     (200, 100, 100))
            self._surface.blit(t, (self.width // 2 - 120, y0))
        for i, m in enumerate(missions):
            r = pygame.Rect(self.width // 2 - 260, y0 + i * 58, 520, 48)
            unlocked = i <= self.mission_index
            hot = r.collidepoint(mouse)
            col = (30, 42, 70) if unlocked else (16, 20, 32)
            pygame.draw.rect(self._surface, col, r, border_radius=6)
            pygame.draw.rect(self._surface,
                             (120, 150, 210) if hot else (70, 90, 140),
                             r, 1, border_radius=6)
            num = self.font_med.render(f"{i + 1:02d}", True,
                                       (150, 175, 220) if unlocked
                                       else (90, 100, 120))
            self._surface.blit(num, (r.x + 14, r.y + 12))
            name = self.font_med.render(
                m.get("name", m.get("id", "?")), True,
                (220, 230, 255) if unlocked else (90, 100, 120))
            self._surface.blit(name, (r.x + 64, r.y + 12))
            if unlocked:
                self.buttons.append({"rect": r, "action": "select_mission",
                                     "payload": i})
        back = pygame.Rect(40, self.height - 80, 180, 46)
        self._button(back, "BACK", "goto_main", hot=back.collidepoint(mouse))

    def _screen_briefing(self) -> None:
        missions = self.campaign.get("missions", [])
        if self.selected_mission >= len(missions):
            self.screen = "campaign"
            return
        m = missions[self.selected_mission]
        self._title(m.get("name", "MISSION"), self.font_big,
                    self.height * 0.08)
        y = self.height * 0.18
        px, py, pw = self.width // 2 - 330, y, 660
        # wrapped briefing text — MUST wrap to the panel's inner width, not
        # the window (a wide window made lines overflow the panel border)
        wrap_w = pw - 40
        words = m.get("briefing", "").split()
        lines, cur = [], ""
        for w in words:
            if self.font_med.size(cur + w)[0] > wrap_w:
                lines.append(cur)
                cur = w + " "
            else:
                cur += w + " "
        if cur:
            lines.append(cur)
        # panel wraps briefing text + objectives + enemy line
        n_obj = len(m.get("objectives", []))
        has_enemy = bool(m.get("enemy"))
        panel_h = (34 * max(1, len(lines)) + 60 + 26 + 22 * n_obj
                   + (42 if has_enemy else 10))
        self._panel((px, py, pw, panel_h))
        ty = py + 16
        for ln in lines:
            self._surface.blit(self.font_med.render(ln, True, (205, 218, 245)),
                               (px + 20, ty))
            ty += 30
        # objectives
        oy = ty + 14
        self._surface.blit(self.font_small.render("OBJECTIVES", True,
                                                  (150, 175, 220)),
                           (px + 20, oy))
        oy += 26
        for o in m.get("objectives", []):
            self._surface.blit(self.font_small.render(
                "- " + o.get("text", o.get("type", "?")), True,
                (185, 200, 230)), (px + 34, oy))
            oy += 22
        # enemy + loadout summary
        ey = oy + 18
        enemy = m.get("enemy", {})
        if enemy:
            self._surface.blit(self.font_small.render(
                f"Enemy: {enemy.get('faction', '?')} force", True,
                (220, 160, 140)), (px + 20, ey))
        # buttons
        mouse = pygame.mouse.get_pos()
        bw, bh = 200, 48
        launch = pygame.Rect(self.width - 300, self.height - 90, bw, bh)
        self._button(launch, "LAUNCH", "launch_mission",
                     payload=self.selected_mission,
                     hot=launch.collidepoint(mouse))
        back = pygame.Rect(self.width - 300 - bw - 20, self.height - 90,
                           bw, bh)
        self._button(back, "BACK", "goto_campaign", hot=back.collidepoint(mouse))

    # -------------------------------------------------------------- events
    def handle_event(self, ev) -> None:
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                if self.screen == "splash":
                    self.result = MenuResult.EXIT
                elif self.screen in ("settings", "campaign", "briefing"):
                    self.screen = "main" if self.screen != "briefing" \
                        else "campaign"
                elif self.screen == "main":
                    self.result = MenuResult.EXIT
            return
        if ev.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button != 1:
            return
        pos = ev.pos
        # sliders need drag handling on UP for simplicity: commit on click
        for b in self.buttons:
            if b["rect"].collidepoint(pos):
                act = b["action"]
                if act == "goto_main":
                    self.screen = "main"
                elif act == "goto_campaign":
                    self.screen = "campaign"
                elif act == "goto_settings":
                    self.screen = "settings"
                elif act == "start_skirmish":
                    self.result = MenuResult.START_SKIRMISH
                elif act == "select_mission":
                    self.selected_mission = b["payload"]
                    self.screen = "briefing"
                elif act == "launch_mission":
                    ms = self.campaign.get("missions", [])
                    if self.selected_mission < len(ms):
                        self.result = MenuResult.START_MISSION
                        self.result_payload = ms[self.selected_mission]
                elif act == "exit":
                    self.result = MenuResult.EXIT
                elif act == "toggle":
                    key = b["payload"]["key"]
                    self.settings[key] = not self.settings.get(key)
                    self._dirty_settings = True
                    if key == "fullscreen":
                        self.result = "toggle_fullscreen"
                elif act == "slider":
                    key = b["payload"]["key"]
                    r = b["payload"]["rect"]
                    frac = (pos[0] - r.x) / max(1, r.w)
                    self.settings[key] = round(min(1.0, max(0.0, frac)), 2)
                    self._dirty_settings = True
                return

    def apply_pending(self) -> None:
        if self._dirty_settings:
            save_settings(self.settings)
            self._dirty_settings = False


def glGenTextures_proxy() -> int:
    """glGenTextures via late import (GL context must exist first)."""
    from OpenGL.GL import glGenTextures
    return glGenTextures(1)