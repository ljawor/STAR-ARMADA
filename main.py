"""STAR ARMADA — fleet-based real-time space RTS (Armada II spirit, original IP).

Run:
  ./.venv/bin/python main.py                     # menus -> skirmish/campaign
  ./.venv/bin/python main.py --smoke             # automated verification run
  ./.venv/bin/python main.py --skirmish          # skip menus, straight to battle
  ./.venv/bin/python main.py --load saves/autosave.json
  ./.venv/bin/python main.py --mods example      # mod loader (spec §38)

Controls (spec §33):
  LMB click/drag  select / box-select            RMB click  order (attack/move/colonize)
  RMB drag        rotate camera                  wheel      zoom
  WASD/arrows     pan                            F10        toggle mouse grab
  1-9 (+shift)    control groups                 G then 1-9 create fleet
  F               fleet panel (formation / commander)
  BACKSPACE stop · J jump · SPACE follow · M free/follow · Q/E rotate · X overview
  P pause         F5/F9 quicksave/quickload
  ESC             cancel placement/panel, otherwise return to main menu
"""
from __future__ import annotations

import json
import os
import sys

# Dispatch before SDL/audio/menu initialization; frozen Windows GUI builds
# return their report through --output rather than a missing console.
if "--benchmark" in sys.argv:
    from game.benchmark import cli as benchmark_cli
    raise SystemExit(benchmark_cli([arg for arg in sys.argv[1:] if arg != "--benchmark"]))

# Same rule for the LAN diagnostic: no SDL, no window, no assets beyond the
# data store — it must run on a machine where the game itself will not start.
if "--netdiag" in sys.argv:
    from game.net.diag import cli as netdiag_cli
    raise SystemExit(netdiag_cli([arg for arg in sys.argv[1:] if arg != "--netdiag"]))

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402
from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE  # noqa: E402

from game.core.manager import GameManager  # noqa: E402
from game.core.state import GameState  # noqa: E402
from game.data.store import DataStore  # noqa: E402
from render.camera import Camera  # noqa: E402
from render.renderer import Renderer  # noqa: E402
from render.hud import HUD  # noqa: E402
from render.input import InputController  # noqa: E402
from render.audio import Audio  # noqa: E402

from render.menus import (MenuStack, MenuResult,  # noqa: E402
                          load_settings, save_settings, USER_DIR, load_balance_into_game)

from game.net.diagnostics import install_exception_hook
install_exception_hook(USER_DIR, lambda: getattr(globals().get('state'), 'tick', None))

TICK_RATE = 30
TICK_DT = 1.0 / TICK_RATE
# User data follows the same rule as menus.py: a frozen app must never write
# into its own bundle, so this is the same directory the menus persist to.
SAVES_DIR = os.path.join(USER_DIR, "saves")
os.makedirs(SAVES_DIR, exist_ok=True)

# --------------------------------------------------------------------------- args
SMOKE = "--smoke" in sys.argv
SMOKE_TICKS = 900                    # 30 sim-seconds of automated play
SKIP_MENUS = "--skirmish" in sys.argv or SMOKE
INITIAL_LOAD = None
if "--load" in sys.argv:
    INITIAL_LOAD = sys.argv[sys.argv.index("--load") + 1]
MODS: list[str] = []
if "--mods" in sys.argv:
    MODS = [m for m in sys.argv[sys.argv.index("--mods") + 1].split(",") if m]

# Which renderer draws the world. `cpp` hands the frames, HUD and effects to the native window over
# the W02-W11 bridge and draws nothing here; `legacy` is this process's own GL renderer and stays
# available as the rollback control. Python keeps every decision either way - the window is a
# display. Since W11 the choice is a setting (`DEFAULT_SETTINGS["renderer"]`), and `--renderer`
# still overrides it for one launch, because someone debugging a display must be able to pick the
# rollback control without editing a file.
RENDERER = "cpp"
if "--renderer" in sys.argv:
    _index = sys.argv.index("--renderer")
    RENDERER = sys.argv[_index + 1] if _index + 1 < len(sys.argv) else ""
    if RENDERER not in ("legacy", "cpp"):
        raise SystemExit("--renderer takes 'legacy' (default) or 'cpp'")
# Absolute: `USER_DIR` is a relative '.' in a source checkout, so the rings would otherwise land in
# the repository (and a frozen app must never write into its own bundle).
CPP_DIR = os.path.join(os.path.abspath(USER_DIR), "cpp-window")
CPP_HUD_SIZE = (1280, 800)
CPP = {"session": None, "window": None, "input": None, "seen": set(), "seen_tick": -1,
       "selection": frozenset(), "quit": False, "failed": False, "fell_back": False,
       "bridge_mark": (0, 0, 0)}

# --------------------------------------------------------------------------- window
pygame.init()
pygame.display.set_caption("STAR ARMADA — Fleet Command")
if SMOKE and os.environ.get("STAR_ARMADA_FORCE_DUMMY") == "1":
    # CI path: dummy SDL has no OpenGL; use only when a real window is impossible
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.quit()
    pygame.init()
SETTINGS = load_settings()
if "--renderer" not in sys.argv:
    RENDERER = str(SETTINGS.get("renderer") or "cpp")
# Station balance (#106) is installed before the first catalogue exists: every DataStore
# folds the overlay into its rules, so one built earlier would hand the player shipped numbers
# in one place and edited ones in another — and a LAN client would announce the wrong tuning
# before the host could hand it its own.
BALANCE = load_balance_into_game()
SETTINGS.setdefault('cinematics_enabled', True)
SETTINGS.setdefault('reduced_motion', False)
FULLSCREEN = "--fullscreen" in sys.argv or bool(SETTINGS.get("fullscreen"))
_flags = pygame.DOUBLEBUF | pygame.OPENGL
_aa = int(SETTINGS.get("msaa", 4))
if os.environ.get("STAR_ARMADA_MSAA"):
    _aa = int(os.environ["STAR_ARMADA_MSAA"])
if _aa > 1:
    # Request a multisampled backbuffer BEFORE set_mode. The context is
    # OpenGL 2.1 (Apple Metal), which reports SAMPLES=0 on the default
    # context: without this every edge in the game is hard-aliased.
    # 8x is not available on this driver, so 4x is the ceiling.
    try:
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, _aa)
    except Exception:                                    # noqa: BLE001
        _aa = 0                                          # keep running, no AA
