"""Menu stack: starting screen, main menu, settings, campaign briefing.

Pure view — no simulation. Rendered as an SDL surface composited to a GL
quad, same pipeline as HUD.draw_gl(). Non-replay menus share the battle movie
backdrop, with a starfield fallback; replay browsing stays static. Own event
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

from render import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Assets are read from the bundle; anything WRITABLE must not be. A frozen app
# lives in /Applications (or runs straight off a read-only DMG), so ROOT is not
# ours to write into — and when it was, every update wiped the user's settings
# and campaign progress. Frozen builds keep user data in Application Support.
def _frozen_asset_root(meipass):
    """The directory that actually owns ``assets`` when running frozen.

    PyInstaller's macOS .app sets ``_MEIPASS`` to ``Contents/Frameworks`` and
    keeps the data in ``Contents/Resources``, exposing it through a symlink
    (``Frameworks/assets -> ../Resources/assets``). The asset resolver refuses any
    path whose realpath leaves its root, so handing it ``Frameworks`` makes it
    reject the bundle's own assets with E_SYMLINK_ESCAPE and the app dies in
    start_game before the first frame. Resolve the real tree and return its
    parent instead. A one-folder build (Windows, or an unpacked mac build) has
    ``assets`` directly inside ``_MEIPASS``, where this is a no-op.
    """
    assets = os.path.realpath(os.path.join(meipass, "assets"))
    if os.path.isdir(assets):
        return os.path.dirname(assets)
    return meipass


_MEIPASS = getattr(sys, "_MEIPASS", None)
ASSET_ROOT = _frozen_asset_root(_MEIPASS) if _MEIPASS is not None else ROOT
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
# Station balance (#106): the same rule as settings and campaign progress. The shipped
# catalogue is inside the bundle and an update replaces it, so anything the player tunes has
# to live here or the next version silently reverts it.
BALANCE_PATH = os.path.join(SAVES_DIR, "balance.json")

DEFAULT_SETTINGS = {
    "music_volume": 0.6,
    "sfx_volume": 0.8,
    "fullscreen": False,
    "resolution": "auto",
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
    # Presentation only: the language selects a pack of drawing strings, and the
    # simulation never reads it, so two peers may ship different languages.
    "language": "en",
    # Render-only selection. S11 switched the production default to the approved
    # Blender catalogue; the legacy procedural renderer stays available as the
    # rollback control and is never deleted by this step.
    "model_preview": True,
    # Which renderer draws the world: 'cpp' (the native window over the W02-W11 bridge) or
    # 'legacy' (the GL renderer this process grew up with). Presentation only - the simulation
    # never reads it, so a LAN match plays the same either way. W11 makes the window the default
    # because that is the migration's whole point; 'legacy' stays as the rollback control and is
    # never deleted by this step.
    "renderer": "cpp",
    # Owner-approved Imperium and Alliance designs are part of the normal game.
    # Enable them here, not through a review-only entry point.
    # Saved selections matching the previous shipped list migrate in load_settings;
    # explicitly customized selections retain their order and choices.
    "visual_packs": [
        "vigil-prototype",
        "imperium-command-prototype",
        "imperium-shipyard-prototype",
        "imperium-mining-prototype",
        "imperium-talon-prototype",
        "imperium-engineer-prototype",
        "imperium-research-prototype",
        "imperium-defense-prototype",
        "imperium-sensor-prototype",
        "imperium-trade-prototype",
        "imperium-fighter-prototype",
        "imperium-repair-prototype",
        "imperium-relay-prototype",
        "imperium-fleet-prototypes",
        "alliance-redesign",
    ],
}

# Freeze historical cohorts: slicing the growing default would lose older migrations.
_SHIPPED_IMPERIUM_13 = (
    'vigil-prototype', 'imperium-command-prototype', 'imperium-shipyard-prototype',
    'imperium-mining-prototype', 'imperium-talon-prototype', 'imperium-engineer-prototype',
    'imperium-research-prototype', 'imperium-defense-prototype', 'imperium-sensor-prototype',
    'imperium-trade-prototype', 'imperium-fighter-prototype', 'imperium-repair-prototype',
    'imperium-relay-prototype',
)
_PREVIOUS_SHIPPED_PACK_LISTS = (
    list(_SHIPPED_IMPERIUM_13),
    [*_SHIPPED_IMPERIUM_13, 'imperium-fleet-prototypes'],
)


# Settings that record *when* a player chose something rather than *what* they chose.
# They live in settings.json beside the preferences but have no row of their own, and
# `DEFAULT_SETTINGS` stays exactly the set of rows a settings page can reach.
BOOKKEEPING_SETTINGS = ('model_preview_explicit',)


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
    # Only normalise the marker when the file actually carries it: a session that never
    # touched the selector must still load exactly DEFAULT_SETTINGS, and that equality is
    # what the settings screens are tested against.
    for key in BOOKKEEPING_SETTINGS:
        if key in result and type(result[key]) is not bool:
            result[key] = False
    if result.get('markers') not in ('all', 'hostiles', 'off'):
        result['markers'] = DEFAULT_SETTINGS['markers']
    if result.get('audio_dynamic_range') not in ('standard', 'night'):
        result['audio_dynamic_range'] = 'standard'
    # A tuple, not a set: an unhashable value in a hand-edited settings.json (a list,
    # say) must be rejected like any other bad value, not crash the loader.
    if result.get('language') not in tuple(code for code, _label in i18n.LANGUAGES):
        result['language'] = DEFAULT_SETTINGS['language']
    from render.display_settings import validate_resolution
    result['resolution'] = validate_resolution(result.get('resolution'))
    from render.asset_selection import selection_preferences
    try:
        result.update(selection_preferences(result))
    except ValueError:
        import warnings
        warnings.warn('Invalid visual pack preferences; using legacy models', RuntimeWarning)
        result.update(model_preview=False, visual_packs=[])
    return result


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    saved = None
    try:
        with open(SETTINGS_PATH) as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            s.update(saved)
    except (OSError, ValueError):
        pass
    # Upgrade either previous shipped Imperium selection, including existing installs.
    # Custom/empty lists are explicit selections and must not be overwritten.
    if (isinstance(saved, dict)
            and saved.get('visual_packs') in _PREVIOUS_SHIPPED_PACK_LISTS):
        s['visual_packs'] = list(DEFAULT_SETTINGS['visual_packs'])
    # The S11 migration. Before the switch every saved file carried
    # `model_preview: false` because that was the default, so the stored value
    # cannot distinguish "chose legacy" from "never chose". Honour the stored
    # value only when the player actually moved the selector; otherwise the new
    # production default applies and the next save records the choice as explicit.
    if not (isinstance(saved, dict) and saved.get("model_preview_explicit") is True):
        s["model_preview"] = DEFAULT_SETTINGS["model_preview"]
    # #160 hard-switched the world renderer: the native window is the only one the game selects,
    # so `legacy` is no longer honoured from a file either. Anything else reads as the default,
    # exactly like a bad volume.
    if s.get("renderer") != "cpp":
        s["renderer"] = DEFAULT_SETTINGS["renderer"]
    return validate_presentation_settings(s)


def save_settings(s: dict) -> None:
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


def load_balance() -> dict:
    """The station balance overlay (#106), normalised. A broken file reads as shipped values.

    Lenient on purpose: this is a file a player may hand-edit, and a station's worth of
    mistyped JSON must not stop the game from starting.
    """
    from game.data import balance
    try:
        with open(BALANCE_PATH, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return balance.defaults()
    return balance.normalize(saved)


def save_balance(config) -> bool:
    """Write the overlay, and install it for the next catalogue. False = refused, unwritten.

    Validated before writing: a config the balance screen could not have produced is a bug
    or a corrupt hand-edit, and persisting it would turn both into a mystery in the next
    match instead of an error here. Nothing is written on refusal — the file on disk stays
    the last good one.
    """
    from game.data import balance
    try:
        clean = balance.validate(config)
    except ValueError:
        return False
    try:
        os.makedirs(os.path.dirname(BALANCE_PATH), exist_ok=True)
        # Explicit UTF-8 both ways, like the campaign and settings files: the locale
        # default is cp1252 on Windows, and a mod's display names are not ours to
        # constrain to ASCII (issue #56's lesson).
        with open(BALANCE_PATH, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=2)
    except (OSError, ValueError):
        return False
    # Installed for later catalogues as well as written: a match started from this menu builds
    # its own catalogue, and the LAN handshake reads the same numbers, so an edit must not
    # need a restart to take effect.
    balance.set_active(clean)
    return True


def load_balance_into_game() -> dict:
    """Read the balance file and install it as the overlay later catalogues pick up."""
    from game.data import balance
    return balance.set_active(load_balance())


def reset_balance() -> None:
    """Forget the tuning: remove the file and go back to the shipped numbers.

    Removing rather than writing a file of shipped values: an absent file and one that
    says nothing must mean the same thing to every reader, and a player who resets has not
    tuned anything — the next build's shipped balance is then genuinely in force.
    """
    from game.data import balance
    try:
        os.remove(BALANCE_PATH)
    except OSError:
        pass                                  # absent is the state we want anyway
    balance.set_active(None)


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


def _write_campaign_progress(unlocked, completed=()) -> None:
    """Schema v3: stable unlock IDs plus the IDs of missions actually won."""
    try:
        os.makedirs(os.path.dirname(CAMPAIGN_PATH), exist_ok=True)
        with open(CAMPAIGN_PATH, 'w') as f:
            json.dump({'schema_version': 3,
                       'unlocked_mission_ids': sorted(unlocked),
                       'completed_mission_ids': sorted(completed)}, f, indent=2)
    except OSError:
        pass


def _campaign_progress() -> tuple[set[str], set[str]]:
    """(unlocked IDs, completed IDs) with the same strictness as v1/v2 loading.

    A missing, unreadable or malformed file yields the tutorial only and is left
    untouched; a valid v1 file is migrated in place (that migration is the one
    documented write-on-read). Completed IDs are additive: v1/v2 files have
    none, so old progress opens with an empty finished set.
    """
    catalogue = _campaign_ids()
    initial = catalogue[:1]
    try:
        with open(CAMPAIGN_PATH) as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            return set(initial), set()
        version = saved.get('schema_version', 1)
        if type(version) is not int or version not in (1, 2, 3):
            return set(initial), set()
        if version in (2, 3):
            ids = saved.get('unlocked_mission_ids')
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                return set(initial), set()
            completed = saved.get('completed_mission_ids', []) if version == 3 else []
            if not isinstance(completed, list) or not all(isinstance(i, str)
                                                          for i in completed):
                return set(initial), set()
            return set(initial + ids), set(completed)
        index = saved.get('mission_index')
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            return set(initial), set()
        ids = list(dict.fromkeys(initial + list(_LEGACY_MISSION_IDS[:index + 1])))
        _write_campaign_progress(ids)
        return set(ids), set()
    except (OSError, ValueError, TypeError, AttributeError):
        return set(initial), set()


def load_campaign_unlocks() -> set[str]:
    """Stable unlock IDs; a missing/corrupt file starts at the tutorial only."""
    return _campaign_progress()[0]


def load_campaign_completed() -> set[str]:
    """IDs of missions the player has won; empty for pre-v3 progress files."""
    return _campaign_progress()[1]


def load_campaign_progress() -> int:
    """Compatibility adapter: highest current index of the stable unlock IDs."""
    unlocked = load_campaign_unlocks()
    return max((i for i, mid in enumerate(_campaign_ids()) if mid in unlocked), default=0)


def unlock_campaign_mission(mission_id: str) -> None:
    """Merge one gameplay unlock without replacing stable or unknown mod IDs."""
    unlocked, completed = _campaign_progress()
    if mission_id not in unlocked:
        unlocked.add(mission_id)
        _write_campaign_progress(sorted(unlocked), completed)


def complete_campaign_mission(mission_id: str | None) -> None:
    """Record a won mission so the campaign screen can mark it COMPLETE.

    Catalogue IDs only: a mod ID or a stale replay mission definition must not
    mint campaign progress. Repeat acknowledgements are idempotent (no rewrite).
    """
    if not isinstance(mission_id, str) or mission_id not in _campaign_ids():
        return
    unlocked, completed = _campaign_progress()
    if mission_id in completed:
        return
    completed.add(mission_id)
    _write_campaign_progress(sorted(unlocked), sorted(completed))


def save_campaign_progress(index: int) -> None:
    """Compatibility setter; indices refer to the current catalogue, not v1."""
    _write_campaign_progress(_campaign_ids()[:max(0, int(index)) + 1],
                             _campaign_progress()[1])


class MenuResult:
    """Outcomes the main loop reacts to."""
    NONE = "none"
    START_SKIRMISH = "start_skirmish"
    START_MISSION = "start_mission"     # payload: mission def dict
    START_REPLAY = 'start_replay'       # payload: validated replay path
    LOAD_GAME = 'load_game'            # payload: selected managed save filepath
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
        # Presentation only: activate the saved pack before the first frame, so a
        # language chosen last session is live in this one.
        i18n.apply_from_settings(self.settings)
        self._dirty_settings = False
        self._music_preview = False
        # #106: the station balance editor works on a draft, and the draft is what gets
        # written. A screen that mutated the live overlay as it drew would half-apply a
        # config the strict reader might have refused whole.
        self.balance_draft = load_balance()
        self.balance_faction = 'imperial'
        self.balance_station = None
        self.balance_page = 0
        self.balance_notice = ''
        self._dirty_balance = False

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

        self.save_paths = []
        self.save_metadata = {}
        self.save_page = 0
        self.save_selected = None
        self.save_confirmation = None
        self.save_notice = ''

        # Presentation-only movie resources open lazily on non-replay menus.
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
        if self.screen != 'replays' and self._draw_splash_movie():
            return
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
        # Drawing edge (#93): every menu button label is looked up here, so a screen
        # is translated without a single call site being touched.
        label = i18n.t(label)
        col = (52, 76, 128) if hot else (30, 42, 70)
        pygame.draw.rect(self._surface, col, rect, border_radius=6)
        pygame.draw.rect(self._surface, (120, 150, 210) if hot else (70, 90, 140),
                         rect, 1, border_radius=6)
        f = self.font_med
        surf = f.render(label, True, (220, 230, 255) if hot else (170, 185, 220))
        self._surface.blit(surf, surf.get_rect(center=rect.center))

    def _title(self, text, font, y, col=(235, 240, 255)) -> None:
        surf = font.render(i18n.t(text), True, col)
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
        elif self.screen == "balance":
            self._screen_balance()
        elif self.screen == "replays":
            self._screen_replays()
        elif self.screen == 'saved_games':
            from render.classic_saves import saved_games
            saved_games(self)
        elif self.screen == "campaign":
            self._screen_campaign()
        elif self.screen == "briefing":
            self._screen_briefing()
        elif self.screen == "lan":
            self._screen_lan_chooser()

        elif self.screen in ('lan_host', 'lan_join', 'lan_lobby'):
            self._screen_lan()

    # --------------------------------------------------------------- screens
    def _screen_splash(self) -> None:
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

    def _draw_splash_movie(self) -> bool:
        """Shared menu battle backdrop; replay browsing stays static."""
        if not self.settings.get('cinematics_enabled', True):
            return False
        if self._menu_movie is None:
            from render.menu_movie import MenuMovie
            self._menu_movie = MenuMovie(os.path.join(ASSET_ROOT, 'assets'))
        if not self._menu_movie.available:
            return False
        meta = self._menu_movie.metadata
        scale = max(self.width / meta['width'], self.height / meta['height'])
        size = (math.ceil(meta['width'] * scale), math.ceil(meta['height'] * scale))
        frame = self._menu_movie.get_frame(
            self.t, size, reduced_motion=self.settings.get('reduced_motion', False))
        if frame is None:
            return False
        self._surface.blit(frame, ((self.width - size[0]) // 2,
                                   (self.height - size[1]) // 2))
        # Never mutate a decoder-owned cached frame; shade our composition only.
        shade_key = (self.width, self.height, self.settings.get('high_contrast_ui', False))
        if self._splash_shade is None or self._splash_shade[0] != shade_key:
            shade = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            shade.fill((3, 8, 14, 165 if shade_key[2] else 110))
            self._splash_shade = (shade_key, shade)
        self._surface.blit(self._splash_shade[1], (0, 0))
        return True

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
        if self.screen == 'lan_host':
            from render.clean_classic import host_setup
            host_setup(self)
        else:
            from render.classic_screens import lan_session
            lan_session(self)

    def _screen_lan_chooser(self):
        from render.classic_screens import lan_chooser
        lan_chooser(self)

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
        from render.classic_replays import replay_library
        replay_library(self)

    def open_saved_games(self):
        from render.save_library import browse
        self.screen = 'saved_games'
        self.buttons = []
        self.save_metadata, self.save_notice = browse(SAVES_DIR)
        self.save_paths = list(self.save_metadata)
        self.save_selected = None
        self.save_page = 0
        self.save_confirmation = None

    def _screen_settings(self) -> None:
        from render.classic_screens import settings
        settings(self)

    def _screen_balance(self) -> None:
        from render.classic_screens import balance
        balance(self)

    def _settings_page_count(self) -> int:
        from render.classic_screens import SETTINGS_PAGE_COUNT
        return SETTINGS_PAGE_COUNT

    def _balance_page_count(self) -> int:
        """Pages the Game Balance editor draws; its tabs carry a page index, not a step."""
        from render.classic_screens import BALANCE_PAGES
        return len(BALANCE_PAGES)

    def balance_summary(self) -> tuple:
        """(station types retuned, hulls gated) in the current draft, for the two screens."""
        from game.data import balance
        return balance.tuned_summary(self.balance_draft, self.skirmish_store.stations)

    # -------------------------------------------------------- station balance (#106)
    def balance_factions(self) -> tuple:
        """Factions that actually field stations, in catalogue order."""
        from game.data import balance
        return tuple(faction for faction in self.skirmish_store.factions
                     if balance.faction_station_types(self.skirmish_store, faction))

    def balance_stations(self) -> tuple:
        """Station types of the selected faction, in catalogue order."""
        from game.data import balance
        return balance.faction_station_types(self.skirmish_store, self.balance_faction)

    def balance_selected(self):
        """The station type the details column describes; falls back to the first listed.

        A selection has to survive a faction change and a screen the player re-enters: the
        alternative is an empty details column that reads as "this faction has no stations".
        """
        stations = self.balance_stations()
        if self.balance_station in stations:
            return self.balance_station
        return stations[0] if stations else None

    def _balance_sync_selection(self) -> None:
        self.balance_station = self.balance_selected()

    def _balance_cycle_faction(self, delta: int) -> None:
        factions = self.balance_factions()
        if not factions:
            return
        index = factions.index(self.balance_faction) if self.balance_faction in factions else 0
        self.balance_faction = factions[(index + delta) % len(factions)]
        self._balance_sync_selection()

    def _balance_gain_step(self, payload) -> None:
        """One stepper press on a per-level gain: edit the draft, never the live overlay."""
        from game.data import balance
        station = self.balance_selected()
        if station is None:
            return
        key = payload['key']
        current = self.balance_draft['station_upgrades'].get(station, {}).get(key)
        if current is None:
            from game.systems import upgrades
            current = upgrades.DEFAULTS[key]
        step = 1 if key in balance.COUNT_KEYS else 0.01
        self.balance_draft = balance.set_gain(self.balance_draft, station, key,
                                             current + step * payload['delta'])
        self._dirty_balance = True
        self.balance_notice = ''

    def _balance_gate_step(self, payload) -> None:
        from game.data import balance
        station, ship_id = payload['station'], payload['ship_id']
        current = self.balance_draft['build_levels'].get(station, {}).get(
            ship_id, balance.DEFAULT_BUILD_LEVEL)
        self.balance_draft = balance.set_build_level(self.balance_draft, station, ship_id,
                                                     current + payload['delta'])
        self._dirty_balance = True
        self.balance_notice = ''

    def _balance_reset_station(self) -> None:
        from game.data import balance
        station = self.balance_selected()
        if station is None:
            return
        self.balance_draft = balance.reset_station(self.balance_draft, station)
        self._dirty_balance = True
        self.balance_notice = i18n.t('{station} is back to the shipped balance.',
                                     station=i18n.name(self.skirmish_store.stations[station].display_name))

    def _balance_reset_all(self) -> None:
        """Reset means "nothing is tuned": the file goes, rather than a file of defaults.

        An absent file and one that says nothing have to mean the same thing to every
        reader, and a player who resets has *not* tuned anything — so the next build's
        shipped balance is genuinely in force, not an overlay that copies it.
        """
        from game.data import balance
        self.balance_draft = balance.defaults()
        self._dirty_balance = False
        reset_balance()
        self.balance_notice = i18n.t('Every station uses the shipped balance again.')

    def _cycle_resolution(self, delta=1) -> None:
        from render.display_settings import available_resolutions, validate_resolution
        choices = available_resolutions(pygame, fullscreen=self.settings.get('fullscreen', False))
        current = validate_resolution(self.settings.get('resolution'))
        index = choices.index(current) if current in choices else 0
        self.settings['resolution'] = choices[(index + delta) % len(choices)]
        self._dirty_settings = True

    def _settings_key(self, ev) -> bool:
        if ev.type != pygame.KEYDOWN or ev.key == pygame.K_ESCAPE:
            return False
        if ev.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            delta = 1 if ev.key == pygame.K_PAGEDOWN else -1
            self.settings_page = min(self._settings_page_count() - 1,
                                     max(0, getattr(self, 'settings_page', 0) + delta))
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
            if button['action'] == 'cycle_resolution':
                self._cycle_resolution(-1 if ev.key == pygame.K_LEFT else 1)
            elif button['action'] == 'slider':
                key = button['payload']['key']
                delta = -0.05 if ev.key == pygame.K_LEFT else 0.05
                self.settings[key] = round(min(1, max(0, self.settings[key] + delta)), 2)
                self._dirty_settings = True
            else:
                self.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button['rect'].center))
        return True

    def _screen_campaign(self) -> None:
        from render.classic_screens import campaign
        campaign(self, load_campaign_unlocks(), load_campaign_completed())

    def _screen_briefing(self) -> None:
        from render.classic_screens import briefing
        briefing(self)

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
            # Enable before either socket is polled: the initial hello must
            # negotiate recovery, never a late gameplay-only opt-in.
            self.lan_session.enable_recovery()
            self.screen = 'lan_lobby'
            self.lan_notice = ''
        except Exception as exc:
            self.close_lan()
            self.lan_notice = str(exc)

    def handle_event(self, ev) -> None:
        if self.screen == 'saved_games' and self.save_confirmation and ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.save_confirmation = None
                self.buttons = []
            return
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
                elif self.screen in ("settings", "campaign", "briefing", "skirmish", "replays", 'saved_games'):
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
                elif act in ('goto_saved_games', 'save_refresh'):
                    self.open_saved_games()
                elif act == 'save_page':
                    self.save_page = min(max(0, (len(self.save_paths) - 1) // 6),
                                         max(0, self.save_page + b['payload']))
                    self.buttons = []
                elif act == 'select_save':
                    if b['payload'] in self.save_metadata:
                        self.save_selected = b['payload']
                    self.buttons = []
                elif act == 'load_save':
                    if self.save_selected and b['payload'] == self.save_selected:
                        self.result = MenuResult.LOAD_GAME
                        self.result_payload = self.save_selected
                        self.buttons = []
                elif act == 'save_delete_all':
                    self.save_confirmation = 'ALL'
                    self.buttons = []
                elif act == 'save_delete':
                    if self.save_selected:
                        self.save_confirmation = self.save_selected
                        self.buttons = []
                elif act == 'save_cancel_delete':
                    self.save_confirmation = None
                    self.buttons = []
                elif act == 'save_confirm_delete':
                    from render.save_library import delete_selected, delete_all
                    path = self.save_confirmation
                    try:
                        count, failed, error = 1, 0, ''
                        if path == 'ALL':
                            count, failed, error = delete_all(SAVES_DIR)
                        else:
                            delete_selected(SAVES_DIR, path)
                        page = self.save_page
                        self.open_saved_games()
                        self.save_page = min(page, max(0, (len(self.save_paths) - 1) // 6))
                        self.save_notice = f'Deleted {count} saved game(s).'
                        if failed:
                            self.save_notice += f' {failed} failed: {error}'
                    except OSError as exc:
                        self.save_confirmation = None
                        self.buttons = []
                        self.save_notice = 'Cannot delete save: ' + str(exc)[:180]
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
                    self.settings_page = min(self._settings_page_count() - 1,
                                             max(0, getattr(self, 'settings_page', 0) + b['payload']))
                    self.settings_focus = -1
                    self.buttons = []
                elif act == "goto_balance":
                    self.screen = "balance"
                    self._balance_sync_selection()
                    self.balance_notice = ''
                    self.buttons = []
                elif act == "balance_back":
                    # Back goes where the door is: the Game Balance page of Settings, which is
                    # how the screen was reached from the menu.
                    self.screen = "settings"
                    self.settings_page = self._settings_page_count() - 1
                    self.buttons = []
                elif act == "balance_faction":
                    self._balance_cycle_faction(b['payload'])
                    self.balance_notice = ''
                    self.buttons = []
                elif act == "balance_station":
                    self.balance_station = b['payload']
                    self.balance_notice = ''
                    self.buttons = []
                elif act == "balance_page":
                    # A tab *names* the page it opens; every other page control in the menus
                    # steps by ±1. Adding this payload is what made "Per-level gains" dead
                    # once "Build levels" was open (#106): the tab was drawn, the press
                    # landed, and the page did not move.
                    self.balance_page = min(self._balance_page_count() - 1,
                                            max(0, int(b['payload'])))
                    self.balance_notice = ''
                    self.buttons = []
                elif act == "balance_step":
                    self._balance_gain_step(b['payload'])
                elif act == "balance_gate_step":
                    self._balance_gate_step(b['payload'])
                elif act == "balance_reset_station":
                    self._balance_reset_station()
                elif act == "balance_reset_all":
                    self._balance_reset_all()
                elif act == "cycle_range":
                    self.settings["audio_dynamic_range"] = ("night" if self.settings.get("audio_dynamic_range") == "standard" else "standard")
                    self._dirty_settings = True
                elif act == "cycle_markers":
                    from render.markers import next_mode
                    self.settings["markers"] = next_mode(
                        self.settings.get("markers", "all"))
                    self._dirty_settings = True
                elif act == "cycle_resolution":
                    self._cycle_resolution()
                elif act == "cycle_language":
                    code = i18n.cycle(str(self.settings.get("language", i18n.DEFAULT_LANGUAGE)))
                    # Apply immediately: the settings row shows the native label of the
                    # pack that is now live, not of the one that was requested.
                    self.settings["language"] = i18n.set_language(code)
                    self._dirty_settings = True
                elif act == "toggle":
                    key = b["payload"]["key"]
                    self.settings[key] = not self.settings.get(key)
                    if key == "model_preview":
                        # Record that this is the player's decision, so the S11
                        # migration can tell it apart from the old default.
                        self.settings["model_preview_explicit"] = True
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
        if self._dirty_balance:
            # Validated before it is written: a draft the strict reader would refuse is a bug
            # in the screen, and saying so beats persisting it and meeting it again as a
            # mystery in the next match.
            from game.data import balance
            if balance.is_default(self.balance_draft):
                # Nothing is tuned, so there is nothing to keep: the file exists exactly when
                # something is tuned, and a reset therefore reaches the shipped numbers.
                reset_balance()
                self._dirty_balance = False
            elif save_balance(self.balance_draft):
                self._dirty_balance = False
            else:
                self.balance_notice = i18n.t('This tuning could not be saved.')


def glGenTextures_proxy() -> int:
    """glGenTextures via late import (GL context must exist first)."""
    from OpenGL.GL import glGenTextures
    return glGenTextures(1)