"""The S03 authoring pipeline is exercised without Blender.

These tests cover the parts that decide whether a rebuild is trustworthy — discovery, the
export-only guard, registry shape, payload sanity, the contract-validator dependency — so the
ordinary gameplay suite never needs Blender installed (S03 acceptance D1/D6).
"""

import ast
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "art"))
import model_pipeline as pipeline  # noqa: E402


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.repo = ROOT
        self.cfg = pipeline.load_pipeline(self.repo)

    def test_every_declared_path_stays_inside_the_repository(self):
        for asset in self.cfg["assets"]:
            for key in ("source", "exporter", "runtime", "expected_hashes"):
                path = pipeline.repo_path(self.repo, asset[key])
                self.assertTrue(str(path).startswith(str(self.repo)), f"{asset['binding']}.{key}")

    def test_selection_by_asset_batch_and_all(self):
        args = type("A", (), {"asset": ["rebel:battleship"], "batch": None, "all": False})()
        self.assertEqual([a["binding"] for a in pipeline.select_assets(self.cfg, args)],
                         ["rebel:battleship"])
        args = type("A", (), {"asset": None, "batch": ["approved-trio"], "all": False})()
        self.assertEqual(len(pipeline.select_assets(self.cfg, args)), 3)
        args = type("A", (), {"asset": None, "batch": None, "all": True})()
        self.assertEqual(len(pipeline.select_assets(self.cfg, args)), len(self.cfg["assets"]))

    def test_no_selection_is_a_refusal_not_a_silent_pass(self):
        args = type("A", (), {"asset": None, "batch": None, "all": False})()
        with self.assertRaises(pipeline.PipelineError) as caught:
            pipeline.select_assets(self.cfg, args)
        self.assertTrue(caught.exception.refused)

    def test_unknown_binding_and_batch_are_reported(self):
        for args in (type("A", (), {"asset": ["nope:nope"], "batch": None, "all": False})(),
                     type("A", (), {"asset": None, "batch": ["nope"], "all": False})()):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.select_assets(self.cfg, args)

    def test_relative_paths_may_not_escape_the_repository(self):
        for bad in ("../../etc/passwd", "/etc/passwd"):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.repo_path(self.repo, bad)


class BlenderDiscoveryTest(unittest.TestCase):
    def test_resolution_order_and_the_error_that_helps(self):
        cfg = {"blender": {"env_var": "SA_TEST_BLENDER", "candidates": {"darwin": []}}}
        here = pathlib.Path(__file__)
        self.assertEqual(pipeline.resolve_blender(str(here), cfg, env={}, which=lambda _: None,
                                                   system="darwin"), here)
        self.assertEqual(pipeline.resolve_blender(None, cfg, env={"SA_TEST_BLENDER": str(here)},
                                                   which=lambda _: None, system="darwin"), here)
        with self.assertRaises(pipeline.PipelineError) as caught:
            pipeline.resolve_blender(None, cfg, env={}, which=lambda _: None, system="darwin")
        self.assertIn("--blender", str(caught.exception))
        self.assertEqual(caught.exception.code, "E_NO_BLENDER")


class ExportOnlyGuardTest(unittest.TestCase):
    """A blend-authoritative exporter must never be able to overwrite the source it exports."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name)
        (self.repo / "tools/art").mkdir(parents=True)
        self.asset = {"binding": "rebel:example"}

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        path = self.repo / "tools/art/export_example.py"
        path.write_text(text, encoding="utf-8")
        return "tools/art/export_example.py"

    def test_a_script_that_saves_the_blend_is_refused(self):
        rel = self.write("import bpy\nbpy.ops.wm.open_mainfile(filepath='x.blend')\n"
                         "bpy.ops.wm.save_as_mainfile(filepath='x.blend')\n")
        with self.assertRaises(pipeline.PipelineError) as caught:
            pipeline.assert_export_only(self.repo, self.asset, rel)
        self.assertEqual(caught.exception.code, "E_EXPORT_WOULD_OVERWRITE_SOURCE")
        self.assertTrue(caught.exception.refused)

    def test_a_script_that_never_opens_the_source_is_refused(self):
        rel = self.write("import json\nopen('out.json', 'w').write(json.dumps({}))\n")
        with self.assertRaises(pipeline.PipelineError) as caught:
            pipeline.assert_export_only(self.repo, self.asset, rel)
        self.assertEqual(caught.exception.code, "E_EXPORT_NOT_FROM_SOURCE")

    def test_an_export_only_script_passes(self):
        rel = self.write("import bpy, json\n"
                         "bpy.ops.wm.open_mainfile(filepath='art/blender/example.blend')\n"
                         "open('assets/models/example.mesh.json', 'w').write(json.dumps({}))\n")
        self.assertTrue(pipeline.assert_export_only(self.repo, self.asset, rel))


class PayloadSanityTest(unittest.TestCase):
    def test_the_approved_exports_are_structurally_sound(self):
        cfg = pipeline.load_pipeline(ROOT)
        report = pipeline.Report()
        for asset in cfg["assets"]:
            payload = pipeline._payload_sanity(ROOT, asset, report)
            self.assertIsNotNone(payload, asset["binding"])
            rows = sum(len(batch) for batch in payload["batches"].values())
            self.assertEqual(rows, payload["triangle_count"])
            self.assertEqual(payload["triangle_count"], asset["expected_triangles"])
            self.assertFalse([e for e in report.errors if asset["binding"] in e["message"]])
        self.assertEqual(report.errors, [])


class ValidateModelsTest(unittest.TestCase):
    """validate-models delegates to the S02 contract validator; it must not pass without it."""

    def run_validate(self, **overrides):
        cfg = pipeline.load_pipeline(ROOT)
        args = type("A", (), {"json": True, "no_contract": False,
                              "allow_source_drift": False, **overrides})()
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = pipeline.validate(ROOT, cfg, args)
        return code, json.loads(buffer.getvalue())

    def test_the_report_is_well_formed_and_the_contract_dependency_is_explicit(self):
        code, report = self.run_validate()
        self.assertGreater(report["checks"], 15)
        validator = ROOT / "tools/art/validate_contract.py"
        codes = {item["code"] for item in report["errors"]}
        if validator.is_file():
            self.assertEqual(codes, set(), report["errors"])
            self.assertEqual(code, 0)
        else:
            # PR #117 supplies it; until then this must fail loudly rather than pass on its own.
            self.assertEqual(codes, {"E_NO_CONTRACT_VALIDATOR"}, report["errors"])
            self.assertEqual(code, 1)
        self.assertFalse(any("Application Support" in json.dumps(item) for item in report["errors"]))

    def test_skipping_the_contract_validator_still_runs_the_build_side_checks(self):
        code, report = self.run_validate(no_contract=True)
        self.assertGreater(report["checks"], 15)
        self.assertNotIn("E_CONTRACT", {item["code"] for item in report["errors"]})


class IsolationTest(unittest.TestCase):
    """The pipeline must not reach into the game, the renderer or the player's user data."""

    def test_the_module_imports_no_game_or_render_code(self):
        tree = ast.parse((ROOT / "tools/art/model_pipeline.py").read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & {"game", "render"}, set(), imported)

    def test_no_user_data_path_is_referenced(self):
        text = (ROOT / "tools/art/model_pipeline.py").read_text(encoding="utf-8")
        offenders = [token for token in ("Application Support", "USER_DIR", "sandbox-exec",
                                        "Library/Application", ".local/share")
                     if token in text]
        self.assertEqual(offenders, [], f"the pipeline must not touch user data: {offenders}")


if __name__ == "__main__":
    unittest.main()
