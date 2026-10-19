# S07 harness recovery — local, not stage closure

Base: `56906ea7c73c219fbdc91c68176104b23d0f7712`.

## Root cause and repair
The source-mutated nonlocal-queue negative control used `exec(..., dict(vars(renderer)))`.
That copy retained native `gl*` functions, bypassing subsequent recording patches.
The preserved native sample of PID 76413 shows pygame crash-cleanup handling; this
is not evidence of a six-hour valid test workload. The process was terminated and
its absence verified. Original partial logs remain unchanged.

Added a pre-execution GL-global identity guard. `harness-namespace-red.txt` fails
in 0.511 seconds at `glDisable bypasses CPU recording seam`, without invoking native GL.
Rebound only the mutated function's bytecode with `FunctionType(..., vars(module))`
so the normal recorder intercepts its calls. No production renderer edit was needed.

`construction-hidden-fixed.txt` and its machine receipt: 12 tests passed,
child elapsed 2.327 seconds, no timeout. Covers 40 station bindings x two placement
validities, four-faction queue-progress controls, historical hidden contacts and
wrong-geometry/nonlocal/scaffold-selection negative controls. This remains CPU coverage.
The queue's pre-existing line-width/depth restoration limitation remains explicit.

## Enforced deadline
`run-bounded.py` launches a separate process group and SIGKILLs/waits at deadline.
`watchdog-control.txt.json` proves a blocked child was killed in 0.506 seconds
with child exit -9 and wrapper exit 124. A tool's own timeout is not relied upon.

## Owner authorization and remaining gates
Owner selected verbatim: **Fix the opt-in rendering paths to match**.
Question: S07 requires cached/uncached matching detail at distant zoom; recommended
fix preserves visible detail and legacy defaults. This authorizes that bounded
renderer repair, NOT an acceptance-criterion relaxation, merge/default activation,
new art revision, scaffold registration or release. Parity repair is not implemented yet.

Native attempt3 passed 24 representative legacy/preview rows, 216 verified capture
hashes and 327 protected pins; readback and inspected owner sheet are retained.
It is not catalogue-wide/motion/construction/hidden-raster or LOD acceptance.

Next: implement and prove the authorized opt-in parity repair; finish outstanding
visual/motion/construction rows; independently review and publish the final bounded
registered-catalogue receipt and verify exact-head CI. Full S07 closure additionally
needs the separately scoped approved/unregistered scaffold resolved explicitly.
No merge, production-default switch or release is implied. New tests/evidence and
harness repair are currently local/uncommitted.
