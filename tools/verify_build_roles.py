"""Verify build roles: command station = engineering only, shipyard = all warships."""
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from test_gameplay import make_game, run_for  # noqa

gm = make_game(ai=False)
st = gm.state
cs = st._construction_system

def menu_for(station_data_id, ent):
    import render.hud as hud_mod  # noqa - only ensure importable when renderer present
    return None

# pick player-0 stations
cmd_st = next(e for e in st.entities.values()
              if e.is_station and e.owner == 0 and e.data_id == "command_station")
yard = next(e for e in st.entities.values()
            if e.is_station and e.owner == 0 and e.data_id == "shipyard")

ships = sorted(gm.ds.ships)
print("== station_can_build_ship ==")
errs = []
for sid in ships:
    sd = gm.ds.ships[sid]
    at_cmd = cs.station_can_build_ship(cmd_st, sid)
    at_yard = cs.station_can_build_ship(yard, sid)
    eng = sd.category == "construction"
    if eng and (not at_cmd or at_yard):
        errs.append(f"engineering {sid}: cmd={at_cmd} yard={at_yard} (want cmd=True yard=False)")
    if not eng and (at_cmd or not at_yard):
        errs.append(f"warship {sid}: cmd={at_cmd} yard={at_yard} (want cmd=False yard=True)")
    print(f"  {sid:30s} cat={sd.category:18s} cmd={str(at_cmd):5s} yard={str(at_yard)}")
if errs:
    print("FAIL:")
    for e_ in errs:
        print("   ", e_)
    sys.exit(1)

# actually queue a battleship at the shipyard and a constructor at the command station
p0 = st.players[0]
p0.credits += 20000; p0.materials += 20000; p0.energy += 5000; p0.crew += 10000
n1 = cs.start_ship(yard.id, "imperial_battleship", 0)
n2 = cs.start_ship(cmd_st.id, "imperial_constructor", 0)
n3 = cs.start_ship(cmd_st.id, "imperial_corvette", 0)  # must be rejected
n4 = cs.start_ship(yard.id, "imperial_constructor", 0)  # must be rejected
print(f"queued: battleship@yard={n1} constructor@cmd={n2} "
      f"corvette@cmd(reject)={n3} constructor@yard(reject)={n4}")
assert n1 == 1 and n2 == 1 and n3 == 0 and n4 == 0, "build-role gating broken"

# fast-forward and confirm the battleship actually spawns
run_for(gm, 80)
bb = [e for e in st.entities.values()
      if e.alive and e.data_id == "imperial_battleship"]
print(f"battleships built: {len(bb)}")
assert bb, "shipyard never spawned the battleship"
print("BUILD ROLES OK")