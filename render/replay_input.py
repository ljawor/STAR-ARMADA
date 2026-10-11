"""Replay camera/inspection only: no gameplay input dispatcher is reachable."""
import pygame
from render.input import InputController


class ReplayInput(InputController):
    def handle_event(self, ev):
        if ev.type == pygame.WINDOWFOCUSLOST:
            self.keys.clear()
            self.drag_start = self.drag_cur = self.right_drag = None
            self.dragging = False
        elif ev.type == pygame.KEYDOWN:
            self.keys.add(ev.key)
            if ev.key in (pygame.K_SPACE, pygame.K_h):
                self._follow_selection()
            elif ev.key == pygame.K_m:
                self.camera.follow_id = None
            elif ev.key == pygame.K_x:
                self.camera.follow_id = None
                self.camera.target = [0., 0., 0.]
                self.camera.distance = self.camera.zoom_limits[1]
                self.camera.pitch = 89.
        elif ev.type == pygame.KEYUP:
            self.keys.discard(ev.key)
        elif ev.type == pygame.MOUSEWHEEL:
            self.camera.zoom(.88 ** ev.y)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 3:
                self.right_drag = ev.pos
            elif ev.button == 1:
                if any(r.collidepoint(ev.pos) for r in getattr(self.hud, 'blocked_rects', [])):
                    return
                self.drag_start = self.drag_cur = ev.pos
                self.dragging = True
        elif ev.type == pygame.MOUSEMOTION:
            if self.right_drag is not None:
                self.camera.rotate(-ev.rel[0] * .25, -ev.rel[1] * .18)
            if self.dragging:
                self.drag_cur = ev.pos
        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 3:
                self.right_drag = None
            elif ev.button == 1 and self.dragging:
                self._finish_box_select(ev.pos)
                self.dragging = False
                self.drag_start = self.drag_cur = None

    def update_placement(self):
        # A stale HUD gameplay button must never arm placement in a replay.
        self.hud.placement = None


def configure_replay_hud(hud):
    """Keep inspection/minimap; do not advertise production or ability actions."""
    hud._right_panel = lambda selection, local_player: None
    hud._ability_rows = lambda panel, y, entities, local_player: None
    original_label = getattr(hud, '_label', None)
    if callable(original_label):
        def label(x, y, text, *args, **kwargs):
            if text == '1-9 control groups · F fleet menu':
                text = 'READ-ONLY: camera and inspection'
            return original_label(x, y, text, *args, **kwargs)
        hud._label = label
