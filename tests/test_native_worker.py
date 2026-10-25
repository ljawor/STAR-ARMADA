"""CPU-only native process boundary tests; never load the GPU renderer."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from render_bridge import embedded
from render_bridge.native_worker import process_creation_time

ROOT = Path(__file__).resolve().parents[1]

STUB = r'''
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static void mark(const char *stage) {
  const char *wanted=getenv("ARMADA_STUB_STAGE"), *path=getenv("ARMADA_STUB_MARKER");
  if(wanted && path && !strcmp(stage,wanted)) {
    FILE *f=fopen(path,"w"); if(f) { fputs(stage,f); fclose(f); }
  }
}
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <process.h>
#define sleep(n) Sleep((n)*1000)
#define write _write
static void load_fault(void) { mark("load"); if(getenv("ARMADA_STUB_BLOCK_LOAD")) for(;;) sleep(1); }
BOOL WINAPI DllMain(HINSTANCE h, DWORD why, LPVOID reserved) {
  if(why==DLL_PROCESS_ATTACH) load_fault();
  return TRUE;
}
#else
#include <unistd.h>
__attribute__((constructor)) static void load_fault(void) {
  mark("load");
  if(getenv("ARMADA_STUB_BLOCK_LOAD")) for(;;) sleep(1);
}
#endif
static int mode;
static int framed;
unsigned armada_abi_version(void) { return ABI; }
void *armada_open(int n, char **v) {
  for(int i=0;i<n;i++) {
    if(!strcmp(v[i],"--mode")) mode=atoi(v[++i]);
    else if(!strcmp(v[i],"--input-ring") || !strcmp(v[i],"--missing-ring")) return 0;
  }
  mark("open");
  if(mode==5) for(;;) sleep(1);
  return (void*)1;
}
int armada_poll(void *h) {
  mark("poll");
  if(mode==8) for(;;) sleep(1);
  if(mode==9 && framed) _exit(9);
  return mode==7 ? 1 : 0;
}
int armada_frame(void *h, void *p, size_t n) {
  mark("frame");
  if(mode==1) _exit(4);
  if(mode==6 || mode==10) {
    char text[4096]; memset(text,'x',sizeof(text));
    for(int i=0;i<40;i++) write(1,text,sizeof(text));
    write(2,"DIAGNOSTIC-END",14);
    if(mode==6) _exit(6);
  }
  framed=1;
  if(mode==2) for(;;) sleep(1);
  if(mode==4) return -1;
  for(size_t i=0;i<n;i++) ((unsigned char*)p)[i]=(unsigned char)(i%251);
  return (int)n;
}
const char *armada_error(void *h) { return "injected terminal error"; }
void armada_close(void *h) { mark("close"); if(mode==3 || mode==4) for(;;) sleep(1); }
'''

class AbortDiagnosticTests(unittest.TestCase):
    """No native fixture: inject only the already-confirmed cleanup failure seam."""

    def test_abort_preserves_original_diagnostic_when_cleanup_fails(self):
        import threading
        window = object.__new__(embedded.EmbeddedWindow)
        window._owner = threading.get_ident()
        window._terminal = False
        window._process = Mock(returncode=4)
        window._tail = bytearray(b'last native diagnostic')
        reason = EOFError('original worker EOF')
        cleanup = PermissionError('frame.bgra is locked')
        with patch.object(window, '_stop', side_effect=cleanup) as stop:
            with self.assertRaises(Exception) as caught:
                window._abort(reason)
        stop.assert_called_once_with(hard=True)
        error = caught.exception
        self.assertIsInstance(error, RuntimeError, 'cleanup replaced the native failure')
        self.assertIs(error.__cause__, reason)
        self.assertIn('original worker EOF', str(error))
        self.assertIn('exitcode=4', str(error))
        self.assertIn('last native diagnostic', str(error))
        self.assertIn('cleanup failed', str(error))
        self.assertIn('PermissionError', str(error))
        self.assertIn('frame.bgra is locked', str(error))
        self.assertTrue(window._terminal)
        with patch.object(embedded, 'send', side_effect=AssertionError('terminal IO')):
            with self.assertRaisesRegex(RuntimeError, 'terminal'):
                window._request('frame')


class NativeWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        cls.base = Path(cls.directory.name)
        source = cls.base / 'stub.c'
        source.write_text(STUB)
        (cls.base / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.25)
project(ArmadaFaultStub C)
foreach(target stub bad)
  add_library(${target} SHARED stub.c)
  set_target_properties(${target} PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS TRUE)
endforeach()
target_compile_definitions(stub PRIVATE ABI=1)
target_compile_definitions(bad PRIVATE ABI=99)
''')
        build = cls.base / 'build'
        configure = ['cmake', '-S', str(cls.base), '-B', str(build)]
        if os.name == 'nt':
            # VS discovers its MSVC toolchain without cl/nmake on the shell PATH.
            configure += ['-G', 'Visual Studio 17 2022', '-A', 'x64']
        try:
            subprocess.run(configure,
                           check=True, capture_output=True, timeout=30)
            subprocess.run(['cmake', '--build', str(build), '--config', 'Release'],
                           check=True, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            cls.directory.cleanup()
            raise RuntimeError('Native CPU tests require CMake >=3.25 and a C compiler: '
                               + str(exc) + str(getattr(exc, 'stderr', b''))) from exc
        suffix = '.dll' if os.name == 'nt' else '.dylib' if sys.platform == 'darwin' else '.so'
        cls.library = next(build.rglob(('' if os.name == 'nt' else 'lib') + 'stub' + suffix))
        cls.bad_library = next(build.rglob(('' if os.name == 'nt' else 'lib') + 'bad' + suffix))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def window(self, mode=0, extra=()):
        with patch.dict(os.environ, STAR_ARMADA_CPP_LIBRARY=str(self.library)), \
                patch.object(ctypes, 'CDLL', side_effect=AssertionError('parent loaded native code')):
            window = embedded.EmbeddedWindow(['viewer', '--width', '320', '--height', '240',
                                              '--mode', str(mode), *extra], root=ROOT)
        self.addCleanup(window.kill)
        return window

    def test_real_child_frames_preserve_bytes_and_cleanup(self):
        window = self.window()
        process = window._process
        directory = Path(window._temporary.name)
        for _ in range(3):
            self.assertEqual(window._request('frame')['count'], 320 * 240 * 4)
            self.assertEqual(bytes(window._pixels[:1000]), bytes(i % 251 for i in range(1000)))
        window.terminate()
        self.assertIsNotNone(process.poll())
        self.assertFalse(directory.exists())
        window.terminate()

    def test_optional_missing_and_input_streams_are_removed_in_worker(self):
        window = self.window(extra=('--input-ring', str(self.library), '--missing-ring',
                                    str(self.base / 'absent')))
        self.assertIsNone(window.poll())

    def test_native_stdout_is_drained_and_diagnostics_are_bounded(self):
        window = self.window(6)
        mapping = window._mapping
        assert mapping is not None and window._temporary is not None
        assert window._process is not None
        directory = Path(window._temporary.name)
        self.assertFalse(mapping.closed)
        self.assertTrue((directory / 'frame.bgra').is_file())
        with self.assertRaisesRegex(RuntimeError, 'exitcode=6') as error:
            window._request('frame')
        self.assertEqual(window._process.poll(), 6)
        self.assertTrue(mapping.closed)
        self.assertIsNone(window._mapping)
        self.assertFalse(directory.exists())
        self.assertTrue(window._terminal)
        self.assertLessEqual(len(window._tail), 8192)
        self.assertIn('DIAGNOSTIC-END', str(error.exception))
        self.assertLess(len(str(error.exception)), 8500)
        window.kill()
        window.terminate()
        self.assertFalse(directory.exists())

    def test_log_disk_failure_still_drains_a_healthy_frame(self):
        window = self.window(10)
        started = time.monotonic()
        with patch.object(Path, 'write_bytes', side_effect=OSError('disk full')) as write, \
                patch.object(embedded, 'FRAME_TIMEOUT', .5):
            self.assertEqual(window._request('frame')['count'], 320 * 240 * 4)
        self.assertLess(time.monotonic() - started, 3)
        self.assertTrue(write.called)
        self.assertIsNone(window._process.poll())
        self.assertFalse(window._terminal)
        self.assertLessEqual(len(window._tail), 8192)
        self.assertIsNone(window.poll())

    def test_invalid_nonce_kills_real_child_and_cleans_startup(self):
        import json
        command = '''import json,socket,sys,time
c=json.load(open(sys.argv[1]))
s=socket.create_connection(('127.0.0.1',c['port']))
s.sendall(b'{"nonce":"wrong"}\\n')
time.sleep(30)
'''
        children = []
        original = subprocess.Popen
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs); children.append(child); return child
        with patch.dict(os.environ, STAR_ARMADA_CPP_LIBRARY=str(self.library)), \
                patch.object(embedded, 'worker_command', side_effect=lambda path:
                             [sys.executable, '-c', command, str(path)]), \
                patch.object(embedded.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaisesRegex(RuntimeError, 'authentication'):
                embedded.EmbeddedWindow(['viewer'], root=ROOT)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())

    def test_native_poll_exit_also_reaps_worker(self):
        window = self.window(7)
        self.assertIsNotNone(window.poll())
        self.assertIsNotNone(window._process.poll())
        self.assertIsNone(window._mapping)

    def test_fatal_exit_is_contained_and_terminal(self):
        window = self.window(1)
        mapping = window._mapping
        assert mapping is not None and window._temporary is not None
        assert window._process is not None
        directory = Path(window._temporary.name)
        self.assertFalse(mapping.closed)
        self.assertTrue((directory / 'frame.bgra').is_file())
        with self.assertRaisesRegex(RuntimeError, 'exitcode=4'):
            window._request('frame')
        self.assertEqual(window._process.poll(), 4)
        self.assertTrue(window._terminal)
        with self.assertRaisesRegex(RuntimeError, 'terminal'):
            window.present()
        self.assertTrue(mapping.closed)
        self.assertIsNone(window._mapping)
        self.assertFalse(directory.exists())
        window.kill()
        window.terminate()
        self.assertEqual(window._process.poll(), 4)
        self.assertFalse(directory.exists())

    def test_blocked_frame_is_killed_and_reaped(self):
        window = self.window(2)
        start = time.monotonic()
        with patch.object(embedded, 'FRAME_TIMEOUT', .15), self.assertRaises(RuntimeError):
            window._request('frame')
        self.assertLess(time.monotonic() - start, 3)
        self.assertIsNotNone(window._process.poll())
        self.assertIsNone(window._mapping)

    def test_terminal_error_is_sent_before_blocked_close(self):
        window = self.window(4)
        start = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'injected terminal error'):
            window._request('frame')
        self.assertLess(time.monotonic() - start, 3)
        self.assertIsNotNone(window._process.poll())

    def test_shutdown_uses_one_absolute_grace_deadline(self):
        window = self.window()
        original = embedded.send
        def slow_send(*args):
            time.sleep(.08)
            return original(*args)
        with patch.object(embedded, 'SHUTDOWN_GRACE', 1.0), \
                patch.object(embedded, 'send', side_effect=slow_send), \
                patch.object(window._process, 'wait', wraps=window._process.wait) as wait:
            window.terminate()
        self.assertLess(wait.call_args_list[0].kwargs['timeout'], .99)

    def test_blocked_close_is_killed_and_reaped(self):
        window = self.window(3)
        start = time.monotonic()
        with patch.object(embedded, 'SHUTDOWN_GRACE', .15):
            window.terminate()
        self.assertLess(time.monotonic() - start, 3)
        self.assertIsNotNone(window._process.poll())
        self.assertIsNone(window._mapping)

    def test_wait_timeout_and_wrong_thread_do_no_io(self):
        import threading
        window = self.window()
        with self.assertRaises(subprocess.TimeoutExpired):
            window.wait(timeout=.02)
        errors = []
        def wrong_thread():
            for method in (window.poll, window.present, window.terminate, window.wait, window.kill):
                try:
                    method()
                except RuntimeError as exc:
                    errors.append(str(exc))
        with patch.object(embedded, 'send', side_effect=AssertionError('unexpected IO')):
            thread = threading.Thread(target=wrong_thread)
            thread.start(); thread.join(timeout=2)
        self.assertEqual(len(errors), 5)
        self.assertTrue(all('creator thread' in message for message in errors))
        self.assertIsNone(window.poll())

    def test_bad_abi_and_partial_startup_cleanup(self):
        bad = self.bad_library
        original = subprocess.Popen
        processes = []
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs); processes.append(child); return child
        before = set(Path(tempfile.gettempdir()).glob('armada-worker-*'))
        for library, mode in ((bad, 0), (self.library, 5)):
            with patch.dict(os.environ, STAR_ARMADA_CPP_LIBRARY=str(library)), \
                    patch.object(embedded, 'STARTUP_TIMEOUT', .3), \
                    patch.object(embedded.subprocess, 'Popen', side_effect=spawn):
                with self.assertRaises(RuntimeError):
                    embedded.EmbeddedWindow(['viewer', '--mode', str(mode)], root=ROOT)
        self.assertTrue(all(child.poll() is not None for child in processes))
        self.assertEqual(before, set(Path(tempfile.gettempdir()).glob('armada-worker-*')))

    def test_dribble_cannot_extend_absolute_deadline(self):
        import socket
        import threading
        from render_bridge.native_worker import receive
        reader, writer = socket.socketpair()
        def dribble():
            try:
                for byte in b'{"ready":true}\n':
                    writer.send(bytes([byte])); time.sleep(.035)
            except OSError:
                pass
        thread = threading.Thread(target=dribble)
        start = time.monotonic()
        thread.start()
        try:
            with self.assertRaises(TimeoutError):
                receive(reader, start + .1)
            self.assertLess(time.monotonic() - start, .3)
        finally:
            reader.close(); writer.close(); thread.join(timeout=1)

    def test_source_and_frozen_command_and_real_native_probe(self):
        import json
        from game import __version__
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(embedded.worker_command('/owned/config'),
                [sys.executable, '-u', '-m', 'render_bridge.native_worker', '/owned/config'])
        with patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(embedded.worker_command('/owned/config'),
                [sys.executable, '--native-render-worker', '/owned/config'])
        output = self.base / 'probe.json'
        env = dict(os.environ, STAR_ARMADA_CPP_LIBRARY=str(self.library))
        result = subprocess.run([sys.executable, '-m', 'render_bridge.native_worker',
                                 '--probe', '--output', str(output)], env=env, timeout=5,
                                 capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text()), dict(status='ok', abi=1,
            version=__version__, frozen=False, native_library=str(self.library)))

    def test_probe_reads_the_single_game_version_authority(self):
        import json
        output = self.base / 'patched-version-probe.json'
        # The real CLI loads a DLL. Keep that lifetime inside a fresh process so
        # Windows can remove the compiled fixture after the child has exited.
        command = '''import sys
from unittest.mock import patch
import game
from render_bridge.native_worker import cli
with patch.object(game, '__version__', '9.8.7-test'):
    raise SystemExit(cli(sys.argv[1:]))
'''
        env = dict(os.environ, STAR_ARMADA_CPP_LIBRARY=str(self.library))
        result = subprocess.run([sys.executable, '-c', command, '--probe',
                                 '--output', str(output)], cwd=ROOT, env=env,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text()), dict(status='ok', abi=1,
            version='9.8.7-test', frozen=False, native_library=str(self.library)))

    def test_configuration_rejects_inconsistent_argv_dimensions_before_load(self):
        import json
        from render_bridge.native_worker import configuration
        frame = self.base / 'config-frame'
        frame.write_bytes(bytes(320 * 240 * 4))
        config = self.base / 'config.json'
        value = dict(port=1234, nonce='a'*64, library=str(self.library), frame=str(frame), parent_pid=os.getpid(), parent_creation_time=process_creation_time(),
                     width=320, height=240, argv=['viewer', '--width', '7680', '--height', '4320'])
        config.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            configuration(config)

    def test_idle_worker_exits_on_parent_socket_eof(self):
        window = self.window()
        window._connection.close()
        self.assertEqual(window._process.wait(timeout=2), 0)
        window.kill()

    def assert_parent_death_contained(self, stage, mode):
        import signal
        driver = r'''
import os, sys, time, subprocess
from pathlib import Path
from unittest.mock import patch
from render_bridge import embedded
pidfile, marker, stage, mode = sys.argv[1:]
original = subprocess.Popen
def spawn(*args, **kwargs):
    child = original(*args, **kwargs)
    Path(pidfile).write_text(str(child.pid))
    return child
with patch.object(embedded.subprocess, 'Popen', side_effect=spawn):
    window = embedded.EmbeddedWindow(['viewer','--width','320','--height','240',
                                     '--mode',mode,'--ring',str(Path(pidfile).parent/'ring')], root=os.getcwd())
if stage == 'idle': Path(marker).write_text('idle')
elif stage == 'close': window.terminate()
elif stage in ('frame', 'poll'): window._request(stage)
time.sleep(30)
'''
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            base = Path(temp)
            pidfile, marker = base / 'pid', base / 'entered'
            env = dict(os.environ, STAR_ARMADA_CPP_LIBRARY=str(self.library),
                       ARMADA_STUB_STAGE=stage, ARMADA_STUB_MARKER=str(marker))
            if stage == 'load':
                env['ARMADA_STUB_BLOCK_LOAD'] = '1'
            parent = subprocess.Popen([sys.executable, '-c', driver, str(pidfile),
                str(marker), stage, str(mode)], cwd=ROOT, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                **({} if os.name == 'nt' else {'start_new_session': True}))
            pid = handle = None
            kernel = None
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline and parent.poll() is None:
                    time.sleep(.02)
                if pidfile.exists():
                    pid = int(pidfile.read_text())
                self.assertIsNotNone(pid, 'driver did not publish worker PID')
                if os.name == 'nt':
                    from ctypes import wintypes
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    kernel.OpenProcess.restype = wintypes.HANDLE
                    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                    kernel.WaitForSingleObject.restype = wintypes.DWORD
                    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                    handle = kernel.OpenProcess(0x100000 | 1 | 0x1000, False, pid)
                    self.assertTrue(handle, 'cannot hold worker process identity')
                self.assertTrue(marker.exists(), f'worker never reached {stage}')
                if os.name != 'nt':
                    self.assertEqual(os.getpgid(pid), pid, 'worker must be outside parent group')
                parent.kill()
                parent.wait(timeout=2)
                def exited():
                    if handle:
                        return kernel.WaitForSingleObject(handle, 0) == 0
                    result = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                        capture_output=True, text=True, timeout=1)
                    status = result.stdout.strip()
                    return not status or status.startswith('Z')
                deadline = time.monotonic() + 3
                while not exited() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(exited(), f'orphan worker {pid} still running in {stage}')
                if handle and stage != 'idle':
                    code = wintypes.DWORD()
                    self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
                    self.assertEqual(code.value, 70)
            finally:
                if parent.poll() is None:
                    parent.kill()
                parent.communicate(timeout=2)
                if pid is None and pidfile.exists():
                    pid = int(pidfile.read_text())
                if handle:
                    if kernel.WaitForSingleObject(handle, 0) != 0:
                        kernel.TerminateProcess(handle, 71)
                        kernel.WaitForSingleObject(handle, 2000)
                    kernel.CloseHandle(handle)
                elif pid is not None:
                    try:
                        os.kill(pid, signal.SIGTERM if os.name == 'nt' else signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_parent_death_idle(self):
        self.assert_parent_death_contained('idle', 0)

    def test_parent_death_blocked_library_load(self):
        self.assert_parent_death_contained('load', 0)

    def test_parent_death_blocked_open(self):
        self.assert_parent_death_contained('open', 5)

    def test_parent_death_blocked_frame(self):
        self.assert_parent_death_contained('frame', 2)

    def test_parent_death_blocked_poll(self):
        self.assert_parent_death_contained('poll', 8)

    def test_parent_death_blocked_close(self):
        self.assert_parent_death_contained('close', 3)

    def test_parent_configuration_is_strict_and_old_schema_is_rejected(self):
        import json
        from render_bridge.native_worker import configuration
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
            base = Path(temp)
            frame = base / 'frame'
            frame.write_bytes(bytes(320 * 240 * 4))
            path = base / 'config.json'
            value = dict(port=1234, nonce='a'*64, library=str(self.library), frame=str(frame),
                parent_pid=os.getpid(), parent_creation_time=process_creation_time(), width=320, height=240,
                argv=['viewer', '--width', '320', '--height', '240'])
            path.write_text(json.dumps(value))
            self.assertEqual(configuration(path)['parent_pid'], os.getpid())
            for invalid in (True, '123', 0, -1, 0x100000000, None):
                with self.subTest(parent_pid=invalid):
                    path.write_text(json.dumps(dict(value, parent_pid=invalid)))
                    with self.assertRaisesRegex(ValueError, 'parent_pid'):
                        configuration(path)
            del value['parent_pid']
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'configuration fields'):
                configuration(path)

    def test_guard_rejects_wrong_direct_parent_before_library_load(self):
        from render_bridge.native_worker import parent_guard
        with self.assertRaisesRegex(RuntimeError, 'direct parent identity'):
            with parent_guard(os.getpid()):
                self.fail('wrong parent allowed')

    def test_invalid_configuration_and_cli_fail_without_native_load(self):
        from render_bridge.native_worker import cli
        with patch.object(ctypes, 'CDLL', side_effect=AssertionError('native load')):
            for argv in ([], ['--bogus'], ['--probe'], ['/missing/config']):
                with self.assertRaises(SystemExit) as error:
                    cli(argv)
                self.assertNotEqual(error.exception.code, 0)

if __name__ == '__main__':
    unittest.main()
