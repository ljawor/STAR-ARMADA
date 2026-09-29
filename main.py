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
  S stop · H follow · J jump · SPACE pause      F5/F9      quicksave/quickload
  ESC             deselect (quit on game over)
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
def make_game(load_path: str | None, mission_def: dict | None = None):
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
    return GameManager.start_skirmish(map_def, mods=MODS or None)


SETTINGS_PATH = os.path.join(SAVES_DIR, "settings.json")


def make_audio(state) -> Audio:
    a = Audio(state, settings=SETTINGS)
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
paused = False
running = True
flash_msg = ""
flash_until = 0.0
mission_def: dict | None = None


def flash(msg: str) -> None:
    global flash_msg, flash_until
    flash_msg = msg
    flash_until = (state.time if state else 0.0) + 2.5


def start_game(load_path: str | None = None, mdef: dict | None = None) -> None:
    """Build the full in-game object graph (skirmish, mission, or load)."""
    global gm, state, camera, renderer, hud, audio, inputc, paused, mission_def
    global flash_until
    paused = False
    mission_def = mdef
    gm = make_game(load_path, mdef)
    state = gm.state
    camera = Camera(W, H)
    _start = next((e for e in state.entities.values()
                   if e.owner == 0 and e.is_station), None)
    if _start is not None:
        camera.target = [_start.pos.x, 0.0, _start.pos.z]
    camera.zoom(0.55)                    # start close-in; wheel out for tactics
    renderer = Renderer(state, camera)
    hud = HUD(W, H, state)
    hud.set_camera_ref(camera)
    audio = make_audio(state)
    audio.set_camera(camera)          # distance attenuation + stereo pan
    inputc = InputController(state, camera, hud, None)
    inputc.local_player = 0
    inputc.app = _AppGlue()


def rebuild(load_path: str | None) -> None:
    """Full object-graph rebuild for quickload (F9)."""
    audio.cleanup()
    start_game(load_path=load_path, mdef=mission_def)
    flash("game loaded")


def _unlock_next_mission() -> None:
    """Mission completed: unlock the next campaign mission (persisted)."""
    from render.menus import load_campaign_progress, save_campaign_progress
    if mission_def is None:
        return
    ids = [m.get("id") for m in menu.campaign.get("missions", [])]
    try:
        idx = ids.index(mission_def.get("id"))
    except ValueError:
        return
    if idx + 1 > load_campaign_progress():
        save_campaign_progress(idx + 1)


def write_save(path: str) -> None:
    """Persist a snapshot. Never fatal: a read-only location must not crash."""
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
        global mode
        mode = "menu"            # back to the main menu, keep app running

    @staticmethod
    def toggle_pause() -> None:
        global paused
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
                start_game(load_path=INITIAL_LOAD)
                mode = "game"
            elif res == MenuResult.START_MISSION:
                save_settings(SETTINGS)
                start_game(load_path=None, mdef=payload)
                mode = "game"
        continue

    # ---- game mode
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            running = False
            break
        if ev.type == pygame.KEYDOWN:
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
                    if mission_def is not None and gm.mission.completed:
                        _unlock_next_mission()
                    mode = "menu"       # campaign result -> back to menus
                    continue
        inputc.handle_event(ev)

    if not paused and not state.game_over:
        accumulator += dt_frame
        while accumulator >= TICK_DT:
            gm.step(TICK_DT)
            accumulator -= TICK_DT
            if state.game_over:
                break

    inputc.update()
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
    renderer.draw(dt_frame, inputc.selection)
    hud.set_floating_texts(renderer.floating_texts_screen())
    # live box-select rectangle while left-dragging
    hud.set_drag_box(inputc.drag_start, inputc.drag_cur)
    flash_left = flash_until - state.time
    hud.render(inputc.selection, None, 0, paused, flash_msg,
               max(0.0, flash_left), fps)
    hud.draw_gl()
    pygame.display.flip()

    frames += 1
    fps_time += dt_frame
    if fps_time >= 1.0:
        fps = frames / fps_time
        frames = 0
        fps_time = 0.0

    # autosave ring every 60 sim-seconds (spec §32): 3 rotating slots
    if not state.game_over and state.time - last_autosave >= 60.0:
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

if audio is not None:
    audio.cleanup()
else:
    # pygame.init() opens a mixer even while sitting in the menus, so there is
    # still a device to release when no game was ever started.
    pygame.mixer.quit()
save_settings(SETTINGS)
pygame.quit()
if SMOKE and state is not None:
    print("SMOKE_DONE " + summary())