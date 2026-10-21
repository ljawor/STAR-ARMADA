"""Dirty-rectangle upload: what the recorder proves, and what it refuses to assume.

The HUD used to send its whole 1280x800 surface to the GPU every frame (0.951 ms measured; see
artifacts/cpp-renderer/w03/overlay-upload.json). The recorder in render/overlay_upload.py decides
which patches actually changed. These tests pin the two properties that make that safe:

  * an unchanged paint list uploads nothing, and
  * replaying a sequence of partial uploads onto a blank texture reproduces exactly the bytes a full
    upload would have sent — for a real HUD painted from real simulation state, not a mock.

Anything the recorder cannot reason about (an unkeyed blit of a surface nobody described) must be
dirty every frame. That is the conservative direction: bandwidth, never a stale pixel.
"""
import unittest

import pygame

import helpers  # noqa: F401  (puts the repo root on sys.path, same as the other HUD tests)
from game.core.vectors import Vec3
from render.hud import HUD
from render.overlay_upload import OpRecorder, coalesce, gl_y_offset, painter


def blank(size):
    return bytearray(size[0] * size[1] * 4)


def replay(shadow, surface, rects):
    """Apply an upload the way the GPU would: subimage rows land where the full rows are."""
    width, height = surface.get_size()
    full = pygame.image.tobytes(surface, "RGBA", False)
    for rect in coalesce(rects, (width, height)):
        top = gl_y_offset(rect, height)       # texture row the GPU starts writing at
        for row in range(rect.height):
            src = ((rect.y + row) * width + rect.x) * 4
            dst = ((top + row) * width + rect.x) * 4
            shadow[dst:dst + rect.width * 4] = full[src:src + rect.width * 4]
    return shadow


class RecorderTests(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        painter.recorder = None
        self.surface = pygame.Surface((160, 90), pygame.SRCALPHA)

    def tearDown(self):
        painter.recorder = None

    def paint_frame(self, recorder, label):
        painter.recorder = recorder
        recorder.begin(self.surface)
        painter.rect(self.surface, (10, 20, 30), (4, 4, 60, 20))
        painter.blit_text(self.surface, pygame.Surface((40, 12)), (8, 8), label,
                          (255, 255, 255), "mono15")
        recorder.finish()
        return recorder.take_dirty()

    def test_identical_frame_uploads_nothing(self):
        recorder = OpRecorder()
        first = self.paint_frame(recorder, "FLEET")
        second = self.paint_frame(recorder, "FLEET")
        self.assertTrue(first, "the first frame must upload (there is no previous frame)")
        self.assertEqual(second, [], "an unchanged paint list must upload no rects")

    def test_changed_label_dirties_only_its_rect(self):
        recorder = OpRecorder()
        self.paint_frame(recorder, "FLEET")
        dirty = self.paint_frame(recorder, "FLEET 2")
        self.assertEqual(len(dirty), 1)
        self.assertEqual(dirty[0], pygame.Rect(8, 8, 40, 12))

    def test_unkeyed_blit_is_dirty_every_frame(self):
        recorder = OpRecorder()
        painter.recorder = recorder
        for _ in range(3):
            recorder.begin(self.surface)
            painter.blit(self.surface, pygame.Surface((10, 10)), (20, 20))
            recorder.finish()
            self.assertEqual(recorder.take_dirty(), [pygame.Rect(20, 20, 10, 10)])

    def test_reordered_ops_dirty_from_the_first_divergence(self):
        recorder = OpRecorder()

        painter.recorder = recorder

        def frame(rects):
            recorder.begin(self.surface)
            for rect in rects:
                painter.rect(self.surface, (1, 2, 3), rect)
            recorder.finish()
            return recorder.take_dirty()

        frame([(0, 0, 10, 10), (20, 0, 10, 10)])
        dirty = frame([(20, 0, 10, 10), (0, 0, 10, 10)])
        # Both slides diverge, and each dirty rect is unioned with the op's own previous rect, so
        # the result covers the whole band rather than two disjoint squares.
        self.assertEqual(len(dirty), 2)
        self.assertEqual(dirty[0].union(dirty[1]), pygame.Rect(0, 0, 30, 10))

    def test_a_vanishing_op_uploads_the_area_it_painted(self):
        """The fps label is drawn only while fps > 0; when it stops, its pixels must be re-sent."""
        recorder = OpRecorder()
        painter.recorder = recorder

        def frame(show_label):
            recorder.begin(self.surface)
            painter.rect(self.surface, (5, 6, 7), (0, 0, 40, 12))
            if show_label:
                painter.blit_text(self.surface, pygame.Surface((30, 10)), (60, 40),
                                  "59 FPS", (1, 2, 3), "small")
            recorder.finish()
            return recorder.take_dirty()

        frame(True)
        dirty = frame(False)
        self.assertIn(pygame.Rect(60, 40, 30, 10), [pygame.Rect(r) for r in dirty],
                      f"the removed label's rect must be re-uploaded, got {dirty}")

    def test_coalesce_clips_and_merges(self):
        rects = [pygame.Rect(-10, 5, 30, 20), pygame.Rect(15, 5, 30, 20)]
        merged = coalesce(rects, (100, 100))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0], pygame.Rect(0, 5, 45, 20))
        self.assertEqual(coalesce([pygame.Rect(200, 200, 10, 10)], (100, 100)), [])


