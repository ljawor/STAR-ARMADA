# Remaining Galactic Imperium fleet — normal-game integration

**Status: owner-approved appearance; normal-game activation and merge authorized.**
The seven-binding pack is enabled by ordinary `main.py`, for fresh settings and the
previous shipped thirteen-pack selection. The shipped native catalogue now names
the exact seven approved meshes. No review launcher is needed to use them.
Simulation, unit data, shaders and the startup cinematic are unchanged.

`OWNER_REVIEW.json` records the owner's approval and activation clarification.
Earlier `evidence.json`/`handover.json` inactive/pending fields describe the original
review-stage candidate and are superseded for delivery, not rewritten as past facts.

## What is new

| Binding | Catalogue subject | Evaluated triangles | Export vertices |
|---|---|---:|---:|
| `imperial:bomber` | Hammer Torpedo Squadron | 2,696 | 1,420 |
| `imperial:frigate` | Lancer Frigate | 6,232 | 3,496 |
| `imperial:cruiser` | Gladiator Cruiser | 8,120 | 4,504 |
| `imperial:battleship` | Executor-class Dreadnought | 9,432 | 5,176 |
| `imperial:supercapital` | Sovereign-class Star Dreadnought | 9,968 | 5,408 |
| `imperial:colonizer` | Colonial Outreach Frigate | 3,760 | 2,064 |
| `imperial:convoy` | Imperial Crew Transport / Imperial trade convoy | 3,496 | 1,920 |

The bomber is one representative render model; its gameplay squadron remains six
members. Crew and Imperial commercial transports deliberately share the existing
`imperial:convoy` binding. No new role, class scale, radius, weapon or balance value
was introduced. The four military hulls have separately authored proportions,
armor/bridge/battery layouts and drive arrangements; they are not scaled duplicates.
Support ships use a heavy torpedo craft, habitat-bank colonizer and twin-pod hauler.

The accepted Vigil, Talon, Engineering Corps, all ten station prototypes, other
factions and core assets remain byte-identical: `protected-baseline.json` pins
560 pre-existing files. The original 13 enabled packs are preserved.

## How to play-test

**Normal game — this is the delivery entry point:**

```sh
.venv/bin/python main.py
```

The models replace their normal ship classes in new and loaded matches; gameplay
construction/progression is unchanged. Default settings enable fourteen packs.
Existing saved settings matching the previous shipped thirteen-pack list migrate
to fourteen without changing other preferences; explicitly custom lists are retained.
The owner's local saved selection is also updated. `assets/cpp/catalogue.snap`
contains all seven approved mesh paths/hashes: changing settings alone would have
left the native game drawing its cached old ship geometry.

`normal-game-catalogue.json` records exactly seven changed asset rows out of 103;
the other 96 rows, scene instances/cameras and all metadata except visual selection
are unchanged.

### Optional diagnostic inspection (not needed to play)

Run in the owner's existing checkout (close any other game instance first):

```sh
.venv/bin/python tools/play_imperium_fleet.py --focus sovereign
```

Replace the focus with `hammer`, `lancer`, `gladiator`, `executor`, `sovereign`,
`colonial`, or `transport`. This calls the **real unchanged `main.py`**, uses its
embedded native renderer, HUD, camera and ordinary input/commands, and selects a
factory-prebuilt review subject near the stock player base. The banner labels
that fixture explicitly. It is not an organic construction or progression test.

A temporary profile contains copies of all 13 accepted packs plus the candidate;
normal saves/settings/replays are neither loaded nor written. The review fails
closed on pack rejection or core fallback. On exit the temporary profile/replay
is removed. This tool remains an isolated diagnostic; ordinary `main.py` now uses
the approved models through normal settings and the shipped native catalogue.
No frozen application or Windows delivery is claimed.

For a finite real-main capture:

```sh
.venv/bin/python tools/play_imperium_fleet.py --focus sovereign --frames 90 \
  --capture /absolute/fresh/path/sovereign.png
```

## Evidence

- `gallery.png`: cropped native after frames, **individually framed**, not a
  true-size fleet comparison. No recoloring or offline look-development render.
- `native-pairs/before-after.png`: same entity, ownership tint and camera on both
  sides, production native world shader. Seven changed subjects plus unchanged
  Vigil control; close, rear and tactical views, 24 pairs / 48 raw frames.
- `native-pairs/metrics.json`: actual mesh identities/hashes, drawn lengths,
  per-view changed pixels and exact cameras. Drawn length differs by under 1%.
