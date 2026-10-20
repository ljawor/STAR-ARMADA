# Talon and Engineering Corps — local appearance review

## Scope and review boundary

The owner approved the Shipyard/Mining Station pair and requested these two next. Their exact words and reviewed hashes are in `../imperial-industry-prototypes/OWNER_REVIEW.json`. The new flight pair is locally committed for appearance review; no new push/PR update, merge or release has been performed.

Accepted Vigil, Command Center, Shipyard and Mining Station mesh/source bytes remain unchanged. No production renderer/shader, core catalogue mesh, gameplay data, squadron membership, construction ability or balance file was modified.

## Original designs

- **Talon Interceptor:** spear fuselage, swept clipped-delta wings with thick roots, forward weapon claws/open muzzles, dark angular cockpit, graphite intakes, armor layering and twin hollow exhausts with restrained cool emitters. 4,304 triangles / 2,252 vertices / 70 editable parts.
- **Engineering Corps Corvette:** stout noncombat working tug with offset raised operations cabin, two articulated hydraulic grapple arms around an open work cradle, workshop pods, component carriers, radiator banks, worklights and hollow stern drives. 8,420 triangles / 4,772 vertices / 301 editable parts.

The existing renderer draws one representative fighter mesh per squadron entity; this changes that representative craft, **not** the six-member gameplay squadron or its formation implementation.

## Play

Desktop/repository launchers:

- `Play Talon Interceptor Squadron.command`
- `Play Engineering Corps Corvette.command`

Each starts a real stock Imperial skirmish with the appropriate existing unit selected/framed; all six prototype packs are enabled. The new pair's starting camera faces their forward quarter relative to the actual spawn heading. Accepted earlier focus launchers retain their framing. Normal controls and gameplay remain available.

The isolated profile is `~/Library/Application Support/STAR ARMADA/Vigil Prototype/`. Normal saves/settings and the installed app are untouched. Only the existing mining-review focus adds a prebuilt review mine; these flight launchers use the stock starting fleet.

## Actual-game evidence

- `before-after.jpg`: same-camera/equal-crop close comparisons, existing core model versus new original prototype.
- `talon/` and `engineer/`: full close/rear/tactical PNG pairs and reports, plus final actual-main-loop gameplay frames and diagnostics; also in `full-resolution-pairs.zip`.
- `provenance.json`: comparison and final-gameplay producing commits, source/runtime/renderer hashes and evidence pins. Comparisons were produced before the launcher-only camera correction; the renderer, diagnostic capture tool and asset bytes were unchanged. Final gameplay screenshots exercise the corrected committed launcher.
- Actual 4× MSAA, shared per-view cameras, unchanged simulation hashes, stable nominal lengths and nonzero pixel differences in all three comparison views.
- All six packs accepted in both actual-game launch checks. Talon HUD retains `FIGHTERS 6/6`; Engineering HUD retains orbital construction options.
- `PYTHONPATH=tests .venv/bin/python -m unittest test_vigil_prototype test_command_prototype test_industry_prototypes test_flight_prototypes -v`: **7 passed**. Real-loader one-binding scope/reversion, accepted model/sibling preservation, isolated profile, mine-review isolation and heading-relative startup framing covered.
- Existing normal user-file hashes remained unchanged after verification.

No fleet-performance, full-suite, package or Windows graphics acceptance is claimed. New pair's appearance approval is the next gate.
