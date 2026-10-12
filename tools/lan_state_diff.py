"""Name the exact value that diverges between two machines' simulations.

The lockstep ticksum (`precise_checksum`) is a yes/no answer: it tells you a
mixed-platform pair will desync, not which number is different. This tool dumps
the *same* structure the checksum hashes, on each machine, so the two dumps can
be diffed down to a JSON path and a pair of values.

Run on each machine (same commit, no local mods):

    PYTHONPATH=. python tools/lan_state_diff.py dump --out state-mac.json
    PYTHONPATH=. python tools/lan_state_diff.py dump --out state-win.json --ticks 1

Then compare them anywhere:

    PYTHONPATH=. python tools/lan_state_diff.py diff state-mac.json state-win.json

`--ticks 0` (the default) compares the scene as built, before any simulation
step: a difference there is in construction (trig, ordering, defaults), while a
difference only after N ticks is in the step itself. Exit status: 0 identical,
1 differences found, 2 the comparison could not run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def dump(ticks, out):
    """Write the canonical state exactly as `precise_checksum` sees it."""
    from game.net.diag import lan_scene
    from game.net.lan import canonical_state, precise_checksum
    manager = lan_scene(ticks)
    state = canonical_state(manager)
    payload = dict(ticks=ticks, checksum=precise_checksum(manager), state=state)
    Path(out).write_text(json.dumps(payload, indent=1, sort_keys=True), encoding='utf-8')
    return payload


def _short(value, limit=120):
    text = json.dumps(value, sort_keys=True)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def differences(left, right, path='$', found=None, limit=None):
    """Walk two canonical states and collect (path, left, right) leaves that differ."""
    if found is None:
        found = []
    if limit is not None and len(found) >= limit:
        return found
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left:
                found.append((f'{path}.{key}', '<absent>', right[key]))
            elif key not in right:
                found.append((f'{path}.{key}', left[key], '<absent>'))
            else:
                differences(left[key], right[key], f'{path}.{key}', found, limit)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            found.append((f'{path} (length)', len(left), len(right)))
        for index, (a, b) in enumerate(zip(left, right)):
            differences(a, b, f'{path}[{index}]', found, limit)
    elif isinstance(left, bool) != isinstance(right, bool) or left != right:
        found.append((path, left, right))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Dump or diff the canonical LAN scene state of two machines.')
    sub = parser.add_subparsers(dest='mode', required=True)
    dump_parser = sub.add_parser('dump', help='write this machine\'s canonical state')
    dump_parser.add_argument('--out', required=True)
    dump_parser.add_argument('--ticks', type=int, default=0,
                             help='simulation steps before dumping (default 0: as built)')
    diff_parser = sub.add_parser('diff', help='compare two dumps')
    diff_parser.add_argument('left')
    diff_parser.add_argument('right')
    diff_parser.add_argument('--limit', type=int, default=25,
                             help='stop after this many differing leaves (0 = all)')
    args = parser.parse_args(argv)

    if args.mode == 'dump':
        payload = dump(args.ticks, args.out)
        print(f'dumped {args.out}: ticks={payload["ticks"]} '
              f'checksum={payload["checksum"][:16]}…')
        return 0

    limit = args.limit or None
    try:
        payloads = [json.loads(Path(path).read_text(encoding='utf-8'))
                    for path in (args.left, args.right)]
    except (OSError, json.JSONDecodeError) as exc:
        print(f'lan_state_diff: {exc}', file=sys.stderr)
        return 2
    for path, payload in zip((args.left, args.right), payloads):
        if 'state' not in payload:
            print(f'lan_state_diff: {path} is not a dump (no "state" key)', file=sys.stderr)
            return 2
        print(f'note {path}: ticks={payload.get("ticks")} '
              f'checksum={str(payload.get("checksum"))[:16]}…')
    if payloads[0].get('checksum') == payloads[1].get('checksum'):
        print('IDENTICAL checksums — no divergence to trace')
        return 0
    found = differences(payloads[0]['state'], payloads[1]['state'], limit=limit)
    print(f'mismatch: checksums differ; {len(found)} differing value(s)'
          + (f' shown (limit {limit}); rerun with --limit 0 for all' if limit else ''))
    for path, left, right in found:
        print(f'  {path}\n    left : {_short(left)}\n    right: {_short(right)}')
    return 1


if __name__ == '__main__':                       # pragma: no cover - manual entry
    raise SystemExit(main())
