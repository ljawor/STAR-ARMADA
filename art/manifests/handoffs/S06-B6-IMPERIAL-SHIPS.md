# S06 B6 — the Imperial ships

> **Batch complete.** Eleven of eleven rows authored, eight approved on their own review pictures.
> Everything below is the scope as settled before authoring; the outcome and the standing rules are in
> `S06-B6-IMPERIAL-SHIPS` → approvals.json (decision `s06-b6-imperial-ships-2026-10-18`) and the close-out
> prompt at `~/.hermes/cache/scratch/star-armada-s10-landing-handover-prompt.md`.

Handoff for the batch that follows B5. Everything here was **measured from the live code and the live
registry** while the scope was settled; nothing is transcribed from a plan. Probe:
`tools/art/probe_b6_scope.py` (exits 0 when the scope is settled).

## 1. The rows

Eleven Imperial bindings are ships. The other sixteen Imperial rows are B3 stations and B4 satellites
and planet installations, already authored — they are not this batch.

Legacy geometry is what each row draws **today**, read out of `render/fleet_geometry.py` through the
row's own shape string, with the probe's own measurement:

| binding | category | legacy shape | triangles | vertices | legacy envelope |
|---|---|---|---|---|---|
| `ship:imperial:battleship` | combat_hull | dagger | 3296 | 1814 | -38.450,-10.000,-80.183 .. 38.450,39.500,108.000 |
| `ship:imperial:supercapital` | combat_hull | dagger | 3296 | 1814 | same as battleship |
| `ship:imperial:cruiser` | combat_hull | cruiser | 2800 | 1542 | -29.450,-7.000,-62.940 .. 29.450,31.500,78.000 |
| `ship:imperial:corvette` | combat_hull | needle | 1552 | 858 | -16.000,-5.000,-43.601 .. 16.000,24.000,48.000 |
| `ship:imperial:frigate` | combat_hull | needle | 1552 | 858 | same as corvette |
| `ship:imperial:constructor` | construction | box | 1536 | 840 | -20.000,-7.000,-24.697 .. 20.000,26.500,24.358 |
| `ship:imperial:colonizer` | construction | box | 1536 | 840 | same as constructor |
| `ship:imperial:crew_transport` | logistics_hull | box | 1536 | 840 | same as constructor |
| `ship:imperial:trade_convoy` | logistics_hull | box | 1536 | 840 | minted by the trading system; no ShipData row |
| `ship:imperial:tie_squadron` | squadron | wedge | 1456 | 792 | -31.250,-3.240,-28.996 .. 31.250,14.000,35.000 |
| `ship:imperial:tie_bomber_squadron` | squadron | wedge | 1456 | 792 | same as tie_squadron |

Five legacy archetypes cover all eleven: `dagger` (the wedge-shaped capital), `cruiser`, `needle`
(the small combat hulls), `box` (construction and logistics) and `wedge` (the TIE squadrons).

**Open before authoring the convoy rows:** `crew_transport` and `trade_convoy` are the minted convoy
rows, not ShipData hulls. The four `trade_convoy` rows' envelope is already an open decision from the
earlier batches, so check how B2 treated the other factions' convoy rows before treating these two the
same way as the nine real hulls.

## 2. What each row owes — and the seam question, answered

The migration record said Imperial ships need a per-binding key in `ship_visual_key`. **They do not.**
Measured, not read:

* `rebel:frigate`, an authored ship that exists today, **is served** with `model_preview` on — the
  mechanism itself, as a control.
* `imperial:cruiser` is not served and not selected, but **already has a registry row**:
  `{"binding": "imperial:cruiser", "manifest": "core:imperial/cruiser", "status": "procedural_legacy"}`.
* `ship_visual_key` returns the legacy `'cruiser'` with preview **off and on**, because the manifest and
  mesh behind that row do not exist yet.
* `SHIP_KEYS`, which omits Imperial, is consulted only on the **procedural** path. `ship_binding` builds
  `f'{faction}:{role}'` for every faction; it returns early and `None` when no resolver is configured,
  which is why patching `selected_binding` proves nothing.

So each row owes exactly what every other batch produced:

