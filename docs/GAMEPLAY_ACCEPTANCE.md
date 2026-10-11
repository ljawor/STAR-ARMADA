# Gameplay acceptance — PR #39

## Scope and approved behavior

This branch reconciles the roadmap with released v0.7.0, increases all built-in
colonized-planet resource and crew rates (including additive crew bonuses) to
exactly 5×, and fixes campaign lifecycle integration. These follow-up changes
are not included in v0.7.0. No release or merge is implied.

Campaign mission objectives determine completion; skirmish command-station rules
must not freeze an active mission. Abandoned nonoperational hulls cannot hold
objective points or count as surviving forces. Destroy-all-forces objectives
ignore intact abandoned enemy hardware. Human force loss takes precedence over
survival completion on the same tick. Mission definition, objective progress and
terminal outcome persist through exact save/restore.

Skirmish/LAN coalition elimination is unchanged: capturing the last operational
enemy force ends the round; capturing its command center while other operational
enemy forces remain does not. AI autonomous engineer dispatch to unsafe abandoned
hulls remains out of scope and a documented limitation.

## Executed observations — October 10, 2026

- Broad sweep: **48 unique scenarios**, all four factions × four skirmish maps ×
  easy/normal/hard, at original map capacity with every slot AI-controlled.
  All reached **120 simulated seconds / 3,600 actual ticks**; **172,800 ticks**
  total, no scenario errors. Seeds are 390000–390047, indexed by canonical
  faction/map/difficulty order. All used the same catalogue-rules fingerprint.
  Observed 70 settlements, 610 station completions and 1,462 ship completions.
- Extended probes: each faction on `skirmish01`, normal difficulty, same-faction
  AI-versus-AI. All four reached **900 simulated seconds / 27,000 actual ticks**;
  **108,000 ticks** total, no scenario errors. None reached terminal victory.
  Convoy deliveries: Imperial 36, Rebel 26, Confederacy 54, Syndicate 54.
  Research completions: Imperial 10, Rebel 9, Confederacy 7, Syndicate 0.
  Syndicate had one abandoned hull and no crew transports at the final checkpoint;
  this does not establish successful autonomous field recovery. No boarding or
  crew-delivery events were observed in these self-play probes.
- Two independent localhost TCP processes: **300 simulation ticks**, **301 matching
  precise checksums**, 29.76/29.57 ticks per wall second; `DIAG_LAN_OK`.
  This is same-machine/macOS LAN evidence, not mixed-platform acceptance.
- Real Cocoa SDL/OpenGL colony diagnostic: **18 captures**, at 1280×800 and
  1024×768; `COLONIES_DIAG_OK`. Actual colony input, satellite production/capture,
  text containment, read-only render state and hardware pixel controls passed.
- Final delivery suite: **789 tests passed in 272.107 seconds** after all restore
  fixes and the main lifecycle fixture update; compile and diff checks passed.
  Existing unclosed-file ResourceWarnings in test_audio/test_persistence remain
  non-failing warnings. Independent final campaign restore re-review passed.
- Focused campaign/boarding/objectives/victory/persistence run: **56 tests passed**;
  final campaign/main/GL-lifecycle fixture regressions: **19 tests passed**.
  Earlier 776/786-test runs are historical intermediate results, not the final gate.

## Evidence and reproduction

Raw local JSON evidence is retained under Hermes scratch:
`star-armada-acceptance-broad-120/matrix.json`,
`star-armada-pr39-long/matrix.json`, `star-armada-pr39-lan/`, and
`star-armada-pr39-colonies/`. These are local artifacts, not committed evidence.

```bash
.venv/bin/python tools/diag_gameplay_acceptance.py --out <scratch>/broad --seconds 120 --wall-limit 120
.venv/bin/python tools/diag_gameplay_acceptance.py --out <scratch>/long --seconds 900 --wall-limit 120 --maps skirmish01 --difficulties normal
PYTHONPATH=. .venv/bin/python tools/diag_lan.py --out <scratch>/lan --ticks 300
PYTHONPATH=. .venv/bin/python tools/diag_colonies.py --out <scratch>/colonies
PYTHONPATH=tests .venv/bin/python -m unittest test_campaign_lifecycle test_colony_income_balance -q
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -q
```

## Gates still open

- Native interactive Windows and mixed-platform LAN playtests (explicitly deferred).
- Statistical/mixed-faction full-match balance and complete campaign playthrough QA.
- AI autonomous repair dispatch to unsafe abandoned hulls; Syndicate full parity.
- The self-play probes do not demonstrate boarding or field crew-delivery acceptance;
  authoritative focused regressions provide separate mechanic coverage.
- Support-order GL diagnostic failed twice at the real-pointer-over-production-list
  precondition; it remains unverified, not a pass. No support-control production code
  was changed in this increment.
- Historical restored entity-bearing checksums failed on `SubsystemStub`. The
  subsequent campaign/replay increment restores canonical subsystem objects and
  persists future AI/system state; extended exact save/replay continuation tests
  cover the corrected path. Old files lacking runtime state cannot recover
  historical AI strategy and carry a compatibility warning.

No other recruitment/repair/combat prices or AI thresholds were silently retuned.
