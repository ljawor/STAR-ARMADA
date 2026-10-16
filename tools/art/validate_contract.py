#!/usr/bin/env python3
"""Validate the S02 extension contract and everything that claims to obey it.

This is the executable half of ``docs/ASSET_EXTENSION_CONTRACT.md``. It checks three
things and refuses to guess about any of them:

1. **Structure** — every example is checked against ``art/schemas/*.schema.json`` by a
   small, explicit JSON-Schema subset evaluator (``type``, ``required``,
   ``additionalProperties``, ``properties``, ``items``, ``enum``, ``const``,
   ``pattern``, ``minItems``, ``maxItems``, ``uniqueItems``, ``minProperties``,
   ``minimum``, ``maximum``, ``exclusiveMinimum``, ``$ref`` to ``#/$defs/...``).
   The subset is documented rather than assumed: a keyword outside it is a hard error,
   so a schema can never be silently half-enforced. ``jsonschema`` is not a dependency of
   this project, and this tool does not add one.
2. **Semantics** — the invariants a schema cannot express: recomputed asset revision,
   pinned file hash/size/existence, path safety including symlink escape, duplicate
   bindings and duplicate pack entries, degenerate envelopes, a pack that adds a binding
   core already defines, an additive pack with no gameplay mod behind it, unknown
   contract ids, an approval whose evidence is gone.
3. **Negative controls** — ``art/schemas/examples/invalid/`` holds documents that must
   be *rejected*, and ``EXPECTED.json`` names the error code each one must produce. A
   validator that only ever sees valid input proves nothing, so every rejection rule has
   a fixture and a runtime-generated symlink-escape case.

Exit code is 0 only when every valid example passes, every invalid fixture fails with the
code it declares, and no example is silently skipped.

Usage:
    python3 tools/art/validate_contract.py [--json]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "art" / "schemas"
EXAMPLES = SCHEMAS / "examples"
INVALID = EXAMPLES / "invalid"

SUPPORTED_KEYWORDS = {
    "type", "required", "additionalProperties", "properties", "items", "enum", "const",
    "pattern", "minItems", "maxItems", "uniqueItems", "minProperties", "minimum",
    "maximum", "exclusiveMinimum", "minLength", "maxLength", "$ref", "$defs", "$schema",
    "$id", "title", "description", "format",
}

# contract id -> (major versions this project understands, schema file)
CONTRACTS = {
    "star-armada/model-manifest": (1, "model-manifest.schema.json"),
    "star-armada/binding-registry": (1, "binding-registry.schema.json"),
    "star-armada/visual-pack": (1, "visual-pack.schema.json"),
}

PATH_FIELDS = ("path", "source")
PACK_PATH_FIELDS = ("manifest",)
# The section 9 extent grace: see extent_grace().
EXTENT_GRACE_UNITS = 2.0

MAX_FILE_BYTES = 67108864


class Rejected(Exception):
    """The first error found, carrying the code the fixture must declare."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Document:
    """Loads a JSON document strictly, so NaN/Infinity cannot sneak past json.loads."""

    def __init__(self, path: Path, root: Path):
        self.path = path
        self.root = root
        try:
            self.text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise Rejected("E_PARSE", f"cannot read {path}: {exc}") from exc
        try:
            self.data = json.loads(self.text, parse_constant=self._reject_constant)
        except Rejected:
            raise
        except Exception as exc:  # noqa: BLE001 - any parse failure is the same rejection
            raise Rejected("E_PARSE", f"not valid JSON: {exc}") from exc
        if not isinstance(self.data, dict):
            raise Rejected("E_SCHEMA", "top level must be an object")

    @staticmethod
    def _reject_constant(name: str):
        # json.loads accepts NaN/Infinity by default; a mesh with NaN vertices must not
        raise Rejected("E_NON_FINITE", f"non-finite number literal '{name}' is not allowed")


# --------------------------------------------------------------------------- structure

def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def _fail(code: str, where: str, why: str):
    raise Rejected(code, f"{where}: {why}")


