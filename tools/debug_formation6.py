"""Probe 5: wrap every manager system; log vel of frozen ship after each stage."""
import sys, math
sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from test_gameplay import make_game, run_for  # noqa
from game.core.vectors import Vec3
from game.core import commands

gm = make_game(ai=False)
st = gm.state
ships = [e.id for e in st.entities.values()
         if e.alive and e.owner == 0 and (e.is_ship or e.is_squadron)]
st.queue_command(commands.FleetCreateCommand(0, ships, "Alpha",
                                             commander="aggressive", formation="wedge"))
run_for(gm, 0.5)
fleet = next(iter(st.fleets.values()))
flagship = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
target = flagship.pos + Vec3(3000, 0, 0)
st.queue_command(commands.PlayerCommand("move", 0, unit_ids=tuple(fleet.member_ids),
                                        target_pos=(target.x, target.y, target.z)))
run_for(gm, 8.0)

frozen = next((e.id for e in st.entities.values()
               if e.id in fleet.member_ids and e.alive and e.vel.length() < 10), None)
print("frozen:", frozen)

SYS = ["movement", "separation", "squadrons", "weapons", "projectiles",
       "damage", "abilities", "economy", "construction", "research",
       "formations", "ai", "victory", "mission"]
wraps = []
for name in SYS:
    sysobj = getattr(gm, name, None)
    if sysobj is None:
        continue
    orig = sysobj.update
    def make_w(nm, fn):
        def wrapped(dt):
            fn(dt)
            e = gm.state.entity(frozen)
            if e is not None:
                v = e.vel.length()
                if v > 3.0 or nm in ("movement", "separation", "squadrons"):
                    print(f"    after {nm:12s} vel={v:7.2f} pos_d={e.pos.dist(Vec3(0,0,0)):8.0f}")
        return wrapped
    sysobj.update = make_w(name, orig)
    wraps.append(name)

for _ in range(8):
    gm.step(1 / 30)