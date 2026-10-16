#!/usr/bin/env python3
"""Build the S01 rendered-model inventory and coverage matrix for STAR ARMADA.

Read-only over the repository: emits
  art/manifests/model_inventory.json          (merged deliverable, S01)
  art/manifests/reviews/S01-coverage-matrix.md (owner-facing review document)

Inputs
  assets/data/**.json                        (authoritative data rows)
  render/**, game/data/store.py              (real dispatch sites, imported and read)
  art/manifests/inventory_audit.json         (curated renderer-dispatch audit, S01)

Every ``file:symbol`` reference in the output is resolved against the tree the
script runs in: the line number is measured here, never transcribed. Two
behaviours follow from that:

* running the script at a different commit re-bases every reference to that
  commit, so the inventory cannot silently drift;
* a cited symbol that no longer exists aborts the build instead of emitting a
  plausible-looking stale reference.

The visual key per ship comes from the production function
``render.ship_sizes.ship_visual_key`` rather than a copy of its rules, so the
inventory reports the mesh the renderer actually selects.

Usage
    .venv/bin/python tools/art/build_model_inventory.py [--check]

``--check`` re-derives the inventory and compares it with the committed files
without writing (non-zero exit on drift).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "art" / "manifests" / "inventory_audit.json"
INVENTORY_PATH = ROOT / "art" / "manifests" / "model_inventory.json"
MATRIX_PATH = ROOT / "art" / "manifests" / "reviews" / "S01-coverage-matrix.md"

FACTIONS = ("imperial", "rebel", "confederacy", "syndicate")
FAMILY = {"rebel": "alliance", "confederacy": "legions", "syndicate": "syndicate"}
CONVOY_PREFIX = {"imperial": "imperial_", "rebel": "rebel_",
                 "confederacy": "confed_", "syndicate": "syndicate_"}
# ShipData.category -> inventory category (data vocabulary, not renderer vocabulary).
CATEGORY_OF = {
    "fighter_squadron": "squadron",
    "corvette": "combat_hull",
    "frigate": "combat_hull",
    "cruiser": "combat_hull",
    "battleship": "combat_hull",
    "supercapital": "combat_hull",
    "construction": "construction",
    "crew_transport": "logistics_hull",
}
STATION_CATEGORY = "station"
# Previews, VFX and attach points, stated per category from what the renderer actually
# draws. There is no socket/hardpoint registry in render/ (grep for socket/attach_point/
# muzzle finds prose comments only), and the only model-touching preview is the
# construction/placement ghost drawn by the renderer's outline passes.
PREVIEW_BY_CATEGORY = {
    "combat_hull": "no 3D preview or icon path; UI panels and the skirmish map preview are "
                   "2D, drawn from map data, not from the mesh. No socket/attach points: "
                   "engine trail/glow effects are drawn per entity, not bound to the model.",
    "squadron": "as combat_hull; squadron members are emitted per member from the same mesh",
    "logistics_hull": "as combat_hull",
    "construction": "as combat_hull for the colony/engineering hulls; the build-site scaffold "
                    "has no preview of its own (the queued station's ghost is shown instead)",
    "station": "construction and placement ghost only: the outline passes draw the full "
               "station-family mesh at the candidate position. No socket/attach points.",
    "satellite": "as station (outline ghost); orbit placement is computed, not socketed",
    "planet_installation": "as station (outline ghost); surface slots are chosen from the "
                           "surface frame, not from model sockets",
    "environment_prop": "not buildable: no preview, no sockets",
    "menu_cinematic": "not a gameplay entity: no preview, no sockets; it is a baked backdrop "
                      "played behind the menus",
}
SATELLITE_KINDS = ("defense_satellite", "attack_satellite")
PLANET_INSTALLATION_KINDS = ("planet_extractor", "planet_trade_hub",
                             "planet_shield_generator", "planet_pulsar_cannon")

# The authored trio approved by the owner. Binding -> runtime export.
APPROVED_TRIO = {
    "ship:rebel:battleship": "assets/models/alliance_battleship.mesh.json",
    "ship:rebel:frigate": "assets/models/alliance_frigate.mesh.json",
    "station:rebel:shipyard": "assets/models/alliance_shipyard.mesh.json",
}

# Renderer symbols resolved dynamically: logical name -> (module, symbol).
SYMBOLS = {
    "legacy_ship_facade": ("render/fleet_geometry.py", "ship_mesh"),
    "legacy_ship_builder": ("render/fleet_geometry.py", "_ship_mesh"),
    "faction_ship_facade": ("render/faction_ships.py", "ship_mesh"),
    "faction_ship_dispatch": ("render/faction_ships.py", "_ship_mesh"),
    "alliance_small": ("render/faction_ships.py", "_alliance_small"),
    "legions_small": ("render/faction_ships.py", "_legions_small"),
    "syndicate_small": ("render/faction_ships.py", "_syndicate_small"),
    "alliance_line": ("render/faction_ships.py", "_alliance_line"),
    "legions_line": ("render/faction_ships.py", "_legions_line"),
    "syndicate_line": ("render/faction_ships.py", "_syndicate_line"),
    "alliance_capital": ("render/faction_ships.py", "_alliance_capital"),
    "legions_capital": ("render/faction_ships.py", "_legions_capital"),
    "syndicate_capital": ("render/faction_ships.py", "_syndicate_capital"),
    "alliance_logistics": ("render/faction_ships.py", "_alliance_logistics"),
    "legions_logistics": ("render/faction_ships.py", "_legions_logistics"),
    "syndicate_logistics": ("render/faction_ships.py", "_syndicate_logistics"),
    "legacy_station_facade": ("render/fleet_geometry.py", "station_mesh"),
    "legacy_station_builder": ("render/fleet_geometry.py", "_station_mesh"),
    "satellite_builder": ("render/fleet_geometry.py", "_satellite_mesh"),
    "faction_station_facade": ("render/faction_stations.py", "station_mesh"),
    "faction_station_dispatch": ("render/faction_stations.py", "_station_mesh"),
    "alliance_station": ("render/faction_stations.py", "_alliance"),
    "legions_station": ("render/faction_stations.py", "_legions"),
    "syndicate_station": ("render/faction_stations.py", "_syndicate"),
    "legions_station_roles": ("render/faction_stations.py", "_legions_roles"),
    "syndicate_station_roles": ("render/faction_stations.py", "_syndicate_roles"),
    "building_facade": ("render/planet_building_geometry.py", "building_mesh"),
    "building_builder": ("render/planet_building_geometry.py", "_building_mesh"),
    "surface_frame": ("render/planet_building_geometry.py", "surface_frame"),
    "attached_contact_point": ("render/planet_building_geometry.py", "attached_contact_point"),
    "construction_sites": ("render/renderer.py", "_draw_construction_sites"),
    "planets": ("render/renderer.py", "_draw_planets"),
    "unit_sphere_list": ("render/renderer.py", "_build_textured_sphere_list"),
    "asteroid_field": ("render/renderer.py", "_draw_asteroid_field"),
    "rock_builder": ("render/renderer.py", "_draw_rock"),
    "rock_facets": ("render/renderer.py", "_rock_facets"),
    "nebulas": ("render/renderer.py", "_draw_nebulas"),
    "jump_points": ("render/renderer.py", "_draw_jump_points"),
    "star": ("render/renderer.py", "_draw_star"),
    "starfield": ("render/renderer.py", "_draw_starfield"),
    # Named in the audit as dead / single-caller code; resolved so the claim stays
    # checkable rather than becoming folklore.
    "emit_hull": ("render/renderer.py", "_emit_hull"),
    "station_ring": ("render/renderer.py", "_station_ring"),
    "draw_sphere": ("render/renderer.py", "_draw_sphere"),
    # The menu backdrop, decided in scope by the owner on 2026-10-16.
    "menu_movie_builder": ("tools/build_menu_movie.py", "build_movie"),
    "menu_splash_draw": ("render/menus.py", "_draw_splash_movie"),
    "menu_movie_frame": ("render/menu_movie.py", "get_frame"),
}

# Owner scope decisions, 2026-10-16 (art/manifests/inventory_audit.json:
# owner_scope_decisions). Only the elements that were actually asked carry a decision;
# the rest keep their proposal and are not presented as approved.
IN_SCOPE_DECISION = "in_scope_owner_approved (s01-scope-2026-10-16)"
KEEP_PROCEDURAL_PROPOSAL = "proposed_keep_procedural_not_asked"

# Ships whose mesh the faction builders do not own: every Imperial data id still
# resolves to the legacy inline shape builders.
ROLE_BUILDER = {
    ("rebel", "fighter"): "alliance_small",
    ("rebel", "bomber"): "alliance_small",
    ("rebel", "corvette"): "alliance_line",
    ("rebel", "frigate"): "alliance_line",
    ("rebel", "cruiser"): "alliance_line",
    ("rebel", "battleship"): "alliance_capital",
    ("rebel", "supercapital"): "alliance_capital",
    ("rebel", "constructor"): "alliance_logistics",
    ("rebel", "colonizer"): "alliance_logistics",
    ("rebel", "convoy"): "alliance_logistics",
    ("confederacy", "fighter"): "legions_small",
    ("confederacy", "bomber"): "legions_small",
    ("confederacy", "corvette"): "legions_line",
    ("confederacy", "frigate"): "legions_line",
    ("confederacy", "cruiser"): "legions_line",
    ("confederacy", "battleship"): "legions_capital",
    ("confederacy", "supercapital"): "legions_capital",
    ("confederacy", "constructor"): "legions_logistics",
    ("confederacy", "colonizer"): "legions_logistics",
    ("confederacy", "convoy"): "legions_logistics",
    ("syndicate", "fighter"): "syndicate_small",
    ("syndicate", "bomber"): "syndicate_small",
    ("syndicate", "corvette"): "syndicate_line",
    ("syndicate", "frigate"): "syndicate_line",
    ("syndicate", "cruiser"): "syndicate_line",
    ("syndicate", "battleship"): "syndicate_capital",
    ("syndicate", "supercapital"): "syndicate_capital",
    ("syndicate", "constructor"): "syndicate_logistics",
    ("syndicate", "colonizer"): "syndicate_logistics",
    ("syndicate", "convoy"): "syndicate_logistics",
}

STATION_BUILDER = {
    "imperial": ("legacy_station_builder", "legacy_station_facade"),
    "rebel": ("alliance_station", "faction_station_dispatch"),
    "confederacy": ("legions_station", "faction_station_dispatch"),
    "syndicate": ("syndicate_station", "faction_station_dispatch"),
}
# Factions that split their station builders again by kind.
STATION_ROLE_BUILDER = {
    "confederacy": "legions_station_roles",
    "syndicate": "syndicate_station_roles",
}
STATION_ROLE_EXEMPT = ("command_station", "shipyard")


def _line_cache(rel: str) -> list[str]:
    with open(ROOT / rel, encoding="utf-8") as fh:
        return fh.read().splitlines()


def symbol_line(rel: str, symbol: str) -> int:
    """Return the 1-based line of ``def symbol``/``class symbol`` in ``rel``."""
    pattern = re.compile(r"\s*(?:def|class)\s+" + re.escape(symbol) + r"\b")
    for index, line in enumerate(_line_cache(rel), 1):
        if pattern.match(line):
            return index
    raise LookupError(f"render symbol not found: {rel}:{symbol}")


def ref(symbol_key: str) -> str:
    rel, symbol = SYMBOLS[symbol_key]
    return f"{rel}:{symbol}:{symbol_line(rel, symbol)}"


def site(symbol_key: str) -> str:
    """``file:symbol:line`` for a symbol, so both reference columns have one shape.

    The dispatch site frequently is the emitting function itself; keeping the same
    three-part form for both columns means a consumer never has to guess how many fields
    to split off, and the published verification snippet can check every reference the
    same way.
    """
    return ref(symbol_key)


def load_json(rel: str):
    with open(ROOT / rel, encoding="utf-8") as fh:
        return json.load(fh)


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # pragma: no cover - inventory still useful without git
        return "unknown"


def code_base_check() -> collections.OrderedDict:
    """Report whether any code the row references name differs from ``origin/main``.

    The inventory is generated on a docs/tools branch, but its line references must be
    true for a reader of main. That holds only while the branch changes no renderer,
    gameplay or test file, so it is checked here instead of being asserted in prose.
    """
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args],
                              capture_output=True, text=True)

    base = git("merge-base", "HEAD", "origin/main")
    if base.returncode != 0:
        return collections.OrderedDict([
            ("checked", False),
            ("note", "origin/main is not available in this clone; code base not verified")])
    diff = git("diff", "--name-only", f"{base.stdout.strip()}...HEAD",
               "--", "render/", "game/", "tests/", "assets/")
    if diff.returncode != 0:
        return collections.OrderedDict([("checked", False),
                                         ("note", "git diff failed; code base not verified")])
    changed = [line for line in diff.stdout.splitlines() if line.strip()]
    return collections.OrderedDict([
        ("checked", True),
        ("merge_base", base.stdout.strip()),
        ("changed_code_paths", changed),
        ("note", ("no renderer, gameplay, test or asset file differs from main, so every line "
                  "reference in this inventory is valid for a reader of main"
                  if not changed else
                  "code differs from main — row references describe this branch, not main")),
    ])


def visual_keys():
    """Real production dispatch: data id -> mesh key, via render.ship_sizes."""
    sys.path.insert(0, str(ROOT))
    import game.core  # noqa: F401  (resolves the core/systems import cycle first)
    from game.data.store import DataStore
    from render.ship_sizes import SHIP_KEYS, ship_visual_key

    store = DataStore()
    return store, {sid: ship_visual_key(store, sid) for sid in sorted(store.ships)}, SHIP_KEYS


def ship_binding(faction: str, data_id: str) -> str:
    prefix = CONVOY_PREFIX[faction]
    return f"ship:{faction}:" + (data_id[len(prefix):] if data_id.startswith(prefix) else data_id)


def build_rows():
    store, keys, ship_keys = visual_keys()
    rows: list[collections.OrderedDict] = []
    by_key: dict[str, list[str]] = collections.defaultdict(list)

    # ---- crews the renderer mints without a ShipData row -------------------
    minted = [("imperial", "box"), ("rebel", "rebel:convoy"),
              ("confederacy", "confederacy:convoy"), ("syndicate", "syndicate:convoy")]
    all_keys = dict(keys)
    for faction, key in minted:
        all_keys[f"__convoy__{faction}"] = key
    for sid, key in all_keys.items():
        if sid.startswith("__convoy__"):
            by_key[key].append(f"ship:{sid.split('_', 2)[2]}:trade_convoy")
        else:
            by_key[key].append(ship_binding(store.ships[sid].faction, sid))

    def shared(binding: str, key: str) -> list[str]:
        return sorted(other for other in by_key[key] if other != binding)

    # ---- ships ------------------------------------------------------------
    for sid in sorted(store.ships):
        ship = store.ships[sid]
        faction, key = ship.faction, keys[sid]
        binding = ship_binding(faction, sid)
        role = key.split(":", 1)[1] if ":" in key else ""
        label = ship.display_name
        if faction == "imperial":
            generator = ref("legacy_ship_builder")
            dispatch = site("legacy_ship_facade")
            envelope = (f"ShipData.radius={ship.radius}; legacy shape {key!r} authored in model "
                        f"space at fixed extent (no scale policy applied)")
        else:
            generator = ref(ROLE_BUILDER[(faction, role)])
            dispatch = site("faction_ship_dispatch")
            envelope = (f"ShipData.radius={ship.radius}; drawn length via render/ship_sizes.py "
                        f"RATIOS[{ship.category}]={_ratio(ship.category)}")
        rows.append(row(
        binding=binding, label=label, faction=faction,
            category=CATEGORY_OF[ship.category],
            source=f"assets/data/ships/{faction}.json",
            generator=generator, dispatch=dispatch,
            shared=shared(binding, key), shape=key, envelope=envelope,
            status="procedural_legacy",
        ))

    # ---- trade convoys (minted by the trading system; no ShipData) --------
    for faction, key in minted:
        binding = f"ship:{faction}:trade_convoy"
        rows.append(row(
            binding=binding, label=None, faction=faction, category="logistics_hull",
            source=None,
            generator=ref("legacy_ship_builder") if faction == "imperial"
            else ref(ROLE_BUILDER[(faction, "convoy")]),
            dispatch=site("legacy_ship_facade") if faction == "imperial"
            else site("faction_ship_dispatch"),
            shared=shared(binding, key), shape=key,
            envelope=("minted by the trading system, no ShipData row; drawn length via "
                      "render/ship_sizes.py RATIOS[crew_transport]=0.8"),
            status="procedural_legacy",
        ))

    # ---- orbital stations -------------------------------------------------
    stations = load_json("assets/data/stations/stations.json")["stations"]
    # The station data file also holds the orbital satellite and planet-surface rows;
    # those are inventoried under their own categories, not as orbital stations.
    station_kinds = tuple(k for k in stations
                          if k not in SATELLITE_KINDS and k not in PLANET_INSTALLATION_KINDS)
    for faction in FACTIONS:
        for kind in station_kinds:
            binding = f"station:{faction}:{kind}"
            builder, dispatcher = STATION_BUILDER[faction]
            generator = ref(builder)
            if faction == "imperial":
                dispatch = site("legacy_station_facade")
            elif (faction in STATION_ROLE_BUILDER and kind not in STATION_ROLE_EXEMPT):
                generator = ref(STATION_ROLE_BUILDER[faction])
                dispatch = site("faction_station_dispatch")
            else:
                dispatch = site("faction_station_dispatch")
            rows.append(row(
                binding=binding, label=stations[kind].get("name"), faction=faction,
                category=STATION_CATEGORY, source="assets/data/stations/stations.json",
                generator=generator, dispatch=dispatch, shared=[], shape=kind,
                envelope=(f"StationData.radius={stations[kind].get('radius')}; station meshes are "
                          f"authored in a radius-50 material space and drawn at radius/50"),
                status="procedural_legacy",
            ))

    # ---- orbital satellites ----------------------------------------------
    for faction in FACTIONS:
        for kind in SATELLITE_KINDS:
            rows.append(row(
                binding=f"hardware:satellite:{faction}:{kind}",
                label=stations[kind].get("name"), faction=faction, category="satellite",
                source="assets/data/stations/stations.json",
                generator=ref("satellite_builder"), dispatch=site("legacy_station_builder"),
                shared=[], shape=kind,
                envelope=(f"StationData.radius={stations[kind].get('radius')}; orbit hardware, "
                          f"placed on the planet frame by "
                          f"{site('attached_contact_point')}"),
                status="procedural_legacy",
            ))

    # ---- planet surface installations ------------------------------------
    for faction in FACTIONS:
        for kind in PLANET_INSTALLATION_KINDS:
            rows.append(row(
                binding=f"hardware:construction:{faction}:{kind}",
                label=stations[kind].get("name"), faction=faction,
                category="planet_installation",
                source="assets/data/stations/stations.json",
                generator=ref("building_builder"), dispatch=site("building_facade"),
                shared=[], shape=kind,
                envelope=(f"placed on the surface slot frame from {site('surface_frame')}; "
                          f"footprint clamped to the planet radius"),
                status="procedural_legacy",
            ))

    # ---- construction-site scaffold --------------------------------------
    rows.append(row(
        binding="construction:site:scaffold", label=None, faction="shared",
        category="construction", source=None,
        generator=ref("construction_sites"), dispatch=ref("construction_sites"),
        shared=[], shape=None,
        envelope="drawn from the queued station's own radius and build progress; no data row",
        status="procedural_legacy",
    ))

    # ---- environment props (data-discovered, not hardcoded) ---------------
    kinds, maps_of = discover_environment_kinds()
    for kind in kinds:
        if kind == "asteroid_field":
            generator, dispatch = ref("rock_builder"), site("asteroid_field")
            envelope = (f"per-rock procedural facets from {ref('rock_facets')}, seeded per instance; "
                        f"rock size comes from the map's asteroid_field entry")
        elif kind == "gas_giant":
            generator, dispatch = ref("unit_sphere_list"), site("planets")
            envelope = "unit UV sphere display list scaled by the map's per-instance radius"
        else:
            generator, dispatch = ref("unit_sphere_list"), site("planets")
            envelope = "unit UV sphere display list scaled by the map's per-instance radius"
        mapped = ";".join(maps_of[kind])
        rows.append(row(
            binding=f"environment:{kind}", label=None, faction="shared",
            category="environment_prop", source=mapped or None,
            generator=generator, dispatch=dispatch, shared=[], shape=kind,
            envelope=envelope, status="in_scope_authoring_pending",
            scope=IN_SCOPE_DECISION,
        ))
    for binding, gen_key, site_key, shape, envelope in (
        ("environment:deep_space_sky_dome", "starfield", "starfield", "deep_space",
         "eye-centred sphere at a fixed large radius; never translates, so it carries no scale "
         "data"),
        ("environment:star", "star", "star", "star",
         "map JSON per-instance size"),
        ("environment:nebula", "nebulas", "nebulas", "nebula",
         "map JSON per-instance extent"),
        ("environment:jump_point", "jump_points", "jump_points", "jump_point",
         "map JSON per-instance placement and radius"),
    ):
        rows.append(row(
            binding=binding, label=None, faction="shared", category="environment_prop",
            source=None, generator=ref(gen_key), dispatch=site(site_key),
            shared=[], shape=shape, envelope=envelope,
            status="keep_procedural_proposed",
        ))

    # ---- menu cinematic backdrop (owner decided in scope 2026-10-16) ------
    rows.append(row(
        binding="menu:cinematic:backdrop", label=None, faction="shared",
        category="menu_cinematic", source=None,
        generator=ref("menu_movie_builder"), dispatch=site("menu_splash_draw"),
        shared=[], shape=None,
        envelope=("baked 3D battle backdrop for the non-replay menus; re-baked from the "
                  f"catalogue by {ref('menu_movie_builder')} and played back through "
                  f"{ref('menu_movie_frame')}"),
        status="in_scope_authoring_pending", scope=IN_SCOPE_DECISION,
    ))
    for entry in rows:
        if entry["canonical_binding"] == "menu:cinematic:backdrop":
            entry["notes"] = ("Owner decision s01-scope-2026-10-16: in scope. Whether the menu "
                              "scene is drawn live or stays baked per catalogue revision is an "
                              "S02/S04 implementation choice; the bake avoids paying battle "
                              "cost behind every menu.")

    # ---- approved trio: retarget the three owner-approved bindings --------
    for entry in rows:
        binding = entry["canonical_binding"]
        if binding in APPROVED_TRIO:
            entry["authored_override"] = APPROVED_TRIO[binding]
            entry["target_asset_id"] = APPROVED_TRIO[binding]
            entry["status"] = "approved_blender_draft_unmerged"
            entry["notes"] = ("Owner-approved Blender design preserved in draft PR #114; the "
                              "procedural generator above is still what main draws. Activation "
                              "is currently unconditional inside the draft, so the cutover must "
                              "stay behind an explicit preview gate before merge.")
    used_keys = {r["geometry_shape_string"] for r in rows
                 if r["canonical_binding"].startswith("ship:")}
    unreachable = [key for key in ship_keys if key not in used_keys]
    return rows, ship_keys, station_kinds, kinds, unreachable, store


def _ratio(category: str) -> float:
    from render.ship_sizes import RATIOS
    return RATIOS[_RATIO_KEY[category]]


_RATIO_KEY = {"fighter_squadron": "fighter_squadron", "corvette": "corvette",
              "frigate": "frigate", "cruiser": "cruiser", "battleship": "battleship",
              "supercapital": "supercapital", "construction": "construction",
              "crew_transport": "crew_transport"}


def discover_environment_kinds():
    """Union of planet/giant/field kinds across every map, so nothing is missed."""
    maps_of: dict[str, list[str]] = collections.defaultdict(list)
    maps_dir = ROOT / "assets" / "data" / "maps"
    for path in sorted(maps_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        present = set()
        for key in ("planets", "gas_giants"):
            for entry in data.get(key) or ():
                if isinstance(entry, dict) and entry.get("type"):
                    present.add(entry["type"])
        if data.get("asteroid_fields"):
            present.add("asteroid_field")
        for kind in present:
            maps_of[kind].append(f"assets/data/maps/{path.name}")
    return sorted(maps_of), maps_of


def check_campaign_coverage(store, rows):
    """Prove the campaign introduces no 3D model the inventory does not already hold.

    The roadmap asks for campaign-only objects explicitly. Counting them as zero is
    only meaningful if every model-shaped reference in the campaign file was resolved,
    so this walks the file and reports the unresolved ones rather than asserting a
    number nobody can check.
    """
    path = ROOT / "assets" / "data" / "campaign" / "campaign.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    tokens: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            tokens.add(node)

    walk(data)
    station_ids = {r["canonical_binding"].split(":")[-1] for r in rows
                   if r["category"] in ("station", "satellite", "planet_installation")}
    ship_refs = sorted(t for t in tokens if t in store.ships)
    station_refs = sorted(t for t in tokens if t in station_ids)
    unresolved = sorted(t for t in tokens
                        if re.fullmatch(r"(?:imperial|rebel|confed|syndicate)_[a-z_]+", t)
                        and t not in store.ships and t not in station_ids)
    return collections.OrderedDict([
        ("source", "assets/data/campaign/campaign.json"),
        ("missions", len(data.get("missions") or ())),
        ("referenced_ship_data_ids", ship_refs),
        ("referenced_station_ids", station_refs),
        ("unresolved_model_references", unresolved),
        ("campaign_only_models", 0 if not unresolved else len(unresolved)),
        ("conclusion", ("every ship and station the campaign references resolves to an "
                        "inventoried binding" if not unresolved
                        else "unresolved references — investigate before closing S01")),
    ])


def row(*, binding, label, faction, category, source, generator, dispatch, shared,
        shape, envelope, status, scope=KEEP_PROCEDURAL_PROPOSAL) -> collections.OrderedDict:
    return collections.OrderedDict([
        ("canonical_binding", binding),
        ("display_label", label),
        ("faction", faction),
        ("category", category),
        ("source_data_file", source),
        ("generator", generator),
        ("dispatch_site", dispatch),
        ("shared_source_with", shared),
        ("geometry_shape_string", shape),
        ("scale_envelope", envelope),
        ("status", status),
        ("scope_decision", scope),
        ("target_asset_id", None),
        ("authored_override", None),
        ("model_owner", "UNASSIGNED"),
        ("preview_vfx_sockets", PREVIEW_BY_CATEGORY[category]),
        ("notes", None),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="re-derive and compare against the committed files")
    args = parser.parse_args()

    audit = annotate_references(json.loads(AUDIT_PATH.read_text(encoding="utf-8")))
    (rows, ship_keys, station_kinds, env_kinds, unreachable_ship_keys,
     store) = build_rows()
    campaign = check_campaign_coverage(store, rows)
    code_base = code_base_check()

    counts = collections.OrderedDict([
        ("total_bindings", len(rows)),
        ("by_category", dict(sorted(collections.Counter(r["category"] for r in rows).items()))),
        ("by_faction", dict(sorted(collections.Counter(r["faction"] for r in rows).items()))),
        ("by_status", dict(sorted(collections.Counter(r["status"] for r in rows).items()))),
        ("ship_bindings", sum(1 for r in rows if r["canonical_binding"].startswith("ship:"))),
        ("distinct_ship_mesh_keys", len({r["geometry_shape_string"] for r in rows
                                         if r["canonical_binding"].startswith("ship:")})),
        ("distinct_ship_mesh_keys_from_data_rows",
         len({r["geometry_shape_string"] for r in rows
              if r["canonical_binding"].startswith("ship:")
              and not r["canonical_binding"].endswith(":trade_convoy")})),
        ("ship_keys_in_registry", len(ship_keys)),
        ("declared_ship_keys_without_a_data_row", unreachable_ship_keys),
        ("station_bindings", sum(1 for r in rows if r["category"] == "station")),
        ("station_kinds", len(station_kinds)),
        ("satellite_bindings", sum(1 for r in rows if r["category"] == "satellite")),
        ("planet_installation_bindings",
         sum(1 for r in rows if r["category"] == "planet_installation")),
        ("environment_prop_bindings",
         sum(1 for r in rows if r["category"] == "environment_prop")),
        ("menu_cinematic_bindings",
         sum(1 for r in rows if r["category"] == "menu_cinematic")),
        ("campaign_prop_bindings",
         sum(1 for r in rows if r["category"] == "campaign_prop")),
        ("campaign_only_models", campaign["campaign_only_models"]),
        ("bindings_in_scope_by_owner_decision",
         sum(1 for r in rows if r["scope_decision"].startswith("in_scope_owner_approved"))),
        ("dispatch_paths", len(audit["dispatch_paths"])),
        ("tooling_dispatch_paths", len(audit["tooling_dispatch_paths"])),
        ("non_model_elements", len(audit["non_model_elements"])),
        ("hidden_duplicate_risk_paths", len(audit["hidden_duplicate_risk_paths"])),
        ("scope_questions_asked_and_answered",
         len(audit["non_model_elements_needing_owner_decision"])),
        ("unresolved_items", len(audit["uncertain_or_unresolved"])),
    ])

    inventory = collections.OrderedDict([
        ("schema", "s01-model-inventory/v2"),
        ("roadmap_step", "S01"),
        # The base is the code base the rows were measured in, not this branch's HEAD:
        # recording the live HEAD would make --check fail on every later commit, and the
        # rows genuinely describe main's code while this branch changes none of it.
        ("base_commit", code_base.get("merge_base") or git_head()),
        ("base_branch", "main"),
        ("code_base", code_base),
        ("generated_by", "tools/art/build_model_inventory.py"),
        ("scope", ("Every 3D model the renderer can draw from data, plus every renderer dispatch "
                   "path that can supply geometry and every visual element that is not a discrete "
                   "model replacement. Environment props are included in the row set but carry "
                   "status 'unknown_needs_owner_scope_decision': they are inventoried so the "
                   "migration cannot silently omit them, not because they are in scope.")),
        ("owner_approved", {
            "decision": "approved-trio-2026-10-16",
            "bindings": sorted(APPROVED_TRIO),
            "preserved_in": "draft PR #114 (feat/blender-approved-trio-checkpoint)",
            "does_not_cover": [
                "any other hull, station, satellite or installation",
                "any other faction",
                "catalogue-wide rollout or a production default switch",
                "Windows or packaged-build acceptance",
            ],
        }),
        ("counts", counts),
        ("declared_ship_keys_without_a_data_row", unreachable_ship_keys),
        ("owner_scope_decisions", audit["owner_scope_decisions"]),
        ("planned_hulls", audit["planned_hulls"]),
        ("campaign_coverage", campaign),
        ("rows", rows),
        ("dispatch_paths", audit["dispatch_paths"]),
        ("tooling_dispatch_paths", audit["tooling_dispatch_paths"]),
        ("non_model_elements", audit["non_model_elements"]),
        ("non_model_elements_needing_owner_decision",
         audit["non_model_elements_needing_owner_decision"]),
        ("hidden_duplicate_risk_paths", audit["hidden_duplicate_risk_paths"]),
        ("reference_bases", audit["reference_base_note"]),
        ("hardcoded_trio_sites_draft_pr114", audit["hardcoded_trio_sites_draft_pr114"]),
        ("uncertain_or_unresolved", audit["uncertain_or_unresolved"]),
        ("grep_evidence", audit["grep_evidence"]),
        ("explicitly_out_of_model_scope_recorded",
         audit["explicitly_out_of_model_scope_recorded"]),
    ])
    payload = json.dumps(inventory, indent=1, ensure_ascii=False) + "\n"
    matrix = render_matrix(inventory, rows, station_kinds, env_kinds, audit)

    if args.check:
        drift = []
        for path, expected in ((INVENTORY_PATH, payload), (MATRIX_PATH, matrix)):
            actual = path.read_text(encoding="utf-8") if path.exists() else None
            if actual != expected:
                drift.append(path.name)
        if drift:
            print("DRIFT in: " + ", ".join(drift))
            return 1
        print("inventory and matrix are up to date")
        return 0

    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_PATH.write_text(payload, encoding="utf-8", newline="\n")
    MATRIX_PATH.write_text(matrix, encoding="utf-8", newline="\n")

    print(f"base_commit {inventory['base_commit']}")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    print(f"wrote {INVENTORY_PATH.relative_to(ROOT)} ({len(payload)} bytes)")
    print(f"wrote {MATRIX_PATH.relative_to(ROOT)} ({len(matrix)} bytes)")

    problems = []
    used = {r["geometry_shape_string"] for r in rows
            if r["canonical_binding"].startswith("ship:")}
    if not used <= set(ship_keys):
        problems.append("a ship binding resolves to a mesh key outside "
                        "render.ship_sizes.SHIP_KEYS")
    if any(r["generator"] is None or r["dispatch_site"] is None for r in rows):
        problems.append("a row is missing its generator or dispatch site")
    if not all(r["model_owner"] for r in rows):
        problems.append("a row is missing a model owner marker")
    if problems:
        for problem in problems:
            print("FAIL:", problem)
        return 1
    print("invariants ok")
    return 0


def render_matrix(inventory, rows, stations, env_kinds, audit) -> str:
    counts = inventory["counts"]
    base = inventory["base_commit"]
    out: list[str] = []
    add = out.append

    add("# S01 — rendered-model inventory and coverage matrix\n")
    add(f"Base: `{base}` (`main`), roadmap step **S01**. "
        f"Regenerate with `.venv/bin/python tools/art/build_model_inventory.py`; "
        f"`--check` fails on drift.\n")
    add("This document is generated from the tree, not transcribed. Every line reference "
        "below is measured by resolving the named symbol at the base commit, so a moved "
        "function re-bases instead of silently pointing at the wrong code. "
        "`art/manifests/model_inventory.json` is the machine-readable form of the same data.\n")
    add("What is measured here and what is merely reproduced: every `generator` and "
        "`dispatch_site` in the row tables is resolved to a real `def` at the base commit, "
        "and each dispatch path records whether the symbols it names exist in this tree. The "
        "audit was taken on the checkpoint tree, so the line ranges quoted inside its prose "
        "are reproduced, not re-measured — each row states whether that range still fits "
        "inside the file here, and a row whose symbols are absent from this tree is listed "
        "separately in section 5.1 instead of being blended into the live paths.\n")
    add(f"Code base: {inventory['code_base']['note']}.\n")

    add("## 1. What this covers\n")
    add("| item | count |")
    add("|---|---|")
    for key, value in counts.items():
        if not isinstance(value, int):
            continue
        add(f"| {key} | {value} |")
    add("")
    add("Coverage comes from the data, not from a hand-written list: ships are enumerated "
        "from `game.data.store.DataStore().ships`, stations and hardware from "
        "`assets/data/stations/stations.json`, and environment props from the union of planet "
        "kinds across every file in `assets/data/maps/`, so a new map kind appears here "
        "automatically.\n")

    add("## 2. Ships — bindings and the mesh the renderer actually selects\n")
    add("| binding | label | category | mesh key | shared with | generator |")
    add("|---|---|---|---|---|---|")
    for entry in rows:
        if not entry["canonical_binding"].startswith("ship:"):
            continue
        add(f"| `{entry['canonical_binding']}` | {entry['display_label'] or '—'} | "
            f"{entry['category']} | `{entry['geometry_shape_string']}` | "
            f"{len(entry['shared_source_with'])} | `{entry['generator']}` |")
    add("")
    add(f"{counts['ship_bindings']} bindings resolve to "
        f"{counts['distinct_ship_mesh_keys']} distinct meshes, and every one of those keys is "
        f"declared in `render.ship_sizes.SHIP_KEYS` ({counts['ship_keys_in_registry']} keys). "
        "That containment is the coverage proof for hulls: no hull can reach the renderer "
        "without landing on an inventoried key.\n")
    unreachable = inventory["declared_ship_keys_without_a_data_row"]
    if unreachable:
        add(f"### 2.1 Declared but unreachable\n")
        add("`SHIP_KEYS` also declares keys that no current data row can select. They are "
            "reported rather than deleted, because the question is whether the slot is "
            "planned or dead:\n")
        for key in unreachable:
            add(f"- `{key}`")
        add("")
        add("**Owner decision 2026-10-16: keep them and plan the hulls.** Battleships and "
            "capital ships build at the shipyard; bombers build at the fighter platform. "
            "`shipyard.builds_ships` is `['*']`, so capital production there already holds; "
            "`fighter_platform.builds_ships` is an explicit list, so a new bomber hull stays "
            "unbuildable until its data id is added to it — a data change to make alongside "
            "the hull, not a model change.\n")

    add("## 3. Stations, satellites and planet installations\n")
    add("| binding pattern | label | category | generator | dispatch |")
    add("|---|---|---|---|---|")
    seen = set()
    for entry in rows:
        if entry["category"] not in ("station", "satellite", "planet_installation"):
            continue
        pattern = re.sub(r":(imperial|rebel|confederacy|syndicate):",
                         ":{faction}:", entry["canonical_binding"])
        key = (pattern, entry["generator"], entry["dispatch_site"])
        if key in seen:
            continue
        seen.add(key)
        add(f"| `{pattern}` | {entry['display_label'] or '—'} | {entry['category']} | "
            f"`{entry['generator']}` | `{entry['dispatch_site']}` |")
    add("")
    add(f"{counts['station_kinds']} station kinds in data, drawn as "
        f"{counts['station_bindings']} faction bindings; "
        f"{counts['satellite_bindings']} satellite bindings and "
        f"{counts['planet_installation_bindings']} planet-installation bindings reuse the same "
        "data rows through their own builders.\n")

    add("## 4. Environment and shared props\n")
    add("| binding | generator | dispatch |")
    add("|---|---|---|")
    for entry in rows:
        if entry["category"] != "environment_prop":
            continue
        add(f"| `{entry['canonical_binding']}` | `{entry['generator']}` | "
            f"`{entry['dispatch_site']}` |")
    add("")
    add(f"Kinds discovered in the maps: {', '.join('`%s`' % k for k in env_kinds)}. "
        "**Owner decision 2026-10-16: the planet bodies and the asteroid field are in scope** "
        "and carry `in_scope_authoring_pending`; they are authoring targets in batch B5. The "
        "sky dome, star, nebula and jump point were proposed `keep procedural` and were not "
        "among the questions asked, so they stay recorded as proposals.\n")

    add("## 5. Renderer dispatch paths\n")
    add("Every path through which the renderer obtains 3D geometry. The last column is measured "
        "here: it says whether the symbols named in the row exist in this tree at the base "
        "commit, so an unmerged path cannot pass for a live one.\n")
    live = [e for e in audit["dispatch_paths"] if e["reference_base"] == "verified_in_this_tree"]
    draft = [e for e in audit["dispatch_paths"] if e["reference_base"] != "verified_in_this_tree"]
    add(f"| id | module:symbol | line reference | line range vs this file | emits | source call |")
    add("|---|---|---|---|---|---|")
    for entry in live:
        add(f"| `{entry['path_id']}` | `{_one_line(entry['module_and_symbol'], 120)}` | "
            f"{_one_line(entry.get('line_reference'), 40)} | "
            f"{entry['line_reference_base']} | "
            f"{_one_line(entry.get('what_it_emits'))} | "
            f"`{_one_line(entry.get('geometry_source_call'))}` |")
    add("")
    if draft:
        add(f"### 5.1 Paths that exist only on the checkpoint branch\n")
        add("These rows describe code in the unmerged trio checkpoint, not in this tree; "
            "the absent symbols are listed so the row is self-checking.\n")
        add("| id | module:symbol | absent here | emits |")
        add("|---|---|---|---|")
        for entry in draft:
            add(f"| `{entry['path_id']}` | `{_one_line(entry['module_and_symbol'], 120)}` | "
                f"`{_one_line(', '.join(entry['symbols_absent_from_this_tree']), 120)}` | "
                f"{_one_line(entry.get('what_it_emits'))} |")
        add("")
    add(f"Tool-only paths ({len(audit['tooling_dispatch_paths'])}), which cannot affect the "
        "shipped renderer:\n")
    for entry in audit["tooling_dispatch_paths"]:
        add(f"- `{entry.get('path_id')}` — `{entry.get('module_and_symbol')} "
            f"{entry.get('line_reference','')}` — {_one_line(entry.get('what_it_emits'))}")
    add("")

    add("## 6. Paths that can hide a second copy of a model\n")
    for entry in audit["hidden_duplicate_risk_paths"]:
        add(_bullet(entry))
    add("")

    add("## 7. Not model replacements — owner scope decisions\n")
    add("| id | element | proposed decision |")
    add("|---|---|---|")
    for entry in audit["non_model_elements"]:
        add(f"| `{entry['element_id']}` | {_one_line(entry.get('what_it_is'))} | "
            f"{_one_line(entry.get('proposed_scope_decision'))} |")
    add("")
    add("### 7.1 Resolved by the owner, 2026-10-16\n")
    add("| element | owner decision, 2026-10-16 |")
    add("|---|---|")
    for entry in audit["non_model_elements_needing_owner_decision"]:
        text = entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)
        text = text.lstrip("-— ")
        element = text.split(" ")[0].rstrip("-—")
        add(f"| {_one_line(element, 60)} | in scope — bring into the catalogue "
            f"(`{_one_line(_one_line(text).split(' ', 1)[-1], 140)}`) |")
    add("")
    add("The elements listed in section 7 above that are **not** in section 7.1 keep their "
        "`keep procedural` proposal. They were not put to the owner, so they are carried as "
        "proposals rather than presented as approved; say so if any of them should change.\n")

    add("## 8. Approved scope and its limits\n")
    add(f"Owner decision `{inventory['owner_approved']['decision']}`; preserved in "
        f"{inventory['owner_approved']['preserved_in']}.\n")
    add("| binding | status | runtime asset | generator in this tree |")
    add("|---|---|---|---|")
    for entry in rows:
        if entry["status"] == "approved_blender_draft_unmerged":
            add(f"| `{entry['canonical_binding']}` | {entry['status']} | "
                f"`{entry['target_asset_id']}` | `{entry['generator']}` |")
    add("")
    add("Approval does **not** cover:")
    for item in inventory["owner_approved"]["does_not_cover"]:
        add(f"- {item}")
    add("")
    add("The three approved bindings still draw the procedural generator above in this tree; "
        "their authored overrides live only in the draft checkpoint.\n")

    add("## 9. Proposed review batches\n")
    add("Ordered so that each batch settles a question before the next one spends effort on "
        "it; counts are current bindings. **Owner decision 2026-10-16: approved in this "
        "order** (`s01-batch-plan`), as a plan and as scope — not as approval of any model "
        "design, which S06 still requires per asset with an enumerated list.\n")
    add("| batch | contents | bindings | question the owner answers |")
    add("|---|---|---|---|")
    add(f"| B1 | combat hulls, one faction (`rebel`) | "
        f"{sum(1 for r in rows if r['category'] in ('combat_hull', 'squadron') and r['faction'] == 'rebel')} | "
        "does the approved battleship/frigate treatment extend to the rest of the fleet? |")
    add(f"| B2 | squadrons and logistics hulls, all factions | "
        f"{sum(1 for r in rows if r['category'] in ('squadron', 'logistics_hull'))} | "
        "are squadron members and transports authored individually or as shared props? |")
    add(f"| B3 | stations, by faction | {counts['station_bindings']} | "
        "does the approved shipyard treatment extend to the other station kinds? |")
    add(f"| B4 | satellites and planet installations | "
        f"{counts['satellite_bindings'] + counts['planet_installation_bindings']} | "
        "orbit/surface hardware in scope at all? |")
    add(f"| B5 | environment props | {counts['environment_prop_bindings']} | "
        "in scope per the owner decision: planet bodies and the asteroid field are authored "
        "here; the sky/star/nebula/jump-point proposals still stand unless objected to |")
    add("")
    add("## 10. Open items\n")
    for entry in audit["uncertain_or_unresolved"]:
        add(_bullet(entry))
    add("")
    add("### 10.1 Counted evidence behind the audit\n")
    add("| command | raw count | note |")
    add("|---|---|---|")
    for entry in audit["grep_evidence"]:
        add(f"| `{_one_line(entry['cmd'], 160)}` | {entry['raw_count']} | "
            f"{_one_line(entry.get('note'), 120)} |")
    add("")
    add("## 11. Verification commands\n")
    add("```")
    add("# inventory regeneration is stable (second run must not change the files)")
    add(".venv/bin/python tools/art/build_model_inventory.py")
    add(".venv/bin/python tools/art/build_model_inventory.py --check")
    add("")
    add("# every cited symbol still exists at the base")
    add("python3 - <<'PY'")
    add("import json,re,pathlib")
    add("root=pathlib.Path('.')")
    add("inv=json.loads((root/'art/manifests/model_inventory.json').read_text())")
    add("for r in inv['rows']:")
    add("    for f in (r['generator'], r['dispatch_site']):")
    add("        p,sym,ln=f.rsplit(':',2); L=(root/p).read_text().splitlines()")
    add("        assert re.match(r'\\s*(def|class) '+re.escape(sym)+r'\\B', L[int(ln)-1]), f")
    add("print('all row references resolve')")
    add("PY")
    add("```")
    add("")

    add("## 12. Owner decisions recorded\n")
    decisions = inventory["owner_scope_decisions"]
    add(f"`{decisions['decision_id']}`, decided by {decisions['decided_by']}, bound to commit "
        f"`{decisions['binds_to']['reviewed_revision_commit']}` "
        f"(PR #{decisions['binds_to']['pr']}) and this document.\n")
    add("| question | answer | owner's own wording |")
    add("|---|---|---|")
    for answer in decisions["answers"]:
        add(f"| `{answer['question_id']}` | {_one_line(answer['answer'], 200)} | "
            f"“{_one_line(answer.get('raw_owner_wording'), 120)}” |")
    add("")
    add("What this does not authorize:")
    for item in ("merging PR #114 or activating the trio in production",
                 "changing the production default (that is S11, and only after S10)",
                 "any specific model design — S06 requires per-asset owner approval with an "
                 "enumerated list"):
        add(f"- {item}")
    add("")
    add("Consequences carried into the inventory:")
    for item in decisions["consequences"]:
        add(f"- {item}")
    add("")
    add("### 12.1 Planned hulls\n")
    hulls = inventory["planned_hulls"]
    add(f"{hulls['owner_rule']} Mechanism: {_one_line(hulls['grounding']['mechanism'])}\n")
    add("| mesh key | data row today | production site | status |")
    add("|---|---|---|---|")
    for hull in hulls["hulls"]:
        add(f"| `{hull['mesh_key']}` | {hull['data_row_today'] or 'none'} | "
            f"`{hull['production_site']}` | {hull['status']} |")
    add("")
    add(f"`fighter_platform.builds_ships` today: "
        f"{', '.join('`%s`' % s for s in hulls['grounding']['fighter_platform.builds_ships'])}. "
        f"{hulls['grounding']['fighter_platform_consequence']}\n")

    add("## 13. Campaign coverage\n")
    campaign = inventory["campaign_coverage"]
    add(f"Read from {campaign['source']}: {campaign['missions']} missions, "
        f"{len(campaign['referenced_ship_data_ids'])} distinct ship data ids and "
        f"{len(campaign['referenced_station_ids'])} station ids referenced; "
        f"**{campaign['campaign_only_models']} campaign-only models**.\n")
    add(f"- {campaign['conclusion']}")
    add(f"- ship ids referenced: "
        f"{', '.join('`%s`' % s for s in campaign['referenced_ship_data_ids'])}")
    add(f"- station ids referenced: "
        f"{', '.join('`%s`' % s for s in campaign['referenced_station_ids'])}")
    add(f"- unresolved model-shaped references: "
        f"{campaign['unresolved_model_references'] or 'none'}")
    add("")
    add("`campaign_prop` is therefore empty because the campaign reuses existing bindings, "
        "not because campaign content was skipped.\n")
    return "\n".join(out)


def annotate_references(audit):
    """Record, per audit row, which cited symbols this tree can actually resolve.

    The audit mixes two reference bases: code in this tree and code that only exists
    on the unmerged checkpoint branch. Rather than trust a prose caveat, resolve every
    ``file`` / ``file:symbol`` token here and let the unresolved ones be labelled in the
    output, so a trio-only path can never be mistaken for a live one.
    """
    token = re.compile(r"([\w/]+\.py)(?::([\w\.]+))?")
    for section in ("dispatch_paths", "tooling_dispatch_paths"):
        for entry in audit[section]:
            resolved, unresolved = [], []
            for rel, symbol in token.findall(entry.get("module_and_symbol", "")):
                if not (ROOT / rel).exists():
                    unresolved.append(f"{rel} (file absent)")
                    continue
                if not symbol:
                    resolved.append(rel)
                    continue
                if symbol_defined(rel, symbol):
                    resolved.append(f"{rel}:{symbol}")
                else:
                    unresolved.append(f"{rel}:{symbol}")
            entry["symbols_resolved_in_this_tree"] = resolved
            entry["symbols_absent_from_this_tree"] = unresolved
            entry["reference_base"] = ("partly_draft_PR_114" if unresolved
                                       else "verified_in_this_tree")
            entry["line_reference_base"] = check_line_reference(entry)
    return audit


def check_line_reference(entry) -> str:
    """Classify the row's quoted line ranges against the files they name.

    The audit was taken on the checkpoint tree, so a range can be valid there and past
    the end of the file here. The row cannot claim more than this check proves: the
    symbols are resolved above, and the ranges are only bounded by the file length.
    """
    module = entry.get("module_and_symbol", "")
    quote = entry.get("line_reference", "") or ""
    match = re.search(r"([\w/]+\.py)", module)
    if not match or not (ROOT / match.group(1)).exists():
        return "not_checked"
    lines = _line_cache(match.group(1))
    numbers = [int(n) for n in re.findall(r"L(\d+)", quote)]
    numbers += [int(n) for n in re.findall(r"\.py:(\d+)", quote)]
    if not numbers:
        return "no_line_number_quoted"
    return ("within_file_at_this_base" if max(numbers) <= len(lines)
            else "range_extends_past_end_of_file_at_this_base")


def symbol_defined(rel: str, symbol: str) -> bool:
    pattern = re.compile(r"\s*(?:def|class)\s+" + re.escape(symbol) + r"\b")
    return any(pattern.match(line) for line in _line_cache(rel))


def _one_line(value, limit: int = 220) -> str:
    if not value:
        return "—"
    text = " ".join(str(value).split())
    text = text.replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _bullet(entry, limit: int = 600) -> str:
    """Render an audit entry as a bullet, whether it is a string or a mapping."""
    if isinstance(entry, dict):
        parts = []
        for key, value in entry.items():
            parts.append(f"{key}: {_one_line(value, 240)}")
        return "- " + _one_line(" — ".join(parts), limit)
    return "- " + _one_line(entry, limit)


if __name__ == "__main__":
    raise SystemExit(main())
