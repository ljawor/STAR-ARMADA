"""Source-only fresh-process before/after matrix (requires git and real SDL/GL).

Run with --output-dir pointing to a writable evidence directory. Baseline code
is loaded from immutable git objects in child processes, never checked out over
working files. Run without concurrent tests, profilers or other benchmarks.
"""
from __future__ import annotations

import argparse
import cProfile
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def child(args):
    from game.benchmark import make_scene, run_benchmark
    if args.implementation == 'baseline':
        for path, package, class_name, method in (
            ('game/systems/weapons.py', 'game.systems', 'WeaponSystem', 'find_target'),
            ('game/systems/separation.py', 'game.systems', 'SeparationSystem', 'update'),
            ('render/fog.py', 'render', 'FogMask', 'surface')):
            code = subprocess.check_output(['git', 'show', args.baseline + ':' + path], cwd=ROOT)
            reference = types.ModuleType(package + '.benchmark_reference')
            reference.__package__ = package
            # Trusted local git source only; no report contents are executed.
            exec(compile(code, path, 'exec'), reference.__dict__)
            live = __import__(package + '.' + Path(path).stem, fromlist=[class_name])
            setattr(getattr(live, class_name), method, getattr(getattr(reference, class_name), method))
    units = args.units[0]
    if args.mode == 'profile':
        gm = make_scene(units)
        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(10):
            gm.step(1 / 30)
        profiler.disable()
        if gm.state.tick != 10 or gm.state.game_over:
            raise RuntimeError('profile fixture stopped early')
        rows = []
        for entry in profiler.getstats():
            code = entry.code
            if isinstance(code, types.CodeType):
                rows.append(dict(file=code.co_filename.split('STAR-ARMADA/')[-1],
                    function=code.co_name, calls=entry.callcount,
                    total_seconds=entry.totaltime, own_seconds=entry.inlinetime))
        result = dict(profile_ticks=gm.state.tick,
                      top=sorted(rows, key=lambda row: row['total_seconds'], reverse=True)[:20])
    else:
        result = run_benchmark(units=units, frames=args.frames, warmup=args.warmup, mode=args.mode)
    result.update(implementation=args.implementation, baseline_ref=args.baseline, units=units)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='470e467')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--units', nargs='+', type=int, default=[200, 500])
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--frames', type=int, default=30)
    parser.add_argument('--warmup', type=int, default=5)
    parser.add_argument('--implementation', choices=('baseline', 'candidate'), help=argparse.SUPPRESS)
    parser.add_argument('--mode', choices=('sim', 'full', 'profile'), help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    # Resolve once, so refs cannot move between children. Reject option-like refs.
    args.baseline = subprocess.check_output(['git', 'rev-parse', '--verify',
        '--end-of-options', args.baseline + '^{commit}'], cwd=ROOT, text=True).strip()
    if args.implementation:
        if args.output is None or args.mode is None or len(args.units) != 1:
            parser.error('child requires one unit count, --mode and --output')
        child(args)
        return
    if args.output_dir is None or args.trials < 1 or len(set(args.units)) != len(args.units):
        parser.error('require --output-dir, positive --trials and unique --units')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows, profiles = [], []

    def collect(implementation, mode, units, target):
        subprocess.run([sys.executable, str(Path(__file__).resolve()),
            '--baseline', args.baseline, '--implementation', implementation,
            '--mode', mode, '--units', str(units), '--frames', str(args.frames),
            '--warmup', str(args.warmup), '--output', str(target)], cwd=ROOT, check=True)
        return json.loads(target.read_text())

    for units in args.units:
        for mode in ('sim', 'full'):
            for trial in range(args.trials):
                order = ('baseline', 'candidate') if trial % 2 == 0 else ('candidate', 'baseline')
                for implementation in order:
                    row = collect(implementation, mode, units,
                                  out / f'{units}-{mode}-{implementation}-{trial}.json')
                    row['trial'] = trial
                    rows.append(row)
                    (out / 'all.json').write_text(json.dumps(rows, indent=2) + '\n')
                    print('STAGES', units, mode, implementation, trial,
                          {stage: round(data['median_ms'], 3) if data['median_ms'] is not None else None
                           for stage, data in row['stages'].items()}, flush=True)
    # Instrumented profiles are deliberately separate from unprofiled timing.
    for units in args.units:
        for implementation in ('baseline', 'candidate'):
            profiles.append(collect(implementation, 'profile', units,
                                    out / f'{units}-profile-{implementation}.json'))
    expected = len(args.units) * args.trials * 4
    if len(rows) != expected:
        raise RuntimeError('incomplete trial matrix')
    for units in args.units:
        subset = [row for row in rows if row['units'] == units]
        for field in ('initial_state_sha256', 'state_sha256'):
            if len({row[field] for row in subset}) != 1:
                raise RuntimeError(f'{units}: precise state mismatch: {field}')
        full = [row for row in subset if row['mode'] == 'full']
        if len({row['framebuffer_sha256'] for row in full}) != 1:
            raise RuntimeError(f'{units}: real GL framebuffer differs')
        if not all(row['executed_ticks'] == args.frames + args.warmup and
                   not row['game_over'] and any(
                       sample['projectiles'] > 0 or sample['effects'] > 0
                       for sample in row['counts_per_sample'])
                   for row in subset):
            raise RuntimeError(f'{units}: vacuous or incomplete combat')
    artifact = dict(baseline=args.baseline, trials=rows, profiles=profiles,
                    precise_state_equal=True, real_gl_framebuffers_equal=True,
                    expected_trials=expected, collected_trials=len(rows))
    (out / 'acceptance.json').write_text(json.dumps(artifact, indent=2) + '\n')
    print('MATRIX_OK', out / 'acceptance.json')


if __name__ == '__main__':
    main()
