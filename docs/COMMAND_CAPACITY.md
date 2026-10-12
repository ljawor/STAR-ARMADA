# Infrastructure command points (#70)

Implemented on `fix/infrastructure-command-points`; not a merge or release claim.

## Accounting contract

- Every living station consumes **1 CMD**, including command centers, satellites
  and surface buildings. The research station consumes **5 CMD**. Existing ship
  and squadron catalogue costs remain unchanged; data-less trade convoys and
  terrain consume zero.
- Paid ship, station, satellite and surface-building queues reserve the complete
  catalogue CMD cost immediately. The top-bar **CMD used/capacity** includes both
  living hardware and these paid reservations, so it matches build admission.
  Unconsumed player/AI commands are intent, not paid reservations; commands are
  admitted sequentially and cannot spend the same last command point twice.
- Build admission checks CMD before paying. Rejected orders spend no resources
  and create no paid work; builders/planets display **Command capacity reached**.
  Existing build-row painters now read the station CMD field, showing 1 or 5
  instead of the old zero. No new render-side simulation writes are introduced.
- Every living eligible colony supplies the same capacity as the loaded
  `command_station.command_capacity` (**20** in the built-in catalogue). Read
  `colonized_by`, not the neutral terrain `owner`. The former military-only +5
  bonus is replaced, not added. Gas giants/asteroids and invalid legacy gas
  colonies provide no capacity, consistent with their existing production rules.
- Base capacity, operational stations' existing capacity contributions and
  research bonuses remain additive exactly once. Capacity uses the existing
  manager's **1 Hz refresh**, plus existing explicit refreshes on setup/boarding.
  Settlement/capture and capacity-provider destruction are reflected on that
  normal refresh; this issue does not introduce a new capacity-update cadence.

## Lifecycle and compatibility

Abandoned but living hulls still consume CMD, and their paused paid queues retain
reservations. Only operational stations supply their catalogue capacity, as before.
Destroyed hulls/queues release usage; canceled work releases its reservation using
existing cancellation/refund rules. Ownership changes transfer living usage.
Colony capture clears old paid work without a refund and transfers completed surface
buildings, so old reservations disappear and surviving hardware counts for its new owner.

Losing capacity can leave a player above the limit: it blocks new admission, **not**
existing hardware or completion of already paid work. New command centers must
reserve their own 1 CMD before contributing capacity when operational. This preserves
the existing ship-production semantics rather than inventing eviction or retroactive
payment/refund policies.

No new save fields or migrations are needed: usage/reservations are derived from
persisted live entities, paid queues and colony ownership. Existing snapshots load
under the currently selected catalogue. Ordinary saved CMD capacity retains the
existing refresh behavior. Precise manager-restore regressions compare complete
JSON-normalized state on every tick, not only replay checksums.

## Mod surface

Station `command_cost` is a nonnegative JSON integer (booleans, strings, fractional
and negative values are rejected). Omission defaults to 1, or 5 for
`research_station`, preserving legacy catalogue/mod files. Explicit mod costs are
literal overrides. Colonies read the modded command-center capacity, never a
hard-coded second copy of 20 or the removed military-only rule keys.

AI keeps its existing policy and resource reserves; its serialized build commands
pass through the same authoritative admission and paid-reservation accounting.
No new AI expansion doctrine is implied.

## Focused verification

```bash
PYTHONPATH=tests .venv/bin/python -m unittest test_infrastructure_command -v
PYTHONPATH=. .venv/bin/python tools/diag_infrastructure_commands.py --out <scratch>
```

The regressions cover all station catalogue entries, all eligible colony types,
real mod loading, atomic rejection, simultaneous last-point purchases, completion
above capacity, abandonment/destruction, capture, and exact restored manager ticks
through mixed paid production and ownership changes. Completion clocks are explicitly
accelerated **after real paid admission** in the lifecycle fixtures; they do not claim
natural-timing human playthrough acceptance.

The real Cocoa/OpenGL diagnostic enumerates every constructor, surface and orbital
build row at 1280×800 and 1024×768, asserts the painted CMD costs and row containment,
reads the real top-bar painter's committed total, captures framebuffers, checks GL
errors and preserves exact simulation state. Paging is programmatic; this is not
native mouse-focus/wheel acceptance.

The parent integration gate must still run the stable combined-tree full suite
serialized, independent review and any requested native packaged/platform acceptance.
