"""GPU-free native release payload and frozen-bundle contracts."""
from pathlib import Path
import importlib.util
import tempfile
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/build_native_release.py'


class ReleasePackagingTests(unittest.TestCase):
    def tool(self):
        self.assertTrue(TOOL.is_file(), 'native release builder is missing')
        spec = importlib.util.spec_from_file_location('native_release', TOOL)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self, platform='darwin', multi=False):
        tool = self.tool()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        products = root / 'Release' if multi else root
        products.mkdir(exist_ok=True)
        for name in tool.product_names(platform):
            (products / name).write_bytes(b'native-fixture')
        (root / 'shaders').mkdir()
        for name in tool.SHADERS:
            (root / 'shaders' / name).write_bytes(b'compiled-shader-fixture')
        return tool, root

    def test_missing_payload_fails_before_packaging(self):
        tool = self.tool()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'Missing native'):
                tool.native_payload(Path(temp), 'darwin', imports=lambda p: set())

    def test_multiconfig_release_stages_actual_windows_products(self):
        tool, root = self.fixture('win32', multi=True)
        tool.stage_products(root, 'win32')
        binaries, data = tool.native_payload(root, 'win32', imports=lambda p: set())
        self.assertEqual({Path(p).name for p, dest in binaries},
                         {'armada_viewer.exe', 'armada_embedded.dll'})
        self.assertTrue(all(dest == 'cpp' and Path(p).read_bytes() == b'native-fixture'
                            for p, dest in binaries))
        self.assertEqual(len(data), 18)
        self.assertTrue(all(dest == 'cpp/shaders' and Path(p).is_file() for p, dest in data))

    def test_shader_missing_or_empty_fails_closed(self):
        tool, root = self.fixture()
        (root / 'shaders' / tool.SHADERS[-1]).write_bytes(b'')
        with self.assertRaisesRegex(RuntimeError, 'Missing native'):
            tool.native_payload(root, 'darwin', imports=lambda p: set())

    def test_recursive_runtime_dependencies_are_real_included_files(self):
        tool, root = self.fixture()
        dep = root / 'libSDL3.dylib'
        child = root / 'libchild.dylib'
        dep.write_bytes(b'SDL'); child.write_bytes(b'child')
        def imports(path):
            return {('libchild.dylib', str(child))} if Path(path) == dep else (
                set() if Path(path) == child else {('libSDL3.dylib', str(dep))})
        binaries, _ = tool.native_payload(root, 'darwin', imports=imports)
        self.assertEqual({Path(p).name for p, _ in binaries},
                         {*tool.product_names('darwin'), dep.name, child.name})
        self.assertTrue(all(Path(p).is_file() for p, _ in binaries))

    def test_unresolved_non_system_dependency_fails_closed(self):
        tool, root = self.fixture()
        with self.assertRaisesRegex(RuntimeError, 'Unresolved native dependency'):
            tool.native_payload(root, 'darwin', imports=lambda p: {('libMissing.dylib', None)})

    def test_release_commands_preserve_existing_cache_and_build_all_targets(self):
        tool = self.tool()
        commands = tool.build_commands(ROOT, ROOT / 'render_cpp/build-w02', jobs=2)
        self.assertIn('-DCMAKE_BUILD_TYPE=Release', commands[0])
        self.assertNotIn('--fresh', commands[0])
        self.assertFalse(any('ARMADA_BGFX_PREFIX' in value for value in commands[0]))
        self.assertIn('--config', commands[1]); self.assertIn('Release', commands[1])
        self.assertNotIn('--target', commands[1])
        self.assertIn('--no-tests=error', commands[2])
        self.assertIn('Release', commands[2])

    def test_fresh_configure_uses_pinned_sdl_source_not_host_package(self):
        tool = self.tool()
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp)
            fresh = tool.build_commands(ROOT, build)[0]
            self.assertIn('-DCMAKE_DISABLE_FIND_PACKAGE_SDL3=ON', fresh)
            (build / 'CMakeCache.txt').write_text('SDL3_DIR:PATH=/existing/package\n')
            existing = tool.build_commands(ROOT, build)[0]
            self.assertNotIn('-DCMAKE_DISABLE_FIND_PACKAGE_SDL3=ON', existing)

    def test_frozen_validator_checks_actual_payload_and_shaders(self):
        tool, build = self.fixture()
        binaries, data = tool.native_payload(build, 'darwin', imports=lambda p: set())
        tool.write_manifest(build, binaries, data, 'darwin')
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            bundle = Path(temp)
            (bundle / 'cpp/shaders').mkdir(parents=True)
            for source, dest in binaries + data:
                shutil.copy2(source, bundle / dest / Path(source).name)
            shutil.copy2(build / 'native-release.json', bundle / 'cpp/native-release.json')
            tool.validate_frozen(bundle, 'darwin')
            (bundle / 'cpp' / tool.product_names('darwin')[1]).unlink()
            with self.assertRaisesRegex(RuntimeError, 'Missing native'):
                tool.validate_frozen(bundle, 'darwin')

    def test_spec_passes_actual_mac_files_and_runtime_graph_to_analysis(self):
        self._check_spec('darwin')

    def test_spec_passes_actual_windows_files_and_runtime_graph_to_analysis(self):
        self._check_spec('win32')

    def _check_spec(self, platform):
        import runpy
        import sys
        from types import ModuleType
        from unittest.mock import patch
        tool, build = self.fixture(platform)
        fake_root = build / 'project'
        (fake_root / 'tools').mkdir(parents=True)
        (fake_root / 'game').mkdir()
        (fake_root / 'game/__init__.py').write_text('__version__ = "1.0.0"\n')
        for package in ('render', 'render_bridge'):
            (fake_root / package).mkdir()
            (fake_root / package / '__init__.py').write_text('')
            (fake_root / package / 'controller.py').write_text('')
        (fake_root / 'render_bridge/newly_added.py').write_text('')
        import shutil
        shutil.copy2(TOOL, fake_root / 'tools/build_native_release.py')
        target = fake_root / 'render_cpp/build-w02'
        target.parent.mkdir(parents=True)
        (target / 'shaders').mkdir(parents=True)
        for name in tool.SHADERS:
            shutil.copy2(build / 'shaders' / name, target / 'shaders' / name)
        for name in tool.product_names(platform):
            shutil.copy2(build / name, target / name)
        captured = {}
        class StopAnalysis(Exception):
            pass
        def analysis(*args, **kwargs):
            captured.update(kwargs)
            raise StopAnalysis
        hooks = ModuleType('PyInstaller.utils.hooks')
        hooks.collect_submodules = lambda package: [package, package + '.controller']
        deps = ModuleType('PyInstaller.depend')
        deps.bindepend = ModuleType('bindepend')
        deps.bindepend.get_imports = lambda *a, **kw: set()
        deps.dylib = ModuleType('dylib')
        deps.dylib.include_library = lambda path: True
        with patch.dict(sys.modules, {'PyInstaller.utils.hooks': hooks, 'PyInstaller.depend': deps}), patch.object(sys, 'platform', platform):
            with self.assertRaises(StopAnalysis):
                runpy.run_path(str(ROOT / 'star_armada.spec'), init_globals={
                    'SPECPATH': str(fake_root), 'Analysis': analysis})
        self.assertEqual({Path(p).name for p, _ in captured['binaries']},
                         set(tool.product_names(platform)))
        for path, destination in captured['binaries']:
            self.assertTrue(Path(path).is_file()); self.assertEqual(destination, 'cpp')
        shaders = [(p, d) for p, d in captured['datas'] if d == 'cpp/shaders']
        self.assertEqual(len(shaders), 18)
        self.assertTrue(all(Path(path).is_file() for path, _ in shaders))
        self.assertIn('render_bridge.newly_added', captured['hiddenimports'])
        self.assertIn('render_bridge.controller', captured['hiddenimports'])
        self.assertIn('render.controller', captured['hiddenimports'])
        (target / tool.product_names(platform)[1]).unlink()
        with patch.dict(sys.modules, {'PyInstaller.utils.hooks': hooks, 'PyInstaller.depend': deps}), patch.object(sys, 'platform', platform):
            with self.assertRaisesRegex(RuntimeError, 'Missing native'):
                runpy.run_path(str(ROOT / 'star_armada.spec'), init_globals={
                    'SPECPATH': str(fake_root), 'Analysis': analysis})


