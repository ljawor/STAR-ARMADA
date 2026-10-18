# S07 opt-in integration — first engineering checkpoint

Status: IN PROGRESS, not S07 acceptance. Parent: PR #130 approval head
`65661e4a9fbde7e37da0bae0881e372c3dc21e59`. Working branch:
`feat/s07-opt-in-catalogue`. No production-default switch, merge or release.

## Fixes locally verified; independent follow-up review passed

The three blockers from `deleg_f45c7347` now have tested fixes. Wrapper exports run
in fresh isolated workspaces, require newly produced output and verify approved
runtime plus preserved master before publication. Metadata identifiers and every
output destination are preflighted; staged per-file replacement rolls back ordinary
IO failures (not a crash-consistent transaction). The interrupted metadata worker's
rollback fixture needed a macOS canonical-root correction so injected replacement
failures actually fired; both the failed and corrected runs are retained.

Parent reran all 99 exports under fresh-output enforcement using Blender 5.0.1:
all match approved bytes, all 327 protected inputs remain unchanged. The combined
runtime/authoring/negative-control union passes **431 tests**. Model validation
passes **1024 checks**, no warnings; all 110 generated metadata files are current,
republishing changes zero bytes. Evidence:
`artifacts/s07-integration/S07-POST-REVIEW-FIXES.json` and
`exports-approved-s06-isolated-attempt1.txt`.

Independent follow-up review `deleg_2c66bab0` passed with no security concerns or
logic errors. Its read-only metadata checks confirmed 110 current outputs, 102 core
bindings, 314 pins and unchanged trio pipeline entries. Summary:
`artifacts/s07-integration/REGISTRATION-FOLLOWUP-REVIEW.json`. The suggestion to
also hard-code original decision membership in the publisher is nonblocking; exact
original membership is already enforced by the shared test guards.

This is a draft preservation checkpoint, not runtime acceptance, default activation,
merge or release. Read the exact published head and CI status from GitHub rather
than assuming this working directory or parent CI represents the delivered head.
The earlier failed review remains in
`artifacts/s07-integration/REGISTRATION-REVIEW-BLOCKERS.json`; the checkpoint below
is historical positive-path evidence.

## Local registration checkpoint (2026-10-18)

The bounded 99-S06 increment is now registered behind the existing explicit
`model_preview` switch: 102 core manifests including the unchanged trio. Legacy
remains the default. The separately appearance-approved scaffold is not part of
this registration increment. No commit, push, merge or release yet.

Real Blender 5.0.1 execution completed: 99 exports matched their approved runtime
bytes; all 33 script-authoritative specimens also reconstructed in isolated
workspaces and matched those bytes. All 327 protected inputs are unchanged.
`validate-models --all` passed 1024 checks with no warnings. The runtime union
passed 174 tests, including assets-only frozen loading of all 102 assets. Earlier
failed union attempts are retained: old unregistered expectations and synthetic
fixtures required deliberate updates; no loader or approval checks were weakened.

The route audit accounts for 120 historical identities: 106 selected identities
(includes four convoy aliases), one approved/unregistered scaffold, ten deferred
textures and three outside-mesh identities; no route or approval-integrity errors.
These are CPU/metadata proofs, not GL or full S07 acceptance.

Receipt: `artifacts/s07-integration/S07-REGISTRATION-CHECKPOINT.json`. This section
records the earlier checkpoint; the verified 431-test union and passed follow-up
review above supersede its then-pending review/guard status. Geometry/LOD,
menu/cache/motion and later S08/S09 gates remain open.

## Implemented and exercised

- Selected Imperial station consumers now use actual authored all-role bounds for
  visual radius, shields, hit contacts and picking. Unselected Imperial paths retain
  their legacy behavior; hidden/unresolved effects retain historical positions.
- Construction outlines consult selected Imperial station geometry rather than
  bypassing it unconditionally.
- Shared scaffold has a production build-queue drawing seam. A selected scaffold
  draws solid six-role hardware, owner paint, and progress-dependent height. The
  unselected lattice block is retained under an explicit fallback guard. Queue,
  timing, collision and serialized simulation data are not modified.
- The scaffold remains UNREGISTERED. Diagnostic selection is a scoped, restored
  in-process injection only. The owner subsequently answered `Pictures approved`;
  `s07-scaffold-appearance-2026-10-18` now pins the pictured scaffold revision,
  separately from the original eight B9 ship approvals. No runtime acceptance or
  default activation follows from this appearance approval.

## Evidence

`artifacts/s07-integration/scaffold-review-attempt1/metrics.json` and paired PNGs:
real macOS native GL, production `Renderer.draw`, actual constructor build queues,
all four owner colors, Imperial progress 10/50/90 percent, close/tactical views.
Six cases, repeat captures pixel-identical, nonzero before/after changes in every
view, nonzero accent/dark/cool ablations, protected inputs unchanged. Owner review
sheet: `scaffold-appearance-grid.jpg` in the same directory. This is not paced FPS,
Windows graphics, platform or packaging acceptance.

`consumers-approval-union-final.txt`: **105 tests passed**, covering selected and
stock consumers, construction seam, bounds/contact/picking/camera regressions,
convoy gate, approval preservation and coverage reconciliation. Earlier RED,
failed fixture, timeout and intermediate attempts are retained. The timeout was
an incomplete headless fixture: material helpers still called real GL functions;
the corrected fixture mocks those GL calls, never substitutes pixel evidence.

98 wrappers current, zero stale sidecars at the initial integration checkpoint.
Coverage regenerated after the engineering renderer-code pin correction.

## Approval integrity

B5 originally pins the entire renderer file in its runtime group. Unrelated S07
station/scaffold changes necessarily invalidated that broad pin; the failure was
retained in `consumers-approval-union.txt`. Its explicit engineering correction
retains the original renderer hash and complete source/export/runtime maps, with
version-neutral AST hashes proving the asteroid draw, prop-list and mesh-emission
methods unchanged against the approved Git blob. Only the broad renderer-code
pin is rebound. Existing owner words, decision scope, all art payload/source/export
pins and `approved_assets` are unchanged. No new appearance approval was invented.
The later failed AST hash attempt is retained: Python 3.14 changed `ast.dump`'s
empty-field formatting; canonical AST field projection now compares across versions.

PR #130 approval-head CI run `39121908603` was re-read: success at the exact parent
head above; real Windows LAN passed, manual Windows packaging skipped. That result
does not apply to this new uncommitted branch delta.

## Still open

- Broader runtime GL/geometry/LOD, cache/menu/preview lifecycle and motion acceptance.
  CPU route auditing, bounded 99-row registration, real resolver tests, assets-only
  frozen closure, authoring guard migration and independent code review are verified
  above and must not be restarted as missing work.
- Commit/push/draft preservation PR and exact-head CI for this delta; read GitHub for
  the final delivery state.
- Scaffold opt-in registration/runtime acceptance remains open; appearance approval
  is recorded in `artifacts/s07-integration/S07-SCAFFOLD-APPEARANCE-APPROVAL.json`.
  `scaffold-approval-union.txt` records 22 passing approval/route/preservation tests.
- Separately bounded S08/S09 platform/performance/package gates, and final default
  activation/merge/release remain unaccepted/out of scope respectively.