if FULLSCREEN:
    _info = pygame.display.Info()
    W, H = _info.current_w, _info.current_h
    _flags |= pygame.FULLSCREEN
else:
    W, H = (1280, 800) if SMOKE else (1440, 900)
screen = pygame.display.set_mode((W, H), _flags)


def toggle_fullscreen() -> None:
    """Switch windowed <-> fullscreen; retarget camera + HUD."""
    global W, H, FULLSCREEN
    FULLSCREEN = not FULLSCREEN
    if FULLSCREEN:
        info = pygame.display.Info()
        W, H = info.current_w, info.current_h
        pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL |
                                pygame.FULLSCREEN)
    else:
        W, H = (1280, 800) if SMOKE else (1440, 900)
        pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
    if camera is not None and hud is not None:
        camera.width, camera.height = W, H
        camera._proj = camera._view = None
        hud.resize(W, H)
    flash("fullscreen ON" if FULLSCREEN else "fullscreen OFF")

# macOS (skill): pump events so the window system is up before any grabbing
for _ in range(10):
    pygame.event.pump()
    pygame.time.wait(50)


# --------------------------------------------------------------------------- game
def make_game(load_path: str | None, mission_def: dict | None = None,
              skirmish_options: dict | None = None):
    # Candidate systems bind a new catalogue singleton during reconstruction.
    # Failed saves must restore even this hidden ownership, including I/O errors.
    previous_store = DataStore._instance
    accepted = False
    try:
        ds = DataStore.reset()
        ds = DataStore(mods=MODS or None)
        map_def = ds.maps["skirmish01"]
        if load_path:
            from render.save_library import managed_name, open_selected, MAX_SAVE_BYTES
            managed = (managed_name(os.path.basename(load_path))
                       and os.path.dirname(os.path.abspath(load_path)) == os.path.abspath(SAVES_DIR))
            with (open_selected(SAVES_DIR, load_path) if managed else open(load_path, 'rb')) as f:
                encoded = f.read(MAX_SAVE_BYTES + 1)
                if len(encoded) > MAX_SAVE_BYTES:
                    raise ValueError('Saved game exceeds size limit (64 MiB)')
                saved = json.loads(encoded)
            try:
                if (not isinstance(saved, dict) or not isinstance(saved.get('players'), dict)
                        or not saved['players'] or not isinstance(saved.get('entities'), dict)):
                    raise ValueError('Not a supported game save')
                if type(saved.get('format', 1)) is not int or saved.get('format', 1) not in (1, 2, 3):
                    raise ValueError('Unsupported saved-game format')
                from game.net.replay_validation import validate_mission, validate_state
                validate_mission(saved.get('mission_state'), ds)
                state = GameState.from_dict(saved)
                manager = GameManager(state=state, mods=MODS or None)
                # Preserve ordinary-save migration/repair, then validate the resulting
                # candidate with the existing typed boundary (including legacy state).
                candidate_state = manager.state.to_dict(precise=True)
                validate_state(candidate_state)
                validate_mission(candidate_state.get('mission_state'), manager.ds)
                accepted = True
                return manager
            except (TypeError, KeyError, AttributeError, IndexError, ZeroDivisionError,
                    OverflowError, RecursionError) as exc:
                raise ValueError('Invalid saved game: ' + str(exc)[:180]) from exc
        if mission_def is not None:
            return GameManager.start_mission(map_def, mission_def, mods=MODS or None)
        if skirmish_options is not None:
            from game.core.skirmish import build_skirmish_map
            map_def = build_skirmish_map(ds, skirmish_options)
        return GameManager.start_skirmish(map_def, mods=MODS or None)
    finally:
        if load_path and not accepted:
            DataStore._instance = previous_store


SETTINGS_PATH = os.path.join(SAVES_DIR, "settings.json")


class _ViewpointAudio(Audio):
    """Keep legacy Audio's positional mixing; resolve outcomes for our slot."""
    def _ev_game_over(self, ev):
        if self._allowed('mission'):
            winner = ev.data.get('winner', self.state.winner)
            won = winner in self.state.allied_player_ids(self.local_player)
            self.play('mission_complete' if won else 'mission_failed', .9)


def make_audio(state) -> Audio:
    a = _ViewpointAudio(state, settings=SETTINGS)
    a.local_player = local_player
    a.start_ambient()
    return a


mode = "menu"                       # "menu" | "game"
menu = MenuStack(W, H)
if SKIP_MENUS:
    mode = "game"

gm = None
state = None
camera = None
renderer = None
hud = None
audio = None
inputc = None
net_session = None
recording = None
playback = None
replay_notice = ""
local_player = 0
paused = False
running = True
flash_msg = ""
flash_until = 0.0
mission_def: dict | None = None
cinematic = None
campaign_outcome_seen = False
presentation = None
recovery_overlay = None


def flash(msg: str) -> None:
    global flash_msg, flash_until
    flash_msg = msg
    flash_until = (state.time if state else 0.0) + 2.5


# --------------------------------------------------------------------------- cpp window
def cpp_session(state, ds, local_player: int):
    """The live producer for this match, started on first use.

    Rings live under the user directory, not the bundle: a frozen app must not write into its own
    package (`menus.py` follows the same rule).
    """
    if CPP["session"] is not None:
        return CPP["session"]
    from render_bridge.live import LiveSession
    from render_bridge import cpp_window
    # The HUD surface size, not the window size: the overlay codec caps a full surface at
    # MAX_PAYLOAD, so the session composes at the size the bridge was measured at and the window
    # presents it. `--overlay-size` in the diagnostic producer is the same figure.
    session = LiveSession(state, ds, directory=CPP_DIR, local_player=local_player,
                          size=CPP_HUD_SIZE, marker_mode="all", camera=camera)
    CPP["session"] = session
    if not SMOKE:
        CPP["window"] = cpp_window.spawn(
            session.paths, root=ROOT, snapshot=os.environ.get("STAR_ARMADA_CPP_SNAPSHOT"),
            log=flash_print)
        if CPP["window"] is not None:
            # The window is the display now. Left in front, this process's own (no longer drawn)
            # surface looks like a game that started and then froze.
            try:
                pygame.display.iconify()
            except Exception:
                pass
    return session


