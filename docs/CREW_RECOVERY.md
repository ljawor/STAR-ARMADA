# Crew recovery, proportional staffing and cautious AI

Merged in PR #38 and packaged in v0.7.0; full-match balance and native Windows/mixed-platform interactive acceptance remain open.
Boarding/life support itself was merged in #37 (`1ca3207`). Recovery adds no towing,
neutral salvage, sale, conversion or allied-hull reclaim.

## Playable loop

- An abandoned hull remains alive and owned. Its owner may recrew it; enemies must
  use boarding/capture first. Allies can provide base service, not take the hull.
- Owned ships, squadrons and stations automatically recruit near an **operational
  friendly command station, shipyard or repair dock**, using the hull owner's
  unassigned crew pool and credits. The base does not contribute its owner's pool.
- Life support must be **at least 50%** before any recruitment or passenger delivery.
  Existing external repair docks/drones repair equipment, never resurrect crew.
  An empty hull cannot travel to a dock or activate its own abilities: send external
  support, then crew. No automatic teleportation or towing exists.
- Build a faction crew transport at an eligible shipyard. Select it and press **L**
  or click **Load passengers at friendly base**. Loading is timed and requires base
  proximity, a functioning operating complement and safe transport life support.
- Press **R** / **Deliver crew to owned hull**, then click your understaffed hull.
  The transport travels using normal movement and transfers only inside 3D range.
  Delivery is explicit: parking a loaded transport beside a hull does nothing.
- **Cancel crew order**, Stop, Move, Attack, Hold or Jump interrupts the mission;
  actual passengers remain aboard. Escape cancels target-pick mode without changing
  simulation state. **R** remains Research for other selections.
- The inspector separates **CREW onboard/max**, **CARGO passengers/capacity**,
  **STAFF %**, life support and next-person progress/live blocked reason. Zero-crew
  hulls show **ABANDONED**. UI and AI queue serialized intent, not direct transfers.

## Initial balance choices (configurable; not final balance)

These defaults are implementation proposals, not user-specified numeric rates.
Change `crew_recovery` in `assets/data/game_rules.json`:

| Rule | Initial value | Meaning |
|---|---:|---|
| `base_range` | 600 | 3D centre distance minus servicing base radius |
| `transfer_range` | 180 | 3D centre distance minus both hull radii |
| `recruitment_rate` | 4/s | Both operating recruitment and passenger loading |
| `delivery_rate` | 8/s | Already-loaded passengers transferred to target |
| `credits_per_crew` | 2 | Charged with one unassigned crew at recruitment/loading |
| `support_threshold` | 0.50 | Minimum support fraction for personnel admission |
| `base_types` | command station, shipyard, repair dock | Operational allied service providers |
| `ai_support_retreat` | 0.65 | Prefer repair dock below this support fraction |
| `ai_staffing_retreat` | 0.60 | Prefer friendly base below this staffing fraction |
| `ai_board_ratio` | 1.5 | Boarding party must exceed visible defenders by this ratio |

All four selectable factions have a distinct data ID (`imperial_crew_transport`,
`rebel_crew_transport`, `confed_crew_transport`, `syndicate_crew_transport`), with
initially identical balance: 24 operating crew, 240 passenger capacity, 550 credits /
300 materials / 75 energy construction cost, command cost 2, build time 15 seconds,
1200 hull, 200 shields per quadrant and speed 70. They are unarmed, use their faction's
solid shaded convoy hardware, and render at 0.8 corvette length. Existing ships retain
their original data/geometry. Passenger capacity belongs to ship data, not geometry.

## Personnel accounting and authoritative safety

One pool crew plus credits is consumed **once**, when recruited or loaded. Delivery
moves cargo into the target's operating complement without charging again. Fractional
progress is timed, not banked while resources/safety/range are absent; no resource debt
or over-complement transfer is allowed. Competing consumers resolve in entity-ID order.
Operating recruitment and passenger loading are separate consumers, even on one ship.

