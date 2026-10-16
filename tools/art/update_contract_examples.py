#!/usr/bin/env python3
"""Re-pin the S02 contract examples to the payloads that are actually on disk.

The contract examples are not invented fixtures: `art/schemas/examples/manifests/*.json` describe
the three *real* approved exports, which is what lets the contract verify itself against the tree
instead of against a copy of itself. The price of that design is a coupling: any approved asset
revision moves the payload's size, sha256 and recomputed revision, and every example that names it
goes stale — including the negative controls derived from the real manifest, which then fail on
`E_FILE_SIZE` before reaching the rule they were built to prove.

So this tool derives rather than transcribes, and it derives from history, not from the working
tree: for each example it re-reads the payload on disk and rewrites the declared size, sha256,
recomputed revision and approval binding, then re-applies to each negative control the *difference*
that control had from the committed manifest — a wrong size, a wrong hash, a wrong path, a zeroed
revision, a stale approval, a missing evidence path. The differences are grouped (file record,
revision, approval) and a control must differ in exactly one group, otherwise the tool refuses
rather than guessing which defect was intended. A control keeps exactly one defect; nothing else
moves, and running the tool twice changes nothing.

    python3 tools/art/update_contract_examples.py            # rewrite in place
    python3 tools/art/update_contract_examples.py --check    # exit 1 if anything is stale

It imports `recompute_revision` from `tools/art/validate_contract.py` rather than reimplementing it,
so the tool and the validator cannot disagree about what a revision is.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "art"))

from validate_contract import (  # noqa: E402  (same directory, one implementation each)
    EXTENT_GRACE_UNITS,
    recompute_revision,
)

EXAMPLES = ROOT / "art" / "schemas" / "examples"
MANIFESTS = EXAMPLES / "manifests"
INVALID = EXAMPLES / "invalid"
APPROVALS = ROOT / "art" / "manifests" / "approvals.json"
EXPECTED = INVALID / "EXPECTED.json"

# Every field that may legitimately move when the payload behind a manifest is re-pinned, grouped by
# the rule it belongs to. A control may carry a defect in exactly one group.
MUTABLE = (
    ("files", "mesh", "path"),
    ("files", "mesh", "bytes"),
    ("files", "mesh", "sha256"),
    ("revision",),
    ("approval", "reviewed_revision"),
    ("approval", "reviewed_evidence"),
    ("approval", "decision_id"),
    ("bounds",),
    ("budgets", "triangles"),
)
GROUPS = {
    "file record": (("files", "mesh", "path"), ("files", "mesh", "bytes"), ("files", "mesh", "sha256")),
    "revision": (("revision",),),
    "approval": (("approval", "reviewed_revision"), ("approval", "reviewed_evidence"),
                 ("approval", "decision_id")),
    "envelope": (("bounds",),),
    "measurement": (("budgets", "triangles"),),
}


def dig(obj, path: tuple):
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


def put(obj: dict, path: tuple, value) -> None:
    for key in path[:-1]:
        obj = obj.setdefault(key, {})
    obj[path[-1]] = value


def committed(relative: str):
    """The manifest as committed, so re-running the tool is idempotent even before the change lands."""
    try:
        blob = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT, check=True,
                              capture_output=True).stdout
        return json.loads(blob)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return json.loads((ROOT / relative).read_text())


def payload_record(path: str) -> dict:
    data = (ROOT / path).read_bytes()
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def decision_evidence(approval_id: str):
    """The evidence a recorded decision actually cites, filtered to files that exist.

    A record may cite something that was never committed; an example must not, because the validator
    rejects a manifest whose evidence is missing. `None` means "keep the example's own list".
    """
    if not APPROVALS.exists():
        return None
    for record in json.loads(APPROVALS.read_text()).get("decision_log", []):
        if record.get("id") == approval_id:
            cited = [p for p in record.get("evidence_references", []) if (ROOT / p).exists()]
            return cited or None
    return None


def refresh_base(manifest: dict, approvals: dict) -> dict:
    """The real manifest, re-pinned to the payload on disk and to the asset's current approval."""
    out = copy.deepcopy(manifest)
    out["files"]["mesh"] = payload_record(out["files"]["mesh"]["path"])
    # The declared envelope follows the payload. Detail stands proud of the surface it sits on, so an
    # approved revision that adds a raised belt or machinery bank widens the mesh; the envelope is the
    # contract's record of that extent, not a wish about it. This is the field that goes stale in
    # silence, because every other check still passes while the mesh quietly outgrows its envelope.
    payload_bounds = json.loads((ROOT / out["files"]["mesh"]["path"]).read_text())["bounds"]
    out["bounds"] = {"min": copy.deepcopy(payload_bounds[0]), "max": copy.deepcopy(payload_bounds[1])}
    # budgets.triangles is the mesh's own count, not the class ceiling: the schema calls it
    # "measured, not aspirational", and the ceiling lives in the section 9 table.
    out.setdefault("budgets", {})["triangles"] = json.loads(
        (ROOT / out["files"]["mesh"]["path"]).read_text())["triangle_count"]
    out["revision"] = recompute_revision(out["asset"], out["files"])
    # Match on the runtime path, not on the asset label: the approval record and the contract
    # examples are separate documents and have already disagreed once about how to spell an id.
    asset = next((a for a in approvals.get("approved_assets", []) if out["files"]["mesh"]["path"] in a.get("runtime", {})), None)
    if asset:
        approval_id = asset["approval_id"]
        out.setdefault("approval", {})["decision_id"] = approval_id
        out["approval"]["reviewed_revision"] = out["revision"]
        evidence = decision_evidence(approval_id)
        if evidence:
            out["approval"]["reviewed_evidence"] = evidence
    return out


