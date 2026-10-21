// W05 slice 3c: damage contacts, ported from render/hit_effects.py::hit_geometry.
//
// A contact is small, damage-resolved and deliberately not an explosion: a geodesic cap crawling on
// the shield sphere with two ripples, or a warm flash with a little smoke and seeded sparks on bare
// hull. Every shape is a pure function of position, normal, size, age and seed, so the parameters
// cross the bridge and the geometry is rebuilt here with the renderer's own numbers.
//
// Two things are this window's business because they need the camera:
//
//   * a shield contact is floored to SHIELD_MIN_PX across (the standing shell's own figure), and
//   * a hull contact is floored to 7 px and capped at the effect's own size.
//
// The renderer applies both with its own `px_per_world`; here `pxPerWorld` is passed in from the
// window's camera, so a contact stays readable at any zoom on either side.
//
// Sparks come from Python's `random.Random(seed)` sequence - the fragments are identical on both
// sides because `PyRandom` is CPython's Mersenne Twister with the same seeding path (an int seed
// goes through init_by_array), not a lookalike hash.
#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace armada {
namespace fx {

// renderer.py::SHIELD_MIN_PX - the standing shell's readability floor, reused for its contacts.
constexpr double kHitShieldMinPx = 74.0;
constexpr double kHitHullMinPx = 7.0;
constexpr double kHitShieldLife = 0.55;   // hit_geometry: `life`
constexpr double kHitHullLife = 0.42;
constexpr double kHitCool[3] = {0.10, 0.62, 1.00};
constexpr double kHitWarm[3] = {1.00, 0.42, 0.08};
constexpr int kHitRippleSegments = 16;
constexpr int kHitCapSegments = 12;
constexpr int kHitFlashSegments = 10;
constexpr int kHitSmokeSegments = 12;

struct HitVertex {
  double x, y, z;
  double r, g, b, a;
};

struct HitCounters {
  size_t capTriangles = 0;     // the 12-triangle contact fan on the shell
  size_t rippleTriangles = 0;  // the two ripples crawling outward
  size_t sparkTriangles = 0;   // ribbons and metal slivers
  size_t smokeTriangles = 0;   // the dark fragment, drawn in its own pass
};

// CPython's Mersenne Twister, seeded the way `random.Random(<int>)` seeds it.
class PyRandom {
 public:
  explicit PyRandom(uint32_t seed) {
    const uint32_t key[1] = {seed};
    initByArray(key, 1);
  }

  uint32_t next() {
    if (index_ >= kState) {
      const uint32_t* mt = state_;
      for (int i = 0; i < kState; ++i) {
        const uint32_t y = (mt[i] & kUpper) | (mt[(i + 1) % kState] & kLower);
        uint32_t value = mt[(i + kM) % kState] ^ (y >> 1);
        if (y & 1u)
          value ^= kMatrix;
        state_[i] = value;
      }
      index_ = 0;
    }
    uint32_t y = state_[index_++];
    y ^= y >> 11;
    y ^= (y << 7) & 0x9d2c5680u;
    y ^= (y << 15) & 0xefc60000u;
    y ^= y >> 18;
    return y;
  }

  // random.random(): 27 bits from one draw, 26 from the next, over 2^53.
  double random() {
    const uint32_t a = next() >> 5;
    const uint32_t b = next() >> 6;
    return (a * 67108864.0 + b) / 9007199254740992.0;
  }

  double uniform(double low, double high) { return low + (high - low) * random(); }

 private:
  static constexpr int kState = 624;
  static constexpr int kM = 397;
  static constexpr uint32_t kMatrix = 0x9908b0dfu;
  static constexpr uint32_t kUpper = 0x80000000u;
  static constexpr uint32_t kLower = 0x7fffffffu;

  void initGenrand(uint32_t seed) {
    state_[0] = seed;
    for (int i = 1; i < kState; ++i)
      state_[i] = 1812433253u * (state_[i - 1] ^ (state_[i - 1] >> 30)) + uint32_t(i);
    index_ = kState;
  }

