"""Validated presentation preferences; importing this module never opens SDL/GL."""

RESOLUTIONS = ('auto', '1280x720', '1280x800', '1440x900', '1600x900',
               '1920x1080', '1920x1200', '2560x1440', '2560x1600', '3840x2160')


def validate_resolution(value):
    """Only bounded, shipped presets may enter the display allocation path."""
    return value if isinstance(value, str) and value in RESOLUTIONS else 'auto'


def window_size(resolution, desktop, *, fullscreen=False, smoke=False):
    """Auto preserves the old window size, or the desktop in fullscreen."""
    if (not isinstance(desktop, (tuple, list)) or len(desktop) != 2
            or any(type(n) is not int or not 1 <= n <= limit
                   for n, limit in zip(desktop, (7680, 4320)))):
        desktop = (1440, 900)
    resolution = validate_resolution(resolution)
    if smoke:
        return (1280, 800)
    if resolution != 'auto':
        return tuple(map(int, resolution.split('x')))
    if fullscreen:
        return tuple(desktop)
    scale = min(1.0, desktop[0] / 1440, desktop[1] / 900)
    return max(1, round(1440 * scale)), max(1, round(900 * scale))


def open_display(pygame, resolution, desktop, flags, *, fullscreen=False, smoke=False):
    """Return the actual surface and effective mode after bounded SDL fallbacks.

    Try the chosen mode, desktop fullscreen when appropriate, then the old safe
    window. Never persist a fallback over the user's preference. A total failure
    raises the last SDL error; duplicated attempts are not retried.
    """
    attempts = [(window_size(resolution, desktop, fullscreen=fullscreen, smoke=smoke), fullscreen)]
    if fullscreen:
        attempts.append((window_size('auto', desktop, fullscreen=True, smoke=smoke), True))
    attempts.append((window_size('auto', desktop, smoke=smoke), False))
    seen = set()
    last_error = None
    for size, full in attempts:
        if (size, full) in seen:
            continue
        seen.add((size, full))
        try:
            mode_flags = (flags & ~pygame.FULLSCREEN) | (pygame.FULLSCREEN if full else 0)
            return pygame.display.set_mode(size, mode_flags), full
        except pygame.error as exc:
            last_error = exc
    assert last_error is not None  # At least one distinct mode was attempted.
    raise last_error
