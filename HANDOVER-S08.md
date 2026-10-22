# HANDOVER — S06/S07 merged, S08 next

**Written:** 2026-10-19, after the S07 stack and two follow-ups merged.
**Audience:** a new chat with no history. Everything below was read from the tree or from live git/CI state, not from an older handover. If a document disagrees with the repository, the repository wins.

---

## 1. State in one paragraph

`main` is at **`0f4f130`**, with **one open PR (#134)** that repairs a guard `main` currently fails — see §3a before trusting any green claim in this document. S06 is closed *for this milestone* by an explicit owner coverage exception (103 of 119 registry bindings authored and approved, 16 excepted), and S07 — the opt-in catalogue integration — is complete, merged and receipted (15/15 criteria). The **legacy renderer remains the production default**; nothing was switched, activated or packaged. The next executable step is **S08 (model replacement and mod compatibility)**. S10 (asset lock) and S11 (default switch) are **not authorized**.

---

## 2. Repository and where the work lives

- GitHub repo: `ljawor/STAR-ARMADA` (`gh` auth via keyring).
- Long-lived clone: `~/Downloads/Project/STAR-ARMADA` — was 84 commits behind at `fd08ac7` (S03 era); fast-forwarded to `0f4f130` on 2026-10-19, so it now matches `main` with renderer `9aff3414`. Still run `git fetch origin` before trusting it in a later session.
- Worktree that carried the recent work: `~/.hermes/cache/scratch/star-armada-s07-integration`. **It is scratch and may be pruned**, so fetch a fresh worktree from `origin/main` for new work rather than depending on it.
- Merge convention that matters: the stacked PRs were merged with **true merge commits, not squashes**, so each upper PR kept its merge-base and the commit SHAs its evidence cites. Keep doing that for stacked work; squashing rewrites SHAs that receipts reference.

Merged, in order:

| PR | What | Merge commit |
|---|---|---|
| #128 / #127 | S06 batch work and coverage reconciliation | `663cd98` / `cdb1d53` |
| #129 | S06 coverage reconciliation + bounded S07 plan | `4ab1472` |
| #130 | Remaining B7–B9 Blender catalogue authoring | `ab62d6d` |
| #131 | S07 opt-in integration, renderer repair, receipt | `d427f66` |
| #132 | Roadmap/ledger brought to the merged state | `ae9bf09` |
| #133 | LAN launch-recovery harness race fix (tests only) | `0f4f130` |
| #134 | Refresh the derived coverage report (see §3a) | open at time of writing |

---

## 3. Verified facts (re-check, do not assume)

```bash
git fetch origin && git log --oneline -1 origin/main    # 0f4f130 Merge pull request #133 ...
shasum -a 256 render/renderer.py | cut -c1-8            # 9aff3414 (on a worktree at that commit)
gh pr list --state open | wc -l                        # 0
```

- Renderer of record: `9aff34140aa3d458eec358a2d87e64d4d4277c924ca198d507e4d29983350f3c`.
- Registry `assets/models/registry.json`: **119 bindings — 103 `core`, 12 `authoring_pending`, 4 `keep_procedural_proposed`**. The 103 are approved under **eleven** `s06-b*` batch decisions plus five rows approved outside them (trio, `rebel:shipyard`, the construction scaffold).
- `art/manifests/reviews/S07-S06-COVERAGE-EXCEPTION.json`: 103 approved / 16 excepted, decision `s07-s06-coverage-exception-2026-10-19`. The receipt refuses to build if this drifts from the registry's non-core rows.
- `artifacts/s07-runtime-final/S07-FINAL-RECEIPT.json`: **15 criteria, overall `pass`**, sha256 `273608f2…`.
- `art/manifests/pipeline_policy.json` → `decision_log`: **13 decisions** (key is `decision_log`, not `decisions`). Latest three: `s07-scaffold-registration-2026-10-19`, `s07-authored-lod-cost-2026-10-19`, `s07-s06-coverage-exception-2026-10-19`.
- Suite gate `artifacts/s07-runtime-final/suite-per-module.json`: **205 modules, 2,246 tests, 204 pass, 1 fail, 967.9 s** — re-swept on the post-decision tree and attached to PR #134 (see §3a). The earlier 2,245-test run predated policy decision 13 and is superseded; the +1 test is the regression added in #133. The one failure is **pre-existing** and carried by owner decision: `test_crew_recovery_ui.RecoveryUITests.test_faction_transports_have_small_known_solid_visuals` (expects `'box'`, tree returns `'imperial:convoy'`, contradicting decision `s06-imperial-convoy-parity-2026-10-18`). It fails identically on the pre-merge base `56906ea`; classification evidence is `artifacts/s07-runtime-final/pre-existing-failures.json`, produced by re-running against a pristine extraction, not asserted.

---

## 3a. A red guard was shipped with S07 — read this before trusting the receipt

`main` at `0f4f130` failed `test_model_coverage_reconciliation` on a clean checkout: `tools/art/reconcile_model_coverage.py --check` printed `STALE: art/manifests/reviews/S06-COVERAGE-RECONCILIATION.json`.

Cause: that report records an `input_sha256` per input. Appending the policy decision `s07-s06-coverage-exception-2026-10-19` changed `art/manifests/pipeline_policy.json` **after** the report was last regenerated, so the hash drifted while every count stayed identical (103 approved assets, 119 bindings, 0 integrity errors). Regenerating changes exactly one line.

The lesson is not the one-line diff, it is the mechanism: the 205-module sweep behind the receipt's suite criterion ran **before** that decision was written, so the only test that reads the report was validated against a tree that did not yet contain the edit. The receipt's green was real for the bytes it swept, and stale for the commit that merged.

Rule for S08: **the suite sweep must run after the last manifest/policy edit, not before it**, and a receipt should record the commit it swept alongside the tally. If a manifest edit lands after the sweep, re-run the gate or say plainly that the evidence is older than the tree.

PR #134 carries both halves: the regenerated report (one line, the recorded input hash) and the re-swept evidence (205 modules, 2,246 tests, 204 pass, the same one pre-existing failure, 967.9 s), with `S07-FINAL-RECEIPT.json` rebuilt so its echoed suite fields match. When it merges, `--check` is `CHECK_OK` on `main` again.

---

## 4. How to run the gates (and why the obvious command is wrong)

**Do not gate this tree with a single-process `unittest discover`.** `tests/test_weapon_sfx.py:17` calls `os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')` at import, process-wide. Observed consequences: 18 GL errors and one 28-minute non-completion, while every affected test passes in seconds in its own process. Two aborted attempts are retained as evidence (`full-suite-final-opaque-aborted.log`, `full-suite-bounded.log`, `full-suite-not-a-valid-gate.json`).

Use the per-module gate:

```bash
.venv/bin/python artifacts/s07-runtime-final/run-suite-per-module.py   # one process per module
```

It declares, rather than hides, three fallbacks: an `import game.core` prelude (works around a pre-existing circular import `game/systems/__init__.py` ↔ `game/core/manager.py:15`, identical on `56906ea`), pytest for pytest-style modules, and script execution for `test_classic_replays_gl` (which has no test cases at all and prints `CLASSIC_REPLAYS_GL_OK captures=14`).

Other fast gates worth running before any PR:

```bash
.venv/bin/python tools/art/validate-models --all              # 1034/1034, 0 failures, 0 warnings
.venv/bin/python tools/art/reconcile_model_coverage.py --check # CHECK_OK
PYTHONPATH=tests .venv/bin/python -m unittest test_s07_approval_preservation test_s06_appearance_records  # guard family
```

Never pipe suite logs through `head`/`tail` in the same pipeline that writes JSON — SIGPIPE killed a report once.

---

## 5. Pitfalls that cost real time here

- **Never `git stash` or `git checkout` files carrying uncommitted work.** Copy the files out, patch, copy back. This was learned twice.
- **Never `git add -A`.** Suite runs leave `saves/`, `replays/` and crash dumps in the repo; one dump rode a feature PR. Stage explicit paths. A typo'd pathspec with discarded stderr also shipped an incomplete commit once — `git add` failures were silent because stderr was redirected.
- **`gh pr checks --json` has no `conclusion` field**; use `name,state,bucket` (`bucket == 'pass'` / `'skipping'`).
- **For CI waiting, use the exit code:** `gh pr checks <pr> >/dev/null` → `rc 0` green, `8` pending, else fail. Home-made JSON pollers have produced bogus green verdicts and buffered-output blackouts.
- **A single red LAN test with a tick mismatch on a slow Windows runner is a harness race, not a regression.** Triage: re-run the same commit → compare suite durations (~195 s green vs ~330 s red) → check whether the test file changed in the suspect range. Fixed in #133: the drive loop now latches the peer's `done` and keeps advancing its own manager to the target (`drive_to_tick()`), instead of breaking on the message's arrival and asserting a tick it never drove. Pin it with fakes; a real two-process reproduction will not fail on a fast machine, and a deliberate stall does not bite because the peer is gated by the host's polling.
- **Background notifications can lie about success.** A wrapper whose last command was `echo` reported exit 0 while the child had been killed with 137. Check the real exit status of the thing you care about.
- **`assets/models/registry.json` shape:** top-level key is `bindings`, and it is a *list* of objects in this tree (handle both list and dict).
- **`pipeline_policy.json` shape:** decisions live under `decision_log`.

---

## 6. Owner decisions this state rests on

Recorded in `art/manifests/pipeline_policy.json` → `decision_log` (13 entries). The recent, load-bearing ones:

- `s07-authored-lod-cost-2026-10-19` — accepted-as-acceptable, owner wording **"Yes acceptable"**. The only live behavioural delta of the four-method renderer repair is authored-only LOD suppression on sub-pixel geometry; the phased-motion branch and `_draw_station` are production-unreachable (verified by call-site inspection: `_draw_ships` at `render/renderer.py:495` always receives a dict from `_ensure_frame_cache`).
- `s07-scaffold-registration-2026-10-19` — authorized execution, *not* appearance. The scaffold's appearance approval is `s07-scaffold-appearance-2026-10-18` with the owner's words **"Pictures approved"**.
- `s07-s06-coverage-exception-2026-10-19` — the S06 stop criterion was met by excepting 16 rows, not by claiming they were finished. The exception wording is the implementer's draft under owner authorization; the owner words are quoted verbatim and are **not** an appearance approval.

Earlier standing decisions still in force: `s07-detail-budget-2026-10-16` (exporter ceiling 11,888 tri / 9,500 verts), `s06-imperial-convoy-parity-2026-10-18`, the S05 repeat-capture policy.

---

## 7. What is explicitly NOT done

Do not report any of these as complete, and do not quietly absorb them into another step:

- **Packaging / DMG / frozen distribution** — skipped on every run, never accepted.
- **Native Windows graphics** — the Windows job exercises the LAN surface only; no native graphics or packaging claim exists.
- **Frame-rate / interactive performance targets and target resolutions** — owner numbers were never supplied; S09 owns them.
- **S10 (asset lock / rollback review)** and **S11 (default switch)** — unauthorized. Registration is not activation; the legacy default is untouched and the rollback path intact.
- **Mixed-machine LAN test** (Filip's Windows laptop) — deferred, needs re-authorization.
- **The 16 excepted art rows** — 12 `authoring_pending` (eight planet environments, `menu:cinematic_backdrop`, `syndicate:battleship` / `:bomber` / `:supercapital`) and 4 `keep_procedural_proposed` (`environment:deep_space_sky_dome`, `:jump_point`, `:nebula`, `:star`). Later authoring work, not an S08 prerequisite.
- **The `<16 px` readability floor** — measured ≈21.84 px but **unproven**; no waiver exists.
- **Two owner policy questions remain open and must not be answered by the implementer:** authoring-extent drift versus collision policy, and the advisory draw-call / texture-byte columns.

---

## 8. Next step: S08 — model replacement and mod compatibility

Goal (dependency table, not yet started): replacement/example packs work, failure is safe, revision/cache behaviour is honest, and save/replay tests prove cosmetic-only change.

Start here:

- `docs/BLENDER_MODEL_MIGRATION_ROADMAP.md` — §2.1 (delivery checkpoints through S07), the step table, and the §8 progress ledgers. Updated by #132; it now reflects reality.
- `docs/BLENDER_MODEL_S07_PLAN.md` — carries a status banner; read it as the acceptance criteria S07 was delivered against, including the "S07 can close only after required S06 coverage is complete or explicitly excepted" clause in §7.
- `assets/models/registry.json` + `tools/art/` — the resolver, contract, policies and pipeline this must extend rather than duplicate.
- `artifacts/s07-runtime-final/` — the harness patterns worth reusing: `build-final-receipt.py` (criteria as code, with negative controls), `compare-captures.py` (byte-bound comparison that refuses self-comparison), `verify-final-movie.py` (binds a candidate to a *named* review's declared bytes).

Non-negotiables carried forward:

1. Legacy default stays; opt-in only.
2. Every claim binds to bytes (hashes of renderer/registry/artefacts), and every gate refuses when its inputs move.
3. A green test that ran zero tests is not a pass — declare runner, prelude and fallbacks in the receipt.
4. Negative controls: prove each new guard bites by breaking it deliberately and restoring.
5. Merge via PR with true merge commits; never commit to `main` directly.

---

## 9. Open questions for the owner

1. When, if ever, to authorize S10 / the S11 default switch?
2. The `<16 px` readability floor: adopt a real threshold, accept ≈21.84 px, or waive it explicitly?
3. Performance targets and target resolutions for S09.
4. Re-authorize the deferred mixed-machine Windows test?
