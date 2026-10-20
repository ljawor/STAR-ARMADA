# Imperial industrial stations — LOCAL appearance review

## Review boundary

The owner accepted the Command Center and asked for the Shipyard and Mining Station next, **before adding these additions to the PR**. These changes are committed locally only. No new push, PR update, merge or release is authorized. Existing draft PR #141 contains the earlier Vigil/Command Center work; the new industry additions await the owner's review.

The accepted Vigil and Command Center mesh, Blender source, builder and production renderer hashes remain unchanged. The Command Center's acceptance is recorded verbatim in `../command-center-prototype/OWNER_REVIEW.json`; it does not approve these new stations.

## Original designs

- **Shipyard:** open fore/top assembly bay; five paired articulated gantries, thick cradle ribs and logistics decks; aft factory, offset observation tower, tank/thermal machinery rafts and cargo cranes. 10,988 triangles, 6,864 vertices, 685 editable parts.
- **Mining Station:** asymmetric armored processing head, raised operations cabin, open ribbed hopper, pressure vessels, loading conveyor/platform, radiator banks and hanging three-jaw hydraulic crusher. 8,564 triangles, 4,888 vertices, 318 editable parts.

Both use the existing six-role shader, original binding envelopes and normal runtime scale. No proprietary assets, core meshes, global renderer/shader edits, game data, balance changes or runtime Blender dependency.

## Play

Desktop/repository launchers:

- `Play Imperial Shipyard.command`: stock Imperial skirmish, starting Shipyard selected/framed.
- `Play Imperial Mining Station.command`: same rules and stock-map copy with **one additional prebuilt mine for immediate visual review**, selected/framed. This is an isolated review fixture, not an organic construction/placement acceptance claim.

All four packs are enabled, including the unchanged Vigil and Command Center. The other launchers still focus their original subject. Persistence remains isolated under `~/Library/Application Support/STAR ARMADA/Vigil Prototype/`; the installed app and normal saves/settings are not replaced.

## Actual-game evidence

- `before-after.jpg`: same-camera, equal-crop close comparisons for both models. Full frames and rear/tactical pairs under `shipyard/` and `mining/`, also in `full-resolution-pairs.zip`.
- Each `report.json`: production shader, actual 4× MSAA, shared cameras, unchanged before/after simulation digest, nonzero close/rear/tactical pixel deltas. The accepted prototype packs stay enabled on both sides; only the reviewed station is added on the candidate side.
- Each `gameplay.png`/`gameplay.json`: real main-loop launch, all four packs accepted, appropriate station selected and usable HUD.
- `provenance.json`: producing local code commit, source/runtime/renderer hashes, evidence pins and limitations. Full-frame diagnostic views contain upper-edge background bands in both baseline and candidate; renderer code was unchanged. The main-loop captures are retained separately.

Focused checks: `PYTHONPATH=tests .venv/bin/python -m unittest test_vigil_prototype test_command_prototype test_industry_prototypes -v` — **5 passed**. Checks include real loader scope/reversion, unchanged accepted models, unaffected siblings, isolated profile and mine-review map copy/spawn. Normal existing user-file hashes remained unchanged after verification.

No fleet-performance claim, full-suite gate, package rebuild or platform acceptance in this visual iteration. Appearance review is the next gate.