class WindowsCompilerImageTests(unittest.TestCase):
    def test_every_windows_job_pins_cmake_compatible_visual_studio_image(self):
        import re
        jobs = {}
        for workflow in ('release.yml', 'windows-signal.yml'):
            source = (ROOT / '.github/workflows' / workflow).read_text(encoding='utf-8')
            for match in re.finditer(r'^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)',
                                     source, re.MULTILINE | re.DOTALL):
                name, body = match.groups()
                if re.search(r'^    runs-on: windows-', body, re.MULTILINE):
                    jobs[(workflow, name)] = body
        self.assertEqual(set(jobs), {('release.yml', 'win'),
                                     ('windows-signal.yml', 'windows-lan'),
                                     ('windows-signal.yml', 'package-windows')})
        for job, body in jobs.items():
            with self.subTest(job=job):
                # cmake 3.31 cannot discover the VS 2026 compiler on windows-latest.
                self.assertIn('    runs-on: windows-2022\n', body)
                self.assertIn('      CMAKE_GENERATOR: Visual Studio 17 2022\n', body)
                self.assertIn('      CMAKE_GENERATOR_PLATFORM: x64\n', body)


class WindowsRuntimeGateTests(unittest.TestCase):
    def _workflow(self):
        return (ROOT / '.github/workflows/windows-signal.yml').read_text(encoding='utf-8')

    def _step(self, source, name):
        block = re.search(r'      - name: ' + re.escape(name) + r'\n(.*?)(?=      - |\n  [a-z]|\Z)',
                          source, re.DOTALL)
        self.assertIsNotNone(block, f'workflow step is missing: {name}')
        return block.group(1)

    def test_windows_runs_every_portable_renderer_case_without_skips(self):
        body = self._step(self._workflow(), 'Portable renderer transport on real Windows')
        for module in ('test_render_camera', 'test_render_live', 'test_render_single_path',
                       'test_render_ring'):
            self.assertIn(f"'{module}'", body)
        # A skipped import or a partially loaded suite must not read as acceptance.
        self.assertIn('assert expected >= 39', body)
        self.assertIn('result.testsRun == expected', body)
        self.assertIn('not result.skipped', body)

    def test_windows_steps_the_native_source_contract(self):
        step = self._step(self._workflow(), 'Native input-ring source contract')
        self.assertIn('render_cpp/tests/test_native_transport_platform_contract.py', step)

    def test_windows_runs_the_worker_cleanup_diagnostic_tests_as_a_counted_gate(self):
        body = self._step(self._workflow(), 'Worker cleanup diagnostic tests')
        # Listed-but-empty and listed-but-skipped must not read as acceptance.
        self.assertIn("loadTestsFromName('test_windows_worker_diagnostic')", body)
        self.assertIn('assert expected >= 5', body)
        self.assertIn('result.testsRun == expected', body)
        self.assertIn('not result.skipped', body)

    def test_cleanup_diagnostic_can_fail_only_when_it_could_not_run(self):
        source = self._workflow()
        body = self._step(source, 'Observe native Windows worker cleanup')
        self.assertIn('if: always()', body)
        self.assertIn('tools/diag_windows_worker_cleanup.py --run --close-process-handle-hypothesis',
                      body)
        # Its findings are not the verdict, but a diagnostic that never launched is:
        # otherwise a broken tool is indistinguishable from a red baseline.
        self.assertNotRegex(body, r'(?m)^\s+continue-on-error:')
        # A red baseline and a tool that died on startup both exit nonzero, so the gate
        # demands the verdict frame the tool emits rather than an exit-code allowlist.
        self.assertNotIn('Select-String', body, 'do not match json.dumps spacing')
        self.assertIn('ConvertFrom-Json', body)
        # The baseline verdict is required on its own: a bare diagnostic_error means the
        # tool crashed, which must not pass as a red baseline.
        self.assertRegex(body, r"\$verdict = \$frames \| Where-Object \{ \$_\.stage -eq 'baseline_verdict' \}")
        self.assertIn("if (-not $verdict)", body)
        self.assertRegex(body, r'(?m)^\s+if \(-not \$verdict\) \{')
        self.assertIn('exit 1', body)
        self.assertNotIn('-eq 9009', body)
        # A crash after the verdict is still a broken observation; take the last verdict.
        self.assertIn('Select-Object -Last 1', body)
        # A watchdog exit or a sub-Python crash leaves a verdict but no error frame. The set is
        # asserted whole: `if ($code -notin 0, 1)` as a substring would also accept a widened
        # `0, 1, 2` or `0, 1, 124`, which is exactly the hole this gate exists to close.
        self.assertIn('if ($code -notin 0, 1) {', body)
        self.assertNotIn('0, 1, 2', body)
        self.assertNotRegex(body, r'-notin 0, 1,')
        self.assertRegex(body, r"if \(\$crashed\) \{ Write-Error '?\"?cleanup diagnostic crashed after")
        self.assertRegex(body, r'(?m)^\s+exit 0$')
        self.assertIn('GITHUB_STEP_SUMMARY', body)

    def test_cleanup_log_is_its_own_artifact_and_missing_is_an_error(self):
        source = self._workflow()
        block = re.search(r'      - uses: actions/upload-artifact@v4\n        if: always\(\)\n'
                          r'        with:\n          name: native-worker-cleanup-windows\n'
                          r'(.*?)(?=\n      - |\n  [a-z]|\Z)', source, re.DOTALL)
        self.assertIsNotNone(block, 'cleanup log artifact is missing')
        self.assertIn('path: native-worker-cleanup-windows.log', block.group(1))
        self.assertIn('if-no-files-found: error', block.group(1))

    def test_packaging_is_not_starved_by_a_red_lan_gate(self):
        source = self._workflow()
        job = re.search(r'  package-windows:\n(.*?)(?=\n  [a-z-]+:\n|\Z)', source, re.DOTALL)
        self.assertIsNotNone(job, 'package-windows job is missing')
        self.assertIn('needs: windows-lan', job.group(1))
        self.assertRegex(job.group(1), r"(?m)^    if: always\(\) && github\.event_name == 'workflow_dispatch'$")
        # ... but the upstream verdict must stay visible in the artifact and the job.
        self.assertIn('GATE-STATUS.txt', job.group(1))
        self.assertIn('needs.windows-lan.result', job.group(1))
        self.assertIn("star-armada-candidate-win${{ needs.windows-lan.result != 'success'", job.group(1))
        # Provenance: a verdict without a run is not attributable evidence. The values reach
        # the script through env (see test_no_step_interpolates_expressions_into_script_source).
        for field in ('COMMIT_SHA: ${{ github.sha }}', 'RUN_URL: ${{ github.server_url }}'):
            self.assertIn(field, job.group(1))
        self.assertIn('commit: $env:COMMIT_SHA', job.group(1))
        # The mark step must write where the zip reads, and before it compresses.
        self.assertLess(job.group(1).index('Mark the candidate with its gate verdict'),
                        job.group(1).index('Zip\n'), 'the verdict must be written before zipping')
        self.assertIn('Tee-Object -FilePath "dist/STAR ARMADA/GATE-STATUS.txt"', job.group(1))
        self.assertIn('-Path "dist/STAR ARMADA/*"', job.group(1))
        # The payload name carries the verdict too, so the file and the artifact agree.
        self.assertIn('STAR-ARMADA-candidate-win$suffix.zip', job.group(1))
        self.assertIn('path: dist/STAR-ARMADA-candidate-win*.zip', job.group(1))
        # Expressions reach the shell through env, never interpolated into script source.
        zip_step = self._step(source, 'Zip')
        self.assertIn('$env:GATE_VERDICT', zip_step)
        self.assertNotIn('${{', zip_step.split('run: |', 1)[1])
        self.assertRegex(job.group(1),
                         r"(?m)^      - name: Require a green LAN gate for a verified candidate\n"
                         r"        if: needs.windows-lan.result != 'success'")


    def test_the_windows_native_build_gets_the_cores_and_the_budget_it_needs(self):
        # The package job failed with a 25-minute timeout while two of the runner's four cores
        # sat idle, and the compile it was waiting on is third-party (SDL3/bgfx/bx/bimg from
        # source), not this repository. Pin the parallelism and a budget sized for a cold runner;
        # the per-test timeout stays where it is, so this cannot hide a slow test.
        body = self._step(self._workflow(), 'Build and test mandatory native renderer (Release)')
        self.assertIn('--jobs 4', body)
        timeout = re.search(r'timeout-minutes:\s*(\d+)', body)
        self.assertIsNotNone(timeout, 'the native build step has no timeout at all')
        self.assertGreaterEqual(int(timeout.group(1)), 40,
                                'a cold runner compiles pinned third-party deps before this repo')
        # ... and the test gate itself keeps its own, much tighter, limit.
        source = (ROOT / 'tools/build_native_release.py').read_text(encoding='utf-8')
        self.assertIn("'--timeout', '60'", source)

    def test_no_step_interpolates_expressions_into_script_source(self):
        """Workflow-wide: `${{ }}` is expanded before the shell sees the script.

        A commit value interpolated into a PowerShell string is a command-injection surface and an
        untestable one (the value is whatever the ref contains). One step was fixed at a time until
        this test existed; five instances survived in the same job and the receipt said "the last".
        """
        source = self._workflow()
        offenders = []
        step = None
        inside_run = False
        indent = None
        body_indent = None
        for number, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if re.match(r'^ {4,8}- (name|uses):', line):
                # ... but only outside a run block, or for a line indented less than that block's
                # body: a script line that happens to look like a step (a dash plus `name:`) is
                # still script, and treating it as a boundary leaves the rest of the block
                # unscanned - the same hole as the `- ` check below, one indentation deeper.
                here_now = len(line) - len(line.lstrip())
                if not inside_run or here_now < (body_indent or 0):
                    step, inside_run, indent, body_indent = stripped, False, None, None
                    continue
            if re.match(r'^ {0,6}(jobs|[a-z-]+):$', line):
                step = None
            match = re.match(r'^(\s*)run:(.*)$', line)
            if match:
                rest = match.group(2).strip()
                # A one-line `run: cmd` has no body: the script is that line, and the next
                # indented line belongs to the step's other keys (`env:`, `if:`), not to it.
                if rest and rest not in ('|', '>', '|-', '>-', '|+', '>+'):
                    if '${{' in rest:
                        offenders.append((number, step, rest[:80]))
                    inside_run, body_indent = False, None
                    continue
                inside_run, indent, body_indent = True, len(match.group(1)), None
                continue
            if inside_run:
                # A block scalar does not end at its first `- name:`-looking line: it ends at the
                # first line indented less than its body. Ending on `- ` anywhere let a script
                # line that begins with a dash stop the scan, so the rest of that block went
                # unchecked - a hole wide enough to hide the very thing this test is for.
                if not stripped:
                    continue
                here = len(line) - len(line.lstrip())
                if body_indent is None:
                    body_indent = here
                if here < body_indent:
                    inside_run = False
                    continue
                if '${{' in line:
                    offenders.append((number, step, stripped[:80]))
        self.assertEqual(offenders, [],
                         'expressions interpolated into script source: '
                         + '; '.join(f'line {n} in {s_}: {text}' for n, s_, text in offenders))


