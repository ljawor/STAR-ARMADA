"""The S02 extension contract is executed, not described.

This test runs the real validator over the real examples and asserts *counts*, so a validator
that silently skipped its input cannot pass here: the number of validated documents, the number
of negative controls and the exact rejection code of each control are all checked.
"""

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools" / "art" / "validate_contract.py"
EXPECTED = ROOT / "art" / "schemas" / "examples" / "invalid" / "EXPECTED.json"


class AssetContractTest(unittest.TestCase):
    """Run the contract validator as a build step would."""

    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.run([sys.executable, str(VALIDATOR), "--json"],
                                  capture_output=True, text=True, cwd=str(ROOT))
        try:
            cls.report = json.loads(cls.proc.stdout)
        except Exception as exc:  # noqa: BLE001 - a non-JSON result is the failure
            raise AssertionError(
                f"validator did not emit JSON (exit {cls.proc.returncode}):\n"
                f"{cls.proc.stdout[-2000:]}\n{cls.proc.stderr[-2000:]}") from exc

    def test_validator_passes(self):
        self.assertEqual(self.proc.returncode, 0,
                         f"contract not satisfied:\n{json.dumps(self.report, indent=2)[:4000]}")

    def test_every_valid_example_was_actually_checked(self):
        """A report with nothing in it is not a pass."""
        valid = [k for k in self.report["report"] if not k.startswith(("invalid/", "runtime/"))]
        self.assertGreaterEqual(len(valid), 8, f"only checked {valid}")
        for name in valid:
            self.assertEqual(self.report["report"][name], "ok", name)
        # the three approved assets migrate to manifests, and the registry names them
        self.assertIn("manifests/alliance_battleship.json", valid)
        self.assertIn("core-registry.json", valid)

    def test_each_negative_control_is_rejected_with_its_declared_code(self):
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        controls = {k: v for k, v in expected.items() if not k.startswith("__")}
        self.assertGreaterEqual(len(controls), 20, "too few negative controls to be evidence")
        for name, code in controls.items():
            outcome = self.report["report"].get(f"invalid/{name}")
            self.assertIsNotNone(outcome, f"{name} was not validated at all")
            self.assertEqual(outcome, f"rejected {code} as declared", name)
        runtime = expected["__runtime_symlink__"]
        self.assertEqual(self.report["report"].get("runtime/symlink-escape"),
                         f"rejected {runtime} as declared")

    def test_validator_is_not_trivially_satisfied(self):
        """Every rejection rule has a control that actually exercises it."""
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        codes = {v for k, v in expected.items() if not k.startswith("__")}
        codes.add(expected["__runtime_symlink__"])  # built at runtime, not committable
        self.assertGreaterEqual(len(codes), 15, f"only {len(codes)} distinct rejection rules controlled")
        for required in ("E_UNSAFE_PATH", "E_SYMLINK_ESCAPE", "E_REVISION_MISMATCH",
                         "E_NON_FINITE", "E_UNKNOWN_CONTRACT", "E_ASSET_COLLISION"):
            self.assertIn(required, codes)


if __name__ == "__main__":
    unittest.main()
