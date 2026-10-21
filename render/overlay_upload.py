"""Dirty-rectangle upload for the HUD overlay surface.

`render/hud.py` paints a full-window SRCALPHA surface every frame and used to hand all of it to
`glTexImage2D`. Measured on this host (macOS, Apple Silicon, Metal; 1280x800 RGBA, 4,096,000 B) that
transfer costs 0.951 ms per frame — about a whole W02 producer budget, every frame, whether or not
the pixels changed. A 320x180 patch costs 0.061 ms, so uploading only what changed is worth it.

The paint calls are the only place that knows what changed, so this module records them:

  * `OpRecorder` keeps one entry per paint call — a *key* built from every argument that affects the
    op's pixels — and a rect. Between frames it compares keys position by position. An op whose key
    is unchanged provably produced the same pixels (the same call on the same arguments), so its
    rect is not uploaded. Ops that cannot be keyed (a blit of a surface nobody described) are marked
    dirty every frame; being conservative here costs bandwidth, never correctness.
  * `OverlayUploader` owns the texture and uploads the resulting rects with `glTexSubImage2D`,
    merging them into vertical bands first. The first upload is always full.

Index-position comparison means a reordered panel marks everything from the first divergence onward,
which again costs bandwidth but never correctness.

Nothing here is used by the C++ viewer: this is the legacy renderer's fix, and the recorded op list
is the natural input to W03's draw-list transport.
"""
from __future__ import annotations

import pygame

from OpenGL.GL import (
    GL_LINEAR, GL_RGBA, GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER,
    GL_UNSIGNED_BYTE, glBindTexture, glGenTextures, glTexImage2D, glTexParameteri,
    glTexSubImage2D,
)

#: Ops whose pixels depend on something the recorder cannot see are marked with this.
UNKNOWN = object()

#: Merge rects whose union is at most this many times their own area into one upload.
MERGE_SLACK = 1.4


def _freeze(value):
    """A hashable stand-in for a draw argument, or `UNKNOWN` if it cannot be keyed."""
    if isinstance(value, (int, float, bool, str, bytes, type(None))):
        return value
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, pygame.Rect):
        return (value.x, value.y, value.width, value.height)
    return UNKNOWN


def _has_unknown(value) -> bool:
    """True when a frozen argument (or anything nested in it) could not be keyed."""
    if value is UNKNOWN:
        return True
    if isinstance(value, tuple):
        return any(_has_unknown(item) for item in value)
    return False


def _bounds(kind: str, args: tuple, kwargs: dict):
    """The rect a `pygame.draw` call touches, or None if it cannot be bounded cheaply."""
    try:
        if kind in ("rect", "ellipse"):
            return pygame.Rect(args[0])
        if kind == "circle":
            (x, y), radius = args[0], args[1]
            width = kwargs.get("width", args[2] if len(args) > 2 else 0)
            r = radius + (width or 0)
            return pygame.Rect(int(x - r), int(y - r), int(2 * r), int(2 * r))
        if kind == "line":
            (x0, y0), (x1, y1) = args[0], args[1]
            width = kwargs.get("width", args[2] if len(args) > 2 else 1) or 1
            left, top = min(x0, x1) - width, min(y0, y1) - width
            return pygame.Rect(int(left), int(top),
                               int(abs(x1 - x0) + 2 * width), int(abs(y1 - y0) + 2 * width))
        if kind == "polygon":
            points = list(args[0])
            xs = [p[0] for p in points] or [0]
            ys = [p[1] for p in points] or [0]
            width = kwargs.get("width", args[1] if len(args) > 1 else 0) or 0
            return pygame.Rect(int(min(xs) - width), int(min(ys) - width),
                               int(max(xs) - min(xs) + 2 * width),
                               int(max(ys) - min(ys) + 2 * width))
    except (IndexError, TypeError, ValueError):
        return None
    return None