* `assets/models/<identifier>.mesh.json` — the authored mesh;
* `assets/models/manifests/<identifier>.json` — the manifest: `contract: star-armada/model-manifest`,
  `contract_major: 1`, `asset: core:imperial/<kind>`, `revision`, `files.mesh {path, sha256, bytes}`,
  `export`, `coordinates: "X beam; Y up; +Z forward"`, `pivot`, `bounds`, `nominal_scale`, `roles`,
  `provenance`. Copy the shape from `assets/models/manifests/alliance_frigate.json`.

The acceptance test for the batch is the flip: with a manifest and a mesh in place and preview on,
`selected_binding('imperial:<role>')` is true and `ship_visual_key` returns `'imperial:<role>'`; with
preview off it returns the legacy shape, and nothing is selected by default.

## 3. The house flow for a batch

1. Guards **RED first** — `tests/test_alliance_blender_b6_imperial_ships.py`, run before the seed
   exists, with the failure logged.
2. Seed — `tools/art/build_b6_imperial_ships.py`, script-authoritative: one script authors every row,
   the `.blend` is derived. Envelopes come from the table above; per-row, never per-kind.
3. Wrapper — add each identifier to `tools/art/gen_export_wrappers.py` (`ASSETS`) and regenerate. The
   default expansion must stay **byte-identical** for every existing wrapper: ships stay above the
   1,800-triangle floor, and only a declared small prop may declare its own. `alliance_common.py` is
   named by every approval record as `source` — do not edit it.
4. Build and export in Blender, then the batch sheet in `art/manifests/pending/S06-BATCH-B6-IMPERIAL-
   SHIPS.json` and sidecars through `tools/art/write_pending_sidecars.py`.
5. Evidence from the real application — `tools/diag_alliance_batch_review.py` — plus the servability
   flip above; the handoff; then commit, CI, PR receipt, Telegram and the ledger in the docs PR.

Traps this session paid for: a generated file that changes for assets outside the change; a shared
helper that an approval names; a guard grepping the template for text that became a slot; and a green
focused union that is not a green CI (the two process-spawning LAN tests flake on Windows).

## Outcome — the batch as it landed

| row | runtime key | triangles | state |
|---|---|---|---|
| corvette | `imperial:corvette` | 2,348 | approved |
| TIE squadron | `imperial:fighter` | 2,136 | approved |
| TIE bomber squadron | `imperial:bomber` | 2,536 | approved |
| battleship | `imperial:battleship` | 2,468 | approved |
| supercapital | `imperial:supercapital` | 2,592 | approved |
| cruiser | `imperial:cruiser` | 2,384 | approved |
| frigate | `imperial:frigate` | 2,416 | approved |
| convoy | `imperial:convoy` | 4,748 | approved (follows the three sibling convoys) |
| constructor, colonizer | — | — | not authored; not requested |

**No seam was needed for the ships.** `ship_binding` builds `f'{faction}:{role}'` for every faction and
`ship_visual_key` asks it first, so an authored Imperial binding is served with no key change; `SHIP_KEYS`,
which omits Imperial, is consulted only on the procedural path. The **convoy** was the one real seam: both
convoy branches carried `faction in FACTIONS[1:]` and `FACTIONS` starts with `imperial`, so the gate was
extended for the convoy branches only (`6f1e5ad`) - widening the general gate would send every Imperial
hull to a key `normalize_ship_key` collapses to `box`. That trap is demonstrated, not asserted, in
`tests/test_imperial_convoy_gate.py`.

Every row carries a labelled review sheet under `artifacts/s06_alliance_batch_review/b6-*/`, each captured
with the harness's own assertions: per-pass MSAA sample and viewport, a zero-pixel legacy repeat leg,
`changed_pixels > 0`, and the subject measured on screen.

**Traps this batch paid for, in the order they were paid:** a job with an empty step list is a billing
block and not a test result; six heads were called flaky on reruns nobody read, and the real cause was a
test barrier that waited on one session index and then consumed three; recreating the GL context per pass
silently drops MSAA and fakes a sub-pixel edge diff; a guard that spawns a subprocess inside the suite is
not evidence for a red LAN job; and pins taken at write time go stale every time the row after them lands.
