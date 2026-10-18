# STAR ARMADA — S06 coverage reconciliation

## 1. Authority and reproducibility

Audit originally taken of the published S06 implementation at `4ffdc600306ecdf4f35265fca689b495e35dd3fe`
(PR #127), subsequently refreshed by the B7/B8/B9 authoring checkpoint; see
`../handoffs/S06-CATALOGUE-COMPLETION.md`. The original S01 inventory is a historical
snapshot and is **not rewritten**. `S06-COVERAGE-RECONCILIATION.json` beside this document
joins every inventory identity to current ship data, approval records, registry and pipeline.
Its inputs are content-addressed; it does not embed live HEAD or register anything.

Run from the repository root, with plain Python and no Blender/game imports:

```bash
python3 tools/art/reconcile_model_coverage.py --check
PYTHONPATH=tests .venv/bin/python -m unittest test_model_coverage_reconciliation test_s06_appearance_records
```

`--check` fails on report drift or an approval's source/runtime hash mismatch. For the S06
batch decisions it also checks every exporter and extra runtime/evidence-tool pin. For the
original trio it checks current source/runtime only; the existing pipeline owns historical
toolchain provenance. Rebuilding and real-renderer acceptance are not claimed here.

## 2. Reconciled counts

| Inventory disposition | Rows | Meaning |
|---|---:|---|
| Approved asset | 103 | 99 S06 batch specimens, one separately pictured S07 scaffold revision, and the original three integrated preview specimens |
| Shared convoy candidate | 4 | Each trade convoy maps to its faction's approved convoy candidate; not a new mesh or independently proven alias |
| Pending appearance | 0 | Scaffold subsequently pictured through the S07 seam and separately approved; runtime acceptance remains open |
| Deferred texture pipeline | 10 | Eight planet surfaces and star/nebula billboards retained on their existing pipeline under the B5 scope decision |
| Outside mesh catalogue | 3 | Sky dome, jump glyph and baked menu backdrop under that same decision |
| **Total** | **120** | Every historical inventory row appears exactly once |

There are **12** `appearance-batch-revisions` decisions covering the **99** S06 specimens.
The separate `appearance-scaffold-revision` decision `s07-scaffold-appearance-2026-10-18` covers one further specimen, without rewriting the original B9 eight-ship approval. Other historical/revision/engineering decisions in the log are different kinds.
The runtime registry has **119** rows and the authoring pipeline **three** assets; registry
row count is not coverage. Normalized identities and planned keys do not have a 1:1 relation
to the historical inventory. The owner's `approved` response records 26 additional pictured revisions; earlier approvals and runtime selection remain unchanged.

| Category | Approved assets | Shared candidates | Pending appearance | Deferred/outside mesh |
|---|---:|---:|---:|---:|
| Combat hull | 18 | 0 | 0 | 0 |
| Squadron | 7 | 0 | 0 | 0 |
| Logistics hull | 4 | 4 | 0 | 0 |
| Station | 40 | 0 | 0 | 0 |
| Satellite | 8 | 0 | 0 | 0 |
| Planet installation | 16 | 0 | 0 | 0 |
| Construction | 9 | 0 | 0 | 0 |
| Environment prop | 1 | 0 | 0 | 12 |
| Menu cinematic | 0 | 0 | 0 | 1 |

These are file/approval dispositions, **not proof of runtime integration**.
The four shared candidates require both real selection paths, bounds/scale and ownership
checks at S07. An existing approval is not invalidated merely because its integration is pending.

## 3. Required inventory meshes authored; 26 pictured appearances approved

All 27 rows below have Blender masters and loader-validated exports. The owner answered `approved` to the three B7/B8/B9 grids on 2026-10-18, approving exactly the 26 pictured revisions at `e9d78bcf684c2128b2e76af30f3e61cd3e952083`. The scaffold was subsequently pictured through the S07 production construction seam; the owner answered `Pictures approved` on 2026-10-18. Its separately pinned approval is `s07-scaffold-appearance-2026-10-18`, preserving the original 26-picture scope. None of these 27 rows is newly registered or runtime-accepted.

1. **Eight combat hulls:** Confederacy `battleship`, `supercapital`, `cruiser`, `frigate`,
   `corvette`; Syndicate `cruiser`, `frigate`, `corvette`.
2. **Ten Imperial orbital stations:** `command_station`, `mining_station`, `shipyard`,
   `research_station`, `defense_platform`, `sensor_station`, `trade_station`,
   `fighter_platform`, `repair_dock`, `energy_relay`.
3. **Nine construction rows:** `constructor` and `colonizer` for each of Imperial, Alliance
   (`rebel`), Confederacy and Syndicate, plus `construction:site:scaffold`.

The generic Imperial station consult already exists. No active authored manifest does **not**
mean a missing renderer seam. Likewise Imperial ships use the generic `ship_binding` path;
the convoy-only gate repair must not be widened to all Imperial procedural ship keys.

## 4. Work beyond the historical denominator

The owner-confirmed Syndicate `bomber`, `battleship` and `supercapital` are three planned keys,
not rows among those 120. They have no ship-data definitions or approved meshes at this audit.
Do not quietly omit them, count them twice, or implement gameplay statistics under an art plan.

The historical production-site decision remains: capital hulls at the shipyard, bomber at the
fighter platform. The shipyard accepts `['*']`; the fighter platform has an explicit list and
will need the new bomber data id as part of an authorized gameplay-data change. The faction
stays non-playable. Data/stat specification and its implementation boundary must be settled,
not inferred from design approval.

## 5. Scope exceptions and identity traps

- `s06-b5-scope-2026-10-17` deliberately leaves ten textures on their own pipeline and the
  two effects plus baked movie outside the mesh catalogue. This is a scoped deferral/exception,
  **not ten authored Blender assets**, and not permission to open a texture class now.
- Canonical inventory IDs are not runtime keys: e.g. `ship:imperial:tie_squadron` maps to
  `imperial:fighter`; `hardware:satellite:rebel:attack_satellite` maps to
  `rebel:attack_satellite`; both crew transport and trade convoy map to `<faction>:convoy`.
- Generated pending sidecars often prefix `ship:` even for stations/hardware, and may use
  role names rather than the source-data suffix. This audit does not rewrite those hash-bound
  records. It joins from the inventory category and live data instead. S07 must add a canonical
  mapping contract before treating those labels as an inventory index.
- Three original approved assets are already registered for opt-in preview. "Nothing is
  registered" means no **new S06 batch specimen**, not no registered asset in the repository.

## 6. Corrected completion and authorization boundary

The delivered B1–B6 sheets and their approved revisions are preserved and their completed
reviews need not be repeated while their bytes remain unchanged. **The full S06 catalogue is
not complete.** The B6 sheet contains eight approved runtime bindings, not eleven distinct
models. Its eleven inventory identities include the separate trade-convoy alias and the
then-unbuilt constructor/colonizer (now authored in pending B9). No approval authorizes silently dropping those construction rows.

The former "S10/S11 landing is the only open item" handoff is superseded. Dependencies remain:
remaining S06 art/scope closure → S07 complete opt-in integration → S08 mod/update compatibility
→ S09 platform/package/performance acceptance → S10 exact asset lock and rollback → S11 separately
authorized default switch. Preview registration, merge, default activation and release are
separate actions; **a release is not part of registering an opt-in model**.

The original reconciliation authorization was `agree. Let do this`. The owner then authorized
`Agree execute 1 , 2 and 3` and most recently requested `please continue part2. Anything pending from my end for this?`.
This increment delivers authoring/export/review evidence and stops before S07 integration.
The later `approved` response supplies appearance approval for the 26 pictured revisions only. It supplies no merge, release, default activation or invented gameplay statistics.

## 7. Evidence limits

The handover's categorical "LAN failure not caused by this branch" is not established by the
recorded 1/30 standalone, 1/4 suite and 0/12 control observations. Keep those receipts; do not
convert a small sample or unchanged subsystem bytes into proof of cause. The original planning task did not
rerun timing-sensitive LAN, Blender, GL, broad-suite or platform acceptance. The B7/B8/B9 checkpoint adds
Blender/export and diagnostic GL still evidence only; no S08/S09 acceptance follows. CI status must be
read on each published head; an older green head is not a receipt for its successor.

The original reproducibility blocker was reproduced on the clean audited implementation and
planning tree: the sidecar checker could not find `tools/art/build_imperial_corvette.py`.
**Resolved in the completion checkpoint:** B6 now declares its real shared seed and executable
per-row argument; the real checker reports zero stale sidecars. Approved source/exporter/runtime
bytes and appearance decisions remain unchanged. Failed baseline and RED/GREEN evidence are retained
under `artifacts/s06-completion/`.
