"""Authority-preserving pipeline execution; never invokes real Blender."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/art"))
import model_pipeline as pipeline


class PipelineExecutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.asset = {
            "binding": "imperial:corvette", "asset_id": "core:imperial/corvette",
            "authority": "script", "source": "art/blender/test.blend",
            "exporter": "tools/art/build_test.py", "export_script": None,
            "runtime": "assets/models/test.mesh.json",
            "expected_hashes": "art/manifests/approved.json", "expected_triangles": 1,
            "roles": ["base"],
        }
        self.cfg = {"assets": [self.asset]}
        self.opts = argparse.Namespace(keep_blend=False, blender_version="5.0.1")
        self.write("tools/art/build_test.py", "# seed\n")
        self.write("tools/art/export_test.py", "# open_mainfile: export only\n")
        self.write(self.asset["source"], "approved master")
        self.write(self.asset["runtime"], '{"triangle_count": 1}\n')
        self.pin()

    def write(self, relative, content):
        target = self.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def pin(self):
        self.write(self.asset["expected_hashes"], json.dumps({
            self.asset[k]: pipeline.sha256_file(self.repo / self.asset[k])
            for k in ("source", "runtime")
        }))

    def test_failed_wrapper_exports_never_publish_or_attest_repository_bytes(self):
        for authority in ("script", "blend"):
            for failure, code in (("bad-output", "E_RUNTIME_HASH"),
                                  ("exit-after-write", "E_BUILD_FAILED"),
                                  ("no-op", "E_BUILD_FAILED")):
                with self.subTest(authority=authority, failure=failure):
                    self.asset.update(authority=authority, export_script="tools/art/export_test.py")
                    self.write(self.asset["source"], "approved master")
                    self.write(self.asset["runtime"], '{"triangle_count": 1}\n')
                    self.pin()
                    before = {k: (self.repo / self.asset[k]).read_bytes()
                              for k in ("source", "runtime")}
                    # Actual subprocess wrapper: no Blender, no fabricated output.
                    self.write(self.asset["export_script"], '''from pathlib import Path
# open_mainfile: export-only wrapper control
root = Path(__file__).resolve().parents[2]
runtime = root / "assets/models/test.mesh.json"
''' + ('''runtime.parent.mkdir(parents=True, exist_ok=True)
runtime.write_text('{"triangle_count": 2}', encoding="utf-8")
''' if failure == "bad-output" else '''runtime.parent.mkdir(parents=True, exist_ok=True)
runtime.write_text('{"triangle_count": 99}\\n', encoding="utf-8")
raise SystemExit(9)
''' if failure == "exit-after-write" else ""))
                    with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed), \
                            mock.patch.object(pipeline, "write_provenance") as attest, \
                            mock.patch.object(pipeline, "resolve_blender", return_value="fake"), \
                            mock.patch.object(pipeline, "blender_version", return_value="5.0.1"), \
                            mock.patch.object(pipeline, "load_pipeline", return_value={
                                **self.cfg, "blender": {"pin": "5.0.1"}}), \
                            mock.patch.object(pipeline.Path, "cwd", return_value=self.repo), \
                            mock.patch("sys.stderr") as errors:
                        self.assertEqual(pipeline.main(["export-model", "--asset",
                                                        self.asset["binding"]]), 1)
                    self.assertIn(code, str(errors.write.call_args_list))
                    attest.assert_not_called()
                    for key, content in before.items():
                        self.assertEqual((self.repo / self.asset[key]).read_bytes(), content)

    def install_wrapper(self, extra=""):
        self.asset.update(export_script="tools/art/export_test.py",
                          export_args=["--asset", "ship:imperial:corvette", "", "value with spaces"])
        self.write("tools/art/wrapper_dependency.py", "PAYLOAD = '{\"triangle_count\": 1}\\n'\n")
        self.write(self.asset["export_script"], '''from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wrapper_dependency import PAYLOAD
# open_mainfile: export only
root = Path(__file__).resolve().parents[2]
source = root / "art/blender/test.blend"
assert source.read_bytes() == b"approved master"
assert sys.argv[sys.argv.index("--") + 1:] == ["--asset", "ship:imperial:corvette", "", "value with spaces"]
runtime = root / "assets/models/test.mesh.json"
assert not runtime.exists(), "an export must start without runtime bytes"
runtime.parent.mkdir(parents=True, exist_ok=True)
runtime.write_text(PAYLOAD, encoding="utf-8")
''' + extra)

    def test_wrapper_rejects_source_edits_without_publishing_or_provenance(self):
        for authority in ("script", "blend"):
            for failure in ("local-edit", "wrapper-edit"):
                with self.subTest(authority=authority, failure=failure):
                    self.asset["authority"] = authority
                    self.write(self.asset["source"], "approved master")
                    self.write(self.asset["runtime"], '{"triangle_count": 1}\n')
                    self.pin()
                    self.install_wrapper('source.write_text("wrapper mutated master", encoding="utf-8")\n'
                                         if failure == "wrapper-edit" else "")
                    if failure == "local-edit":
                        self.write(self.asset["source"], "user-edited master")
                    before = {k: (self.repo / self.asset[k]).read_bytes()
                              for k in ("source", "runtime")}
                    with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed) as run:
                        with self.assertRaises(pipeline.PipelineError) as caught:
                            pipeline.export_asset(self.repo, self.cfg, self.asset, "fake", self.opts)
                    self.assertEqual(caught.exception.code, "E_SOURCE_DRIFT")
                    if failure == "local-edit":
                        run.assert_not_called()
                    for key, content in before.items():
                        self.assertEqual((self.repo / self.asset[key]).read_bytes(), content)
                    self.assertIsNone(pipeline.provenance_state(self.repo, self.cfg, self.asset))

    def test_argument_arrays_reject_non_string_lists(self):
        for key in ("build_args", "export_args"):
            for bad in (None, "--asset imperial:corvette", {}, 7, [1], [False], [["--all"]]):
                with self.subTest(key=key, bad=bad):
                    self.asset[key] = bad
                    self.write(pipeline.PIPELINE_REL, json.dumps(self.cfg))
                    with self.assertRaises(pipeline.PipelineError) as caught:
                        pipeline.load_pipeline(self.repo)
                    self.assertEqual(caught.exception.code, "E_PIPELINE_SHAPE")
            self.asset.pop(key)

    def test_execution_forwards_exact_arguments_for_the_script_being_run(self):
        for authority, action, key, selector in (
                ("script", "build", "build_args", "ship:imperial:corvette"),
                ("script", "export", "build_args", "rebel:defense_satellite"),
                ("blend", "export", "export_args", "value with spaces")):
            with self.subTest(authority=authority, action=action):
                self.asset.update(authority=authority, build_args=["unused build"],
                                  export_args=["unused export"],
                                  export_script="tools/art/export_test.py" if authority == "blend" else None)
                self.asset[key] = ["--asset", selector, "", "--literal=quoted value"]
                with mock.patch.object(pipeline, "run_blender", return_value=(0, "")) as run:
                    pipeline._run_and_verify(self.repo, self.cfg, self.asset, "fake-blender",
                                             self.asset["export_script"] or self.asset["exporter"],
                                             self.opts, action)
                self.assertEqual(run.call_args.kwargs.get("argv"), self.asset[key])
                self.assertEqual(run.call_args.kwargs["cwd"], self.repo)

    def test_omitted_and_empty_argument_arrays_keep_legacy_execution(self):
        for value in (None, []):
            if value is not None:
                self.asset.update(build_args=value, export_args=value)
            self.write(pipeline.PIPELINE_REL, json.dumps(self.cfg))
            pipeline.load_pipeline(self.repo)
            with mock.patch.object(pipeline, "run_blender", return_value=(0, "")) as run:
                pipeline._run_and_verify(self.repo, self.cfg, self.asset, "fake-blender",
                                         self.asset["exporter"], self.opts, "build")
            self.assertEqual(list(run.call_args.kwargs.get("argv", ())), [])

    def install_seed(self):
        self.write("tools/art/seed_dependency.py", "PAYLOAD = '{\"triangle_count\": 1}\\n'\n")
        self.write(self.asset["exporter"], '''from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_dependency import PAYLOAD
root = Path(__file__).resolve().parents[2]
source = root / "art/blender/test.blend"
if source.exists():
    raise RuntimeError("editable master exists: refusing to overwrite")
assert sys.argv[sys.argv.index("--") + 1:] == ["--asset", "ship:imperial:corvette"]
source.parent.mkdir(parents=True, exist_ok=True)
source.write_text("regenerated nondeterministic blend", encoding="utf-8")
runtime = root / "assets/models/test.mesh.json"
runtime.parent.mkdir(parents=True, exist_ok=True)
runtime.write_text(PAYLOAD, encoding="utf-8")
''')
        self.asset["build_args"] = ["--asset", "ship:imperial:corvette"]
        self.write(pipeline.PIPELINE_REL, json.dumps(self.cfg))

    def python_seed(self, executable, script, argv=(), cwd=None):
        # Real subprocess/filesystem execution, but ordinary Python, not Blender.
        result = pipeline.subprocess.run([sys.executable, str(script), "--", *argv],
                                         cwd=cwd, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def test_script_build_reconstructs_in_isolation_preserving_approved_master(self):
        self.install_seed()
        master = self.repo / self.asset["source"]
        before = master.read_bytes()
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed) as run:
            record, payload = pipeline.build_asset(self.repo, self.cfg, self.asset,
                                                    "not-real-blender", self.opts)
        self.assertNotEqual(run.call_args.kwargs["cwd"], self.repo)
        self.assertEqual(run.call_args.kwargs["argv"], self.asset["build_args"])
        self.assertEqual(master.read_bytes(), before)
        self.assertEqual(record["source_sha256"], pipeline.sha256_file(master))
        self.assertTrue(record["matches_approved"])
        self.assertEqual(payload["triangle_count"], 1)
        self.assertFalse(Path(run.call_args.kwargs["cwd"]).exists())

    def test_script_source_drift_is_refused_before_reconstruction(self):
        self.install_seed()
        self.write(self.asset["source"], "unrecorded local edit")
        with mock.patch.object(pipeline, "run_blender", return_value=(0, "")) as run:
            with self.assertRaises(pipeline.PipelineError) as caught:
                pipeline.build_asset(self.repo, self.cfg, self.asset, "not-real-blender", self.opts)
        self.assertEqual(caught.exception.code, "E_SOURCE_DRIFT")
        run.assert_not_called()
        self.assertEqual((self.repo / self.asset["source"]).read_text(), "unrecorded local edit")

    def test_explicit_keep_blend_publishes_only_verified_script_build_source(self):
        self.install_seed()
        self.opts.keep_blend = True
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed):
            record, _ = pipeline.build_asset(self.repo, self.cfg, self.asset,
                                              "not-real-blender", self.opts)
        source = self.repo / self.asset["source"]
        self.assertEqual(source.read_text(), "regenerated nondeterministic blend")
        self.assertEqual(record["source_sha256"], pipeline.sha256_file(source))

    def test_script_reconstruction_requires_its_derived_source(self):
        self.install_seed()

        def runtime_only(executable, script, argv=(), cwd=None):
            assert cwd is not None
            runtime = Path(cwd) / self.asset["runtime"]
            runtime.parent.mkdir(parents=True, exist_ok=True)
            runtime.write_bytes((self.repo / self.asset["runtime"]).read_bytes())
            return 0, ""

        with mock.patch.object(pipeline, "run_blender", side_effect=runtime_only):
            with self.assertRaises(pipeline.PipelineError) as caught:
                pipeline.build_asset(self.repo, self.cfg, self.asset, "not-real-blender", self.opts)
        self.assertEqual(caught.exception.code, "E_BUILD_NO_SOURCE")

    def test_build_can_reconstruct_a_missing_script_derived_master(self):
        self.install_seed()
        source = self.repo / self.asset["source"]
        source.unlink()
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed):
            record, _ = pipeline.build_asset(self.repo, self.cfg, self.asset,
                                              "not-real-blender", self.opts)
        self.assertEqual(source.read_text(), "regenerated nondeterministic blend")
        self.assertEqual(record["source_sha256"], pipeline.sha256_file(source))

    def test_script_export_preserves_source_even_with_keep_blend(self):
        self.install_seed()
        self.opts.keep_blend = True
        source = self.repo / self.asset["source"]
        original = source.read_bytes()
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed) as run:
            record, _ = pipeline.export_asset(self.repo, self.cfg, self.asset,
                                               "not-real-blender", self.opts)
        self.assertNotEqual(run.call_args.kwargs["cwd"], self.repo)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(record["source_sha256"], pipeline.sha256_file(source))

    def test_failed_or_changed_reconstruction_publishes_nothing(self):
        self.install_seed()
        self.opts.keep_blend = True
        source = self.repo / self.asset["source"]
        runtime = self.repo / self.asset["runtime"]
        before = (source.read_bytes(), runtime.read_bytes())
        for action in (pipeline.build_asset, pipeline.export_asset):
            for failure in ("exit", "hash", "no-runtime"):
                with self.subTest(action=action.__name__, failure=failure):
                    def fail(executable, script, argv=(), cwd=None):
                        assert cwd is not None
                        self.python_seed(executable, script, argv, cwd)
                        output = Path(cwd) / self.asset["runtime"]
                        if failure == "hash":
                            output.write_text('{"triangle_count": 2}', encoding="utf-8")
                        if failure == "no-runtime":
                            output.unlink()
                        return (1 if failure == "exit" else 0), "intentional failure control"
                    with mock.patch.object(pipeline, "run_blender", side_effect=fail) as run:
                        with self.assertRaises(pipeline.PipelineError) as caught:
                            action(self.repo, self.cfg, self.asset, "not-real-blender", self.opts)
                    self.assertEqual(caught.exception.code,
                                     "E_RUNTIME_HASH" if failure == "hash" else "E_BUILD_FAILED")
                    self.assertEqual((source.read_bytes(), runtime.read_bytes()), before)
                    self.assertFalse(Path(run.call_args.kwargs["cwd"]).exists())

    def test_blend_authority_refuses_build_and_uses_export_wrapper_arguments(self):
        self.asset.update(authority="blend", build_args=["--replace-seed"], export_args=[],
                          export_script="tools/art/export_test.py")
        with mock.patch.object(pipeline, "run_blender", return_value=(0, "")) as run:
            with self.assertRaises(pipeline.PipelineError) as caught:
                pipeline.build_asset(self.repo, self.cfg, self.asset, "not-real-blender", self.opts)
            self.assertEqual(caught.exception.code, "E_WRONG_AUTHORITY")
            self.assertTrue(caught.exception.refused)
            run.assert_not_called()
        self.install_wrapper()
        self.asset["export_args"] = []
        wrapper = self.repo / self.asset["export_script"]
        wrapper.write_text(wrapper.read_text().replace(
            'assert sys.argv[sys.argv.index("--") + 1:] == ["--asset", "ship:imperial:corvette", "", "value with spaces"]',
            'assert sys.argv[sys.argv.index("--") + 1:] == []'), encoding="utf-8")
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed) as run:
            pipeline.export_asset(self.repo, self.cfg, self.asset, "not-real-blender", self.opts)
            workdir = run.call_args.kwargs["cwd"]
            self.assertNotEqual(workdir, self.repo)
            self.assertEqual(run.call_args.args[1], (workdir / self.asset["export_script"]).resolve())
            self.assertEqual(run.call_args.kwargs["argv"], [])
        self.write(self.asset["export_script"], "# open_mainfile save_as_mainfile\n")
        with mock.patch.object(pipeline, "run_blender") as run:
            with self.assertRaises(pipeline.PipelineError) as caught:
                pipeline.export_asset(self.repo, self.cfg, self.asset, "not-real-blender", self.opts)
            self.assertEqual(caught.exception.code, "E_EXPORT_WOULD_OVERWRITE_SOURCE")
            run.assert_not_called()

    def test_run_blender_preserves_argv_tokens_after_separator_without_shell(self):
        argv = ["--asset", "ship:imperial:corvette", "value with spaces", "", "; not a shell"]
        result = argparse.Namespace(returncode=0, stdout="out", stderr="err")
        with mock.patch.object(pipeline.subprocess, "run", return_value=result) as run:
            self.assertEqual(pipeline.run_blender("fake blender", "recipe.py", argv, self.repo),
                             (0, "outerr"))
        self.assertEqual(run.call_args.args[0], ["fake blender", "--background",
                         "--python-exit-code", "1", "--python", "recipe.py", "--", *argv])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_actual_b4_b6_seed_preflights_refuse_existing_selected_masters(self):
        for name, selector, identifier, guard in (
                ("build_b4_hardware.py", "rebel:defense_satellite", "alliance_defense_satellite",
                 "_refuse_existing_masters(_ARGV)"),
                ("build_b6_imperial_ships.py", "ship:imperial:corvette", "imperial_corvette",
                 "_refuse_existing_master(_ARGV)")):
            with self.subTest(seed=name):
                text = (ROOT / "tools/art" / name).read_text(encoding="utf-8")
                # Run the exact production preflight only, before its first Blender import.
                prefix = text[:text.index(guard) + len(guard)]
                master = self.write(f"art/blender/{identifier}.blend", "untouched")
                namespace = {"__file__": str(self.repo / "tools/art" / name)}
                with mock.patch.object(sys, "argv", [name, "--", "--asset", selector]):
                    with self.assertRaisesRegex(RuntimeError, "editable master"):
                        exec(compile(prefix, name, "exec"), namespace)
                    self.assertEqual(master.read_text(), "untouched")
                    master.unlink()
                    exec(compile(prefix, name, "exec"), namespace)

    def test_reconstruction_cannot_execute_an_absolute_original_recipe(self):
        self.install_seed()
        self.asset["exporter"] = str(self.repo / self.asset["exporter"])
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed) as run:
            with self.assertRaises(pipeline.PipelineError) as caught:
                pipeline.build_asset(self.repo, self.cfg, self.asset, "not-real-blender", self.opts)
        run.assert_not_called()
        self.assertEqual(caught.exception.code, "E_PATH")

    def test_seed_only_build_runs_export_wrapper_in_same_isolated_workspace(self):
        self.install_seed()
        self.asset["export_script"] = "tools/art/export_test.py"
        seed = self.repo / self.asset["exporter"]
        seed.write_text(seed.read_text().split('runtime = root /')[0], encoding="utf-8")
        self.write(self.asset["export_script"], '''from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_dependency import PAYLOAD
# open_mainfile: this wrapper is export-only
root = Path(__file__).resolve().parents[2]
assert (root / "art/blender/test.blend").read_text() == "regenerated nondeterministic blend"
assert sys.argv[sys.argv.index("--") + 1:] == ["--output-mode", "runtime only"]
runtime = root / "assets/models/test.mesh.json"
runtime.parent.mkdir(parents=True, exist_ok=True)
runtime.write_text(PAYLOAD, encoding="utf-8")
''')
        self.asset["export_args"] = ["--output-mode", "runtime only"]
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed) as run:
            record, _ = pipeline.build_asset(self.repo, self.cfg, self.asset,
                                              "not-real-blender", self.opts)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].kwargs["argv"], self.asset["build_args"])
        self.assertEqual(run.call_args_list[1].kwargs["argv"], self.asset["export_args"])
        self.assertEqual(run.call_args_list[0].kwargs["cwd"], run.call_args_list[1].kwargs["cwd"])
        self.assertNotEqual(run.call_args.kwargs["cwd"], self.repo)
        self.assertEqual(record["exporter"], self.asset["export_script"])
        self.assertEqual((self.repo / self.asset["source"]).read_text(), "approved master")

    def test_script_export_with_wrapper_opens_master_without_running_seed(self):
        self.install_seed()
        self.install_wrapper()
        self.opts.keep_blend = True
        source_before = (self.repo / self.asset["source"]).read_bytes()
        # Prove publication is the generated output, not reuse of the repository export.
        self.write(self.asset["runtime"], "old repository runtime")
        with mock.patch.object(pipeline, "run_blender", side_effect=self.python_seed) as run:
            record, _ = pipeline.export_asset(self.repo, self.cfg, self.asset,
                                               "not-real-blender", self.opts)
        run.assert_called_once()
        workdir = run.call_args.kwargs["cwd"]
        self.assertNotEqual(workdir, self.repo)
        self.assertEqual(run.call_args.args[1], (workdir / self.asset["export_script"]).resolve())
        self.assertFalse(workdir.exists())
        self.assertEqual(run.call_args.kwargs["argv"], self.asset["export_args"])
        self.assertEqual(record["source_sha256"], pipeline.sha256_file(self.repo / self.asset["source"]))
        self.assertEqual((self.repo / self.asset["source"]).read_bytes(), source_before)
        self.assertEqual((self.repo / self.asset["runtime"]).read_bytes(), b'{"triangle_count": 1}\n')


if __name__ == "__main__":
    unittest.main()
