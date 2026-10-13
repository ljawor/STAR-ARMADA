# Issue #75 — complete satellite orbits on Nebula Frontier

## Reproduction and root cause

The latest supplied replay is `match-403f1985031d4e199ef6cdb9cf434e8e.json`,
format 2, game 0.11.0, map `skirmish04` (Nebula Frontier), end tick 111156.
Its content digest is
`9820514e0960032f93c0f8c8d9b137cf6a93c2110f75330df48f104028402461`.
Assigned base `f913802` matches that digest and passes production playback
compatibility validation. The immutable v0.11.0 tag does **not** match its content;
its rejected playback attempt is not gameplay evidence.

Production replay execution reached tick 25401 (846.7 simulated seconds).
Defense satellite 203, attached to planet 13 in slot 2, had phase
`5.000395102392876` and position
`[3754.4079389884923, 144.76543841687462, 6959.819988639355]`.
Its next step was 3431.8338622970514 units from gas giant 9, inside the unchanged
3432-unit `(satellite.radius + giant.radius) * 1.6` keep-out. Station spacing
passed, and no applicable engagement pause was observed. Accepting one initial
construction position did not establish that the whole inclined ring was legal.
The old orbit repeatedly retried the same impossible next phase.

## Implementation

- Certify the **complete** circle analytically against public fixed terrain.
  Preserve the original per-slot planes wherever their full circles fit.
- In crowded geometry, select deterministic neighbouring-body-normal, nearly
  polar planes. A shared 32-unit-increment shell offset (32 on Nebula Frontier)
  preserves the existing nested-shell gap. No terrain clearance is reduced.
- Construction and orbital integration use the same terrain-derived geometry.
  Paid and completed satellite hardware reserve their entire rings against
  subsequent station placement, including the side opposite the initial site.
  Check whole-ring station/paid-site availability before payment and completion.
- Existing saved satellites rejoin the nearest certified ring at orbital speed.
  Each displacement uses a swept-sphere test; migration never teleports them.
  Actual accepted velocity remains available to projectile lead.
- Existing combat detection, targeting, engagement pauses, resume behavior,
  abandonment behavior, costs, income, weapons and territorial clearances are
  unchanged. No renderer, shader, map, catalogue or serialization fields change.
  Derived planning caches are not saved and do not affect checksums.

## Executed acceptance

Commands below use `PYTHONPATH=tests:.` and the existing project virtualenv Python.

- Baseline red: `test_nebula_satellite_orbits.NebulaSatelliteOrbitTests.test_replay_derived_blocked_satellite_completes_safe_orbit`
  reports zero angular travel using `f913802` orbital integration, rather than
  an import/setup error. The fixed test exceeds one revolution without crossing
  a terrain keep-out or jumping more than 5 units per tick.
- Focused gate: `python -m unittest test_nebula_satellite_orbits test_satellite_orbits test_satellite_velocity test_colonies test_infrastructure_command -q`
  completed with 51 tests passing. Two subsequently added whole-ring reservation
  tests were independently run and passed. The interrupted earlier run is not
  counted as acceptance.
- Every registered map (`skirmish01`–`skirmish04`), all 18 eligible planets,
  all six slots: 108 unique map/planet/slot fixtures. Actual production orbit-system
  updates ran 3300 ticks per map; every satellite travelled at least 6.6 radians.
  Minimum analytical terrain keep-out margin was 3.2549228645548283 units.
- Six paid alternating-role satellites completed sequentially on Nebula Frontier.
  Exact catalogue costs were deducted, all slots completed, and every satellite
  completed a revolution. Original/restored managers matched exact JSON-normalized
  full-precision state on each of 7800 ticks through paid construction and motion.
- The **actual replay snapshot**, with its AI/runtime state intact, matched an
  independently restored manager for 300 further manager ticks. Previously wedged
  satellite 203 moved 706.947123868137 units; no synthetic state was substituted
  for this continuation probe.
- `tools/diag_nebula_satellite_orbits.py --out DIR` ran real Cocoa SDL/OpenGL on
  Apple M4. Four framebuffer captures proved visible satellite hardware against
  a draw-disabled control, read-only rendering and zero GL errors. The isolated
  replay-derived fixture travelled 9.492 radians, retained at least 4.6382 units
  of terrain keep-out margin, and moved at most 2.894 units per tick. Camera
  bearings vary when the opaque planet occludes the satellite; the report's
  position/phase telemetry, not screenshot comparison, proves motion.
- Compile checks and `git diff --check` passed.

Evidence is retained outside the repository in the Hermes scratch directory
`star-armada-75-evidence`: `replay-baseline.log`, `replay-blocked-report.json`,
`replay-blocked-state.json`, `red.log`, `baseline-and-live-restore.log`,
`live-restore-report.json`, `verified-focused.log`, `reservation-tests.log`,
`all-maps-report.json`, and `gl-final/` (report plus four PNGs).

## Independent review follow-up (third fix)

The independent review supplied two radius-500 controlled planets at
`[0, 0, 0]` and `[2165.0635094610966, 0, 1249.9999999999998]`, with only
slot 5 unlocked. Both purchases passed initial-point checks, yet the first
ring at phase `4.9043751981040655` came within `21.395788` units of the second
complete ring, below the unchanged 144-unit clearance.

