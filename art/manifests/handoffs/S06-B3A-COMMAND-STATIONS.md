# Handoff: S06 B3a — faction command stations (3 stations)

**Status: review-ready, pending owner appearance approval. Not an approval record, not a
registry entry, not a runtime manifest, and no asset here is selected in production.**
Nothing in this batch is merged, released or switched on by default; the PR stays a draft.

This is the first slice of the station chapter of S06 (B3). It authors the three faction
**command stations** — the largest, most visible structure in each fleet — inside their
bindings' legacy procedural extents. The remaining station kinds, the ten imperial
stations and `rebel:shipyard` are named in "Not in this batch, deliberately" below.

## Owned files and bindings

| Binding | Identifier | Station kind | Triangles | Legacy triangles | Bytes |
|---|---|---|---|---|---|
| `rebel:command_station` | `alliance_command_station` | `command_station` | 3,172 | 2,112 | 219,115 |
| `confederacy:command_station` | `legion_command_station` | `command_station` | 2,161 | 1,616 | 131,301 |
| `syndicate:command_station` | `syndicate_command_station` | `command_station` | 3,208 | 1,120 | 221,182 |

Each row is 1.3×–2.9× the procedural layout it would replace, inside the owner-set 11,500
triangle station advisory budget (`art/manifests/pipeline.json`) and the runtime loader's
hard 12,000 / 10,000 / 2,000,000-byte caps (`render/authored_mesh.py`).

Files owned by this batch:

* `tools/art/build_b3_stations.py` — the initial authoring seed for all three masters, plus
  the station vocabulary (`torus`, `ringy`, `strut`, `bank`, `collar`) and the build-time
  bounds report. **Initial authoring recipes only**; each editable `.blend` is authoritative
  afterwards, and the seed refuses to overwrite one without `--replace-seed`.
* `tools/art/export_{alliance,legion,syndicate}_command_station.py` — generated from
  `tools/art/templates/export_wrapper.tmpl` by `tools/art/gen_export_wrappers.py`, whose
  `ASSETS` table now carries the three station rows with their envelopes and length floors.
* `art/blender/{alliance,legion,syndicate}_command_station.blend` — the editable masters.
* `assets/models/{alliance,legion,syndicate}_command_station.mesh.json` — the runtime exports.
* `art/manifests/pending/S06-BATCH-B3A-COMMAND-STATIONS.json` — the batch sheet, and the
  three per-asset sidecars the writer generates from it.
* `tests/test_alliance_blender_b3_stations.py` — 19 cheap per-station guards.
* `tools/diag_alliance_batch_review.py` — the shared batch review harness, extended for
  station rows (see "Review-harness corrections").

## What each station is

Three different structures sharing one kit of station primitives, not one body in three
paints. The kit is deliberately *not* the hull kit: a station is radial structure, so it
needs rings on a vertical axis, members between arbitrary points, and rows of small blocks.

* **`alliance_command_station` — a ring habitat.** Twin elliptical bands (96 wide, 59 deep —
  the binding is nowhere near circular) on twelve trusses with lateral stays, an armoured
  hub drum and belt, a lit command tower with a crown rim and mast, eight habitation modules
  around the inboard deck, machinery and vent banks on the hub roof, ring collars at the
  cardinal points of the outer band, four open docking ports on the hub roof, and a keel
  plate and strakes under the band.
* **`legion_command_station` — a hex platform under an angular citadel.** A six-sided
  platform ring with an accent rim and a guide strip, a long wedge keep with a dorsal crest,
  flank plating and window bands, two buttresses and two lower stays, twin work booms ending
  in lit pods and outriggers on sponsons, a mast spine with a sensor dish forward of the
  crest, open platform ports, eight machinery blocks on the platform deck and a base plate.