def cpp_trace(message: str) -> None:
    """Diagnostics for the input path, only when asked for: selection is invisible otherwise."""
    if os.environ.get("STAR_ARMADA_CPP_TRACE"):
        print(message, flush=True)


def cpp_drawing() -> bool:
    """True while the native window is actually up and drawing.

    A renderer mode that can silently show nothing is worse than the one it replaces, so when the
    window is not there the caller draws with the legacy path instead of publishing into a void.
    """
    window = CPP["window"]
    return window is not None and window.poll() is None


def flash_print(message: str) -> None:
    print(message, flush=True)


def cpp_seen_ids(state, local_player: int) -> set:
    """What this player can see, refreshed a few times a second.

    `state.can_see` costs ~45 ms p95 over a full fleet (docs/RENDER_BRIDGE_W02.md section 4), so the
    answer is recomputed every 6 ticks instead of every tick: visibility changes on the scale of a
    sensor sweep, not a frame. The window receives the answer; it never derives it.
    """
    if state.tick - CPP["seen_tick"] >= 6:
        CPP["seen"] = {entity.id for entity in state.entities.values()
                       if entity.alive and state.can_see(local_player, entity.id)}
        CPP["seen_tick"] = state.tick
    return CPP["seen"]


def cpp_publish(state, ds, local_player: int, selection, dt: float, *, paused: bool = False,
                message: str = "", flash_left: float = 0.0, fps: float = 0.0,
                drag_box=None, floating_texts=None):
    """Hand one frame to the window: world, cues, effects, fog, HUD, camera. Returns False on fault.

    The window sends its pointer and keyboard back on the input ring, and they enter the same
    `InputController` a native window feeds, so a click builds the same `PlayerCommand` and the
    simulation validates it as usual. That only works while both sides mean the same pixel, which
    is why the camera pose crosses (`ARMCAM01`) and the camera is measured in the window's pixels.
    """
    try:
        session = cpp_session(state, ds, local_player)
        if session is None:
            return False
        if CPP["input"] is None and session.paths["input"].exists():
            from render.input_bridge import RingInput

            class _Traced:
                """Pass-through that writes down what the window sent, when asked to."""

                def __init__(self, inner):
                    self.inner = inner

                def __getattr__(self, name):
                    return getattr(self.inner, name)

                def handle_event(self, ev):
                    if os.environ.get("STAR_ARMADA_CPP_TRACE"):
                        print(f"CPP_EVENT {ev.type} {getattr(ev, 'pos', None)} "
                              f"btn={getattr(ev, 'button', None)} key={getattr(ev, 'key', None)}",
                              flush=True)
                    result = self.inner.handle_event(ev)
                    if os.environ.get("STAR_ARMADA_CPP_TRACE"):
                        print(f"CPP_STATE sel={sorted(self.inner.selection)} "
                              f"drag={self.inner.drag_start} dragging={self.inner.dragging}",
                              flush=True)
                    return result
            # The window's events enter the same controller the keyboard does. One batch per frame:
            # draining a backlog would deliver a press and its release before the game updated, and
            # a held key would be lost.
            target = inputc
            if os.environ.get("STAR_ARMADA_CPP_TRACE"):
                target = _Traced(inputc)
            CPP["input"] = RingInput(session.paths["input"], target, CPP_HUD_SIZE)
        if CPP["input"] is not None:
            CPP["input"].poll(limit=1)
            if CPP["input"].quit_requested:
                CPP["input"].quit_requested = False
                CPP["quit"] = True
        CPP["camera"] = session.camera
        session.publish(state, selection=selection, visible_ids=cpp_seen_ids(state, local_player),
                        dt=dt, paused=paused, message=message, flash_left=flash_left, fps=fps,
                        drag_box=drag_box, floating_texts=floating_texts)
    except Exception as exc:
        # A fault in the producer must not end the match: drop the window and let the legacy path
        # draw from the next frame on.
        CPP["session"] = None
        CPP["failed"] = repr(exc)
        flash_print(f"cpp producer failed ({exc!r}); falling back to the legacy renderer")
        if CPP.get("window") is not None:
            try:
                CPP["window"].terminate()
            except Exception:
                pass
        return False
    return True


def start_game(load_path: str | None = None, mdef: dict | None = None,
               skirmish_options: dict | None = None, lan_session=None,
               replay_path: str | None = None) -> None:
    """Build the full in-game object graph (skirmish, mission, or load)."""
    global gm, state, camera, renderer, hud, audio, inputc, paused, mission_def
    global flash_until
    global net_session, local_player, accumulator, last_autosave
    global recording, playback, replay_notice
    global presentation
    from game.net.replay import MatchRecording, PlaybackSession, load_replay
    candidate = PlaybackSession(load_replay(replay_path)) if replay_path else None
    # Decode and construct the complete manager before ending recording, closing
    # network ownership, or replacing any live graph/resources. Failed saves are inert.
    candidate_gm = (candidate.gm if candidate is not None else
                    GameManager.start_skirmish(lan_session.launch['map_def'], mods=MODS or None)
                    if lan_session is not None else make_game(load_path, mdef, skirmish_options))
    if 'finish_recording' in globals():
        finish_recording()
    playback = candidate
    replay_notice = ''
    paused = False
    if net_session is not None and net_session is not lan_session:
        net_session.close()
    net_session = lan_session
    local_player = int(lan_session.launch['local_player']) if lan_session is not None else 0
    if playback is not None:
        local_player = int(playback._data.get('local_player', 0))
    gm = candidate_gm
    mission_def = gm.mission.mission
    state = gm.state
    state._net_session = lan_session
    recording = None
    if playback is None and 'begin_recording' in globals():
        recording = begin_recording(gm)
    accumulator = 0.0
    last_autosave = state.time
    camera = Camera(W, H)
    _start = next((e for e in state.entities.values()
                   if e.owner == local_player and e.is_station), None)
    if _start is not None:
        camera.target = [_start.pos.x, 0.0, _start.pos.z]
    camera.zoom(0.55)                    # start close-in; wheel out for tactics
    if renderer is not None:
        renderer.close()
    if hud is not None:
        hud.close()
    from render.asset_selection import configure_from_settings
    configure_from_settings(SETTINGS, data_store=gm.ds)
    renderer = Renderer(state, camera)
    renderer.local_player = local_player
    # Ownership-marker verbosity is view-only; Settings owns the value.
    renderer.marker_mode = SETTINGS.get("markers", "all")
    hud = HUD(W, H, state)
    hud.local_player = local_player
    hud.set_camera_ref(camera)
    if audio is not None:
        audio.cleanup()
    audio = make_audio(state)
    audio.local_player = local_player
    audio.set_camera(camera)          # distance attenuation + stereo pan
    if playback is not None:
        from render.replay_input import ReplayInput, configure_replay_hud
        configure_replay_hud(hud)
        inputc = ReplayInput(state, camera, hud, None)
    else:
        inputc = InputController(state, camera, hud, None)
    inputc.local_player = local_player
    inputc.app = _AppGlue()
    from render.presentation import PresentationOverlay
    if globals().get('presentation') is not None:
        presentation.cleanup()
    presentation = PresentationOverlay(W, H, SETTINGS, local_player)
    globals()['cinematic'] = None
    globals()['campaign_outcome_seen'] = False
    if mdef is not None and load_path is None:
        start_campaign_presentation(fresh=True)


