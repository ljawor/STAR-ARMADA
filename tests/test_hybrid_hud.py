"""The HUD the player sees must be the HUD the controller operates."""
import tempfile
import unittest
from unittest.mock import patch
import pygame
from game.core.manager import GameManager
from game.data.store import DataStore
from render.hud import HUD
from render.camera import Camera
from render_bridge.live import LiveSession
from render_bridge import overlay, ring


class SharedHUDTests(unittest.TestCase):
    def test_live_surface_uses_the_real_hud_including_mutable_ui_state(self):
        previous = DataStore._instance
        self.addCleanup(setattr, DataStore, '_instance', previous)
        gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        pygame.font.init()
        hud = HUD(1280, 800, gm.state)
        self.addCleanup(hud.close)
        camera = Camera(1280, 800)
        hud.set_camera_ref(camera)
        hud.fleet_panel = True
        with tempfile.TemporaryDirectory() as tmp:
            session = LiveSession(gm.state, gm.ds, directory=tmp, hud=hud, camera=camera)
            try:
                self.assertIs(session.hud, hud)
                with patch.object(hud, 'compose', wraps=hud.compose) as compose:
                    session.publish(gm.state, visible_ids=set(gm.state.entities))
                    compose.assert_called_once()
                with ring.Ring.open(session.paths['overlay']) as reader:
                    frame = overlay.decode(reader.latest()[1])
                self.assertEqual((frame['width'], frame['height']), (1280, 800))
                self.assertTrue(hud.fleet_panel)
            finally:
                # Closing transport must not close the application-owned HUD.
                with patch.object(hud, 'close', wraps=hud.close) as close:
                    session.close()
                    close.assert_not_called()


    def test_extra_layers_are_uploaded_and_removed_without_stale_pixels(self):
        gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
        with tempfile.TemporaryDirectory() as tmp:
            session = LiveSession(gm.state, gm.ds, directory=tmp, size=(320, 200))
            try:
                layer = pygame.Surface((320, 200), pygame.SRCALPHA)
                layer.fill((251, 17, 83, 255))
                session.publish(gm.state, visible_ids=set(), overlay_layers=[layer])
                with ring.Ring.open(session.paths['overlay']) as reader:
                    frame = overlay.decode(reader.latest()[1])
                    # Inspect the wire image, not just the argument handed to composition.
                    self.assertIn(bytes((251, 17, 83, 255)) * 100, frame['payload'])
                    session.publish(gm.state, visible_ids=set())
                    clean = overlay.decode(reader.latest()[1])
                    self.assertTrue(clean['full'])
                    self.assertNotEqual(clean['payload'], frame['payload'])
            finally:
                session.close()


if __name__ == '__main__':
    unittest.main()
