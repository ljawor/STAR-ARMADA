"""Dump every entity's world+screen position at smoke-end state (no GL needed)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game.data.store import DataStore
from game.core.manager import GameManager
from tests.helpers import run_for
from render.camera import Camera

DataStore.reset()
ds = DataStore()
gm = GameManager.start_skirmish(ds.maps["skirmish01"])
run_for(gm, 900)          # same as smoke: 30 sim-seconds
st = gm.state

cam = Camera(1280, 800)
stn = next(e for e in st.entities.values() if e.owner == 0 and e.is_station)
cam.target = [stn.pos.x, 0.0, stn.pos.z]
cam.zoom(0.55)

print(f"camera target=({cam.target[0]:0.0f},{cam.target[2]:0.0f}) "
      f"eye=({cam.eye_position()[0]:0.0f},{cam.eye_position()[1]:0.0f},"
      f"{cam.eye_position()[2]:0.0f})")
for e in sorted(st.entities.values(), key=lambda x: x.id):
    if not e.alive or e.owner != 0:
        continue
    sp = cam.world_to_screen(e.pos.x, e.pos.y, e.pos.z)
    px = f"({sp[0]:5.0f},{sp[1]:5.0f})" if sp else "  offscreen  "
    print(f"  #{e.id:<3d} {e.kind:10s} {e.data_id:26s} "
          f"pos=({e.pos.x:7.0f},{e.pos.y:5.0f},{e.pos.z:7.0f}) r={e.radius:6.1f} "
          f"px={px} vel={e.vel.length():6.1f} order={e.order_type}")