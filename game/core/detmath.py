"""Deterministic simulation math — no platform `libm` in the simulation.

IEEE 754 `+  -  *  /` and `sqrt` are correctly rounded, so every platform computes
the same bits from them. `sin`, `cos` and `atan2` are not: they come from the
platform's `libm`, and macOS and Windows differ by 1 ULP. That is not academic —
a mixed Windows/macOS LAN pair hashed `anchor.x + sin(ang) * r` while placing a
start shipyard and got `11496.363787673816` on one side and `11496.363787673814…`
on the other (issue #56), so the lockstep checksums differed from tick 0 and the
match would desync the moment it connected.

Everything here is written from the correctly-rounded primitives only, so peers
compute bit-identical values. Accuracy is a few ULP — far below anything gameplay
can observe — and identical everywhere, which is the property the simulation
needs. Rendering keeps the platform's fast `math` functions.

Only functions that ARE deterministic are exported: the exact ones re-exported
from `math` (`sqrt`, `floor`, `ceil`, `isfinite`, `pi`, `radians`, `dist`, …) and
the ones implemented here (`sin`, `cos`, `atan2`, `tan`, `hypot`). `exp`, `log` and
`pow` are deliberately absent: they are libm functions with no deterministic
implementation here yet, so a simulation module that reaches for one fails
loudly instead of silently desynchronizing a mixed-platform match. Add them the
same way if the simulation ever needs them.

Range reduction uses a three-part split of pi/2 (verified against a 60-digit
`Decimal` reconstruction, error 4.7e-50); the polynomials are the fdlibm kernels
CPython itself uses. Simulation angles are bounded by map coordinates, so the
simple reduction is accurate enough; a huge argument would lose accuracy but stay
deterministic.
"""
from __future__ import annotations

from math import (ceil, copysign, degrees, dist, fabs, floor, fmod, inf,
                  isfinite, isinf, isnan, nan, nextafter, pi, radians, sqrt, trunc)

__all__ = ['sin', 'cos', 'tan', 'atan2', 'hypot', 'ceil', 'copysign', 'degrees',
           'dist', 'fabs', 'floor', 'fmod', 'inf', 'isfinite', 'isinf', 'isnan',
           'nan', 'nextafter', 'pi', 'radians', 'sqrt', 'trunc']

# pi/2 in three exactly representable parts, residual 2.1e-43. The leading part
# is truncated to 33 significant bits on purpose: k * _HALF_PI_HI is then EXACT for
# every |k| < 2**20, so only the tiny second and third terms round (a 3-part split
# whose leading part carries all 53 bits leaves k * hi rounded by ~7e-13, which
# destroys sin() near a multiple of pi/2).
_HALF_PI_HI = 1.5707963267341256
_HALF_PI_MID = 6.077100506506192e-11
_HALF_PI_LO = 3.5215598651832e-27
_HALF_PI = 1.5707963267948966
_QUARTER_PI_HI = 0.7853981633670628
_QUARTER_PI_MID = 3.038550253253096e-11
_QUARTER_PI_LO = 1.7607799325916e-27
_TWO_OVER_PI = 0.6366197723675814
_TAN_PI_8 = 0.41421356237309503

_S1, _S2, _S3 = (-1.66666666666666324348e-01, 8.33333333332248946124e-03,
                 -1.98412698298579493134e-04)
_S4, _S5, _S6 = (2.75573137070700676789e-06, -2.50507602534068634195e-08,
                 1.58969099521155010221e-10)

_C1, _C2, _C3 = (4.16666666666666019037e-02, -1.38888888888741095749e-03,
                 2.48015872894767294178e-05)
_C4, _C5, _C6 = (-2.75573143513906633035e-07, 2.08757232129817482790e-09,
                 -1.13596475577881948265e-11)

_ATAN_COEFFS = (3.33333333333329318027e-01, -1.99999999998764832476e-01,
                 1.42857142725034663711e-01, -1.11111104054726221193e-01,
                 9.09088713343650656196e-02, -7.69187620504482999495e-02,
                 6.66107313738753120669e-02, -5.83357013379057348645e-02,
                 4.97687799461593236017e-02, -3.65315727442169155270e-02,
                 1.62858201153657823623e-02)


def _sin_kernel(x):
    """sin on |x| <= pi/4 (fdlibm kernel): multiplies and adds only."""
    z = x * x
    v = z * x
    r = _S2 + z * (_S3 + z * (_S4 + z * (_S5 + z * _S6)))
    return x + v * (_S1 + z * r)


