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


def floating_texts_screen(state, camera, local_player: int) -> list:
    """Project live floating texts to [(x, y, text, rgb, alpha), ...]."""
    out = []
    for ft in state.floating_texts:
        if not state.is_position_visible(local_player, ft["pos"]):
            continue
        alpha = max(0.0, 1.0 - ft.get("t", 0.0) / LIFETIME)
        if alpha <= 0:
            continue
        pos = ft["pos"]
        get = pos.get if isinstance(pos, dict) else (lambda k, i=None: pos[i])
        screen = camera.world_to_screen(get("x", 0), get("y", 1), get("z", 2))
        if screen is None:
            continue
        out.append((int(screen[0]), int(screen[1]), ft.get("text", ""),
                    _colour(ft.get("color", (1, 1, 1))), alpha))
    return out