def install_recovered_manager(candidate):
    """Validate the drained canonical barrier, prepare, then publish one graph.

    The caller ACKs only after this returns. No tick rewind, new recording or
    mixer restart is permitted. Constructors touch only a private camera.
    """
    global gm, state, camera, renderer, hud, inputc, mission_def
    global accumulator, last_autosave
    from game.net.lan import precise_checksum
    from game.net.replay_validation import validate_state, validate_mission
    if net_session is None or candidate is gm:
        raise ValueError('Recovery requires a detached LAN manager')
    old_gm, old_state = gm, state
    old_renderer, old_hud = renderer, hud
    # Candidate reconstruction may replace the singleton. Live consumers must
    # retain their original catalogue even when preparation/validation fails.
    previous_store = old_gm.ds
    prepared_renderer = prepared_hud = None
    published = False
    try:
        validate_state(candidate.state.to_dict(precise=True))
        validate_mission(candidate.state.mission_state, candidate.ds)
        if (candidate.state.tick != old_state.tick
                or precise_checksum(candidate) != precise_checksum(old_gm)):
            raise ValueError('Recovered manager differs from the drained canonical barrier')
        DataStore._instance = candidate.ds
        prepared_camera = Camera(W, H)
        for name in ('distance', 'yaw', 'pitch', 'fov', 'near', 'far', 'zoom_limits'):
            setattr(prepared_camera, name, getattr(camera, name))
        prepared_camera.target = list(camera.target)
        def retained(eid):
            entity = candidate.state.known_entity(local_player, eid)
            return entity is not None and entity.alive
        prepared_camera.follow_id = camera.follow_id if retained(camera.follow_id) else None
        prepared_hud = HUD(W, H, candidate.state)
        prepared_hud.local_player = local_player
        prepared_hud.set_camera_ref(prepared_camera)
        prepared_input = InputController(candidate.state, prepared_camera, prepared_hud, _AppGlue())
        prepared_input.local_player = local_player
        prepared_input.selection = {eid for eid in inputc.selection if retained(eid)}
        prepared_input.groups = {key: {eid for eid in ids if retained(eid)}
                                 for key, ids in inputc.groups.items()}
        prepared_input.grab_mouse = inputc.grab_mouse
        # Bind renderer last so the camera keeps its animation callback too.
        prepared_renderer = Renderer(candidate.state, prepared_camera)
        prepared_renderer.local_player = local_player
        prepared_renderer.marker_mode = SETTINGS.get('markers', 'all')
        # No remaining preparation can fail after ownership transfer. Undo audio
        # if recorder transfer rejects a malformed/closed recording.
        if audio is not None:
            audio.rebind_state(candidate.state, candidate.ds)
        try:
            if recording is not None:
                recording.rebind_manager(candidate)
        except Exception:
            if audio is not None:
                audio.rebind_state(old_state, old_gm.ds)
            raise
        candidate.state._net_session = net_session
        gm, state, camera, renderer, hud, inputc = (
            candidate, candidate.state, prepared_camera, prepared_renderer,
            prepared_hud, prepared_input)
        mission_def = gm.mission.mission
        accumulator, last_autosave = 0.0, state.time
        old_state._net_session = None
        if audio is not None:
            audio.set_camera(camera)
        published = True
    finally:
        if not published:
            DataStore._instance = previous_store
            if prepared_renderer is not None:
                prepared_renderer.close()
            if prepared_hud is not None:
                prepared_hud.close()
    # Old resources are released only after all live references agree.
    old_renderer.close()
    old_hud.close()


def load_saved_game(path):
    """Main-menu transition; use the existing save factory and full start_game path."""
    global mode
    from render.save_library import selected_name
    try:
        selected_name(SAVES_DIR, path)
        start_game(load_path=path)
    except (OSError, ValueError, RecursionError) as exc:
        menu.screen = 'saved_games'
        menu.buttons = []
        menu.save_notice = 'Cannot load save: ' + str(exc)[:200]
        mode = 'menu'
        return False
    mode = 'game'
    return True


def begin_recording(manager):
    from game.net.replay import MatchRecording
    from render.menus import USER_DIR
    current = MatchRecording(manager,
                             mode='lan' if net_session is not None else 'campaign' if mission_def is not None else 'skirmish',
                             local_player=local_player, mods=MODS)
    current.user_dir = USER_DIR
    return current


def finish_recording():
    """Persist once on match end/leave/rebuild/quit; failure never kills play."""
    global recording, replay_notice
    current = globals().get('recording')
    if current is None:
        return
    recording = None
    current.close()
    import os
    user_dir = getattr(current, 'user_dir', None)
    if user_dir is None:
        from render.menus import USER_DIR
        user_dir = USER_DIR
    from uuid import uuid4
    path = os.path.join(user_dir, 'replays', 'match-' + uuid4().hex + '.json')
    try:
        current.save(path)
        replay_notice = 'Replay saved: ' + os.path.basename(path)
    except (OSError, ValueError) as exc:
        replay_notice = 'Replay could not be saved: ' + str(exc)
    if globals().get('menu') is not None:
        menu.replay_notice = replay_notice
    print(replay_notice)