class ShaderIncludePathContractTests(unittest.TestCase):
    def test_the_shader_include_dir_is_derived_from_the_fetched_tree(self):
        # The Windows package job failed with "Could not open include file 'bgfx_shader.sh'": the
        # from-source branch passed `${BGFX_DIR}/src`, a variable bgfx.cmake sets in its own
        # directory scope, so it expanded to `/src` there. Local builds never hit it because they
        # use the prebuilt shaderc, which is exactly why the path has to be asserted statically.
        source = (ROOT / 'render_cpp' / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertNotIn('set(ARMADA_BGFX_SHADER_INCLUDE "${BGFX_DIR}/src")', source,
                         'the include dir is guessed from a variable that is empty in this scope')
        self.assertIn('_deps/bgfx_source-src/src', source)
        self.assertIn('EXISTS "${candidate}/bgfx_shader.sh"', source)
        self.assertIn('bgfx_shader.sh is not under', source,
                      'nothing refuses to build with an include path that cannot hold the header')


class WindowsMathConstantContractTests(unittest.TestCase):
    def test_native_build_defines_msvc_math_constants(self):
        # Static contract only: MSVC hides M_PI behind _USE_MATH_DEFINES, and the POSIX
        # build cannot observe that. Actual proof is the Windows package job compiling it.
        source = (ROOT / 'render_cpp' / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('add_compile_definitions(_USE_MATH_DEFINES)', source)


class FrozenProbeShellImportTests(unittest.TestCase):
    def test_actual_python_shell_preludes_import_checkout_from_temp_script(self):
        import os
        import subprocess
        import sys
        import textwrap
        from game import __version__
        for workflow in ('release.yml', 'windows-signal.yml'):
            with self.subTest(workflow=workflow):
                lines = (ROOT / '.github/workflows' / workflow).read_text().splitlines()
                marker = lines.index('        shell: python')
                self.assertEqual(lines[marker + 1], '        run: |')
                end = next(i for i in range(marker + 2, len(lines))
                           if lines[i].strip() == 'from game import __version__')
                prefix = textwrap.dedent('\n'.join(lines[marker + 2:end + 1]))
                compile(prefix, workflow, 'exec')
                with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as temp:
                    script = Path(temp) / 'github-python-shell.py'
                    script.write_text(prefix + '\nimport game\nprint(__version__)\nprint(game.__file__)\n')
                    env = dict(os.environ, GITHUB_WORKSPACE=str(ROOT))
                    env.pop('PYTHONPATH', None)
                    result = subprocess.run([sys.executable, str(script)], cwd=ROOT,
                                            env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(),
                                 [__version__, str(ROOT / 'game/__init__.py')])


if __name__ == '__main__':
    unittest.main()
