"""The simulation's trig must be identical on every platform (issue #56).

A mixed Windows/macOS LAN pair hashed `anchor.x + sin(ang) * r` to
`11496.363787673816` on one machine and `11496.363787673814…` on the other,
because `math.sin` comes from the platform's `libm`. `game.core.detmath` is built
from the correctly-rounded operations only, and these tests pin both halves of
that claim: the numbers are as good as libm to a few ULP, and nothing in the
simulation can reach a platform transcendental any more.
"""
from __future__ import annotations

import ast
import math
import random
import re
import subprocess
import unittest
from pathlib import Path

from game.core import detmath

ROOT = Path(__file__).resolve().parents[1]
SIM_PACKAGES = ('game/core', 'game/systems', 'game/ai')
# Functions whose platform implementations differ between macOS and Windows.
LIBC_NAMES = ('sin', 'cos', 'tan', 'atan2', 'exp', 'log', 'pow', 'hypot')


def _ulp_distance(left, right):
    if left == right:
        return 0.0
    return abs(left - right) / math.ulp(max(abs(left), abs(right), 5e-324))


def _simulation_sources():
    for package in SIM_PACKAGES:
        for path in sorted((ROOT/package).glob('*.py')):
            if path.name != 'detmath.py':
                yield path


class AccuracyTests(unittest.TestCase):
    def test_sine_and_cosine_track_libm_within_two_ulp(self):
        random.seed(1234)
        angles = [random.uniform(-7000, 7000) for _ in range(4000)]
        angles += [0.1, 0.5, 1.0, 2.5, -3.7, math.pi/4, 100.0, -2500.0]
        for angle in angles:
            with self.subTest(angle=angle):
                self.assertLessEqual(_ulp_distance(detmath.sin(angle), math.sin(angle)), 2.0)
                self.assertLessEqual(_ulp_distance(detmath.cos(angle), math.cos(angle)), 2.0)

    def test_accuracy_holds_at_multiples_of_half_pi_where_sine_is_near_zero(self):
        """The hard case for range reduction: a 53-bit pi/2 split fails here.

        sin(pi) is ~1e-16, so a reduction error of ~1e-13 (what a leading part
        carrying all 53 bits produces) is a wrong answer, not a rounding wobble.
        """
        angles = [k * math.pi / 2 for k in range(-12, 13)] + [1234 * math.pi / 2, -777 * math.pi / 2]
        for angle in angles:
            with self.subTest(angle=angle):
                self.assertLessEqual(abs(detmath.sin(angle) - math.sin(angle)), 1e-20)
                self.assertLessEqual(abs(detmath.cos(angle) - math.cos(angle)), 1e-20)
        self.assertEqual(detmath.sin(math.pi), math.sin(math.pi))
        self.assertEqual(detmath.cos(math.pi / 2), math.cos(math.pi / 2))

    def test_arctangent_two_argument_matches_libm_and_its_conventions(self):
        random.seed(4321)
        points = [(random.uniform(-60, 60), random.uniform(-60, 60)) for _ in range(4000)]
        points += [(0.0, 1.0), (1.0, 0.0), (-1.0, 0.0), (0.0, -1.0), (1.0, -1.0), (-1.0, -1.0),
                   (1e-9, 1.0), (1.0, 1e-9), (3.0, 4.0), (100.0, 0.001)]
        for y, x in points:
            with self.subTest(y=y, x=x):
                self.assertLessEqual(abs(detmath.atan2(y, x) - math.atan2(y, x)), 1e-15)
        # Conventions the simulation relies on (and that libm shares).
        self.assertEqual(detmath.atan2(0.0, 0.0), 0.0)
        self.assertEqual(detmath.atan2(-0.0, 0.0), -0.0)
        self.assertEqual(detmath.atan2(0.0, -0.0), math.pi)
        self.assertEqual(detmath.atan2(-0.0, -0.0), -math.pi)
        self.assertEqual(detmath.atan2(1.0, 0.0), math.pi/2)
        self.assertEqual(detmath.atan2(-1.0, 0.0), -math.pi/2)
        self.assertEqual(detmath.atan2(0.0, -1.0), math.pi)
        self.assertEqual(detmath.atan2(float('inf'), 1.0), math.pi/2)
        self.assertTrue(math.isnan(detmath.atan2(float('nan'), 1.0)))

    def test_special_values_do_not_crash_or_lose_signs(self):
        self.assertEqual(str(detmath.sin(-0.0)), '-0.0')
        self.assertEqual(detmath.cos(0.0), 1.0)
        self.assertEqual(detmath.sin(1e-300), 1e-300)
        self.assertTrue(math.isnan(detmath.sin(float('nan'))))
        self.assertTrue(math.isnan(detmath.cos(float('inf'))))
        self.assertEqual(detmath.hypot(3.0, 4.0), 5.0)
        self.assertEqual(detmath.hypot(1e200, 1e200), 1.414213562373095e+200)
        self.assertEqual(detmath.hypot(-3.0, -4.0), 5.0)
        self.assertEqual(detmath.hypot(0.0, 0.0), 0.0)
        self.assertTrue(math.isnan(detmath.hypot(float('nan'), 1.0)))

    def test_tangent_is_consistent_with_the_deterministic_sine_and_cosine(self):
        random.seed(99)
        for angle in [random.uniform(-1000, 1000) for _ in range(300)] + [0.7, -1.2]:
            with self.subTest(angle=angle):
                self.assertLessEqual(abs(detmath.tan(angle) - math.tan(angle)), 1e-14)

    def test_exact_helpers_are_shared_with_the_standard_library(self):
        """sqrt/floor/ceil/isfinite are correctly rounded: re-export, never reimplement."""
        for name in ('sqrt', 'floor', 'ceil', 'isfinite', 'isfinite', 'nextafter', 'dist', 'radians'):
            self.assertIs(getattr(detmath, name), getattr(math, name), name)
        self.assertEqual(detmath.pi, math.pi)

    def test_libm_only_functions_are_absent_so_a_miss_is_loud(self):
        """exp/log/pow have no deterministic implementation here yet.

        Re-exporting them would silently reintroduce platform divergence, so they
        are deliberately missing: a simulation module reaching for one raises.
        """
        for name in ('exp', 'log', 'pow'):
            self.assertFalse(hasattr(detmath, name), name)


