#!/usr/bin/env python3
"""Build/test the mandatory renderer, then enumerate a fail-closed frozen payload.

Requires CMake >=3.25, a C++20 toolchain and PyInstaller (dependency inspection).
An existing CMake cache is deliberately reused: no generator/prefix overrides.
No GPU, application window, or release publication is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SHADERS = tuple(f'{stage}_{kind}.bin' for kind in (
    'fleet', 'shadow', 'ui', 'top_hud', 'planet', 'mark', 'fog', 'shield', 'star'
) for stage in ('vs', 'fs'))


def product_names(platform):
    if platform == 'win32':
        return 'armada_viewer.exe', 'armada_embedded.dll'
    if platform == 'darwin':
        return 'armada_viewer', 'libarmada_embedded.dylib'
    raise RuntimeError(f'Unsupported native release platform: {platform}')


def require_file(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f'Missing native payload (or empty file): {path}')
    return path


def build_commands(root, build_dir, jobs=2):
    configure = ['cmake', '-S', str(Path(root) / 'render_cpp'), '-B', str(build_dir),
                 '-DCMAKE_BUILD_TYPE=Release']
    if not (Path(build_dir) / 'CMakeCache.txt').exists():
        # Fresh CI must use the pinned FetchContent SDL, not whatever happens
        # to be installed on a moving runner image. Preserve existing caches.
        configure.append('-DCMAKE_DISABLE_FIND_PACKAGE_SDL3=ON')
    return [
        configure,
        ['cmake', '--build', str(build_dir), '--config', 'Release', '--parallel', str(jobs)],
        ['ctest', '--test-dir', str(build_dir), '-C', 'Release', '--output-on-failure',
         '--no-tests=error', '--timeout', '60'],
    ]


def stage_products(build_dir, platform):
    """Visual Studio emits Release/*.exe/dll; runtime expects build-w02/*.

    Prefer Release products even when an older staged copy exists. Shaders are
    configuration-independent CMake outputs already under build-w02/shaders.
    """
    build_dir = Path(build_dir)
    for name in product_names(platform):
        source = build_dir / 'Release' / name
        if source.is_file():
            shutil.copy2(require_file(source), build_dir / name)
        require_file(build_dir / name)


def native_payload(build_dir, platform=None, *, imports=None):
    """Return explicit (source, frozen directory) entries, including transitive deps.

    Use PyInstaller's platform-aware binary inspector and system-library policy,
    but unlike its warning-only default reject unresolved non-system libraries.
    Injecting the inspector allows GPU-free tests with actual temporary files.
    """
    platform = platform or sys.platform
    build_dir = Path(build_dir).resolve()
    queue = [require_file(build_dir / name) for name in product_names(platform)]
    data = [(str(require_file(build_dir / 'shaders' / name)), 'cpp/shaders') for name in SHADERS]
    if imports is None:
        from PyInstaller.depend import bindepend, dylib
        include = dylib.include_library
        search = [str(build_dir), str(build_dir / 'Release')]
        imports = lambda path: bindepend.get_imports(str(path), search_paths=search)
    else:
        include = lambda path: True
    found = {}
    while queue:
        path = require_file(queue.pop(0)).resolve()
        key = path.name.casefold()
        if key in found:
            if found[key] != path:
                raise RuntimeError(f'Native dependency basename collision: {found[key]} and {path}')
            continue
        found[key] = path
        for name, resolved in sorted(imports(path)):
            if not resolved:
                if include(name):
                    raise RuntimeError(f'Unresolved native dependency {name} required by {path}')
                continue
            if include(resolved):
                queue.append(require_file(resolved))
    return [(str(path), 'cpp') for path in found.values()], data


def write_manifest(build_dir, binaries, data, platform):
    manifest = {
        'schema': 1, 'platform': platform, 'configuration': 'Release',
        'binaries': [Path(path).name for path, _ in binaries],
        'shaders': {Path(path).name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                    for path, _ in data},
    }
    path = Path(build_dir) / 'native-release.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return path


def validate_frozen(bundle_root, platform=None):
    """Validate the actual _MEIPASS tree (macOS Contents/Frameworks or _internal)."""
    platform = platform or sys.platform
    root = Path(bundle_root) / 'cpp'
    manifest = json.loads(require_file(root / 'native-release.json').read_text(encoding='utf-8'))
    if (manifest.get('schema') != 1 or manifest.get('platform') != platform
            or manifest.get('configuration') != 'Release'):
        raise RuntimeError('Invalid native release manifest platform/configuration')
    names = manifest.get('binaries', [])
    if not set(product_names(platform)).issubset(names):
        raise RuntimeError('Missing native products from manifest')
    for name in names:
        if Path(name).name != name:
            raise RuntimeError('Invalid native dependency manifest path')
        require_file(root / name)
    if set(manifest.get('shaders', {})) != set(SHADERS):
        raise RuntimeError('Missing native shader manifest entries')
    for name, expected in manifest['shaders'].items():
        path = require_file(root / 'shaders' / name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Native shader checksum mismatch: {path}')
    print(f'NATIVE_PAYLOAD_OK platform={platform} binaries={len(names)} shaders={len(SHADERS)}', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=Path('render_cpp/build-w02'))
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--validate-frozen', type=Path, metavar='MEIPASS_ROOT')
    args = parser.parse_args(argv)
    if args.validate_frozen:
        validate_frozen(args.validate_frozen)
        return 0
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    build_dir = args.build_dir.resolve()
    for command in build_commands(ROOT, build_dir, args.jobs):
        print('+ ' + subprocess.list2cmdline(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    stage_products(build_dir, sys.platform)
    binaries, data = native_payload(build_dir)
    manifest = write_manifest(build_dir, binaries, data, sys.platform)
    print(f'NATIVE_BUILD_OK binaries={len(binaries)} shaders={len(data)} manifest={manifest}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
