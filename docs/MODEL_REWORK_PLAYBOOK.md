# Imperial model rework — how we do it

Working playbook for replacing STAR ARMADA's Imperial (Galactic Imperium) ships and stations with
original, Blender-authored models in the Homeworld-2 design language. It records what we build, what
we test, what we deliberately do not test, and how each unit is presented for approval.

Use it as the brief for the next chat. The ships batch is the remaining work (see §10).

---

## 1. Where the work stands

| Batch | Units | Status |
|---|---|---|
| Flight prototypes | `vigil`, `imperium-command`, `imperium-shipyard`, `imperium-mining`, `imperium-talon`, `imperium-engineer` | approved and shipped (before this series) |
| Station trio | research station, defence platform, sensor station | approved, in PR #142 |
| Dockyard quartet | trade station, fighter dock, repair station, energy relay | approved, in PR #142 |
| Stations static | cosmetic station yaw frozen at 0 | in review on the branch |

Vehicle for the whole series: branch `feat/imperial-approved-defaults`, PR **#142**. Each approved
model and its default-switch entry land there together.

Shipped default is now **thirteen** packs in `DEFAULT_SETTINGS["visual_packs"]` (`render/menus.py`),
mirrored in the owner's gitignored `saves/settings.json`.

## 2. Ground rules

- **Original art only.** Homeworld 2 is a silhouette reference; no copied, ripped or purchased
  geometry, textures or layouts.
- **Prototype packs, never core overwrite.** Each unit ships as `visual_packs/<pack>/` with
  `visual-pack.json`, `SOURCE.md`, `assets/models/<stem>.mesh.json` and
  `assets/models/manifests/<stem>.json`. Never touch `assets/models/registry.json`,
  `art/manifests/pipeline.json`, receipts or the core catalogue for a prototype.
- **The binding's envelope is preserved exactly.** In-game length, collision radii, ship sizes and
  `state_sha256` stay untouched. A deliberate size change is a separate approval.
- **The owner judges in the running game**, not from a render sheet. Capture frames only prepare the
  session; they are not the review.
- **Minimal gates + `[skip ci]`** — accepted because only art moves. Never describe CI as green when
  it was skipped.
- **Decisions are recorded with the owner's words verbatim** in
  `art/manifests/pipeline_policy.json` → `decision_log`, plus an `OWNER_REVIEW.json` per batch.
- **Git**: never commit to `main`; work on the feature branch and deliver through the PR.

## 3. The loop

Per batch (the owner names the units):

1. **Measure first.** Read each binding's envelope from `assets/models/registry.json`
   (`bindings[].envelope`) and any per-unit data in `assets/data/{ships,stations}/imperial.json`.
2. **Author in Blender from a script**, never by hand-editing `.blend`:
   `tools/art/build_imperial_station_prototypes.py` holds a `ROWS` table — one row per unit with
   `key`, `label`, `binding`, `asset`, `master` (`.blend` path), `export` (mesh path), the measured
   `envelope`, and a builder callable. `--only <key>` builds one unit, `--render <dir>` writes review
   stills. Build the whole batch before presenting any of it.
3. **Pass the per-model gates** (§6), fix, rebuild.
4. **Package** with `tools/art/package_station_prototypes.py` (add the row first). It recomputes the
   same revision the loader does and writes the manifest, descriptor and `SOURCE.md`.
5. **Show it in the game** (§8) — one live match with every unit of the batch placed.
6. **Owner verdict.** Iterate on what he says, in the game, not on the render.
7. **Commit and switch the default** once he approves: pack + `.blend` + builder + tests + docs +
   decision + review record, in one commit, with `[skip ci]`.

## 4. Authoring rules that survived contact

Geometry is authored Y-up (X beam, Y up, +Z forward), scale 1 unit = 1 world-ish unit before the
per-entity draw scale (`radius/50`).

- **Fit to 0.9995 of the envelope**, per axis, never the span itself — the exporter rounds
  coordinates to 7 decimals and the loader compares with a bare `>`, so landing exactly on the bound
  is rejected (`E_EXTENT_DRIFT`) and takes the whole pack with it.
- **Read the printed per-axis fit scale.** Below 1 means the design overshot and the asset was
  uniformly compressed (it reads as a toy); 1.0495 means it is narrower than the box. Reshape to the
  box rather than shipping a squashed station.
