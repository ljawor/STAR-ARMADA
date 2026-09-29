"""Effect geometry: the vertex structure of the blast billboards.

This exists because the blast shipped with a bug that no pixel count, and no
silhouette metric, could see, and that I mis-diagnosed twice before bisecting
it: `_draw_glow_ring` and `_draw_shock_shell` emitted THREE vertices per angle
inside ONE GL_QUAD_STRIP.

A quad strip joins CONSECUTIVE vertices, so it must alternate between exactly
two curves. With three, the strip walks inner -> mid -> outer and then pairs
outer(angle i) with inner(angle i+1): a quad spanning the full band radially,
one per angle, which renders as a dark radial SPOKE. Drawing the shock shell
alone produced 12+ wedges and no ring at all.

These tests pin the invariant directly, by capturing the GL calls:

  * a blob (inner=0, one band) must be a GL_TRIANGLE_FAN with a single shared
    centre vertex. As a quad strip the centre is duplicated once per angle and
    each copy carries its angle's brightness jitter, so neighbouring wedges
    disagree in the middle -> pinwheel.
  * a banded billboard must emit one GL_QUAD_STRIP per band, each with exactly
    TWO vertices per angle, on the two radii that band spans.

Headless on purpose: the GL entry points are stubbed out, so this runs with no
context. Run with: PYTHONPATH=.:tests ./.venv/bin/python tests/test_effect_geometry.py
"""
from __future__ import annotations

import math
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import render.renderer as R  # noqa: E402


class _Capture:
    """Stub the GL calls and record the vertex structure."""

    def __init__(self, mod):
        self.mod = mod
        self.saved = {}
        self.strips = []
        self._cur = None

    def _begin(self, mode):
        self._cur = [mode, []]

    def _vertex(self, x, y, z):
        self._cur[1].append((x, y, z))

    def _end(self):
        self.strips.append((self._cur[0], self._cur[1]))
        self._cur = None

    def __enter__(self):
        m = self.mod
        for name, fn in (("glBegin", self._begin), ("glVertex3f", self._vertex),
                         ("glEnd", self._end),
                         ("glColor4f", lambda *a: None),
                         ("glBlendFunc", lambda *a: None),
                         ("glPushMatrix", lambda: None),
                         ("glPopMatrix", lambda: None),
                         ("glTranslatef", lambda *a: None),
                         ("glDisable", lambda *a: None)):
            self.saved[name] = getattr(m, name)
            setattr(m, name, fn)
        return self

    def __exit__(self, *exc):
        for name, fn in self.saved.items():
            setattr(self.mod, name, fn)
        return False


def _fake_renderer():
    """A Renderer with no GL setup at all — __init__ would need a context."""
    r = R.Renderer.__new__(R.Renderer)
    r.camera = types.SimpleNamespace(yaw=0.0, pitch=25.0)
    return r


def _radii(strip):
    return [math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) for v in strip[1]]


