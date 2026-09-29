"""Prove the audio probe/tests are not vacuous.

Reinstates the ORIGINAL defects in a COPY of the source text and confirms the
tests FAIL. A probe that passes both ways has proven nothing.

The rate defect is reproduced FAITHFULLY: the real bug was never "22050 is the
wrong number", it was that the buffers were synthesized at one rate while the
mixer played them at another. So the reversal keeps the mixer at the device
default and synthesizes at 22050 — a genuine mismatch.

Usage: PYTHONPATH=. ./.venv/bin/python tools/reverse_audio_check.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "render", "audio.py")
BACKUP = "/tmp/audio_new_backup.py"


def run_tests(label):
    env = dict(os.environ, SDL_AUDIODRIVER="dummy",
               PYTHONPATH=f"{ROOT}:{ROOT}/tests")
    r = subprocess.run(
        [os.path.join(ROOT, ".venv/bin/python"), "-m", "unittest",
         "tests.test_audio"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    lines = (r.stderr or r.stdout).strip().splitlines()
    text = "\n".join(lines)
    detail = next((ln for ln in reversed(lines) if ln.strip()), "")
    print(f"  {label}: exit={r.returncode}  {detail}")
    # a SyntaxError is not evidence the tests caught anything — the module
    # simply failed to import, so every test would "fail" for free
    if "SyntaxError" in text or "IndentationError" in text:
        print(f"  !! {label}: INVALID — the injection broke the module")
        return 0        # treat as a failure of the reversal, not a pass
    return r.returncode


def inject(src, old, new, label):
    """Replace `old` (a regex) once; assert it actually matched."""
    out, n = re.subn(old, new, src, count=1)
    assert n == 1, f"could not inject: {label}"
    return out


def main():
    src = open(AUDIO).read()
    shutil.copy(AUDIO, BACKUP)
    print(f"backed up render/audio.py -> {BACKUP}")
    ok = True
    try:
        # --- defect 1: synthesize at 22050 while the mixer runs at 44100 ----
        print("\n[1] reinstate the sample-rate MISMATCH (the 2x-pitch bug)")
        bad = inject(
            src,
            re.escape(
                "            if pygame.mixer.get_init() is not None:\n"
                "                pygame.mixer.quit()\n"
                "            pygame.mixer.init(frequency=RATE, size=-16, "
                "channels=2, buffer=512)"
            ),
            "            pygame.mixer.init(frequency=RATE, size=-16, "
            "channels=2, buffer=512)",
            "no mixer reopen",
        )
        bad = inject(bad, r"self\.rate = int\(init\[0\]\)",
                     "self.rate = 22050   # BUG: buffers at 22050, mixer at 44100",
                     "synth rate 22050")
        open(AUDIO, "w").write(bad)
        ok &= run_tests("rate mismatch") != 0

        # --- defect 2: one laser voice for every weapon ---------------------
        print("\n[2] reinstate a single voice for all weapons")
        bad = inject(src, r'(\s+)if wtype == "turbolaser":',
                     r'\1return "laser"   # BUG: every weapon sounds the same\n'
                     r'\1if wtype == "turbolaser":', "flat voice set")
        open(AUDIO, "w").write(bad)
        ok &= run_tests("flat voice set") != 0

        # --- defect 3: unfiltered white-noise burst for the hull impact -----
        print("\n[3] reinstate the raw hiss burst for hull impacts")
        bad = inject(
            src,
            r"clang = _tone\(n, rate, f, f \* 0\.85, curve=0\.4,\s*\n"
            r"\s*harmonics=\(\(1, 0\.6\), \(2\.41, 0\.3\), \(3\.77, 0\.18\), "
            r"\(5\.3, 0\.1\)\)\)",
            "clang = _rng(seed).uniform(-1.0, 1.0, n)   # BUG: raw white noise",
            "hiss impacts",
        )
        open(AUDIO, "w").write(bad)
        ok &= run_tests("hiss impacts") != 0

        # --- defect 4: abrupt envelope start (onset click) ------------------
        print("\n[4] reinstate a click-prone envelope (start at full gain)")
        bad = inject(src, r"a = np\.clip\(t / max\(attack, 1e-4\), 0\.0, 1\.0\)",
                     "a = np.ones(n)   # BUG: no attack ramp -> onset click",
                     "onset clicks")
        open(AUDIO, "w").write(bad)
        ok &= run_tests("onset clicks") != 0

        # --- defect 5: no sub-bass in the blast ----------------------------
        print("\n[5] reinstate a blast with no sub-bass body")
        bad = inject(src, r"\+ sub \* _env\(n, rate, 0\.010, sub_dec\) \* 0\.75",
                     "+ sub * 0.0", "no sub-bass")
        open(AUDIO, "w").write(bad)
        ok &= run_tests("no sub-bass") != 0
    finally:
        open(AUDIO, "w").write(src)
        print("\nrestored render/audio.py from the original text")

    print("\n" + ("REVERSAL_OK — every injected defect failed the suite"
                  if ok else "REVERSAL_FAIL — a defect slipped through"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
