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
import sys

import numpy as np
import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Assets are read from the bundle; anything WRITABLE must not be. A frozen app
# lives in /Applications (or runs straight off a read-only DMG), so ROOT is not
# ours to write into — and when it was, every update wiped the user's settings
# and campaign progress. Frozen builds keep user data in Application Support.
ASSET_ROOT = getattr(sys, "_MEIPASS", ROOT)
if getattr(sys, "frozen", False):
    if sys.platform == "darwin":
        USER_DIR = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", "STAR ARMADA")
    elif os.name == "nt":
        USER_DIR = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")), "STAR ARMADA")
    else:
        USER_DIR = os.path.join(
            os.environ.get("XDG_DATA_HOME",
                           os.path.join(os.path.expanduser("~"), ".local", "share")),
            "STAR ARMADA")
else:
    USER_DIR = ROOT

SAVES_DIR = os.path.join(USER_DIR, "saves")
SETTINGS_PATH = os.path.join(SAVES_DIR, "settings.json")
CAMPAIGN_PATH = os.path.join(SAVES_DIR, "campaign.json")

DEFAULT_SETTINGS = {
    "music_volume": 0.6,
    "sfx_volume": 0.8,
    "fullscreen": False,
    "pan_speed": 1.0,
    "autosave": True,
    # Ownership marker verbosity in the 3D view: 'all' | 'hostiles' | 'off'.
    # Read-only view state — never part of the simulation.
    "markers": "all",
    "audio_dynamic_range": "standard",
    "audio_mono": False,
    "cinematics_enabled": True,
    "reduced_motion": False,
    "tutorial_hints": True,
    "high_contrast_ui": False,
}


def validate_presentation_settings(settings: dict) -> dict:
    """Normalize only presentation preferences; retain legacy/mod settings."""
    result = dict(settings) if isinstance(settings, dict) else {}
    for key in ('music_volume', 'sfx_volume', 'pan_speed'):
        value = result.get(key)
        if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
            value = DEFAULT_SETTINGS[key]
        result[key] = min(1.0, max(0.0, value))
    for key in ('fullscreen', 'autosave', 'audio_mono', 'cinematics_enabled',
                'reduced_motion', 'tutorial_hints', 'high_contrast_ui'):
        if type(result.get(key)) is not bool:
            result[key] = DEFAULT_SETTINGS[key]
    if result.get('markers') not in ('all', 'hostiles', 'off'):
        result['markers'] = DEFAULT_SETTINGS['markers']
    if result.get('audio_dynamic_range') not in ('standard', 'night'):
        result['audio_dynamic_range'] = 'standard'
    return result


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH) as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            s.update(saved)
    except (OSError, ValueError):
        pass
    return validate_presentation_settings(s)


def save_settings(s: dict) -> None:
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


# Frozen v1 order: never infer legacy indices from a reordered catalogue.
_LEGACY_MISSION_IDS = (
    'm01_first_fleet', 'm02_supply_line', 'm03_asteroid_war',
    'm04_first_blood', 'm05_the_gate', 'm06_rebel_hunt',
    'm07_fortress_line', 'm08_steel_rain', 'm09_the_conference', 'm10_armada',
)


def _campaign_ids() -> list[str]:
    try:
        # Game data is UTF-8 on every platform: the locale default (cp1252 on
        # Windows) decoded a non-ASCII asset differently there (issue #56).
        with open(os.path.join(ASSET_ROOT, 'assets', 'data', 'campaign', 'campaign.json'),
                  encoding='utf-8') as f:
            return [m['id'] for m in json.load(f)['missions']]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _write_campaign_unlocks(ids: list[str]) -> None:
    try:
        os.makedirs(os.path.dirname(CAMPAIGN_PATH), exist_ok=True)
        with open(CAMPAIGN_PATH, 'w') as f:
            json.dump({'schema_version': 2, 'unlocked_mission_ids': ids}, f, indent=2)
    except OSError:
        pass


def load_campaign_unlocks() -> set[str]:
    """Stable unlock IDs; a missing/corrupt file starts at the tutorial only."""
    catalogue = _campaign_ids()
    initial = catalogue[:1]
    try:
        with open(CAMPAIGN_PATH) as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            return set(initial)
        version = saved.get('schema_version', 1)
        if type(version) is not int or version not in (1, 2):
            return set(initial)
        if version == 2:
            ids = saved.get('unlocked_mission_ids')
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                return set(initial)
            return set(initial + ids)
        index = saved.get('mission_index')
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            return set(initial)
        ids = list(dict.fromkeys(initial + list(_LEGACY_MISSION_IDS[:index + 1])))
        _write_campaign_unlocks(ids)
        return set(ids)
    except (OSError, ValueError, TypeError, AttributeError):
        return set(initial)


def load_campaign_progress() -> int:
    """Compatibility adapter: highest current index of the stable unlock IDs."""
    unlocked = load_campaign_unlocks()
    return max((i for i, mid in enumerate(_campaign_ids()) if mid in unlocked), default=0)


def unlock_campaign_mission(mission_id: str) -> None:
    """Merge one gameplay unlock without replacing stable or unknown mod IDs."""
    unlocked = load_campaign_unlocks()
    if mission_id not in unlocked:
        unlocked.add(mission_id)
        _write_campaign_unlocks(sorted(unlocked))


def save_campaign_progress(index: int) -> None:
    """Compatibility setter; indices refer to the current catalogue, not v1."""
    _write_campaign_unlocks(_campaign_ids()[:max(0, int(index)) + 1])


