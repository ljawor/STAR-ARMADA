"""GL-free manifest resolution using only metadata shipped beneath assets/models.

No authoring modules, executable pack content, or gameplay data writers cross this
boundary. Geometry has the immutable authored_mesh role -> (normal, triangle) form.
"""
from collections import OrderedDict, namedtuple
from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import math
import os
import stat
from pathlib import Path
from itertools import islice
from typing import NoReturn

from game import __version__
import re
import sys
from types import MappingProxyType


MAX_BYTES = 2_000_000
CONTRACTS = {f'star-armada/{name}': f'{name}.schema.json'
             for name in ('model-manifest', 'binding-registry', 'visual-pack')}
SUPPORTED_KEYWORDS = {
    'type', 'required', 'additionalProperties', 'properties', 'items', 'enum', 'const',
    'pattern', 'minItems', 'maxItems', 'uniqueItems', 'minProperties', 'minimum',
    'maximum', 'exclusiveMinimum', 'minLength', 'maxLength', '$ref', '$defs', '$schema',
    '$id', 'title', 'description', 'format',
}


class Diagnostics(list):
    """Latest bounded diagnostics; no per-frame accumulation during fallback."""
    def append(self, item):
        super().append(item)
        del self[:-256]


class AssetError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f'{code}: {message}')


def _fail(code, where, why) -> NoReturn:
    raise AssetError(code, f'{where}: {why}')


def _safe(root, relative):
    if (not isinstance(relative, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,180}', relative)
            or any(p in ('', '.', '..') for p in relative.split('/'))):
        _fail('E_UNSAFE_PATH', 'path', repr(relative))
    try:
        root = Path(root).resolve()
        target = (root / relative).resolve()
    except (OSError, RuntimeError) as exc:
        _fail('E_UNSAFE_PATH', 'path', str(exc))
    if not target.is_relative_to(root):
        _fail('E_SYMLINK_ESCAPE', 'path', relative)
    return target


def _pack_files(root):
    """Lazy non-symlink-following walk; unreadable subtrees fail closed."""
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    child = Path(entry.path)
                    yield child
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(child)
        except OSError as exc:
            _fail('E_FILE_MISSING', str(directory), str(exc))


def _read(path):
    try:
        if not stat.S_ISREG(Path(path).stat().st_mode):
            _fail('E_FILE_TYPE', str(path), 'expected a regular data file')
        # Nonblocking open plus fstat also closes a regular-file -> FIFO swap.
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                _fail('E_FILE_TYPE', str(path), 'expected a regular data file')
            raw = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        _fail('E_FILE_MISSING', str(path), str(exc))
    if len(raw) > MAX_BYTES:
        _fail('E_FILE_SIZE', str(path), 'exceeds hard byte ceiling')
    return raw


def _json(raw):
    def constant(value):
        _fail('E_NON_FINITE', 'JSON', value)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail('E_PARSE', 'JSON', f'duplicate key {key}')
            result[key] = value
        return result

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            constant(value)
        return result

    try:
        data = json.loads(raw, parse_constant=constant, parse_float=finite_float, object_pairs_hook=pairs)
    except AssetError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        _fail('E_PARSE', 'JSON', str(exc))
    if not isinstance(data, dict):
        _fail('E_SCHEMA', 'JSON', 'expected object')
    return data


def _paths(data, root):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ('path', 'source'):
                _safe(root, value)
            else:
                _paths(value, root)
    elif isinstance(data, list):
        for value in data:
            _paths(value, root)


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}', value):
        _fail('E_ENGINE_VERSION', 'version', repr(value))
    return tuple(map(int, value.split('.')))



ROLES = ('base', 'dark', 'trim', 'accent', 'lit', 'cool')
MAX_VERTICES = 10_000
MAX_TRIANGLES = 12_000
# Session-retained optional geometry, across all bindings and LODs. This is
# separate from the disposable LRU and prevents many small valid files exhausting RAM.
MAX_PACK_SNAPSHOT_TRIANGLES = 240_000
MAX_PACK_SNAPSHOT_BYTES = 32_000_000


