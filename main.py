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
                          load_settings, save_settings, USER_DIR)

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
    ds = DataStore.reset()
    ds = DataStore(mods=MODS or None)
    map_def = ds.maps["skirmish01"]
    if load_path:
        with open(load_path) as f:
            saved = json.load(f)
        state = GameState.from_dict(saved)
        return GameManager(state=state, mods=MODS or None)
    if mission_def is not None:
        return GameManager.start_mission(map_def, mission_def, mods=MODS or None)
    if skirmish_options is not None:
        from game.core.skirmish import build_skirmish_map
        map_def = build_skirmish_map(ds, skirmish_options)
    return GameManager.start_skirmish(map_def, mods=MODS or None)


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


def flash(msg: str) -> None:
    global flash_msg, flash_until
    flash_msg = msg
    flash_until = (state.time if state else 0.0) + 2.5


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
        gm = playback.gm
        local_player = int(playback._data.get('local_player', 0))
    elif lan_session is not None:
        gm = GameManager.start_skirmish(lan_session.launch['map_def'], mods=MODS or None)
    else:
        gm = make_game(load_path, mdef, skirmish_options)
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
            leave_game()


def advance_simulation(dt_frame):
    """LAN advances at most one barrier per frame; waiting never accrues debt."""
    global accumulator
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


def leave_game(reason=''):
    """Release match ownership and return to a usable reconnect/menu screen."""
    global net_session, mode, paused, accumulator, audio
    global presentation
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
    menu.screen = 'replays' if replaying else 'lan_join' if networked else 'main'
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
        if net_session.snapshot.get('error'):
            leave_game(str(net_session.snapshot['error']))
    except Exception as exc:
        leave_game(str(exc))


def handle_game_input(ev):
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
    try:
        inputc.handle_event(ev)
    except Exception as exc:
        if net_session is None and globals().get('playback') is None:
            raise
        leave_game(str(exc))


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
    if net_session is None or ev.type != pygame.KEYDOWN:
        return False
    if ev.key == pygame.K_ESCAPE:
        leave_game()
        return True
    if ev.key in (pygame.K_p, pygame.K_F5, pygame.K_F9):
        flash('Pause/save/load are disabled in LAN games.')
        return True
    return False


def _unlock_next_mission() -> None:
    """Mission completed: unlock the next campaign mission (persisted)."""
    from render.menus import unlock_campaign_mission
    if mission_def is None or globals().get('playback') is not None:
        return
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
    sync_campaign_outcome()
    presentation_frame = cinematic is not None
    help_frame = presentation is not None and presentation.help_visible
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            running = False
            break
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
            if ev.key == pygame.K_ESCAPE:
                if state.game_over or (mission_def is not None
                                       and (gm.mission.completed
                                            or gm.mission.failed)):
                    # campaign result: persist progress before menus
                    if (mission_def is not None and gm.mission.completed
                            and not globals().get('campaign_outcome_seen', False)):
                        _unlock_next_mission()
                        campaign_outcome_seen = True
                    if 'finish_recording' in globals():
                        finish_recording()
                    mode = "menu"       # campaign result -> back to menus
                    continue
        handle_game_input(ev)
        if mode != 'game':
            break

    if mode != 'game' or not running:
        continue
    if presentation_frame:
        draw_campaign_presentation(dt_frame)
        continue
    try:
        advance_simulation(dt_frame)
    except Exception as exc:
        if net_session is None and globals().get('playback') is None:
            raise
        leave_game(str(exc))
        continue

    sync_campaign_outcome()
    if cinematic is not None:
        draw_campaign_presentation(dt_frame)
        continue

    if playback is None and state.game_over:
        finish_recording()
    inputc.update(dt_frame)
    inputc.update_placement()

    # mission progress -> HUD panel
    if mission_def is not None:
        hud.mission_progress = gm.mission.progress_text()
        hud.mission_name = mission_def.get("name", "MISSION")
        hud.mission_done = gm.mission.completed
        hud.mission_failed = gm.mission.failed
    else:
        hud.mission_progress = None

    # ---- draw
    camera.apply(W, H)
    renderer.placement = hud.placement  # render-side preview only; never sim state
    renderer.draw(dt_frame, inputc.selection)
    hud.set_floating_texts(renderer.floating_texts_screen())
    # live box-select rectangle while left-dragging
    hud.set_drag_box(inputc.drag_start, inputc.drag_cur)
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
    hud.render(inputc.selection, None, local_player, view_paused, view_msg,
               max(0.0, flash_left), fps)
    hud.draw_gl()
    draw_presentation_overlay()
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