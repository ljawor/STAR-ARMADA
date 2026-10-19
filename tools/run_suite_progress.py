"""Run the unittest suite with per-test progress, so a long run says where it is.

`python -m unittest discover` prints one character per test and nothing else: a suite that is
stalled inside one test looks identical to a suite that is merely slow, and the running test's
name does not exist anywhere until the run ends. This runner prints a line per test:

    [  1187/2003] 14:02:11   4.213s  ok    test_x.Class.test_name

plus a STALL line while one test is still running past the threshold — which names the test
that is costing the time instead of leaving a frozen log. It never changes test semantics: the
same loader builds the same suite and execution goes through unittest.TestResult, so a green
run here means what a green run there means.

Usage:
    PYTHONPATH=tests .venv/bin/python tools/run_suite_progress.py \
        --start-dir tests --top-level tests \
        --log artifacts/suite.log --json artifacts/suite.json --stall-seconds 120

Exit code is 0 only when every test passed and none errored.
"""
import argparse
import json
import os
import sys
import threading
import time
import traceback
import unittest

# Running as a script puts tools/ on sys.path, not the repository root, so `game` and
# `render` would be unimportable in the very suite this runner is meant to run.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class Tee:
    """Write the same progress lines to stdout and to a log file, flushing both."""

    def __init__(self, stream, handle):
        self.stream = stream
        self.handle = handle

    def write(self, data):
        self.stream.write(data)
        self.handle.write(data)

    def flush(self):
        self.stream.flush()
        self.handle.flush()

    def close(self):
        self.flush()
        self.handle.close()


class ProgressResult(unittest.TextTestResult):
    # `records` deliberately avoids the stdlib's own `durations` attribute, which
    # TextTestResult/TestResult already use for runner-side timing.
    def __init__(self, stream, descriptions, verbosity, total, stall_seconds):
        super().__init__(stream, descriptions, verbosity)
        self.total = total
        self.stall_seconds = stall_seconds
        self.records = []
        self.current = None
        self.current_since = None

    def out(self, text):
        self.stream.write(text + '\n')
        self.stream.flush()

    def startTest(self, test):
        super().startTest(test)
        self.current = test.id()
        self.current_since = time.monotonic()

    def stopTest(self, test):
        super().stopTest(test)
        elapsed = time.monotonic() - (self.current_since or time.monotonic())
        kind = 'ok'
        if any(t.id() == test.id() for t, _ in self.failures):
            kind = 'fail'
        elif any(t.id() == test.id() for t, _ in self.errors):
            kind = 'error'
        elif any(t.id() == test.id() for t, _ in self.skipped):
            kind = 'skip'
        elif any(t.id() == test.id() for t, _ in self.unexpectedSuccesses):
            kind = 'unexp'
        self.records.append({'test': test.id(), 'seconds': round(elapsed, 3), 'outcome': kind})
        self.current = None
        self.current_since = None
        stamp = f'[{len(self.records):5d}/{self.total}]'
        self.out(f'{stamp} {time.strftime("%H:%M:%S")} {elapsed:8.3f}s  {kind:<5} {test.id()}')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            kind = 'fail' if issubclass(err[0], test.failureException) else 'error'
            self.out(f'          subtest {kind}: {subtest}  {err[1]!r}')
            for line in ''.join(traceback.format_exception(*err)).rstrip().splitlines():
                self.out('          | ' + line)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        for line in ''.join(traceback.format_exception(*err)).rstrip().splitlines():
            self.out('          | ' + line)

    def addError(self, test, err):
        super().addError(test, err)
        for line in ''.join(traceback.format_exception(*err)).rstrip().splitlines():
            self.out('          | ' + line)


class ProgressRunner(unittest.TextTestRunner):
    def __init__(self, result, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._result = result

    def _makeResult(self):
        return self._result


def watchdog(result, stop, stall_seconds, heartbeat):
    last_note = 0.0
    while not stop.wait(1.0):
        if result.current is None or result.current_since is None:
            continue
        running = time.monotonic() - result.current_since
        if running >= stall_seconds and (running - last_note) >= heartbeat:
            last_note = running
            result.out(f'!! STALL {running:7.1f}s  [{len(result.records):5d}/{result.total}]  '
                       f'still running: {result.current}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-dir', default='tests')
    parser.add_argument('--top-level', default='tests')
    parser.add_argument('--pattern', default='test*.py')
    parser.add_argument('--log', default=None, help='tee progress to this file as well as stdout')
    parser.add_argument('--json', default=None, help='write machine-readable per-test results here')
    parser.add_argument('--stall-seconds', type=float, default=120.0)
    parser.add_argument('--heartbeat', type=float, default=60.0)
    args = parser.parse_args()

    tests = list(flatten(unittest.TestLoader().discover(
        args.start_dir, pattern=args.pattern, top_level_dir=args.top_level)))
    total = len(tests)

    stream = sys.stdout
    tee = Tee(sys.stdout, open(args.log, 'w')) if args.log else None
    if tee is not None:
        stream = tee

    result = ProgressResult(stream, True, 0, total, args.stall_seconds)
    runner = ProgressRunner(result, stream=stream, verbosity=0, failfast=False)
    stop = threading.Event()
    thread = threading.Thread(target=watchdog,
                              args=(result, stop, args.stall_seconds, args.heartbeat),
                              daemon=True)
    thread.start()

    started = time.time()
    print(f'discovered {total} tests in {args.start_dir}/  started {time.strftime("%H:%M:%S")}',
          file=stream, flush=True)
    runner.run(unittest.TestSuite(tests))
    stop.set()
    wall = time.time() - started

    passed = sum(1 for row in result.records if row['outcome'] == 'ok')
    slowest = sorted(result.records, key=lambda row: row['seconds'], reverse=True)[:10]
    summary = {
        'discovered': total,
        'executed': len(result.records),
        'passed': passed,
        'failures': [t.id() for t, _ in result.failures],
        'errors': [t.id() for t, _ in result.errors],
        'skipped': [t.id() for t, _ in result.skipped],
        'expected_failures': [t.id() for t, _ in result.expectedFailures],
        'unexpected_successes': [t.id() for t, _ in result.unexpectedSuccesses],
        'wall_seconds': round(wall, 1),
        'stall_seconds_threshold': args.stall_seconds,
        'slowest': slowest,
        'ok': result.wasSuccessful(),
    }
    print('', file=stream)
    print(f'--- {len(result.records)} executed, {passed} passed, {len(result.failures)} failures, '
          f'{len(result.errors)} errors, {len(result.skipped)} skipped in {wall:.1f}s ---',
          file=stream)
    for row in slowest[:5]:
        print(f'    slowest: {row["seconds"]:8.2f}s  {row["test"]}', file=stream)
    for name in summary['failures']:
        print(f'    FAILURE: {name}', file=stream)
    for name in summary['errors']:
        print(f'    ERROR:   {name}', file=stream)
    stream.flush()
    if args.json:
        with open(args.json, 'w') as handle:
            json.dump(summary, handle, indent=2)
            handle.write('\n')
    if tee is not None:
        tee.close()
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