* **`syndicate_command_station` — a scaffolded redoubt.** A four-stage offset tower with a
  belt, an accent ring, a lit head, a mast and cap; twelve scrapped hull sections bolted
  round it at mixed heights and angles with bolt plates; a gantry frame over the tower; a
  starboard boom to a lit salvage cab and a left spur to a lit cab; a crane mast, jib and
  block; two ring collars; open mast and cab ports; three scaffold rails with posts; and a
  keel deck and strake.

## Authored inside the legacy extent — to the extent, not merely inside it

The legacy procedural station fills its declared box exactly, and the review harness compares
the candidate footprint against the legacy *station mesh* within 1 % per axis. A replacement
that merely fits the envelope still fails — it would frame and collide differently — so every
extreme was authored onto the legacy extent:

| Binding | Legacy extent (lo → hi) | Authored extent | Worst axis delta |
|---|---|---|---|
| `rebel:command_station` | `[-48, -6.8, -29.6] → [48, 26.48, 29.6]` | same | 0.000 |
| `confederacy:command_station` | `[-53.8231, -6.0, -38.4] → [53.8231, 41.6, 60.0]` | `[-53.8, -6.0, -38.0] → [53.8, 41.6, 60.0]` | 0.4 (0.4 %) |
| `syndicate:command_station` | `[-52.1606, -15.2, -53.6606] → [48.0, 45.6, 38.4883]` | `[-52.019, -15.2, -53.66] → [48.0, 45.6, 38.400]` | 0.142 (0.14 %) |

`assets/data/stations/stations.json` is untouched: `command_station` still carries
`radius: 130`, and the mesh Z extent of each station is far above its exported length floor,
so the catalogue's class scale, contact distance and collision radius are all unchanged. No
simulation field, gameplay id or checksum is affected: a station mesh is render-only and the
specimen is not selectable.

## Not in this batch, deliberately

* **The ten imperial stations.** `render.fleet_geometry.station_mesh(data_id, faction)`
  dispatches them straight to `_station_mesh(did)` with no `asset_selection.mesh_for` seam, so
  authoring them is a renderer change — an owner decision, not an asset batch. Recorded in
  `art/manifests/handoffs/S06-B3-STATIONS-PLAN.md` and asserted by
  `test_the_imperial_station_rows_still_have_no_seam`.
* **`rebel:shipyard`.** Already delivered as the approved trio's `core` asset
  `alliance_shipyard`; re-authoring it would collide with an owner-approved revision.
* **The remaining 27 faction station rows** (nine other kinds × three families): `mining_station`,
  `research_station`, `defense_platform`, `sensor_station`, `trade_station`,
  `fighter_platform`, and the planet installations and satellites. All sit behind the same
  seam and are the next slices.

## Source authority / versions

* Authority: `blend` (script-authored first, editable `.blend` authoritative afterwards);
  the seed is an initial recipe and refuses to overwrite a master without `--replace-seed`.
* Blender: 5.0.1 headless, `--background --python-exit-code 1`.
* Export is export-only: each generated wrapper opens the declared master, validates the
  source is the declared one, and contains no `save_as_mainfile`/`save_mainfile`.
* No proprietary geometry or textures; all three designs are original.

## Hashes of this revision

| Asset | Master `.blend` sha256 | Runtime `.mesh.json` sha256 |
|---|---|---|
| alliance_command_station | `a2377c1d8f815258791345869c005e95efe13ca99c99c5ba90ede8598ff0fd4c` | `ee9790e6f95bdd2a5e0650fd4eb1d1d5496637b32956929a9c6d50df0ee8c93c` |
| legion_command_station | `159e8288e6341e329046591475875e17a1446466eb23c1dcd1b3b456e880ec66` | `a9f6bdb8259217f1649ee47b44809cef79ac4c3369c680325f8e5c874a0cd0d8` |
| syndicate_command_station | `f3342e0ed63c8b730d91bafdca9c8d7d0bbf9bc0bfe7e54293bff792e27e4d17` | `edb2fc8369f6a0d8d4d40020ac538b553659a5066face5ef3b1273b6afea778a` |

## What changed visibly

