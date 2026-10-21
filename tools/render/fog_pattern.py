"""A deterministic fog mask, used by both renderers for the slice-4 parity frame.

The live mask moves with the fleet - sensors ride on hulls, so two captures of "the same" mask a few
ticks apart are not the same mask at all, and comparing them would measure the simulation rather than
the transport. This pattern is fixed: a visible third, a charted third, an unexplored third, plus a
single see-through cell in the middle of the unexplored block so a transposed or mirrored upload
shows up as a picture that is wrong rather than as a number that is off.

Nothing here describes real visibility; the frame is labelled synthetic in the artifact report.
"""
from __future__ import annotations

CELLS = 72


def pattern(cells: int = CELLS) -> list[tuple[int, int, int, int]]:
    """Return (width, height, rgb, alpha) runs in the order a pygame surface wants them."""
    states = [(0, 0, 0, 0), (12, 22, 38, 155), (3, 6, 13, 255)]
    pixels = []
    hole = (cells // 2, cells // 2)
    for z in range(cells):
        for x in range(cells):
            if (x, z) == hole:
                pixels.append(states[0])
            elif x < cells // 3:
                pixels.append(states[0])          # the team's sensors reach the left third
            elif x < 2 * cells // 3:
                pixels.append(states[1])          # charted, not currently seen
            else:
                pixels.append(states[2])          # never explored
    return pixels


def surface(cells: int = CELLS, pygame_module=None):
    import pygame
    module = pygame_module or pygame
    picture = module.Surface((cells, cells), module.SRCALPHA)
    for z in range(cells):
        for x in range(cells):
            picture.set_at((x, z), pattern(cells)[z * cells + x])
    return picture
