"""Runtime metadata must be reproducible, not a manually maintained second catalogue."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeMetadataTests(unittest.TestCase):
    def test_shipped_metadata_matches_source_contract_and_inventory(self):
        result = subprocess.run([sys.executable, 'tools/art/sync_runtime_metadata.py', '--check'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