Each station is now a drawn structure instead of the procedural primitive assembly: real
ring bands and trusses (Alliance), a citadel with a crest, buttresses and booms (Legion), a
bolted wreck belt with gantries and cranes (Syndicate), at 1.3×–2.9× the triangle count.
**The owner judges this from the captures, not from this paragraph** — see "Actual-game
captures and recipe" for the contact sheet and the per-role ablations.

## Review-harness corrections made in this batch

The shared harness needed four changes before it could review a station at all; each is a
fact about stations that will recur in the next station slice:

1. **A station row spawns a station.** `placements_for` emitted `kind='ship'` for every
   asset; the shared scene's `spawn_station` path and `capture_slice.geometry`'s
   `station_bounds` branch already existed, so the row now carries `station_kind` and the
   placement follows it.
2. **A station has no `ship_size` class.** The length check would have resolved a station
   binding through a ship key it does not have. It now compares the *station footprint*,
   legacy against candidate, per axis, within the recorded 1 % review tolerance.
3. **Union-safe station cameras are scaled by the game's station scale.** A station is
   framed from `radius / 50` (130 / 50 here) of its nominal footprint; framing a 96-unit-wide
   station like a 96-unit-long ship puts the eye inside the union and
   `capture_slice.camera_check` refuses the capture, which is what it did on the first run.
4. **The batch overview is a station overview.** `first_z 1200`, `spacing 600`,
   `distance 1100` — the ship row's `spacing 300` / `distance 620` would overlap three
   stations of this size.

5. **A station row must be owned by a player of its own faction.** The first full run
   reported `changed_percent: 0.0` and `bbox: null` on the confederacy and syndicate rows
   while the rebel row changed by 26.8 % — the injection had never reached the renderer.
   The renderer resolves a *station's* faction from its **owner**
   (`owner_faction(state, e.owner)` in its station draw), and every row was owned by
   player 0, the rebel player: so all three rows drew the *Alliance* command station, the
   seam was queried as `rebel:command_station`, and no candidate matched it. A ship row is
   immune to this (its visual key comes from the ship data row, which is why the B2 batch's
   eight hulls all measured non-zero), so it is a station-specific trap. The scene now
   holds a player of the specimen's faction (`players_for`) and re-owns the specimen with
   it, which is the situation the binding describes: a station built by a player of that
   faction. After the fix the two rows measure 40.1 % and 40.3 % at close range.
6. **A row label must be unique per asset.** All three rows carried the label
   `command station`, so each station's captures overwrote the previous one's on disk and
   the evidence directory held only the last station's frames. Labels are now
   `alliance command station`, `legion command station`, `syndicate command station`.

The build side gained a **build-time bounds report** (`report_bounds` in the seed): evaluated
`lo`/`hi` per axis, every breach, and the object that reaches each extreme, printed on the
run that authors the master. Iterating through the exporter instead names one axis at a time
and costs a full Blender build per round trip; this batch burned five such builds before the
report existed, and one run afterwards.

## Review metrics (the numbers behind the captures)

`artifacts/s06_alliance_batch_review/b3a-command-stations/metrics.json`, one row per
binding. Changed pixels are the same camera, same state, candidate injected through the
seam only, so they are a measurement of the replacement and nothing else.

| Binding | close | rear | tactical | common-scale | ablations (accent / dark / cool) |
|---|---|---|---|---|---|
| `rebel:command_station` | 26.76 % | 20.82 % | 1.54 % | 1.03 % | 7,081 / 23,797 / 6,327 px |
| `confederacy:command_station` | 40.10 % | 33.39 % | 2.06 % | 1.72 % | 2,010 / 42,031 / 892 px |
| `syndicate:command_station` | 40.28 % | 38.53 % | 2.50 % | 1.79 % | 1,532 / 59,080 / 269 px |

* Every role ablation is non-zero from the camera that can see it, so the owner paint and
  the material roles reach pixels on all three stations.
* `restored_changed_pixels = 0` for all three: with the seam switched back off the frame
  returns pixel-identical to the legacy baseline, so nothing else moved.
