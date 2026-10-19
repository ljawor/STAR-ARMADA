# Blender model migration — S07 integration plan

## 1. Authority, state and limits

Read-only planning against published S06 head `4ffdc600306ecdf4f35265fca689b495e35dd3fe`
(PR #127). Read the roadmap S07–S11, S02 contract, S03 policies and adjacent coverage report
before implementation. The owner's `agree. Let do this` accepted coverage reconciliation
and this plan, not registration, renderer implementation, merge, release or default activation.

The joined report accounts for all 120 historical inventory identities: 76 approved unique
assets (73 new specimens across nine batch decisions plus the trio), four shared convoy
candidates, 27 missing meshes, ten deferred textures and three outside-mesh rows. Three planned
Syndicate hulls are additional data/model work outside that denominator. Existing appearance
approvals remain valid for the unchanged bytes; do not repeat their reviews merely for S07.
Only the original trio is registered. S00–S05 are closed; S06 catalogue closure is not achieved.
This plan and code inspection establish **no integrated-renderer acceptance**.

## 2. Prerequisites and the immediate next task

1. Preserve the approved revisions and close remaining S06 art in bounded batches: eight combat
   hulls, ten Imperial orbital stations, eight faction constructor/colonizer hulls and the shared
   scaffold. Suggested order is Imperial stations, the remaining combat hulls, then construction.
   This is a recommendation, not a new owner-approved batch sequence or design approval.
2. Settle data/stat specifications for the three planned Syndicate hulls before implementing data.
   The bomber's explicit fighter-platform build list also needs updating under that authorization.
3. Repair the B6 sidecar reproducibility blocker as a separate bounded maintenance task:
   `write_pending_sidecars.py --check` raises `FileNotFoundError` for
   `tools/art/build_imperial_corvette.py`. The existing generator supports `seed`/`seed_arg`,
   but B6's sheet lacks the per-row seed declarations. Reproduced on clean audited S06 head;
   not introduced or repaired here. Inventory the actual seeds, add behavioral RED→GREEN
   regression, and prove no approved blend/export/mesh or unrelated sidecar changes. Changes
   to any approval-bound tool require the existing correction/re-pin mechanism, not new approval.
4. Explicitly authorize a bounded **opt-in registration** scope before changing runtime records.
   Full S07 closure depends on S06; a separately authorized partial preview must remain labelled
   partial. Preserve production legacy selection and existing pending-registration guards until
   the authorized migration deliberately replaces their expectations.

## 3. Work packages and file ownership

These packages are proposed implementation units, not instructions to edit them now.
Keep shared renderer work serialized; give parallel workers disjoint files/functions.

| Package | Prerequisites | Owned files / functions | Output and completion check |
|---|---|---|---|
| WP1: identity/route contract | Coverage report; declared registration scope | New `tests/test_s07_binding_routes.py`; mapping report/tool. Historical inventory stays unchanged; generator corrections, if necessary, are separate | Inventory identity → live runtime key → dispatch/class → exact approved revision/shared source → selected or explicit fallback. Complete behavioral route table, unknown controls and preserved exceptions |
| WP2: selected station consumers | WP1; isolated selected Imperial station fixture | `render/renderer.py`: `_station_visual_radius`, `_visual_hit`, `_shield_radius`, `_draw_construction_sites`; `render/input.py:_ship_pick_distance` | Evaluate Imperial legacy bypasses against selected geometry. Selected bounds/picking/contact/shield/construction proof, paired with byte/behavior-preserving unselected controls |
| WP3: geometry/ownership matrix | WP1, then WP2 | `render/ship_sizes.py`; `render/camera_geometry.py:scene_boxes`; `render/planet_building_geometry.py` contact/frame/pick helpers | Rotation, owner remap/capture, attachment slots, camera, hidden/history contacts and convoy aliases. Change only demonstrated defects; unchanged authoritative state digests |
| WP4: LOD semantics | WP1; serialize renderer with WP2 | `renderer.py:_draw_ship_role_batch`, `_draw_ship`; selection/resolver only if a demonstrated requirement needs it | Threshold boundary sweeps, cached/uncached parity, material-role silhouette/readability and station/asteroid checks. Record existing role suppression versus actual mesh-LOD support separately |
| WP5: menu/environment closure | WP1; relevant S06 assets and scope decisions | `tools/build_menu_movie.py`; `render/menu_movie.py`; `render/menus.py:_draw_splash_movie`; no planet pipeline expansion | Revision-bound candidate bake provenance, explicit selection policy and existing movie controls. Retain texture/effect exceptions; asteroid success is not planet-texture migration |
| WP6: integrated preview receipt | All applicable WPs; complete S06 prerequisite | Completeness report; runtime manifests/approval receipts; lifecycle/metadata tests | Exact approved candidate set routes through opt-in registry with no unexplained fallback, clean source/frozen metadata closure and representative campaign entry. No production default switch |

## 4. Live-code findings the implementation must honor

- `render/asset_selection.py:ship_binding` constructs faction-generic bindings before procedural
  dispatch. Imperial ships need no widening of `FACTIONS`/`SHIP_KEYS` or a duplicate mesh seam.
- `render/fleet_geometry.py:station_mesh` consults `mesh_for` before the Imperial fallback.
  Unselected `mesh_for(...) is None` is not proof that dispatch lacks a seam. B3/B3b/B3c test
  names claiming "no seam" need selected/unselected behavioral controls, not registration as a fix.
- Ordinary Imperial station consumers retain bypasses in the five WP2 functions; attached hardware
  takes separate routes first. Evaluate the consumers with real selected fixtures and preserve stock.
- `asset_selection.mesh_for` resolves default `mesh`; resolver support for a `lod` argument is not
  proof of renderer mesh-LOD selection. Current ship batches suppress roles at 16/34 projected px;
  uncached drawing emits all roles. Freeze intended semantics before adding new LOD geometry;
  altered model revisions require their own appearance approval.
- Squadron inventory prose claims per-member emission, but inspected draw paths transform each
  squadron entity once. Do not add member formations under an integration task or call them tested.
- Menu runtime reads baked `assets/menu/battle.zip`, not a mesh placeholder. The baker's model-ID
  metadata does not establish resolved candidate revision hashes. Planet surfaces are generated
  textures on a sphere, outside this mesh loader's class. Their retained pipeline is an explicit
  B5 scope decision, not an unresolved duty to build new textured meshes in S07.
- Asteroid dispatch already consults `environment:asteroid_field`, with shared placement/RNG before
  the branch. Preserve that determinism and the approved small-prop class.
- `star_armada.spec` bundles `assets/`, not `art/` or tooling. Runtime metadata/schema/approval
  dependencies must remain under bundled assets; no runtime imports from repository-only tooling.

## 5. Identity examples and route acceptance

| Historical identity | Runtime binding / disposition |
|---|---|
| `ship:rebel:battleship` | `rebel:battleship` |
| `ship:confederacy:bomber_squadron` | `confederacy:bomber` |
| `ship:<faction>:crew_transport`, `ship:<faction>:trade_convoy` | `<faction>:convoy`; both branches need independent scale/ownership/envelope proof |
| `station:imperial:shipyard` | `imperial:shipyard` |
| `hardware:satellite:imperial:defense_satellite` | `imperial:defense_satellite` |
| `hardware:construction:imperial:planet_extractor` | `imperial:planet_extractor`, through generic station entry |
| `menu:cinematic:backdrop` | Registry placeholder `menu:cinematic_backdrop`; actual runtime is the movie ZIP |

Generated sidecar `ship:` prefixes and inventory shared-reference strings are not authority for
runtime identity. Derive mapping from live data/dispatch; do not rewrite historical inventory just
to make it look current. No shared-source substitution approval is created by this table.

## 6. Verification commands and boundaries

These are the **eventual implementation owner's commands**, not a claim they ran in this audit.
Use isolated user-data/write policy and one GL/heavy owner, not simultaneous suite/capture jobs.

```bash
python3 tools/art/reconcile_model_coverage.py --check
python3 tools/art/gen_export_wrappers.py --check
python3 tools/art/write_pending_sidecars.py --check  # known B6 blocker until repaired
python3 tools/art/sync_runtime_metadata.py --check
PYTHONPATH=tests .venv/bin/python tools/art/validate-models --all
PYTHONPATH=tests .venv/bin/python -m unittest \
  test_asset_selection test_asset_registry test_generic_model_preview \
  test_imperial_convoy_gate test_faction_visuals test_ship_sizes \
  test_camera_safety test_surface_geometry_integration test_runtime_asset_metadata
# Separate real-driver run, after all writers settle:
PYTHONPATH=tests .venv/bin/python -m unittest \
  test_model_context_lifecycle test_ship_material_passes
```

Add the new route/consumer tests to that union. `build_model_inventory.py --check` may report
historical/provenance drift; diagnose in a disposable copy and publish generator refresh separately,
not by silently editing the historical input. Source/frozen discovery checks do not replace a build.

Machine gates: exact approval hashes, selected/fallback routes, all-role bounds/contact/picking,
ownership, no simulation/save/replay changes, cache/context lifecycle, source/frozen dependency
closure, nonzero discriminating captures and inspected motion. Retain failures and raw receipts.
Owner gates: genuinely new/revised appearances and separate registration/merge/switch authorizations.
Full protected suite, performance, packaging and native-platform acceptance belong to S09, not this plan.

## 7. Stop and handoff criteria

S07 can close only after required S06 coverage is complete or explicitly excepted, every applicable
route is proven for the exact authorized candidate, all required focused/visual checks pass and the
receipt names exact heads, hashes, failed attempts and remaining gates. Default stays legacy.
Then proceed S08 mod/update compatibility → S09 integrated/platform/package acceptance → S10
revision lock/rollback/owner review → separately authorized reversible S11 switch. Do not jump from
appearance approvals to S10 or conflate opt-in registration with a release.