def rebuild(load_path: str | None) -> None:
    """Full object-graph rebuild for quickload (F9)."""
    if net_session is not None or globals().get('playback') is not None:
        return
    start_game(load_path=load_path, mdef=mission_def)
    flash("game loaded")


def start_campaign_presentation(fresh=False):
    """Intro only for a fresh local campaign; never suspend LAN/replay."""
    global cinematic, campaign_outcome_seen
    from render.cinematics import CampaignCinematic
    cinematic = None
    campaign_outcome_seen = False
    if (fresh and mission_def is not None and net_session is None
            and globals().get('playback') is None
            and SETTINGS.get('cinematics_enabled', True)):
        cinematic = CampaignCinematic(mission_def, camera,
                                     reduced_motion=SETTINGS.get('reduced_motion', False))


def sync_campaign_outcome():
    """Latch the real outcome, persist success independently of skip/settings."""
    global cinematic, campaign_outcome_seen
    from render.cinematics import CampaignCinematic
    if (globals().get('mission_def') is None or net_session is not None
            or globals().get('playback') is not None
            or globals().get('campaign_outcome_seen', False)):
        return
    if not (gm.mission.completed or gm.mission.failed or state.game_over):
        return
    campaign_outcome_seen = True
    won = gm.mission.completed
    if won:
        _unlock_next_mission()
    if SETTINGS.get('cinematics_enabled', True):
        controller = globals().get('inputc')
        if controller is not None:
            controller.keys.clear()
            controller.dragging = False
            controller.drag_start = controller.drag_cur = controller.right_drag = None
        if cinematic is not None:
            cinematic.finish()
        cinematic = CampaignCinematic(mission_def, camera,
            reduced_motion=SETTINGS.get('reduced_motion', False),
            outcome='MISSION COMPLETE' if won else 'MISSION FAILED')


def draw_campaign_presentation(dt_frame):
    """The production world, frozen simulation/FX, with a view-only overlay."""
    global cinematic, accumulator
    accumulator = 0.0
    cinematic.update(dt_frame)
    camera.apply(W, H)
    renderer.placement = None
    renderer.draw(0.0, set())
    cinematic.draw_gl(W, H)
    pygame.display.flip()
    if cinematic.finished:
        outcome = cinematic.outcome
        cinematic = None
        if outcome is not None:
            # A campaign result returns to the campaign screen, not the main menu
            # (#89); the cinematic only ever exists for a campaign mission.
            leave_game(screen='campaign' if mission_def is not None else None)


def lan_recovering():
    return net_session is not None and net_session.snapshot.get('status') == 'recovering'


def drive_lan_recovery():
    """Bounded canonical drain; the session never publishes application state."""
    global accumulator
    accumulator = 0.0
    net_session.recovery_step(gm)
    candidate = net_session.take_restored_manager()
    if candidate is not None:
        install_recovered_manager(candidate)
        net_session.acknowledge_install(candidate)


def advance_simulation(dt_frame):
    """LAN advances at most one barrier per frame; waiting never accrues debt."""
    global accumulator
    if net_session is not None and getattr(net_session, 'snapshot', {}).get('status') == 'recovering':
        drive_lan_recovery()
        return
    if globals().get('cinematic') is not None and net_session is None and globals().get('playback') is None:
        accumulator = 0.0
        return
    if globals().get('playback') is not None:
        playback.advance(dt_frame)
        return
    if paused or state.game_over:
        accumulator = 0.0
        return
    if net_session is not None:
        accumulator += dt_frame
        if accumulator >= TICK_DT:
            # Preserve fractional render time on success, but never retain
            # whole overdue ticks that could cause a later catch-up burst.
            if net_session.advance(gm, TICK_DT):
                accumulator -= TICK_DT
                # A quantized frame may leave one tick (within roundoff):
                # keep it, since the one-step cap delayed legitimate progress.
                # Larger render hitches must not fund a later catch-up burst.
                if accumulator > TICK_DT + 1e-12:
                    accumulator %= TICK_DT
            else:
                # A network barrier wait discards all accumulated time.
                accumulator = 0.0
        return
    accumulator += dt_frame
    while accumulator >= TICK_DT:
        gm.step(TICK_DT)
        accumulator -= TICK_DT
        sync_campaign_outcome()
        if globals().get('cinematic') is not None:
            accumulator = 0.0
            break
        if state.game_over:
            break


def leave_game(reason='', screen=None, *, phase='termination', exception=None):
    """Release match ownership and return to a usable reconnect/menu screen.

    ``screen`` overrides the destination when the caller knows where the player
    came from; the default keeps the LAN/replay/skirmish behaviour unchanged.
    """
    global net_session, mode, paused, accumulator, audio
    global presentation, recovery_overlay
    if globals().get('recovery_overlay') is not None:
        recovery_overlay.cleanup()
        recovery_overlay = None
    if (reason or exception is not None) and net_session is not None and globals().get('USER_DIR') is not None:
        from game.net.diagnostics import record_failure
        record_failure(USER_DIR, phase=phase, tick=getattr(state, 'tick', None),
                       reason=reason, exception=exception)
    if globals().get('presentation') is not None:
        presentation.cleanup()
    presentation = None
    if globals().get('cinematic') is not None:
        cinematic.finish()
        globals()['cinematic'] = None
    finish_recording()
    replaying = globals().get('playback') is not None
    globals()['playback'] = None
    networked = net_session is not None
    if net_session is not None:
        net_session.close()
        net_session = None
    if state is not None:
        state._net_session = None
    if audio is not None:
        audio.cleanup()
        audio = None
    mode, paused, accumulator = 'menu', False, 0.0
    menu.close_lan()
    menu.screen = screen or ('replays' if replaying else 'lan_join' if networked else 'main')
    if replaying:
        menu.open_replays()
        menu.replay_notice = reason
    menu.lan_notice = reason or ('Left LAN game. Host or reconnect to play again.' if networked else '')
    menu.buttons = []


