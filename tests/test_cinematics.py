"""Campaign presentation regressions using the actual main function bodies."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import pygame
from render.camera import Camera

ROOT = Path(__file__).resolve().parents[1]


def main_functions(**values):
    tree = ast.parse((ROOT / 'main.py').read_text())
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    ns = dict(pygame=pygame, Audio=object, Camera=Camera, accumulator=0., paused=False,
              net_session=None, playback=None, cinematic=None, mission_def=None,
              campaign_outcome_seen=False, SETTINGS={}, TICK_DT=1/30)
    ns.update(values)
    exec(compile(ast.Module(body=body, type_ignores=[]), 'main.py', 'exec'), ns)
    return ns


class CinematicsTests(unittest.TestCase):
    def test_main_campaign_intro_blocks_first_tick_and_discards_debt(self):
        camera = Camera(1024, 768)
        state = SimpleNamespace(game_over=False)
        steps = []
        ns = main_functions(camera=camera, state=state,
                            gm=SimpleNamespace(step=steps.append),
                            mission_def={'id':'stable-id', 'name':'First Fleet',
                                         'briefing':'Establish your fleet.'})
        self.assertIn('start_campaign_presentation', ns,
                      'production main has no campaign intro integration')
        ns['start_campaign_presentation'](fresh=True)
        self.assertIsNotNone(ns['cinematic'])
        ns['advance_simulation'](10.)
        self.assertEqual(steps, [])
        self.assertEqual(ns['accumulator'], 0.)
        self.assertEqual(ns['cinematic'].mission_id, 'stable-id')


    def test_production_start_and_loop_route_presentation(self):
        tree = ast.parse((ROOT / 'main.py').read_text())
        start = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'start_game')
        calls = {n.func.id for n in ast.walk(start) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn('start_campaign_presentation', calls)
        loop = next(n for n in tree.body if isinstance(n, ast.While))
        calls = {n.func.id for n in ast.walk(loop) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn('sync_campaign_outcome', calls)
        self.assertIn('draw_campaign_presentation', calls)

    def test_all_caption_rects_fit_and_objectives_are_derived(self):
        from render.cinematics import CampaignCinematic
        pygame.font.init()
        mission = {'id':'test', 'name':'LongTitle'*60,
                   'briefing':'LongUnbrokenToken'*80,
                   'objectives':[{'description':'Secure the sector.'}]}
        movie = CampaignCinematic(mission, Camera(1024,768), reduced_motion=True)
        self.assertTrue(hasattr(movie, 'compose'), 'missing readable caption compositor')
        self.assertIn('Secure the sector.', movie.caption)
        for w,h in ((1024,768),(1280,800)):
            surface = movie.compose(w,h)
            for rect in movie.caption_rects:
                self.assertTrue(surface.get_rect().contains(rect), rect)
            for i,r in enumerate(movie.caption_rects):
                for other in movie.caption_rects[i+1:]:
                    self.assertFalse(r.colliderect(other))

    def test_finished_skip_frame_does_not_reapply_pan(self):
        from render.cinematics import CampaignCinematic
        camera = Camera(1024,768)
        movie = CampaignCinematic({'id':'stable'},camera)
        original = movie.saved_view
        movie.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN))
        movie.update(.033)
        self.assertEqual(original,(camera.target,camera.distance,camera.yaw,camera.pitch,camera.follow_id))

    def test_outro_clears_held_controls_and_half_gestures(self):
        controller = SimpleNamespace(keys={pygame.K_q},dragging=True,
                                     drag_start=(2,2),drag_cur=(3,3),right_drag=(4,4))
        ns = main_functions(camera=Camera(1024,768),inputc=controller,
            state=SimpleNamespace(game_over=False),mission_def={'id':'stable'},
            gm=SimpleNamespace(mission=SimpleNamespace(completed=False,failed=True)))
        ns['sync_campaign_outcome']()
        self.assertEqual(controller.keys,set())
        self.assertFalse(controller.dragging)
        self.assertIsNone(controller.right_drag)
        self.assertIsNone(controller.drag_start)

    def test_outcome_unlocks_on_completion_once_even_when_disabled(self):
        calls = []
        ns = main_functions(camera=Camera(1024,768),
            state=SimpleNamespace(game_over=False),
            mission_def={'id':'stable', 'name':'Mission', 'objectives':[]},
            gm=SimpleNamespace(mission=SimpleNamespace(completed=True, failed=False)),
            SETTINGS={'cinematics_enabled':False})
        ns['_unlock_next_mission'] = lambda: calls.append('unlock')
        self.assertIn('sync_campaign_outcome', ns)
        ns['sync_campaign_outcome']()
        ns['sync_campaign_outcome']()
        self.assertEqual(calls, ['unlock'])
        self.assertIsNone(ns['cinematic'])
        for flag in ('net_session', 'playback'):
            ns[flag] = object()
            ns['campaign_outcome_seen'] = False
            ns['sync_campaign_outcome']()
            self.assertEqual(calls, ['unlock'])
            ns[flag] = None

    def test_skips_restore_view_and_reduced_motion_is_static(self):
        from render.cinematics import CampaignCinematic
        for key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE, None):
            camera = Camera(1024,768)
            camera.follow_id = 42
            original = (list(camera.target), camera.distance, camera.yaw, camera.pitch, camera.follow_id)
            movie = CampaignCinematic({'id':'stable', 'briefing':'Briefing'}, camera,
                                     reduced_motion=True)
            framed = (list(camera.target), camera.distance, camera.yaw, camera.pitch)
            movie.update(.5)
            self.assertEqual(framed, (camera.target, camera.distance, camera.yaw, camera.pitch))
            self.assertTrue(hasattr(movie, 'handle_event'), 'missing cinematic skip controls')
            ev = pygame.event.Event(pygame.KEYDOWN, key=key) if key is not None else pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(1,1))
            self.assertTrue(movie.handle_event(ev))
            self.assertTrue(movie.finished)
            self.assertEqual(original, (camera.target, camera.distance, camera.yaw, camera.pitch, camera.follow_id))


if __name__ == '__main__':
    unittest.main()
