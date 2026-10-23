# Rim Syndicate fleet rework — the 23 pre-existing bindings

Every Rim Syndicate binding that still drew legacy geometry now draws an authored mesh in the
same industrial language as the Marauder battleship, Leviathan dreadnought and Cutthroat strike
wing merged earlier. This is a **core catalogue** change: launch `main.py` and it is there. There
is no visual pack to enable, no profile setting and no helper script involved.

## What changed

| Family | Bindings |
| --- | --- |
| Combat hulls | `corvette`, `frigate`, `cruiser`, `fighter` (Jackal) |
| Support hulls | `convoy`, `colonizer`, `constructor` |
| Stations | `command_station`, `defense_platform`, `energy_relay`, `fighter_platform`, `mining_station`, `repair_dock`, `research_station`, `sensor_station`, `shipyard`, `trade_station` |
| Satellites | `attack_satellite`, `defense_satellite` |
| Planet installations | `planet_extractor`, `planet_pulsar_cannon`, `planet_shield_generator`, `planet_trade_hub` |

Each one is a Blender master in `art/blender/syndicate_fleet/<stem>.blend`, a runtime mesh in
`assets/models/syndicate_<stem>.mesh.json`, and an updated manifest in
`assets/models/manifests/`. All six runtime material roles (`base`, `dark`, `trim`, `accent`,
`lit`, `cool`) are present on every asset, so lit windows, drive throats and cool emitters behave
like the rest of the catalogue.

The new hulls read at a glance as Syndicate: welded barge lofts, ochre ownership bands, port
armour sponson against a starboard welded outrigger boom with its counterweight drum, external
reactor drums in cradles, casemate turret collars, blunt salvage ram, annular drive throats.
Stations are a trussed wheel — spine, hub drum, docking hoop, spokes and ribs — with one legible
working kit (cranes, tanks, dishes, gantries) rather than generic clutter.

## What did **not** change

- **Length, framing and collision radii.** Every mesh is *contained* inside the envelope its
  binding was already approved at; nothing is scaled up to fill a padded box. `E_EXTENT_DRIFT`
  would reject it otherwise. Verified across all 23 in `tests/test_syndicate_fleet_rework.py`.
- **Gameplay data.** No cost, speed, damage, hit point or build-tree row moved. The bindings
  resolve to the same identities with the same envelopes.
- **The three hulls from the previous batch.** Their sources, manifests and revisions are
  byte-identical; the geometry module only gained optional parameters.

## Approval state

Nothing here claims the owner's approval. All 23 manifests carry
`approval.status = "pending"` with the review evidence paths, and
`art/manifests/pipeline.json → review_batches.syndicate-fleet-rework` records the batch as
`owner_review_pending`. The decision that approved each *envelope* is still the one named in
`approval.decision_id` — untouched, because the envelopes did not move.

After the owner runs the game and says yes, `python3 tools/art/register_syndicate_fleet.py
--approve` writes the decision, the accepted status and the loader-verified receipts.

## Evidence

`artifacts/syndicate-fleet/review/<stem>-{quarter,profile,bow}.jpg` — 69 Blender stills, three
angles per binding, the same files the manifests list as review evidence.

`artifacts/syndicate-fleet/captures/` — in-engine captures of the rework drawn by the game's own
fleet factory (fleet line-up, hulls, stations, a close pass on the cruiser).

## Rebuilding

    /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/art/build_syndicate_fleet.py \
        -- --replace-own [--only cruiser] [--render art/.../stills]
    python3 tools/art/register_syndicate_fleet.py

`tools/art/syndicate_fleet_designs.py` holds the design vocabulary, `tools/art/build_syndicate_fleet.py`
the batch driver (it refuses to overwrite an accepted master without `--replace-own`), and
`register_syndicate_fleet.py` the catalogue registration.