- Admission and completion now check **complete ring against complete ring**
  for live/paid and paid/paid hardware, across planets as well as within a colony.
  Current live positions and stored paid birth sites remain additional keep-outs.
- The certificate is conservative, not sample-only acceptance: distance to a
  closed circle is 1-Lipschitz. For every arc interval on circle A, its distance
  to the complete circle B is bounded below by midpoint-to-B distance minus
  `A.radius * interval_half_angle`. Only intervals whose lower bound clears the
  original minimum plus a numerical guard are accepted; all unresolved intervals
  are subdivided. Exact enclosing-sphere/radial-shell lower bounds handle easy
  pairs. Budget exhaustion (4096 intervals, depth 18), intersection and near-boundary
  uncertainty reject, never claim safety. A bounded derived cache stores only
  geometry/minimum-dependent certificates, not simulation state.
- Planetary paid-reservation preview authority uses `colonized_by` and the
  reservation's matching `source_owner`, not neutral terrain `owner`. The existing
  allied placement-reservation policy is retained; this does **not** authorize
  allied production-menu inspection. Detected enemy planets/builders still reveal
  no private paid intent. Own/allied/visible-enemy/stale-enemy-source controls pass.
- A mobile hull overlapping a satellite birth site rejects new admission without
  payment (the deterministic slot search may choose another clear slot). If a
  mobile arrives during already-paid work, completion is deferred at that same
  precise site/slot with its paid reservation retained. Departure allows delivery;
  there is no cancellation, repayment or refund for this transient condition.
  Manager/restore tests compare every deferred and resumed tick exactly, with an
  independent income control proving no monetary change besides normal income.
  Existing stationary-conflict and ownership-invalidation policies are unchanged.
- Mod geometry fails closed for nonpositive/nonfinite hull or orbit geometry,
  capacity outside 1–64, inclination above pi, and shell gaps below the largest
  hull-pair clearance plus guard. The bounded radial search also certifies the
  parent keep-out for the innermost point of each integration chord (at most .02
  radians), rather than merely its circular endpoints. It does not shrink hulls,
  spacing, parent clearance or terrain exclusions.

### Final executed follow-up gates

Evidence root: `star-armada-75-evidence/third/` in Hermes scratch.

- Red: `red-rings.log` records both live/paid and paid/paid admissions wrongly
  succeeding; `red-preview.log` records own/allied reservations omitted;
  `red-mobile.log` records admitted overlap and consumed paid completion;
  `red-mod.log` / `red-angle.log` record uncertified mod shells/parent/angle geometry.
  Green: all eight new review regressions pass (`review.log`).
- Final serialized focused gates: **107 tests passed**, split into review (8),
  orbit/velocity/penalty (19), construction exclusions/range (29),
  colonies/surface/CMD (46), Nebula fast (4) and the separately executed long
  exact-continuation test (1). `focused-report.json` and per-gate logs retain
  actual exit codes, counts and wall times. The 7800-tick paid-constellation
  restore/revolution test completed; no interrupted run is counted as passing.
- Two old hostile-spacing fixtures also failed at unchanged `a9843b7`
  (`baseline-spacing-fixtures.log`): their initial-point legality did not prove
  complete-ring legality. They now retain exact 3000-unit point-boundary equality,
  paid-site blocking and abandoned-hostile exclusions using legal full-ring fixtures.
  A third old fixture placed an untyped satellite reservation on a constructor;
  it now creates actual paid planet work with source/slot metadata and preserves
  exact slot-search/spending assertions.
- Fresh all-map probe: **108 unique fixtures**, all 18 eligible planets on all four
  registered maps, and **1566 certified ring pairs**. Every default terrain plan
  equals `a9843b7` exactly. Actual production orbital updates executed 3300 ticks
  per map; every satellite travelled at least `6.599999999999273` radians, with
  analytical terrain margin at least `3.2549228645548283` units. Per-map JSON
  batches are read back, deduplicated and checked against the expected 108 count.
  See `all-maps-report.json`, `all-maps.log`, and `skirmish*-orbits.json`.
- Final Cocoa/Apple M4 GL diagnostic passed after the final simulation changes:
  four real framebuffer stages (38–76 hardware-control pixels), exact read-only
  rendering and no GL errors, `9.491999999999676` radians of travel, minimum
  terrain margin `4.638210172808613`, and maximum displacement
  `2.8939995176673037` units/tick. `gl-final/report.json`, four PNGs and
  `gl-final.log` retain the evidence. The scene includes the existing fog/background
  cards; this orbital fix does not change rendering.
- Focused compilation and `git diff --check` passed. No prices, maps, catalogue
  defaults, combat rules, serialization fields or migration speed changed.

## Limits

The replay was executed to the first demonstrated persistent block, not its full
111156-tick horizon. Full-suite and independent integration review are parent
agent gates; this worker intentionally did not run the full suite. GL fixtures
isolate orbital geometry and omit unrelated combat simulation; they are not a
human full-match playthrough. Dynamic ships can still physically block travel,
and valid detected engagement still pauses it. Arbitrary/modded terrain has a
bounded deterministic candidate search (up to 512 extra radial units); impossible
or unrepresented safe rings fail closed without purchasing new satellites.
Existing invalid overlaps or externally inserted/captured fixed obstacles are
not erased or teleported through to manufacture orbit completion.
