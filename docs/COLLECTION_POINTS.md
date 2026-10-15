# Station collection points (#105)

## Player contract

- Select an owned operational ship-producing station (including fighter platforms), then right-click empty battlefield space. The destination is queued as a normal human command; input and drawing never directly mutate simulation state.
- The station Actions / Build panel shows the destination coordinates and **Clear collection point**. Clearing is also queued, rechecks current selection/ownership, and does not cancel paid production, refund resources, or rewrite existing units' orders.
- A selected owned producer displays a turquoise station-to-destination link and diamond/cross endpoint. The marker is presentation-only.
- Ordinary minimap right-click orders are **not supported**. They are ignored rather than incorrectly projecting minimap pixels onto battlefield ground. Minimap camera navigation and explicit jump targeting retain their existing paths.
- Empty-space orders on mixed selections set eligible stations' destinations and retain attack-move for owned mobile hulls. Clicking a hardware target retains existing attack/colonize priority; it does not set a collection point.

## Simulation and wire contract

`CollectionPointCommand(player, station_id, target=None)` emits type `collection_point`, the owning player, station `target_id`, and optional three-coordinate `target_pos`. Omitted/null position clears. The LAN/replay schema requires the station target and rejects unrelated payload fields.

At consumption time the source must be an owned station, alive, crewed, not being boarded, and have a station definition with `builds_ships`. Dead, abandoned, foreign and nonproducing stations cannot change their destination. Coordinates must be exactly three finite int/float values, excluding booleans, each within inclusive ±1e9. Invalid intent leaves the existing point untouched. Set/clear is a production edit, not a replacement standing unit order.

Normal upfront payment, build eligibility, queue progress, seeded spawn offset and ship-built events are unchanged. A completed ship samples the station's **current** destination, copies it into a `move` order, and travels normally; it is not teleported to the point. The copy prevents later set/clear from redirecting already-built hulls. No destination preserves the existing idle birth behavior. Fighter replenishment must not discard an existing move/attack-move/attack/explore order on departure.

## Persistence and compatibility

- Configured points are included at full precision in entity save projections and typed manager/runtime/reconnect snapshots. Default `None` is omitted from the legacy entity projection.
- Saved-runtime migration supplies only a missing `collection_point=None`; an existing point is preserved. Save restoration and reconnect snapshots are tested through an ensuing queued birth and aligned simulation ticks, not only field equality.
- Replay command validation uses the collection-point wire contract. New recordings preserve set/build/clear with accepted simulation ticks and replay to identical per-tick precise digests.
- Legacy `state_checksum` changes only when a point is configured. The default fixture digest was independently measured with the pre-#105 HEAD implementation and pinned as `8758ea70dbe5b52ef3ca287fe33c509aa5ccf6d86f697ff41e270c31204325a6`; clearing restores it.
- Save migration does not silently rewrite old strict replay runtime graphs. A replay runtime missing the new entity field is rejected. This is distinct from permissive legacy projection loading; do not promise exact continuation for old runtime-less recordings.

## Acceptance evidence (local macOS / Apple M4)

Evidence root: `/Users/lukaszjawor/.hermes/cache/scratch/collection105/`.

### Focused protected tests

Read the safety launcher before use. From repository root:

```sh
ARMADA_VERIFY_OUT=<new-external-evidence-directory> \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. .venv/bin/python \
  /Users/lukaszjawor/.hermes/cache/scratch/star-armada-release-safety/protected_suite.py \
  test_collection_points test_collection_points_lan test_fighter_exploration \
  test_build_cancel test_station_upgrades test_checksum_canonicalization -q
```

`review-final/run.log`: **125 tests in 19.590s, OK**. `review-final/safety-result.json`: native sandbox enabled, child return code 0, source and user data preserved, zero audit violations, success true. No full suite was run in this review.

Coverage includes real paid shipyard and fighter-platform production/departure, latest destination at completion, no teleport/shared Vec3, clear preserving paid work and existing hulls, ownership/operational/boarding gates, malformed coordinates/wire fields, save/runtime migration and strict replay validation. The new continuation check restores both saved runtime and reconnect snapshot immediately before a paid ship completes and compares all subsequent aligned hashes.

`test_collection_points_lan` uses actual loopback TCP, both host and client origins, natural right-click/build/clear through production input/main seams, one paid birth, exactly one consumed build entry and exactly three recorded commands (set/build/clear). Its first accepted set is tick 3. It compares peers at aligned ticks and playback against every recorded precise hash. This is not a claim of frozen Windows/macOS mixed-machine or launched-app disconnect/rejoin acceptance.

### Review-found regression

A natural minimap right-click incorrectly queued a destination from the ground-camera projection. `review-red/run.log` captures the expected failing command assertion; the minimal input guard now ignores ordinary minimap right-clicks. The regression passes in `review-final`. Initial strengthened-test runs also exposed two fixture mistakes (integer projection keys and incomplete fabricated queue schema); the final continuation test uses an actual paid build queue instead.

The initial independent 122-test run was green, but its all-source snapshot observed a concurrent parent version edit to `game/__init__.py`; this was not a tested-code write. Its user-data snapshot and audit remained clean. The final run was fully clean.

### Real-driver controls, pixels, and captures

The diagnostic was rerun inside the protected launcher at both sizes (`review-gl1024` and `review-gl1280`), using `--python-child tools/diag_collection_points.py --out <external-directory> --width ... --height ...`. Both safety reports succeeded with no source/user-data changes or audit violations.

| Capture | Marker-vs-disabled baseline changed pixels | Clear button | Action panel |
| --- | ---: | --- | --- |
| `review-captures/collection_point_1024x768.png` | 569 | [706,136,296,24] | [694,44,320,458] |
| `review-captures/collection_point_1280x800.png` | 582 | [962,136,296,24] | [950,44,320,458] |

Both measurements assert natural set/clear, unchanged precise simulation hash during drawing, clear-button containment and no overlapping action buttons. The diagnostic disables the marker draw for an in-process baseline; this is view-only instrumentation, not source mutation. Visual inspection of both resolutions finds a visible endpoint/link, readable coordinates and clear/refit/build controls without overlap or clipping. Long disabled production names have the existing row clipping behavior, not collection-control overlap.

### Existing source sabotage evidence (not rerun concurrently)

The earlier `sabotage/matrix.json` has ten CAUGHT rows: ownership, coordinates, newborn move, fighter refill, save projection, save migration, digest, set control, clear control and real-GL marker. The script saves source bytes before each mutation and asserts SHA-256 restoration in `finally`; the prior worker transcript records each restoration and final completion.

This review performed read-only backup/hash comparisons (`backup-hash-review.json`), not new source mutation. Command handling, construction, squadrons, state projection and save migration still exactly match their backups. Later differences were inspected: replay adds strict command-schema validation, input adds the minimap guard, and renderer contains the sibling worker's constructor/GL rollback work. They are not leftover sabotage. Do not restore those old backups over newer changes. Source mutation tests must remain exclusive of all other shared-tree test runs.

## Remaining integration gates

The parent owns language packs/tooling, release version/docs and the final protected full suite after all writers settle. The network worker owns `game/net/lan.py` and live recovery; the renderer worker owns `render/renderer.py`. This review changed neither owned file and found no additional station-specific patch required there. Full application recovery, native cross-platform behavior, and distribution acceptance remain separate gates.
