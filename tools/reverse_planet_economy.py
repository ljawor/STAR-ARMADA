#!/usr/bin/env python3
"""Prove tests/test_planet_economy.py actually catches the three EN barriers.

A test that passes against BOTH the broken and the fixed code has proven
nothing. This reinstates each of the three defects, one at a time, in a COPY,
and confirms the suite fails for the right reason. The working tree is never
touched.

The three defects (each alone makes energy income unreachable):
  D1 economy.py   — income loop keyed on e.owner, which is -1 for all planets
  D2 stations.json— energy_relay requires_range 3200 -> 1100 (inside exclusion)
  D3 ships/*.json — drop energy_relay from every can_build_stations
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "bin", "python")


def run_suite(cwd):
    env = dict(os.environ, SDL_AUDIODRIVER="dummy", PYTHONPATH=".:tests")
    p = subprocess.run(
        [PY, "-m", "unittest", "tests.test_planet_economy"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    out = p.stdout + p.stderr
    return p.returncode, out


def patch(path, old, new):
    """Apply a literal replacement; assert it actually matched."""
    with open(path) as f:
        src = f.read()
    if old not in src:
        raise AssertionError(f"injection did not match in {os.path.basename(path)}: {old!r}")
    with open(path, "w") as f:
        f.write(src.replace(old, new, 1))


def main():
    print("=== control: unmodified tree must PASS ===")
    rc, out = run_suite(ROOT)
    print("   exit=%d  (0 = pass)" % rc)
    if rc != 0:
        print(out[-1500:])
        print("REVERSE_FAIL: the suite does not pass on the clean tree")
        return 1

    tmp = tempfile.mkdtemp(prefix="planet_rev_")
    print("   copy -> %s" % tmp)

    defects = []

    # ---------------- D1: economy income loop keyed on e.owner ----------------
    def d1(d):
        p = os.path.join(d, "game/systems/economy.py")
        with open(p) as f:
            src = f.read()
        # restore the original broken shape: skip planets with owner < 0 and
        # compare colonized_by to owner
        broken = src.replace(
            """            if e.is_planet:
                if e.colonized_by is None or e.colonized_by < 0:
                    continue
                owner = e.colonized_by
            else:
                owner = e.owner
                if owner < 0:
                    continue""",
            """            if e.owner < 0:
                continue
            owner = e.owner""", 1)
        if broken == src:
            raise AssertionError("D1 injection did not match")
        broken = broken.replace(
            "            if e.is_planet:\n                rates = dict(planet_income.get(e.data_id, {}))",
            "            if e.is_planet and e.colonized_by == e.owner:\n                rates = dict(planet_income.get(e.data_id, {}))", 1)
        with open(p, "w") as f:
            f.write(broken)
        return "planet income gate keyed on e.owner again"

    defects.append(("D1 economy.py owner-keyed income", d1))

    # ------------- D2: drop the body-clearance term (the load-bearing fix) ---
    def d2(d):
        p = os.path.join(d, "game/systems/construction.py")
        with open(p) as f:
            src = f.read()
        # Returning 0 is exactly the old behaviour: requires_range was compared
        # against distance from the body CENTRE with no compensation for the
        # spacing exclusion zone. The data value alone cannot fix that — with a
        # flat window the band 0..rng lies entirely inside the zone for any
        # rng below the clearance (3658u for a gas giant).
        broken = src.replace(
            "    return (body.radius + station_radius) * 1.6 + 50.0",
            "    return 0.0   # DEFECT INJECTION: no clearance compensation", 1)
        if broken == src:
            raise AssertionError("D2 injection did not match")
        with open(p, "w") as f:
            f.write(broken)
        return "requires_range back to a flat distance from the body centre"

    defects.append(("D2 no body-clearance compensation", d2))

    # ------------- D3: relay removed from every constructor ------------------
    def d3(d):
        touched = []
        for fac in ("imperial", "rebel", "confederacy", "syndicate"):
            p = os.path.join(d, f"assets/data/ships/{fac}.json")
            with open(p) as f:
                src = f.read()
            if '"energy_relay"' not in src:
                continue
            new = src.replace(', "energy_relay"]', ']', 1)
            if new == src:
                new = src.replace('"defense_platform", "energy_relay"]',
                                  '"defense_platform"]', 1)
            if new == src:
                raise AssertionError(f"D3 injection did not match in {fac}")
            with open(p, "w") as f:
                f.write(new)
            touched.append(fac)
        if not touched:
            raise AssertionError("D3 found nothing to change")
        return "energy_relay removed from: %s" % ", ".join(touched)

    defects.append(("D3 relay missing from build lists", d3))

    # ------------- D4: AI loses its energy-relay build order -----------------
    def d4(d):
        p = os.path.join(d, "game/ai/ai.py")
        with open(p) as f:
            src = f.read()
        broken = src.replace(
            '        if not self.my_stations("energy_relay") and idle and p.credits > 900:',
            '        if False and idle and p.credits > 900:', 1)
        if broken == src:
            raise AssertionError("D4 injection did not match")
        with open(p, "w") as f:
            f.write(broken)
        return "AI never queues an energy_relay again"

    defects.append(("D4 AI has no relay build order", d4))

    # ------------- D5: AI skips gas giants when colonising -------------------
    def d5(d):
        p = os.path.join(d, "game/ai/ai.py")
        with open(p) as f:
            src = f.read()
        broken = src.replace('            if e.data_id == "barren":\n                continue',
                             '            if e.data_id in ("gas_giant", "barren"):\n                continue', 1)
        if broken == src:
            raise AssertionError("D5 injection did not match")
        with open(p, "w") as f:
            f.write(broken)
        return "AI skips gas giants again (the only EN-paying planet)"

    defects.append(("D5 AI skips gas giants", d5))

    print()
    caught = 0
    for i, (name, fn) in enumerate(defects, 1):
        work = os.path.join(tmp, f"d{i}")
        shutil.copytree(ROOT, work, symlinks=True,
                        ignore=shutil.ignore_patterns(
                            ".git", "dist", "build", "saves", "__pycache__",
                            "*.pyc", ".venv", "*.dmg", "*.app"))
        # a copy has no venv; point PY at the real one but run from the copy
        detail = fn(work)
        rc, out = run_suite(work)

        # a syntax/import error is an INVALID injection, not a caught defect —
        # a module that cannot import "fails" every test for free
        invalid = ("SyntaxError" in out or "IndentationError" in out
                   or "ModuleNotFoundError" in out or "ImportError" in out)
        if invalid:
            print("  INVALID  %s — injection produced %s" % (name, detail))
            print("           %s" % out.strip().splitlines()[-1][:160])
            continue

        if rc != 0:
            failed = len(re.findall(r"^(FAIL|ERROR):", out, re.M))
            print("  CAUGHT   %s  (%d failing tests)  — %s" % (name, failed, detail))
            caught += 1
        else:
            print("  MISSED   %s  — %s" % (name, detail))
            print("           the suite still passed; it does not detect this defect")

    print()
    print("%d/%d defects caught" % (caught, len(defects)))
    shutil.rmtree(tmp, ignore_errors=True)
    if caught != len(defects):
        print("REVERSE_FAIL")
        return 1
    print("REVERSE_OK — every barrier is genuinely detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
