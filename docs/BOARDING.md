# Boarding, crew and life support

## Design source and scope

The original master prompt §27 specifies: disable the target, launch boarding craft,
fight for control, then capture or destroy. It suggests repair, sale, conversion,
research and temporary use as potential uses of captured vessels. This implementation
provides the disable / physical craft / contested control / capture loop for enemy
ships and stations. Destruction remains normal combat; losing a boarding fight does
not automatically detonate the target. Captured hulls retain their original hardware
and can be commanded and repaired by the new owner.

The numeric thresholds below are configurable implementation defaults, not numbers
specified by the original prompt. Selling, conversion, captured-tech research,
limited-duration ownership, AI boarding doctrine, neutral salvage and friendly
recrewing are not implemented by this change.

## Player controls

1. Select your frigates, cruisers, battleships or supercapitals.
2. Bring a detected hostile hull within boarding range and lower **every shield
   quadrant**. PR #40 removes the disabled-subsystem prerequisite for staffed
   targets. Successful capture stabilizes life support to at least 10% health,
   without restoring dead crew. Destroyed shield generators prevent regeneration;
   otherwise regenerated shields interrupt the attempt.
3. Press **B** or click **Board enemy hull**, then left-click the target.
4. A real, damageable boarding craft transports a party drawn from the source ship's
   onboard crew. The source leaves its formation, holds position and ceases firing
   at that target; other ships still follow their own combat orders.
5. The inspector displays `BOARDING TRANSIT`, `CONTROL` or `RETURN`, progress and
   surviving party size. The enemy can destroy the craft or defeat the party.

Esc / right-click cancels *target selection*. Stop or another command to the source
interrupts a deployed mission and returns surviving party members. Losing detection,
range, target eligibility or original target ownership also triggers return. Loss of
source ownership, source crew or source hull fails the mission. The party's survivors
are lost if there is no operational source to return to.

## Onboard crew and abandonment

Every factory ship, squadron, convoy, boarding craft and station has onboard
`crew`, `max_crew` and a damageable `life_support` subsystem. Catalogue complements
use `crew_cost`, minimum one; the complement is **not** the player's unassigned crew
resource. Planets do not use this system. Legacy saves receive catalogue complements
and healthy life support when those fields are absent.

Life support below 25% health starts gradual casualties. The default rate scales
linearly from zero at 25% health to one crew member per second at total failure.
Fractional casualties accumulate deterministically across ticks and saves. Operational
repair docks and repair drones can restore nearby owned hulls' life-support equipment;
they never regenerate dead crew.

At zero crew the intact hull is **abandoned**, not destroyed and not made neutral.
It retains its previous owner and may still be detected and damaged. It no longer
moves, fires, observes, runs abilities, generates income, researches, builds or acts
as a hangar. Active orders, jumps and fleet membership are cleared; shields collapse.
Abandoned command stations do not prevent annihilation defeat. Empty hulls have no
boarding resistance and no disable-subsystem requirement, so capture is easier.
Capturing a hull with broken life support does **not** repair that equipment: the new
crew continues to suffer casualties unless external support repairs it.

## Capture and conservation

Parties take 25% of the source complement, rounded down with a minimum of one, while
leaving at least one member aboard. Sources need at least two crew and may deploy
only one party at a time. Boarding craft cannot receive ordinary fleet/movement orders.

Control progresses at `dt / (control_seconds + resistance_seconds * defenders / party)`.
Staffed defenders and attackers incur deterministic mutual casualties weighted by
relative complement size. Once control reaches 100%, surviving attackers crew the
captured hull up to its complement; excess attackers return to the source. Remaining
defenders are removed from the operational complement (they do not become a free
crew-resource refund). Competing parties resolve in stable craft-ID order; parties
whose target changed owner return instead of capturing it again.

Capture clears old orders, fleet membership, jump state, active abilities, build
queues, hangar references and trade endpoints. Research jobs pinned to the captured
station are removed, and command capacity is recomputed. Paid old-owner queues are
lost rather than refunded to either side. Crew and resource pools are not minted by
capture. Destroyed ships reclaim only the configured fraction of their **remaining**
onboard crew, rather than their original catalogue complement.

## Data and determinism

`assets/data/game_rules.json` → `boarding`:

| Setting | Default |
|---|---|
| `life_support_failure_fraction` | 0.25 |
| `life_support_loss_per_second` | 1.0 |
| `range` | 500 units beyond source + target collision radii |
| `party_fraction` | 0.25 (must not exceed 0.5) |
| `craft_speed` | 180 units/sec |
| `craft_hull` | 80 |
| `control_seconds` | 5 |
| `resistance_seconds` | 20 |
| `combat_losses_per_second` | 1.0 |
| `capable_categories` | frigate, cruiser, battleship, supercapital |

Numeric settings must be finite and positive. Omitted settings in older mods use
simulation defaults. Catalogue `systems.life_support` can override the default
100-HP subsystem. All crew, fractional casualty accumulators, craft mission phases,
control progress and source-party references are persisted and covered by replay
checksums. No wall-clock or renderer mutation determines boarding outcomes.

## Verification

```bash
PYTHONPATH=tests .venv/bin/python -m unittest test_crew test_boarding test_boarding_ui -q
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=. .venv/bin/python tools/diag_boarding.py --out /path/to/evidence
```

The GL diagnostic drives a real HUD button and world target pick, queues serialized
intent, advances real manager ticks, captures transit/control/captured stages at
1280×800 and 1024×768, checks read-only state, text/bar separation, hitbox containment,
OpenGL errors and craft-specific framebuffer pixels. Simulation regressions include
illegal targets, resistance/party defeat, ship and station capture, competing parties,
crew conservation, interruption, life-support repair, legacy saves and full-precision
JSON equality after restore at every boarding tick.
