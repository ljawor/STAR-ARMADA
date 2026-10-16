# Draw-local view reuse — partial performance delivery

## 1. Scope and source identity

This is the third bounded performance pass for PR #113, following `7a0e893` and `6ea098fa4e4de755705cb83b4c163b1a88d41eda`. Integration starts at `42e0348664fbba9b8432d749175edbe694c0ee48`; the first two passes and their evidence documents are unchanged. This is performance headroom, **not a visual upgrade, finished scaling solution, release, or catalogue cutover**.

Only `render/renderer.py` changes runtime behavior. Its SHA-256 is `d315f30912d554e68c77527a88bc79f7a4bfc7c87d7558c70b30b40f9c1d2469`, exactly the frozen round-three measured candidate. The final portable test SHA-256 is `eb317fd5b6bece961212366397e7225c519c48c005bffc75fb284192cab0d592`; this includes the later discriminating uncached-oracle regression. The feature version is `0.15.1`; no tag or release is created.

The approved Blender trio is preserved separately in draft PR #114, head `313f9683e9e7e4f376b05cedaeb28bb2dd300c9f`. No model, authoring file, material change or art-integrated renderer is included here. PR #114 remains draft and unmerged. The roadmap retains its historical baseline and adds a current partial-delivery ledger: S00 in progress, draft published; S11 not done.

## 2. Exact reuse boundary

Each synchronous `Renderer.draw` owns a new lazy view dictionary. It reuses the collision-safe camera eye/basis, projection height/tangent, and readable ship sizes retained by object identity. The exact preceding scope, including attribute absence, is restored in `finally`; nested/exceptional draws cannot leak their scope. Nothing persists across input, simulation or a later draw; standalone helper calls stay live.

The post-`camera.apply()` check clears pre-apply geometry, projection and sizes if refreshed keep-outs changed the safe eye. The existing persistent frame cache is not redesigned. Exact depth/Euclidean formulas, multiplication/division order, thresholds, shielding, hit contacts and visibility behavior remain intact. No geometry, fog, material pass, MSAA, gameplay, checksum or LAN pacing quality trade-off funds this gain.

Eight no-context regressions cover exact legacy arithmetic/catalogue outputs, safe-eye refresh, read-only contacts/entities, same-tick mutation between scopes, public-ID collisions, nested cleanup and actual operation-count discrimination. The repeated 12-iteration workload executes against both the independent frozen legacy oracle and candidate using the same wrapped real expensive helpers: legacy readable-size calls 24 versus candidate 1, candidate basis calls 1, with strictly greater oracle counts. Most tests substitute the read-only draw body; the apply test substitutes frame-cache creation and scene refresh. They do **not** establish full persistent-cache or real bound-scene-refresh parity; native frozen scene evidence is a separate gate. Both the historical final static review and a fresh independent read-only review of the exact renderer/test hashes passed. The fresh review confirms the oracle ASTs match the baseline and finds no concrete logic/security regression; its optional suggestion to pin the exact baseline basis count does not block the existing discriminating inequality. The non-blocking coverage limitations above remain retained.

`test_draw_view_scope` needs imports but no real GL context: renderer and camera GL entrypoints are mocked in the apply-boundary test. It is explicitly added to the existing dummy-video Windows job, not misrepresented as Windows graphics acceptance.

## 3. Paired native Mac timing

Historical round-three results are reused only after rechecking every original source-manifest entry, successful report/capture receipt and report hash. The integrated renderer is byte-exact. Runtime differences outside it are limited to the explicit version bump; the Windows workflow and strengthened test are not the measured runtime. `GRAPHICS_DRAW_SCOPE_EVIDENCE.json` preserves numeric summaries and exact identities.

Apple M4, Cocoa, GL 2.1 Metal, shader on, actual 1280×800 drawable/viewport, actual 4× MSAA, swap interval 0. Three alternating fresh-process full trials per revision/workload, 10 warmup +60 measured ticks, plus separate sim controls. Each full trial has 60 sim/camera/world/HUD/checksum samples and 59 frame/swap samples (capture-adjacent final exclusion). Values below are **medians of the three trial-mean synchronized diagnostic frame durations, not interactive FPS**. Percent reductions are descriptive paired measurements, not statistical significance claims; the small stock-distributed difference is especially modest.

| Workload | Before ms | After ms | Reduction |
|---|---:|---:|---:|
| Stock distributed | 39.02938840677966 | 38.84286233898305 | 0.477911838772771% |
| Stock combat | 54.09860169491525 | 51.2208100338983 | 5.319530580930776% |
| Stress distributed | 103.78915820338983 | 100.93364120338983 | 2.7512671356329954% |
| Stress combat | 330.2028170677966 | 308.1179555423729 | 6.688271687545688% |

