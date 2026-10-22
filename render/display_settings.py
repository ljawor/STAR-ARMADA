"""Validated, presentation-only display preferences (no SDL/GL at import time)."""

RESOLUTIONS = ('auto', '1280x720', '1280x800', '1440x900', '1600x900',
               '1920x1080', '1920x1200', '2560x1440', '2560x1600', '3840x2160')


def validate_resolution(value):
    return value if isinstance(value, str) and value in RESOLUTIONS else 'auto'


def window_size(resolution, desktop, *, fullscreen=False, smoke=False):
    """Auto keeps the existing window size; fullscreen auto uses the desktop."""
    if (not isinstance(desktop, (tuple, list)) or len(desktop) != 2
            or any(type(n) is not int or n <= 0 for n in desktop)):
        desktop = (1440, 900)
    resolution = validate_resolution(resolution)
    if smoke:
        return (1280, 800)
    if resolution != 'auto':
        return tuple(map(int, resolution.split('x')))
    if fullscreen:
        return tuple(desktop)
    scale = min(1.0, desktop[0] / 1440, desktop[1] / 900)
    return round(1440 * scale), round(900 * scale)


def open_display(pygame, resolution, desktop, flags, *, fullscreen=False, smoke=False):
    """Try the saved size, then desktop fullscreen, then a safe window.

    Return the real surface and effective fullscreen state; callers must use its
    size rather than the requested mode for native buffers and pointer scaling.
    A total display failure still raises the original SDL error normally.
    """
    requested = window_size(resolution, desktop, fullscreen=fullscreen, smoke=smoke)
    attempts = [(requested, fullscreen)]
    if fullscreen:
        attempts.append((window_size('auto', desktop, fullscreen=True, smoke=smoke), True))
    attempts.append((window_size('auto', desktop, smoke=smoke), False))
    seen = set()
    for size, full in attempts:
        if (size, full) in seen:
            continue
        seen.add((size, full))
        try:
            mode_flags = (flags & ~pygame.FULLSCREEN) | (pygame.FULLSCREEN if full else 0)
            return pygame.display.set_mode(size, mode_flags), full
        except pygame.error:
            if (size, full) == attempts[-1]:
                raise
    raise RuntimeError('No usable display mode')
