# Handoff: S05 — approved trio through the generic path

## 1. Status and authority

**Review-ready with a recorded historical repeatability limitation.** The two current full matrices
pass under the owner-authorized capture-only amendment; this is not a fix for the old capture failure.
S04 PR #124 is merged as `7030dd252ddb4da3bb4f69fecb2f2028650ffe6c`, with the exact tested tree.
Owner instruction, verbatim: **"OK we can merge and continue with next step"**.
This authorizes S05 execution, not automatic S05 merge, new model appearance approval, release or S11.

Branch: `feat/s05-trio-generic-equivalence`, isolated scratch worktree.
Criteria were frozen before implementation: `art/manifests/equivalence/S05-CRITERIA.json`.
Prototype control: `5bddd7b67245ddff4b595bb3b477ca8ceede0a6c`.
Generic preview and legacy negative control: `7030dd252ddb4da3bb4f69fecb2f2028650ffe6c`.

## 2. Implemented evidence

- New real-GL harness: `tools/diag_trio_generic_equivalence.py`.
- New focused tests: `tests/test_trio_generic_equivalence.py`.
- Original run: 102 paired frames, ten frozen views, all eight actual owner colours across 32 frames,
  60 motion samples over 360 simulation ticks / 361 state hashes. Four actual AttackCommands and
  70 weapon-fired events; movement, projectiles and damage measured.
- Original run's paired prototype/generic frames are pixel-identical. Legacy differs in every frame.
- Four individual yard worklights and two emitters per approved ship measured by feature-specific
  ablation and restoration, not a whole-role emissive count.
- Actual 1280×800, 4×MSAA, production GLSL and normal fog. Selected exported captures and motion
  evidence inspected. Yard translation is static and labelled as such.
- Parent independently reran the original 47-test focused invocation: passed.

The preserved `initial-run/verification.json` describes that original successful run. It does **not** override the
subsequent parent failure. No engineering approval-transfer record has been accepted.

## 3. Parent reproduction failure and diagnosis

Full parent rerun failed candidate `motion-0270-escort-close`: two identical frozen draws differed
by 96 pixels / 99 channels, maximum channel delta 1. No tolerance was relaxed.
Failure, original PNG pair, partial summaries and user-file preservation are retained in
`artifacts/s05_trio_generic_equivalence/attempts/parent-reproduction/` and `parent-reproduction.json`.

Bounded diagnosis reproduced the exact simulation digest/camera and the parent's first image exactly.
500 further draws and 500 immediate rereads stayed identical. Original full history through tick 270
replayed with 87 exact paired samples, then deliberately stopped; that is not a completed acceptance run.
Differences are outside the central escort, over background planet/distant ship pixels. This location
and a last-modifying-pass trace do not establish the originating cause. Dither, driver rounding,
implicit resolve and renderer caches remain hypotheses, not findings.

The measurement-only same-quality 4×MSAA offscreen-FBO/explicit-resolve experiment completed without
reproducing instability on either route. It retained production passes, fog, shader and dither.
Default versus FBO differed by 10,170 pixels / maximum channel delta 63, so the FBO is **not** accepted
as a replacement, rebaseline or fix. Root cause remains unresolved. Reports are retained under
`artifacts/s05_trio_generic_equivalence/diagnosis/`. No production edit or quality downgrade occurred.

## 4. Review and open work

Independent code/provenance/retained-pixel review passed its scoped audit, including recomputation of
eight feature measurements and 107 original publication-manifest entries. It completed before the
parent failure could be delivered; `independent-review-initial.json` records that limit explicitly.
The passing review is not a real-GL reproduction pass.

The harness also needs post-commit reproducibility: its initial live-HEAD==candidate assertion would
prevent rerunning once the harness itself is committed. The bounded TDD fix now passes: pinned revision preflight, immutable pin-manifest reads and portable
scratch/user-root paths no longer depend on live HEAD. Capture/metrics/inventory ASTs and strict
gates remain unchanged. The exact original harness is preserved in `initial-run/original-harness.py`.
The extended focused invocation passes **53 tests**; model validation 34/34 and metadata reproduction
also pass. None of these checks clears the real-GL repeatability blocker.

Next: publish the verified **blocked draft** checkpoint and resolve the strict-repeatability gate,
or obtain an explicit owner decision about a revised acceptance contract. Preserve all failures. Record engineering
equivalence only once the required evidence actually satisfies the gate; never fabricate a new owner
model approval. If appearance differs, show it to the owner for renewed approval.

## 5. Scope preserved

No approved mesh, Blender source, exporter, gameplay or renderer source changed. No full-suite,
performance, native Windows graphics/package or S11 acceptance is claimed. The two unanswered owner
policy questions remain unanswered. Live checkout/user data are not to be edited or cleaned up.

## 6. Durable publication status

The top-level evidence `verification.json` says **BLOCKED-S05-NOT-ACCEPTED**. All original
107 publication-manifest files remain byte-identical under `initial-run/`; the original report is
not the current acceptance verdict. The final pushed head and CI receipt belong on the draft PR,
not in a self-referential commit field. No S05 merge is authorized.

## 7. Owner-authorized repeatability amendment — implementation in progress

Owner reply, verbatim: **"ok go"**, to the proposal for a bounded capture-only background
repeatability allowance. Frozen before implementation in
`art/manifests/equivalence/S05-REPEATABILITY-POLICY.json`: maximum one 8-bit colour level,
maximum 128 changed pixels per frozen repeat, and zero changes inside conservative geometry-derived
protected regions for all three approved models including worklights and emitters. The numeric cap
is an engineering interpretation of the approved small fixed cap, not a quoted owner-selected value.

Prototype/generic parity, simulation hashes, source/runtime hashes and feature ablation/restoration
remain strict. No extra retries, warmups, FBO substitution, quality change or production renderer
edit is authorized. Every nonzero tolerated pair must remain visible in evidence with its mask.
Implementation and full matrix rerun are in progress; no amended-gate pass is claimed yet.
The previous blocked verdict and original failure remain retained. No S05 merge is authorized.

## 8. Amended current results and remaining limitation

Two complete executions (`policy-run/` and independent `policy-parent-run/`) each pass all 102
prototype/generic frame pairs with **zero** cross-source differences, 361 matching simulation hashes,
all eight owner colours, real combat and eight individual feature controls. Both had zero nonzero
frozen repeats, so neither consumed the background allowance. The extended invocation passes
**57 tests**, pipeline 34/34 and nine-file metadata reproduction.

The replay of the original failing pair remains **rejected**, including 15 differences inside
conservative protected boxes. No box or padding was reduced to admit it. This must not be described
as an eliminated rendering cause. Future protected differences still fail. This is current bounded
engineering evidence, with historical instability explicitly retained for owner review.

Independent code/gate review found only an actively written publication-log hash mismatch; the log
was finalized and all 87 indexed entries then verified. The original failed verdict and current
receipt are in `policy-review.json`. Current top-level verdict and scoped per-model engineering
record are `verification.json` and `art/manifests/equivalence/S05-TRIO-EQUIVALENCE.json`. Existing owner
approvals are referenced, not rewritten. Owner review/merge of S05 is still a separate gate.
