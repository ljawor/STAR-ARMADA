#!/usr/bin/env python3
"""Local stand-in for the STAR ARMADA GitHub CI jobs.

Why this file exists
--------------------
Every job on this repository's recent GitHub Actions runs is blocked before it
starts -- "The job was not started because recent account payments have failed
or your spending limit needs to be increased" -- so no green check is available
until the owner clears the billing block, and the logs of the runs that did
execute have since been purged (BlobNotFound).  This script runs, on this Mac,
every CI step that can run here, names every step it skips together with the
reason it is skipped, and writes a log plus a machine-readable summary so the
result is a receipt rather than a claim.

It is NOT a CI run.  It says nothing about Windows-only steps, and it does not
publish anything.  Read `does_not_cover` in the summary JSON before quoting it.

Usage
-----
    .venv/bin/python tools/ci_local.py          # or ./tools/ci_local.py

No arguments.  Runs against the worktree this file lives in, at whatever head
that worktree is at, and is safe to re-run: it writes only under
`artifacts/ci-local/` and never mutates tracked files.

Outputs
-------
    artifacts/ci-local/ci-local-<head-sha7>-<UTC>.log    full transcript
    artifacts/ci-local/ci-local-<head-sha7>-<UTC>.json   summary receipt

Exit status
-----------
    0  every step that could run here passed (skips do not fail the run)
    1  at least one step that ran here failed
    2  the runner could not start (not a git work tree, no interpreter)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'ci-local'
PYTHON = ROOT / '.venv' / 'bin' / 'python'

# The CI job's own environment for the focused LAN test step (windows-signal.yml).
LAN_TEST_ENV = {
    'PYTHONPATH': 'tests',
    'SDL_VIDEODRIVER': 'dummy',
    'SDL_AUDIODRIVER': 'dummy',
    # The workflow lowers the pacing floor for a shared 2-vCPU runner; the
    # correctness clauses still gate.  Reproduced as-is so this run matches CI.
    'STAR_ARMADA_PACING_FLOOR': '15',
}

# Modules from the windows-signal.yml "Focused LAN tests on Windows" step, in
# the workflow's own order.  Copied verbatim from the workflow file.
LAN_TEST_MODULES = [
    'test_netdiag', 'test_netdiag_compare', 'test_lan_state_diff',
    'test_sim_profiles', 'test_lan', 'test_multiplayer',
    'test_checksum_canonicalization', 'test_orbit_spacing_batch',
    'test_draw_view_scope', 'test_lan_human_safety',
    'test_lan_failure_diagnostics', 'test_lan_reconnect',
    'test_lan_production_reconnect', 'test_lan_reconnect_admission',
    'test_lan_launch_recovery', 'test_station_balance',
    'test_collection_points', 'test_collection_points_lan',
    'test_i18n', 'test_i18n_russian', 'test_language_tools',
    'test_windows_worker_diagnostic',
]

PROVISIONING = (
    'Runner provisioning: the action clones the repository into / installs '
    'software on a fresh GitHub-hosted runner. There is no runner here to '
    'provision - the worktree is already checked out and its head is recorded '
    'in this receipt instead.'
)
MACOS = 'darwin/arm64'

STEPS: list[dict] = [
    # ------------------------------------------------------------------
    # .github/workflows/release.yml   (trigger: push tags ["v*"])
    # ------------------------------------------------------------------
    dict(id='release.mac.1', workflow='release.yml', job='mac', runs_on='macos-latest',
         ci_step='Checkout repository', ci_command='uses: actions/checkout@v4',
         kind='skip', skip_reason=PROVISIONING),
    dict(id='release.mac.2', workflow='release.yml', job='mac', runs_on='macos-latest',
         ci_step='Set up Python', ci_command='uses: actions/setup-python@v5\nwith:\n  python-version: "3.11"',
         kind='skip',
         skip_reason=PROVISIONING + ' (The worktree interpreter reports 3.11, which matches the '
                     'version this step pins; recorded in host.python below.)'),
    dict(id='release.mac.3', workflow='release.yml', job='mac', runs_on='macos-latest',
         ci_step='Install deps',
         ci_command='python3 -m venv .venv\n./.venv/bin/pip install --upgrade pip\n'
                    './.venv/bin/pip install -r requirements.txt pyinstaller',
         kind='run',
         local_command=[str(PYTHON), '-m', 'pip', 'install', '--dry-run',
                        '-r', 'requirements.txt', 'pyinstaller'],
         timeout=300, env={},
         reproduction='dry_run',
         note='PARTIAL. This does not create a venv or upgrade pip: the worktree already carries a '
              'provisioned .venv (a symlink to the live checkout, Python 3.11.16), and mutating a '
              'shared virtualenv is out of scope. What is verified here is that the pinned '
              'requirements plus pyinstaller resolve and are satisfied by that interpreter. '
              'pyinstaller itself is used only by the packaging step, which is skipped.'),
    dict(id='release.mac.4', workflow='release.yml', job='mac', runs_on='macos-latest',
         ci_step='Build app + DMG',
         ci_command='./.venv/bin/pyinstaller star_armada.spec --noconfirm\n'
                    'codesign --force --deep --sign - "dist/STAR ARMADA.app"\n'
                    'mkdir -p dist/dmg_staging\n'
                    'cp -R "dist/STAR ARMADA.app" dist/dmg_staging/\n'
                    'ln -s /Applications dist/dmg_staging/Applications\n'
                    'hdiutil create -volname "STAR ARMADA" -srcfolder dist/dmg_staging \\\n'
                    '  -ov -format UDZO "dist/STAR-ARMADA-${GITHUB_REF_NAME}-mac.dmg"',
         kind='skip',
         skip_reason='Packaging step. It is reachable on macOS in principle (pyinstaller, codesign, '
                     'hdiutil all exist here) but it is deliberately out of scope: it is a '
                     'tag-triggered release build, it mutates dist/, and it is not a per-push '
                     'correctness gate - nothing about a source change is decided by it.'),
    dict(id='release.mac.5', workflow='release.yml', job='mac', runs_on='macos-latest',
         ci_step='Upload artifact (mac-dmg)',
         ci_command='uses: actions/upload-artifact@v4\nwith:\n  name: mac-dmg\n  '
                    'path: dist/STAR-ARMADA-*-mac.dmg',
         kind='skip',
         skip_reason='CI artifact storage (and it depends on the skipped packaging step). This run '
                     'keeps its own evidence under artifacts/ci-local/ instead.'),

    dict(id='release.win.1', workflow='release.yml', job='win', runs_on='windows-latest',
         ci_step='Checkout repository', ci_command='uses: actions/checkout@v4',
         kind='skip', skip_reason=PROVISIONING + ' PLATFORM MISMATCH: job runs on windows-latest.'),
    dict(id='release.win.2', workflow='release.yml', job='win', runs_on='windows-latest',
         ci_step='Set up Python',
         ci_command='uses: actions/setup-python@v5\nwith:\n  python-version: "3.11"',
         kind='skip', skip_reason=PROVISIONING + ' PLATFORM MISMATCH: job declares runs-on '
                     'windows-latest; this machine is ' + MACOS + '.'),
    dict(id='release.win.3', workflow='release.yml', job='win', runs_on='windows-latest',
         ci_step='Install deps',
         ci_command='python -m pip install --upgrade pip\npip install -r requirements.txt pyinstaller',
         kind='skip', skip_reason='PLATFORM MISMATCH: Windows-only job (windows-latest); this machine '
                     'is ' + MACOS + '. The requirements themselves are resolved on macOS by '
                     'release.mac.3, but that is not evidence about the Windows runner.'),
    dict(id='release.win.4', workflow='release.yml', job='win', runs_on='windows-latest',
         ci_step='Build exe', ci_command='pyinstaller star_armada.spec --noconfirm',
         kind='skip', skip_reason='PLATFORM MISMATCH and packaging: a Windows .exe build on '
                     'windows-latest. Not run here and not substitutable on macOS.'),
    dict(id='release.win.5', workflow='release.yml', job='win', runs_on='windows-latest',
         ci_step='Zip',
         ci_command='Compress-Archive -Path "dist/STAR ARMADA/*" `\n  -DestinationPath '
                    '"dist/STAR-ARMADA-${env:GITHUB_REF_NAME}-win.zip"',
         kind='skip', skip_reason='PLATFORM MISMATCH: Compress-Archive is a PowerShell cmdlet that '
                     'exists only on Windows. Packaging step.'),
    dict(id='release.win.6', workflow='release.yml', job='win', runs_on='windows-latest',
         ci_step='Upload artifact (win-zip)',
         ci_command='uses: actions/upload-artifact@v4\nwith:\n  name: win-zip\n  '
                    'path: dist/STAR-ARMADA-*-win.zip',
         kind='skip', skip_reason='CI artifact storage on a Windows-only job; depends on the '
                     'skipped packaging step.'),

    dict(id='release.release.1', workflow='release.yml', job='release', runs_on='ubuntu-latest',
         ci_step='Download artifacts',
         ci_command='uses: actions/download-artifact@v4\nwith:\n  path: artifacts',
         kind='skip', skip_reason='Publishing job: it collects the mac and win packaging artifacts '
                     'out of GitHub\'s artifact store, which does not exist locally and whose '
                     'producers are skipped above.'),
    dict(id='release.release.2', workflow='release.yml', job='release', runs_on='ubuntu-latest',
         ci_step='Create GitHub release',
         ci_command='uses: softprops/action-gh-release@v2\nwith:\n  name: "STAR ARMADA '
                    '${{ github.ref_name }}"\n  ... files: artifacts/mac-dmg/* , artifacts/win-zip/*',
         kind='skip', skip_reason='Publishing: creates a public GitHub release and uploads the '
                     'binaries. Neither local nor appropriate - this runner must not publish.'),

    # ------------------------------------------------------------------
    # .github/workflows/windows-signal.yml
    # (trigger: workflow_dispatch, pull_request, push branches [main])
    # ------------------------------------------------------------------
    dict(id='windows-lan.1', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Checkout repository',
         ci_command='uses: actions/checkout@v4',
         kind='skip', skip_reason=PROVISIONING),
    dict(id='windows-lan.2', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Set up Python',
         ci_command='uses: actions/setup-python@v5\nwith:\n  python-version: "3.11"\n  cache: pip',
         kind='skip', skip_reason=PROVISIONING + ' (The worktree interpreter reports 3.11, matching '
                     'this step\'s pin; pip\'s cache is a runner speed feature with no local '
                     'equivalent needed.)'),
    dict(id='windows-lan.3', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Install deps',
         ci_command='python -m pip install --upgrade pip\npip install -r requirements.txt',
         kind='run',
         local_command=[str(PYTHON), '-m', 'pip', 'install', '--dry-run', '-r', 'requirements.txt'],
         timeout=300, env={},
         reproduction='dry_run',
         note='PARTIAL. No venv is created and pip is not upgraded; the worktree already carries a '
              'provisioned .venv (Python 3.11.16, matching the job\'s 3.11 pin). Verified: the '
              'pinned requirements resolve and are already satisfied (pygame-ce, PyOpenGL, numpy).'),

    dict(id='windows-lan.4', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='netdiag on real Windows',
         ci_command='python main.py --netdiag info --out netdiag-windows.json',
         kind='run',
         local_command=[str(PYTHON), 'main.py', '--netdiag', 'info', '--out',
                        str(ARTIFACTS / 'netdiag-macos.json')],
         timeout=180, env={},
         reproduction='other_platform',
         note='PARTIAL, and read this one carefully. The command really runs: the entry point, the '
              'environment probe, the local-address enumeration and the real host+join socket '
              'pairing all execute, and the report is written. But the step is named "on real '
              'Windows" and its whole purpose is the Windows half of a cross-platform comparison. '
              'This run is the macOS half. It says the netdiag code path works on macOS; it says '
              'nothing about Windows, and it does NOT substitute for the CI step. Output written '
              'to artifacts/ci-local/netdiag-macos.json (not the CI\'s netdiag-windows.json) so the '
              'two can never be confused.'),
    dict(id='windows-lan.5', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Show the report',
         ci_command='Get-Content netdiag-windows.json',
         kind='run',
         local_command=[str(PYTHON), '-c',
                        'import sys,pathlib;sys.stdout.write('
                        'pathlib.Path("artifacts/ci-local/netdiag-macos.json").read_text()[:4000])'],
         timeout=60, env={},
         reproduction='substituted_command',
         note='SUBSTITUTED. This is a display step (its command is the PowerShell built-in '
              'Get-Content, which does not exist on macOS). Its intent - put the report the '
              'previous step wrote in front of the reader - is reproduced by reading that file, '
              'and the full report is in the log. No gate is decided here.'),
    dict(id='windows-lan.6', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Dump the scene states on Windows',
         ci_command='python tools/lan_state_diff.py dump --out state-win-ticks0.json\n'
                    'python tools/lan_state_diff.py dump --out state-win-ticks1.json --ticks 1\n'
                    'python tools/lan_state_diff.py dump --out state-win-contact-ticks60.json '
                    '--scene contact --ticks 60',
         kind='run',
         local_command=[
             [str(PYTHON), 'tools/lan_state_diff.py', 'dump', '--out',
              str(ARTIFACTS / 'state-macos-ticks0.json')],
             [str(PYTHON), 'tools/lan_state_diff.py', 'dump', '--out',
              str(ARTIFACTS / 'state-macos-ticks1.json'), '--ticks', '1'],
             [str(PYTHON), 'tools/lan_state_diff.py', 'dump', '--out',
              str(ARTIFACTS / 'state-macos-contact-ticks60.json'), '--scene', 'contact',
              '--ticks', '60'],
         ],
         timeout=240, env={},
         reproduction='other_platform',
         note='PARTIAL. All three dumps execute and are written (macOS names, so they cannot be '
              'mistaken for the CI\'s state-win-*.json). These are pure-Python, platform-generic '
              'dumps of exactly the structure precise_checksum hashes, and two macOS peers can be '
              'diffed from them with `tools/lan_state_diff.py diff`. The comparison the CI step '
              'exists for is Windows-vs-macOS, and that half cannot be produced on this machine; '
              'the checksums below are the macOS side of that comparison only.'),
    dict(id='windows-lan.7', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Focused LAN tests on Windows',
         ci_command='env: PYTHONPATH=tests, SDL_VIDEODRIVER=dummy, SDL_AUDIODRIVER=dummy, '
                    'STAR_ARMADA_PACING_FLOOR=15\n'
                    'python -m unittest ' + ' '.join(LAN_TEST_MODULES) + ' -v',
         kind='run',
         local_command=[str(PYTHON), '-m', 'unittest'] + LAN_TEST_MODULES + ['-v'],
         timeout=1800, env=LAN_TEST_ENV,
         reproduction='exact_commands',
         note='REPRODUCED EXACTLY: same 21 modules, same order, same environment including the '
              'lowered STAR_ARMADA_PACING_FLOOR=15, the dummy SDL drivers and PYTHONPATH=tests. '
              'The commands are identical; the platform is not, so this is macOS evidence about '
              'modules that are platform-portable, not Windows evidence. Two-process LAN tests in '
              'this list are load-sensitive; the summary records the machine\'s load average before '
              'and after the run (host.loadavg_1_5_15_*) - read a timing failure against those '
              'numbers rather than assuming the box was idle. It was not necessarily: a sibling '
              'task was editing this same worktree while the receipt was produced, which is '
              'recorded in does_not_cover.'),
    dict(id='windows-lan.8', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Replay deletion on real Windows',
         ci_command='python -c "import os, unittest; assert os.name == \'nt\', \'Native Windows '
                    'deletion gate requires Windows\'; suite = unittest.defaultTestLoader.'
                    'loadTestsFromName(\'test_replay_deletion_windows.'
                    'NativeWindowsDeletionTests\'); expected = suite.countTestCases(); result = '
                    'unittest.TextTestRunner(verbosity=2).run(suite); optional = '
                    '\'test_file_symlink_is_never_deleted_or_followed\'; raise SystemExit(0 if '
                    'result.wasSuccessful() and result.testsRun == expected and all(test.'
                    '_testMethodName == optional for test, reason in result.skipped) else 1)"\n'
                    'if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n'
                    'python -m unittest test_replay_deletion_windows test_replay_library -v',
         kind='skip',
         skip_reason='PLATFORM MISMATCH, and reproducing it here would produce a FALSE PASS, so it '
                     'is skipped on purpose. The step\'s first command asserts os.name == \'nt\' - on '
                     'macOS it exits 1 by construction. The module it gates carries '
                     '@unittest.skipUnless(os.name == \'nt\', \'native Windows kernel required; NOT '
                     'accepted on macOS\'), so running the step verbatim on macOS would report green '
                     'while executing none of the native deletion gates it exists for. Those gates '
                     'need real Windows handles, junctions and locked files. The portable member of '
                     'the step\'s second command is run separately below, clearly labelled as a '
                     'local addition rather than as this step passing.'),
    dict(id='windows-lan.9', workflow='windows-signal.yml', job='windows-lan',
         runs_on='windows-latest', ci_step='Upload artifact (netdiag-windows)',
         ci_command='uses: actions/upload-artifact@v4\nif: always()\nwith:\n  '
                    'name: netdiag-windows\n  path: netdiag-windows.json, state-win-ticks0.json, '
                    'state-win-ticks1.json, state-win-contact-ticks60.json',
         kind='skip', skip_reason='CI artifact storage. The four equivalent macOS files are written '
                     'under artifacts/ci-local/ by windows-lan.4 and windows-lan.6 instead.'),

    dict(id='package-windows.1', workflow='windows-signal.yml', job='package-windows',
         runs_on='windows-latest', ci_step='Checkout repository',
         ci_command='uses: actions/checkout@v4',
         kind='skip', skip_reason=PROVISIONING + ' Job is also gated on github.event_name == '
                     'workflow_dispatch (manual runs only).'),
    dict(id='package-windows.2', workflow='windows-signal.yml', job='package-windows',
         runs_on='windows-latest', ci_step='Set up Python',
         ci_command='uses: actions/setup-python@v5\nwith:\n  python-version: "3.11"\n  cache: pip',
         kind='skip', skip_reason=PROVISIONING + ' PLATFORM MISMATCH: windows-latest; this machine '
                     'is ' + MACOS + '. Job is also manual-dispatch only.'),
    dict(id='package-windows.3', workflow='windows-signal.yml', job='package-windows',
         runs_on='windows-latest', ci_step='Install deps',
         ci_command='python -m pip install --upgrade pip\npip install -r requirements.txt pyinstaller',
         kind='skip', skip_reason='PLATFORM MISMATCH: Windows-only job (windows-latest), and this '
                     'job only runs on a manual workflow_dispatch. The requirements are resolved on '
                     'macOS under release.mac.3 / windows-lan.3.'),
    dict(id='package-windows.4', workflow='windows-signal.yml', job='package-windows',
         runs_on='windows-latest', ci_step='Build exe',
         ci_command='pyinstaller star_armada.spec --noconfirm',
         kind='skip', skip_reason='PLATFORM MISMATCH and packaging: a Windows .exe build. Not '
                     'substitutable on macOS.'),
    dict(id='package-windows.5', workflow='windows-signal.yml', job='package-windows',
         runs_on='windows-latest', ci_step='Zip',
         ci_command='Compress-Archive -Path "dist/STAR ARMADA/*" `\n  -DestinationPath '
                    '"dist/STAR-ARMADA-candidate-win.zip"',
         kind='skip', skip_reason='PLATFORM MISMATCH: Compress-Archive is Windows PowerShell only. '
                     'Packaging step.'),
    dict(id='package-windows.6', workflow='windows-signal.yml', job='package-windows',
         runs_on='windows-latest', ci_step='Upload artifact (star-armada-candidate-win)',
         ci_command='uses: actions/upload-artifact@v4\nwith:\n  name: star-armada-candidate-win\n  '
                    'path: dist/STAR-ARMADA-candidate-win.zip',
         kind='skip', skip_reason='CI artifact storage on a Windows-only, manual-only packaging job.'),

    # ------------------------------------------------------------------
    # Local addition: not a CI step. The portable member of the skipped
    # windows-lan.8 command, run because it *is* part of the local-able set
    # and would otherwise be silently dropped with the step.
    # ------------------------------------------------------------------
    dict(id='local-extra.1', workflow='(none)', job='(local addition)', runs_on='(this machine)',
         ci_step='test_replay_library (portable member of the skipped Windows step)',
         ci_command='(no CI step runs this module alone; it is the second of the two modules in '
                    'windows-lan.8\'s second command)',
         kind='run', ci_step_is_ci=False,
         local_command=[str(PYTHON), '-m', 'unittest', 'test_replay_library', '-v'],
         timeout=600,
         env={'PYTHONPATH': 'tests', 'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'},
         reproduction='exact_commands',
         note='LOCAL ADDITION, not a CI step. The CI runs this module together with '
              'test_replay_deletion_windows, which self-skips wholesale on macOS; running only the '
              'portable member keeps windows-lan.8 honestly marked as skipped while still covering '
              'the part of it that macOS can exercise.'),
]

COVERS = [
    'The focused LAN test suite from windows-signal.yml\'s windows-lan job: the same 21 modules, '
    'in the same order, under the same environment (PYTHONPATH=tests, dummy SDL video/audio, '
    'STAR_ARMADA_PACING_FLOOR=15) - executed on macOS.',
    'The netdiag entry point (python main.py --netdiag info): environment probe, local-address '
    'enumeration and a real host+join socket pairing on macOS.',
    'The three tools/lan_state_diff.py scene-state dumps (ticks 0, ticks 1, contact scene at 60 '
    'ticks), writing the same structure precise_checksum hashes, as the macOS half of the '
    'cross-platform comparison.',
    'Requirements resolvability/installation for -r requirements.txt (and + pyinstaller for the '
    'packaging job) against a Python 3.11 interpreter - as a dry run, not a fresh install.',
    'The portable member of the Windows-only replay-deletion step (test_replay_library), labelled '
    'as a local addition.',
    'A named head: the summary records the full 40-character SHA, the branch and the sha256 of '
    'both workflow files the steps were enumerated from.',
]
DOES_NOT_COVER = [
    'It is NOT a CI run. No GitHub-hosted runner was involved and no check was reported to GitHub.',
    'Every Windows-only step: both windows-latest jobs in windows-signal.yml and the win job plus '
    'the release job in release.yml. That is the entire Windows evidence for issue #56 - netdiag '
    'on real Windows, the focused suite on Windows, the cross-platform checksum comparison and the '
    'native Windows replay-deletion gates (os.name == "nt" handles, junctions, locked files).',
    'The native Windows replay-deletion gate specifically: it self-skips on macOS, so a green '
    'result here would be a false pass, which is why windows-lan.8 is reported as skipped.',
    'All packaging: pyinstaller builds, codesign, hdiutil DMG creation, Compress-Archive zips, and '
    'the artifact upload/download steps that carry them.',
    'The publish step (softprops/action-gh-release) and anything the tag-triggered release workflow '
    'does after a build.',
    'Runner provisioning (actions/checkout, actions/setup-python): the worktree is reused as-is, '
    'and its head is recorded rather than re-cloned.',
    'The CI\'s dependency install as such: it is verified as a pip dry run against the existing '
    'worktree virtualenv (a symlink to the live checkout), not by building a fresh .venv.',
    'Fresh-clone conditions, and an idle machine. The CI checks out into an empty runner and owns '
    'it; this run was taken in a worktree that a sibling task was editing at the same time, under '
    'a non-trivial load average (recorded in host.loadavg_1_5_15_start/end). The tracked state it '
    'ran against is recorded in git_status_before/after and is not pristine.',
    'Blender or any art/asset gate - none of the CI steps here run one.',
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_unittest(text: str) -> dict | None:
    """Pull the counts out of a unittest run's tail - None if this was not one."""
    match = re.search(r'^Ran (\d+) tests? in ([\d.]+)s', text, re.M)
    if not match:
        return None
    lines = text.rstrip().splitlines()
    last = lines[-1].strip() if lines else ''
    skipped = re.search(r'skipped=(\d+)', last)
    return {
        'tests': int(match.group(1)),
        'seconds': float(match.group(2)),
        'skipped': int(skipped.group(1)) if skipped else 0,
        'verdict': 'OK' if last.startswith('OK') else last[:80],
    }


