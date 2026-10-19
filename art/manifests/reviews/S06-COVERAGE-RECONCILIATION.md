# STAR ARMADA — S06 coverage reconciliation

## 1. Authority and reproducibility

Audit of the published S06 implementation at `4ffdc600306ecdf4f35265fca689b495e35dd3fe`
(PR #127), not the owner's stale live checkout. The original S01 inventory is a historical
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
| Approved asset | 76 | 73 S06 pending-registration specimens plus the original three integrated preview specimens |
| Shared convoy candidate | 4 | Each trade convoy maps to its faction's approved convoy candidate; not a new mesh or independently proven alias |
| Missing mesh | 27 | No approved revision supplies this required inventory row |
| Deferred texture pipeline | 10 | Eight planet surfaces and star/nebula billboards retained on their existing pipeline under the B5 scope decision |
| Outside mesh catalogue | 3 | Sky dome, jump glyph and baked menu backdrop under that same decision |
| **Total** | **120** | Every historical inventory row appears exactly once |

There are **nine** `appearance-batch-revisions` decisions covering the **73** S06 specimens,
not ten. Other historical/revision/engineering decisions in the log are different kinds.
The runtime registry has **119** rows and the authoring pipeline **three** assets; registry
row count is not coverage. Normalized identities and planned keys do not have a 1:1 relation
to the historical inventory. Existing guards, manifests and approval records are unchanged.

| Category | Approved assets | Shared candidates | Missing meshes | Deferred/outside mesh |
|---|---:|---:|---:|---:|
| Combat hull | 10 | 0 | 8 | 0 |
| Squadron | 7 | 0 | 0 | 0 |
| Logistics hull | 4 | 4 | 0 | 0 |
| Station | 30 | 0 | 10 | 0 |
| Satellite | 8 | 0 | 0 | 0 |
| Planet installation | 16 | 0 | 0 | 0 |
| Construction | 0 | 0 | 9 | 0 |
| Environment prop | 1 | 0 | 0 | 12 |
| Menu cinematic | 0 | 0 | 0 | 1 |

These are file/approval dispositions, **not proof that 80 rows are runtime-integrated**.
The four shared candidates require both real selection paths, bounds/scale and ownership
checks at S07. An existing approval is not invalidated merely because its integration is pending.

## 3. Remaining required inventory meshes

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
unbuilt constructor/colonizer. No approval authorizes silently dropping those construction rows.

The former "S10/S11 landing is the only open item" handoff is superseded. Dependencies remain:
remaining S06 art/scope closure → S07 complete opt-in integration → S08 mod/update compatibility
→ S09 platform/package/performance acceptance → S10 exact asset lock and rollback → S11 separately
authorized default switch. Preview registration, merge, default activation and release are
separate actions; **a release is not part of registering an opt-in model**.

Current task authorization is the owner's `agree. Let do this`, answering the bounded proposal
for this reconciliation and an S07 plan. It authorizes no new appearance decision, registration,
merge, tag, release, default switch, platform waiver or gameplay-stat change.

## 7. Evidence limits

The handover's categorical "LAN failure not caused by this branch" is not established by the
recorded 1/30 standalone, 1/4 suite and 0/12 control observations. Keep those receipts; do not
convert a small sample or unchanged subsystem bytes into proof of cause. This task does not
rerun timing-sensitive LAN, Blender, GL, broad-suite or platform acceptance. CI status must be
read on each published head; an older green head is not a receipt for its successor.

A cheap reproducibility blocker was reproduced on the clean audited implementation as well as
the reconciliation tree: `python3 tools/art/write_pending_sidecars.py --check` raises
`FileNotFoundError` for `tools/art/build_imperial_corvette.py`. B6 lacks per-row seed declarations
expected by the generator. No sidecar or approved input is changed here; repair belongs to a
bounded follow-up, with source/export/mesh preservation controls.