class OpRecorder:
    """Records the paint ops of one surface frame and reports what has to be re-uploaded."""

    def __init__(self) -> None:
        self.size = (0, 0)
        self.ops: list = []          # keys, in paint order, for the frame being built
        self.rects: list = []        # rect per key, same index
        self._previous: list = []     # (key, rect) per op, previous frame
        self._pending: list = []     # rects to upload for the frame just finished
        self.frames = 0
        self.ops_seen = 0

    def begin(self, surface: pygame.Surface) -> None:
        self.size = surface.get_size()
        self.ops = []
        self.rects = []

    def note(self, key, rect: pygame.Rect) -> None:
        self.ops.append(key)
        self.rects.append(rect)
        self.ops_seen += 1

    def unknown(self, rect: pygame.Rect) -> None:
        self.note(UNKNOWN, rect)

    def finish(self) -> None:
        """Diff against the previous frame; the result is what `take_dirty` returns.

        A changed op dirties the union of where it paints now and where that op painted last frame:
        a bar that got shorter uncovers pixels the op behind it drew, and those pixels were never
        re-uploaded, so the old rect has to be re-sent too.
        """
        previous = self._previous
        pending = []
        for index, key in enumerate(self.ops):
            rect = self.rects[index]
            stale = previous[index] if index < len(previous) else None
            if key is not UNKNOWN and stale is not None and stale[0] == key:
                continue
            if stale is not None:
                rect = rect.union(stale[1])
            pending.append(rect)
        # Ops that disappeared were painting something last frame; that area has to be re-sent or
        # the old pixels survive. Index alignment catches removals in the middle of the list; this
        # catches the ones at the end.
        for stale in previous[len(self.ops):]:
            pending.append(stale[1])
        self._previous = list(zip(self.ops, self.rects))
        self._pending = pending
        self.frames += 1

    def take_dirty(self) -> list:
        pending, self._pending = self._pending, []
        return pending

    def invalidate(self) -> None:
        """Force the next frame to upload everything (resize, context loss, first frame)."""
        self._previous = []


def coalesce(rects, size, slack: float = MERGE_SLACK) -> list:
    """Merge rects into as few uploads as the slack allows, clipped to the surface."""
    bounds = pygame.Rect(0, 0, size[0], size[1])
    clipped = []
    for rect in rects:
        rect = pygame.Rect(rect).clip(bounds)
        if rect.width and rect.height:
            clipped.append(rect)
    if not clipped:
        return []
    total = sum(rect.width * rect.height for rect in clipped)
    union = clipped[0].unionall(clipped[1:]) if len(clipped) > 1 else clipped[0]
    if len(clipped) > 1 and union.width * union.height <= slack * total:
        return [union]
    clipped.sort(key=lambda r: (r.y, r.x))
    bands: list = []
    for rect in clipped:
        if bands:
            band = bands[-1]
            trial = band.union(rect)
            area = sum(r.width * r.height for r in clipped if trial.contains(r))
            if trial.width * trial.height <= slack * area:
                bands[-1] = trial
                continue
        bands.append(pygame.Rect(rect))
    return bands


def gl_y_offset(rect: pygame.Rect, height: int) -> int:
    """Row offset for `glTexSubImage2D`, in the texture's own row order.

    glTexImage2D copies the bytes verbatim, so texture row 0 (t = 0) is the surface's *first* row;
    yoffset counts rows from that same origin, which makes it `rect.y` and not `height - bottom`.
    """
    return rect.y


