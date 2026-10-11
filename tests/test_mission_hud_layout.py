"""Mission-card geometry measured from every actual text blit (no GL)."""
import unittest
import pygame
from helpers import make_game
from render.hud import HUD


class RecordingSurface(pygame.Surface):
    def blit(self, source, dest, *args, **kwargs):
        rect = source.get_rect(topleft=dest)
        self.text_rects.append(rect)
        return super().blit(source, dest, *args, **kwargs)


class MissionHUDLayoutTests(unittest.TestCase):
    def draw_card(self, width, name, rows, done=False, failed=False):
        gm = make_game(ai=False)
        hud = HUD(width, 768 if width == 1024 else 800, gm.state)
        hud.overlay = RecordingSurface((hud.width, hud.height), pygame.SRCALPHA)
        hud.overlay.text_rects = []
        hud.mission_name, hud.mission_progress = name, rows
        hud.mission_done, hud.mission_failed = done, failed
        sides = [pygame.Rect(10, 44, 320, 400), pygame.Rect(width-330, 44, 320, 400)]
        hud.blocked_rects = sides.copy()
        before = gm.state.to_dict(precise=True)
        hud._mission_panel(0)
        self.assertEqual(before, gm.state.to_dict(precise=True))
        card = hud.blocked_rects[-1]
        self.assertTrue(pygame.Rect(0, 0, hud.width, hud.height).contains(card))
        self.assertFalse(any(card.colliderect(side) for side in sides))
        rects = hud.overlay.text_rects
        self.assertTrue(rects)
        for i, rect in enumerate(rects):
            self.assertTrue(card.inflate(-20, -12).contains(rect), (card, rect))
            self.assertFalse(any(rect.colliderect(other) for other in rects[i+1:]))
        return hud, card, rects

    def test_tutorial_objective_wraps_inside_card_between_controls(self):
        for width in (1024, 1280):
            with self.subTest(width=width):
                _, _, rects = self.draw_card(width, 'Recovery Drill',
                    ['[ ] Capture the disabled Syndicate corvette (0/1 captured)'])
                self.assertGreaterEqual(len(rects), 3)


    def test_long_tokens_titles_and_terminal_rows_stay_contained(self):
        for width in (1024, 1280):
            for done, failed in ((False, False), (True, False), (False, True)):
                with self.subTest(width=width, done=done, failed=failed):
                    _, _, rects = self.draw_card(width,
                        'Recovery drill with an unusually long mission title',
                        ['[x] ' + 'LongUnbrokenModObjective' * 3,
                         '[ ] Restore personnel to the abandoned frigate (0/10)'],
                        done=done, failed=failed)
                    self.assertGreater(len(rects), 5)


if __name__ == '__main__':
    unittest.main()