def defect_groups(base: dict, control: dict) -> list[str]:
    return [name for name, fields in GROUPS.items()
            if any(dig(base, f) != dig(control, f) for f in fields)]


def repin_registry(bases: dict, check: bool, changes: list, accept_extent: "str | None") -> bool:
    """The binding registry declares each binding's extent. Widening one is an approval, not a re-pin.

    The envelope is the extent the hull was approved at, so this pass compares the manifest's bounds
    against it instead of copying them across. Inside the section 9 grace (1 % of that axis, or two
    units, whichever is smaller) the envelope is left exactly as it was: a small proud detail is not an
    approval event, and rewriting the envelope to hug the mesh would erase the baseline the next
    revision is measured against. Past the grace the tool refuses unless the caller names, with
    `--accept-extent <decision id>`, the approval that accepted the new extent; it then widens the
    envelope and records that id in `envelope_decision`, which the validator checks against the
    manifest's own approval. Returns True when it refused.
    """
    path = EXAMPLES / "core-registry.json"
    registry = json.loads(path.read_text())
    refused = False
    for entry in registry.get("bindings", []):
        asset = entry.get("manifest")
        if asset not in bases or entry.get("envelope") is None:
            continue
        envelope, bounds = entry["envelope"], bases[asset][1]["bounds"]
        grace = [min(0.01 * (hi - lo), EXTENT_GRACE_UNITS)
                 for lo, hi in zip(envelope["min"], envelope["max"])]
        # How far the mesh reaches *past* the envelope on each axis; a mesh smaller than the
        # envelope is inside it and scores zero.
        over = {axis: max(0.0, envelope["min"][i] - bounds["min"][i], bounds["max"][i] - envelope["max"][i])
                for i, axis in enumerate("xyz")}
        worst = max(over, key=lambda axis: over[axis])
        if over[worst] <= grace["xyz".index(worst)]:
            continue
        if accept_extent is None:
            print(f"REFUSED {entry['binding']}: the mesh reaches {worst} "
                  f"{round(bounds['min']['xyz'.index(worst)], 3)}..{round(bounds['max']['xyz'.index(worst)], 3)} "
                  f"against a declared envelope of "
                  f"{round(envelope['min']['xyz'.index(worst)], 3)}..{round(envelope['max']['xyz'.index(worst)], 3)}: "
                  f"{round(over[worst], 3)} units past it, more than the "
                  f"{round(grace['xyz'.index(worst)], 3)}-unit grace. That is a new extent, so it needs a "
                  f"new approval - pass --accept-extent <decision id> once the owner has given one.")
            refused = True
            continue
        changes.append(f"{path.relative_to(ROOT)}: {entry['binding']} envelope widened on {worst} to "
                       f"{round(bounds['max']['xyz'.index(worst)], 3)} under {accept_extent}")
        entry["envelope"] = copy.deepcopy(bounds)
        entry["envelope_decision"] = accept_extent
    if not check:
        path.write_text(json.dumps(registry, indent=2) + "\n")
    return refused


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-pin the S02 contract examples to the payloads that are actually on disk.")
    parser.add_argument("--check", action="store_true", help="report staleness instead of rewriting")
    parser.add_argument("--accept-extent", metavar="DECISION_ID", default=None,
                        help="record this approval as the one that accepted a widened envelope")
    args = parser.parse_args()

    approvals = json.loads(APPROVALS.read_text()) if APPROVALS.exists() else {}
    json.loads(EXPECTED.read_text())          # fail early if the expectations themselves are broken
    bases: dict[str, tuple[dict, dict]] = {}  # asset -> (as committed, re-pinned)
    changes: list[str] = []
    refused = False

    for path in sorted(MANIFESTS.glob("*.json")):
        relative = str(path.relative_to(ROOT))
        old, new = committed(relative), refresh_base(json.loads(path.read_text()), approvals)
        bases[old["asset"]] = (old, new)
        if new != json.loads(path.read_text()):
            changes.append(f"{relative}: bytes {old['files']['mesh']['bytes']} -> "
                           f"{new['files']['mesh']['bytes']}, revision {old['revision'][:12]} -> "
                           f"{new['revision'][:12]}")
            if not args.check:
                path.write_text(json.dumps(new, indent=2) + "\n")

    for path in sorted(INVALID.glob("*.json")):
        if path.name == "EXPECTED.json":
            continue
        relative = str(path.relative_to(ROOT))
        control, authored = json.loads(path.read_text()), committed(relative)
        asset = authored.get("asset")
        if asset not in bases:       # not a variant of a real manifest: not this tool's business
            continue
        old_base, new_base = bases[asset]
        groups = defect_groups(old_base, authored)
        if len(groups) > 1:
            print(f"REFUSED {path.name}: differs from the real manifest in {len(groups)} groups "
                  f"({', '.join(groups)}) - which defect was intended is not derivable")
            refused = True
            continue
        # Start from the control as authored, not from the refreshed manifest: most controls carry
        # their defect in a field this tool does not manage at all (a missing key, an extra key, an
        # unknown contract id), and starting from the refreshed manifest would quietly delete it and
        # leave a control that passes.
        new = copy.deepcopy(authored)
        for field in MUTABLE:
            if dig(old_base, field) != dig(authored, field):  # this control's own defect, kept
                put(new, field, copy.deepcopy(dig(authored, field)))
                continue
            # A control authored in the same commit that moved the base reads as merely stale here,
            # so its defect is erased: a declared budget below the mesh's count is both a defect and
            # exactly what a refresh would have replaced. Author such a control in its own commit,
            # after the re-pin has landed, and the committed base makes its defect visible.
            put(new, field, copy.deepcopy(dig(new_base, field)))  # re-pinned to the payload on disk
        if new != control:
            label = groups[0] if groups else "re-pin only"
            changes.append(f"{str(path.relative_to(ROOT))}: re-pinned ({label})")
            if not args.check:
                path.write_text(json.dumps(new, indent=2) + "\n")

    refused = repin_registry(bases, args.check, changes, args.accept_extent) or refused

    if not changes and not refused:
        print("contract examples: current - every example names the payloads on disk")
        return 0
    verb = "stale" if args.check else "re-pinned"
    for line in changes:
        print(f"  {verb}: {line}")
    print(f"contract examples: {len(changes)} file(s) {verb}")
    return 2 if refused else (1 if args.check else 0)


if __name__ == "__main__":
    raise SystemExit(main())