def loadavg() -> list[float] | None:
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except OSError:                                  # not every platform has it
        return None


class Transcript:
    """Writes every line to stdout and, in full, to the log file."""

    def __init__(self, log_path: Path):
        self.handle = log_path.open('w', encoding='utf-8')
        self.lines: list[str] = []

    def say(self, text: str = '') -> None:
        print(text, flush=True)
        self.handle.write(text + '\n')
        self.handle.flush()
        self.lines.append(text)

    def log_only(self, text: str) -> None:
        """Full subprocess output: goes to the log, truncated on stdout."""
        self.handle.write(text if text.endswith('\n') else text + '\n')
        self.handle.flush()
        lines = text.splitlines()
        if len(lines) <= 50:
            print(text, flush=True)
        else:
            elision = f'... [{len(lines) - 40} lines omitted - full output in the log]'
            shown: list[str] = list(lines[:20])
            shown.append(elision)
            shown.extend(lines[-20:])
            print('\n'.join(shown), flush=True)
        self.lines.append(text)

    def close(self) -> None:
        self.handle.close()


def git(*args: str) -> str:
    out = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    return out.stdout.strip() if out.returncode == 0 else ''


def run_command(cmd, timeout: int, env_overrides: dict) -> dict:
    """Run one command with an explicit timeout; never raise for a failed step."""
    env = dict(os.environ)
    env.update(env_overrides or {})
    started = time.monotonic()
    try:
        completed = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                                    timeout=timeout)
        return dict(exit_code=completed.returncode, stdout=completed.stdout,
                    stderr=completed.stderr, duration_s=round(time.monotonic() - started, 2),
                    timed_out=False)
    except subprocess.TimeoutExpired as expired:
        return dict(exit_code=None,
                    stdout=(expired.stdout or b'').decode('utf-8', 'replace') if isinstance(expired.stdout, bytes) else (expired.stdout or ''),
                    stderr=f'TIMED OUT after {timeout}s',
                    duration_s=round(time.monotonic() - started, 2), timed_out=True)
    except FileNotFoundError as missing:
        return dict(exit_code=None, stdout='', stderr=f'COMMAND NOT FOUND: {missing}',
                    duration_s=round(time.monotonic() - started, 2), timed_out=False)