class DeterminismTests(unittest.TestCase):
    def test_the_implementations_are_python_not_libm_wrappers(self):
        for name in ('sin', 'cos', 'tan', 'atan2', 'hypot'):
            self.assertTrue(hasattr(getattr(detmath, name), '__code__'),
                            f'detmath.{name} must be a Python function, not a libm wrapper')

    def test_detmath_source_never_calls_a_platform_transcendental(self):
        source = (ROOT/'game/core/detmath.py').read_text(encoding='utf-8')
        body = source.split('"""', 2)[-1]               # skip the module docstring
        for name in LIBC_NAMES:
            self.assertNotIn(f'math.{name}(', body, name)
            self.assertNotIn(f'from math import {name}', body, name)

    def test_no_simulation_module_imports_the_platform_math_module(self):
        """The guard that keeps this fixed: new code cannot reach libm by accident."""
        offenders = []
        for path in _simulation_sources():
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if re.match(r'^\s*(import math|from math import)\b', line):
                    offenders.append(f'{path.relative_to(ROOT)}:{number}: {line.strip()}')
        self.assertEqual(offenders, [], 'simulation modules must import game.core.detmath')

    def test_every_module_that_uses_math_binds_it(self):
        """A module may not reference `math.` without importing something as math.

        Swapping the import and rewriting exponents in one pass is exactly how
        separation.py lost its binding once; this catches it in a second instead
        of 86 runtime errors.
        """
        offenders = []
        for path in _simulation_sources():
            source = path.read_text(encoding='utf-8')
            if not re.search(r'\bmath\.', source):
                continue
            tree = ast.parse(source)
            bound = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    bound |= any(alias.name == 'math' or alias.asname == 'math' for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names = [alias.asname or alias.name for alias in node.names]
                    bound |= 'math' in names or node.module in ('math', 'game.core.detmath')
            if not bound:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_no_simulation_module_uses_float_exponentiation(self):
        """`x ** 2` and `x ** 0.5` compile to libm pow, which is not identical.

        Multiplication and sqrt are; use those (see detmath's docstring).
        """
        pattern = re.compile(r'\*\*\s*[0-9]')
        offenders = []
        for path in _simulation_sources():
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if pattern.search(line) and not line.lstrip().startswith('#'):
                    offenders.append(f'{path.relative_to(ROOT)}:{number}: {line.strip()}')
        self.assertEqual(offenders, [])

    def test_the_simulation_scene_still_runs_and_is_reproducible(self):
        from game.net import diag
        first = diag.sim_fingerprint(ticks=5)
        second = diag.sim_fingerprint(ticks=5)
        self.assertEqual(first['checksum'], second['checksum'])
        self.assertRegex(first['checksum'] or '', r'^[0-9a-f]{64}$')


class RepoWideGuardTests(unittest.TestCase):
    def test_renderer_may_keep_the_fast_platform_math(self):
        """Only the simulation needs determinism; rendering performance matters."""
        renderer = subprocess.run(
            ['bash', '-c', 'grep -rl "^import math" render/*.py || true'],
            cwd=ROOT, capture_output=True, text=True).stdout.split()
        for path in renderer:
            self.assertFalse((ROOT/path).read_text(encoding='utf-8').startswith('from game.core'),
                             f'{path} unexpectedly swapped to detmath')


if __name__ == '__main__':                       # pragma: no cover - manual entry
    unittest.main()