def check_schema(node, schema: dict, where: str, root_schema: dict) -> None:
    """Evaluate the documented subset. Raises Rejected('E_SCHEMA', ...) on violation."""
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            _fail("E_SCHEMA", where, f"unsupported $ref '{ref}'")
        schema = root_schema["$defs"][ref.split("/")[-1]]

    for keyword in schema:
        if keyword not in SUPPORTED_KEYWORDS:
            _fail("E_SCHEMA", where, f"schema uses unsupported keyword '{keyword}'")

    if "const" in schema and node != schema["const"]:
        _fail("E_SCHEMA", where, f"must equal {schema['const']!r}, got {node!r}")
    if "enum" in schema and node not in schema["enum"]:
        _fail("E_SCHEMA", where, f"{node!r} is not one of {schema['enum']}")

    types = schema.get("type")
    if types:
        types = [types] if isinstance(types, str) else list(types)
        actual = ("integer" if isinstance(node, int) and not isinstance(node, bool)
                  else "number" if isinstance(node, (int, float)) and not isinstance(node, bool)
                  else "boolean" if isinstance(node, bool)
                  else "null" if node is None
                  else "array" if isinstance(node, list)
                  else "object" if isinstance(node, dict)
                  else "string")
        ok = actual in types or (actual == "integer" and "number" in types)
        if not ok:
            _fail("E_SCHEMA", where, f"expected {types}, got {actual}")

    if isinstance(node, str):
        if "minLength" in schema and len(node) < schema["minLength"]:
            _fail("E_SCHEMA", where, f"shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(node) > schema["maxLength"]:
            _fail("E_SCHEMA", where, f"longer than maxLength {schema['maxLength']}")
    if isinstance(node, str) and "pattern" in schema:
        # Patterns in these schemas are anchored; the span check is what makes that true
        # even if a later edit forgets a '^' or '$'.
        match = re.search(schema["pattern"], node)
        if match is None or match.group(0) != node:
            _fail("E_SCHEMA", where, f"{node!r} does not match {schema['pattern']}")

    if isinstance(node, (int, float)) and not isinstance(node, bool):
        if "minimum" in schema and node < schema["minimum"]:
            _fail("E_SCHEMA", where, f"{node} < minimum {schema['minimum']}")
        if "maximum" in schema and node > schema["maximum"]:
            _fail("E_SCHEMA", where, f"{node} > maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and node <= schema["exclusiveMinimum"]:
            _fail("E_SCHEMA", where, f"{node} <= exclusiveMinimum {schema['exclusiveMinimum']}")

    if isinstance(node, list):
        if "minItems" in schema and len(node) < schema["minItems"]:
            _fail("E_SCHEMA", where, f"needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(node) > schema["maxItems"]:
            _fail("E_SCHEMA", where, f"allows at most {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            seen = [json.dumps(item, sort_keys=True) for item in node]
            if len(set(seen)) != len(seen):
                _fail("E_SCHEMA", where, "items must be unique")
        if "items" in schema:
            for i, item in enumerate(node):
                check_schema(item, schema["items"], f"{where}[{i}]", root_schema)

    if isinstance(node, dict):
        for key in schema.get("required", []):
            if key not in node:
                _fail("E_SCHEMA", where, f"missing required '{key}'")
        if "minProperties" in schema and len(node) < schema["minProperties"]:
            _fail("E_SCHEMA", where, f"needs at least {schema['minProperties']} keys")
        for key, value in node.items():
            if key in schema.get("properties", {}):
                check_schema(value, schema["properties"][key], f"{where}.{key}", root_schema)
            elif schema.get("additionalProperties") is False:
                _fail("E_SCHEMA", where, f"unexpected key '{key}'")


# --------------------------------------------------------------------------- semantics

def iter_paths(node, where="", fields=PATH_FIELDS) -> list[tuple[str, str]]:
    """Every string held in a path-like field, with a label for the error message."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in fields and isinstance(value, str):
                found.append((f"{where}.{key}".lstrip("."), value))
            else:
                found.extend(iter_paths(value, f"{where}.{key}".lstrip("."), fields))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(iter_paths(value, f"{where}[{i}]", fields))
    return found


def check_path_safety(doc: Document) -> None:
    # A registry's `manifest` holds an asset id, not a path, so it is checked here only
    # inside a pack, where it does name a file.
    fields = PATH_FIELDS
    if doc.data.get("contract") == "star-armada/visual-pack":
        fields = PATH_FIELDS + PACK_PATH_FIELDS
    for where, value in iter_paths(doc.data, fields=fields):
        if value.startswith("/") or "\\" in value or ":" in value:
            raise Rejected("E_UNSAFE_PATH", f"{where}: '{value}' is absolute or non-relative")
        if any(part in ("..", "") for part in value.split("/")):
            raise Rejected("E_UNSAFE_PATH", f"{where}: '{value}' escapes the root")
        resolved = (doc.root / value)
        real_root = os.path.realpath(doc.root)
        real = os.path.realpath(resolved)
        if real != real_root and not real.startswith(real_root + os.sep):
            raise Rejected("E_SYMLINK_ESCAPE", f"{where}: '{value}' resolves outside the root")
        # A path that does not exist yet is legal at this stage (a pack names files it
        # ships); existence is enforced where the contract requires it.


def recompute_revision(asset: str, files: dict) -> str:
    body = "\n".join(f"{lod}:{files[lod]['sha256']}" for lod in sorted(files))
    return hashlib.sha256(f"{asset}\n{body}".encode()).hexdigest()


EXPORT_KEYS = ("vertices", "batches", "bounds", "triangle_count")
SIX_ROLES = {"base", "dark", "trim", "accent", "lit", "cool"}


def check_export_payload(target: Path, where: str, manifest_roles, manifest_bounds) -> dict:
    """Validate the pinned export itself, not just its hash.

    The manifest says *which* file; this says the file is a usable mesh: strict JSON
    (so NaN cannot hide in a vertex), the declared envelope ordered, the six material
    roles, finite 3-vectors and triangle lists. The legacy integer marker `schema: 1`
    is accepted during the migration window declared in art/manifests/decisions.md.
    """
    doc = Document(target, target.parent)
    payload = doc.data
    if payload.get("schema") != 1 and payload.get("contract") != "star-armada/mesh-export":
        raise Rejected("E_EXPORT_SHAPE",
                       f"{where}: payload declares neither legacy 'schema': 1 nor the mesh-export contract")
    for key in EXPORT_KEYS:
        if key not in payload:
            raise Rejected("E_EXPORT_SHAPE", f"{where}: payload has no '{key}'")
    unknown = sorted(set(payload["batches"]) - SIX_ROLES)
    if unknown:
        raise Rejected("E_SCHEMA", f"{where}: payload uses unknown material roles {unknown}")
    vertices = payload["vertices"]
    if not isinstance(vertices, list) or not vertices:
        raise Rejected("E_EXPORT_SHAPE", f"{where}: payload has no vertices")
    for i, vertex in enumerate(vertices):
        if not isinstance(vertex, list) or len(vertex) != 3 or \
                any(type(c) not in (int, float) or not math.isfinite(c) for c in vertex):
            raise Rejected("E_EXPORT_SHAPE", f"{where}: vertices[{i}] is not a finite 3-vector")
    # A batch row is [nx, ny, nz, i0, i1, i2]: the exporter's flat display-list form.
    # Indices must land inside the vertex array -- a silently wrapping index draws a
    # garbled hull rather than failing, which is exactly what a validator is for.
    total = 0
    for role, batch in payload["batches"].items():
        if not isinstance(batch, list):
            raise Rejected("E_EXPORT_SHAPE", f"{where}: batch '{role}' is not a list")
        for row in batch:
            if not isinstance(row, list) or len(row) != 6:
                raise Rejected("E_EXPORT_SHAPE",
                               f"{where}: batch '{role}' row is not [nx,ny,nz,i0,i1,i2]")
            if any(type(c) not in (int, float) or not math.isfinite(c) for c in row[:3]):
                raise Rejected("E_EXPORT_SHAPE", f"{where}: batch '{role}' has a non-finite normal")
            for index in row[3:6]:
                if type(index) is not int or not 0 <= index < len(vertices):
                    raise Rejected("E_EXPORT_SHAPE",
                                   f"{where}: batch '{role}' index {index} outside 0..{len(vertices)-1}")
        total += len(batch)
    if total != payload["triangle_count"]:
        raise Rejected("E_EXPORT_SHAPE",
                       f"{where}: batches hold {total} triangles, triangle_count says {payload['triangle_count']}")
    lo, hi = payload["bounds"]
    if any(a > b for a, b in zip(lo, hi)):
        raise Rejected("E_BOUNDS_DEGENERATE", f"{where}: payload bounds min {lo} exceeds max {hi}")
    if set(payload["batches"]) != set(manifest_roles):
        raise Rejected("E_ROLE_MISMATCH",
                       f"{where}: payload fills {sorted(payload['batches'])}, "
                       f"manifest claims {sorted(manifest_roles)}")
    envelope = manifest_bounds
    if any(p < e for p, e in zip(lo, envelope["min"])) or \
            any(p > e for p, e in zip(hi, envelope["max"])):
        raise Rejected("E_BOUNDS_MISMATCH",
                       f"{where}: mesh bounds {lo}..{hi} escape the declared envelope "
                       f"{envelope['min']}..{envelope['max']}")
    return payload


def check_manifest_files(doc: Document) -> None:
    data = doc.data
    lo, hi = data["bounds"]["min"], data["bounds"]["max"]
    if any(a > b for a, b in zip(lo, hi)):
        raise Rejected("E_BOUNDS_DEGENERATE", f"bounds min {lo} exceeds max {hi}")
    for lod, entry in data["files"].items():
        target = doc.root / entry["path"]
        if not target.is_file():
            raise Rejected("E_FILE_MISSING", f"files.{lod}: {entry['path']} does not exist")
        size = target.stat().st_size
        if size > MAX_FILE_BYTES:
            raise Rejected("E_FILE_SIZE", f"files.{lod}: {size} bytes exceeds the pack budget")
        if entry["bytes"] != size:
            raise Rejected("E_FILE_SIZE", f"files.{lod}: declared {entry['bytes']}, actual {size}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != entry["sha256"]:
            raise Rejected("E_FILE_HASH", f"files.{lod}: sha256 mismatch for {entry['path']}")
        payload = check_export_payload(target, f"files.{lod}", data["roles"], data["bounds"])
        # budgets.triangles is the asset's own declared cost, and the mesh must fit inside it: a
        # manifest claiming less than the mesh it pins is a claim about a file that is gone. Nothing
        # read this field, so it was free to rot - the three specimens still declared their
        # pre-detail counts after S06/S07 added 2,756 / 2,580 / 2,832 triangles. Equality is not
        # demanded (a declared ceiling is legal, and a pack may promise more room than its stub
        # uses); draw calls stay a declaration, because the count depends on how the renderer
        # batches roles, not on the payload.
        declared = (data.get("budgets") or {}).get("triangles")
        if declared is not None and declared < payload["triangle_count"]:
            raise Rejected("E_MEASUREMENT_STALE",
                           f"budgets.triangles says {declared}, the mesh has "
                           f"{payload['triangle_count']}: the manifest declares a cost its own "
                           "mesh has outgrown")
    expected = recompute_revision(data["asset"], data["files"])
    if data["revision"] != expected:
        raise Rejected("E_REVISION_MISMATCH",
                       f"revision {data['revision'][:12]} != recomputed {expected[:12]}")
    approval = data.get("approval")
    if approval and approval.get("status") == "approved":
        if not approval.get("decision_id"):
            raise Rejected("E_EVIDENCE_MISSING", "approved without a decision id")
        if approval.get("reviewed_revision") != data["revision"]:
            raise Rejected("E_APPROVAL_STALE",
                           "approval binds a different revision than the one now declared")
        for rel in approval.get("reviewed_evidence", []):
            if not (ROOT / rel).is_file():
                raise Rejected("E_EVIDENCE_MISSING", f"reviewed evidence {rel} is not in the tree")


def check_registry(doc: Document, manifests_by_asset: dict) -> None:
    seen = set()
    for i, binding in enumerate(doc.data["bindings"]):
        key = binding["binding"]
        if key in seen:
            raise Rejected("E_DUPLICATE_BINDING", f"bindings[{i}]: '{key}' appears twice")
        seen.add(key)
    for i, binding in enumerate(doc.data["bindings"]):
        key = binding["binding"]
        check_binding_extent(binding, i, manifests_by_asset)
        if binding["status"] == "core" and binding["manifest"] not in manifests_by_asset:
            raise Rejected("E_MANIFEST_UNRESOLVED",
                           f"bindings[{i}]: core binding '{key}' names {binding['manifest']}, "
                           "which no manifest in this tree defines")
        for other in binding.get("shared_source_with", []):
            if other == key:
                raise Rejected("E_SCHEMA", f"bindings[{i}]: shared_source_with itself")


def extent_grace(envelope: dict) -> list:
    """How far a mesh may move past its binding's declared envelope without a fresh approval.

    The owner's rule (s02-extent-tolerance-2026-10-16): at most 1 % of that axis, or two world units,
    whichever is smaller. Detail stands proud of the surface it is placed on, so without a grace
    every raised belt would fail the contract; without a limit a detail pass can widen a hull by six
    percent and nothing notices, which is exactly what happened to the battleship's beam.
    """
    return [min(0.01 * (hi - lo), EXTENT_GRACE_UNITS) for lo, hi in zip(envelope["min"], envelope["max"])]


def check_binding_extent(binding: dict, index: int, manifests_by_asset: dict) -> None:
    """The binding's envelope is the extent the hull was approved at, and it is checkable.

    A manifest cannot move the envelope: it can only declare bounds, and the mesh must fit inside
    them. So an authored revision that grows the mesh has to be met by a *new* envelope in the
    registry — and that edit is the point of review. Widening it past the grace is what
    `tools/art/update_contract_examples.py --accept-extent` records with an approval id, and a
    receipt that names something other than the approval the manifest carries is a dangling claim.
    """
    envelope = binding.get("envelope")
    manifest = manifests_by_asset.get(binding.get("manifest"))
    if envelope is None or manifest is None:
        return
    bounds = manifest.data["bounds"]
    grace = extent_grace(envelope)
    for axis, name in enumerate("xyz"):
        lo, hi = bounds["min"][axis], bounds["max"][axis]
        if lo < envelope["min"][axis] - grace[axis] or hi > envelope["max"][axis] + grace[axis]:
            raise Rejected("E_EXTENT_DRIFT",
                           f"bindings[{index}] '{binding['binding']}': the manifest reaches {name} "
                           f"{lo}..{hi}, past the declared envelope "
                           f"{envelope['min'][axis]}..{envelope['max'][axis]} by more than the "
                           f"{grace[axis]:.3f}-unit grace - that is a new extent, so it needs a new "
                           "approval and a re-declared envelope")
    decision = binding.get("envelope_decision")
    if decision and decision != (manifest.data.get("approval") or {}).get("decision_id"):
        raise Rejected("E_EXTENT_DRIFT",
                       f"bindings[{index}] '{binding['binding']}': envelope_decision '{decision}' "
                       "names no approval this manifest carries")


def check_pack(doc: Document, core_bindings: set) -> None:
    data = doc.data
    for contract in data["requires"]["contracts"]:
        name, _, major = contract.rpartition("/v")
        known = CONTRACTS.get(name)
        if not known or int(major) not in ([known[0]] if isinstance(known[0], int) else []):
            raise Rejected("E_UNKNOWN_CONTRACT", f"requires.contracts: unknown contract '{contract}'")
    content = data["content"]
    seen = set()
    for entry in content.get("replaces", []):
        if entry["binding"] not in core_bindings:
            raise Rejected("E_UNKNOWN_BINDING",
                           f"replaces: '{entry['binding']}' is not a core binding")
        if entry["binding"] in seen:
            raise Rejected("E_DUPLICATE_ID", f"replaces: '{entry['binding']}' twice in one pack")
        seen.add(entry["binding"])
    for entry in content.get("adds", []):
        if entry["binding"] in core_bindings:
            raise Rejected("E_ASSET_COLLISION",
                           f"adds: '{entry['binding']}' already exists in core")
        if entry["binding"] in seen:
            raise Rejected("E_DUPLICATE_ID", f"'{entry['binding']}' appears twice in one pack")
        seen.add(entry["binding"])
        if not data["requires"].get("gameplay_mod"):
            raise Rejected("E_MISSING_GAMEPLAY_MOD",
                           "an additive pack must name the gameplay mod that defines its entities")
        if not entry.get("entity_source"):
            raise Rejected("E_MISSING_GAMEPLAY_MOD",
                           f"adds: '{entry['binding']}' does not name its entity source")


def validate(doc: Document, *, manifests_by_asset=None, core_bindings=None) -> None:
    data = doc.data
    if "contract" in data:
        name, major = data["contract"], data.get("contract_major")
        if name not in CONTRACTS or major != CONTRACTS[name][0]:
            raise Rejected("E_UNKNOWN_CONTRACT",
                           f"contract '{name}' major {major} is not understood by this build")
    check_path_safety(doc)
    schema = load_schema(CONTRACTS[data["contract"]][1])
    check_schema(data, schema, doc.path.name, schema)
    if data["contract"] == "star-armada/model-manifest":
        check_manifest_files(doc)
    elif data["contract"] == "star-armada/binding-registry":
        check_registry(doc, manifests_by_asset or {})
    elif data["contract"] == "star-armada/visual-pack":
        check_pack(doc, core_bindings or set())


# --------------------------------------------------------------------------- driver

def valid_examples() -> dict[str, Document]:
    payloads = set()
    for path in sorted(EXAMPLES.rglob("*.json")):
        if INVALID in path.parents or path.name == "EXPECTED.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a broken document is reported as a document
            continue
        if isinstance(data, dict) and data.get("contract") == "star-armada/model-manifest":
            rel = path.relative_to(EXAMPLES)
            root = EXAMPLES / "packs" / rel.parts[1] if rel.parts[0] == "packs" else ROOT
            for entry in data.get("files", {}).values():
                payloads.add((root / entry["path"]).resolve())
    docs = {}
    for path in sorted(EXAMPLES.rglob("*.json")):
        if INVALID in path.parents or path.name == "EXPECTED.json":
            continue
        if path.resolve() in payloads:
            continue  # a pinned export payload: data, validated through its manifest
        rel = path.relative_to(EXAMPLES)
        root = ROOT
        if rel.parts[0] == "packs":
            root = EXAMPLES / "packs" / rel.parts[1]  # the pack root, whatever its depth
        docs[str(rel)] = Document(path, root)
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    args = parser.parse_args()

    report = collections.OrderedDict()
    failures = []

    # 1. valid examples, as one set: a registry resolves against the manifests it names
    docs = valid_examples()
    if not docs:
        print("no examples found — that is a failure, not a pass")
        return 1
    manifests, manifests_by_asset = {}, {}
    for rel, doc in docs.items():
        if doc.data.get("contract") == "star-armada/model-manifest":
            manifests[rel] = doc
            manifests_by_asset[doc.data["asset"]] = doc
    core_bindings = set()
    for rel, doc in docs.items():
        if doc.data.get("contract") == "star-armada/binding-registry":
            core_bindings |= {b["binding"] for b in doc.data["bindings"]}
    for rel, doc in sorted(docs.items()):
        try:
            validate(doc, manifests_by_asset=manifests_by_asset, core_bindings=core_bindings)
            report[rel] = "ok"
        except Rejected as exc:
            report[rel] = f"{exc.code} {exc.message}"
            failures.append((rel, exc))

    # 2. negative controls
    expected = json.loads((INVALID / "EXPECTED.json").read_text(encoding="utf-8"))
    for name, code in expected.items():
        if name.startswith("__"):
            continue
        path = INVALID / name
        try:
            validate(Document(path, ROOT),
                     manifests_by_asset=manifests_by_asset, core_bindings=core_bindings)
            report[f"invalid/{name}"] = "ACCEPTED — the control was not rejected"
            failures.append((name, Rejected("E_NOT_REJECTED", "fixture was accepted")))
        except Rejected as exc:
            if exc.code != code:
                report[f"invalid/{name}"] = f"{exc.code} (expected {code})"
                failures.append((f"invalid/{name}", exc))
            else:
                report[f"invalid/{name}"] = f"rejected {exc.code} as declared"

    # 3. the one control that cannot be a file: a manifest reached through a symlink
    runtime_code = expected["__runtime_symlink__"]
    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / "outside"
        inside = Path(tmp) / "packroot"
        (outside / "models").mkdir(parents=True)
        (inside / "assets/models").mkdir(parents=True)
        (outside / "models/escape.json").write_text("{}", encoding="utf-8")
        os.symlink(outside, inside / "assets/link")
        probe = dict(json.loads((EXAMPLES / "manifests/alliance_battleship.json").read_text()))
        probe["files"] = {"mesh": {"path": "assets/link/models/escape.json",
                                   "sha256": "0" * 64, "bytes": 2}}
        probe_path = inside / "assets/models/probe.json"
        probe_path.write_text(json.dumps(probe), encoding="utf-8")
        doc = Document(probe_path, inside)
        try:
            validate(doc)
            report["runtime/symlink-escape"] = "ACCEPTED — the control was not rejected"
            failures.append(("runtime/symlink-escape", Rejected("E_NOT_REJECTED", "escape accepted")))
        except Rejected as exc:
            if exc.code != runtime_code:
                report["runtime/symlink-escape"] = f"{exc.code} (expected {runtime_code})"
                failures.append(("runtime/symlink-escape", exc))
            else:
                report["runtime/symlink-escape"] = f"rejected {exc.code} as declared"

    if args.json:
        print(json.dumps({"report": report, "failures": [{"item": i, "code": e.code,
                                                          "message": e.message}
                                                         for i, e in failures]}, indent=2))
    else:
        failed_items = {item for item, _exc in failures}
        for item, outcome in report.items():
            print(f"  {'FAIL' if item in failed_items else 'ok  '}  {item}: {outcome}")
        print()
        if failures:
            print(f"{len(failures)} failure(s): the contract is not satisfied")
        else:
            print(f"contract satisfied: {len(report)} checks, "
                  f"{len([r for r in report if r.startswith('invalid/') or r.startswith('runtime/')])} negative controls, "
                  "0 skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
