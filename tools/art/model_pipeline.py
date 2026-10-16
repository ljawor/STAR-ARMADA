#!/usr/bin/env python3
"""STAR ARMADA model authoring pipeline: build, export and validate.

Three commands, one implementation (also reachable as ``build-model``, ``export-model`` and
``validate-models`` in this directory, which forward here):

    python3 tools/art/build-model     --asset rebel:battleship
    python3 tools/art/build-model     --batch approved-trio
    python3 tools/art/export-model    --asset rebel:battleship
    python3 tools/art/validate-models --all

Contract (S03 decision `s03-pipeline-policy-2026-10-16`, `art/manifests/pipeline_policy.json`):

* Nothing here writes user data, and nothing here imports the game or the renderer. It only runs
  Blender on the declared exporter and hashes the result.
* ``build-model`` regenerates a script-authoritative asset's source and runtime export from code,
  then *verifies* the runtime export against the approved byte record. A rebuild that would change
  what the owner approved fails instead of silently landing.
* ``export-model`` produces the runtime export without ever touching the declared source: a
  script-authoritative asset is exported inside a throwaway copy of the tree, and a
  blend-authoritative asset's export script is refused unless it is genuinely export-only.
* ``validate-models`` is the S02 contract validator plus the build-side checks (approved hashes,
  payload sanity, provenance, tree hygiene, packaging). If the contract validator is missing it
  fails: it is not a second opinion.

Blender is never hardcoded in code. Resolution order: ``--blender PATH``, ``$STAR_ARMADA_BLENDER``,
``blender`` on PATH, then the per-platform candidates in ``art/manifests/pipeline.json``.

Exit codes: 0 satisfied, 1 failed (a real problem), 2 refused (the request contradicts the policy).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_REL = "art/manifests/pipeline.json"
CONTRACT_VALIDATOR_REL = "tools/art/validate_contract.py"
EXPORT_MARKER = "GAME_EXPORT"
SAVE_CALL = re.compile(r"save_as_mainfile|save_mainfile|wm\.save")
OPEN_CALL = re.compile(r"open_mainfile|blend_data")
TOOL_VERSION = 1


class PipelineError(RuntimeError):
    """A refusal (exit 2) or a failure (exit 1) with a message meant for a human."""

    def __init__(self, message, code="E_PIPELINE", refused=False):
        super().__init__(message)
        self.code = code
        self.refused = refused


# --------------------------------------------------------------------------------------------------
# files and records


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_path(repo, relative):
    """Resolve a repo-relative path, refusing anything that escapes the repository."""
    if not isinstance(relative, str) or not relative:
        raise PipelineError(f"not a usable path: {relative!r}", "E_PATH")
    candidate = (Path(repo) / relative).resolve()
    root = Path(repo).resolve()
    if root != candidate and root not in candidate.parents:
        raise PipelineError(f"path escapes the repository: {relative!r}", "E_PATH")
    return candidate


def load_pipeline(repo=REPO_ROOT):
    path = Path(repo) / PIPELINE_REL
    if not path.is_file():
        raise PipelineError(f"missing {PIPELINE_REL}", "E_NO_PIPELINE")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(f"{PIPELINE_REL} is not valid JSON: {exc}", "E_PIPELINE_JSON") from exc
    assets = data.get("assets")
    if not isinstance(assets, list) or not assets:
        raise PipelineError(f"{PIPELINE_REL} declares no assets", "E_PIPELINE_SHAPE")
    seen = set()
    for asset in assets:
        for key in ("binding", "asset_id", "authority", "source", "exporter", "runtime",
                    "expected_hashes", "expected_triangles", "roles"):
            if key not in asset:
                raise PipelineError(f"{asset.get('binding', '?')}: missing key {key!r}",
                                    "E_PIPELINE_SHAPE")
        if asset["authority"] not in ("script", "blend"):
            raise PipelineError(f"{asset['binding']}: unknown authority {asset['authority']!r}",
                                "E_PIPELINE_SHAPE")
        if asset["binding"] in seen:
            raise PipelineError(f"duplicate binding {asset['binding']}", "E_DUPLICATE_BINDING")
        seen.add(asset["binding"])
        if asset["authority"] == "blend" and not asset.get("export_script"):
            raise PipelineError(
                f"{asset['binding']} is blend-authoritative but declares no export_script; an "
                "export-only path is required so the .blend is never overwritten",
                "E_PIPELINE_SHAPE")
    for name, members in (data.get("batches") or {}).items():
        unknown = [b for b in members if b not in seen]
        if unknown:
            raise PipelineError(f"batch {name!r} names unknown bindings {unknown}",
                                "E_UNKNOWN_BINDING")
    return data


def find_asset(cfg, binding):
    for asset in cfg["assets"]:
        if asset["binding"] == binding:
            return asset
    raise PipelineError(f"unknown binding {binding!r}; known: "
                        f"{', '.join(a['binding'] for a in cfg['assets'])}", "E_UNKNOWN_BINDING")


def select_assets(cfg, args):
    chosen = []
    for binding in getattr(args, "asset", None) or ():
        chosen.append(find_asset(cfg, binding))
    for name in getattr(args, "batch", None) or ():
        members = (cfg.get("batches") or {}).get(name)
        if not members:
            raise PipelineError(f"unknown batch {name!r}; known: "
                                f"{', '.join(cfg.get('batches') or {})}", "E_UNKNOWN_BATCH")
        chosen.extend(find_asset(cfg, binding) for binding in members)
    if getattr(args, "all", False):
        chosen = list(cfg["assets"])
    if not chosen:
        raise PipelineError("nothing selected: pass --asset BINDING, --batch NAME or --all",
                            "E_NO_SELECTION", refused=True)
    unique = {}
    for asset in chosen:
        unique[asset["binding"]] = asset
    return [unique[key] for key in sorted(unique)]


def expected_hashes(repo, asset):
    path = repo_path(repo, asset["expected_hashes"])
    if not path.is_file():
        raise PipelineError(f"{asset['binding']}: missing approved-hash record "
                            f"{asset['expected_hashes']}", "E_NO_APPROVED_RECORD")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------
# Blender discovery and execution


def resolve_blender(explicit=None, cfg=None, env=None, which=None, system=None):
    """Find a Blender executable without hardcoding one in code."""
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    system = platform.system().lower() if system is None else system
    env_var = (cfg or {}).get("blender", {}).get("env_var", "STAR_ARMADA_BLENDER")
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_file():
            raise PipelineError(f"--blender {explicit} does not exist", "E_NO_BLENDER")
        return candidate
    from_env = env.get(env_var)
    if from_env:
        candidate = Path(from_env)
        if not candidate.is_file():
            raise PipelineError(f"${env_var} points at {from_env}, which does not exist",
                                "E_NO_BLENDER")
        return candidate
    on_path = which("blender")
    if on_path:
        return Path(on_path)
    key = {"darwin": "darwin", "windows": "win32", "linux": "linux"}.get(system, system)
    candidates = ((cfg or {}).get("blender", {}).get("candidates") or {}).get(key, [])
    for candidate in candidates:
        if Path(candidate).is_file():
            return Path(candidate)
    raise PipelineError(
        "no Blender found. Pass --blender /path/to/blender, set "
        f"${env_var}, or add your install to the '{key}' candidates in {PIPELINE_REL}. "
        f"Tried: {', '.join(candidates) or 'nothing'}", "E_NO_BLENDER")


def blender_version(executable):
    result = subprocess.run([str(executable), "--version"], capture_output=True, text=True)
    match = re.search(r"Blender\s+([0-9]+(?:\.[0-9]+)+)", result.stdout or "")
    if not match:
        raise PipelineError(f"could not read a version from {executable}: "
                            f"{(result.stdout or result.stderr or '').strip()[:200]}",
                            "E_BLENDER_VERSION")
    return match.group(1)


def run_blender(executable, script, argv=(), cwd=None):
    command = [str(executable), "--background", "--python-exit-code", "1",
               "--python", str(script)]
    if argv:
        command += ["--", *[str(a) for a in argv]]
    result = subprocess.run(command, capture_output=True, text=True, cwd=str(cwd or REPO_ROOT),
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def parse_export(output):
    for line in reversed(output.splitlines()):
        if line.startswith(EXPORT_MARKER):
            try:
                return json.loads(line[len(EXPORT_MARKER):].strip())
            except json.JSONDecodeError:
                return None
    return None


def assert_export_only(repo, asset, script_rel):
    """A blend-authoritative export script may read the source; it may never write it."""
    script = repo_path(repo, script_rel)
    if not script.is_file():
        raise PipelineError(f"{asset['binding']}: export script {script_rel} is missing",
                            "E_NO_EXPORTER")
    text = script.read_text(encoding="utf-8")
    saving = SAVE_CALL.search(text)
    if saving:
        raise PipelineError(
            f"{asset['binding']}: export script {script_rel} saves the Blender file "
            f"({saving.group(0)!r}). A blend-authoritative exporter is export-only: "
            "it must open the source and write the runtime export, never the .blend. Refusing to run "
            "it.", "E_EXPORT_WOULD_OVERWRITE_SOURCE", refused=True)
    if not OPEN_CALL.search(text):
        raise PipelineError(
            f"{asset['binding']}: export script {script_rel} never opens the declared source, so it "
            "cannot be an export of that source", "E_EXPORT_NOT_FROM_SOURCE", refused=True)
    return script


# --------------------------------------------------------------------------------------------------
# provenance


def write_provenance(repo, cfg, asset, record):
    rel_dir = cfg.get("provenance", {}).get("dir", "art/manifests/provenance")
    directory = repo_path(repo, rel_dir)
    directory.mkdir(parents=True, exist_ok=True)
    slug = asset["binding"].replace(":", "-")
    path = directory / f"{slug}.json"
    payload = {
        "schema": 1,
        "binding": asset["binding"],
        "asset_id": asset["asset_id"],
        "authority": asset["authority"],
        "tool": "tools/art/model_pipeline.py",
        "tool_version": TOOL_VERSION,
        "recorded": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {"system": platform.system(), "release": platform.release(),
                 "machine": platform.machine()},
        "coordinate_policy": asset["coordinates"],
        "blender": {"executable_name": Path(record["blender"]).name,
                    "version": record["blender_version"], "pin": cfg["blender"]["pin"]},
        "source": {"path": asset["source"], "sha256": record["source_sha256"]},
        "exporter": {"path": record["exporter"], "sha256": record["exporter_sha256"]},
        "runtime": {"path": asset["runtime"], "sha256": record["runtime_sha256"],
                    "bytes": record["runtime_bytes"],
                    "triangles": record["runtime_triangles"]},
        "approved_reference": {"record": asset["expected_hashes"],
                               "sha256": record["approved_sha256"],
                               "matches": record["matches_approved"]},
        "action": record["action"],
        "notes": record["notes"],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def provenance_state(repo, cfg, asset) -> dict | None:
    rel_dir = cfg.get("provenance", {}).get("dir", "art/manifests/provenance")
    slug = asset["binding"].replace(":", "-")
    path = repo_path(repo, f"{rel_dir}/{slug}.json")
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_corrupt": True}


# --------------------------------------------------------------------------------------------------
# build / export


def _run_and_verify(repo, cfg, asset, executable, script_rel, opts, action, workdir=None):
    """Run one exporter, then verify the runtime export against the approved bytes."""
    root = Path(workdir or repo)
    runtime = root / asset["runtime"]
    source = root / asset["source"]
    before_runtime = sha256_file(runtime) if runtime.is_file() else None
    before_source = sha256_file(source) if source.is_file() else None
    result = run_blender(executable, root / script_rel, cwd=root)
    rc, output = result
    if rc != 0 or not runtime.is_file():
        tail = "\n".join(output.strip().splitlines()[-25:])
        raise PipelineError(f"{asset['binding']}: Blender exited {rc} without a runtime export\n"
                            f"{tail}", "E_BUILD_FAILED")
    after_runtime = sha256_file(runtime)
    after_source = sha256_file(source) if source.is_file() else None
    approved = expected_hashes(repo, asset).get(asset["runtime"])
    if approved is None:
        raise PipelineError(f"{asset['binding']}: {asset['expected_hashes']} records no hash for "
                            f"{asset['runtime']}; an asset with no approved bytes is an error, not "
                            "a pass", "E_NO_APPROVED_HASH")
    if after_runtime != approved:
        raise PipelineError(
            f"{asset['binding']}: the rebuilt runtime export does not match the approved bytes.\n"
            f"  approved {approved}\n  produced {after_runtime}\n"
            "  The appearance the owner approved changed. Do NOT commit this; review the export and "
            "re-approve the revision deliberately.", "E_RUNTIME_HASH")
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    restored = False
    if action == "build" and after_source != before_source and after_runtime == before_runtime \
            and not opts.keep_blend:
        subprocess.run(["git", "-C", str(repo), "checkout", "--", asset["source"]],
                       capture_output=True, text=True)
        restored = True
        after_source = before_source
    record = {
        "action": action,
        "blender": str(executable),
        "blender_version": opts.blender_version,
        "source_sha256": after_source,
        "exporter": script_rel,
        "exporter_sha256": sha256_file(root / script_rel),
        "runtime_sha256": after_runtime,
        "runtime_bytes": runtime.stat().st_size,
        "runtime_triangles": payload.get("triangle_count"),
        "approved_sha256": approved,
        "matches_approved": after_runtime == approved,
        "notes": [],
    }
    if restored:
        record["notes"].append(
            "the .blend was regenerated from code with unchanged runtime bytes and restored from "
            "Git, so a rebuild never leaves an approved binary modified for no reason")
    if action == "export" and workdir:
        record["notes"].append("exported inside an isolated copy of the tree; the repository's "
                              "declared source was not opened for writing")
    return record, payload


def build_asset(repo, cfg, asset, executable, opts):
    if asset["authority"] != "script":
        raise PipelineError(
            f"{asset['binding']} is blend-authoritative: its .blend is the master and build-model "
            "regenerates sources from code, so it does not apply. Use export-model.",
            "E_WRONG_AUTHORITY", refused=True)
    exporter = repo_path(repo, asset["exporter"])
    if not exporter.is_file():
        raise PipelineError(f"{asset['binding']}: missing exporter {asset['exporter']}",
                            "E_NO_EXPORTER")
    return _run_and_verify(repo, cfg, asset, executable, asset["exporter"], opts, "build")


def export_asset(repo, cfg, asset, executable, opts):
    """Produce the runtime export without touching the declared source."""
    if asset["authority"] == "blend":
        script_rel = assert_export_only(repo, asset, asset["export_script"])
        return _run_and_verify(repo, cfg, asset, executable,
                               str(script_rel.relative_to(repo)), opts, "export")
    # Script-authoritative: the generator is the source, and it writes its own .blend on the way.
    # Run it in a throwaway copy of the tree so the approved source is never the one written.
    scratch = Path(tempfile.mkdtemp(prefix="sa-export-"))
    try:
        (scratch / "tools").mkdir(parents=True)
        shutil.copytree(repo_path(repo, "tools/art"), scratch / "tools/art")
        (scratch / PIPELINE_REL).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_path(repo, PIPELINE_REL), scratch / PIPELINE_REL)
        for relative in (asset["expected_hashes"],):
            target = scratch / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_path(repo, relative), target)
        record, payload = _run_and_verify(repo, cfg, asset, executable, asset["exporter"], opts,
                                          "export", workdir=scratch)
        produced = scratch / asset["runtime"]
        target = repo_path(repo, asset["runtime"])
        if not target.is_file() or sha256_file(target) != record["runtime_sha256"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(produced, target)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return record, payload


# --------------------------------------------------------------------------------------------------
# validation


class Report:
    def __init__(self):
        self.checks = []
        self.errors = []
        self.warnings = []
        self.notes = []

    def check(self, name, ok, code, message, refused=False):
        self.checks.append({"name": name, "ok": bool(ok)})
        if not ok:
            self.errors.append({"code": code, "message": message, "refused": refused})
        return ok

    def warn(self, code, message):
        self.warnings.append({"code": code, "message": message})

    def note(self, message):
        self.notes.append(message)

    @property
    def ok(self):
        return not self.errors


def _payload_sanity(repo, asset, report):
    path = repo_path(repo, asset["runtime"])
    if not path.is_file():
        report.check(f"payload[{asset['binding']}]", False, "E_FILE_MISSING",
                     f"{asset['runtime']} is missing")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.check(f"payload[{asset['binding']}]", False, "E_PAYLOAD_JSON",
                     f"{asset['runtime']} is not strict JSON: {exc}")
        return None
    rows = sum(len(batch) for batch in payload.get("batches", {}).values())
    triangles = payload.get("triangle_count")
    report.check(f"payload[{asset['binding']}].triangle_count", rows == triangles, "E_PAYLOAD_SHAPE",
                 f"{asset['runtime']}: triangle_count {triangles} but batches hold {rows} rows")
    report.check(f"payload[{asset['binding']}].triangles",
                 triangles == asset["expected_triangles"], "E_TRIANGLE_COUNT",
                 f"{asset['runtime']}: {triangles} triangles, expected {asset['expected_triangles']}")
    low, high = payload.get("bounds", [[0, 0, 0], [0, 0, 0]])
    report.check(f"payload[{asset['binding']}].bounds",
                 all(high[i] > low[i] for i in range(3)), "E_BOUNDS_DEGENERATE",
                 f"{asset['runtime']}: degenerate envelope {payload.get('bounds')}")
    roles = list(payload.get("batches", {}))
    unknown = [role for role in roles if role not in asset["roles"]]
    report.check(f"payload[{asset['binding']}].roles", not unknown, "E_UNKNOWN_ROLE",
                 f"{asset['runtime']}: undeclared material roles {unknown}")
    budget = asset.get("advisory_budget_triangles")
    if budget and triangles and triangles > budget:
        report.warn("W_TRIANGLE_BUDGET",
                     f"{asset['binding']}: {triangles} triangles over the advisory budget {budget} "
                     "(the S02 section 9 budgets are still pending the owner's review)")
    return payload


def _tree_hygiene(repo, cfg, report):
    hygiene = cfg.get("tree_hygiene") or {}
    patterns = hygiene.get("forbidden_patterns") or []
    offenders = []
    for root in hygiene.get("source_roots", []):
        directory = repo_path(repo, root)
        if not directory.is_dir():
            continue
        for pattern in patterns:
            for path in directory.rglob(pattern):
                if path.is_file():
                    offenders.append(str(path.relative_to(repo)))
    report.check("tree_hygiene", not offenders, "E_TREE_HYGIENE",
                 f"autosaves or temporary files under the source roots: {sorted(offenders)[:8]}")


def _packaging(repo, cfg, report):
    packaging = cfg.get("packaging") or {}
    spec_rel = packaging.get("spec")
    if not spec_rel:
        return
    spec = repo_path(repo, spec_rel)
    if not spec.is_file():
        report.check("packaging", False, "E_NO_SPEC", f"{spec_rel} is missing")
        return
    text = spec.read_text(encoding="utf-8")
    # datas entries are tuples; a mention elsewhere (a comment, a docstring) is not a bundle.
    bundled = [token for token in packaging.get("must_not_bundle", [])
               if any(candidate in text for candidate in (f'"{token}', f"'{token}"))]
    report.check("packaging", not bundled, "E_PACKAGING",
                 f"{spec_rel} appears to bundle {bundled}; editable sources and authoring tools "
                 "must not ship")


def _contract_validator(repo, cfg, report, run=True):
    rel = (cfg.get("contract_validation") or {}).get("validator", CONTRACT_VALIDATOR_REL)
    path = repo_path(repo, rel)
    if not path.is_file():
        message = (f"{rel} is missing. D2 requires validate-models to BE the S02 contract validator "
                   "rather than a second, weaker opinion; it arrives with PR #117.")
        if run:
            report.check("contract_validator", False, "E_NO_CONTRACT_VALIDATOR",
                         message + " Refusing to pass on the build-side checks alone.")
        else:
            report.warn("W_CONTRACT_SKIPPED",
                        message + " Running the build-side checks only: this is not acceptance "
                        "evidence.")
        return None
    report.check("contract_validator_present", True, "E_NO_CONTRACT_VALIDATOR", "")
    if not run:
        return None
    result = subprocess.run([sys.executable, str(path)], capture_output=True, text=True,
                            cwd=str(repo))
    report.check("contract_validator", result.returncode == 0, "E_CONTRACT",
                 f"{rel} failed (exit {result.returncode}): "
                 f"{((result.stdout or result.stderr) or '').strip().splitlines()[-1:]}")
    return result.returncode


def validate(repo, cfg, args, stream=None):
    stream = stream or sys.stdout
    report = Report()
    run_contract = not getattr(args, "no_contract", False)
    try:
        chosen = select_assets(cfg, args)
    except PipelineError as exc:
        if exc.code != "E_NO_SELECTION":
            raise
        chosen = list(cfg["assets"])
        report.note("no selection given: validating every asset in the registry")
    _contract_validator(repo, cfg, report, run=run_contract)
    for asset in chosen:
        binding = asset["binding"]
        for key in ("source", "exporter", "runtime"):
            path = repo_path(repo, asset[key])
            report.check(f"{binding}.{key}", path.is_file(), "E_FILE_MISSING",
                         f"{binding}: {key} {asset[key]} is missing")
        record = expected_hashes(repo, asset)
        approved_runtime = record.get(asset["runtime"])
        actual_runtime = None
        runtime_path = repo_path(repo, asset["runtime"])
        if runtime_path.is_file():
            actual_runtime = sha256_file(runtime_path)
        report.check(f"{binding}.approved_runtime",
                     approved_runtime is not None and approved_runtime == actual_runtime,
                     "E_RUNTIME_HASH",
                     f"{binding}: {asset['runtime']} is {actual_runtime}, the approved record says "
                     f"{approved_runtime}. The bytes the owner approved are not on disk.")
        approved_source = record.get(asset["source"])
        source_path = repo_path(repo, asset["source"])
        actual_source = sha256_file(source_path) if source_path.is_file() else None
        if approved_source is not None and actual_source != approved_source:
            message = (f"{binding}: {asset['source']} is {actual_source}, the approved record says "
                       f"{approved_source}. The source record is stale - rebuild with build-model "
                       "(which restores an unchanged .blend) or re-record it deliberately.")
            if getattr(args, "allow_source_drift", False):
                report.warn("W_SOURCE_DRIFT", message)
            else:
                report.check(f"{binding}.approved_source", False, "E_SOURCE_DRIFT", message)
        _payload_sanity(repo, asset, report)
        if (cfg.get("provenance") or {}).get("required"):
            state = provenance_state(repo, cfg, asset)
            if state is None:
                report.check(f"{binding}.provenance", False, "E_PROVENANCE_MISSING",
                             f"{binding}: no provenance record. Run build-model or export-model; a "
                             "shipped asset must say which toolchain produced it.")
            elif state.get("_corrupt"):
                report.check(f"{binding}.provenance", False, "E_PROVENANCE_JSON",
                             f"{binding}: the provenance record is not valid JSON")
            else:
                recorded = (state.get("runtime") or {}).get("sha256")
                report.check(f"{binding}.provenance", recorded == actual_runtime,
                             "E_PROVENANCE_STALE",
                             f"{binding}: the provenance record describes {recorded}, the file on "
                             f"disk is {actual_runtime}")
                report.check(f"{binding}.provenance_approval",
                             (state.get("approved_reference") or {}).get("matches") is True,
                             "E_PROVENANCE_UNVERIFIED",
                             f"{binding}: the provenance record does not claim a verified match "
                             "against the approved bytes")
    _tree_hygiene(repo, cfg, report)
    _packaging(repo, cfg, report)
    payload = {
        "ok": report.ok,
        "checks": len(report.checks),
        "errors": report.errors,
        "warnings": report.warnings,
        "notes": report.notes,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for item in report.errors:
            print(f"FAIL {item['code']}: {item['message']}")
        for item in report.warnings:
            print(f"WARN {item['code']}: {item['message']}")
        for item in report.notes:
            print(f"note: {item}")
        passed = sum(1 for check in report.checks if check["ok"])
        verdict = "satisfied" if report.ok else "FAILED"
        print(f"validate-models: {verdict} - {passed}/{len(report.checks)} checks, "
              f"{len(report.errors)} failures, {len(report.warnings)} warnings")
    return 0 if report.ok else 1


# --------------------------------------------------------------------------------------------------
# command line


def add_common(parser):
    parser.add_argument("--asset", action="append", metavar="BINDING",
                       help="one binding, e.g. rebel:battleship (repeatable)")
    parser.add_argument("--batch", action="append", metavar="NAME", help="a declared batch")
    parser.add_argument("--all", action="store_true", help="every asset in the registry")
    parser.add_argument("--blender", metavar="PATH", help="Blender executable to use")
    parser.add_argument("--allow-blender-mismatch", action="store_true",
                       help="run a Blender other than the pinned version")
    parser.add_argument("--keep-blend", action="store_true",
                       help="do not restore a regenerated .blend whose runtime bytes are unchanged")
    parser.add_argument("--json", action="store_true", help="machine-readable output")


def build_parser():
    parser = argparse.ArgumentParser(prog="model-pipeline", description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("build-model", "regenerate a script-authoritative asset"),
                            ("export-model", "produce the runtime export without touching the source"),
                            ("validate-models", "validate the registry, the bytes and the tree")):
        sub = subparsers.add_parser(name, help=help_text)
        add_common(sub)
        if name == "validate-models":
            sub.add_argument("--allow-source-drift", action="store_true",
                             help="downgrade a stale approved .blend hash to a warning")
            sub.add_argument("--no-contract", action="store_true",
                             help="skip the S02 contract validator (never for acceptance)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    repo = Path.cwd()
    try:
        cfg = load_pipeline(repo)
    except PipelineError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2 if exc.refused else 1
    if args.command == "validate-models":
        try:
            return validate(repo, cfg, args)
        except PipelineError as exc:
            print(f"{exc.code}: {exc}", file=sys.stderr)
            return 2 if exc.refused else 1
    try:
        chosen = select_assets(cfg, args)
        executable = resolve_blender(args.blender, cfg)
        opts = argparse.Namespace(keep_blend=args.keep_blend, blender_version=None)
        opts.blender_version = blender_version(executable)
        pin = cfg["blender"]["pin"]
        if opts.blender_version != pin and not args.allow_blender_mismatch:
            raise PipelineError(f"Blender {opts.blender_version} at {executable} is not the pinned "
                                f"{pin}; re-export deliberately with --allow-blender-mismatch",
                                "E_BLENDER_MISMATCH", refused=True)
        results = []
        for asset in chosen:
            action = build_asset if args.command == "build-model" else export_asset
            record, payload = action(repo, cfg, asset, executable, opts)
            record_path = write_provenance(repo, cfg, asset, record)
            results.append({"binding": asset["binding"], "runtime": asset["runtime"],
                            "sha256": record["runtime_sha256"],
                            "triangles": record["runtime_triangles"],
                            "provenance": str(record_path.relative_to(repo))})
            print(f"{args.command} {asset['binding']}: ok - {record['runtime_triangles']} triangles, "
                  f"runtime sha256 {record['runtime_sha256'][:16]}... matches the approved bytes")
        if args.json:
            print(json.dumps({"ok": True, "blender": str(executable),
                              "blender_version": opts.blender_version, "results": results},
                             indent=2, ensure_ascii=False))
        return 0
    except PipelineError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2 if exc.refused else 1
    except json.JSONDecodeError as exc:
        print(f"E_PAYLOAD_JSON: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
