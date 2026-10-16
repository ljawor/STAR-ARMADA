# Alliance three-asset visual review

## Review first

- `before-after-contact-sheet.jpg` — large, same-camera frigate and shipyard comparisons, identical crops on both variants. The full uncropped per-frame sets are raw capture output and are deliberately **not** committed (see "Scope and limitations"); the crops carry the comparison.
- `three-asset-review.jpg` — the approved Pelagic battleship, new Tern frigate and new Anchorage yard. Individual detail framing, **not common scale**.
- `trio-in-game.png` — all three simultaneously in the actual game at common scale.
- `before-after-aft-drives.jpg` — low aft comparison showing both recessed cyan frigate emitters.
- `before-after-motion.mp4` — synchronized 6-second / 180-frame / 30fps actual-game reel, before left / after right. Three short subject-relative orbits: frigate, yard, capital. Offline capture, not an FPS claim.
- `candidate/initial-tactical.png`, `candidate/initial-escort-tactical.png`, `candidate/initial-yard-tactical.png` — honest play-distance views; full frames, no geometry enlargement.

All images are from the production pygame/OpenGL renderer, not Blender renders. Normal visibility/fog, actual 4x MSAA, original postfx and global material shader are preserved. Only the two newly authored specimens join the existing opt-in authored-surface profile. Blue owner-painted plates, warm glazing/worklights and cyan machinery retain the normal material-role passes.

## Delivered art and integration

- Editable `art/blender/alliance_frigate.blend` and `alliance_shipyard.blend`.
- Reproducible `tools/art/build_alliance_frigate.py`, `build_alliance_shipyard.py`, shared `alliance_common.py`.
- Immutable validated runtime `assets/models/alliance_frigate.mesh.json` (5,128 triangles) and `alliance_shipyard.mesh.json` (7,935 triangles).
- Runtime uses the existing bounded loader; no Blender dependency. Dedicated asset IDs, unit normals, winding, indices, bounds, byte/triangle budgets and exact metadata are validated before immutable role batches are returned. Missing/corrupt optional art uses the prior cached procedural facade.
- Frigate: continuous narrow prow, slender open-waist escort silhouette, unequal twin drive bodies, one forward twin battery, exterior warm bridge.
- Yard: open construction slip, long rails, separate guide/clamp hardware, low structural ties, lifting gantries, offset operations tower, outboard service hardware and four exposed broad-face worklights.
- Approved battleship mesh, `.blend`, generator and dispatch function are byte-exact. Global `render/fleet_materials.py` is also byte-exact.

Build from the repository root:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --python tools/art/build_alliance_frigate.py
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --python tools/art/build_alliance_shipyard.py
```

Both runtime exports were rebuilt and compared byte-for-byte. `rebuild-verification.json` records hashes. `.blend` binary metadata is not claimed reproducible.

## Validation

- 79 focused tests passed, including the new authored contracts, unchanged capital contracts, silhouette/base-LOD, real-driver material/GL state, ships/stations, hardware identity, camera/contact integration, ship sizes and deterministic math. No full suite was run.
- `tests/fixtures/alliance_trio_unselected.sha256.json` pins all 73 unselected canonical fleet meshes, including Imperial legacy ship shapes and stations. All matched exactly.
- New asset contract initially failed RED before assets/loader existed. A separate broad-disc ray test failed RED on buried drive emitters; the corrected geometry passed GREEN. Actual low-aft game pixels confirmed both cyan discs.
- Four named yard worklights were individually removed from the production lit display list while retaining every other triangle. Their normal postfx game-frame crops contributed **185, 260, 276 and 413 visible warm pixels**, respectively. `worklight-pixels.json` and `pixel-checks/` retain per-feature controls; this is not an any-emissive-triangle test.
- Baseline/candidate real combat matched at every initial/stepped checksum (181 states / 180 simulation ticks), with 37 genuine weapon-fired events each and observed shield/hull reduction. Render and HUD draws were read-only. The motion reel matched the same combat timeline.
- All 660 inventoried user-data files were byte-exact afterwards, with no additions/deletions. Native inherited sandbox denial was canary-tested; all five persistence constants were redirected. User replays were untouched.

Source seals:

- Baseline: `d2c9b57f93e653436c88d7c42f995332e037a799f52058a6836d63d333bda072`
- Candidate: `47c6b3bbeab091c3725809b7b00b62843fe06c7cd8059410d56541dcc3ba3d27`
- Initial simulation: `549ae8fa52c544d00a46c2b01f35d9dcdffbecdb4b487abb52bcec23eeb2071d`
- Final simulation: `2a17e3a7454fc746b7323ff40e1acd9291c616d7b30573b2f7d34b652c35c607`

`verification.json` holds complete receipts and quality/context details. `evidence/` contains the committed capture/probe workflows, the retained RED/GREEN logs, scoped source diffs and the per-tick motion records; `pixel-checks/` holds the per-worklight controls. Sealed source copies and the remaining capture intermediates are not part of the repository — they live only in an ephemeral local scratch directory and are **not** the source of truth for any claim above.

## Scope and limitations

Only pre-existing files changed during this task: `render/authored_mesh.py`, the Alliance frigate region of `render/faction_ships.py`, shipyard dispatch in `render/faction_stations.py`, bounded authored-surface selection in `render/renderer.py`, and the material-pass test's expected selected specimens (plus a nonselected sibling reset control). All other pre-existing bytes and every pre-existing path survived.

An initial extra-view harness run omitted the final tactical camera key, and an isolated subprocess import test initially lacked inherited PYTHONPATH. These were harness defects, fixed without production changes; failed receipts were retained in scratch. Existing low-aft background/horizon artifacts were not altered.

macOS real-driver evidence only; Windows not run. Specimens use actual factory entities and real combat commands, not a paid construction walkthrough. No LAN investigation, full-suite claim, catalogue rollout, merge or release. Appearance approval was subsequently recorded and this work preserved as the S00 checkpoint — see `art/manifests/handoffs/S00-PRESERVATION.md` and `art/manifests/approvals.json`; the no-merge/no-rollout statement still stands.
