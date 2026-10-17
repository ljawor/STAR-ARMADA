# S05 — current matrix passes; historical repeatability limitation retained

**Review-ready under the owner-authorized capture-only policy. Not merged and not a new model approval.**

Two complete current executions each have 102 exact prototype/generic frame pairs, all eight owner
colours, 361 matching state hashes over 360 ticks, real combat and eight individual lamp/emitter
controls. Both had **zero nonzero frozen repeats**: neither actually needed the allowance.
The independent parent run matches the worker's frame hashes exactly. 57 focused tests pass,
model validation is 34/34 and runtime metadata reproduces.

## Authorized amendment and its limits

Owner reply **"ok go"** approved the background-only repeatability amendment. The pre-implementation
policy fixes maximum channel delta 1, at most 128 changed pixels and zero changes inside protected
regions for all three approved models, lamps and emitters. The numeric cap is an engineering
interpretation, not a quoted owner-selected value. Regions use complete immutable mesh bounds,
actual transforms and safety padding. Invalid projections fail closed by protecting the whole frame.
Source parity, simulation/source/mesh hashes and feature restoration remain exact.
Injected controls prove delta 2, 129 pixels, protected-pixel changes and cross-source single-pixel
changes are rejected. No retries, extra warmups, FBO substitution or quality change were introduced.

**The old failing pair is still rejected:** its 96 one-level differences include 15 pixels inside the
conservative boxes. Protection was not shrunk to admit it. The new executions establish current
matrix equivalence, **not a fix for the unidentified historical capture instability**. A future
protected-region difference still fails. This limitation must accompany any owner review of S05.

## Evidence and provenance

- `verification.json`: authoritative current verdict and limitations.
- `policy-run/`: complete worker execution, capture sheet, movie and real-image negative controls.
- `policy-parent-run/`: independent complete reproduction, matching frame hashes and known-pair replay.
- `policy-review.json`: scoped independent audit and corrected/finalized publication-index receipt.
- `initial-run/`: original 107-file successful publication, preserved byte-for-byte with its original harness.
- `attempts/parent-reproduction/`: original failing pair and partial run.
- `diagnosis/`: bounded repeat/FBO investigations; FBO is not an accepted replacement or cure.
- `pre-policy-verification.json`: original blocked verdict, retained rather than erased.

The maintained command remains:

```sh
.venv/bin/python tools/diag_trio_generic_equivalence.py run \
  --output "$HOME/.hermes/cache/scratch/s05-new-reproduction"
```

Use a new output directory. It archives pinned revisions independently of live HEAD; scratch and
extra user roots can be supplied explicitly. Publisher logs must be finalized before being indexed;
never redirect an active publication stream into a file that is simultaneously hashed.

Selected motion evidence: `policy-run/paired-motion.mp4` (five seconds/60 frames spanning twelve
seconds of simulation, with static station translation truthfully labelled). Approved model bytes,
gameplay and production rendering stay unchanged. No S05 merge, release, Windows graphics/package,
full-suite/performance or S11 acceptance is authorized or inferred.