- **The fill has a floor as well as a ceiling** (`AssertionError: (axis, fill)` with 0.80–0.85 is
  under-filled). Restore the span with real structure — a keel, a taller gantry — not by stretching
  detail.
- **Seat surface detail on the real hull section at its own height**, never at a remembered radius:
  `section(levels, y)` → `(half_x, half_z, chamfer)`, `octagon_radius(w, d, c, theta)`,
  `hull_point(levels, y, theta, loc, inset)`. Keep tier tables as module constants shared by the mass
  and its detail. Detail placed at a remembered radius sits 0.5–9 units off wherever the hull narrows
  or the chamfer cuts in — in game that is "small blue and black squares floating beside the station".
- **A band across a chamfered section must be a ring, not a box.** A full-width box centred on the
  face plane has zero width at the corners, so its ends hang in air. Use
  `ring(..., radius = section(levels, y)[0] * 1.06, sides=8, axis='y')`.
- **Flank plates go ~0.5 outside the surface** with a thin `dark` seam; inset by 0.4 they leave a
  black seam that reads as z-fighting from distance.
- **`base` is mid slate that turns near-black away from the key light.** A cluster of unlit boxes
  reads as a hole, not as cargo: alternate `trim`/`base` per block, frame stacks with corner posts and
  run one `lit` band across them.
- **Dishes built as frustums read as white mushrooms** at every angle. Build a concave bowl with a rim
  lip and a dark throat, keep it small relative to the hull, or drop it. At play distance a dish can
  also read as a lamp — a flat array panel often reads better.
- **Break a wide flat envelope with verticals** (spire, mast, hoop, gantries, raised batteries), not
  with more top-face detail.
- **A dock reads as a shed** while its mouth is narrower than its bay and its roof is fully braced.
  Mouth to full bay width, three or four cross braces, crane above them.
- **The exporter has a contact gate**: any part whose world-space box touches no other part prints
  `FLOATING [...]` and fails the build. `STATION_DUMP=1` prints `PART <role> <name> x[..] y[..] z[..]`
  so a reported defect can be matched to a named part instead of guessed from a shaded render.
- Preview cameras must be built by hand for Y-up assets: `back = loc - target`,
  `right = (0,1,0).cross(back)`, `up = back.cross(right)`.

Six material roles are always filled, declared per face as it is created:
`base, dark, trim, accent, lit, cool`.

## 5. Packaging and wiring

- `package_station_prototypes.py` writes `manifest`, `visual-pack.json` and `SOURCE.md`, computing
  `revision = sha256(asset + "\n" + "\n".join(f"{key}:{sha256(file)}" for key in sorted(files)))`.
  A hand-written revision fails `E_REVISION_MISMATCH`.
- `budgets.triangles` must be `>=` the mesh's own count, or the loader reports
  `E_MEASUREMENT_STALE`.
- Pack names are not globbed by the test tree, so new packs do not disturb existing pins.
- The default switch lives in `DEFAULT_SETTINGS["visual_packs"]` **and** in the owner's
  `saves/settings.json` (gitignored — a saved file overrides the defaults, which is why the first
  station batch did not appear in his run).
- Packaged builds resolve no packs at all (they must live outside a frozen bundle): the switch is a
  source-run selection, not core registration, and authorizes no tag or release.

## 6. What we test, and what we deliberately do not

Per unit, before the owner sees it:

| Gate | Detail |
|---|---|
| Blender build | script-authoritative, `.blend` master committed |
| Reproducible export | identical bytes from a clean rerun |
| Budgets | exporter asserts `1,800 < triangles < 11,888`, 9,500-vertex ceiling; loader caps 12,000 / 10,000 / 2,000,000 bytes |
| Six roles | all present and non-empty, every triangle row well formed |
| Envelope | per-axis inside the binding's approved box |
| Contact | no part floats (exporter gate) |
| Live capture | one real-driver frame, inspected before it is shown |
| Focused loader test | pack resolves through `AssetResolver.activate_packs`, siblings untouched, unload restores core revision byte-exactly |

Deliberately **not** run for an art-only change: the full suite (~68 min, 211 modules), the
contract-trio matrix, the art-validator sweep. Commits carry `[skip ci]`.

Focused commands actually used:

```
SDL_VIDEODRIVER=dummy PYTHONPATH=tests .venv/bin/python -m unittest \
    test_station_prototypes test_asset_selection
.venv/bin/python tools/art/reconcile_model_coverage.py --check        # -> CHECK_OK
```

Two test facts that bite:

- `tests/test_asset_selection.py::ShippedPrototypeDefaultTests` builds its expectation from the
  batch review records listed in `REVIEWS`, and asserts the total equals
  `len(DEFAULT_SETTINGS["visual_packs"])`; each record must expose an **`assets` list** of
  `{binding, triangle_count}` rows. A record with a differently shaped payload silently fails the
  count.
- Any geometry change turns the shipped-mesh test red until the record is rewritten. That red is the
  review gate, not a regression: get sign-off, then update the record — never edit the expectation to
  match a new mesh.

## 7. Evidence and decision records

`artifacts/<batch>-review/` holds per-unit in-game and Blender captures plus `OWNER_REVIEW.json`:
`approval_kind`, `owner_words_verbatim`, `question_answered`, per-unit `triangle_count`, `parts`,
`bounds`, sha256 of mesh / builder / `.blend` / descriptor / manifest, capture hashes, and a
`revision_history` when a batch is revised (the surface-fit fix kept revision 1 alongside revision 2).

`art/manifests/pipeline_policy.json` → `decision_log` (append-only) gets one entry per approval: `id`,
`date`, `owner`, `decision`, `owner_wording` (verbatim), `question_answered`, scope, gates,
`deliberately_skipped`. Adding a decision dirties the generated coverage report — regenerate with
`tools/art/reconcile_model_coverage.py`, then `--check`.

PR body carries a numbered section per commit: what the unit is, a metrics table (triangles, parts,
`.blend`), the owner's words, and what the change does *not* authorize.

## 8. How review is presented

The owner's standing request, verbatim: *"you need also to fire the game with the new models so I can
look in real game on it, rotate it ... as I would run a game."*

- `tools/play_station_prototypes.py` boots the real `main.py` in a stock Imperial skirmish with **one
  of every unit in the batch** placed, on an isolated profile
  (`~/Library/Application Support/STAR ARMADA/Station Prototypes/`), so live saves and settings are
  untouched. `--focus <key>` only chooses the starting frame; `--verify-out <dir>` captures a frame at
  the twelfth flip and asserts the accepted pack-id set from `diagnostics()`.
- Ship a `Play Station Prototypes.command` launcher so the owner can relaunch unaided.
- Framing: stations want roughly 250–320 units of distance at 18–30° pitch; a distance that framed a
  small hull leaves a 120-unit station unreadable.
- **A captured frame is not firing the game.** Launch the review window as a detached background
  process and leave it open; give the controls (right-drag rotate, wheel zoom, WASD/arrows pan,
  left-click select), plus the pid so he can Cmd+Tab to it. This host has no Screen Recording or
  Automation permission, so `screencapture` and Apple events fail — prove the window with `ps`
  (`%CPU` non-zero) rather than claiming you raised it.
- **Restart after touching geometry.** Meshes load at startup; a window opened before a rebuild keeps
  drawing the old asset under the same pack name.
- Present in-game frames first, then the metrics table, then a one-line description of each unit, then
  ask what to change. Do not open with render sheets, and do not claim a fix is done from a render.
- His feedback is terse and typo-laden with a screenshot. Treat intent, diagnose from the image.

## 9. Costs and known noise

- **`render/renderer.py` is hash-pinned** by `art/manifests/approved-s06-source-hashes.json`,
  `approved-trio-source-hashes.json` and several `runtime` entries in `approvals.json`. Any edit — even
  cosmetic — fails `test_s07_scaffold_approval` (`runtime hash mismatch: render/renderer.py`) and
  `test_s07_scaffold_registration` (`approved pin mismatch`) until a re-pinned appearance revision is
  recorded. Those pin files are themselves guarded by `test_s06_appearance_records`, so re-pinning is
  an owner-signed appearance revision, not a drive-by edit.
- A full rebuild rewrites every committed `.blend`, so already-approved masters show as modified.
  Restore the untouched ones (`git checkout -- art/blender/<name>.blend`) and verify each against its
  `OWNER_REVIEW.json` sha256 before staging.
