"""Closed beveled armor lofts, generated once then cached in GL display lists.

Coordinates remain in model space; neither geometry nor materials touch sim RNG.
"""
from __future__ import annotations
import math


def armor_loft(sections, bevel=2.0):
    """Return (unit normal, triangle) tuples from (z, halfwidth, top, bottom).

    Eight-sided cross sections retain flat readable decks while chamfered edges
    catch the key light. Width can taper along the hull (unlike a scaled cube).
    """
    if len(sections) < 2 or bevel <= 0:
        raise ValueError('a loft needs two sections and a positive bevel')
    rings = []
    for z, w, top, bottom in sections:
        if w <= 0 or top <= bottom:
            raise ValueError('sections require positive width and height')
        b = min(bevel, w * .45, (top-bottom) * .3)
        rings.append([(-w+b, top, z), (w-b, top, z), (w, top-b, z),
                      (w, bottom+b, z), (w-b, bottom, z), (-w+b, bottom, z),
                      (-w, bottom+b, z), (-w, top-b, z)])
    if any(b[0] <= a[0] for a,b in zip(sections, sections[1:])):
        raise ValueError('section z coordinates must increase')
    result = []

    def triangle(a,b,c,ref):
        u = tuple(b[i]-a[i] for i in range(3))
        v = tuple(c[i]-a[i] for i in range(3))
        n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        if sum(n[i]*((a[i]+b[i]+c[i])/3-ref[i]) for i in range(3)) < 0:
            b,c = c,b
            n = tuple(-x for x in n)
        length = math.sqrt(sum(x*x for x in n))
        result.append((tuple(x/length for x in n), (a,b,c)))

    for index,(a,b) in enumerate(zip(rings, rings[1:])):
        ref = (0, (sections[index][2]+sections[index][3])/2,
               (sections[index][0]+sections[index+1][0])/2)
        for i in range(8):
            j = (i+1)%8
            triangle(a[i], b[i], b[j], ref)
            triangle(a[i], b[j], a[j], ref)
    for ring,section,direction in ((rings[0], sections[0], 1), (rings[-1], sections[-1], -1)):
        center = (0, (section[2]+section[3])/2, section[0])
        ref = (center[0], center[1], center[2]+direction)
        for i in range(8):
            triangle(center, ring[i], ring[(i+1)%8], ref)
    return result
