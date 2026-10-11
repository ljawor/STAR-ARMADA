# Planetary hardware and collapsible HUD

## Delivery status

Implemented for the v0.10.0 source increment; release preparation is in progress.
Independent source and final-delta reviews approved the feature. The final stable-tree
suite passed **946 tests in 397.945 seconds**. The preceding 944-test run exposed stale
fixtures and a genuine AI projected-reserve defect; both were corrected without
relaxing visibility, reserve, construction or input assertions.
Final native Cocoa wheel-input acceptance remains open because the diagnostic cannot
reliably acquire focus. The user authorized merge and release with this known gate
still open; publication and downloaded-package verification are separate gates.

## Controls

Selection details (left), actions/build controls (right), and mission tasks
(top-center) each have an independent **Minimize** button. The compact header
remains available to restore the panel. The preference survives selection and
viewport changes within the match. Hidden panel bodies no longer block the world;
restore headers still consume input. Surface/orbit tabs and paged lists keep
planetary production reachable at 1024×768 and 1280×800.

## Satellites

Existing attack/defense roles share six satellite slots. Paid construction reserves
capacity. Positions now travel on an inclined 3D orbit, not a fixed flat ring.
Valid, detected, in-range engagement pauses orbital movement; normal weapons or
missile interception execute, then orbital travel resumes when no eligible threat
remains. Physical obstructions can hold an orbit; satellites do not phase through
other structures. Abandoned hardware does not orbit or fire.

Initial configurable proposals: 600 credits / 700 materials / 150 energy and
100 crew per satellite, 5,500 hull plus four 1,000-shield quadrants, 15 shield
regeneration, 22-second construction. Orbit speed is 0.06 radians/second and
inclination 0.55 radians. These are tuning defaults, not statistical balance claims.

## Planetary surface buildings

Owned non-gas colonies have **six separate surface slots**, in addition to the
satellite slots. Any free slot can host any building, including repeated types.
The menu queues a serialized `build_planet_building` command; the authoritative
manager reserves and pays for the first free slot. Existing construction exclusion
around hostile command centers is enforced before payment and at completion.
Buildings have solid outward-oriented meshes on the actual planet surface.

| Building | Credits / materials / energy | Supplemental output or effect |
|---|---|---|
| Resource Extractor | 800 / 600 / 200 | +3 materials and +1 energy per second |
| Trade Hub | 900 / 500 / 200 | +4 credits per second |
| Surface Shield Generator | 1,100 / 900 / 200 | Shared protection for this colony's surface buildings only |
| Pulsar Cannon | 1,400 / 1,200 / 200 | Long-range anti-ship beam; requires current detection |

All four initially require 100 crew and 24 seconds of construction. Staffing and
subsystem health affect operation. Basic colony income and recruitment remain
unchanged; surface production adds to that income exactly once through the ordinary
station economy. Trade hubs provide income rather than spawning a second convoy
system. Ships and orbital satellites never receive the surface generator's protection.

Destroying hardware frees its slot. Completed surface hardware survives colony
capture and transfers to the new owner; the former owner's paid queue is cleared
without a refund, and obsolete combat references are removed. Surface hardware does
not count as a satellite for the existing timed-capture gate.

Commands, paid queues, attachment slots, precise orbital phase and combat cooldowns
are serialized. The AI makes conservative surface investments while retaining its
infrastructure/economic reserve. No new released-package or cross-platform claim is
implied by source implementation.

## Executed evidence

- Final whole-tree suite: **946 tests passed**, after the independent reserve/fixture
  review; compile and whitespace checks passed.
- Independent replay reconstruction probes rejected duplicate live/queued slot
  occupancy in either entity order, while preserving separate domains/planets and
  dead-slot reuse. AI differential probes reproduced the old credit/material reserve
  failures and confirmed paid surplus purchases remain possible after the fix.
- 67 focused simulation, HUD, geometry, contact, camera and existing faction tests
  passed after production contact integration.
- `tools/diag_collapsible_hud.py`: 18 real Cocoa/OpenGL frames across both resolutions;
  actual SDL input, surface catalogue paging, minimize/restore, text containment,
  command-before-payment, stale controls and read-only simulation assertions passed.
- `tools/diag_planet_buildings.py`: 10 hardware/slot captures across both resolutions;
  real paid manager completion, shaded hardware versus draw-disabled controls,
  outward sphere clearance, visible slot differences and immutable rendering passed.
- Exact JSON-normalized `precise=True` state continuation is tested every tick through
  paid construction, output, capture, active orbital combat and missile interception.

These are controlled fixtures, not natural campaign playthroughs or full-match balance
acceptance. Post-review hardware GL rerun passed all ten captures. The original
18-capture HUD input run passed, but final focus-dependent reruns did not complete;
historical success is not final-tree native input acceptance. This limitation remains
disclosed despite release authorization. Native Windows and mixed-platform interactive
acceptance are not established by these macOS probes.