- A second complete native capture produced **48/48 pixel-identical images**.
  Vigil control has zero changed pixels in all three views.
- `main/{focus}.png` and `{focus}.json`: seven composed **actual-main** captures,
  each after 90 real native presents, selected ship/HUD and validated 14-pack
  configuration. `main/summary.json` enumerates all seven.
- `main/normal-profile-{before,after}.json`: hashes of six normal user-profile
  files are unchanged across the seven actual-main runs; no file contents copied.
- `build/all.json`: real Blender 5.0.1 evaluated counts/bounds, zero skipped
  degenerates, all six runtime roles, and authoring-source SHA-256s. Editable
  masters are the seven new `art/blender/imperium_*_prototype.blend` files.
- `evidence.json`: original review-stage payload/evidence hashes, preservation
  checks and then-unapproved/unactivated states. `OWNER_REVIEW.json` supersedes those
  states after approval. `committed-main/` is a fresh composed
  real-main capture from clean content commit `088e87757558e2ac0c6594487b4a9bdd965f95c9`;
  `handover.json` binds that commit and the exact reviewed source/payload hashes.
  `native-final-run.json` records the
  final externally supervised capture run; `watchdog-negative.json` proves its
  timeout path on a deliberately blocked child (not a product test failure).
- Native viewer PNGs originally used uncompressed storage. Retained PNGs were
  losslessly recompressed, with decoded pixel hashes checked before/after:
  `lossless-retention.json`. Original pixels, dimensions and colors are unchanged.

Native inspection captures omit the HUD/effects/fog and are not organic matches;
the separate `main/` captures demonstrate the composed real-game path. None of
this substitutes for the owner's physical play-test or appearance decision.
No full-suite, performance target, CI, merge, tag or release pass is implied.

## Normal-game activation verification

- `tests/test_imperium_game_activation.py` covers fresh settings, previous shipped
  thirteen-pack settings migration, preservation of explicit custom selections,
  and the actual shipped native catalogue's seven approved paths/hashes. The
  catalogue test first failed on all seven old hashes before regeneration.
- Final focused activation/asset/design/review/default-switch union: **45 tests,
  85 subtests passed**, one known baseline stale-release-lock test deselected.
  The committed baseline checker reproduces that stale lock with unchanged core
  inputs: `release-lock-preexisting-failure.json`. The older metadata-registration
  failure documented below also remains outside this feature; no full-suite pass
  is claimed.
- Ordinary `main.py --smoke`, using the normal local settings and shipped native
  catalogue (not the inspection launcher), exited zero after 30 simulation seconds:
  **SMOKE_CPP_OK**, 283 published frames. `normal-main-smoke.{json,txt}` retain
  the supervised receipt and real runtime output. This is not an organic build
  of all seven classes or an FPS acceptance claim.
- Incremental independent review passed with no security/logic blockers:
  `activation-independent-review.json`. Two nonblocking hardening suggestions
  remain recorded rather than silently claimed implemented.

## Rebuild and checks

The builder refuses existing outputs unless `--replace-own` is supplied; that
flag applies only to these new unapproved masters. Never rebuild accepted packs.

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python-exit-code 1 --python tools/art/build_imperium_fleet.py -- --replace-own
.venv/bin/python tools/art/package_imperium_fleet.py
.venv/bin/python tools/render/verify_imperium_fleet.py --include-control \
  --out /absolute/fresh/path/native-review
.venv/bin/python -m pytest -q tests/test_remaining_imperium_fleet.py \
  tests/test_imperium_capital_designs.py tests/test_imperium_support_designs.py \
  tests/test_imperium_fleet_capture.py tests/test_play_imperium_fleet.py
```

The new-feature suite passed **16 tests / 21 subtests**. The broader focused
asset/contract/registry/metadata union passed **62 tests / 130 subtests**, with
**one pre-existing failure** in
`test_runtime_asset_metadata.RuntimeMetadataTests.test_shipped_metadata_matches_source_contract_and_inventory`:
`sync_runtime_metadata.py` still pins the deleted legacy `render/renderer.py`.
The exact committed baseline script reproduces that same failure; the checker,
registration tool and test are untouched. See `metadata-preexisting-failure.json`.
The removed renderer was not restored and that unrelated tool was not changed.

Static scan of added Python source found no credential assignment, shell-exec,
eval/exec or pickle patterns. Independent review **passed**, with no blocking
security/correctness findings: `independent-review.json`. Its two nonblocking
suggestions (exclusive evidence creation and additional negative guard tests)
remain explicitly recorded; they were not silently treated as implemented.
