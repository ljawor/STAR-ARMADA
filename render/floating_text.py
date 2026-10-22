"""Floating combat text, projected from the game's camera into window pixels.

Damage numbers are simulation state (`state.floating_texts`); where they land on screen is a view
question the application answers, because only it knows the camera and the window size. This used
to be a method on the legacy renderer, which is why the game still built one; it is a function now,
so the window can be the only renderer (#160).
"""
from __future__ import annotations

LIFETIME = 2.2


def _colour(col) -> tuple[int, int, int]:
    """Accepts 0..1 floats or 0..255 ints; the sim uses both."""
    return (int(col[0] * 255) if col[0] <= 1 else int(col[0]),
            int(col[1] * 255) if col[1] <= 1 else int(col[1]),
            int(col[2] * 255) if col[2] <= 1 else int(col[2]))


def _position(value):
    """A floating text stores `Vec3.to_dict()`; the visibility test wants the point back."""
    from game.core.vectors import Vec3
    if isinstance(value, Vec3):
        return value
    if isinstance(value, dict):
        return Vec3(value['x'], value['y'], value['z'])
    return Vec3(*value[:3])


def floating_texts_screen(state, camera, local_player: int) -> list:
    """Project live floating texts to [(x, y, text, rgb, alpha), ...]."""
    out = []
    for ft in state.floating_texts:
        pos = _position(ft['pos'])
        if not state.is_position_visible(local_player, pos):
            continue
        alpha = max(0.0, 1.0 - ft.get("t", 0.0) / LIFETIME)
        if alpha <= 0:
            continue
        screen = camera.world_to_screen(pos.x, pos.y, pos.z)
        if screen is None:
            continue
        out.append((int(screen[0]), int(screen[1]), ft.get("text", ""),
                    _colour(ft.get("color", (1, 1, 1))), alpha))
    return out
