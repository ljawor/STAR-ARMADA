# Combat presentation — owner handover

## 1. Revision and evidence

Code and capture harness committed at `8b6aa096c15ba1d620a8df056296dad61b781067` before final captures. Source pins in each report were checked against that immutable commit. Later evidence-only commits do not change renderer bytes.

Baseline: `2eed8e322563ff59b8e6eb1f692acca117870497`; zoom ratios 1/1/1, off-axis error 27.627 degrees. Final visible-length near/far ratios: {'laser': 4.70002953055752, 'missile': 5.176303960924519, 'torpedo': 4.87174510701236}; off-axis error 0.163 degrees. The strengthened probe passed nonempty/absolute-readability/aspect, 4x-distance zoom and perspective-axis checks. Raw failed internal attempts retain their uncommitted source hashes and are NOT owner-review revisions.

## 2. Validation

115 focused Python tests; all 16 native CTest targets. The new native guards reject source mutations reintroducing pixel length, dropping depth velocity and permitting through-hull flight. Release-lock RED and GREEN preserved; only engine_version changed, catalogue/approval pins unchanged. Initial independent review blocked the stale lock; followup review passed the correction and evidence/report improvements. Initial real-game clips were rejected because the live camera ring overrode both requested distances to 1650; camera-red.txt preserves the refusal. Corrected final clips assert the native-reported distances are truly 1600/3500.

Both actual-main battle clips contain 360 frames, real attack orders, stock weapons and damage, laser/missile/torpedo fire, state-neutral presentation and reaped workers. The native report confirms nonzero expanded FLIGHT geometry with zero decode failures and dropped vertices. Spawned fleets are fixtures, not paid construction/stock-queue eligibility claims. Clips are encoded at 60 frames/second; simulation timestamps are in the per-frame receipts, not an interactive FPS claim.

## 3. Scope and limits

See `verification.json` for explicit limitations. This first native-renderer presentation pass does not relocate capital muzzles, change gameplay, finish a Homeworld-style combat overhaul, validate Windows rendering, rebuild the installed app, or authorize merge/release. GitHub Windows signal CI is disabled by owner request; Release remains available. No GitHub CI success is claimed.

## 4. Reproduction

Use the commands in `docs/RENDER_W05_EMISSIVE.md`, fresh output directories and serial native workloads with process-group deadlines. The owner runs `.venv/bin/python main.py` from the normal checkout on the handover branch.
