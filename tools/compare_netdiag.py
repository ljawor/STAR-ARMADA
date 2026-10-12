"""Diff two `--netdiag info` reports from two different machines.

Run: PYTHONPATH=. .venv/bin/python tools/compare_netdiag.py MAC.json WIN.json

Answers the only question that matters for a LAN pair: can these two machines
play the same match? It compares the handshake identity (version, protocol,
content hash — issue #56's failure), the deterministic scene fingerprint (a pair
whose ticks checksum differently desyncs after connecting), and, when the
fingerprint differs, the first divergent tick and the differing state components
so the divergence can be localized instead of guessed at.

Exit status: 0 both machines agree, 1 a clause differs, 2 the comparison itself
could not run (missing file, not a netdiag report).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CLAUSES = ('identity', 'simulation')


def _load(path):
    text = Path(path).read_text(encoding='utf-8')
    report = json.loads(text)
    if not isinstance(report, dict) or report.get('tool') != 'netdiag':
        raise ValueError(f'{path} is not a --netdiag report (tool={report.get("tool")!r})')
    return report


def _first_divergent_tick(left, right):
    """Compare two per-tick timelines by tick, not by position."""
    ticks = {entry['tick']: entry['checksum'] for entry in left}
    other = {entry['tick']: entry['checksum'] for entry in right}
    shared = sorted(set(ticks) & set(other))
    for tick in shared:
        if ticks[tick] != other[tick]:
            return tick, len(shared)
    return None, len(shared)


def divergent_components(left, right):
    """Top-level state keys whose digests differ, or None if a report predates them."""
    left_keys, right_keys = left.get('components'), right.get('components')
    if not left_keys or not right_keys:
        return None
    keys = sorted(set(left_keys) | set(right_keys))
    return [key for key in keys if left_keys.get(key) != right_keys.get(key)]


def compare(mac, win, mac_label='machine-a', win_label='machine-b'):
    """Return (ok, lines). Every line is either OK / FAIL / note."""
    lines = []
    ok = True

    for label, report in ((mac_label, mac), (win_label, win)):
        env = report.get('environment') or {}
        lines.append(f'note {label}: {env.get("os_name")} {env.get("os_release")} '
                     f'({env.get("machine")}) / python {env.get("python")}')

    # 1. Handshake identity — the clause that decided issue #56.
    for key, label in (('game_version', 'game_version'),
                       ('protocol_version', 'protocol_version')):
        left = mac.get('environment', {}).get(key)
        right = win.get('environment', {}).get(key)
        if left is None or right is None:
            ok = False
            lines.append(f'FAIL {label}: missing from a report ({left!r} vs {right!r})')
        elif left != right:
            ok = False
            lines.append(f'FAIL {label}: {mac_label} {left!r} != {win_label} {right!r} — '
                         'install the same release on both machines')
        else:
            lines.append(f'OK   {label} {left!r}')

    left = mac.get('environment', {}).get('content_hash')
    right = win.get('environment', {}).get('content_hash')
    if left is None or right is None:
        ok = False
        lines.append(f'FAIL content_hash: missing from a report ({left!r} vs {right!r})')
    elif left != right:
        ok = False
        lines.append(f'FAIL content_hash: {mac_label} {left[:16]}… != {win_label} '
                     f'{right[:16]}… — the host will reject the join with "content '
                     'mismatch"; the game data is not byte-identical (mods installed on '
                     'one side, or a platform-dependent read)')
    else:
        lines.append(f'OK   content_hash {left[:16]}… — the handshake accepts this pair')

    # 2. Simulation identity — a matching handshake still desyncs if this differs.
    left = mac.get('sim_fingerprint') or {}
    right = win.get('sim_fingerprint') or {}
    for label, fp in ((mac_label, left), (win_label, right)):
        if fp.get('error'):
            ok = False
            lines.append(f'FAIL simulation fingerprint on {label}: {fp["error"]}')
    left_sum, right_sum = left.get('checksum'), right.get('checksum')
    left_ticks, right_ticks = left.get('timeline') or [], right.get('timeline') or []
    tick = shared = None
    compared_ticks = bool(left_ticks and right_ticks)
    if compared_ticks:
        tick, shared = _first_divergent_tick(left_ticks, right_ticks)
    if not left_sum or not right_sum:
        ok = False
        lines.append(f'FAIL simulation fingerprint: missing ({left_sum!r} vs {right_sum!r})')
    elif left_sum == right_sum and tick is None:
        lines.append(f'OK   simulation fingerprint {left_sum[:16]}… over '
                     f'{left.get("ticks")} ticks — both machines advance the scene identically')
    else:
        ok = False
        if left_sum != right_sum:
            lines.append(f'FAIL simulation fingerprint: {mac_label} {left_sum[:16]}… != '
                         f'{win_label} {right_sum[:16]}… — the handshake will succeed but the '
                         'lockstep checksum comparison desyncs the match')
        else:
            # A mid-scene divergence that happens to end on the same value is still a
            # desync: lockstep compares every tick, not only the last one.
            lines.append(f'FAIL simulation fingerprint: the final checksums agree '
                         f'({left_sum[:16]}…) but the per-tick timeline diverges at tick '
                         f'{tick} of {shared} — the scene is not identical every tick, so '
                         'lockstep desyncs the match before that point')
        if not compared_ticks:
            lines.append('note one report carries no per-tick timeline — rerun '
                         '"--netdiag info" on both machines to localize the divergence')
        elif tick is None:
            lines.append(f'note no divergent tick among the {shared} ticks both reports '
                         'list — the timelines disagree about the scene they measured')
        else:
            lines.append(f'note first divergent tick: {tick} of {shared} compared ticks')
        components = divergent_components(left, right)
        if components is None:
            lines.append('note no per-component digests in these reports (older report?)')
        elif components:
            lines.append('note differing state components: ' + ', '.join(components))
        else:
            lines.append('note no per-component difference (digests agree) — the difference '
                         'is inside a component this report does not break down further')

    # 3. Informational: what each machine can be dialed at.
    for label, report in ((mac_label, mac), (win_label, win)):
        addresses = report.get('addresses') or {}
        dialable = addresses.get('dialable') if isinstance(addresses, dict) else addresses
        lines.append(f'note {label} dialable at: {", ".join(dialable or []) or "(none reported)"}')
    return ok, lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Compare two --netdiag info reports from two machines.')
    parser.add_argument('reports', nargs=2, metavar=('A.json', 'B.json'))
    parser.add_argument('--labels', nargs=2, metavar=('A', 'B'), default=None,
                        help='machine names for the output (default machine-a/b)')
    parser.add_argument('--json', action='store_true', help='emit the comparison as JSON')
    args = parser.parse_args(argv)
    labels = args.labels or ('machine-a', 'machine-b')
    try:
        left, right = (_load(path) for path in args.reports)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'compare_netdiag: {exc}', file=sys.stderr)
        return 2
    ok, lines = compare(left, right, labels[0], labels[1])
    if args.json:
        print(json.dumps(dict(ok=ok, lines=lines), indent=1))
    else:
        for line in lines:
            print(line)
        print('COMPARE_OK' if ok else 'COMPARE_FAIL')
    return 0 if ok else 1


if __name__ == '__main__':                       # pragma: no cover - manual entry
    raise SystemExit(main())