class TestBlastGeometry(unittest.TestCase):
    def test_blob_is_one_fan_with_a_single_shared_centre(self):

        ring = R.Renderer._fx_ring(11, 0.4, 5, 0.34, 24)
        r = _fake_renderer()
        with _Capture(R) as cap:
            R.Renderer._draw_glow_ring(r, [0.0, 0.0, 0.0], 100.0,
                                       (1.0, 0.5, 0.2), 0.5, ring, rot=3)
        modes = [s[0] for s in cap.strips]
        assert modes == [R.GL_TRIANGLE_FAN], (
            f"a plain blob must be a single triangle fan, got {modes}")
        verts = cap.strips[0][1]
        assert len(verts) == len(ring) + 2, (
            f"expected one centre vertex plus one rim vertex per ring point "
            f"(the loop closes the ring, emitting {len(ring) + 1}), got {len(verts)}")
        assert verts[0] == (0.0, 0.0, 0.0), (
            f"the fan must start at a single shared centre, got {verts[0]}")
        assert sum(1 for v in verts if v == (0.0, 0.0, 0.0)) == 1, (
            "the centre must be ONE vertex; duplicating it per angle makes "
            "neighbouring wedges disagree and renders as a pinwheel")

    def test_banded_billboard_is_one_strip_per_band_two_verts_per_angle(self):

        """THE regression test for the spoke bug."""
        n = len(R.Renderer._fx_ring(7, 0.2, 4, 0.30, 30))
        ring = R.Renderer._fx_ring(7, 0.2, 4, 0.30, 30)
        radius, inner, nrings = 120.0, 0.35, 3
        r = _fake_renderer()
        with _Capture(R) as cap:
            R.Renderer._draw_glow_ring(r, [0.0, 0.0, 0.0], radius,
                                       (1.0, 1.0, 1.0), 0.6, ring, rot=0,
                                       additive=True, inner=inner, nrings=nrings)
        strips = [s for s in cap.strips if s[0] == R.GL_QUAD_STRIP]
        assert len(strips) == nrings, (
            f"expected one quad strip per band ({nrings}), got {len(strips)}")
        r0 = radius * inner
        for k, strip in enumerate(strips):
            verts = strip[1]
            assert len(verts) == 2 * (n + 1), (
                f"band {k}: a quad strip must carry TWO vertices per angle "
                f"(2*{n + 1}), got {len(verts)} — three per angle pairs "
                f"outer(i) with inner(i+1) and renders a radial spoke")
            fa, fb = k / nrings, (k + 1) / nrings
            rad = _radii(strip)
            for i in range(n + 1):
                m = ring[i % n][0]
                want_a = r0 + (radius * m - r0) * fa
                want_b = r0 + (radius * m - r0) * fb
                got_a, got_b = rad[2 * i], rad[2 * i + 1]
                assert abs(got_a - want_a) < 1e-3, (
                    f"band {k} angle {i}: even vertex should sit on the inner "
                    f"contour {want_a:.3f}, got {got_a:.3f}")
                assert abs(got_b - want_b) < 1e-3, (
                    f"band {k} angle {i}: odd vertex should sit on the outer "
                    f"contour {want_b:.3f}, got {got_b:.3f}")

    def test_shock_shell_has_no_full_width_quads(self):

        """The shock was the worst offender: alone it drew wedges, not a ring.

        Checked STRUCTURALLY rather than by a radial-step heuristic: ring wobble
        makes consecutive-vertex jumps noisy (a legitimate angle-to-angle step can
        exceed the band width), so assert the exact contour radii instead. A
        correct strip alternates inner(angle i), mid(angle i); the buggy
        3-per-angle strip walks inner, mid, outer, and then pairs outer(angle i)
        with inner(angle i+1) — a quad spanning the whole band radially.
        """
        ring = R.Renderer._fx_ring(5, 0.9, 4, 0.34, 40)
        n = len(ring)
        radius, thickness = 160.0, 90.0
        r = _fake_renderer()
        with _Capture(R) as cap:
            R.Renderer._draw_shock_shell(r, [0.0, 0.0, 0.0], radius,
                                         (1.0, 0.86, 0.66), 0.3, thickness, ring)
        strips = [s for s in cap.strips if s[0] == R.GL_QUAD_STRIP]
        assert len(strips) == 2, (
            f"the shock shell should draw two strips (inner->mid, mid->outer), "
            f"got {len(strips)}")
        for k, strip in enumerate(strips):
            verts = strip[1]
            assert len(verts) == 2 * (n + 1), (
                f"shock band {k}: expected 2 vertices per angle ({2 * (n + 1)}), "
                f"got {len(verts)} — a 3-per-angle strip emits a full-width radial "
                f"quad every segment (measured: 12+ dark spokes, no ring)")
            rad = _radii(strip)
            for i in range(n + 1):
                m = ring[i % n][0]
                rm = radius * m
                inner = rm - thickness * m
                mid = inner + (rm - inner) * 0.55
                outer = rm + thickness * 0.85 * m
                want = (inner, mid) if k == 0 else (mid, outer)
                got = (rad[2 * i], rad[2 * i + 1])
                for tag, w, g in (("first", want[0], got[0]),
                                  ("second", want[1], got[1])):
                    assert abs(g - w) < 1e-3, (
                        f"shock band {k} angle {i}: {tag} vertex should be {w:.2f}, "
                        f"got {g:.2f}")

    def test_shock_fades_at_its_outer_edge(self):

        """A bright outer contour reads as a drawn donut, so the strip must end
        dimmer than its middle."""
        ring = R.Renderer._fx_ring(5, 0.9, 4, 0.34, 20)
        r = _fake_renderer()
        seen = []
        with _Capture(R):
            orig = R.glColor4f
            R.glColor4f = lambda a, b, c, d: seen.append(d)
            try:
                R.Renderer._draw_shock_shell(r, [0.0, 0.0, 0.0], 120.0,
                                             (1.0, 1.0, 1.0), 0.4, 60.0, ring)
            finally:
                R.glColor4f = orig
        angles = len(ring) + 1
        first = seen[:2 * angles]
        mid = [first[2 * i + 1] for i in range(angles)]
        # second strip holds mid -> outer; outer must be the dimmest of the three
        second = seen[2 * angles:4 * angles]
        out_vals = [second[2 * i + 1] for i in range(angles)]
        assert max(out_vals) < min(mid), (
            f"the outer edge must be dimmer than the band middle "
            f"(max outer {max(out_vals)} vs min mid {min(mid)})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
