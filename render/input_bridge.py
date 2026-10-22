"""W04: feed the window's events into the game, with the game still in charge.

The C++ window records what the pointer and the keyboard did and publishes batches on an input
ring (`render_bridge/input.py` documents the format). This module turns those batches into the
pygame events `InputController.handle_event` already handles, so the migration adds no second
input path: the same controller builds the same PlayerCommands, and the simulation validates them
exactly as it does for a native window.

Two conversions are unavoidable and both are explicit here:

* **Coordinates.** The HUD surface is a fixed W x H the Python side composes; the window can be
  any pixel size. The window publishes pointer positions in its own pixels, so they are scaled
  onto the surface before the controller sees them. A click that selects a ship must select the
  same ship at 1280x800 and at 2560x1600.
* **Latency.** Input is sampled, not delivered: `poll()` drains everything published since the
  last call and hands it to the controller in order. If the game falls a whole ring behind, the
  oldest batches were already overwritten; `poll()` reports how many, because silently dropping a
  click is the kind of bug that reads as "the game ignored me".
"""
from __future__ import annotations

import pygame

from render_bridge import input as wire


class RingInput:
    """A pygame-event source backed by the window's input ring."""

    def __init__(self, path, controller, surface_size, *, from_oldest=False):
        self.controller = controller
        self.surface_size = (int(surface_size[0]), int(surface_size[1]))
        self.window_size = self.surface_size
        self._reader = wire.InputReader(path, from_oldest=from_oldest)
        # Counters, so a caller can report what the bridge actually did rather than assert it.
        self.events_delivered = 0
        self.batches_read = 0
        self.batches_skipped = 0
        self.unmapped = 0
        self.quit_requested = False
        # The pointer delta a MOUSEMOTION carries. The game's right-drag does
        # `dx, dy = ev.rel; camera.rotate(...)`, which is how the camera is orbited out of top-down
        # into the 3D view; the ring carries absolute positions only, so the delta is computed here
        # rather than published (a dropped frame must not change what a drag means).
        self._last_pos = None

    # -- size ----------------------------------------------------------------
    def _learn_window(self, event):
        if event.kind == wire.RESIZE:
            width, height = event.size
            if width > 0 and height > 0:
                self.window_size = (width, height)

    def _scale(self, event):
        """Window pixels -> HUD surface pixels."""
        if event.kind not in (wire.MOTION, wire.BUTTON_DOWN, wire.BUTTON_UP, wire.WHEEL):
            return event
        window_w, window_h = self.window_size
        surface_w, surface_h = self.surface_size
        if (window_w, window_h) == (surface_w, surface_h):
            return event
        x = int(round(event.x * surface_w / window_w))
        y = int(round(event.y * surface_h / window_h))
        return wire.Event(event.kind, event.button, event.code, x, y, event.extra)

    # -- delivery ------------------------------------------------------------
    def poll(self, limit=None):
        """Deliver pending events to the controller. Returns how many it received.

        `limit` caps how many batches are consumed (one batch is one window frame). A caller
        that runs at the window's frame rate passes `limit=1` so a held key keeps its hold:
        draining a backlog in one call would deliver a press and its release before the game
        ever runs an update, and the held state would vanish.
        """
        batches = self._reader.read(limit)
        self.batches_read += len(batches)
        self.batches_skipped += self._reader.skipped
        delivered = 0
        for batch in batches:
            for event in batch:
                self._learn_window(event)
                event = self._scale(event)
                try:
                    pygame_event = wire.to_pygame(event)
                except wire.InputError:
                    self.unmapped += 1
                    continue
                if pygame_event.type == pygame.QUIT:
                    # The window is closing; the game loop decides what that means, so the
                    # controller is not told to quit by an input event.
                    self.quit_requested = True
                    continue
                pygame_event.remote = True
                if pygame_event.type == pygame.MOUSEMOTION:
                    # Absolute positions cross the bridge; the delta the game rotates with is the
                    # change since the previous event. The first motion of a drag has no previous
                    # point, so it reports no movement rather than a jump from the last click.
                    last = self._last_pos
                    pygame_event.rel = ((0, 0) if last is None
                                        else (event.x - last[0], event.y - last[1]))
                    self._last_pos = (event.x, event.y)
                elif pygame_event.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWRESIZED):
                    # The previous sample belongs to another focus/coordinate space.
                    self._last_pos = None
                elif pygame_event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                    self._last_pos = event.pos
                self.controller.handle_event(pygame_event)
                delivered += 1
                self.events_delivered += 1
        return delivered

    def close(self):
        self._reader.close()

    def report(self):
        return {
            'events_delivered': self.events_delivered,
            'batches_read': self.batches_read,
            'batches_skipped': self.batches_skipped,
            'unmapped': self.unmapped,
            'quit_requested': self.quit_requested,
            'window': list(self.window_size),
            'surface': list(self.surface_size),
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
