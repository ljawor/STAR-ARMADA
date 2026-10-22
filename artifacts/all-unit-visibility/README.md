# Late-built ship visibility — native census

Root cause: per-session binding tables were seeded from starting entities and
future stations, but not future ships. A paid Colonial Outreach Frigate completed
normally and then had no published hull record. Its model already existed in the
shipped native catalogue. Reserve all loaded ship bindings and weapon IDs once at
session startup; never rebuild or change table indices during the match.

Evidence:
- Authored-selection regression: real paid command-station colonizer queue,
  completion after tables already existed; failed before fix, passes after.
- Full native pixel census: **105 unique rows, 105 passed**: 37 loaded ship IDs,
  16 station IDs for each of 4 factions (64 rows), plus 4 automatically generated
  faction trade convoys. Exact manifest/results JSONL/CSV and per-entry captures.
- Each native row is the ONLY instance. No HUD, ownership marker, fog or effects
  are published. Empty-frame control at the same camera is subtracted; the smallest
  hull had 3,859 changed pixels (threshold >40, pixel delta >12/255).
- Tables created before any audited entity. All bindings exist in the shipped
  native catalogue. One continuously running native Metal renderer consumed all
  entries, with 3 readback frames per empty/object state.
- 377 targeted Python/integration regressions passed, including natural paid
  inputs, host/join recovery and replay, resolution and earlier fog/station fixes.

IMPORTANT: This native census uses UnitFactory-created real entities for isolated
visual inspection. It does NOT by itself prove all units can be paid-built; a
separate exhaustive paid-build audit is pending. Automatic convoys were generated
by TradingSystem.update with two market prerequisites, not passed off as buildable
player queue items. Captures are diagnostic isolated views, not a live playthrough.

Existing WIP renderer lifecycle/fatal/concurrency/packaging blockers remain open.
No overall merge/release, packaged runtime or Windows acceptance is claimed.
