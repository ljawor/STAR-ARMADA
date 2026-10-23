"""CPU-only diagnostic safety and receipt gates; never start SDL/OpenGL."""
import builtins
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


PATH = Path(__file__).resolve().parents[1] / 'tools/render/capture_native_notification_hud_game.py'
spec = importlib.util.spec_from_file_location('notification_capture', PATH)
assert spec is not None and spec.loader is not None
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


@pytest.mark.parametrize('command', ['python3 main.py --skirmish',
                                     '/usr/bin/python3 /checkout/main.py',
                                     '/checkout/armada_viewer --embedded'])
def test_owner_refusal_precedes_any_graphics_import_and_writes_failed_receipt(tmp_path, monkeypatch, command):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        stdout=f'{capture.os.getpid()} 1 python capture.py\n1 0 launchd\n987654 1 {command}\n'))
    real_import = builtins.__import__
    imports = []

    def guarded_import(name, *a, **kw):
        if name.split('.')[0] in {'pygame', 'OpenGL', 'PIL', 'render', 'game'}:
            imports.append(name)
            raise AssertionError('graphics/game import before owner-game refusal')
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    out = tmp_path / 'capture'
    assert capture.main(['--out', str(out)]) == 1
    report = json.loads((out / 'notification-metrics.json').read_text())
    assert 'owner game' in report['error']
    assert '987654' in report['error']
    assert not imports
    assert not report['passed'] and not report['acceptance_complete']
    assert not report['cleanup_complete']
    assert sorted(p.name for p in out.iterdir()) == ['notification-metrics.json']


@pytest.mark.parametrize('argv', [
    ['python', 'main.py'], ['/usr/bin/python3.11', '/checkout/main.py', '--skirmish'],
    ['Python', '-u', './main.py'], ['python3', '-X', 'dev', '--', '../main.py'],
    ['/checkout/build/armada_viewer', '--embedded'],
])
def test_owner_argv_matches_only_execution_positions(argv):
    assert capture._owner_game_argv(argv)


@pytest.mark.parametrize('argv', [
    [], ['cat', 'docs/main.py'], ['sh', '-c', 'python main.py'],
    ['python3', '-c', 'print("main.py armada_viewer")'],
    ['python3', '-cprint("main.py")'], ['python3', '-m', 'pydoc', 'main.py'],
    ['python3', 'docs.py', 'main.py', 'armada_viewer'],
    ['python3', 'main.py.txt'], ['echo', 'armada_viewer'],
    ['python3', '-W', 'main.py', 'docs.py'], ['python3', '-X', 'main.py', 'docs.py'],
])
def test_non_game_mentions_are_not_owner_games(argv):
    assert not capture._owner_game_argv(argv)


def install_snapshot(monkeypatch, text):
    monkeypatch.setattr(capture.os, 'getpid', lambda: 50)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=text))


@pytest.mark.parametrize('command', ['python3 main.py', 'python3 /checkout/main.py',
                                     '/checkout/armada_viewer --embedded'])
def test_owner_pid_reported_without_stopping_it(monkeypatch, command):
    install_snapshot(monkeypatch, f'50 40 python3 capture.py\n40 1 shell\n1 0 launchd\n88 1 {command}\n')
    def forbidden(*a, **kw):
        pytest.fail('preflight must never signal a process')
    monkeypatch.setattr(capture.os, 'kill', forbidden)
    with pytest.raises(RuntimeError, match=r'owner game running \(PID 88\)'):
        capture.require_no_owner_game()


def test_excludes_self_and_entire_ancestor_chain_not_siblings(monkeypatch):
    snapshot = '50 40 python main.py\n40 20 /bin/armada_viewer\n20 1 python main.py\n1 0 launchd\n'
    install_snapshot(monkeypatch, snapshot)
    capture.require_no_owner_game()
    install_snapshot(monkeypatch, snapshot + '51 40 python main.py\n')
    with pytest.raises(RuntimeError, match='PID 51'):
        capture.require_no_owner_game()


@pytest.mark.parametrize('error', [OSError('ps unavailable'),
    subprocess.CalledProcessError(1, 'ps'), subprocess.TimeoutExpired('ps', 10)])
def test_process_enumeration_errors_fail_closed(monkeypatch, error):
    def broken(*a, **kw):
        raise error
    monkeypatch.setattr(subprocess, 'run', broken)
    with pytest.raises(RuntimeError, match='owner game preflight failed'):
        capture.require_no_owner_game()


@pytest.mark.parametrize('snapshot', ['', 'unparseable', '50 40 python capture.py\n',
    '50 40 python capture.py\n40 50 shell\n',
    '50 0 python capture.py\n50 0 python capture.py\n',
    '50 0 python capture.py\n88 0 python "unterminated\n'])
def test_incomplete_or_malformed_process_snapshot_fails_closed(monkeypatch, snapshot):
    install_snapshot(monkeypatch, snapshot)
    with pytest.raises(RuntimeError, match='owner game preflight failed'):
        capture.require_no_owner_game()


def test_cli_help_does_not_enumerate_processes_or_import_graphics(monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail('help entered game preflight')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(SystemExit) as exc:
        capture.main(['--help'])
    assert exc.value.code == 0


@pytest.mark.parametrize('flags', [{}, {'acceptance_complete': True},
    {'acceptance_complete': True, 'cleanup_complete': True},
    {'acceptance_complete': True, 'cleanup_complete': True, 'protected_files_unchanged': False}])
def test_incomplete_acceptance_cannot_write_passing_receipt(tmp_path, monkeypatch, flags):
    monkeypatch.setattr(capture, 'run', lambda args, report: report.update(flags))
    assert capture.main(['--out', str(tmp_path / 'capture')]) == 1
    report = json.loads((tmp_path / 'capture/notification-metrics.json').read_text())
    assert report['passed'] is False
    assert report['error']


def test_no_reuse_of_output_directory(tmp_path, monkeypatch):
    existing = tmp_path / 'notification-metrics.json'
    existing.write_text('owner artifact')
    monkeypatch.setattr(capture, 'run', lambda *a: pytest.fail('reused nonempty output'))
    with pytest.raises(SystemExit):
        capture.main(['--out', str(tmp_path)])
    assert existing.read_text() == 'owner artifact'


def test_ship_resolution_presets_are_read_from_production_source():
    presets = capture.shipped_resolutions()
    assert presets[0] == 'auto' and '1280x720' in presets and '2560x1440' in presets
    for size in ('1024x640', '1280x801'):
        assert size not in presets
    assert capture.shipped_resolutions(
        path=capture.ROOT / 'render/display_settings.py') == presets


def test_unshipped_resolution_is_refused_before_any_output_or_run(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, 'run', lambda *a: pytest.fail('ran an unshipped resolution'))
    out = tmp_path / 'capture'
    with pytest.raises(SystemExit) as exc:
        capture.main(['--out', str(out), '--width', '1024', '--height', '640'])
    assert exc.value.code == 2
    assert not out.exists()