The receipt also retains world and frame median/p95/p99 summaries. Precise initial/final simulation and final LAN checksums agree across all 32 ordinary reports (24 full +8 sim). Local checksum timing excludes sockets/barriers. Combat remains expensive; no target FPS, sustained live LAN or deferred laptop acceptance is claimed.

## 4. Frozen frame acceptance and retained failure

Four workloads pass fresh-process **control/control/candidate exact framebuffer equality**: stock distributed, stress distributed, stress combat and stress close. All five have exact precise-state/LAN equality within their frozen triplet.

**Stock combat is not an exact scene pass.** Its unchanged controls differ by one pixel at `(669, 343)`, maximum channel difference 1. Both complete attempts remain retained. In the first attempt candidate matches control 1; in the bounded unchanged repeat candidate matches control 2. For that repeat: control1/control2 and control1/candidate each differ by that one pixel, control2/candidate differ by zero. The strict equality assertion is unchanged and still fails for stock combat; no tolerance was introduced. This is unresolved unchanged-control nondeterminism, not evidence that the candidate caused the pixel difference and not “all five exact.”

## 5. Protected integration verification

Verification is run from an immutable performance-only archive, never discovery in the live dirty repository. A manifest pins all source files, read-only source permissions prevent incidental edits, and before/after comparison verifies the snapshot. Final documentation is written after execution; runtime/test/workflow/version bytes must still match the tested snapshot before staging.

The inspected scratch `graphics-mac-round2/protected_suite.py` launcher pins native Cocoa before discovery, redirects all five persistence constants before unsafe imports and per test, repeats redirects inside Python descendants, preserves genuine headless children and production path contracts, and uses a native descendant-inherited sandbox over the real repository and Application Support data plus an independent Python audit barrier. Source/user-data inventories and canaries are independent of application fixtures. Its self-test runs before application tests and exercises real parent GL, native child rejection, descriptor-relative writes, truncation, ordinary and regular-FD writes, anonymous IPC, five-path child isolation, real production exit and unchanged safe-deletion capability. Expected deliberate self-test audit denials are kept distinct from unexpected suite violations.

**Protected immutable performance-only whole suite: 1,668 tests, 0 failures, 0 errors, 9 skips.** Seven skips require the native Windows kernel; one fixture ship already has shields; one Git-only check needs a `.git` directory absent from the archive. That exact Git-only check separately passed in a disposable Git-initialized copy with identical source bytes. The strict whole discovery passed on its first attempt; no retry, timeout/assertion weakening or baseline failure classification was needed for this performance-only gate.

The protected focused invocation passed **88 tests, no skips** (`test_draw_view_scope`, `test_detmath`, performance/separation/fog/GL-lifecycle/graphics-benchmark/orbit modules in that exact order). A separate protected dummy-video child passed all **8 draw-view regressions**, with an explicit assertion that no display was initialized. This proves dummy-safe execution, not native Windows execution. Compileall and diff whitespace checks passed; an explicit added-path credential-pattern scan found no matches.

All application runs had **zero unexpected audit violations**, unchanged independent live source/user-data inventories, and an unchanged tested source snapshot. The preceding 14-canary self-test passed, including the real production child exit; its three deliberate audit rejections are expected evidence, not suite violations. The committed JSON records exact skip names, result counts, log hashes, manifest identity and safety verdicts. Every non-documentation file from the snapshot is checked byte-for-byte against the final worktree before staging; only delivery documentation is added/updated after the suite.

## 6. Reproduction, evidence and handoff

Portable module: `PYTHONPATH=tests:. .venv/bin/python -m unittest test_draw_view_scope -v`. For broad or persistence tests, use the protected launcher described above rather than running unsafe discovery in a user's live checkout. The protection launcher is retained scratch tooling, not a shipped clean-checkout command or a change to application assertions.

Raw retained evidence roots: `graphics-mac-round3/` (source/candidate manifests, three paired timing trials, frozen triplets, original RED/GREEN logs, review verdict) and `graphics-integration-delivery/` (performance snapshot/manifest, historical verification, self-test/focused/whole logs, before/after inventories, audit and final receipts). Paths are under the owner's Hermes scratch directory; the compact committed JSON is the durable numeric/source receipt, not a claim all raw captures or the launcher are shipped in this PR.

Merge is explicitly left to the parent after exact pushed-head/CI verification; no merge, auto-merge, tag, release, branch deletion or worktree removal is performed here. The parent publishes an exact post-merge receipt only after any actual authorized merge. Native Windows graphics/packages, physical mixed-platform LAN, agreed live performance targets and complete model migration remain separate gates. The historical art-integrated 1,671-test run's LAN `tick 6 != 8` and owner-created replays remain preserved and unresolved; this performance-only acceptance cannot retroactively make that run green.
