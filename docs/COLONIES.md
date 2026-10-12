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
- Destroying a satellite locks **the site it occupied** for `satellite_penalty_seconds` (180 s). While the penalty runs the slot cannot be rebuilt in, the orbit panel prints `REBUILD <time left>` instead of `FREE`, and the slot search places the next paid satellite elsewhere. It is world state: it survives save/reload, replay digests and a capture of the planet. Re-destroying a satellite on a locked site can only push the deadline out.
- AI follows the same serialized commands, expands to eligible planets, builds both satellite roles and attacks detected defending satellites before attempting capture. It must not inspect hidden live planetary ownership.

## Initial tuning, not final balance

`assets/data/game_rules.json` contains the `colonies` block:

| Setting | Initial value |
|---|---:|
| `control_seconds` | 15 seconds |
| `satellite_cap` | 6 shared slots |
| `approach_range` | 600 units beyond the planetary surface |
| `orbit_clearance` | 350 units beyond planet + satellite radii |
| `orbit_shell_spacing` | 160 units added per successive satellite slot: each slot rides its own orbit shell |
| `satellite_penalty_seconds` | 180 seconds: how long a destroyed satellite's slot stays unbuildable |

Satellite costs, crew, hulls, weapons and production time are data-driven in `assets/data/stations/stations.json`. Planet income is configured in `economy.planet_income`, with `planet_crew_bonus` added **once**. The built-in resource rates and additive crew bonuses have both been increased to exactly **5×** their previous values; station income (including mining, trade and energy relays), convoy rewards, AI difficulty multipliers, command-capacity bonuses and all costs are unchanged. These numeric defaults still require long-match balancing.

Effective output per second, including crew bonuses (**v0.8.0 income balance change from PR #39; not included in v0.7.0**):

| Planet type | Credits (old → new) | Materials (old → new) | Crew (old → new) |
|---|---:|---:|---:|
| Temperate | 1.2 → 6 | 0 → 0 | 0.4 → 2 |
| Industrial | 0.4 → 2 | 1 → 5 | 0.1 → 0.5 |
| Agricultural | 0.5 → 2.5 | 0 → 0 | 0.8 → 4 |
| Military | 0.3 → 1.5 | 0 → 0 | 0.3 → 1.5 |
| Research | 0.6 → 3 | 0 → 0 | 0.1 → 0.5 |
| Barren | 0.2 → 1 | 0 → 0 | 0.05 → 0.25 |
| Trade | 1.8 → 9 | 0 → 0 | 0.1 → 0.5 |

All eligible built-in planet types produce zero energy. Temperate base crew is now 1.25 plus 0.75 bonus; agricultural base crew is 2.5 plus 1.5 bonus. Gas giants remain ineligible and provide no colony output, including legacy saved gas colonies.

This is a data-only default change, not a runtime multiplier: the simulation and HUD read the same configured rates. Mods replacing `game_rules.json` retain their literal configured output; omitted income/bonus tables still default to empty, without inheriting built-in rates or an implicit 5× multiplier. Existing saves use the currently loaded catalogue rules on restoration, since economic rates are not stored in the saved state.

## Persistence and compatibility

The existing `colonized_by` field is authoritative for colony ownership; planets remain neutral terrain under `owner`. Satellites persist their `planet_id` and `satellite_slot`. Mission queues retain source/target ownership and full-precision timers in precise saves.

The lockout is stored on the planet as `satellite_locks` (`{slot: sim time the penalty ends}`), so it reloads and replays exactly; `game/net/replay_validation.py` rejects a lock map on anything but a live planet, with a slot outside `satellite_cap` or with a non-finite/negative deadline. Render code only ever reads it (`colonies.satellite_lock_remaining`) — expiring entries are pruned by the simulation, never by a draw call.

Legacy gas-planet ownership is retained as historical save data, but cannot provide colony income or authorize satellite construction. Energy production near gas giants uses energy relays instead. For compatibility, legacy command-mode planet-majority/economic requirements and timed scoring still count that saved ownership; ordinary skirmish/LAN elimination does not use planet ownership to determine victory. New matches cannot create gas colonies.

The `build_satellite` command is registered for serialized commands and LAN validation. The colony increment and follow-up support orders are **merged in #40 and packaged in v0.7.0**. Historical acceptance after support-order integration: **766 full-suite tests passed**, independent review passed, and real SDL/OpenGL diagnostics passed at 1280×800 and 1024×768. Existing test-helper unclosed-file ResourceWarnings remain non-failing warnings. This does not establish native interactive Windows or cross-platform LAN gameplay acceptance, nor acceptance of the branch-only 5× income change.

## Verification

```bash
PYTHONPATH=tests .venv/bin/python -m unittest test_colonies test_colonies_ui -q
PYTHONPATH=. .venv/bin/python tools/diag_colonies.py --out <scratch-directory>
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -q
```

The real SDL/OpenGL diagnostic exercises physical selection, right-click colony intent, the planet's build buttons, progress, construction and capture at 1280×800 and 1024×768. It checks render-state immutability and satellite pixels against a draw-disabled control. Full-precision restoration tests compare exact JSON-normalized state on continuation, not only replay hashes.

### Satellite slot lockout (#57)

`tests/test_satellite_penalty.py` covers it end to end: a cruiser kills an `attack_satellite` through the real damage path, the lock appears at exactly 180 s, the next paid satellite is reserved in a different slot, the slot frees itself 180 s later, the deadline survives a `to_dict(precise=True)` round trip with bit-identical continuation, malformed lock maps are rejected by the replay schema, a capture of the planet keeps the wreck penalty, and the AI does not queue into a fully locked orbit (with a non-vacuity control that removes the lock and sees the same decision fire). The panel text is asserted through the real HUD with the labels captured, at both ends of the countdown.

### Orbital velocity and ship fire (#62)

Unengaged satellites now report `vel = (accepted_position - previous_position) / dt`
from their actual orbital displacement. This lets existing projectile lead hit a
moving defense satellite without changing its targets: defense still engages only
fighters and missiles, never cruisers. The orbit system remains the sole position
integrator; movement and separation skip stations, preventing double integration.
Engagement, abandoned crew, a fully blocked orbit or a missing parent clears velocity
to zero; partially blocked ticks report only accepted travel. Orbital phase, velocity
and projectile state use the existing precise save/replay fields.

`tests/test_satellite_velocity.py` verifies both roles' position/velocity consistency,
engagement and resumption, blocked/abandoned motion, phase wrap, zero-duration ticks,
missing parents, precise saved/replayed combat continuation and real cruiser kills
with the existing slot lockout. On the controlled 1,500-unit cruiser fixture, defense
went from **6 hits / 431 projectiles, no kill in 300 s** to **115 hits / 131 projectiles,
one kill in 106.233 s**; defense fired zero shots back. Attack also remains killable
(**107 hits / 110 projectiles, one kill in 109.033 s**). These are regression-fixture
measurements, not a balance retune or natural-playthrough acceptance.