class OverlayUploader:
    """Owns the overlay texture and uploads dirty rects instead of the whole surface."""

    def __init__(self) -> None:
        self.tex = None
        self.full_pending = True
        self.uploads = 0
        self.pixels = 0
        self.full_uploads = 0

    def release(self) -> None:
        if self.tex is not None:
            from OpenGL import GL
            GL.glDeleteTextures([self.tex])
            self.tex = None
            self.full_pending = True

    def upload(self, surface: pygame.Surface, rects) -> int:
        """Upload `rects` (or the whole surface if the texture is new). Returns pixels sent."""
        width, height = surface.get_size()
        if self.tex is None:
            self.tex = glGenTextures(1)
            self.full_pending = True
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        if self.full_pending:
            data = pygame.image.tobytes(surface, "RGBA", False)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                         GL_RGBA, GL_UNSIGNED_BYTE, data)
            self.full_pending = False
            self.full_uploads += 1
            self.uploads += 1
            self.pixels += width * height
            return width * height
        sent = 0
        for rect in coalesce(rects, (width, height)):
            patch = surface.subsurface(rect)
            data = pygame.image.tobytes(patch, "RGBA", False)
            glTexSubImage2D(GL_TEXTURE_2D, 0, rect.x, gl_y_offset(rect, height),
                            rect.width, rect.height, GL_RGBA, GL_UNSIGNED_BYTE, data)
            sent += rect.width * rect.height
        self.uploads += 1
        self.pixels += sent
        return sent


class Painter:
    """Stand-in for `pygame.draw` on the overlay: paints, and records what it painted.

    Every method keeps pygame's signature with the surface first, so a call site only has to swap
    `pygame.draw` for this proxy.
    """

    recorder: OpRecorder | None = None

    def _op(self, kind, surface, color, args, kwargs, rect):
        recorder = self.recorder
        if recorder is not None:
            key = (kind, _freeze(color), _freeze(tuple(args)),
                   tuple(sorted((name, _freeze(value)) for name, value in kwargs.items())))
            if rect is None or _has_unknown(key):
                recorder.unknown(rect or pygame.Rect(0, 0, *surface.get_size()))
            else:
                recorder.note(key, rect)
        return getattr(pygame.draw, kind)(surface, color, *args, **kwargs)

    def rect(self, surface, color, rect, width=0, **kwargs):
        return self._op("rect", surface, color, (rect, width), kwargs, _bounds("rect", (rect,), {}))

    def ellipse(self, surface, color, rect, width=0, **kwargs):
        return self._op("ellipse", surface, color, (rect, width), kwargs,
                        _bounds("ellipse", (rect,), {}))

    def circle(self, surface, color, center, radius, width=0, **kwargs):
        return self._op("circle", surface, color, (center, radius, width), kwargs,
                        _bounds("circle", (center, radius), {"width": width}))

    def line(self, surface, color, start, end, width=1, **kwargs):
        return self._op("line", surface, color, (start, end, width), kwargs,
                        _bounds("line", (start, end), {"width": width}))

    def polygon(self, surface, color, points, width=0, **kwargs):
        return self._op("polygon", surface, color, (tuple(points), width), kwargs,
                        _bounds("polygon", (points,), {"width": width}))

    def fill(self, surface, color, rect=None, **kwargs):
        target = pygame.Rect(rect) if rect is not None else pygame.Rect(0, 0, *surface.get_size())
        recorder = self.recorder
        if recorder is not None:
            key = ("fill", _freeze(color), _freeze(target))
            if _has_unknown(key):
                recorder.unknown(target)
            else:
                recorder.note(key, target)
        return surface.fill(color, rect, **kwargs)

    def blit(self, surface, source, dest, key=None, area=None, **kwargs):
        """A blit whose `key` describes `source`; without one the rect is dirty every frame."""
        if isinstance(dest, pygame.Rect):
            target = pygame.Rect(dest)
        else:
            target = pygame.Rect(0, 0, *source.get_size())
            target.topleft = tuple(dest)[:2]
        recorder = self.recorder
        if recorder is not None:
            if key is None:
                recorder.unknown(target)
            else:
                recorder.note(("blit", _freeze(key), _freeze(target), _freeze(area)), target)
        if area is not None:
            return surface.blit(source, dest, area, **kwargs)
        return surface.blit(source, dest, **kwargs)

    def blit_text(self, surface, source, dest, text, color, font_id, **kwargs) -> None:
        """A blit of a freshly rendered font surface, keyed by what was rendered."""
        self.blit(surface, source, dest, key=("text", text, _freeze(color), font_id), **kwargs)


painter = Painter()
