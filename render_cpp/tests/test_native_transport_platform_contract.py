"""Source-only portability tripwires, NOT a Windows compile/runtime proof.

Run without building: python -B render_cpp/tests/test_native_transport_platform_contract.py
Real Win32 and POSIX transport behavior remains in the CTest `input` executable.
"""
from pathlib import Path
import re
import unittest

HEADER = Path(__file__).resolve().parents[1] / "include" / "input_ring.hpp"


def windows_source(source):
    """Select the explicit platform branches; do not emulate SDK/compiler behavior."""
    active = [True]
    branches = []
    result = []
    for line in source.splitlines():
        directive = line.strip()
        if directive.startswith(("#ifdef ", "#ifndef ")):
            macro = directive.split()[1]
            condition = macro == "_WIN32"
            if directive.startswith("#ifndef"):
                condition = not condition
            branches.append(condition)
            active.append(active[-1] and condition)
        elif directive == "#else":
            active[-1] = active[-2] and not branches[-1]
        elif directive == "#endif":
            active.pop()
            branches.pop()
        elif active[-1]:
            result.append(line)
    return "\n".join(result)


class NativeTransportPlatformContract(unittest.TestCase):
    def test_windows_branch_excludes_posix_dependencies(self):
        source = windows_source(HEADER.read_text())
        self.assertNotRegex(source, r"#include <(?:fcntl|unistd|sys/[^>]+)\.h>")
        self.assertNotRegex(source, r"::(?:open|flock|ftruncate|mmap|munmap|close)\(")
        for api in ("CreateFileW", "LockFileEx", "CreateFileMappingW", "MapViewOfFile",
                    "UnmapViewOfFile", "CloseHandle"):
            self.assertIn(api + "(", source)

    def test_lock_is_nonblocking_before_resize_and_outside_wire_payload(self):
        source = windows_source(HEADER.read_text())
        self.assertIn("LOCKFILE_FAIL_IMMEDIATELY", source)
        self.assertIn("LOCKFILE_EXCLUSIVE_LOCK", source)
        self.assertRegex(source, r"kProducerLockOffset\s*=\s*uint64_t\{1\}\s*<<\s*62")
        self.assertLess(source.index("::LockFileEx("), source.index("::SetEndOfFile("))
        self.assertNotIn("CREATE_ALWAYS", source)
        self.assertNotIn("TRUNCATE_EXISTING", source)

    def test_close_releases_view_then_mapping_then_producer_handle(self):
        source = windows_source(HEADER.read_text())
        close = source[source.index("  void close() {"):source.index("  size_t payloadBytes()")]
        for api in ("::UnmapViewOfFile(", "::CloseHandle(mapping_)", "::CloseHandle(file_)"):
            self.assertTrue(api in close, "missing Windows close operation: " + api)
        self.assertLess(close.index("::UnmapViewOfFile("), close.index("::CloseHandle(mapping_)"))
        self.assertLess(close.index("::CloseHandle(mapping_)"), close.index("::CloseHandle(file_)"))
        # CloseHandle releases the lock only after the view and mapping are gone.
        self.assertNotIn("UnlockFileEx", close)


if __name__ == "__main__":
    unittest.main()
