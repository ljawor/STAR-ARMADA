"""Diag: menu stack screens + start_mission() wiring.

Part A (real window): render splash/main/settings/campaign/briefing,
click through transitions, screenshot each, assert lit pixels + result.
Part B (headless): GameManager.start_mission applies loadout, swaps enemy
faction, spawns mission units, MissionSystem active.
"""
import os
os.environ["STAR_ARMADA_SKIP"] = ""
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
import numpy as np

os.makedirs("saves", exist_ok=True)
pygame.init()
W, H = 1280, 800
pygame.display.set_mode((W, H), pygame.DOUBLEBUF | pygame.OPENGL)
pygame.display.set_caption("diag menu")
for _ in range(5):
    pygame.event.pump()
    pygame.time.wait(30)

from OpenGL.GL import glGetError, glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
from render.menus import MenuStack, MenuResult

menu = MenuStack(W, H)
shots = []


def snap(name):
    # skill pitfall: glReadPixels BEFORE pygame.display.flip() — after the
    # flip the read buffer is the wrong back buffer (black frames)
    data = glReadPixels(0, 0, W, H, GL_RGB, GL_UNSIGNED_BYTE)
    # menu quad fills the window via the inverted ortho — raw readback rows
    # are already screen-order (a flip here turns screenshots upside down)
    arr = np.frombuffer(data, dtype=np.uint8).reshape(H, W, 3)
    lit = int(((arr[:, :, 0] > 40) & (arr[:, :, 0] < 250)).sum())
    err = glGetError()
    print(f"  {name:12s} lit={lit:8d} mean={arr.mean():6.1f} GLerr=0x{err:x}")
    assert lit > 2000, f"{name}: menu not visible"
    assert err == 0, f"{name}: GL error"
    assert arr.mean() < 200, f"{name}: frame is blank/white (readback bug)"
    surf = pygame.image.frombuffer(arr.tobytes(), (W, H), "RGB")
    pygame.image.save(surf, f"saves/diag_menu_{name}.png")
    pygame.display.flip()
    pygame.time.wait(20)
    shots.append(name)


def click(x, y):
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (x, y), "button": 1})
    menu.handle_event(ev)
    ev = pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": (x, y), "button": 1})
    menu.handle_event(ev)


print("== Part A: menu screens")
menu.render(0.016)
menu.draw_gl()
snap("splash")

click(W // 2, H // 2)               # anywhere -> main
assert menu.screen == "main", menu.screen
menu.render(0.016)
menu.draw_gl()
snap("main")

# find SETTINGS button (3rd item) and click it
menu.render(0.016)                  # rebuild buttons for the settings screen
btn = next(b for b in menu.buttons if b["action"] == "goto_settings")
click(*btn["rect"].center)
assert menu.screen == "settings"
old = menu.settings["sfx_volume"]
# drag the SFX slider to ~90%
menu.render(0.016)                  # buttons rebuilt per screen
sbtn = next(b for b in menu.buttons if b["action"] == "slider"
            and b["payload"]["key"] == "sfx_volume")
r = sbtn["payload"]["rect"]
click(int(r.x + r.w * 0.9), r.centery)
assert abs(menu.settings["sfx_volume"] - 0.9) < 0.03, menu.settings["sfx_volume"]
menu.render(0.016)
menu.draw_gl()
snap("settings")
print(f"  sfx volume {old} -> {menu.settings['sfx_volume']} (slider OK)")

back = next(b for b in menu.buttons if b["action"] == "goto_main")
click(*back["rect"].center)
menu.render(0.016)                  # rebuild main-menu buttons
btn = next(b for b in menu.buttons if b["action"] == "goto_campaign")
click(*btn["rect"].center)
assert menu.screen == "campaign"
menu.render(0.016)
menu.draw_gl()
snap("campaign")

menu.render(0.016)                  # rebuild campaign-list buttons
m1 = next(b for b in menu.buttons if b["action"] == "select_mission")
click(*m1["rect"].center)
assert menu.screen == "briefing"
menu.render(0.016)
menu.draw_gl()
snap("briefing")

launch = next(b for b in menu.buttons if b["action"] == "launch_mission")
click(*launch["rect"].center)
assert menu.result == MenuResult.START_MISSION, menu.result
assert menu.result_payload is not None
assert menu.result_payload.get("id") == "m01_first_fleet"
print(f"  LAUNCH -> START_MISSION payload={menu.result_payload['id']}")
print("MENU_DIAG_OK")

print("== Part B: start_mission() headless")
from game.data.store import DataStore
from game.core.manager import GameManager
DataStore.reset()
ds = DataStore()
mdef = ds.campaign["missions"][0]
gm = GameManager.start_mission(ds.maps["skirmish01"], mdef)
st = gm.state
p0 = st.players.get(0)
res = mdef["loadout"]["resources"]
assert abs(p0.credits - res["credits"]) < 0.01, p0.credits
p1 = st.players.get(1)
assert p1.faction == "syndicate", p1.faction
p0_units = [e for e in st.entities.values()
            if e.alive and e.owner == 0 and (e.is_ship or e.is_station
                                             or e.is_squadron)]
p1_units = [e for e in st.entities.values()
            if e.alive and e.owner == 1 and (e.is_ship or e.is_station
                                             or e.is_squadron)]
n_loadout = sum(int(v) for v in mdef["loadout"]["start_units"].values())
n_enemy = sum(int(v) for v in mdef["enemy"]["start_units"].values())
print(f"  P0 units={len(p0_units)} (loadout {n_loadout}) "
      f"P1 units={len(p1_units)} (enemy {n_enemy})")
assert len(p0_units) == n_loadout, (len(p0_units), n_loadout)
assert len(p1_units) == n_enemy, (len(p1_units), n_enemy)
assert gm.mission is not None and gm.mission.mission is not None
assert len(gm.mission.objectives) == 3
# sim runs: mission system steps without error
for _ in range(60):
    gm.step(1 / 30)
print(f"  sim 2s OK, mission.progress={gm.mission.progress_text()[0]}")
print("MISSION_DIAG_OK")
print("ALL_OK")