class MenuResult:
    """Outcomes the main loop reacts to."""
    NONE = "none"
    START_SKIRMISH = "start_skirmish"
    START_MISSION = "start_mission"     # payload: mission def dict
    START_REPLAY = 'start_replay'       # payload: validated replay path
    START_LAN = 'start_lan'             # payload: session; ownership transfers to main
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
        self.mission_index = load_campaign_progress()
        from game.data.store import DataStore
        from game.core.skirmish import default_skirmish_options
        self.skirmish_store = DataStore.get()
        self.skirmish_options = default_skirmish_options(self.skirmish_store)
        self.skirmish_notice = ""
        self.skirmish_text_bounds = []
        self.skirmish_preview_starts = []
        from copy import deepcopy
        self.lan_options = deepcopy(self.skirmish_options)
        self.lan_options.update(human_count=2, ai_count=0, cooperative=False)
        self.lan_port = '7777'
        self.lan_address = '127.0.0.1'
        self.lan_name = 'Player'
        self.lan_focus = None
        self.lan_notice = ''
        self.lan_session = None
        self.replay_paths = []
        self.replay_page = 0
        self.replay_selected = None
        self.replay_confirmation = None
        self.replay_metadata = {}
        self.replay_notice = ''
        self.replay_rows = {}

        # Presentation-only movie resources are opened lazily on the splash.
        self._menu_movie = None
        self._splash_shade = None

    # ------------------------------------------------------------- campaign
    def _load_campaign(self) -> dict:
        path = os.path.join(ASSET_ROOT, "assets", "data", "campaign", "campaign.json")
        try:
            with open(path, encoding='utf-8') as f:
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
        from OpenGL import GL as gl
        matrix_mode = int(gl.glGetIntegerv(gl.GL_MATRIX_MODE))
        gl.glPushAttrib(gl.GL_ENABLE_BIT | gl.GL_COLOR_BUFFER_BIT |
                        gl.GL_TEXTURE_BIT | gl.GL_CURRENT_BIT)
        gl.glDisable(gl.GL_LIGHTING)
        gl.glDisable(gl.GL_CULL_FACE)
        gl.glBlendEquation(gl.GL_FUNC_ADD)
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
        gl.glPopAttrib()
        gl.glMatrixMode(matrix_mode)

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
            if not self.settings.get("reduced_motion", False):
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
        if not self.settings.get("reduced_motion", False):
            self.t += dt
        self.buttons = []
        self._draw_backdrop()
        if self.screen == "splash":
            self._screen_splash()
        elif self.screen == "main":
            self._screen_main()
        elif self.screen == "skirmish":
            self._screen_skirmish()
        elif self.screen == "settings":
            self._screen_settings()
        elif self.screen == "replays":
            self._screen_replays()
        elif self.screen == "campaign":
            self._screen_campaign()
        elif self.screen == "briefing":
            self._screen_briefing()
        elif self.screen == "lan":
            self._title('LAN MULTIPLAYER', self.font_big, 70)
            for i, (label, action) in enumerate((('HOST GAME', 'lan_host_setup'),
                                                ('JOIN GAME', 'lan_join_setup'),
                                                ('BACK', 'goto_main'))):
                self._button(pygame.Rect(self.width // 2 - 170, 170 + i * 66, 340, 48),
                             label, action)

        elif self.screen in ('lan_host', 'lan_join', 'lan_lobby'):
            self._screen_lan()

    # --------------------------------------------------------------- screens
    def _screen_splash(self) -> None:
        self._draw_splash_movie()
        self._title("STAR", self.font_title, self.height * 0.22)
        self._title("ARMADA", self.font_title, self.height * 0.22 + 74)
        sub = self.font_med.render("FLEET COMMAND", True, (140, 165, 220))
        self._surface.blit(sub, sub.get_rect(centerx=self.width // 2,
                                             y=self.height * 0.22 + 150))
        pulse = (1.0 if self.settings.get('reduced_motion', False)
                 else 0.55 + 0.45 * math.sin(self.t * 2.2))
        hint = self.font_small.render("click anywhere to begin", True,
                                      (int(150 * pulse + 60), 170, 220))
        self._surface.blit(hint, hint.get_rect(centerx=self.width // 2,
                                               y=self.height * 0.72))
        self.buttons.append({"rect": pygame.Rect(0, 0, self.width, self.height),
                             "action": "goto_main", "payload": None})

    def _draw_splash_movie(self) -> None:
        """Baked battle playback, isolated from every gameplay/recording object."""
        if not self.settings.get('cinematics_enabled', True):
            return
        if self._menu_movie is None:
            from render.menu_movie import MenuMovie
            self._menu_movie = MenuMovie(os.path.join(ASSET_ROOT, 'assets'))
        if not self._menu_movie.available:
            return
        meta = self._menu_movie.metadata
        scale = max(self.width / meta['width'], self.height / meta['height'])
        size = (math.ceil(meta['width'] * scale), math.ceil(meta['height'] * scale))
        frame = self._menu_movie.get_frame(
            self.t, size, reduced_motion=self.settings.get('reduced_motion', False))
        if frame is None:
            return
        self._surface.blit(frame, ((self.width - size[0]) // 2,
                                   (self.height - size[1]) // 2))
        # Never mutate a decoder-owned cached frame; shade our composition only.
        shade_key = (self.width, self.height, self.settings.get('high_contrast_ui', False))
        if self._splash_shade is None or self._splash_shade[0] != shade_key:
            shade = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            shade.fill((3, 8, 14, 165 if shade_key[2] else 110))
            self._splash_shade = (shade_key, shade)
        self._surface.blit(self._splash_shade[1], (0, 0))

    def _screen_main(self) -> None:
        from render.clean_classic import main_menu
        main_menu(self)

    def skirmish_capacity(self, map_id):
        return len(self.skirmish_store.maps[map_id]['players'])

    def _lan_choice(self, action, value):
        from game.core.skirmish import PLAYER_COLORS
        o = self.lan_options
        capacity = self.skirmish_capacity(o['map_id'])
        if action == 'lan_map':
            o['map_id'] = value
            capacity = self.skirmish_capacity(value)
            o['human_count'] = min(capacity, o['human_count'])
            o['ai_count'] = min(o['ai_count'], capacity - o['human_count'])
        elif action == 'lan_humans':
            o['human_count'] = min(capacity, max(2, o['human_count'] + value))
            o['ai_count'] = min(o['ai_count'], capacity - o['human_count'])
        elif action == 'lan_ai':
            o['ai_count'] = min(2, capacity - o['human_count'], max(0, o['ai_count'] + value))
        elif action == 'lan_color':
            palette = list(PLAYER_COLORS)
            old = o['colors'][value]
            new = palette[(palette.index(old) + 1) % len(palette)]
            for slot, color in enumerate(o['colors']):
                if slot != value and color == new:
                    o['colors'][slot] = old
            o['colors'][value] = new
        elif action in ('lan_faction', 'lan_difficulty'):
            keys = ('imperial', 'rebel', 'confederacy', 'syndicate') if action == 'lan_faction' else ('easy', 'normal', 'hard')
            current = o['factions'][value] if action == 'lan_faction' else o['ai_difficulty']
            new = keys[(keys.index(current) + 1) % len(keys)]
            if action == 'lan_faction':
                o['factions'][value] = new
            else:
                o['ai_difficulty'] = new
        elif action == 'lan_cooperative':
            o['cooperative'] = not o['cooperative']

    def _screen_lan(self):
        """Preserve join/lobby controls; host shares deployment presentation."""
        if self.screen == 'lan_host':
            from render.clean_classic import host_setup
            host_setup(self)
            return
        from game.core.skirmish import SKIRMISH_MAP_IDS, COLOR_NAMES
        target = self._surface
        self._surface = pygame.Surface((800, 600))
        self._surface.fill((6, 9, 19))
        from render.clean_classic import font as classic_font
        font = classic_font(18)
        self.lan_rendered_text = []
        def text(value, x, y, width=744):
            value = str(value)
            self.lan_rendered_text.append(value)
            while font.size(value)[0] > width:
                value = value[:-2] + '…'
            self._surface.blit(font.render(value, True, (210, 222, 246)), (x, y))
        def button(rect, label, action, payload=None):
            rect = pygame.Rect(rect)
            self.buttons.append(dict(rect=rect, action=action, payload=payload))
            pygame.draw.rect(self._surface, (30, 48, 76), rect, border_radius=5)
            text(label, rect.x + 8, rect.y + 7, rect.w - 16)
        text('LAN / ' + self.screen[4:].upper(), 28, 20)
        o = self.lan_options
        if self.screen == 'lan_lobby' and self.lan_session is not None:
            snap = self.lan_session.snapshot
            o = snap.get('options') or self.lan_options
            text(f"{snap.get('status', 'Connecting')} / TCP {snap.get('port', self.lan_port)}", 28, 62)
            text('Host IPs: ' + ', '.join(snap.get('addresses', [])), 28, 92)
            text(f"Map: {o['map_id']} / Humans: {o['human_count']} / AI: {o['ai_count']} / {o['ai_difficulty']}", 28, 126)
            text('Humans vs AI' if o['cooperative'] else 'Free for all', 28, 152)
            players = {p['slot']: p for p in snap.get('players', [])}
            for slot in range(o['human_count']):
                p = players.get(slot)
                text(f"{slot + 1}: " + (f"{p['name']} — {'READY' if p['ready'] else 'NOT READY'}" if p else 'Waiting for player…'), 28, 196 + slot * 42)
            if not snap.get('error'):
                if snap.get('is_host'):
                    button((28, 390, 220, 38), 'EDIT SETUP', 'lan_edit')
                p = players.get(self.lan_session.local_player)
                if p:
                    button((360, 390, 180, 38), 'UNREADY' if p['ready'] else 'READY', 'lan_ready')
                if snap.get('is_host') and snap.get('can_start'):
                    button((550, 390, 196, 38), 'LAUNCH GAME', 'lan_start')
                text('All humans must connect and ready.' if snap.get('is_host') else 'Waiting for host to launch.', 28, 446)
            else:
                button((526, 540, 220, 38), 'RECONNECT', 'lan_reconnect')
        if self.screen in ('lan_host', 'lan_join'):
            for i, (field, label) in enumerate((('lan_name', 'Nickname'), ('lan_port', 'TCP port'))):
                text(label, 28, 398 + i * 44)
                button((164, 390 + i * 44, 300, 36), getattr(self, field) + (' |' if self.lan_focus == field else ''), 'lan_field', field)
            if self.screen == 'lan_join':
                text('Host IPv4 address', 28, 158)
                button((28, 194, 718, 40), self.lan_address + (' |' if self.lan_focus == 'lan_address' else ''), 'lan_field', 'lan_address')
            button((526, 540, 220, 38), 'APPLY SETUP' if self.lan_session is not None else 'HOST' if self.screen == 'lan_host' else 'CONNECT', 'lan_connect')
        text(self.lan_notice, 28, 496)
        button((28, 540, 180, 38), 'BACK / ESC', 'lan_back')
        logical = self._surface
        self._surface = target
        scale = min(self.width / 800, self.height / 600)
        ox, oy = (self.width - round(800 * scale)) // 2, (self.height - round(600 * scale)) // 2
        target.blit(pygame.transform.smoothscale(logical, (round(800 * scale), round(600 * scale))), (ox, oy))
        for b in self.buttons:
            r = b['rect']
            b['rect'] = pygame.Rect(ox + round(r.x * scale), oy + round(r.y * scale), round(r.w * scale), round(r.h * scale))

    def _screen_skirmish(self):
        from render.clean_classic import skirmish_setup
        skirmish_setup(self)

    def open_replays(self):
        """Snapshot bounded directory entries; only visible pages parse files."""
        self.screen = 'replays'
        self.buttons = []
        self.replay_paths = []
        self.replay_rows = {}
        self.replay_metadata = {}
        self.replay_page = 0
        self.replay_selected = None
        self.replay_confirmation = None
        self.replay_notice = ''
        folder = os.path.join(USER_DIR, 'replays')
        try:
            if os.path.islink(folder):
                raise OSError('Refusing symlinked replay directory')
            with os.scandir(folder) as entries:
                for index, entry in enumerate(entries):
                    if index >= 4096:
                        self.replay_notice = 'Scan limit: showing newest 1000 of first 4096 entries. Delete ALL still covers all files.'
                        break
                    if entry.name.endswith('.json') and entry.is_file(follow_symlinks=False):
                        self.replay_paths.append(entry.path)
            from render.replay_library import metadata
            for path in self.replay_paths:
                try:
                    self.replay_metadata[path] = metadata(path)
                except OSError:
                    self.replay_metadata[path] = (0, 'Unknown time / unavailable', {})
            self.replay_paths.sort(key=lambda path: (-self.replay_metadata[path][0], os.path.basename(path)))
            if len(self.replay_paths) > 1000:
                self.replay_paths = self.replay_paths[:1000]
                self.replay_metadata = {path: self.replay_metadata[path] for path in self.replay_paths}
                if not self.replay_notice:
                    self.replay_notice = 'Browser limit: showing newest 1000 replays. Delete ALL still covers all files.'
        except FileNotFoundError:
            self.replay_paths = []
            self.replay_metadata = {}
        except OSError as exc:
            self.replay_paths = []
            self.replay_metadata = {}
            self.replay_notice = 'Cannot browse replays: ' + str(exc)[:180]

    def _screen_replays(self):
        target = self._surface
        self._surface = pygame.Surface((800, 600))
        self._surface.fill((6, 9, 19))
        self.replay_rendered_text = []
        self.replay_text_bounds = []
        def text(value, x, y, width=744):
            value = str(value)
            while value and self.font_small.size(value)[0] > width:
                value = value[:-2] + '…'
            glyph = self.font_small.render(value, True, (205, 220, 245))
            bounds = glyph.get_rect(topleft=(x, y))
            self._surface.blit(glyph, bounds)
            self.replay_text_bounds.append(bounds)
            self.replay_rendered_text.append(value)
        def button(rect, label, action, payload=None):
            rect = pygame.Rect(rect)
            self.buttons.append(dict(rect=rect, action=action, payload=payload))
            pygame.draw.rect(self._surface, (26, 43, 69), rect, border_radius=5)
            text(label, rect.x + 10, rect.y + 9, rect.w - 20)
        text('REPLAYS / READ-ONLY PLAYBACK', 28, 22)
        text('Matches record automatically. P pause / [ ] speed / Esc exit.', 28, 52)
        paths = self.replay_paths[self.replay_page * 6:(self.replay_page + 1) * 6]
        if not paths:
            text('No replays yet. Finish or leave a match to save one.', 28, 126)
        for i, path in enumerate(paths):
            self.replay_rows.setdefault(path, self.replay_metadata[path][1])
            y = 96 + i * 60
            button((28, y, 744, 54), ('> ' if path == self.replay_selected else '') + os.path.basename(path), 'select_replay', path)
            text(self.replay_rows[path], 38, y + 32, 724)
        pages = max(1, (len(self.replay_paths) + 5) // 6)
        text(f'Page {self.replay_page + 1}/{pages} / {len(self.replay_paths)} files / newest first', 28, 452)
        text(self.replay_notice, 28, 475)
        if self.replay_selected:
            button((28, 502, 180, 34), 'PLAY SELECTED', 'play_replay', self.replay_selected)
            button((220, 502, 180, 34), 'DELETE SELECTED', 'replay_delete')
        button((590, 502, 182, 34), 'DELETE ALL REPLAYS', 'replay_delete_all')
        button((28, 540, 136, 38), 'BACK / ESC', 'goto_main')
        button((174, 540, 136, 38), 'REFRESH', 'replay_refresh')
        if self.replay_page:
            button((456, 540, 146, 38), 'PREVIOUS', 'replay_page', -1)
        if self.replay_page + 1 < pages:
            button((612, 540, 160, 38), 'NEXT', 'replay_page', 1)
        if self.replay_confirmation:
            self._surface.fill((6, 9, 19))
            self.buttons = []
            self.replay_text_bounds = []
            self.replay_rendered_text = []
            text('DELETE ALL REPLAYS?' if self.replay_confirmation == 'ALL' else 'DELETE SELECTED REPLAY?', 28, 150)
            text('ALL replay JSON files, including files beyond the browser limit.' if self.replay_confirmation == 'ALL' else os.path.basename(self.replay_confirmation), 28, 200)
            text('Permanent deletion. This cannot be undone.', 28, 250)
            button((28, 320, 270, 42), 'CANCEL / ENTER / ESC', 'replay_cancel_delete')
            button((410, 320, 270, 42), 'DELETE PERMANENTLY', 'replay_confirm_delete')
        logical = self._surface
        self._surface = target
        scale = min(self.width / 800, self.height / 600)
        ox, oy = (self.width - round(800 * scale)) // 2, (self.height - round(600 * scale)) // 2
        target.blit(pygame.transform.smoothscale(logical, (round(800 * scale), round(600 * scale))), (ox, oy))
        def transform(r):
            return pygame.Rect(ox + round(r.x * scale), oy + round(r.y * scale),
                               round(r.w * scale), round(r.h * scale))
        for b in self.buttons:
            b['rect'] = transform(b['rect'])
        self.replay_text_bounds = [transform(r) for r in self.replay_text_bounds]

    def _screen_settings(self) -> None:
        """Three bounded pages, with explicit values and keyboard focus."""
        pages = (
            ('Sound & display', (('Music volume', 'music_volume', 'slider'),
                ('SFX volume', 'sfx_volume', 'slider'), ('Fullscreen', 'fullscreen', 'toggle'),
                ('Autosave', 'autosave', 'toggle'), ('Ownership markers', 'markers', 'cycle_markers'),
                ('Camera pan speed', 'pan_speed', 'slider'))),
            ('Audio & presentation', (('Dynamic range', 'audio_dynamic_range', 'cycle_range'),
                ('Mono audio', 'audio_mono', 'toggle'), ('Cinematics', 'cinematics_enabled', 'toggle'),
                ('Reduced motion', 'reduced_motion', 'toggle'), ('Tutorial hints', 'tutorial_hints', 'toggle'))),
            ('Readability & help', (('High contrast panels', 'high_contrast_ui', 'toggle'),)),
        )
        self.settings_page = min(2, max(0, getattr(self, 'settings_page', 0)))
        self.settings_focus = getattr(self, 'settings_focus', -1)
        self.settings_text_bounds = []
        title, rows = pages[self.settings_page]
        mouse = pygame.mouse.get_pos()
        foreground = (255, 255, 255) if self.settings['high_contrast_ui'] else (220, 230, 255)
        panel = pygame.Rect(self.width // 2 - 330, 112, 660, self.height - 222)
        pygame.draw.rect(self._surface, (0, 0, 0) if self.settings['high_contrast_ui'] else (10, 14, 26), panel)

        def text(label, pos, font=None):
            rendered = (font or self.font_small).render(label, True, foreground)
            bounds = self._surface.blit(rendered, pos)
            self.settings_text_bounds.append((label, bounds))

        text('SETTINGS', (panel.x + 18, 58), self.font_big)
        text(f'{title} - Page {self.settings_page + 1}/3', (panel.x + 18, panel.y + 18), self.font_med)
        for index, (label, key, action) in enumerate(rows):
            y = panel.y + 64 + index * 60
            r = pygame.Rect(panel.x + 18, y, panel.w - 36, 42)
            focused = self.settings_focus == index
            hot = focused or r.collidepoint(mouse)
            pygame.draw.rect(self._surface, (45, 65, 105) if hot else (20, 28, 46), r)
            pygame.draw.rect(self._surface, foreground if focused else (100, 125, 165), r, 2 if focused else 1)
            value = self.settings.get(key)
            if action == 'slider':
                value = min(1.0, max(0.0, float(value)))
                bar = pygame.Rect(r.right - 220, r.y + 16, 140, 10)
                pygame.draw.rect(self._surface, (60, 75, 95), bar)
                pygame.draw.rect(self._surface, (160, 190, 255), (bar.x, bar.y, int(value * bar.w), bar.h))
                text(f'{int(value * 100)}%', (r.right - 65, r.y + 10))
                payload = {'key': key, 'rect': bar}
            else:
                value = ('ON' if value else 'OFF') if action == 'toggle' else str(value).upper()
                text(value, (r.right - 145, r.y + 10))
                payload = {'key': key}
            text(label, (r.x + 12, r.y + 10))
            self.buttons.append({'rect': r, 'action': action, 'payload': payload})
        if self.settings_page == 2:
            for index, line in enumerate(('F1: keyboard and controls help during play.',
                'High contrast applies to help / hint panels only.',
                'Reduced motion disables menu drift and cinematic motion.',
                'Not whole-game scaling or full colorblind compliance.')):
                text(line, (panel.x + 18, panel.y + 142 + index * 30))
        text('Tab/Up/Down: focus  Enter: toggle  Left/Right: volume', (panel.x + 18, panel.bottom - 52))
        text('Page Up/Down: pages  Esc: back', (panel.x + 18, panel.bottom - 28))
        for index, (label, action, payload) in enumerate((('PREVIOUS', 'settings_page', -1),
                ('NEXT', 'settings_page', 1), ('BACK', 'goto_main', None))):
            r = pygame.Rect(panel.x + index * 224, self.height - 90, 212, 48)
            self._button(r, label, action, payload, hot=r.collidepoint(mouse))
            # Include the actual button glyph bounds in diagnostic containment.
            self.settings_text_bounds.append((label, self.font_med.render(label, True, foreground).get_rect(center=r.center)))

    def _settings_key(self, ev) -> bool:
        if ev.type != pygame.KEYDOWN or ev.key == pygame.K_ESCAPE:
            return False
        if ev.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            delta = 1 if ev.key == pygame.K_PAGEDOWN else -1
            self.settings_page = min(2, max(0, getattr(self, 'settings_page', 0) + delta))
            self.settings_focus = -1
            self.buttons = []
            return True
        controls = [b for b in self.buttons if isinstance(b.get('payload'), dict) and 'key' in b['payload']]
        if not controls:
            return True
        focus = getattr(self, 'settings_focus', -1)
        if ev.key in (pygame.K_TAB, pygame.K_UP, pygame.K_DOWN):
            delta = -1 if ev.key == pygame.K_UP or (ev.key == pygame.K_TAB and getattr(ev, 'mod', 0) & pygame.KMOD_SHIFT) else 1
            self.settings_focus = (focus + delta) % len(controls)
        elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_LEFT, pygame.K_RIGHT):
            focus = max(0, min(len(controls) - 1, focus))
            button = controls[focus]
            if button['action'] == 'slider':
                key = button['payload']['key']
                delta = -0.05 if ev.key == pygame.K_LEFT else 0.05
                self.settings[key] = round(min(1, max(0, self.settings[key] + delta)), 2)
                self._dirty_settings = True
            else:
                self.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
        return True

    def _screen_campaign(self) -> None:
        self._title(self.campaign.get("campaign", "CAMPAIGN"),
                    self.font_big, self.height * 0.08)
        missions = self.campaign.get("missions", [])
        mouse = pygame.mouse.get_pos()
        y0 = int(self.height * 0.20)
        page_size = max(1, (self.height - 120 - y0) // 58)
        pages = max(1, (len(missions) + page_size - 1) // page_size)
        self.campaign_page = min(pages - 1, max(0, getattr(self, 'campaign_page', 0)))
        unlocked_ids = load_campaign_unlocks()
        self.campaign_rows = {}
        if not missions:
            t = self.font_med.render("No missions defined.", True,
                                     (200, 100, 100))
            self._surface.blit(t, (self.width // 2 - 120, y0))
        start = self.campaign_page * page_size
        for i in range(start, min(len(missions), start + page_size)):
            m = missions[i]
            r = pygame.Rect(self.width // 2 - 260, y0 + (i - start) * 58, 520, 48)
            self.campaign_rows[m.get('id')] = r
            unlocked = m.get('id') in unlocked_ids
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
        if pages > 1:
            self._title(f'PAGE {self.campaign_page + 1} / {pages}',
                        self.font_small, self.height - 112)
            if self.campaign_page > 0:
                previous = pygame.Rect(self.width - 440, self.height - 80, 180, 46)
                self._button(previous, 'PREVIOUS', 'campaign_page', payload=-1,
                             hot=previous.collidepoint(mouse))
            if self.campaign_page < pages - 1:
                following = pygame.Rect(self.width - 220, self.height - 80, 180, 46)
                self._button(following, 'NEXT', 'campaign_page', payload=1,
                             hot=following.collidepoint(mouse))
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
    def close(self):
        """Release owned networking and GL resources before context teardown."""
        self.close_lan()
        if self._menu_movie is not None:
            self._menu_movie.close()
            self._menu_movie = None
        self._splash_shade = None
        if self.overlay_tex is not None:
            from OpenGL.GL import glDeleteTextures
            glDeleteTextures([self.overlay_tex])
            self.overlay_tex = None

    def close_lan(self):
        if self.lan_session is not None:
            self.lan_session.close()
            self.lan_session = None
        self.lan_focus = None
        self.buttons = []

    def _lan_call(self, method, *args):
        try:
            getattr(self.lan_session, method)(*args)
        except Exception as exc:
            self.lan_notice = str(exc)
            self.close_lan()
            self.screen = 'lan_join'

    def _connect_lan(self):
        from copy import deepcopy
        if self.lan_session is not None:
            try:
                if not self.lan_session.snapshot.get('is_host'):
                    return
                self.lan_session.configure(deepcopy(self.lan_options))
                self.screen = 'lan_lobby'
                self.lan_focus = None
                self.buttons = []
            except Exception as exc:
                self.lan_notice = str(exc)
            return
        if not self.lan_port.isascii() or not self.lan_port.isdecimal() or not 1 <= int(self.lan_port) <= 65535:
            self.lan_notice = 'TCP port must be a number from 1 to 65535.'
            return
        if not self.lan_name.strip() or (self.screen == 'lan_join' and not self.lan_address.strip()):
            self.lan_notice = 'Enter a nickname and host address.'
            return
        try:
            from game.net.lan import LanSession
            self.close_lan()
            port = int(self.lan_port)
            if self.screen == 'lan_host':
                self.lan_session = LanSession.host(port, deepcopy(self.lan_options), name=self.lan_name.strip())
            else:
                self.lan_session = LanSession.join(self.lan_address.strip(), port, name=self.lan_name.strip())
            self.screen = 'lan_lobby'
            self.lan_notice = ''
        except Exception as exc:
            self.lan_notice = str(exc)

    def handle_event(self, ev) -> None:
        if self.screen == 'replays' and self.replay_confirmation and ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.replay_confirmation = None
                self.buttons = []
            return
        if self.screen == 'settings' and self._settings_key(ev):
            return
        if self.screen in ('lan_host', 'lan_join') and self.lan_focus:
            field = self.lan_focus
            if ev.type == pygame.TEXTINPUT:
                value = ev.text
                if field == 'lan_port':
                    value = ''.join(c for c in value if c in '0123456789')
                setattr(self, field, (getattr(self, field) + value)[:5 if field == 'lan_port' else 64])
                return
            if ev.type == pygame.KEYDOWN and ev.key != pygame.K_ESCAPE:
                if ev.key == pygame.K_BACKSPACE:
                    setattr(self, field, getattr(self, field)[:-1])
                elif ev.key == pygame.K_a and getattr(ev, 'mod', 0) & (pygame.KMOD_CTRL | pygame.KMOD_META):
                    setattr(self, field, '')
                elif ev.key == pygame.K_TAB:
                    fields = ['lan_name', 'lan_port'] + (['lan_address'] if self.screen == 'lan_join' else [])
                    self.lan_focus = fields[(fields.index(field) + 1) % len(fields)]
                elif ev.key == pygame.K_RETURN:
                    self._connect_lan()
                return
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                if self.screen.startswith('lan'):
                    self.close_lan()
                    self.screen = 'main' if self.screen == 'lan' else 'lan'
                elif self.screen == "splash":
                    self.result = MenuResult.EXIT
                elif self.screen in ("settings", "campaign", "briefing", "skirmish", "replays"):
                    self.screen = "main" if self.screen != "briefing" \
                        else "campaign"
                elif self.screen == "main":
                    self.result = MenuResult.EXIT
                self.buttons = []
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
                if ev.type == pygame.MOUSEBUTTONUP and act != 'slider':
                    return
                if act == "goto_main":
                    self.screen = "main"
                elif act == 'goto_replays':
                    self.open_replays()
                elif act == 'replay_page':
                    self.replay_page = min(max(0, (len(self.replay_paths) - 1) // 6),
                                           max(0, self.replay_page + b['payload']))
                    self.buttons = []
                elif act == 'replay_refresh':
                    self.open_replays()
                elif act == 'select_replay':
                    self.replay_selected = b['payload']
                    from game.net.replay import load_replay
                    try:
                        data = load_replay(self.replay_selected)
                        duration = (data['end_tick'] - data['initial_state'].get('tick', 0)) / 30
                        detail = (f"{data.get('mode', 'legacy')} / {duration:.1f}s / "
                                  f"game {data.get('game_version', '?')} / format v{data['version']}")
                        if data.get('compatibility_warning'):
                            detail += (' / legacy: duration/content unverified' if data['version'] == 1
                                       else ' / future-state unavailable')
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        detail = 'Cannot play: ' + str(exc)[:180]
                    self.replay_notice = detail
                    self.replay_rows[self.replay_selected] = self.replay_metadata[self.replay_selected][1] + ' / ' + detail
                    self.buttons = []
                elif act == 'replay_delete_all':
                    self.replay_confirmation = 'ALL'
                    self.buttons = []
                elif act == 'replay_delete':
                    if self.replay_selected:
                        self.replay_confirmation = self.replay_selected
                        self.buttons = []
                elif act == 'replay_cancel_delete':
                    self.replay_confirmation = None
                    self.buttons = []
                elif act == 'replay_confirm_delete':
                    path = self.replay_confirmation
                    try:
                        from render.replay_library import delete_selected, delete_all
                        folder = os.path.join(USER_DIR, 'replays')
                        count, failed, error = 1, 0, ''
                        if path == 'ALL':
                            count, failed, error = delete_all(folder)
                        else:
                            delete_selected(folder, path)
                        page = self.replay_page
                        self.open_replays()
                        self.replay_page = min(page, max(0, (len(self.replay_paths) - 1) // 6))
                        self.replay_notice = f'Deleted {count} replay(s).'
                        if failed:
                            self.replay_notice += f' {failed} failed: {error}'
                    except OSError as exc:
                        self.replay_confirmation = None
                        self.buttons = []
                        self.replay_notice = 'Cannot delete replay: ' + str(exc)[:180]
                elif act == 'play_replay':
                    from game.net.replay import load_replay, validate_replay
                    try:
                        validate_replay(load_replay(b['payload']), check_compatibility=True)
                        self.result = MenuResult.START_REPLAY
                        self.result_payload = b['payload']
                        self.buttons = []
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        self.replay_notice = str(exc)[:240]
                elif act == "goto_lan":
                    self.screen = "lan"
                elif act in ('lan_host_setup', 'lan_join_setup'):
                    self.screen = 'lan_host' if act == 'lan_host_setup' else 'lan_join'
                    self.buttons = []
                elif act == 'lan_field':
                    if self.lan_session is None:
                        self.lan_focus = b['payload']
                elif act == 'lan_edit' and self.lan_session is not None:
                    from copy import deepcopy
                    if self.lan_session.snapshot.get('is_host'):
                        self.lan_options = deepcopy(self.lan_session.snapshot['options'])
                        self.screen = 'lan_host'
                        self.buttons = []
                elif act == 'lan_connect':
                    self._connect_lan()
                elif act == 'lan_back':
                    self.close_lan()
                    self.screen = 'lan'
                elif act == 'lan_ready' and self.lan_session is not None:
                    p = next((p for p in self.lan_session.snapshot['players'] if p['slot'] == self.lan_session.local_player), None)
                    if p and not self.lan_session.snapshot.get('error'):
                        self._lan_call('set_ready', not p['ready'])
                    self.buttons = []
                elif act == 'lan_start' and self.lan_session is not None:
                    snap = self.lan_session.snapshot
                    if snap.get('is_host') and snap.get('can_start') and not snap.get('error'):
                        self._lan_call('start')
                    self.buttons = []
                elif act == 'lan_reconnect':
                    host = self.lan_session.snapshot.get('is_host', False)
                    self.close_lan()
                    self.screen = 'lan_host' if host else 'lan_join'
                elif act in ('lan_map', 'lan_humans', 'lan_ai', 'lan_color', 'lan_faction', 'lan_difficulty', 'lan_cooperative'):
                    self._lan_choice(act, b['payload'])
                    if act in ('lan_map', 'lan_humans', 'lan_ai'):
                        self.buttons = []
                elif act == "campaign_page":
                    self.campaign_page = max(0, getattr(self, 'campaign_page', 0) + b['payload'])
                    self.buttons = []
                elif act == "goto_campaign":
                    self.screen = "campaign"
                elif act == "goto_settings":
                    self.screen = "settings"
                elif act == "start_skirmish":
                    self.screen = "skirmish"
                    self.buttons = []
                elif act == "skirmish_map":
                    self.skirmish_options['map_id'] = b['payload']
                    maximum = self.skirmish_capacity(b['payload']) - 1
                    if self.skirmish_options['ai_count'] > maximum:
                        self.skirmish_options['ai_count'] = maximum
                        self.skirmish_notice = f'Map capacity: reduced to {maximum} AI player(s).'
                    else:
                        self.skirmish_notice = ''
                    self.buttons = []
                elif act == "skirmish_ai":
                    options = self.skirmish_options
                    options['ai_count'] = min(self.skirmish_capacity(options['map_id']) - 1,
                                              max(1, options['ai_count'] + b['payload']))
                    from game.core.skirmish import PLAYER_COLORS
                    used = set()
                    for slot in range(options['ai_count'] + 1):
                        color = options['colors'][slot]
                        if color in used:
                            color = next(key for key in PLAYER_COLORS if key not in used)
                            options['colors'][slot] = color
                        used.add(color)
                    self.buttons = []
                elif act == "skirmish_color":
                    from game.core.skirmish import PLAYER_COLORS
                    colors = self.skirmish_options['colors']
                    slot = b['payload']
                    palette = list(PLAYER_COLORS)
                    old = colors[slot]
                    new = palette[(palette.index(old) + 1) % len(palette)]
                    active = self.skirmish_options['ai_count'] + 1
                    for other in range(active):
                        if other != slot and colors[other] == new:
                            colors[other] = old
                            break
                    colors[slot] = new
                elif act == "skirmish_faction":
                    factions = ('imperial', 'rebel', 'confederacy', 'syndicate')
                    slot = b['payload']
                    current = self.skirmish_options['factions'][slot]
                    self.skirmish_options['factions'][slot] = factions[(factions.index(current) + 1) % len(factions)]
                elif act == "skirmish_team":
                    slot = b['payload']
                    teams = self.skirmish_options['teams']
                    teams[slot] = (teams[slot] + 1) % 4
                    self.skirmish_notice = ''
                elif act == "skirmish_difficulty":
                    levels = ('easy', 'normal', 'hard')
                    current = self.skirmish_options['ai_difficulty']
                    self.skirmish_options['ai_difficulty'] = levels[(levels.index(current) + 1) % len(levels)]
                elif act == "launch_skirmish":
                    from copy import deepcopy
                    from game.core.skirmish import build_skirmish_map
                    try:
                        build_skirmish_map(self.skirmish_store, self.skirmish_options)
                    except ValueError as exc:
                        self.skirmish_notice = str(exc)
                        return
                    self.result_payload = deepcopy(self.skirmish_options)
                    self.result = MenuResult.START_SKIRMISH
                    self.buttons = []
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
                elif act == "settings_page":
                    self.settings_page = min(2, max(0, getattr(self, 'settings_page', 0) + b['payload']))
                    self.settings_focus = -1
                    self.buttons = []
                elif act == "cycle_range":
                    self.settings["audio_dynamic_range"] = ("night" if self.settings.get("audio_dynamic_range") == "standard" else "standard")
                    self._dirty_settings = True
                elif act == "cycle_markers":
                    from render.markers import next_mode
                    self.settings["markers"] = next_mode(
                        self.settings.get("markers", "all"))
                    self._dirty_settings = True
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
                if act.startswith('goto_') or act in ('select_mission', 'launch_mission', 'exit'):
                    self.buttons = []
                return

    def apply_pending(self) -> None:
        if self.lan_session is not None:
            try:
                self.lan_session.poll()
                snap = self.lan_session.snapshot
                if snap.get('error'):
                    self.lan_notice = str(snap['error'])
                    self.buttons = []
                elif self.lan_session.launch is not None:
                    self.result = MenuResult.START_LAN
                    self.result_payload = self.lan_session
                    self.lan_session = None
                    self.buttons = []
            except Exception as exc:
                self.lan_notice = str(exc)
                self.close_lan()
                self.screen = 'lan_join'
        if self._dirty_settings:
            save_settings(self.settings)
            self._dirty_settings = False


def glGenTextures_proxy() -> int:
    """glGenTextures via late import (GL context must exist first)."""
    from OpenGL.GL import glGenTextures
    return glGenTextures(1)