"""Opt-in, CPU-only, one-shot Windows fatal-worker cleanup observation.

Run from the repository with its test dependencies/CMake/MSVC installed:
  python tools/diag_windows_worker_cleanup.py --run
Optional: --handle-exe C:\\Sysinternals\\handle64.exe (elevated, EULA already accepted).
Handle is queried read-only; no external handles are forcibly closed.
Optional: --close-process-handle-hypothesis is NOT a repair or acceptance test.
It closes only this Popen's process handle after a failed baseline cleanup, then
makes exactly one frame unlink observation. No cleanup retry loop is performed.
The outer process bounds compilation + reproduction to 100 seconds by default.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def emit(stage, **data):
    print(json.dumps(dict(stage=stage, **data), ensure_ascii=True), flush=True)


def ownership(frame, executable):
    executable = executable or shutil.which('handle64.exe') or shutil.which('handle.exe')
    if not executable:
        return dict(status='unavailable', reason='Sysinternals Handle not installed/on PATH; ownership unknown')
    # Never accept an EULA, install software or use Handle's destructive -c flag.
    try:
        result = subprocess.run([executable, '-a', str(frame)], capture_output=True,
                                text=True, errors='replace', timeout=5,
                                stdin=subprocess.DEVNULL)
        return dict(status='raw_observation', executable=executable,
                    returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
                    caveat='Requires elevation and previously accepted EULA; no matches do not prove no mapped references')
    except (OSError, subprocess.SubprocessError) as exc:
        return dict(status='unavailable', reason=repr(exc))


def reproduce(args):
    sys.path.insert(0, str(ROOT))
    from tests.test_native_worker import NativeWorkerTests

    case = NativeWorkerTests()
    window = None
    built = False
    emit('start', observer_pid=os.getpid(), mode=args.mode, platform=sys.platform)
    try:
        NativeWorkerTests.setUpClass()
        built = True
        window = case.window(args.mode)
        process = window._process
        mapping = window._mapping  # mmap reference only, not an exported pixel view
        directory = Path(window._temporary.name)
        frame = directory / 'frame.bgra'
        emit('before_fault', worker_pid=process.pid, returncode=process.poll(),
             directory=str(directory), frame_exists=frame.exists(), mapping_closed=mapping.closed)
        error = None
        try:
            if args.mode == 9:
                window._request('frame')
                window._request('poll')
            else:
                window._request('frame')
        except Exception as exc:
            error = repr(exc)
            emit('fault_exception', exception=error, traceback=traceback.format_exc())
        code = process.poll()
        baseline = dict(worker_pid=process.pid, returncode=code,
                        mapping_closed=mapping.closed, mapping_attribute_none=window._mapping is None,
                        pixels_attribute_present=hasattr(window, '_pixels'), terminal=window._terminal,
                        log_thread_alive=window._log_thread.is_alive(), stdout_closed=process.stdout.closed,
                        directory=str(directory), directory_exists=directory.exists(),
                        frame_exists=frame.exists(), fault_reported=error)
        emit('baseline_after_first_cleanup', **baseline)
        if frame.exists():
            emit('windows_ownership', **ownership(frame, args.handle_exe))
        else:
            emit('windows_ownership', status='not_applicable', reason='frame was removed')
        # Freeze baseline verdict before any opt-in hypothesis observation.
        expected_code = {1: 4, 6: 6, 9: 9}[args.mode]
        baseline_ok = (error is not None and code == expected_code and mapping.closed
                       and window._mapping is None and not directory.exists())
        if args.close_process_handle_hypothesis:
            if code is not None and frame.exists() and directory.exists():
                emit('hypothesis_begin', label='Popen process-handle retention; NOT a production fix',
                     baseline_cleanup_failed=True)
                process._handle.Close()
                try:
                    frame.unlink()  # one observation, not TemporaryDirectory.cleanup retry
                    emit('hypothesis_single_unlink', removed=True)
                except OSError as exc:
                    emit('hypothesis_single_unlink', removed=False, exception=repr(exc))
            else:
                emit('hypothesis_skipped', reason='Requires an exited child and a surviving frame after baseline cleanup')
        emit('baseline_verdict', passed=baseline_ok, expected_exitcode=expected_code,
             note='Hypothesis outcome cannot change this baseline verdict')
        return 0 if baseline_ok else 1
    except Exception as exc:
        emit('diagnostic_error', exception=repr(exc), traceback=traceback.format_exc())
        return 2
    finally:
        # Do not call case.doCleanups(): that would retry a failed frame cleanup
        # before the evidence is consumed. Stop a surviving writer, without
        # pretending cleanup succeeded. Worker temp finalizers may still report
        # their actual failure as this diagnostic process exits.
        if window is not None and window._process.poll() is None:
            try:
                window._process.kill()
                emit('emergency_reap', worker_pid=window._process.pid,
                     returncode=window._process.wait(timeout=2))
            except Exception as exc:
                emit('emergency_reap_failed', exception=repr(exc))
        if built:
            try:
                NativeWorkerTests.tearDownClass()
                emit('stub_fixture_cleanup', removed=not NativeWorkerTests.base.exists())
            except Exception as exc:
                emit('stub_fixture_cleanup', removed=False, exception=repr(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Explicitly allow compiling/running the CPU fault stub')
    parser.add_argument('--mode', type=int, choices=(1, 6, 9), default=1)
    parser.add_argument('--handle-exe')
    parser.add_argument('--close-process-handle-hypothesis', action='store_true')
    parser.add_argument('--deadline', type=int, choices=range(30, 121), default=100, metavar='30..120')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.run:
        parser.error('--run is required; this diagnostic compiles and runs a native CPU fault stub')
    if os.name != 'nt':
        parser.error('Real Windows is required; a non-Windows pass cannot diagnose the reported lock')
    if args.child:
        return reproduce(args)
    started = time.monotonic()
    command = [sys.executable, '-u', str(Path(__file__).resolve()), *sys.argv[1:], '--child']
    child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    emit('watchdog_start', diagnostic_pid=child.pid, deadline_seconds=args.deadline)
    timed_out = False
    try:
        output, _ = child.communicate(timeout=args.deadline)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        output = exc.output or b''
        watchdog_failed = False
        try:
            result = subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                                    capture_output=True, timeout=10)
            emit('watchdog_taskkill', returncode=result.returncode,
                 stdout=result.stdout.decode(errors='replace'), stderr=result.stderr.decode(errors='replace'),
                 note='Tree termination requested; its effect on descendants is not verified here')
            # A taskkill that runs but fails (no such process, access denied) confirms
            # nothing: treat it as unconfirmed and fall back to the direct child.
            if result.returncode != 0:
                watchdog_failed = True
                try:
                    child.kill()
                except OSError as kill_error:
                    emit('watchdog_reap_error', diagnostic_pid=child.pid, exception=repr(kill_error),
                         note='Neither tree nor direct-child termination is confirmed')
        except (OSError, subprocess.SubprocessError) as exc:
            # A timeout or launch failure of taskkill itself must not escape: that would
            # skip reporting and leave the diagnostic and its descendants unreaped.
            watchdog_failed = True
            partial = (getattr(exc, 'output', None) or getattr(exc, 'stdout', None) or b'')
            partial_error = getattr(exc, 'stderr', None) or b''
            emit('watchdog_taskkill', exception=repr(exc),
                 stdout=partial.decode(errors='replace'), stderr=partial_error.decode(errors='replace'),
                 note='Tree termination unconfirmed; the fallback below stops only the direct child')
            try:
                child.kill()
            except OSError as kill_error:
                emit('watchdog_reap_error', diagnostic_pid=child.pid, exception=repr(kill_error),
                     note='Neither tree nor direct-child termination is confirmed')
        # communicate only establishes completion of the direct child, not its tree.
        try:
            collected, _ = child.communicate(timeout=5)
            output = collected or output
        except subprocess.TimeoutExpired as final:
            # Even when the child cannot be reaped, the evidence it produced is the
            # reason this diagnostic ran: print it before reporting failure, and keep
            # the newer snapshot when the second timeout carries more output.
            late = final.output or b''
            if len(late) > len(output):
                output = late
            print(output.decode('utf-8', errors='replace'), end='', flush=True)
            emit('watchdog_failed', diagnostic_pid=child.pid, descendants_verified_stopped=False)
            return 125
        if watchdog_failed:
            print(output.decode('utf-8', errors='replace'), end='', flush=True)
            emit('watchdog_failed', diagnostic_pid=child.pid, direct_child_reaped=True,
                 descendants_verified_stopped=False,
                 note='Descendant ownership unresolved; direct-child reaping is not tree cleanup')
            return 125
    print(output.decode('utf-8', errors='replace'), end='', flush=True)
    # taskkill /T is a request, not proof: never report descendant cleanup as verified,
    # and never let a timeout read as a pass.
    ending = ({'descendants_verified_stopped': False,
               'note': 'Timeout: child termination was requested but descendant cleanup is '
                       'not independently verified; retain full output'}
              if timed_out else
              {'note': 'Child exited before the deadline; retain full output'})
    emit('watchdog_end', diagnostic_pid=child.pid, returncode=child.returncode,
         elapsed_seconds=round(time.monotonic() - started, 3), timed_out=timed_out, **ending)
    return 124 if timed_out else child.returncode


def _entry():
    """Run main(), but never leave the log without a verdict frame.

    A crash before run() reported anything would otherwise look like an ordinary red
    baseline; the observation gate refuses a log with no frame at all.
    """
    try:
        return main()
    except SystemExit:
        raise
    except BaseException as exc:                     # noqa: BLE001 - the frame must exist
        emit('diagnostic_error', exception=repr(exc), traceback=traceback.format_exc())
        return 2


if __name__ == '__main__':
    raise SystemExit(_entry())
