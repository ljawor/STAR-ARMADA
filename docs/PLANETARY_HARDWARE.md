# Planetary hardware and collapsible HUD

## Delivery status

Merged in PR #43 and published in v0.10.0 on October 11, 2026. The immutable release
tag points to `16502e6b2376f9527474ea5f1c302020966b042d`; publication documentation
is a separate later commit, not a moved production tag.
Independent source and final-delta reviews approved the feature. The final stable-tree
suite passed **946 tests in 397.945 seconds**. The preceding 944-test run exposed stale
fixtures and a genuine AI projected-reserve defect; both were corrected without
relaxing visibility, reserve, construction or input assertions.
Final native Cocoa wheel-input acceptance remains open because the diagnostic cannot
reliably acquire focus. The user authorized merge and release with this known gate
still open. Publication and downloaded-package verification subsequently passed:
both SHA-256 digests match GitHub, DMG/ZIP integrity passes, 26 inspected modules and
15 tracked assets match tagged source, and the read-only mounted macOS app produced
fresh screenshot/replay output with `SMOKE_OK` under an isolated HOME. The old v0.9.0
Windows package was rejected by the v0.10.0 freshness comparison.

## Controls

Selection details (left), actions/build controls (right), and mission tasks
(top-center) each have an independent **Minimize** button. The compact header
remains available to restore the panel. The preference survives selection and
viewport changes within the match. Hidden panel bodies no longer block the world;
restore headers still consume input. Surface/orbit tabs and paged lists keep
planetary production reachable at 1024×768 and 1280×800.

## Satellites

Existing attack/defense roles share six satellite slots. Paid construction reserves
capacity. Each slot rides its **own** inclined 3D orbit: the node and the inclination
are derived deterministically from `(planet_id, satellite_slot)`, and each slot adds
`orbit_shell_spacing` (160 units) to its orbit radius, so a planet's satellites no
longer share one ring. Both values are recomputed, never serialized, so they stay
stable across save/restore and agree between lockstep peers.
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
| Pulsar Cannon | 1,400 / 1,200 / 200 | 8,400-unit anti-ship beam; its own sensor range matches the gun, so it engages without a forward sensor |

All four initially require 100 crew and 24 seconds of construction. Staffing and
subsystem health affect operation. Basic colony income and recruitment remain
unchanged; surface production adds to that income exactly once through the ordinary
station economy. A planet **Trade Hub is a real market end**: convoys run between it
and any other own/allied market (hub or trade station), the destination owner is paid
on arrival, and the convoy is raidable like any other. A hub trades only while its
host world is still its owner's, so losing the colony closes the route. Ships and
orbital satellites never receive the surface generator's protection.

An operational, owner-held Surface Shield Generator also raises a **visible field**: a
translucent additive shell hugging the world just above its foundations (planet radius
times 1.04, plus 48 units). It is drawn after the fog pass so the ground overlay cannot
composite over it, depth-tested without depth writes so it never hides the hardware
inside it, and brightens while it absorbs. It deliberately stops well short of the
lowest satellite shell: the simulation shields the colony's surface buildings only, so
the field never advertises protection for satellites or ships. Ownership stays
authoritative — a world that changes hands, or a generator without crew, draws nothing.

Destroying hardware frees its slot. Completed surface hardware survives colony
capture and transfers to the new owner; the former owner's paid queue is cleared
without a refund, and obsolete combat references are removed. Surface hardware does
not count as a satellite for the existing timed-capture gate.

Commands, paid queues, attachment slots, precise orbital phase and combat cooldowns
are serialized. The AI makes conservative surface investments while retaining its
infrastructure/economic reserve. No new released-package or cross-platform claim is
implied by source implementation.

## Planetary hardware fixes (merged in #61, released in v0.11.0)

Four reported defects in the hardware above, fixed together on one branch: every
satellite on a planet rode a single ring, the Pulsar Cannon could not reach anything
worth shooting, a Trade Hub earned income but never traded, and an operational
Surface Shield Generator drew nothing.

- **#51 varied satellite orbits** — the node and inclination are derived from
  `(planet_id, satellite_slot)` and each slot adds `orbit_shell_spacing` (160 units)
  to its radius, so six satellites hold six shells and six planes. Six built
  satellites measured radii 1,095 → 1,895 units, six distinct planes, kept orbiting
  for 300 s and never closed nearer than 444.7 units (the sim's own spacing floor is
  144). Deterministic and peer-safe: nothing new is serialized.
- **#52 pulsar reach** — the emplacement already auto-fired, it simply out-ranged
  itself. The beam is now 8,400 units and the cannon's own sensor range matches the
  gun, because current detection gates every launch. Measured: engages and strips 320
  shields at 2,000 / 6,000 / 8,400 units, and holds fire at 9,000 units, where it is
  not detected. With the previous values it never fired at 6,000 or 8,000 units.
- **#53 trade hub as a market end** — a market is now a `trade_station` **or** a
  `planet_trade_hub` (`TradingSystem.markets`), a hub trades only while its host world
  is still its owner's (`market_held`), and both the spawn gate and the HUD's "needs a
  second market" line read that one source. Measured: a lone hub spawns nothing;
  hub + station spawned 18 convoys, 14 arrived, +7,500 credits over 400 s, with live
  routes running in both directions.
- **#55 visible planet shields** — a colonized world with an operational, owner-held
  generator raises the translucent additive shell described above; an abandoned
  generator, a lost colony, a foreign generator or a collapsed field draws nothing.

Each new regression was replayed against the pre-fix baseline loaded in memory
to prove it was not vacuous: that baseline used one coplanar constellation ring,
never fired past 4,200 units, did not treat a hub as a market and had no planet
shield field. These are historical control results, not current HEAD behavior.

## Executed evidence

- Whole-tree suite on this branch: **963 tests passed** in 448.274 seconds, exit 0,
  after the four fixes and their regressions; compile and whitespace checks passed.
  The branch's focused gate (satellite orbits, surface buildings, surface geometry,
  trade, construction exclusions) is 58 of those tests.
- `tools/diag_planet_shields.py`: five real Cocoa/OpenGL control-versus-field captures
  at 1280×800 and 1024×768. The field is additive, entirely contained in the projected
  shell, never hides the hardware inside it, draws **exactly zero** changed pixels once
  the generator is abandoned, and returns at full strength afterwards.
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
