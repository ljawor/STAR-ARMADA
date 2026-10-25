"""GPU-free native release payload and frozen-bundle contracts."""
from pathlib import Path
import importlib.util
import tempfile
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
    def _step(self, source, name):
        import re
        block = re.search(r'      - name: ' + re.escape(name) + r'\n(.*?)(?=      - |\Z)',
                          source, re.DOTALL)
        self.assertIsNotNone(block, f'workflow step is missing: {name}')
        return block.group(1)

    def test_windows_runs_every_portable_renderer_case_without_skips(self):
        source = (ROOT / '.github/workflows/windows-signal.yml').read_text(encoding='utf-8')
        body = self._step(source, 'Portable renderer transport on real Windows')
        for module in ('test_render_camera', 'test_render_live', 'test_render_single_path',
                       'test_render_ring'):
            self.assertIn(f"'{module}'", body)
        # A skipped import or a partially loaded suite must not read as acceptance.
        self.assertIn('assert expected >= 39', body)
        self.assertIn('result.testsRun == expected', body)
        self.assertIn('not result.skipped', body)

    def test_windows_steps_the_native_source_contract(self):
        source = (ROOT / '.github/workflows/windows-signal.yml').read_text(encoding='utf-8')
        step = self._step(source, 'Native input-ring source contract')
        self.assertIn('render_cpp/tests/test_native_transport_platform_contract.py', step)

    def test_cleanup_diagnostic_is_observation_and_keeps_its_artifact(self):
        source = (ROOT / '.github/workflows/windows-signal.yml').read_text(encoding='utf-8')
        body = self._step(source, 'Observe native Windows worker cleanup')
        self.assertIn('if: always()', body)
        self.assertIn('tools/diag_windows_worker_cleanup.py --run --close-process-handle-hypothesis',
                      body)
        # The handle retention it observes is still an open defect: a red baseline
        # must stay out of the job verdict and must not starve the packaging job.
        self.assertIn('continue-on-error: true', body)
        self.assertIn('$null -eq $code', body)
        self.assertIn('exit 0', body)
        self.assertIn('native-worker-cleanup-windows.log', body)
        self.assertIn('            native-worker-cleanup-windows.log\n', source)


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