def poll_network():
    if net_session is None:
        return
    try:
        net_session.poll()
        if (net_session.snapshot.get('status') == 'recovering'
                or globals().get('recovery_overlay') is not None):
            sync_recovery_overlay()
        if net_session.snapshot.get('status') == 'error' or net_session.snapshot.get('error'):
            leave_game(str(net_session.snapshot.get('error') or 'LAN session failed.'),
                       phase=net_session.snapshot.get('failure_phase', 'transport'))
    except Exception as exc:
        leave_game(str(exc), phase='transport', exception=exc)


def sync_recovery_overlay():
    """Invalidate pending world gestures once on entry, not every render frame."""
    global recovery_overlay, accumulator
    if lan_recovering():
        accumulator = 0.0
        if globals().get('recovery_overlay') is None:
            from render.recovery_overlay import RecoveryOverlay
            recovery_overlay = RecoveryOverlay(W, H)
            inputc.keys.clear()
            inputc.dragging = False
            inputc.drag_start = inputc.drag_cur = inputc.right_drag = None
            inputc._pending_fleet = inputc._pending_jump = inputc._pending_ability = None
            inputc._menu_armed = False
            hud.placement = None
    elif globals().get('recovery_overlay') is not None:
        recovery_overlay.cleanup()
        recovery_overlay = None


def draw_recovery_overlay():
    sync_recovery_overlay()
    if recovery_overlay is not None:
        recovery_overlay.draw(net_session.recovery_snapshot, width=W, height=H)
        recovery_overlay.draw_gl()


def handle_recovery_event(ev):
    """Consume all world input during recovery; allow only view-safe controls."""
    if not lan_recovering():
        return False
    sync_recovery_overlay()
    if recovery_overlay.handle_event(ev):
        net_session.abort_recovery()
        leave_game('Reconnect cancelled. You left the LAN match.')
        return True
    view_keys = {pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
                 pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d,
                 pygame.K_q, pygame.K_e}
    if ev.type in (pygame.KEYDOWN, pygame.KEYUP) and ev.key in view_keys:
        if ev.type == pygame.KEYDOWN:
            inputc.keys.add(ev.key)
        else:
            inputc.keys.discard(ev.key)
    elif ev.type == pygame.WINDOWFOCUSLOST:
        inputc.keys.clear()
    elif ev.type == pygame.MOUSEWHEEL:
        camera.zoom(0.88 ** ev.y)
    return True


def handle_game_input(ev):
    if net_session is not None and getattr(net_session, 'snapshot', {}).get('status') == 'recovering':
        handle_recovery_event(ev)
        return
    if globals().get('playback') is not None and ev.type == pygame.KEYDOWN:
        if ev.key == pygame.K_ESCAPE:
            leave_game()
            return
        if ev.key == pygame.K_p:
            if not getattr(ev, 'repeat', False):
                playback.paused = not playback.paused
            return
        if ev.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
            if not getattr(ev, 'repeat', False):
                playback.change_speed(-1 if ev.key == pygame.K_LEFTBRACKET else 1)
            return
        if ev.key in (pygame.K_F5, pygame.K_F9):
            return
    from game.net.lan import LocalSubmissionRejected
    try:
        inputc.handle_event(ev)
    except LocalSubmissionRejected as exc:
        flash(str(exc))
    except Exception as exc:
        if net_session is None and globals().get('playback') is None:
            raise
        leave_game(str(exc), phase='input', exception=exc)


def step_game_frame(dt_frame):
    """Actual main simulation exception boundary, shared with focused probes."""
    try:
        advance_simulation(dt_frame)
    except Exception as exc:
        if net_session is None and globals().get('playback') is None:
            raise
        leave_game(str(exc), phase='simulation', exception=exc)
        return False
    return True


def handle_presentation_input(ev):
    """Help is view-only and modal for input, never a LAN pause."""
    overlay = globals().get('presentation')
    if overlay is None:
        return False
    was_open = overlay.help_visible
    consumed = overlay.handle_event(ev)
    if overlay.help_visible != was_open:
        inputc.keys.clear()
        inputc.dragging = False
        inputc.drag_start = inputc.drag_cur = inputc.right_drag = None
        inputc._pending_fleet = None
        inputc._cancel_jump()
        inputc._cancel_ability()
        hud_view = globals().get('hud')
        if hud_view is not None:
            hud_view.placement = None
    elif consumed and ev.type == pygame.MOUSEBUTTONUP:
        # End only the intercepted gesture, without selecting or issuing orders.
        if ev.button == 1:
            inputc.dragging = False
            inputc.drag_start = inputc.drag_cur = None
        elif ev.button == 3:
            inputc.right_drag = None
    return consumed


def draw_presentation_overlay():
    overlay = globals().get('presentation')
    if overlay is not None:
        overlay.draw(state, inputc, width=W, height=H, local_player=local_player,
                     blocked_rects=hud.blocked_rects)
        overlay.draw_gl()
        hud.blocked_rects.extend(overlay.panel_rects)


def handle_network_event(ev):
    """LAN-only keys. #69: Escape is NOT swallowed here — a networked player
    cancels the current operation and leaves the match with the same rule as a
    local one, so a single press cannot drop them out mid-order."""
    if net_session is None or ev.type != pygame.KEYDOWN:
        return False
    if ev.key in (pygame.K_p, pygame.K_F5, pygame.K_F9):
        flash('Pause/save/load are disabled in LAN games.')
        return True
    return False


def escape_from_decided_match() -> bool:
    """A decided match: one Escape returns to the previous screen. True if handled.

    #69 keeps a single Escape as the abort key during play, but once the result
    is on screen the player is acknowledging an outcome, not cancelling an
    order, so one press is enough there.
    """
    global campaign_outcome_seen, mode
    if not (state.game_over or (mission_def is not None
                                and (gm.mission.completed or gm.mission.failed))):
        return False
    # campaign result: persist progress before menus
    if (mission_def is not None and gm.mission.completed
            and not globals().get('campaign_outcome_seen', False)):
        _unlock_next_mission()
        campaign_outcome_seen = True
    if 'finish_recording' in globals():
        finish_recording()
    if net_session is not None:
        # a decided LAN match still owns a live session: release it properly
        leave_game('Match finished.')
    else:
        mode = "menu"       # campaign result -> back to the previous screen
        if mission_def is not None:
            # campaign result (cinematics disabled): the campaign screen is the
            # screen the player deployed from, not the main menu (#89)
            menu.screen = 'campaign'
            menu.buttons = []
    return True


