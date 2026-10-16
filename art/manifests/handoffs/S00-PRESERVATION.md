# Handoff: S00 — publish and reconcile the approved prototype

Status: **review-ready.** S00's deliverables are complete on this branch: coherent tracked sources,
exports, authoring tools, loader, material fixes, tests, owner-bound approval records and selected
evidence, reconciled against current `main`. The draft PR stays **unmerged** and the production
default is unchanged.

## Base commit / branch

- Base: `16523bf0b06a39e3f77961d0c213b0af184a16b6` (`main`, the squashed performance integration from
  PR #113; tree identical to tested head `a24a4ed32f0cec6c76b40c30640a61bee6f60a2b`, version `0.15.1`).
- Branch: `feat/blender-approved-trio-checkpoint`.
- Earlier checkpoint preserved: `313f9683e9e7e4f376b05cedaeb28bb2dd300c9f` remains in this branch's
  history; reconciliation is a merge commit, not a rewrite.
- **PR and exact pushed head:** draft PR #114. Read the exact head, file list and receipts from
  GitHub — never from a local scratch path. This document's own commit is the branch head at review
  time, so a head hash cannot be baked into it.

## Prerequisites verified

- PR #113 merged; `main` carries the three performance passes and version `0.15.1`. Verified by
  reading `git` in this repository, not from a report.
- The art checkpoint and `main` were reconciled by merging `main` into this branch. Performance-owned
  files were taken from `main` (draw-local view scope in `render/renderer.py`, the Windows
  dummy-video job, `docs/BLENDER_MODEL_MIGRATION_ROADMAP.md`, `docs/GRAPHICS_DRAW_SCOPE_*.{md,json}`,
  `game/__init__.py`); the art/material delta is the 37-file set listed below.
- Verified after reconciliation: the branch's `render/renderer.py` differs from `main` **only** in the
  art hunks — every performance symbol (`_draw_view` scope setup/restore, `_draw_view_geometry`,
  projection caching, safe-eye refresh clear) is intact, and the tree delta against `main` contains no
  performance or documentation file.

## Owned files and assets/bindings

Approved bindings (the only ones this checkpoint claims): `rebel_battleship`, `rebel_frigate`, and the
Alliance-owned (`rebel`) `shipyard`.

- Sources: `art/blender/alliance_{battleship,frigate,shipyard}.blend`, `art/blender/README.md`.
- Exporters: `tools/art/build_alliance_{battleship,frigate,shipyard}.py`, `tools/art/alliance_common.py`.
- Runtime data: `assets/models/alliance_{battleship,frigate,shipyard}.mesh.json`.
- Loader/integration: `render/authored_mesh.py`, `render/faction_ships.py`,
  `render/faction_stations.py`, `render/fleet_materials.py`, `render/renderer.py` (art hunks only).
- Tests: `tests/test_alliance_blender_battleship.py`, `tests/test_alliance_blender_trio.py`,
  `tests/test_alliance_visual_slice.py`, `tests/test_ship_material_passes.py`,
  `tests/test_fleet_materials.py`, `tests/fixtures/alliance_trio_unselected.sha256.json`.
- Records and evidence: `art/manifests/approved-trio-source-hashes.json`,
  `art/manifests/approvals.json`, `artifacts/alliance_blender_trio/**`,
  `artifacts/alliance_blender_battleship/**`, `artifacts/alliance_battleship_materials/**`.

No other model, faction or catalogue entry is touched, and no gameplay/simulation file changes.

## Source authority / Blender / exporter / schema versions

- All three assets are **script-authoritative** (the exporter rebuilds the scene; it does not consume
  a hand-edited `.blend`). Preserve manual `.blend` edits before running a generator.
- Blender 5.0.1. Runtime export schema `1`. Material profile version 1, six existing roles
  (`base`, `dark`, `trim`, `accent`, `lit`, `cool`) — no new roles.
- Gameplay identifiers, balance data, collision radii and catalogue size policy are unchanged.

## Changed source and runtime hashes

Runtime exports (re-counted and re-hashed on this branch):

| Asset | SHA-256 | Bytes | Triangles |
|---|---|---:|---:|
| battleship | `57a5496c539a0252a237ef7a3671509f705308416da3f2afe0c9555ff17e9fec` | 594,859 | 8,701 |
| frigate | `045d1383ac8a774d0bb9733a598ca83777dfcdc26645e6900b9d23ee7392348c` | 358,072 | 5,128 |
| shipyard | `67d4db64c8677a8898f74d6e966a1b2476ffc721fd72c363ddbc992360630aaf` | 505,314 | 7,935 |

Source/loader/tool hashes are pinned in `art/manifests/approved-trio-source-hashes.json`, and the
owner decision is bound to the same revisions in `art/manifests/approvals.json`.

Re-measured in-game size on this branch (via `render.ship_sizes.ship_size`): battleship
`224.421225`, frigate `96.180525` world units; the shipyard keeps data radius `110`. These match the
pre-existing catalogue policy, so the authored hulls do not change visible scale, collision or
simulation fields.

## What changed visibly

Three Alliance models — a battleship, an escort frigate and an industrial shipyard — change from
procedural hulls to evaluated Blender geometry with authored material-role separation. The shipyard
carries four individually measured broad-face worklights. Nothing else in the rendered catalogue
changes: `tests/fixtures/alliance_trio_unselected.sha256.json` pins 73 unselected canonical fleet
meshes and they must hash-match.

## Owner approval

Recorded in `art/manifests/approvals.json` as decision `approved-trio-2026-10-16`, owner Lukasz Jawor:
the shown Blender geometry and material direction is approved for **exactly** `rebel_battleship`,
`rebel_frigate` and the Alliance-owned `shipyard`. Evidence references are listed in that manifest and
resolved by committed files. The decision explicitly does **not** approve any other model/faction, a
generic registry, a production default switch, or Windows/packaged acceptance. Approval is bound to
the revisions above; a meaningful visual revision invalidates it until reviewed again.

## Tests and commands actually executed

On the reconciled tree (this branch), with the real video driver:

```
PYTHONPATH=tests:. .venv/bin/python -m unittest test_alliance_blender_trio \
  test_alliance_blender_battleship test_alliance_visual_slice test_ship_material_passes \
  test_fleet_materials test_faction_ships test_ship_sizes test_detmath test_draw_view_scope
```

Result: **63 tests, 0 failures, 0 errors, 0 skips** (`OK`, 7.0 s). This is a focused re-verification of
the reconciliation, not a new full-suite acceptance.

Retained earlier receipts, unchanged by this reconciliation: 79 focused tests across ten modules,
181 equal per-tick combat state samples over 180 ticks, 37 weapon-fire events per variant, four
worklights measured at 185/260/276/413 warm pixels, byte-exact repeated exports, and 660 user-data
files unchanged (`artifacts/alliance_blender_trio/verification.json`, `rebuild-verification.json`,
`worklight-pixels.json`).

Retained failed attempts, not hidden: the new asset contract was RED before the assets/loader existed;
a broad-disc ray test was RED on buried drive emitters and GREEN after the geometry fix
(`artifacts/alliance_blender_trio/evidence/red-tests.log`, `red-buried-drives.log`).

## Actual-game captures/video

Production pygame/OpenGL captures, not Blender renders: `artifacts/alliance_blender_trio/`
(`three-asset-review.jpg`, `trio-in-game.png`, `before-after-contact-sheet.jpg`,
`before-after-aft-drives.jpg`, `before-after-motion.mp4`, `pixel-checks/`), plus the battleship
material/geometry comparisons in `artifacts/alliance_battleship_materials/` and
`artifacts/alliance_blender_battleship/`. Capture/probe recipes are committed under
`artifacts/alliance_blender_trio/evidence/`. Raw per-frame sets and the showcase reel are deliberately
not committed (roadmap storage rule) and are named in `art/blender/README.md` §6.

## Performance / packaging / platform evidence and limitations

- Evidence is macOS / Apple M4 / Cocoa / OpenGL 2.1 Metal at 1280×800 with real 4× MSAA, normal fog.
- No Windows-native graphics, frozen/packaged build, or clean-install acceptance exists for the trio.
- No interactive FPS or performance target is claimed here. The merged performance work is separate
  and remains "headroom", not an art upgrade.
- Specimens were placed with real factory entities and real combat commands, not a paid construction
  walkthrough.

## User-data preservation and unrelated work retained

- User data, settings, balances, campaign progress and replays were not touched by this
  reconciliation. All work happened in a separate git worktree.
- The original working tree at `~/Downloads/Project/STAR-ARMADA` is **unchanged**; its 220 dirty and
  untracked files were hashed to a snapshot before any edit.
- Identified but deliberately **not** staged here, because it is unrelated to S00 and would bundle
  another workstream: `docs/UNREAL_PORT.md`, `tools/capture_showcase.py`, `artifacts/showcase/`,
  `artifacts/fight_poster.png`, `artifacts/star_armada_fight.mp4`, and the raw per-iteration capture
  sets under `artifacts/`. These exist only in the local working tree and are not published anywhere.
  **They need an owner decision** — they will be lost if that tree is deleted.

## Open issues, blockers and decisions required

1. **Activation boundary (blocker for any art merge).** The trio is selected by hardcoded identity
   checks in `render/faction_ships.py` and `render/faction_stations.py` with no persisted switch. S02
   (contract) and S04 (gated registry path) must replace this before a production art merge. This
   checkpoint is a preview prototype and must stay draft until then.
2. **Approval coverage.** Approval exists for three bindings only. Every other catalogue row is
   pending (S01/S06).
3. **Acceptance debt, unresolved.** The earlier 1,671-test art-integrated run had one LAN recovery
   `tick 6 != 8` failure; isolated repetitions did not reproduce it. It is not classified as fixed and
   no full suite of this checkpoint has been run.
4. **Unpublished unrelated local work** listed above awaits an owner decision.

## Next executable step and its acceptance criteria

**S01 — inventory and batch design.** Generate the rendered-model inventory from both data and
renderer dispatch, covering combat hulls, squadrons, logistics, faction station variants,
construction, satellites, planet installations, environment props and campaign props, plus an explicit
scope decision for non-model visuals (planets, terrain, sky, particles, screen-space effects). Each row
must end in an approved Blender asset/binding or an explicit owner-approved exception.

Acceptance: owner-reviewed coverage matrix with no silently omitted dispatch path, settled scope
exceptions and faction/reuse identities, and an agreed first batch order. S01 does **not** authorize
building new models, and it cannot be closed by an AI's own judgement.

No merge, tag, release, user-data cleanup or broader catalogue approval is implied by this checkpoint.
