#!/usr/bin/env python3
"""Windowless Metal/D3D native pixel acceptance using the production producer/library.

This is a HUD-only diagnostic, not a substitute for the ordinary-main game capture.
No pygame display, settings writes, synthetic screenshots or alternate renderer.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--width', type=int, default=2560)
    parser.add_argument('--height', type=int, default=1440)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    import pygame
    from PIL import Image, ImageChops
    from game.core.manager import GameManager
    from game.data.store import DataStore
    from render import i18n
    from render_bridge import top_hud, overlay
    from render_bridge.live import LiveSession
    from render_bridge.embedded import EmbeddedWindow
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    pygame.font.init()
    session = LiveSession(gm.state, gm.ds, directory=args.out / 'rings',
                          size=(1280, 800), overlay_keyframe=0.00001)
    argv = ['viewer', '--snapshot', str(ROOT / 'assets/cpp/catalogue.snap'),
            '--assets', str(ROOT), '--width', str(args.width), '--height', str(args.height),
            '--overlay-ring', str(session.paths['overlay']),
            '--top-hud-ring', str(session.paths['top_hud']), '--seconds', '0']
    window = None
    receipts = []
    language = i18n.language()
    try:
        try:
            window = EmbeddedWindow(argv, root=ROOT)
        except RuntimeError as exc:
            raise AssertionError('rebuilt ordinary native library must accept --top-hud-ring') from exc

        def draw():
            for _ in range(3):
                count = window._lib.armada_frame(window._handle, window._pixels, len(window._pixels))
                assert count == len(window._pixels), window._lib.armada_error(window._handle).decode()
            return Image.frombytes('RGBA', window.size, bytes(window._pixels), 'raw', 'BGRA')

        def publish(native=True, paused=False, fps=60):
            session.hud.native_top_bar = native
            session.publish(gm.state, visible_ids=set(), paused=paused, fps=fps)
            model = top_hud.build(gm.state, 0, paused=paused, fps=fps, active=native)
            session._top_hud.publish(top_hud.encode(model))
            return model

        publish(False)
        before = draw()
        before.save(args.out / 'before.png')
        # Capture the clean native state before any native pause/FPS is drawn.
        publish(True, False, 0)
        clean_reference = draw()
        publish(True)
        after = draw()
        after.save(args.out / 'after.png')
        header = round(34 * args.height / 800)
        band = (0, 0, args.width, header)
        assert ImageChops.difference(before.crop(band).convert('RGB'),
                                    after.crop(band).convert('RGB')).getbbox(), 'native pass drew no changed pixels'
        # Empty overlay control: GPU bar must still draw without Python's bitmap.
        session._overlay.publish(overlay.encode(1280, 800, full=bytes(1280 * 800 * 4)))
        bar_only = draw()
        bar_only.save(args.out / 'native-without-python-overlay.png')
        import numpy as np
        pixels = np.asarray(bar_only.crop(band).convert('RGB')).astype('int16')
        color_counts = {}
        for label, color in {'credits': (86, 140, 220), 'materials': (200, 170, 120),
                             'energy': (150, 220, 240), 'crew': (110, 200, 120),
                             'zero_income': (232, 92, 76)}.items():
            # Small antialiased glyphs need not contain any fully opaque texel.
            # Count coverage along the expected straight-alpha colour ramp,
            # rather than requiring the endpoint RGB and rejecting valid type.
            background = np.array((10, 17, 25))
            vector = np.array(color) - background
            coverage = ((pixels - background) * vector).sum(axis=2) / (vector * vector).sum()
            predicted = background + coverage[..., None] * vector
            count = int(((coverage >= 0.35) & (coverage <= 1.05)
                         & (np.abs(pixels - predicted).max(axis=2) <= 8)).sum())
            assert count >= 8, f'native glyph colour missing: {label} ({count} pixels)'
            color_counts[label] = count
        # A malformed snapshot must leave the last good geometry untouched.
        session._top_hud.publish(b'{"version":2}')
        rejected = draw()
        assert rejected.crop(band).tobytes() == bar_only.crop(band).tobytes(), 'bad model damaged last good strip'
        inactive = top_hud.build(gm.state, 0, active=False, fps=60)
        session._top_hud.publish(top_hud.encode(inactive))
        cleared = draw()
        assert cleared.crop(band).tobytes() != bar_only.crop(band).tobytes(), 'inactive model retained old geometry'
        cleared.save(args.out / 'inactive-native-control.png')
        # Same world and transparent overlay, changing only native activation.
        assert ImageChops.difference(cleared.crop(band).convert('RGB'),
                                    bar_only.crop(band).convert('RGB')).getbbox(), 'native-only control has no strip'
        for code in ('en', 'de', 'pl', 'ru'):
            i18n.set_language(code)
            model = publish(True, True)
            image = draw()
            image.save(args.out / f'paused-{code}.png')
            receipts.append({'language': code, 'paused': model['paused'],
                             'model_bytes': len(top_hud.encode(model)), 'image': f'paused-{code}.png'})
        # Clearing state must remove old glyphs, not retain yesterday's pause text.
        publish(True, False, 0)
        clean = draw()
        clean.save(args.out / 'resumed.png')
        assert clean.crop(band).tobytes() == clean_reference.crop(band).tobytes(), 'old pause/FPS survived resumed clean-state control'
        publish(True, False, 0)
        repeat = draw()
        # Only the top strip is compared: the world includes wall-clock animation.
        assert clean.crop(band).tobytes() == repeat.crop(band).tobytes(), 'unchanged native bar is not repeatable'
        # Fully opaque app overlay must cover native type (native is below app layers).
        cover = pygame.Surface((1280, 800), pygame.SRCALPHA)
        cover.fill((251, 17, 83, 255))
        session.publish(gm.state, visible_ids=set(), overlay_layers=[cover])
        modal = draw()
        assert modal.crop(band).convert('RGB').getextrema() == ((251, 251), (17, 17), (83, 83)), 'bar leaked above modal overlay'
        report = {'passed': True, 'drawable': [args.width, args.height], 'header_pixels': header,
                  'mode': 'windowless production bgfx library; real skirmish HUD, catalogue world',
                  'languages': receipts, 'native_without_python_bitmap': True,
                  'repeatable_top_strip': True, 'opaque_app_overlay_covers_native': True}
        report.update(native_glyph_color_pixels=color_counts, malformed_model_preserves_good=True,
                      inactive_model_clears=True, inactive_native_pixel_control=True,
                      resumed_matches_pre_pause_pre_fps_control=True)
        (args.out / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
    finally:
        i18n.set_language(language)
        if window is not None:
            window.terminate()
        session.close()


if __name__ == '__main__':
    main()
