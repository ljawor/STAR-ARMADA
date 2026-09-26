"""STAR ARMADA — fleet-based real-time space RTS (Armada II spirit, original IP).

Run:
  ./.venv/bin/python main.py                     # 1v1 skirmish, Kotarri Sector
  ./.venv/bin/python main.py --smoke             # automated verification run
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

TICK_RATE = 30
TICK_DT = 1.0 / TICK_RATE
SAVES_DIR = os.path.join(ROOT, "saves")
os.makedirs(SAVES_DIR, exist_ok=True)

# --------------------------------------------------------------------------- args
SMOKE = "--smoke" in sys.argv
SMOKE_TICKS = 900                    # 30 sim-seconds of automated play
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
FULLSCREEN = "--fullscreen" in sys.argv
_flags = pygame.DOUBLEBUF | pygame.OPENGL
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
    camera.width, camera.height = W, H
    camera._proj = camera._view = None
    hud.resize(W, H)
    flash("fullscreen ON" if FULLSCREEN else "fullscreen OFF")

# macOS (skill): pump events so the window system is up before any grabbing
for _ in range(10):
    pygame.event.pump()
    pygame.time.wait(50)


# --------------------------------------------------------------------------- game
def make_game(load_path: str | None):
    ds = DataStore.reset()
    ds = DataStore(mods=MODS or None)
    map_def = ds.maps["skirmish01"]
    if load_path:
        with open(load_path) as f:
            saved = json.load(f)
        state = GameState.from_dict(saved)
        return GameManager(state=state, mods=MODS or None)
    return GameManager.start_skirmish(map_def, mods=MODS or None)


gm = make_game(INITIAL_LOAD)
state = gm.state

camera = Camera(W, H)
_start = next((e for e in state.entities.values()
               if e.owner == 0 and e.is_station), None)
if _start is not None:
    camera.target = [_start.pos.x, 0.0, _start.pos.z]
camera.zoom(0.55)                    # start close-in; wheel out for tactical view

renderer = Renderer(state, camera)
hud = HUD(W, H, state)
hud.set_camera_ref(camera)
audio = Audio(state)
audio.start_ambient()

flash_msg = ""
flash_until = 0.0


def flash(msg: str) -> None:
    global flash_msg, flash_until
    flash_msg = msg
    flash_until = state.time + 2.5


class _AppGlue:
    """Adapter so InputController can talk back without circular imports."""

    @staticmethod
    def request_exit() -> None:
        global running
        running = False

    @staticmethod
    def toggle_pause() -> None:
        global paused
        paused = not paused

    @staticmethod
    def flash(msg: str) -> None:
        flash(msg)


paused = False
running = True
inputc = InputController(state, camera, hud, None)
inputc.local_player = 0
inputc.app = _AppGlue()


def rebuild(load_path: str | None) -> None:
    """Full object-graph rebuild for quickload (F9)."""
    global gm, state, camera, renderer, hud, audio, inputc
    audio.cleanup()
    gm = make_game(load_path)
    state = gm.state
    camera = Camera(W, H)
    renderer = Renderer(state, camera)
    hud = HUD(W, H, state)
    hud.set_camera_ref(camera)
    audio = Audio(state)
    audio.start_ambient()
    inputc = InputController(state, camera, hud, None)
    inputc.local_player = 0
    inputc.app = _AppGlue()
    flash("game loaded")


def write_save(path: str) -> None:
    with open(path, "w") as f:
        json.dump(state.to_dict(), f)


def take_screenshot(path: str) -> None:
    data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    img = pygame.image.frombuffer(data, (W, H), "RGB")
    img = pygame.transform.flip(img, False, True)
    pygame.image.save(img, path)


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


# --------------------------------------------------------------------------- loop
clock = pygame.time.Clock()
accumulator = 0.0
frames = 0
fps = 0.0
fps_time = 0.0
last_autosave = 0.0

while running:
    dt_frame = min(clock.tick(TICK_RATE) / 1000.0, 0.25)
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

    # ---- draw
    camera.apply(W, H)
    renderer.draw(dt_frame, inputc.selection)
    hud.set_floating_texts(renderer.floating_texts_screen())
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

    # autosave every 60 sim-seconds (spec §32)
    if not state.game_over and state.time - last_autosave >= 60.0:
        write_save(os.path.join(SAVES_DIR, "autosave.json"))
        last_autosave = state.time

    # smoke-mode exit: capture proof and stop
    if SMOKE and state.tick >= SMOKE_TICKS:
        shot = os.path.join(ROOT, "saves", "smoke_screenshot.png")
        take_screenshot(shot)
        print("SMOKE_OK " + summary() + " shot=" + shot)
        running = False

audio.cleanup()
pygame.quit()
if SMOKE:
    print("SMOKE_DONE " + summary())