- `tools/art/build_model_inventory.py --check` reports drift on pristine `main` too (pre-existing,
  from #141's line-number re-base). Not ours to fix inside an art change.
- Settings-page wording "Preview is opt-in; OFF keeps stock legacy models." is stale from the opt-in
  era; changing it drags four i18n packs — its own PR.
- `.venv/bin/python`, tests with `SDL_VIDEODRIVER=dummy PYTHONPATH=tests`, Blender via
  `/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --python <builder>`.

## 10. Imperial ships — what is different

Ten Imperial ships live in `assets/data/ships/imperial.json` (radius in units; two are squadrons):

| data id | radius | class |
|---|---|---|
| `imperial_tie_squadron` | 22 | fighter squadron (`is_squadron`, `squadron_size`) |
| `imperial_tie_bomber_squadron` | 24 | fighter squadron |
| `imperial_corvette` | 34 | corvette, 2 weapons |
| `imperial_frigate` | 55 | frigate, 2 weapons |
| `imperial_cruiser` | 90 | cruiser, 3 weapons |
| `imperial_battleship` | 150 | battleship, 4 weapons |
| `imperial_supercapital` | 260 | supercapital, 4 weapons |
| `imperial_constructor` / `imperial_colonizer` / `imperial_crew_transport` | 30 / 40 / 32 | construction / construction / crew transport, no weapons |

Mesh bindings are keyed by class, not by data id: the two squadron rows resolve through
`imperial:fighter` and `imperial:bomber` (both 62.5 × 17.2 × 64), the crew transport through
`imperial:convoy`, and `imperial:supercapital` has its own binding. Read `registry.json` for the row a
unit actually resolves to before measuring anything.

Their envelopes (already in `registry.json`) are much longer than tall — e.g. corvette/frigate
32 × 29 × 91.6, cruiser 58.9 × 38.5 × 140.9, battleship 76.9 × 49.5 × 188.2. That is the opposite
problem to a station: a long thin box punishes a blobby mass and rewards a strong axial read.

Differences that matter when authoring ships rather than stations:

- **Axial silhouette.** The camera reads length first: bow, spine, engine block. Break the line with
  dorsal structures and outriggers, but keep the profile legible from the typical 3/4 top view.
- **Thrusters and trails** are emitted before hulls, so the engine mass and its glow must sit where the
  trail reads as coming out of it.
- **Squadrons are one entity with a fighter_count** and draw through the same ship path. Check how a
  squadron mesh reads at its in-game squadron spacing before authoring — several small hulls per
  entity change what "detail" means.
- **Weapons are data-side** (`weapons: [{weapon, count, arcs}]`); there are no per-hardpoint anchors in
  the mesh contract, so turret rows have to look right rather than line up with a firing point. Keep
  the muzzle arcs readable from above.
- The six approved flight prototypes are pinned in
  `artifacts/imperial-flight-prototypes/OWNER_REVIEW.json` — read it before touching anything the ships
  batch overlaps, and add the new record to `REVIEWS` in `tests/test_asset_selection.py`.

Opening checklist for the ships chat:

1. Read the envelopes for all ten bindings and the ship rows in `imperial.json`.
2. Decide the batch (the owner names the units) and whether the flight-prototype six stay as they are.
3. Add `ROWS` entries + builders to the builder script, one `build_<unit>()` per ship.
4. Build, gate, package, then review in one live match with every ship of the batch.
5. After sign-off: commit + default switch + decision + review record, same as the stations.

## 11. Command reference

```
# build every row (or one unit), and write review stills
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 \
    --python tools/art/build_imperial_station_prototypes.py -- --render /tmp/review
    ... -- --only trade

# package the packs (recomputes revisions and manifests)
.venv/bin/python tools/art/package_station_prototypes.py

# live review window, one unit focused, and headless verification capture
SDL_VIDEODRIVER=cocoa .venv/bin/python tools/play_station_prototypes.py --focus trade
SDL_VIDEODRIVER=cocoa .venv/bin/python tools/play_station_prototypes.py --focus trade --verify-out /tmp/live

# the owner's own run with the shipped defaults
SDL_VIDEODRIVER=cocoa .venv/bin/python main.py

# focused gates
SDL_VIDEODRIVER=dummy PYTHONPATH=tests .venv/bin/python -m unittest test_station_prototypes test_asset_selection
.venv/bin/python tools/art/reconcile_model_coverage.py && .venv/bin/python tools/art/reconcile_model_coverage.py --check
```
