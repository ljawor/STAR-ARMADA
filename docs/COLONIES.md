# Planetary colonies and satellites

## Approved gameplay contract

- Each built-in faction (Imperial, Rebel, Confederacy and Syndicate) has a colony ship, built **only at a command center**. Adding Syndicate's colony ship does not enable full Syndicate gameplay parity or change its non-playable catalogue flag.
- Non-gas planets may be colonized. Gas giants and asteroid terrain cannot become colonies; gas-giant energy relays remain available.
- A colony belongs to a player, not globally to everyone using that faction. Its owner receives crew and planet-type resource income.
- Select a colony ship and right-click an eligible neutral planet to settle it or an enemy colony to capture it. Own and allied colonies cannot be captured.
- Capture requires destroying **every live satellite attached to the planet** first. Abandoned satellites still block capture and cannot be boarded instead.
- The ship approaches, then completes a control timer. Leaving range, a replacement order, loss of the ship, loss of operational crew, ownership changes or a newly built defending satellite interrupt control. Damage alone does not reset progress.
- A colony ship is consumed only when settlement/capture succeeds. There is **no additional settlement/capture fee**; building the ship supplies its personnel and resources. A competing unsuccessful ship survives.
- Select an owned planet to build satellites through its HUD. Build costs are charged when the simulation accepts the command. Both satellite roles share one per-planet capacity, including paid queued construction.
- Defense satellites intercept hostile missiles and engage hostile fighters. Attack satellites engage hostile ships.
- Capture transfers future income and loses the previous owner's unfinished satellite construction without refunds.
- AI follows the same serialized commands, expands to eligible planets, builds both satellite roles and attacks detected defending satellites before attempting capture. It must not inspect hidden live planetary ownership.

## Initial tuning, not final balance

`assets/data/game_rules.json` contains the `colonies` block:

| Setting | Initial value |
|---|---:|
| `control_seconds` | 15 seconds |
| `satellite_cap` | 6 shared slots |
| `approach_range` | 600 units beyond the planetary surface |
| `orbit_clearance` | 350 units beyond planet + satellite radii |

Satellite costs, crew, hulls, weapons and production time are data-driven in `assets/data/stations/stations.json`. Planet income is configured in `economy.planet_income`, with existing `planet_crew_bonus` added once. Every built-in eligible planet type supplies some crew and at least one economic resource. These numeric defaults require long-match balancing.

## Persistence and compatibility

The existing `colonized_by` field is authoritative for colony ownership; planets remain neutral terrain under `owner`. Satellites persist their `planet_id` and `satellite_slot`. Mission queues retain source/target ownership and full-precision timers in precise saves.

Legacy gas-planet ownership is retained as historical save data, but cannot provide colony income or authorize satellite construction. Energy production near gas giants uses energy relays instead. For compatibility, legacy command-mode planet-majority/economic requirements and timed scoring still count that saved ownership; ordinary skirmish/LAN elimination does not use planet ownership to determine victory. New matches cannot create gas colonies.

The `build_satellite` command is registered for serialized commands and LAN validation. This source increment is **implemented and verified, awaiting merge**, not packaged. Acceptance: **699 full-suite tests passed**, independent review passed, and the real SDL/OpenGL diagnostic passed at both 1280×800 and 1024×768 with 18 captures. Python compilation and diff checks passed. Existing test-helper unclosed-file ResourceWarnings remain non-failing warnings. This does not establish native Windows or cross-platform LAN gameplay acceptance.

## Verification

```bash
PYTHONPATH=tests .venv/bin/python -m unittest test_colonies test_colonies_ui -q
PYTHONPATH=. .venv/bin/python tools/diag_colonies.py --out <scratch-directory>
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -q
```

The real SDL/OpenGL diagnostic exercises physical selection, right-click colony intent, the planet's build buttons, progress, construction and capture at 1280×800 and 1024×768. It checks render-state immutability and satellite pixels against a draw-disabled control. Full-precision restoration tests compare exact JSON-normalized state on continuation, not only replay hashes.
