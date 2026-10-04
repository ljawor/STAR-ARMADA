"""Small damage-resolved contacts, not explosions or opaque billboard discs.

hit_geometry is pure and deterministic. draw_hit owns every begin/end and
restores all GL attributes it changes. It never mutates fx or simulation state.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

TAU = math.tau


def _unit(v):
    d = math.sqrt(sum(x*x for x in v))
    return tuple(x / d for x in v) if d > 1e-9 else (0., 0., 1.)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _offset(p, v, scale):
    return tuple(p[i] + v[i]*scale for i in range(3))


def _basis(n):
    u = _unit(_cross((0., 1., 0.) if abs(n[1]) < .9 else (1., 0., 0.), n))
    return u, _cross(n, u)


@lru_cache(maxsize=256)
def _fragments(seed):
    rng = random.Random(int(seed))  # private render RNG, never state.rng()
    return tuple((rng.random()*TAU, rng.uniform(.25, 1.), rng.uniform(.25, 1.),
                  rng.uniform(.5, 1.5)) for _ in range(9))


def hit_geometry(fx, radius=None, billboard_basis=None, visual_size=None):
    """Return batched (position, RGBA) vertices and curved-shell test samples.

    `radius` optionally aligns a shield contact with the renderer's tactical
    shell size floor. Maximum patch aperture is .42 rad (~4% of a sphere).
    """
    mesh = dict(triangles=[], lines=[], shell=[])
    kind = fx.get('kind', 'impact')
    shield = kind == 'shield_hit'
    t = max(0., float(fx.get('t', 0.)))
    life = .55 if shield else .42
    if t >= life:
        return mesh
    fade = (1. - t/life)**1.7
    n = _unit(fx.get('normal', tuple(-x for x in fx.get('direction', (0, 0, -1)))))
    u, v = _basis(n)
    p = tuple(fx['pos'])
    size = (float(visual_size) if visual_size is not None else
            min(18., max(1., float(fx.get('size', 5.)))))
    triangles, lines = mesh['triangles'], mesh['lines']
    cool = (.10, .62, 1.)
    warm = (1., .42, .08)

    def tri(a, b, c):
        triangles.extend((a, b, c))

    if shield:
        center = tuple(fx.get('center', _offset(p, n, -fx.get('radius', size*8))))
        r = max(1., float(radius if radius is not None else fx.get('radius', size*8)))
        p = _offset(center, n, r)
        # Geodesic cap: every sample lies on the actual spherical shell.
        def sphere(theta, phi):
            radial = tuple(n[k]*math.cos(theta) +
                           (u[k]*math.cos(phi)+v[k]*math.sin(phi))*math.sin(theta)
                           for k in range(3))
            q = _offset(center, radial, r)
            mesh['shell'].append(q)
            return q

        mesh['shell'].append(p)
        aperture = min(.19, max(.055, size/r))
        for i in range(12):
            a, b = TAU*i/12, TAU*(i+1)/12
            tri((p, (*cool, .20*fade*math.exp(-t*12))),
                (sphere(aperture, a), (*cool, 0.)),
                (sphere(aperture, b), (*cool, 0.)))
        # Two differently timed ripples crawl OUTWARD along the curved shell.
        for delay in (0., .085):
            age = t-delay
            if age < 0:
                continue
            theta = min(.42, aperture*.65 + age*.9)
            width = .012 + .013*(1-fade)
            strength = .26*fade*(1-age/.6)
            for i in range(16):
                a, b = TAU*i/16, TAU*(i+1)/16
                modulation = .7+.3*math.sin(a*5 + fx.get('seed', 0))
                c0 = (*cool, strength*modulation)
                c1 = (*cool, 0.)
                q0, q1 = sphere(theta, a), sphere(theta, b)
                q2, q3 = sphere(max(0., theta-width), b), sphere(max(0., theta-width), a)
                tri((q0, c0), (q1, c0), (q2, c1))
                tri((q0, c0), (q2, c1), (q3, c1))
    else:
        # Tiny irregular warm flash; radius never uses the full target radius.
        bu, bv = billboard_basis if billboard_basis is not None else (u, v)
        flash = math.exp(-t*32)*fade
        for i in range(10):
            a, b = TAU*i/10, TAU*(i+1)/10
            def rim(phi):
                rr = size*.32*(1+.18*math.sin(phi*5+fx.get('seed', 0)))
                return tuple(p[k]+rr*(bu[k]*math.cos(phi)+bv[k]*math.sin(phi)) for k in range(3))
            tri((p, (1., .64, .20, .52*flash)),
                (rim(a), (*warm, 0.)), (rim(b), (*warm, 0.)))
        # A tiny non-additive smoky fragment is intentionally dark, not luminous.
        # Emitted in a separate batch by draw_hit.
        mesh['smoke'] = []
        if t > .025:
            smoke_p = _offset(p, n, size*(.12+t*.5))
            smoke_r = size*(.10+t*.24)
            for i in range(12):
                a, b = TAU*i/12, TAU*(i+1)/12
                def smoke_rim(phi):
                    return tuple(smoke_p[k]+smoke_r*(bu[k]*math.cos(phi)+bv[k]*math.sin(phi)) for k in range(3))
                mesh['smoke'].extend(((smoke_p, (.11, .12, .14, .10*fade)),
                                      (smoke_rim(a), (.11, .12, .14, 0.)),
                                      (smoke_rim(b), (.11, .12, .14, 0.))))

    # Seeded asymmetric cool flecks / warm metal sparks. No screen-filling glow.
    for i, (angle, speed, lift, jitter) in enumerate(_fragments(fx.get('seed', 0))):
        if shield and i >= 5:
            break
        tangent = tuple(u[k]*math.cos(angle)+v[k]*math.sin(angle) for k in range(3))
        travel = size*(.08 + t*(2.5 if shield else 4.0)*speed)
        head = _offset(_offset(p, tangent, travel), n, size*t*lift)
        tail = _offset(head, tangent, -size*(.06+.14*speed)*fade)
        col = cool if shield else (1., .26+.35*lift, .06+.12*lift)
        lines.extend(((tail, (*col, .03*fade)), (head, (*col, .68*fade))))
        # Subpixel GL_LINES vanish at tactical scales. A thin tapered ribbon
        # has real raster coverage while remaining a spark, never a disc.
        lateral = tuple(u[k]*-math.sin(angle)+v[k]*math.cos(angle) for k in range(3))
        left = _offset(head, lateral, size*.08)
        right = _offset(head, lateral, -size*.08)
        tri((tail, (*col, .04*fade)), (left, (*col, .56*fade)),
            (right, (*col, .56*fade)))
        if not shield and i < 4:
            # Slanted metal triangles, with varied tones and cooling envelopes.
            side = _offset(head, v, size*.025*jitter)
            tri((head, (.64, .40, .22, .62*fade)),
                (tail, (.24, .20, .18, .2*fade)),
                (side, (.80, .53, .29, .45*fade)))
    return mesh


def draw_hit(renderer, fx):
    """Draw one contact inside the renderer's translucent-effects pass."""
    from OpenGL import GL
    radius = None
    if fx.get('kind') == 'shield_hit':
        # Use exactly the standing shell's tactical minimum radius.
        from render.renderer import SHIELD_MIN_PX
        center = fx.get('center', fx['pos'])
        ppw = renderer._px_per_world(center)
        if ppw <= 0:
            return
        radius = float(fx.get('radius', 1.))
        if not fx.get('visual_contact'):
            radius = max(radius, SHIELD_MIN_PX*.5/ppw)
    right, up, _ = renderer.camera.basis()
    visual_size = None
    ppw = renderer._px_per_world(fx['pos'])
    if ppw <= 0:
        return
    if fx.get('kind') != 'shield_hit':
        # At tactical zoom a physically-sized spark fell entirely between
        # pixel centers. Keep a 7px contact, not an explosion-sized billboard.
        visual_size = max(min(18., float(fx.get('size', 5.))), 7./ppw)
        if fx.get('visual_contact'):
            visual_size = min(visual_size, float(fx.get('size', 5.)))
    mesh = hit_geometry(fx, radius=radius, billboard_basis=(right, up),
                        visual_size=visual_size)
    if not mesh['triangles'] and not mesh['lines']:
        return
    GL.glPushAttrib(GL.GL_ENABLE_BIT | GL.GL_CURRENT_BIT | GL.GL_COLOR_BUFFER_BIT |
                    GL.GL_DEPTH_BUFFER_BIT | GL.GL_LINE_BIT)
    try:
        GL.glDisable(GL.GL_LIGHTING)
        # Contacts are surface markings; their visual contact radius is an
        # approximation, so compose them above opaque armor, not inside it.
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_TEXTURE_2D)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_BLEND)
        GL.glDepthMask(False)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        # Alpha blending instead of additive saturation, even under many hits.
        import numpy as np
        GL.glPushClientAttrib(GL.GL_CLIENT_VERTEX_ARRAY_BIT)
        try:
            GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
            GL.glEnableClientState(GL.GL_COLOR_ARRAY)
            for mode, vertices in ((GL.GL_TRIANGLES, mesh['triangles']),
                                   (GL.GL_LINES, mesh['lines']),
                                   (GL.GL_TRIANGLES, mesh.get('smoke', []))):
                if vertices:
                    # One array draw, not hundreds of Python-to-GL vertex calls.
                    positions = np.asarray([v[0] for v in vertices], dtype=np.float32)
                    colors = np.asarray([v[1] for v in vertices], dtype=np.float32)
                    GL.glLineWidth(1.)
                    GL.glVertexPointer(3, GL.GL_FLOAT, 0, positions)
                    GL.glColorPointer(4, GL.GL_FLOAT, 0, colors)
                    GL.glDrawArrays(mode, 0, len(vertices))
        finally:
            GL.glPopClientAttrib()
    finally:
        GL.glPopAttrib()
