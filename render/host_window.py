"""The one place that raises the host window, and the one place that names pygame's bridge.

`main.cpp_restore_window` needs `restore`/`show`/`focus` on this process's own SDL window.
pygame-ce 2.5 deprecated `Window.from_display_module()`, and its notice points at
`Window.get_surface`/`Window.flip` — i.e. moving *presentation* onto a `pygame.Window`.
This application presents through the display module: menus, the HUD and the native
blit all draw to `pygame.display.get_surface()` and flip it. Until that whole path
moves, the deprecated bridge is the only route to those three calls, so it is used
here and nowhere else, so the day presentation moves there is one call site to delete.

Two things this module deliberately does *not* do:

  * Poke SDL directly through ctypes. `pygame.display.get_wm_info()['window']` is the
    platform handle — on macOS a `PyCapsule` holding the `NSWindow`, not the
    `SDL_Window` — so `SDL_*Window` functions answer zeroes for it (measured: size
    0x0, empty title, while `SDL_GetWindowFromID(1)` returns a different pointer).
    Driving window state from a reinterpreted handle would be a per-platform
    guess that silently does nothing.
  * Emit the deprecation notice. It is the player's console, and the notice is
    about a migration this issue does not perform; the suppression is scoped to this
    call, named after this comment, and disappears with the call.

The player's path does not reach any of this: only the separate-window diagnostic
launch iconifies the pygame window (`STAR_ARMADA_CPP_EXTERNAL=1`), and the embedded
renderer draws into that window instead. `main.cpp_restore_window` therefore calls
this only after it has recorded an iconification.
"""
from __future__ import annotations

import warnings

_NOTICE = r'.*surface-rendering with Window.*'


def restore() -> bool:
    """Restore, show and focus the display-module window. False when there is none."""
    try:
        import pygame
        if not pygame.display.get_init():
            return False
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message=_NOTICE, category=DeprecationWarning)
            from pygame._sdl2.video import Window
            window = Window.from_display_module()
            window.restore()
            window.show()
            window.focus()
    except Exception:
        # A window that cannot be raised must never take the game down on the way out.
        return False
    return True
