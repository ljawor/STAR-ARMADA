"""Visual: does a built planet shield generator actually raise a visible field?

Reported (#55) "planet shield generator does not show any visual". Builds real
surface hardware on a colonized world through the production command path, then
renders the SAME scene twice: once with the planet-shield pass skipped (control)
and once normally. Probes the pixel delta for presence, additive character,
remaining hardware visibility, the empty-pool case and both diagnostic
resolutions.

Run: PYTHONPATH=. ./.venv/bin/python tools/diag_planet_shields.py [outdir]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                     # noqa: E402
import pygame                                          # noqa: E402
from OpenGL.GL import (glFinish, glReadPixels, glViewport,   # noqa: E402
                       GL_RGB, GL_UNSIGNED_BYTE)

outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "saves")
os.makedirs(outdir, exist_ok=True)

pygame.init()
pygame.display.set_mode((1280, 800), pygame.DOUBLEBUF | pygame.OPENGL)
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from game.core.commands import PlayerCommand               # noqa: E402
from game.core.manager import GameManager                  # noqa: E402
from game.data.store import DataStore                      # noqa: E402
from render.camera import Camera                           # noqa: E402
from render.renderer import Renderer                       # noqa: E402

DT = 1 / 30.0
DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
st = gm.state

world = next(e for e in st.entities.values() if e.data_id == "temperate")
world.colonized_by = 0
p0 = st.players[0]
p0.credits = p0.materials = p0.energy = p0.crew = 100000
for kind in ("planet_shield_generator", "planet_trade_hub", "planet_extractor"):
    st.queue_command(PlayerCommand("build_planet_building", 0, target_id=world.id,
                                   station_kind=kind))
for _ in range(int(80 / DT)):
    gm.step(DT)
hardware = [e for e in st.entities.values() if e.planet_id == world.id and e.alive]
print("surface hardware:", sorted((e.data_id, e.id) for e in hardware))
generator = next((e for e in hardware if e.data_id == "planet_shield_generator"), None)
assert generator is not None, "FAIL: generator was never built"
print(f"generator shields={generator.total_shield():.0f}/"
      f"{generator.max_shield_total():.0f}  planet r={world.radius}")

cam = Camera(1280, 800)
cam.target = [world.pos.x, world.pos.y, world.pos.z]
renderer = Renderer(st, cam)
renderer.diff_render = True     # freeze the clock: the two frames must be comparable
renderer.time = 3.0


def shoot(rw, rh, yaw, pitch, distance):
    """One control frame (pass skipped) and one real frame at this viewport."""
    if (rw, rh) != (cam.width, cam.height):
        pygame.display.set_mode((rw, rh), pygame.DOUBLEBUF | pygame.OPENGL)
        for _ in range(3):
            pygame.event.pump()
            pygame.time.wait(30)
        cam.apply(rw, rh)
    glViewport(0, 0, rw, rh)        # the renderer never sets its own viewport
    cam.yaw, cam.pitch, cam.distance = yaw, pitch, distance
    frames = []
    for skip in ({"planet_shields"}, set()):
        renderer.skip = skip
        renderer.draw(DT, set())
        glFinish()
        raw = glReadPixels(0, 0, rw, rh, GL_RGB, GL_UNSIGNED_BYTE)
        img = pygame.image.frombuffer(bytes(raw), (rw, rh), "RGB")
        img = pygame.transform.flip(img, False, True)
        frames.append(np.frombuffer(pygame.image.tobytes(img, "RGB"),
                                    dtype=np.uint8).reshape(rh, rw, 3)
                      .astype(np.float32) / 255.0)
    renderer.skip = set()
    return frames


def shell_box(rw, rh):
    """Screen box of the projected shield shell (planet radius + its own field).

    Project along the CAMERA's own right/up axes: the world X limb collapses to
    half its screen offset at a 60 degree yaw and would under-size the box.
    """
    r = world.radius * 1.04 + 48.0          # planet_shield_field's own clearance
    right, up, _fwd = cam.basis()
    centre = cam.world_to_screen(world.pos.x, world.pos.y, world.pos.z)
    assert centre is not None, "world is off-screen"
    rad = 0.0
    for axis in (right, up):
        limb = cam.world_to_screen(world.pos.x + axis[0] * r * 1.15,
                                   world.pos.y + axis[1] * r * 1.15,
                                   world.pos.z + axis[2] * r * 1.15)
        assert limb is not None, "world is off-screen"
        rad = max(rad, abs(limb[0] - centre[0]), abs(limb[1] - centre[1]))
    return (max(0, int(centre[0] - rad)), max(0, int(centre[1] - rad)),
            min(rw, int(centre[0] + rad)), min(rh, int(centre[1] + rad)))


def report(label, frames, rw, rh, expect_on=True):
    control, field = frames
    changed = np.abs(field - control).max(axis=2) > (2.0 / 255.0)
    n = int(changed.sum())
    box = shell_box(rw, rh)
    inside = int(changed[box[1]:box[3], box[0]:box[2]].sum())
    gain = float((field[changed] - control[changed]).mean()) if n else 0.0
    print(f"[{label:10s} {rw}x{rh}] changed={n:6d} inside_shell={inside:6d} "
          f"mean_delta={gain:+.4f} box={box}")
    if expect_on:
        assert n > 0, f"FAIL: no visible planet shield ({label})"
        assert inside >= 0.98 * n, "FAIL: shield pixels escaped the world"
        assert gain > 0.0, "FAIL: field did not brighten the frame"
        peak_c, peak_f = float(control[changed].max()), float(field[changed].max())
        assert peak_f >= peak_c - 1e-6, "FAIL: shell hid the hardware inside it"
    else:
        assert n == 0, f"FAIL: field drawn without an operational generator ({label})"
    return n


frames = shoot(1280, 800, 0.0, 22.0, 2200.0)
report("close", frames, 1280, 800)
for name, arr in zip(("control", "on"), frames):
    surf = pygame.image.frombuffer((arr[::-1] * 255).astype(np.uint8).tobytes(),
                                   (1280, 800), "RGB")
    pygame.image.save(surf, os.path.join(outdir, f"planet_shield_{name}.png"))
print(f"  saved {outdir}/planet_shield_control.png + planet_shield_on.png")
frames = shoot(1280, 800, 60.0, 34.0, 4200.0)
report("tactical", frames, 1280, 800)

generator.crew = 0                       # abandoned: no operational generator
report("abandoned", shoot(1280, 800, 0.0, 22.0, 2200.0), 1280, 800, expect_on=False)
generator.crew = 20
report("restored", shoot(1280, 800, 0.0, 22.0, 2200.0), 1280, 800)

report("close", shoot(1024, 768, 35.0, 26.0, 1800.0), 1024, 768)

print("DIAG_OK")