Passengers never power a hull or raise its staffing fraction. Both operating crew and
passengers suffer the existing life-support failure casualty rule, with independent
fractional casualty accumulators. Destruction loses all cargo; it does **not** return
passengers to the pool. The existing destruction reclaim fraction applies only to
surviving operating crew. Cancellation does not unload/refund passengers. Capture
retains actual cargo but clears the old owner's mission and recruitment progress;
the new owner must issue a new valid order. Boarding-party surplus returns only up to
the source's complement, then to the party owner's pool, preventing auto-replenishment
from creating an overfilled source.

Commands recheck source ownership, operating state, transport capacity and target
eligibility on consumption. Missions revalidate before movement and on transfer.
Ownership/destruction invalidates dependent recovery orders; dead/hostile targets do
not remain follow destinations. Unsafe support/range/resources pause progress, with
live reasons; full targets/holds and empty cargo finish orders. Accepted recovery
orders detach fleet/jump intent. Recovery completes only after physically reaching
its chosen base and restoring the full operating complement. At a recruitment-only
base, life support need only be safe (at least the configured AI support-retreat and
personnel-admission thresholds; initially 65%), not fully repaired. A usable own
repair dock instead finishes life-support repair to 99%. Allied docks provide
recruitment service but currently do not repair another owner's life support.

## Proportional staffing

`game/systems/stats.py` defines the capped onboard/max complement fraction. It scales
weapon damage, movement speed/turn, sensors, construction, station production, research,
external repairs and hangar repair/reinforcement once through the relevant effective
stat/helper. Auxiliary boarding craft and commercial convoys use the same speed helper.
Cargo is excluded. Full-complement multipliers remain 1. Shield regeneration, weapon
cooldown and life-support subsystem effectiveness are not additionally staff-scaled.
Life-support casualty risk depends on equipment health, avoiding a staffing-driven
support/casualty feedback loop. Crew changes participate in sensor-cache fingerprints,
so same-tick visibility does not reuse a stale range.

## Cautious AI and limits

AI reserves recovery transports and deployed boarding sources from ordinary combat
fleet retasking. It routes damaged support toward an operational friendly repair dock,
otherwise routes understaffed ships to a base. It can request repair infrastructure
when an existing constructor has that faction capability, and builds a missing crew
transport for safely supported owned stranded hulls. Transports load/recover/deliver
through the same command handlers as players. Boarding decisions require detection,
legal shield/disable conditions and a favourable visible defender ratio; hidden enemy
crew/position are not inspected to select a boarding target.

This is a cautious heuristic, not optimal evacuation/pathfinding: a zero-crew hull with
unsafe support still needs external repairs; no transport repairs it. AI does not gain
new faction construction abilities or invent missing pools/credits. Syndicate's wider
catalogue/infrastructure parity remains incomplete. Long full-match balance, campaign
crew tutorials, mixed-platform LAN and native packaged release playtests remain separate
acceptance work; this increment does not claim those were completed.

## Persistence and verification

Recruitment progress, passenger cargo/loss accumulators, mission phase/owner/target/
progress/reason and command-capacity timer serialize exactly. Legacy saves default
new fields safely. Recovery state contributes to replay checksums. Tests compare exact
JSON-normalized precise state every real tick during loading/delivery/casualties,
mid-recovery AI restore, and a 700-tick recorded command replay (not checksum alone).

```bash
PYTHONPATH=tests .venv/bin/python -m unittest test_crew_recovery test_crew_recovery_lifecycle test_staffing test_crew_recovery_ai test_crew_recovery_ui -v
PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m compileall -q game render tools/diag_crew_recovery.py main.py
git diff --check
PYTHONPATH=. .venv/bin/python tools/diag_crew_recovery.py --out /absolute/scratch/crew-gl
```

The diagnostic requires real SDL/OpenGL (no dummy driver), at 1280×800 and 1024×768.
It drives actual load/cancel/deliver HUD buttons and owned-world picks, rejects unsafe
support, activates an eligible external repair ship via the authoritative ability
command, advances real travel/delivery, and reads the real framebuffer before flip.
It checks glyph pixels, bar separation, inspector/control containment, read-only precise
render state, GL errors, compact empty selection, and frozen same-state draw-disabled
hull differences/shading for all four faction transports. PNGs and `metrics.json` are
written to the requested evidence directory; inspect the actual captures as well as
machine assertions. Headless tests may print existing unclosed-file ResourceWarnings
in `test_audio.py` / `test_persistence.py`; these are not new recovery failures.