  void initByArray(const uint32_t* key, size_t length) {
    initGenrand(19650218u);
    int i = 1, j = 0;
    size_t k = kState > length ? size_t(kState) : length;
    for (; k; --k) {
      state_[i] = (state_[i] ^ ((state_[i - 1] ^ (state_[i - 1] >> 30)) * 1664525u)) +
                  key[j] + uint32_t(j);
      ++i;
      ++j;
      if (i >= kState) {
        state_[0] = state_[kState - 1];
        i = 1;
      }
      if (size_t(j) >= length)
        j = 0;
    }
    for (k = size_t(kState) - 1; k; --k) {
      state_[i] = (state_[i] ^ ((state_[i - 1] ^ (state_[i - 1] >> 30)) * 1566083941u)) -
                  uint32_t(i);
      ++i;
      if (i >= kState) {
        state_[0] = state_[kState - 1];
        i = 1;
      }
    }
    state_[0] = 0x80000000u;
  }

  uint32_t state_[kState]{};
  int index_ = kState;
};

struct HitFragment {
  double angle, speed, lift, jitter;
};

// hit_effects.py::_fragments - nine fragments, four numbers each, from the contact's own seed.
inline std::array<HitFragment, 9> hitFragments(uint32_t seed) {
  PyRandom rng(seed);
  std::array<HitFragment, 9> out{};
  const double tau = 6.283185307179586;
  for (auto& fragment : out) {
    fragment.angle = rng.random() * tau;
    fragment.speed = rng.uniform(0.25, 1.0);
    fragment.lift = rng.uniform(0.25, 1.0);
    fragment.jitter = rng.uniform(0.5, 1.5);
  }
  return out;
}

namespace detail {

inline void unit(const double v[3], double out[3]) {
  const double length = std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  if (length > 1e-9) {
    out[0] = v[0] / length;
    out[1] = v[1] / length;
    out[2] = v[2] / length;
  } else {
    out[0] = 0.0;
    out[1] = 0.0;
    out[2] = 1.0;
  }
}

inline void cross(const double a[3], const double b[3], double out[3]) {
  out[0] = a[1] * b[2] - a[2] * b[1];
  out[1] = a[2] * b[0] - a[0] * b[2];
  out[2] = a[0] * b[1] - a[1] * b[0];
}

// hit_effects.py::_basis - a stable tangent frame for the contact normal.
inline void basis(const double n[3], double u[3], double v[3]) {
  const bool upIsStable = std::abs(n[1]) < 0.9;
  const double reference[3] = {upIsStable ? 0.0 : 1.0, upIsStable ? 1.0 : 0.0, 0.0};
  cross(reference, n, u);
  unit(u, u);
  cross(n, u, v);
}

inline double dot(const double a[3], const double b[3]) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

inline void push(std::vector<HitVertex>& out, const double p[3], double r, double g, double b,
                 double a) {
  out.push_back({p[0], p[1], p[2], r, g, b, a});
}

}  // namespace detail

// Rebuild one contact. `a` is the shell centre (shield) or the contact point (hull); `normal` is the
// outward normal; `radius` is the shell radius (shield) or the effect size (hull); `size` is the
// effect's own visual size, which feeds the cap aperture and the flash/smoke extent.
inline void appendHit(bool shield, const double a[3], const double normal[3], double radius,
                      double size, double age, uint32_t seed, bool visualContact,
                      double pxPerWorld, const double right[3], const double up[3],
                      std::vector<HitVertex>& triangles, std::vector<HitVertex>& smoke,
                      HitCounters* counters) {
  const double life = shield ? kHitShieldLife : kHitHullLife;
  const double t = std::max(0.0, age);
  if (t >= life)
    return;
  const double fade = std::pow(1.0 - t / life, 1.7);

  double n[3], u[3], v[3];
  detail::unit(normal, n);
  detail::basis(n, u, v);

  double p[3] = {a[0], a[1], a[2]};
  double visualSize = size;
  if (shield) {
    double shell = radius;
    if (!visualContact && pxPerWorld > 0.0)
      shell = std::max(shell, kHitShieldMinPx * 0.5 / pxPerWorld);
    for (int k = 0; k < 3; ++k)
      p[k] = a[k] + n[k] * shell;
    radius = shell;
  } else {
    // At tactical zoom a physically sized spark falls between pixel centres; the renderer keeps a
    // 7 px contact, and a contact the simulation already resolved visually keeps its own size.
    if (pxPerWorld > 0.0)
      visualSize = std::max(std::min(18.0, size), kHitHullMinPx / pxPerWorld);
    if (visualContact)
      visualSize = std::min(visualSize, size);
  }

  if (shield) {
    // Geodesic cap: every sample lies on the actual spherical shell.
    auto sphere = [&](double theta, double phi, double out[3]) {
      const double ct = std::cos(theta), st = std::sin(theta);
      const double cp = std::cos(phi), sp = std::sin(phi);
      for (int k = 0; k < 3; ++k)
        out[k] = a[k] + (n[k] * ct + (u[k] * cp + v[k] * sp) * st) * radius;
    };
    const double aperture = std::min(0.19, std::max(0.055, size / radius));
    const double centreAlpha = 0.20 * fade * std::exp(-t * 12.0);
    for (int i = 0; i < kHitCapSegments; ++i) {
      const double lo = 6.283185307179586 * i / kHitCapSegments;
      const double hi = 6.283185307179586 * (i + 1) / kHitCapSegments;
      double q0[3], q1[3];
      sphere(aperture, lo, q0);
      sphere(aperture, hi, q1);
      detail::push(triangles, p, kHitCool[0], kHitCool[1], kHitCool[2], centreAlpha);
      detail::push(triangles, q0, kHitCool[0], kHitCool[1], kHitCool[2], 0.0);
      detail::push(triangles, q1, kHitCool[0], kHitCool[1], kHitCool[2], 0.0);
      ++counters->capTriangles;
    }
    // Two differently timed ripples crawl outward along the curved shell.
    for (const double delay : {0.0, 0.085}) {
      const double rippleAge = t - delay;
      if (rippleAge < 0.0)
        continue;
      const double theta = std::min(0.42, aperture * 0.65 + rippleAge * 0.9);
      const double width = 0.012 + 0.013 * (1.0 - fade);
      const double strength = 0.26 * fade * (1.0 - rippleAge / 0.6);
      for (int i = 0; i < kHitRippleSegments; ++i) {
        const double lo = 6.283185307179586 * i / kHitRippleSegments;
        const double hi = 6.283185307179586 * (i + 1) / kHitRippleSegments;
        const double modulation = 0.7 + 0.3 * std::sin(lo * 5.0 + double(seed));
        const double gain = strength * modulation;
        double q0[3], q1[3], q2[3], q3[3];
        sphere(theta, lo, q0);
        sphere(theta, hi, q1);
        sphere(std::max(0.0, theta - width), hi, q2);
        sphere(std::max(0.0, theta - width), lo, q3);
        detail::push(triangles, q0, kHitCool[0], kHitCool[1], kHitCool[2], gain);
        detail::push(triangles, q1, kHitCool[0], kHitCool[1], kHitCool[2], gain);
        detail::push(triangles, q2, kHitCool[0], kHitCool[1], kHitCool[2], 0.0);
        detail::push(triangles, q0, kHitCool[0], kHitCool[1], kHitCool[2], gain);
        detail::push(triangles, q2, kHitCool[0], kHitCool[1], kHitCool[2], 0.0);
        detail::push(triangles, q3, kHitCool[0], kHitCool[1], kHitCool[2], 0.0);
        counters->rippleTriangles += 2;
      }
    }
  } else {
    // Tiny irregular warm flash; the radius never uses the full hull radius.
    const double flash = std::exp(-t * 32.0) * fade;
    auto rim = [&](double phi, double out[3]) {
      const double rr = visualSize * 0.32 * (1.0 + 0.18 * std::sin(phi * 5.0 + double(seed)));
      for (int k = 0; k < 3; ++k)
        out[k] = p[k] + rr * (right[k] * std::cos(phi) + up[k] * std::sin(phi));
    };
    for (int i = 0; i < kHitFlashSegments; ++i) {
      const double lo = 6.283185307179586 * i / kHitFlashSegments;
      const double hi = 6.283185307179586 * (i + 1) / kHitFlashSegments;
      double q0[3], q1[3];
      rim(lo, q0);
      rim(hi, q1);
      detail::push(triangles, p, 1.0, 0.64, 0.20, 0.52 * flash);
      detail::push(triangles, q0, kHitWarm[0], kHitWarm[1], kHitWarm[2], 0.0);
      detail::push(triangles, q1, kHitWarm[0], kHitWarm[1], kHitWarm[2], 0.0);
      ++counters->sparkTriangles;
    }
    // A tiny non-additive smoky fragment: deliberately dark, so it rides its own batch.
    if (t > 0.025) {
      double smokeP[3];
      for (int k = 0; k < 3; ++k)
        smokeP[k] = p[k] + n[k] * visualSize * (0.12 + t * 0.5);
      const double smokeR = visualSize * (0.10 + t * 0.24);
      auto smokeRim = [&](double phi, double out[3]) {
        for (int k = 0; k < 3; ++k)
          out[k] = smokeP[k] + smokeR * (right[k] * std::cos(phi) + up[k] * std::sin(phi));
      };
      for (int i = 0; i < kHitSmokeSegments; ++i) {
        const double lo = 6.283185307179586 * i / kHitSmokeSegments;
        const double hi = 6.283185307179586 * (i + 1) / kHitSmokeSegments;
        double q0[3], q1[3];
        smokeRim(lo, q0);
        smokeRim(hi, q1);
        detail::push(smoke, smokeP, 0.11, 0.12, 0.14, 0.10 * fade);
        detail::push(smoke, q0, 0.11, 0.12, 0.14, 0.0);
        detail::push(smoke, q1, 0.11, 0.12, 0.14, 0.0);
        ++counters->smokeTriangles;
      }
    }
  }

  // Seeded asymmetric cool flecks / warm metal sparks. The renderer also emits a one-pixel GL_LINES
  // pair per spark, which bgfx cannot express; the tapered ribbon below is the geometry the comment
  // in hit_effects.py calls the one with real raster coverage.
  const auto fragments = hitFragments(seed);
  for (int i = 0; i < 9; ++i) {
    if (shield && i >= 5)
      break;
    const auto& fragment = fragments[size_t(i)];
    double tangent[3], lateral[3];
    for (int k = 0; k < 3; ++k) {
      tangent[k] = u[k] * std::cos(fragment.angle) + v[k] * std::sin(fragment.angle);
      lateral[k] = u[k] * -std::sin(fragment.angle) + v[k] * std::cos(fragment.angle);
    }
    const double travel = visualSize * (0.08 + t * (shield ? 2.5 : 4.0) * fragment.speed);
    double head[3], tail[3];
    for (int k = 0; k < 3; ++k) {
      head[k] = p[k] + tangent[k] * travel + n[k] * visualSize * t * fragment.lift;
      tail[k] = head[k] - tangent[k] * visualSize * (0.06 + 0.14 * fragment.speed) * fade;
    }
    const double colour[3] = {shield ? kHitCool[0] : 1.0,
                              shield ? kHitCool[1] : 0.26 + 0.35 * fragment.lift,
                              shield ? kHitCool[2] : 0.06 + 0.12 * fragment.lift};
    double left[3], rightPoint[3];
    for (int k = 0; k < 3; ++k) {
      left[k] = head[k] + lateral[k] * visualSize * 0.08;
      rightPoint[k] = head[k] - lateral[k] * visualSize * 0.08;
    }
    detail::push(triangles, tail, colour[0], colour[1], colour[2], 0.04 * fade);
    detail::push(triangles, left, colour[0], colour[1], colour[2], 0.56 * fade);
    detail::push(triangles, rightPoint, colour[0], colour[1], colour[2], 0.56 * fade);
    ++counters->sparkTriangles;
    if (!shield && i < 4) {
      // Slanted metal triangles, with varied tones and cooling envelopes.
      double side[3];
      for (int k = 0; k < 3; ++k)
        side[k] = head[k] + v[k] * visualSize * 0.025 * fragment.jitter;
      detail::push(triangles, head, 0.64, 0.40, 0.22, 0.62 * fade);
      detail::push(triangles, tail, 0.24, 0.20, 0.18, 0.20 * fade);
      detail::push(triangles, side, 0.80, 0.53, 0.29, 0.45 * fade);
      ++counters->sparkTriangles;
    }
  }
}

}  // namespace fx
}  // namespace armada
