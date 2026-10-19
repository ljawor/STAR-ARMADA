# S08 evidence index

Status: review-ready; focused engineering gates passed. Not a merge/release, S09 platform
acceptance, owner artwork approval or default-switch authorization. Legacy is unchanged.

- `S08-RECEIPT.json`: parent-verified final source/evidence seals, preservation and gate totals.
- `integrated/receipt.json`: final serial native gate, 18 modules / 150 tests, zero skips,
  four tools, source inputs unchanged throughout. Source changes invalidate older results.
- `integrated/cosmetic/{summary,tick-checksums}.json`: final 16 × 181 history comparisons,
  separate-process real TCP peers at 181 boundaries, eight commands and gameplay rejection.
- `provenance.json`: parent seal for standalone cosmetic and lifecycle receipts. It records
  verified source equality to the final integrated run, not an invented execution-time pin.
- `review.json`: original independent review, 35 bounded headless checks, no blocking findings.
- `review-supplement.json`: final small delta review; use its updated file pins when an
  original review pin was superseded by documentation or portable subprocess path fixes.
- `native-examples/report.json`: actual Cocoa production-renderer capture/source/state hashes,
  measured visible replacement and exact disabled rollback. This artwork is not reapproved.
- `pack-safety/COMMANDS.txt`: retained 12 RED→GREEN safety cycles and already-green matrix.
- `examples/`: build/reproduce/install/loader proof on real evaluated Blender export.
- `cosmetic/`: earlier standalone run, 3 tests in 62.721 seconds; not the final-run timing.
- `integrated-attempt1/`: first failed integrated gate; missing prerequisite scaffold record.
- `integrated-attempt2/`: intermediate green before final portability-only harness edits.
- `prerequisite-control/`: actual pristine-base failures and exact record-recovery receipt.

Full scope, source authority, limitations and next step: `docs/BLENDER_MODEL_S08_PLAN.md`,
`docs/VISUAL_MODEL_PACKS.md`, `art/manifests/handoffs/s08.md`.

## Reproduction on the native macOS development host

Use the existing project venv (not a runtime Blender dependency). Run from the S08 source root,
with no competing GL/test writer. Keep previous evidence directories rather than overwriting
failed attempts. The parent invoked the final gate through `sandbox-exec` with file-write
barriers on the primary checkout, installed STAR ARMADA user-data root, and worktree
`saves/`/`replays/`, then ran:

```sh
/Users/lukaszjawor/Downloads/Project/STAR-ARMADA/.venv/bin/python tools/art/run_s08_gates.py
```

The harness bounds subprocess groups, imports `game.core` before module discovery, uses
fresh module processes, and fails on zero tests/skips or input changes. It is intentionally
native macOS, not a cross-platform whole-suite or frozen-package acceptance runner.

Final exact-head remote blob/readback and CI results are in the PR publication comment so
this committed receipt does not attempt to name its own commit SHA. Never infer Windows
native rendering from the existing LAN signal job, or count skipped package jobs as passed.