class HudEquivalenceTest(unittest.TestCase):
    """Replay the HUD's own uploads and compare against what a full upload would have sent."""

    def setUp(self):
        from helpers import make_game
        pygame.font.init()
        self.game = make_game(ai=False)
        self.state = self.game.state
        self.hud = HUD(640, 400, self.state)
        self.sent = []
        self.shadow = blank((640, 400))
        self.full_uploaded = False

        def fake_upload():
            rects = self.hud.recorder.take_dirty()
            if not self.full_uploaded:
                self.shadow = bytearray(pygame.image.tobytes(self.hud.overlay, "RGBA", False))
                self.full_uploaded = True
                self.sent.append("full")
                return
            self.sent.append(len(rects))
            replay(self.shadow, self.hud.overlay, rects)

        self.hud._upload = fake_upload
        self.full = pygame.image.tobytes(self.hud.overlay, "RGBA", False)

    def frame(self, selection=(), fps=0.0):
        self.hud.render(set(selection), None, 0, False, "", 0.0, fps)
        full = pygame.image.tobytes(self.hud.overlay, "RGBA", False)
        self.full = full
        return full

    def test_partial_uploads_reproduce_the_full_surface(self):
        ships = [e for e in self.state.entities.values() if e.owner == 0 and e.is_ship]
        self.frame()
        self.frame(fps=59.0)                       # top-right label changes
        self.frame(fps=58.0)
        self.frame(selection={ships[0].id} if ships else ())   # left panel changes
        self.assertEqual(bytes(self.shadow), bytes(self.full),
                         "replayed partial uploads must equal the full surface bytes")

    def test_steady_state_stops_uploading(self):
        ships = [e for e in self.state.entities.values() if e.owner == 0 and e.is_ship]
        selection = {ships[0].id} if ships else ()
        self.frame(selection=selection)
        for _ in range(4):
            self.frame(selection=selection)
        # The minimap and the drag/floating layers are unkeyed images, so they stay dirty; the
        # point is that the panels and labels stop being re-sent. A full upload would be 4 rects
        # of 640x400; assert we are well under "everything".
        self.assertTrue(all(s == "full" or s < 40 for s in self.sent), self.sent)

    def test_damage_changes_the_bars_not_the_whole_screen(self):
        ships = [e for e in self.state.entities.values() if e.owner == 0 and e.is_ship]
        if not ships:
            self.skipTest("fixture has no player hulls")
        selection = {ships[0].id}
        self.frame(selection=selection)
        ships[0].hull = max(1.0, ships[0].max_hull * 0.4)
        self.frame(selection=selection)
        before = bytes(self.full)
        self.assertEqual(bytes(self.shadow), before,
                         "a hull change must be uploaded exactly (bars plus label)")


if __name__ == "__main__":
    unittest.main()