def main() -> int:
    if not (ROOT / '.git').exists() and not (ROOT / 'pyproject.toml').exists():
        print(f'ci_local: {ROOT} is not the STAR ARMADA worktree', file=sys.stderr)
        return 2

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    head = git('rev-parse', 'HEAD')
    if not head:
        print('ci_local: cannot read HEAD with git', file=sys.stderr)
        return 2
    head7 = head[:7]
    now = _dt.datetime.now(_dt.timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    stem = f'ci-local-{head7}-{stamp}'
    log_path = ARTIFACTS / f'{stem}.log'
    summary_path = ARTIFACTS / f'{stem}.json'

    transcript = Transcript(log_path)
    status_before = git('status', '--short')
    load_start = loadavg()
    started = time.monotonic()
    say = transcript.say

    say('=' * 78)
    say('STAR ARMADA - local stand-in for the GitHub CI jobs')
    say('=' * 78)
    say(f'worktree   : {ROOT}')
    say(f'head       : {head}')
    say(f'branch     : {git("rev-parse", "--abbrev-ref", "HEAD")}')
    say(f'utc        : {now.strftime("%Y-%m-%dT%H:%M:%SZ")}')
    say(f'interpreter: {PYTHON}')
    say(f'host       : {platform.platform()} / {platform.machine()}')
    say(f'git status : {status_before if status_before else "(clean)"}')
    say('')
    say('NOT a CI run. Skips are named with their reason; see the summary for what')
    say('this receipt does and does not cover.')
    say('')

    py_version = ''
    if PYTHON.exists():
        probe = subprocess.run([str(PYTHON), '-VV'], capture_output=True, text=True, timeout=60)
        py_version = probe.stdout.strip()
    say(f'python     : {py_version or f"MISSING at {PYTHON}"}')
    say('')

    results: list[dict] = []
    current_group = None
    for step in STEPS:
        group = f'{step["workflow"]} / job {step["job"]} (runs-on {step["runs_on"]})'
        if group != current_group:
            current_group = group
            say('-' * 78)
            say(group)
            say('-' * 78)

        record = {
            'id': step['id'],
            'workflow': step['workflow'],
            'job': step['job'],
            'runs_on': step['runs_on'],
            'ci_step': step['ci_step'],
            'ci_command': step['ci_command'],
            'ci_step_is_ci_step': step.get('ci_step_is_ci', True),
        }
        say(f'[{step["id"]}] {step["ci_step"]}')
        for line in step['ci_command'].splitlines():
            say(f'      ci> {line}')

        if step['kind'] == 'skip':
            record.update(result='SKIP', reproduction='out_of_scope', skipped=True,
                          skip_reason=step['skip_reason'], exit_code=None, duration_s=0.0)
            say(f'      SKIP - {step["skip_reason"]}')
            if 'PLATFORM' in step['skip_reason']:
                say(f'      platform mismatch: needed windows-latest, this machine is {MACOS}')
            say('')
            results.append(record)
            continue

        commands = step['local_command']
        if commands and isinstance(commands[0], str):
            commands = [commands]
        outcomes = []
        parsed_tests = []
        for command in commands:
            say(f'      run> {" ".join(command)}')
            outcome = run_command(command, step['timeout'], step.get('env') or {})
            outcomes.append(outcome)
            combined = ''
            for stream in ('stdout', 'stderr'):
                text = outcome[stream].rstrip('\n')
                if text:
                    combined += text + '\n'
                    transcript.log_only(f'      --- {stream} ---')
                    transcript.log_only(text)
            parsed = parse_unittest(combined)
            if parsed:
                parsed_tests.append(parsed)
                say(f'      tests: {parsed["tests"]} ran, {parsed["skipped"]} skipped, '
                    f'{parsed["verdict"]}')
            say(f'      exit={outcome["exit_code"]} in {outcome["duration_s"]}s'
                + ('  [TIMED OUT]' if outcome['timed_out'] else ''))

        passed = all(o['exit_code'] == 0 for o in outcomes)
        record.update(
            result='PASS' if passed else 'FAIL',
            reproduction=step['reproduction'],
            skipped=False,
            local_command=commands,
            local_env=step.get('env') or {},
            exit_code=outcomes[-1]['exit_code'],
            command_exit_codes=[o['exit_code'] for o in outcomes],
            duration_s=round(sum(o['duration_s'] for o in outcomes), 2),
            note=step['note'],
        )
        if parsed_tests:
            record['unittest'] = parsed_tests
        if len(outcomes) == 1 and outcomes[0]['exit_code'] is None:
            record['failure_reason'] = outcomes[0]['stderr'].splitlines()[-1] if outcomes[0]['stderr'] else 'no exit status'
        say(f'      {record["result"]} - {step["ci_step"]}')
        for line in step['note'].split('. '):
            if line.strip():
                say(f'      note: {line.strip().rstrip(".")}.')
        say('')
        results.append(record)

    # --- verdict ----------------------------------------------------------
    wall_time = round(time.monotonic() - started, 2)
    ci_steps = [r for r in results if r.get('ci_step_is_ci_step', True)]
    ran = [r for r in ci_steps if r['result'] in ('PASS', 'FAIL')]
    skipped = [r for r in ci_steps if r['result'] == 'SKIP']
    failed = [r for r in results if r['result'] == 'FAIL']
    extras = [r for r in results if not r.get('ci_step_is_ci_step', True)]
    status_after = git('status', '--short')
    load_end = loadavg()

    say('=' * 78)
    verdict = 'PASS' if not failed else 'FAIL'
    say(f'VERDICT: {verdict}')
    say(f'  CI steps enumerated : {len(ci_steps)}')
    say(f'  run here            : {len(ran)} ({sum(1 for r in ran if r["result"] == "PASS")} pass, '
        f'{sum(1 for r in ran if r["result"] == "FAIL")} fail)')
    say(f'  skipped, with reason: {len(skipped)}')
    say(f'  local additions     : {len(extras)} ({sum(1 for r in extras if r["result"] == "PASS")} pass)')
    say(f'  wall time           : {wall_time}s')
    say(f'  load average 1m     : {load_start} -> {load_end}')
    say('')
    if failed:
        say('  failed steps:')
        for r in failed:
            say(f'    {r["id"]} {r["ci_step"]} (exit {r["exit_code"]})')
        say('')
    say('  This receipt is a local reproduction of the CI steps that can run on')
    say('  macOS. It is NOT a CI run and it does not cover the Windows-only steps,')
    say('  the packaging steps or the publish step. Full list of both:')
    say(f'    {summary_path}')
    say(f'  Full transcript:')
    say(f'    {log_path}')
    say(f'  head {head}  git status: {status_after if status_after else "(clean)"}')
    say('=' * 78)

    workflow_files = sorted((ROOT / '.github' / 'workflows').glob('*.yml'))
    summary = {
        'schema': 1,
        'kind': 'local-ci-reproduction',
        'is_ci_run': False,
        'head_sha': head,
        'head_sha7': head7,
        'branch': git('rev-parse', '--abbrev-ref', 'HEAD'),
        'utc': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'started_utc': now.isoformat().replace('+00:00', 'Z'),
        'finished_utc': _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'wall_time_s': wall_time,
        'verdict': verdict,
        'exit_code': 1 if failed else 0,
        'host': {
            'platform': platform.system().lower(),
            'release': platform.release(),
            'machine': platform.machine(),
            'python': sys.version.split()[0],
            'worktree_python': py_version,
            'loadavg_1_5_15_start': load_start,
            'loadavg_1_5_15_end': load_end,
            'ci_runners_reproduced': [],
            'ci_runners_not_reproduced': ['macos-latest', 'windows-latest', 'ubuntu-latest'],
        },
        'counts': {
            'steps_total': len(results),
            'ci_steps_enumerated': len(ci_steps),
            'ci_steps_run': len(ran),
            'ci_steps_skipped': len(skipped),
            'steps_failed': len(failed),
            'local_addition_steps': len(extras),
            'unittest_total_ran': sum(t['tests'] for r in results for t in r.get('unittest', [])),
            'unittest_total_skipped': sum(t['skipped'] for r in results for t in r.get('unittest', [])),
        },
        'workflow_files': [
            {'path': str(p.relative_to(ROOT)), 'sha256': sha256(p), 'bytes': p.stat().st_size}
            for p in workflow_files
        ],
        'runner_script': {'path': str(Path(__file__).resolve().relative_to(ROOT)),
                          'sha256': sha256(Path(__file__).resolve())},
        'git_status_before': status_before.splitlines(),
        'git_status_after': status_after.splitlines(),
        'steps': results,
        'steps_run': [r for r in results if r['result'] in ('PASS', 'FAIL')],
        'steps_skipped': [{'id': r['id'], 'workflow': r['workflow'], 'job': r['job'],
                           'ci_step': r['ci_step'], 'ci_command': r['ci_command'],
                           'reason': r['skip_reason']} for r in skipped],
        'local_addition_steps': extras,
        'covers': COVERS,
        'does_not_cover': DOES_NOT_COVER,
        'log_path': str(log_path),
        'summary_path': str(summary_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    transcript.close()
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