def _unlock_next_mission() -> None:
    """Mission completed: mark it finished and unlock the next mission (persisted)."""
    from render.menus import complete_campaign_mission, unlock_campaign_mission
    if mission_def is None or globals().get('playback') is not None:
        return
    complete_campaign_mission(mission_def.get('id'))
    ids = [m.get("id") for m in menu.campaign.get("missions", [])]
    try:
        idx = ids.index(mission_def.get("id"))
    except ValueError:
        return
    if idx + 1 < len(ids):
        unlock_campaign_mission(ids[idx + 1])


def write_save(path: str) -> None:
    """Persist a snapshot. Never fatal: a read-only location must not crash."""
    if net_session is not None or globals().get('playback') is not None:
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state.to_dict(), f)
    except OSError as exc:
        print(f"WARN: could not write save {path}: {exc}")


def take_screenshot(path: str) -> None:
    data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(data, (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        pygame.image.save(img, path)
    except (OSError, pygame.error) as exc:
        # a screenshot must never take the app down
        print(f"WARN: could not save screenshot {path}: {exc}")


def summary() -> str:
    counts: dict[int, int] = {}
    for e in state.entities.values():
        if e.alive and e.owner >= 0:
            counts[e.owner] = counts.get(e.owner, 0) + 1
    p0 = state.players.get(0)
    p1 = state.players.get(1)
    return (f"t={state.time:0.0f}s winner={state.winner} "
            f"entities={counts} "
            f"P0(cr={p0.credits:0.0f} mt={p0.materials:0.0f} "
            f"techs={len(p0.researched)}) "
            f"P1(cr={p1.credits:0.0f} techs={len(p1.researched)})")


class _AppGlue:
    """Adapter so InputController can talk back without circular imports."""

    @staticmethod
    def request_exit() -> None:
        leave_game()

    @staticmethod
    def toggle_pause() -> None:
        global paused
        if net_session is None:
            paused = not paused

    @staticmethod
    def flash(msg: str) -> None:
        flash(msg)


if SKIP_MENUS:
    start_game(load_path=INITIAL_LOAD)

# --------------------------------------------------------------------------- loop
clock = pygame.time.Clock()
accumulator = 0.0
frames = 0
fps = 0.0
fps_time = 0.0
last_autosave = 0.0

while running:
    dt_frame = min(clock.tick(TICK_RATE) / 1000.0, 0.25)

    if mode == "menu":
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                break
            menu.handle_event(ev)
            if menu.result == "toggle_fullscreen":
                menu.result = MenuResult.NONE
                toggle_fullscreen()
        menu.apply_pending()
        SETTINGS.update(menu.settings)
        if audio is not None:
            audio.apply_settings(SETTINGS)
        menu.render(dt_frame)
        menu.draw_gl()
        pygame.display.flip()
        if menu.result != MenuResult.NONE:
            res, payload = menu.result, menu.result_payload
            menu.result = MenuResult.NONE
            menu.result_payload = None
            if res == MenuResult.EXIT:
                running = False
            elif res == MenuResult.START_SKIRMISH:
                save_settings(SETTINGS)
                start_game(load_path=None, skirmish_options=payload)
                mode = "game"
            elif res == MenuResult.START_MISSION:
                save_settings(SETTINGS)
                start_game(load_path=None, mdef=payload)
                mode = "game"
            elif res == MenuResult.START_REPLAY:
                try:
                    start_game(replay_path=payload)
                    mode = 'game'
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    menu.open_replays()
                    menu.replay_notice = str(exc)[:240]
                    mode = 'menu'
            elif res == MenuResult.LOAD_GAME:
                load_saved_game(payload)
            elif res == MenuResult.START_LAN:
                try:
                    start_game(lan_session=payload)
                    mode = 'game'
                except Exception as exc:
                    payload.close()
                    leave_game(str(exc))
        continue

    # ---- game mode
    poll_network()
    if mode != 'game':
        continue
    if CPP.get("quit"):
        # The native window was closed: leave the match the way Escape would, not by dying.
        CPP["quit"] = False
        leave_game()
        continue
    sync_campaign_outcome()
    presentation_frame = cinematic is not None
    help_frame = presentation is not None and presentation.help_visible
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            running = False
            break
        if handle_recovery_event(ev):
            if mode != 'game':
                break
            continue
        if presentation_frame:
            cinematic.handle_event(ev)
            continue
        if handle_presentation_input(ev):
            help_frame = help_frame or presentation.help_visible
            continue
        if help_frame:
            continue
        if ev.type == pygame.KEYDOWN:
            if playback is not None and ev.key != pygame.K_F11:
                handle_game_input(ev)
                if mode != 'game':
                    break
                continue
            if handle_network_event(ev):
                if mode != 'game':
                    break
                continue
            if ev.key == pygame.K_F5:
                write_save(os.path.join(SAVES_DIR, "quicksave.json"))
                flash("quicksaved")
                continue
            if ev.key == pygame.K_F9:
                rebuild(os.path.join(SAVES_DIR, "quicksave.json"))
                continue
            if ev.key == pygame.K_F11 and not SMOKE:
                toggle_fullscreen()
                continue
            if ev.key == pygame.K_ESCAPE and escape_from_decided_match():
                continue
        handle_game_input(ev)
        if mode != 'game':
            break

    if mode != 'game' or not running:
        continue
    if presentation_frame:
        draw_campaign_presentation(dt_frame)
        continue
    if not step_game_frame(dt_frame):
        continue

    sync_campaign_outcome()
    if cinematic is not None:
        draw_campaign_presentation(dt_frame)
        continue

    if playback is None and state.game_over:
        finish_recording()
    inputc.update(dt_frame)
    if not lan_recovering():
        inputc.update_placement()

    # mission progress -> HUD panel
    if mission_def is not None:
        hud.mission_progress = gm.mission.progress_text()
        hud.mission_name = mission_def.get("name", "MISSION")
        hud.mission_done = gm.mission.completed
        hud.mission_failed = gm.mission.failed
    else:
        hud.mission_progress = None

    # ---- what the HUD is told
    # One place decides it, so the window and the legacy path cannot disagree about whether the
    # match is paused, what the status line says, or where the drag box is. The window used to
    # compose the HUD with `paused=False, message=''` unconditionally, which is why a paused match
    # looked like a running one.
    flash_left = flash_until - state.time
    view_msg = flash_msg
    view_paused = paused
    if playback is not None:
        view_paused = playback.paused
        status = 'ENDED' if playback.ended else 'PAUSED' if playback.paused else 'PLAYING'
        elapsed = (state.tick - playback._data['initial_state'].get('tick', 0)) / TICK_RATE
        duration = (playback.end_tick - playback._data['initial_state'].get('tick', 0)) / TICK_RATE
        view_msg = f'REPLAY {status} {elapsed:.1f}/{duration:.1f}s {playback.speed:g}x | P pause [ ] speed Esc exit'
        flash_left = 1.
    elif replay_notice:
        view_msg, flash_left = replay_notice, 1.
    view_flash = max(0.0, flash_left)
    view_drag = (inputc.drag_start, inputc.drag_cur)
    # Floating texts are projected from the *game's* camera and handed over as finished pixels.
    view_texts = renderer.floating_texts_screen() if renderer is not None else []

    # ---- draw
    # In `cpp` mode the producer runs whether or not a window is up (the smoke run has no window and
    # still exercises every ring); the legacy path draws only when the window is not doing it.
    if RENDERER == "cpp" and not CPP.get("failed") and (SMOKE or CPP["session"] is None
                                                        or cpp_drawing()):
        # `apply` also sets the camera's pixel size, and that size is what turns a click into a
        # world ray. The view surface in this mode is the window (CPP_HUD_SIZE = the size the HUD is
        # composed at and the window draws at), not the hidden SDL window (2560x1440 here) - a
        # camera left at the SDL size put every pick at half the pointer's x and 0.55x its y.
        camera.apply(*CPP_HUD_SIZE)
        cpp_publish(state, gm.ds, local_player, inputc.selection, dt_frame,
                    paused=view_paused, message=view_msg, flash_left=view_flash, fps=fps,
                    drag_box=view_drag, floating_texts=view_texts)
        if os.environ.get("STAR_ARMADA_CPP_TRACE"):
            marker = (view_paused, view_msg, len(view_texts), view_drag)
            if marker != CPP.get("view_mark"):
                CPP["view_mark"] = marker
                cpp_trace(f"CPP_VIEW paused={view_paused} msg={view_msg!r} "
                          f"texts={len(view_texts)} drag={view_drag}")
        if SMOKE or cpp_drawing():
            # Nothing is drawn into this process's GL context: the window is the display, and the HUD
            # is composed by the same `render.hud` code (design A) inside the session, so text stays
            # SDL_ttf. The loop tail (autosave, smoke exit, fps counter) runs as in legacy mode.
            if not SMOKE:
                pygame.event.pump()
            frames += 1
            fps_time += dt_frame
            if fps_time >= 1.0:
                fps = frames / fps_time
                frames = 0
                fps_time = 0.0
            if CPP["input"] is not None:
                bridge = CPP["input"]
                marker = (bridge.batches_read, bridge.events_delivered, bridge.unmapped)
                if marker != CPP["bridge_mark"]:
                    CPP["bridge_mark"] = marker
                    cpp_trace(f"CPP_INPUT batches={bridge.batches_read} events={bridge.events_delivered} "
                              f"unmapped={bridge.unmapped} skipped={bridge.batches_skipped}")
            current = frozenset(inputc.selection)
            if current != CPP["selection"]:
                CPP["selection"] = current
                cpp_trace(f"CPP_SELECTION {sorted(current)}")
            if SMOKE and state.tick >= SMOKE_TICKS:
                print("SMOKE_CPP_OK " + summary())
                if CPP["session"] is not None:
                    print("SMOKE_CPP_COST " + json.dumps(CPP["session"].report(), default=str))
                raise SystemExit(0)
            continue

    if RENDERER == "cpp" and not CPP.get("fell_back"):
        # The window is gone (killed, crashed, or it never started). Say it once and draw the match
        # here: a player who launched a skirmish must never be left looking at a frozen menu.
        CPP["fell_back"] = True
        flash_print("cpp window is not drawing; falling back to the legacy renderer")
        try:
            pygame.display.set_mode((W, H))
        except Exception:
            pass

    camera.apply(W, H)
    renderer.placement = hud.placement  # render-side preview only; never sim state
    renderer.draw(dt_frame, inputc.selection)
    hud.set_floating_texts(view_texts)
    # live box-select rectangle while left-dragging
    hud.set_drag_box(*view_drag)
    hud.render(inputc.selection, None, local_player, view_paused, view_msg,
               view_flash, fps)
    hud.draw_gl()
    draw_presentation_overlay()
    draw_recovery_overlay()
    pygame.display.flip()

    frames += 1
    fps_time += dt_frame
    if fps_time >= 1.0:
        fps = frames / fps_time
        frames = 0
        fps_time = 0.0

    # autosave ring every 60 sim-seconds (spec §32): 3 rotating slots
    if playback is None and net_session is None and not state.game_over and state.time - last_autosave >= 60.0:
        ring = int(SETTINGS.get("autosave_index", 0)) % 3
        write_save(os.path.join(SAVES_DIR, f"autosave_{ring}.json"))
        SETTINGS["autosave_index"] = ring + 1
        last_autosave = state.time

    # smoke-mode exit: capture proof and stop
    if SMOKE and state.tick >= SMOKE_TICKS:
        shot = os.path.join(SAVES_DIR, "smoke_screenshot.png")
        take_screenshot(shot)
        print("SMOKE_OK " + summary() + " shot=" + shot)
        running = False

if 'finish_recording' in globals():
    finish_recording()
menu.close()
if recovery_overlay is not None:
    recovery_overlay.cleanup()
if net_session is not None:
    net_session.close()
if audio is not None:
    audio.cleanup()
else:
    # pygame.init() opens a mixer even while sitting in the menus, so there is
    # still a device to release when no game was ever started.
    pygame.mixer.quit()
save_settings(SETTINGS)
if renderer is not None:
    renderer.close()
if hud is not None:
    hud.close()
if presentation is not None:
    presentation.cleanup()
pygame.quit()
if SMOKE and state is not None:
    print("SMOKE_DONE " + summary())