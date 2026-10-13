# Station upgrades (#77)

Stations are upgradable in five levels the way veteran ships are ranked: level 1 is
the hull as it comes out of the yard and each of the four paid steps above it is
bought with a button on the station panel. This file is the contract the command,
the simulation, the HUD and the save format all share; `docs/DEV_PLAN.md` listed
defining it as the prerequisite for implementing #77.

## Eligibility

| Eligible | Excluded |
|---|---|
| Every station hull laid down by a construction ship or a shipyard: `command_station`, `mining_station`, `shipyard`, `research_station`, `defense_platform`, `sensor_station`, `trade_station`, `fighter_platform`, `repair_dock`, `energy_relay` | Everything built **on** a planet — the four surface buildings (`planet_extractor`, `planet_trade_hub`, `planet_shield_generator`, `planet_pulsar_cannon`) and the two orbit satellites (`defense_satellite`, `attack_satellite`) |

The issue excludes planet-built hardware explicitly, and satellites are built in a
planet's orbit slots, so they follow the same rule. A construction ship in transit
is not yet a station and cannot be upgraded.

## Levels, costs and timing

`Entity.upgrade_level` starts at 1 and is capped by
`station_upgrades.max_level` (5). Upgrade *n* is bought from level *n* to *n + 1*;
the four steps are tuned in `assets/data/game_rules.json`:

| Step | Cost (× the station's own build cost) | Refit time (× its build time) |
|---|---|---|
| 1 → 2 | 0.75 | 0.60 |
| 2 → 3 | 1.10 | 0.85 |
| 3 → 4 | 1.50 | 1.10 |
| 4 → 5 | 2.00 | 1.40 |

Costs scale with the station's catalogue cost, so a command station is a dearer
refit than a sensor station, and a full ladder costs 5.35× the hull plus 3.95× its
build time. The refit is **paid up front, queued on the station's own build queue
and completed on a timer** — the same shape as ship construction, so the station
must be operational and idle enough to hold the work. The station keeps operating
(shooting, earning, repairing) for the whole refit: it is work inside a live hull.
Only one refit may be pending per station, and the queue is serial, so a refit
orders itself behind any ship already building.

## Bonuses

Every level above 1 raises the hull, and the category bonuses follow the issue: a
hull that can fire gains firepower, a hull that collects gains output, a market
gains convoys.

| Effect | Per level | At level 5 | Applies to |
|---|---|---|---|
| Hull capacity | +10% of the as-built hull | +40% | every eligible station |
| Shield capacity | +10% of the as-built quad | +40% | every station with shields |
| Shield regeneration | +8% of the as-built rate | +32% | every station with shields |
| Weapon damage | +12% | +48% | stations whose catalogue carries a damaging weapon |
| Shots per volley | +1 shot per weapon mount | +4 shots | same |
| Resource output | +15% | +60% | stations whose catalogue carries `income` |
| Convoy cargo | +15% | +60% | markets (`trade_station`) |
| Convoy count | +1 convoy every two levels | +2 convoys | same |

The categories are read from the catalogue, never from the name: a hull is "armed"
when a weapon in its `weapons` list deals damage greater than zero, and "producing"
when it has an `income` table, so a mod that arms a mining station gets a firepower
ladder for it with no code change.

Damage and volley bonuses ride the existing stat aggregation
(`stats.effective_weapon_damage`, the per-mount `count` in `weapons.py`) and the
production bonus rides `stats.effective_production_rate`, so every system keeps
asking one helper. Hull, shield capacity and regeneration are stored entity fields
(damage, repair, AI strength and the digest all read them directly), so they are
raised once, when the refit completes: the new capacity is applied and the station's
current shield quads and hull are scaled with it, so an upgraded station is never
left at a fraction of the capacity it just paid for.

## Command

`upgrade_station` is a sibling of `cancel_build` — `PlayerCommand(target_id=<station>)`
submitted through the same serialized seam as every other order, and listed in
both command whitelists — `game/core/commands.py` (which is also the replay
allowlist) and `game/net/lan.py`.

The simulation re-checks everything: the station must exist, be alive, be operational,
be owned by the submitting player, be an eligible non-planet station hull, be below
the level cap, and have no refit already queued; the player must be able to pay the
step's cost. A rejected request changes nothing, pays nothing, and says why in a
float text. A refit is a queue edit like `cancel_build`, not new intent, so it is
dispatched *before* the command handler's supersede sweep and cannot strip another
standing order on its way through.

The panel only ever offers the row on a hull you own: the action panel drops every
entity whose owner is not the local player before it draws anything, and a row left
over from a station captured between the frame and the click is inert on the input
path (it must still name a live, owned station that is part of the current selection).

Refit work is cancellable through `cancel_build` (its own command, no special case
in the UI): because the price of a step depends on the station's target level and
its catalogue cost, the queued item carries the exact cost that was paid, and a
cancellation refunds 50% of that — the usual half pays for work already done.

## Persistence, migration and determinism

`upgrade_level` is a plain entity field, so it is written by the state graph and read
back by the strict decoder. `game/core/runtime_snapshot.py: migrate_saved_runtime`
adds a default of 1 to remembered entity graphs that predate the field, so a save
made before #77 loads as an all-level-1 fleet rather than failing schema validation.
The level is part of the per-tick desync digest
(`game/net/replay.py: state_digest`) — cheap and strict beats clever.

## Capture and AI policy

`upgrade_level` belongs to the hull, not to the owner: a captured station is worth
what its previous owner paid for it and keeps its level. The AI has **no upgrade
heuristic yet** — it accepts the command (the seam is owner-agnostic) but never
chooses to spend on a refit, and says so here rather than pretending parity. Closing
that gap means teaching the AI to value a station's refit against a new hull, which
is a balance decision, not plumbing.

## Verification

`tests/test_station_upgrades.py` covers eligibility and rejection paths, the cost and
time ladders, each bonus category, the queue seam, cancellation with its half refund,
save/load and old-save migration, the digest, and the HUD/input affordance.
`tools/diag_station_upgrades.py` renders the panel at both supported resolutions and
reports the geometry of the upgrade row.
