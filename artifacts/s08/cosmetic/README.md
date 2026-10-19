# S08 cosmetic compatibility evidence

**Result:** focused headless unittest run passed: **3 tests, 62.721 seconds**.
See `test-output.txt` for the retained, unedited final test output.

## Acceptance exercised

- **16 save/replay × visual-selection cases**, each checked at the initial boundary and after **180 production manager ticks** (181 precise snapshots per case; **2,896 comparisons**). Cases cover ordinary canonical saves, production-written v2 recordings, generated legacy saves, and generated v1 recordings. Recording starts at tick 37; continuation crosses the strategic AI cadence boundary.
- Four independent-process visual selections: legacy, approved core preview, `s08test:amber`, and `s08test:blue`. The test packs are real **7,708-triangle** uniform-scale derivatives of the approved Alliance frigate export, not placeholder triangle meshes. The derivatives use modern mesh contracts, recomputed hashes/revisions/bounds, and do **not** claim owner appearance approval. Production `asset_selection.configure`, `mesh_for`, and `AssetResolver` must validate and select them. Selected mesh hashes must distinguish all four modes.
- **Two concurrently running Python processes** use real production `LanSession.host/join`, TCP loopback handshake/readiness/start, command interception, delayed input frames, checksum barriers and `advance`. They select different validated frigate payloads. Their full authoritative state and precise save dictionaries match at tick zero and **every tick through tick 180**. Production LAN content hashes and replay content digests agree, while selected payload and resolved mesh hashes differ.
- Both peers submit actual move/hold/move/stop commands. Production recordings prove **8 accepted commands**, in player-slot order, exactly at submitted ticks plus `INPUT_DELAY`. Immediate post-consumption order types are asserted. Both ships move from their original positions and finish idle. A real AI player remains active on both peers.
- **Gameplay negative control:** a temporary gameplay mod changes `rebel_frigate` hull from 2400 to 2523. Production LAN content checking rejects mods with `LAN does not support mods`. A production-written replay accepts its matching gameplay mod. Changing that mod's hull again to 2856 makes production `PlaybackSession` reject it with `Replay content/mods are incompatible.` Compatibility checking is never disabled.

Each compared snapshot contains both `GameState.to_dict(precise=True)` and production `lan.canonical_state(manager)`, including future-affecting AI/system state. Production `precise_checksum` and replay `state_checksum` are compared too. Hash equality is **not** substituted for dictionary comparison. Failure reports include the first differing tick/path/value.

## What “legacy” means here

These are **generated compatibility fixtures, not historical user files**. The fixture is created using the current production save codec, then `runtime_state` is removed **before** historical projection fields. Removed fields include sensors, crew/boarding/recruitment state, collection points and upgrade levels; the old life-support subsystem omission is also exercised. Assertions verify production sensor/crew/upgrade/collection/life-support defaults and fresh/lazy AI/reset timer fallback.

There is no claim that missing historical AI strategy or timers can be recovered. The legacy baseline is the supported migrated state, not the pre-migration original. All visual selections must continue that same migrated input identically. The v1 recording uses production `ReplayRecorder.save` followed by explicit historical-field removal from its generated fixture. Production validation warns that original content compatibility and unknown duration cannot be verified. A final recorded command provides the conservative v1 stopping boundary; unknown commandless tails are not invented.

Canonical current saves additionally compare against the **original live manager continuation**, not only another restored copy. v2 recordings are written by production `MatchRecording.save`, loaded by `load_replay`, and played by compatibility-enabled `PlaybackSession`.

## Retained machine evidence

- `summary.json`: gate completion, fixture definition, 16 case summaries, selected payload/mesh identities and hashes, warnings, production content digests, peer process IDs, accepted commands, and observed movement outcomes.
- `tick-checksums.json`: one trajectory per verified equality pair (16 history cases plus the LAN pair). Every trajectory contains 181 production LAN/replay checksums and hashes of the full snapshots that were actually dictionary-compared. The LAN trajectory is the client side after equality to the host has been established.
- Full state traces, generated packs/mods and save/replay fixtures are disposable scratch data and are deleted on test completion. Diagnostic pack paths in the summary therefore describe the actual run, not installed user packs.

## Scope and isolation

Only `tests/test_s08_cosmetic_compatibility.py` and this artifact directory belong to this evidence work. No production code is changed by it. No main/menu initialization, settings write, real user save or replay write, GL context, full suite, hardware LAN, cross-platform network, frozen-package or S09 acceptance is claimed. Test persistence uses a `TemporaryDirectory` beneath the scratch worktree's parent; the gameplay-mod loader is redirected to that disposable fixture root and restored afterward. Visual selections are process-local; history workers run serially, while the two live LAN peers have separate globals.

## Reproduce

From the repository root, using the project's existing Python environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. \
S08_COSMETIC_EVIDENCE=artifacts/s08/cosmetic \
/Users/lukaszjawor/Downloads/Project/STAR-ARMADA/.venv/bin/python \
-m unittest test_s08_cosmetic_compatibility -v \
> artifacts/s08/cosmetic/test-output.txt 2>&1
```

Omit `S08_COSMETIC_EVIDENCE` to leave no persistent evidence output. The tests always retain real simulation assertions and production compatibility gates.