* The baseline and candidate **geometry** differ for all three rows, and the union-safe
  camera is computed against both.
* The batch overview (three stations at one shared scale) changes 137,558 pixels.
* Motion: 150 frames at 30 fps, 5 s, on `rebel:command_station`; the paired before/after
  sample timeline is equal, i.e. the candidate is render-only and the simulation did not
  move. The clip is `alliance command station-after-motion.mp4` in the evidence directory.
* 40 PNGs are retained: eight views per station (before and after), three role ablations per
  station, the restored frame, the overview pair and the contact sheet.

## Owner approval

The only thing needed from the owner is the one-line answer he has already been asked for on
the B1 and B2 sheets: **do these three command stations look like the right direction, and
may the remaining station kinds be authored the same way?** No merge, release or
production-default switch is implied by a yes; each revision still lands only after a
separate landing decision.

## Tests and commands actually executed

* `PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b3_stations` →
  **Ran 19 tests, OK.**
* The shared guard set (`test_alliance_blender_b3_stations`, `…_b2_squadron`, `…_b1_combat`,
  `…_cruiser`, `…_trio`, `…_battleship`, `test_asset_contract`, `test_model_pipeline`,
  `test_generic_model_preview`, `test_model_context_lifecycle`) → **Ran 93 tests, OK.**
* Seeding: Blender 5.0.1, `--all --replace-seed` → `SEED_OK` ×3, no `BREACH` line.
* Exporting: all three wrappers exit 0, each printing `GAME_EXPORT` with bounds equal to the
  legacy extent and its own triangle count.
* Sidecars: `tools/art/write_pending_sidecars.py` then `--check` → three new sidecars, no
  stale ones.
* Batch review: `tools/diag_alliance_batch_review.py --spec …B3A… --out …b3a-command-stations`
  → see the metrics above and the contact sheet in that directory.

## Actual-game captures and recipe

The review harness renders the **real application** with the candidate injected through
`render.asset_selection` only — one process per batch, `SDL_VIDEODRIVER` unset so the real
driver is used, 1280×800, four views per station (`close`, `rear`, `tactical`,
`common-scale`) plus a single-scale batch overview, a motion clip per station, and a per-role
ablation for every material role so a flat-looking station cannot pass unseen. The evidence
directory carries `metrics.json`, the capture PNGs, the contact sheet and the motion clips;
every image is stamped `UNAPPROVED REVIEW ONLY — pending owner approval`.

## Performance / packaging / platform

Station meshes are render-only. This batch touches no `game/`, `render/`, `assets/data/`,
`docs/` or `scripts/` file, changes no simulation input, and adds nothing to the shipped
package: the masters and exports are art, the seed and wrappers are authoring tools. CI runs
on the branch are the platform gate; no package acceptance is claimed from a green PR here.

## Open issues, blockers and decisions required

1. **Appearance approval** for these three stations (and the eleven earlier S06 specimens).
2. **The imperial seam.** Authoring the ten imperial stations needs an owner decision about a
   `mesh_for` seam in `render/fleet_geometry.station_mesh`; until then they cannot be authored
   as an asset batch.
3. **The remaining 27 faction station rows** — same seam, awaiting the answer to (1).

## Status of this batch vs. the S06 scope

| Batch | Scope | Bindings | Assets | State |
|---|---|---|---|---|
| B1 | Alliance combat (cruiser + corvette + carrier) | 3 | 3 | authored, exported, reviewed — pending approval |
| B2 | Squadrons + logistics | 15 (8 modelled, 3 shared-source, 4 `trade_convoy`) | 8 | authored, exported, reviewed — pending approval |
| B3a | Faction command stations | 3 | 3 | authored, exported, reviewed — pending approval |
| B3b | Remaining faction stations + planet installations | 27 + 24 | 0 | not started |
| B3c | Imperial stations | 10 | 0 | blocked on a renderer decision |
| B4–B5 | Environment props, campaign props | — | 0 | not started |