def _cos_kernel(x):
    """cos on |x| <= pi/4 (fdlibm kernel)."""
    z = x * x
    r = z * (_C1 + z * (_C2 + z * (_C3 + z * (_C4 + z * (_C5 + z * _C6)))))
    return 1.0 - (0.5 * z - z * r)


def _quadrant(x):
    """Nearest multiple of pi/2 and the remainder in [-pi/4, pi/4]."""
    k = int(floor(x * _TWO_OVER_PI + 0.5))
    r = ((x - k * _HALF_PI_HI) - k * _HALF_PI_MID) - k * _HALF_PI_LO
    return k, r


def sin(x):
    """Deterministic sine: identical bits on every platform, a few ULP of libm."""
    if x != x or isinf(x):
        return nan
    if x == 0.0:
        return x
    k, r = _quadrant(x)
    quadrant = k & 3
    if quadrant == 0:
        return _sin_kernel(r)
    if quadrant == 1:
        return _cos_kernel(r)
    if quadrant == 2:
        return -_sin_kernel(r)
    return -_cos_kernel(r)


def cos(x):
    """Deterministic cosine."""
    if x != x or isinf(x):
        return nan
    k, r = _quadrant(x)
    quadrant = (k + 1) & 3
    if quadrant == 0:
        return _sin_kernel(r)
    if quadrant == 1:
        return _cos_kernel(r)
    if quadrant == 2:
        return -_sin_kernel(r)
    return -_cos_kernel(r)


def tan(x):
    """Deterministic tangent, from the deterministic sine and cosine."""
    denom = cos(x)
    if denom == 0.0:
        return copysign(inf, sin(x))
    return sin(x) / denom


def _atan_small(t):
    """atan on |t| <= tan(pi/8) (fdlibm coefficients)."""
    z = t * t
    w = z * z
    a = _ATAN_COEFFS
    s1 = z * (a[0] + w * (a[2] + w * (a[4] + w * (a[6] + w * (a[8] + w * a[10])))))
    s2 = w * (a[1] + w * (a[3] + w * (a[5] + w * (a[7] + w * a[9]))))
    return t - t * (s1 + s2)


def _atan(t):
    """atan on t >= 0, from `_atan_small` and the half/quarter-angle identities."""
    if t <= _TAN_PI_8:
        return _atan_small(t)
    if t <= 1.0:
        # atan(t) = pi/4 + atan((t - 1) / (t + 1))
        u = (t - 1.0) / (t + 1.0)
        return (_QUARTER_PI_HI + _atan_small(u)) + _QUARTER_PI_MID
    u = 1.0 / t
    if u <= _TAN_PI_8:
        # atan(t) = pi/2 - atan(1/t)
        return (_HALF_PI_HI - _atan_small(u)) + _HALF_PI_MID
    v = (u - 1.0) / (u + 1.0)
    inner = (_QUARTER_PI_HI + _atan_small(v)) + _QUARTER_PI_MID
    return (_HALF_PI_HI - inner) + _HALF_PI_MID


def atan2(y, x):
    """Deterministic arctangent of (y, x), libm convention: the result is in [-pi, pi]."""
    if x != x or y != y:
        return nan
    if isinf(y):
        if isinf(x):
            return copysign(3 * _QUARTER_PI_HI, y) if x < 0 else copysign(0.0, y)
        return copysign(_HALF_PI, y)
    if isinf(x):
        return copysign(0.0, y) if x > 0 else copysign(pi, y)
    if x == 0.0:
        # atan2(+-0, +0) = +-0, atan2(+-0, -0) = +-pi: the sign of x matters here.
        if y == 0.0:
            return copysign(0.0, y) if copysign(1.0, x) > 0 else copysign(pi, y)
        return copysign(_HALF_PI, y)
    if y == 0.0:
        return copysign(0.0, y) if x > 0 else copysign(pi, y)
    angle = _atan(abs(y) / abs(x))
    if x > 0.0:
        return angle if y > 0.0 else -angle
    if y > 0.0:
        return pi - angle
    return angle - pi


def hypot(*coordinates):
    """Deterministic hypot: the largest magnitude scales the sum, so squares cannot overflow."""
    largest = 0.0
    for value in coordinates:
        magnitude = abs(value)
        if magnitude != magnitude:
            return magnitude
        if isinf(magnitude):
            return inf
        if magnitude > largest:
            largest = magnitude
    if largest == 0.0:
        return 0.0
    total = 0.0
    for value in coordinates:
        scaled = value / largest
        total += scaled * scaled
    return largest * sqrt(total)