def _snapshot_bytes(manifest):
    return (len(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
            + sum(entry['bytes'] for entry in manifest['files'].values()))


def _snapshot_triangles(snapshot):
    return sum(len(faces) for mesh in snapshot.values() for faces in mesh.values())


def _geometry(payload, manifest, legacy_identifiers=()):
    def bad(why):
        _fail('E_EXPORT_SHAPE', manifest['asset'], why)

    def vec(value):
        return (isinstance(value, list) and len(value) == 3
                and all(_finite_number(x) for x in value))

    export = manifest.get('export', {})
    if 'schema' in payload:
        if type(payload['schema']) is not int or payload['schema'] != 1 or export.get('legacy_schema_int') != 1:
            bad('unsupported legacy schema')
        if payload.get('asset') not in legacy_identifiers:
            bad('legacy payload identifier is not an alias of the manifest asset')
    elif (payload.get('contract') != 'star-armada/mesh-export'
          or type(payload.get('contract_major')) is not int or payload['contract_major'] != 1):
        bad('unsupported mesh contract')
    if not isinstance(payload.get('asset'), str) or not payload['asset']:
        bad('missing payload asset identity')
    if 'schema' not in payload and payload['asset'] != manifest['asset']:
        bad('payload asset identity differs from manifest')
    vertices, batches = payload.get('vertices'), payload.get('batches')
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= MAX_VERTICES or not all(map(vec, vertices)):
        bad('finite vertex array / vertex budget')
    if (not isinstance(batches, dict) or set(batches) != set(manifest['roles'])
            or not set(batches).issubset(ROLES)):
        bad('material roles differ')
    vertices = tuple(tuple(point) for point in vertices)
    bounds = [list(min(p[i] for p in vertices) for i in range(3)),
              list(max(p[i] for p in vertices) for i in range(3))]
    if payload.get('bounds') != bounds:
        bad('payload bounds do not match measured vertices')
    envelope = manifest['bounds']
    if any(bounds[0][i] < envelope['min'][i] or bounds[1][i] > envelope['max'][i] for i in range(3)):
        _fail('E_BOUNDS_MISMATCH', manifest['asset'], 'mesh exceeds manifest envelope')
    total = 0
    result = {}
    for role in ROLES:
        faces = batches.get(role, [])
        if not isinstance(faces, list) or (role in batches and not faces):
            bad('empty or invalid declared role')
        total += len(faces)
        if total > min(MAX_TRIANGLES, manifest.get('requires', {}).get('max_triangles', MAX_TRIANGLES)):
            bad('triangle budget')
        triangles = []
        for face in faces:
            if not isinstance(face, list) or len(face) != 6 or not vec(face[:3]):
                bad('face must be [nx,ny,nz,i0,i1,i2]')
            normal = tuple(face[:3])
            if abs(sum(c*c for c in normal) - 1) > 1e-8:
                bad('normal must be unit length')
            indices = face[3:]
            if any(type(i) is not int or not 0 <= i < len(vertices) for i in indices):
                bad('index out of range or not integer')
            tri = tuple(vertices[i] for i in indices)
            a, b, c = tri
            u = tuple(b[i]-a[i] for i in range(3))
            v = tuple(c[i]-a[i] for i in range(3))
            cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            area = math.sqrt(sum(x*x for x in cross))
            if not math.isfinite(area) or area <= 1e-9 or sum(n*x for n, x in zip(normal, cross)) / area < 1 - 1e-8:
                bad('degenerate, reversed or incorrectly shaded face')
            triangles.append((normal, tri))
        result[role] = tuple(triangles)
    if type(payload.get('triangle_count')) is not int or payload['triangle_count'] != total:
        bad('triangle count mismatch')
    return MappingProxyType(result)


@dataclass(frozen=True)
class ResolvedAsset:
    mesh: object = field(repr=False)
    revision: str
    asset: str
    material_profile: str
    source: str
    pack_id: str | None = None
    pack_revision: str = ''
    lod: str = 'mesh'


class AssetResolver:
    def __init__(self, asset_root=None, *, registry_path=None, max_cache_entries=64,
                 gameplay_entities=None, engine_version=None):
        if type(max_cache_entries) is not int or not 0 <= max_cache_entries <= 4096:
            _fail('E_CACHE_LIMIT', 'max_cache_entries', 'must be an integer in 0..4096')
        self._gameplay_entities = gameplay_entities or {}
        self._max_cache_entries = max_cache_entries
        self._cache = OrderedDict()
        self._failed = OrderedDict()
        self._hits = self._misses = 0
        self.diagnostics = Diagnostics()
        self.root = Path(asset_root) if asset_root is not None else Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        self.engine_version = _version(engine_version or __version__)
        self._schemas = {name: _json(_read(_safe(self.root, f'assets/models/schemas/{file}')))
                         for name, file in CONTRACTS.items()}
        self.root = self.root.resolve()
        registry = Path(registry_path) if registry_path else self.root / 'assets/models/registry.json'
        if not registry.is_absolute():
            registry = self.root / registry
        try:
            relative = registry.relative_to(self.root).as_posix()
        except ValueError:
            _fail('E_UNSAFE_PATH', 'registry_path', 'must be inside asset_root')
        registry = _safe(self.root, relative)
        data = _json(_read(registry))
        self._document(data, self.root, 'star-armada/binding-registry')
        self._bindings = {}
        self._aliases = {}
        for row in data['bindings']:
            key = row['binding']
            if key in self._bindings:
                _fail('E_DUPLICATE_BINDING', key, 'duplicate registry binding')
            self._bindings[key] = row
        for row in data['bindings']:
            for alias in row.get('legacy_identifiers', []):
                if alias in self._aliases or alias in self._bindings:
                    _fail('E_DUPLICATE_BINDING', alias, 'ambiguous legacy identifier')
                self._aliases[alias] = row['binding']
        self._manifests = {}
        self._overrides = {}
        self.active_order = ()
        manifest_paths = list(islice((self.root / 'assets/models/manifests').glob('*.json'), 513))
        if len(manifest_paths) > 512:
            _fail('E_FILE_SIZE', 'core manifests', 'manifest count exceeds 512')
        for path in sorted(manifest_paths):
            try:
                data = _json(_read(_safe(self.root, path.relative_to(self.root).as_posix())))
                if not isinstance(data.get('asset'), str):
                    if 'contract' in data:
                        self._document(data, self.root, 'star-armada/model-manifest')
                    _fail('E_SCHEMA', str(path), 'missing asset identity')
                if data['asset'] in self._manifests:
                    _fail('E_DUPLICATE_ID', data['asset'], 'ambiguous core manifest identity')
                self._manifests[data['asset']] = data
            except AssetError as exc:
                if exc.code == 'E_DUPLICATE_ID':
                    raise
                self.diagnostics.append({'code': exc.code, 'message': str(exc), 'path': str(path)})

    def _document(self, data, root, contract):
        if (data.get('contract') != contract or type(data.get('contract_major')) is not int
                or data['contract_major'] != 1):
            _fail('E_UNKNOWN_CONTRACT', contract, 'unsupported contract id or major')
        export = data.get('export')
        if isinstance(export, dict) and (export.get('contract') != 'star-armada/mesh-export'
                or type(export.get('contract_major')) is not int or export['contract_major'] != 1):
            _fail('E_UNKNOWN_CONTRACT', 'export', 'unsupported format')
        _paths(data, root)
        if contract == 'star-armada/visual-pack' and isinstance(data.get('content'), dict):
            for entries in data['content'].values():
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict) and 'manifest' in entry:
                            _safe(root, entry['manifest'])
        schema = self._schemas[contract]
        check_schema(data, schema, contract, schema)
        requires = data.get('requires', {})
        if 'min_engine' in requires and _version(requires['min_engine']) > self.engine_version:
            _fail('E_ENGINE_VERSION', contract, 'requires a newer engine')
        if contract == 'star-armada/visual-pack':
            supported = {name + '/v1' for name in CONTRACTS} | {'star-armada/mesh-export/v1'}
            for required in requires['contracts']:
                if required not in supported:
                    _fail('E_UNKNOWN_CONTRACT', 'requires.contracts', required)
            if data['content'].get('material_profiles'):
                _fail('E_MATERIAL_PROFILE', 'content', 'pack-supplied material profiles are not implemented')
        if contract == 'star-armada/model-manifest':
            export = data.get('export', {})
            if export and (export.get('contract') != 'star-armada/mesh-export'
                           or type(export.get('contract_major')) is not int or export['contract_major'] != 1):
                _fail('E_UNKNOWN_CONTRACT', 'export', 'unsupported format')
            profile = requires.get('material_profile', 'core:fleet/standard')
            if profile != 'core:fleet/standard':
                _fail('E_MATERIAL_PROFILE', 'requires', profile)
            lo, hi = data['bounds']['min'], data['bounds']['max']
            if any(a >= b for a, b in zip(lo, hi)):
                _fail('E_BOUNDS_DEGENERATE', 'bounds', 'non-positive axis')

    def _load(self, manifest, root, lod, *, pack_id=None, pack_revision='', envelope=None,
              snapshot=None):
        self._document(manifest, root, 'star-armada/model-manifest')
        body = '\n'.join(f"{key}:{manifest['files'][key]['sha256']}" for key in sorted(manifest['files']))
        revision = hashlib.sha256(f"{manifest['asset']}\n{body}".encode()).hexdigest()
        if revision != manifest['revision']:
            _fail('E_REVISION_MISMATCH', 'revision', 'content revision differs')
        meshes = {}
        for level, entry in manifest['files'].items():
            path = _safe(root, entry['path'])
            raw = _read(path)
            if len(raw) != entry['bytes']:
                _fail('E_FILE_SIZE', entry['path'], 'declared size differs')
            if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                _fail('E_FILE_HASH', entry['path'], 'sha256 differs')
            payload = _json(raw)
            aliases = {alias for row in self._bindings.values() if row['manifest'] == manifest['asset']
                       for alias in row.get('legacy_identifiers', [])}
            meshes[level] = _geometry(payload, manifest, aliases)
            if envelope is not None:
                lo, hi = payload['bounds']
                if any(lo[i] < envelope['min'][i] or hi[i] > envelope['max'][i] for i in range(3)):
                    _fail('E_EXTENT_DRIFT', manifest['asset'], 'replacement exceeds approved binding envelope')
            if manifest.get('budgets', {}).get('triangles', 12000) < payload['triangle_count']:
                _fail('E_MEASUREMENT_STALE', 'budgets.triangles', 'below mesh count')
        approval = manifest.get('approval', {})
        if approval.get('status') == 'approved' and approval.get('reviewed_revision') != revision:
            _fail('E_APPROVAL_STALE', 'approval', 'reviewed revision differs')
        self._approval(manifest, root)
        if lod not in meshes:
            _fail('E_LOD', 'lod', lod)
        if snapshot is not None:
            snapshot.update(meshes)
        return ResolvedAsset(meshes[lod], revision, manifest['asset'],
                             manifest.get('requires', {}).get('material_profile', 'core:fleet/standard'),
                             'core' if pack_id is None else str(root), pack_id, pack_revision, lod)

    def _approval(self, manifest, root):
        """Verify a packaged receipt, never open repository-only art/evidence paths.

        The receipt pins the entire manifest (including tool/material metadata),
        revision, decision, and evidence identities/hashes. It is a reproducible
        release attestation, NOT a signature or a new owner approval. Source-tree
        tests verify evidence hashes when preparing the bundle. Packs declaring
        approval must likewise ship their own receipt at this fixed location.
        """
        approval = manifest.get('approval', {})
        if approval.get('status') != 'approved':
            return
        evidence = approval.get('reviewed_evidence')
        if not approval.get('decision_id') or not approval.get('decided_by') or not evidence:
            _fail('E_EVIDENCE_MISSING', 'approval', 'missing decision, reviewer or evidence')
        try:
            date.fromisoformat(approval.get('decided_on', ''))
        except ValueError:
            _fail('E_APPROVAL_STALE', 'approval', 'invalid review date')
        for relative in evidence:
            _safe(root, relative)
        try:
            receipts = _json(_read(_safe(root, 'assets/models/approval-receipts.json')))
        except AssetError as exc:
            _fail('E_EVIDENCE_MISSING', 'approval receipt', str(exc))
        if (receipts.get('contract') != 'star-armada/approval-receipts'
                or type(receipts.get('contract_major')) is not int or receipts['contract_major'] != 1
                or not isinstance(receipts.get('receipts'), dict)):
            _fail('E_EVIDENCE_MISSING', 'approval receipt', 'unsupported receipt format')
        receipt = receipts['receipts'].get(manifest['asset'])
        if not isinstance(receipt, dict):
            _fail('E_EVIDENCE_MISSING', 'approval receipt', 'asset has no packaged receipt')
        canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
        if (receipt.get('manifest_sha256') != hashlib.sha256(canonical).hexdigest()
                or receipt.get('reviewed_revision') != manifest['revision']
                or receipt.get('decision_id') != approval['decision_id']):
            _fail('E_APPROVAL_STALE', 'approval receipt', 'manifest metadata or revision changed')
        hashes = receipt.get('evidence_sha256')
        if (not isinstance(hashes, dict) or set(hashes) != set(evidence)
                or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in hashes.values())):
            _fail('E_EVIDENCE_MISSING', 'approval receipt', 'evidence identities or hashes missing')

    def cache_clear(self):
        self._cache.clear()
        self._failed.clear()
        self._hits = self._misses = 0

    def cache_info(self):
        return namedtuple('CacheInfo', 'hits misses maxsize currsize')(
            self._hits, self._misses, self._max_cache_entries, len(self._cache))

    def has_binding(self, binding):
        return isinstance(binding, str) and (binding in self._bindings or binding in self._overrides or binding in self._aliases)

    def is_authored(self, binding):
        return self.resolve(binding) is not None

    def cache_key(self, binding):
        asset = self.resolve(binding)
        return None if asset is None else (asset.revision, asset.pack_revision, asset.material_profile, asset.lod)

    def _core_manifest(self, binding):
        row = self._bindings[binding]
        manifest = self._manifests.get(row['manifest'])
        if manifest is None:
            _fail('E_MANIFEST_UNRESOLVED', binding, row['manifest'])
        self._document(manifest, self.root, 'star-armada/model-manifest')
        envelope = row.get('envelope')
        if envelope is not None:
            if any(a >= b for a, b in zip(envelope['min'], envelope['max'])):
                _fail('E_BOUNDS_DEGENERATE', binding, 'invalid binding envelope')
            grace = [min(.01 * (b-a), 2) for a, b in zip(envelope['min'], envelope['max'])]
            bounds = manifest['bounds']
            if any(bounds['min'][i] < envelope['min'][i] - grace[i]
                   or bounds['max'][i] > envelope['max'][i] + grace[i] for i in range(3)):
                _fail('E_EXTENT_DRIFT', binding, 'core manifest exceeds approved envelope grace')
        decision = row.get('envelope_decision')
        if decision and decision != manifest.get('approval', {}).get('decision_id'):
            _fail('E_EXTENT_DRIFT', binding, 'envelope decision differs from manifest approval')
        return manifest

    def coverage(self, *, full=False):
        """Report broken required core separately; an override cannot hide it.

        The default is a *structural* verdict: manifest document and revision, plus every
        declared payload read, size-checked and hashed. That is what a session boundary can
        afford — parsing all 103 payloads costs about a second, which is a session-start
        regression, not a check. `full=True` also runs each payload through the real `_load`
        path (JSON parse, identifiers, envelope, budgets) and belongs in acceptance tooling,
        not in startup or a draw path.
        """
        failures, authored = [], []
        for key, row in self._bindings.items():
            if row.get('status') == 'core':
                try:
                    manifest = self._core_manifest(key)
                    body = '\n'.join(f"{name}:{manifest['files'][name]['sha256']}"
                                      for name in sorted(manifest['files']))
                    revision = hashlib.sha256(f"{manifest['asset']}\n{body}".encode()).hexdigest()
                    if revision != manifest['revision']:
                        _fail('E_REVISION_MISMATCH', key, 'content revision differs')
                    for level, entry in manifest['files'].items():
                        # Bytes are read and hashed: cheap next to parsing them, and it is the
                        # only way a structural verdict notices corruption rather than absence.
                        try:
                            raw = _read(_safe(self.root, entry['path']))
                        except (OSError, AssetError):
                            _fail('E_FILE_SIZE', entry['path'], 'declared payload is missing')
                        if len(raw) != entry['bytes']:
                            _fail('E_FILE_SIZE', entry['path'], 'declared size differs')
                        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                            _fail('E_FILE_HASH', entry['path'], 'sha256 differs')
                    if full:
                        self._load(manifest, self.root, 'mesh')
                    authored.append(key)
                except AssetError as exc:
                    failures.append(key)
                    self.diagnostics.append({'binding': key, 'code': exc.code, 'message': str(exc), 'source': 'core'})
        return {'ok': not failures, 'required_core_failures': tuple(failures),
                'authored': tuple(authored),
                'procedural': tuple(k for k, r in self._bindings.items() if r.get('status') != 'core'),
                'active_order': self.active_order}

    def pack_bindings(self):
        """Effective optional origins only; bounded by enabled pack/entry ceilings.

        Fresh metadata copies avoid disk I/O, core catalogue loading and exposing
        the resolver's mutable internal manifest/staging records to callers.
        """
        return [{'binding': key, 'asset': manifest['asset'], 'source': str(root),
                 'pack_id': identity, 'pack_revision': revision}
                for key, (manifest, root, identity, revision, _, _) in sorted(self._overrides.items())]

    def activate_packs(self, pack_paths, *, gameplay_entities=None, pack_root=None):
        """Reset to core, then validate/activate each pack atomically in caller order.

        Return accepted pack ids. active_order and the I_PACK_ORDER diagnostic
        include every requested path, including failed and duplicate entries.
        """
        pack_paths = list(islice(iter(pack_paths), 33))
        if len(pack_paths) > 32:
            _fail('E_PACK_LIMIT', 'enabled packs', 'maximum 32')
        self._overrides = {}
        fixtures = self._gameplay_entities if gameplay_entities is None else gameplay_entities
        self.cache_clear()
        order, ids, paths = [], set(), set()
        for requested in pack_paths:
            path = Path(requested).absolute()
            outcome = {'path': str(path), 'accepted': False, 'code': None}
            try:
                try:
                    canonical = path.resolve()
                except (OSError, RuntimeError) as exc:
                    _fail('E_UNSAFE_PATH', str(path), str(exc))
                if pack_root is not None and not canonical.is_relative_to(Path(pack_root).resolve()):
                    _fail('E_SYMLINK_ESCAPE', str(path), 'enabled directory escapes external pack root')
                if getattr(sys, 'frozen', False) and canonical.is_relative_to(self.root):
                    _fail('E_UNSAFE_PATH', str(path), 'visual packs must be outside the frozen bundle')
                if canonical in paths:
                    _fail('E_DUPLICATE_ID', str(path), 'duplicate enabled pack path')
                paths.add(canonical)
                root = path.parent.resolve()
                data = _json(_read(_safe(root, path.name)))
                self._document(data, root, 'star-armada/visual-pack')
                prohibited = {'.py', '.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib', '.exe',
                              '.blend', '.pickle', '.pkl', '.glsl', '.vert', '.frag', '.sh',
                              '.bat', '.cmd', '.js', '.wasm'}
                for index, child in enumerate(_pack_files(root)):
                    if index >= 4096:
                        _fail('E_FILE_SIZE', str(root), 'pack file-count limit exceeded')
                    target = _safe(root, child.relative_to(root).as_posix())
                    if not (target.is_file() or target.is_dir()):
                        _fail('E_FILE_TYPE', str(child), 'expected a regular file or directory')
                    if child.suffix.lower() in prohibited:
                        _fail('E_EXECUTABLE_CONTENT', str(child), 'not a data-only visual pack')
                if data['id'] in ids:
                    _fail('E_DUPLICATE_ID', data['id'], 'duplicate enabled pack id')
                staged = {}
                staged_triangles = staged_bytes = 0
                active_triangles = sum(_snapshot_triangles(item[-1]) for item in self._overrides.values())
                active_bytes = sum(_snapshot_bytes(item[0]) for item in self._overrides.values())
                asset_ids = set()
                digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode())
                for kind in ('replaces', 'adds'):
                    for entry in data['content'].get(kind, []):
                        key = entry['binding']
                        if key in staged:
                            _fail('E_DUPLICATE_ID', key, 'duplicate binding inside pack')
                        if kind == 'replaces' and key not in self._bindings:
                            _fail('E_UNKNOWN_BINDING', key, 'replacement is not a core binding')
                        if kind == 'adds':
                            if key in self._bindings:
                                _fail('E_ASSET_COLLISION', key, 'addition collides with core binding')
                            if key in self._overrides:
                                _fail('E_DUPLICATE_BINDING', key, 'addition already supplied by an enabled pack')
                            source = data['requires'].get('gameplay_mod')
                            if not source or entry.get('entity_source') != source or source not in fixtures:
                                _fail('E_MISSING_GAMEPLAY_MOD', key, 'gameplay dependency is not active or differs')
                            if key not in fixtures[source]:
                                _fail('E_GAMEPLAY_ENTITY', key, 'gameplay fixture does not define this binding')
                            row = {}
                        else:
                            row = self._bindings[key]
                        if kind == 'replaces' and entry.get('replace_of', row['manifest']) != row['manifest']:
                            _fail('E_ASSET_COLLISION', key, 'replace_of differs from core asset identity')
                        manifest_path = _safe(root, entry['manifest'])
                        manifest = _json(_read(manifest_path))
                        self._document(manifest, root, 'star-armada/model-manifest')
                        envelope = row.get('envelope')
                        if kind == 'replaces' and envelope is None:
                            _fail('E_EXTENT_DRIFT', key, 'core binding has no approved replacement envelope')
                        if kind == 'adds' and manifest.get('asset') in {r['manifest'] for r in self._bindings.values()}:
                            _fail('E_ASSET_COLLISION', key, 'additive asset id collides with core')
                        if kind == 'adds' and manifest.get('asset') in {
                                m['asset'] for m, *_ in self._overrides.values()}:
                            _fail('E_ASSET_COLLISION', key, 'additive asset id already supplied by an enabled pack')
                        snapshot = {}
                        self._load(manifest, root, 'mesh', pack_id=data['id'], envelope=envelope,
                                   snapshot=snapshot)
                        if manifest['asset'] in asset_ids:
                            _fail('E_DUPLICATE_ID', manifest['asset'], 'duplicate asset identity inside pack')
                        asset_ids.add(manifest['asset'])
                        digest.update(key.encode())
                        digest.update(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
                        staged_triangles += _snapshot_triangles(snapshot)
                        staged_bytes += _snapshot_bytes(manifest)
                        if key in self._overrides:
                            active_triangles -= _snapshot_triangles(self._overrides[key][-1])
                            active_bytes -= _snapshot_bytes(self._overrides[key][0])
                        if (active_triangles + staged_triangles > MAX_PACK_SNAPSHOT_TRIANGLES
                                or active_bytes + staged_bytes > MAX_PACK_SNAPSHOT_BYTES):
                            _fail('E_PACK_RESOURCE', data['id'], 'session snapshot byte/triangle ceiling exceeded')
                        staged[key] = (manifest, root, data['id'], '', envelope, MappingProxyType(snapshot))
                revision = digest.hexdigest()
                staged = {key: (m, r, identity, revision, envelope, snapshot)
                          for key, (m, r, identity, _, envelope, snapshot) in staged.items()}
                for key, item in staged.items():
                    if key in self._overrides:
                        previous = self._overrides[key]
                        self.diagnostics.append({'code': 'I_BINDING_OVERRIDE', 'binding': key,
                                                 'previous_pack_id': previous[2],
                                                 'previous_pack_revision': previous[3],
                                                 'pack_id': data['id'], 'pack_revision': revision,
                                                 'source': str(item[1])})
                self._overrides.update(staged)
                ids.add(data['id'])
                outcome.update(accepted=True, pack_id=data['id'], revision=revision)
            except AssetError as exc:
                outcome.update(code=exc.code, message=str(exc))
                self.diagnostics.append(dict(outcome))
            order.append(MappingProxyType(outcome))
        self.active_order = tuple(order)
        self.diagnostics.append({'code': 'I_PACK_ORDER', 'active_order': self.active_order})
        return tuple(item['pack_id'] for item in order if item['accepted'])

    def resolve(self, binding, *, lod='mesh'):
        binding = self._aliases.get(binding, binding)
        if binding not in self._bindings and binding not in self._overrides:
            _fail('E_UNKNOWN_BINDING', str(binding), 'not in registry or active gameplay fixture')
        failure_key = (binding, lod)
        if failure_key in self._failed:
            self._failed.move_to_end(failure_key)
            return None
        row = self._bindings.get(binding)
        if binding in self._overrides:
            manifest, root, pack_id, pack_revision, envelope, snapshot = self._overrides[binding]
        elif row.get('status') == 'core':
            manifest, root, pack_id, pack_revision, envelope = self._manifests.get(row['manifest']), self.root, None, '', None
        else:
            return None
        try:
            if pack_id is None:
                manifest = self._core_manifest(binding)
            # Optional packs are session snapshots: never mix cached old entries
            # with disk changes after transactional activation (including other LODs).
            key = (manifest['revision'], pack_revision, manifest.get('requires', {}).get('material_profile', 'core:fleet/standard'), lod)
            if key in self._cache:
                self._hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]
            self._misses += 1
            if pack_id is None:
                result = self._load(manifest, root, lod)
            else:
                if lod not in snapshot:
                    _fail('E_LOD', 'lod', lod)
                result = ResolvedAsset(snapshot[lod], manifest['revision'], manifest['asset'],
                                       key[2], str(root), pack_id, pack_revision, lod)
            if self._max_cache_entries:
                self._cache[key] = result
                while len(self._cache) > self._max_cache_entries:
                    self._cache.popitem(last=False)
            return result
        except AssetError as exc:
            self.diagnostics.append({'binding': binding, 'code': exc.code, 'message': str(exc)})
            if self._max_cache_entries:
                self._failed[failure_key] = exc.code
                while len(self._failed) > self._max_cache_entries:
                    self._failed.popitem(last=False)
            return None


# Stdlib schema subset mirrored from the authoring contract validator.
def check_schema(node, schema: dict, where: str, root_schema: dict) -> None:
    """Evaluate the documented subset. Raises AssetError('E_SCHEMA', ...) on violation."""
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
        if not _finite_number(node):
            _fail("E_SCHEMA", where, "number must be finite and float-representable")
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
