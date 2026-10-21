// W05 slice 3b: the layered detonation, ported term for term from
// render/renderer.py::_draw_explosion.
//
// The blast is carried as *parameters* - position, size, age, seed - not as geometry, because a
// single station-scale blast is ~40 irregular shells and several thousand vertices. Sending that
// every frame would dwarf the frame ring itself; the window rebuilds it with the same formulas, the
// same seed and the same colour ramp, which is what keeps it the same phenomenon.
//
// Faithfulness notes that matter:
//   * `fxRing` reproduces the lumpy silhouette (radius harmonic) and the deliberately subtle
//     per-angle brightness jitter, at 0.84..1.0 - a stronger jitter renders as radial spokes.
//   * `glowRing` draws ONE quad strip per band with exactly two vertices per angle. Three
//     vertices per angle makes a strip pair outer(i) with inner(i+1), which draws a full-width
//     radial quad per segment and reads as a dark spoke.
//   * the shock shell ends on a nearly transparent outer vertex; a bright outer edge is a crisp
//     contour and a crisp contour at this size reads as a drawn donut.
#pragma once

#include <array>
#include <cmath>
#include <cstdint>
#include <vector>

namespace armada {
namespace fx {

struct Vertex {
  float x, y, z, r, g, b, a;
};

struct Sample {
  float m;   // radius multiplier (irregular silhouette)
  float j;   // brightness jitter, 0.84..1.0
};

inline uint32_t hash32(uint32_t value) {
  value ^= value >> 16;
  value *= 0x7feb352du;
  value ^= value >> 15;
  value *= 0x846ca68bu;
  value ^= value >> 16;
  return value;
}

// renderer.py::__init__ lambda `rnd`
inline float rnd(uint32_t h, int i) {
  const uint32_t mixed = (h >> (i * 3)) ^ uint32_t(i) * 1103515245u;
  return float(mixed & 0xFFFFu) / 65535.0f;
}

// renderer.py::_fx_ring
inline std::vector<Sample> fxRing(uint32_t seed, float phase, int lobes, float wobble, int n) {
  std::vector<Sample> out;
  out.reserve(size_t(n));
  constexpr float kTau = 6.28318f;
  for (int i = 0; i < n; ++i) {
    const float a = float(i) / float(n) * kTau;
    float m = 1.0f;
    for (int k = 0; k < lobes; ++k) {
      const float ph = float((seed >> (k * 5)) & 0xFFu) / 255.0f * kTau;
      m += (wobble / float(k + 1)) *
           std::sin(float(k + 2) * a + ph + phase * (0.6f + 0.35f * float(k)));
    }
    float j = 1.0f;
    for (int k = 0; k < 3; ++k) {
      const float ph = float(((seed + 13u) >> (k * 5)) & 0xFFu) / 255.0f * kTau;
      j += (0.5f / float(k + 1)) *
           std::sin(float(k + 2) * (a * 1.7f + 0.9f) + ph +
                    phase * 1.69f * (0.6f + 0.35f * float(k)));
    }
    out.push_back({std::max(0.22f, m), 0.84f + 0.16f * std::sqrt(std::max(0.22f, j))});
  }
  return out;
}

// renderer.py::_fx_ramp - white-hot -> yellow -> orange -> red
inline std::array<float, 3> fxRamp(float age) {
  static const float stops[5][4] = {{0.00f, 1.00f, 0.97f, 0.88f},
                                    {0.16f, 1.00f, 0.88f, 0.52f},
                                    {0.40f, 1.00f, 0.55f, 0.16f},
                                    {0.70f, 0.86f, 0.26f, 0.07f},
                                    {1.00f, 0.44f, 0.10f, 0.04f}};
  const float a = std::max(0.0f, std::min(1.0f, age));
  for (int i = 0; i < 4; ++i) {
    const float t0 = stops[i][0], t1 = stops[i + 1][0];
    if (a <= t1) {
      const float f = (t1 <= t0) ? 0.0f : (a - t0) / (t1 - t0);
      return {stops[i][1] + (stops[i + 1][1] - stops[i][1]) * f,
              stops[i][2] + (stops[i + 1][2] - stops[i][2]) * f,
              stops[i][3] + (stops[i + 1][3] - stops[i][3]) * f};
    }
  }
  return {stops[4][1], stops[4][2], stops[4][3]};
}

class Emitter {
 public:
  Emitter(std::vector<Vertex>& additive, std::vector<Vertex>& alpha,
          const float right[3], const float up[3])
      : additive_(additive), alpha_(alpha), right_(right), up_(up) {}

  int calls = 0;
  double alphaSum = 0.0;
  double vertexAlphaSum = 0.0;

  // renderer.py::_draw_glow_ring - one quad strip per band, two vertices per angle.
  void glowRing(const float pos[3], float radius, const std::array<float, 3>& colour, float alpha,
                const std::vector<Sample>& ring, int rot = 0, bool blendAdditive = true,
                float inner = 0.0f, int bands = 1) {
    if (radius <= 0.f || alpha <= 0.f || ring.empty())
      return;
    ++calls;
    alphaSum += alpha;
    std::vector<Vertex>& out = blendAdditive ? additive_ : alpha_;
    const int n = int(ring.size());
    const int count = std::max(1, bands);
    constexpr float kTau = 6.28318f;
    auto at = [&](int i) { return ring[size_t(((i + rot) % n + n) % n)]; };
    if (inner <= 0.f && count == 1) {
      // Plain blob: a single shared centre vertex carries no jitter, so neighbouring wedges
      // cannot disagree at the middle and the puff does not render as a pinwheel.
      for (int i = 0; i < n; ++i) {
        const Sample s0 = at(i), s1 = at(i + 1);
        const float a0 = float(i) / float(n) * kTau;
        const float a1 = float(i + 1) / float(n) * kTau;
        push(out, pos[0], pos[1], pos[2], colour, std::min(1.f, alpha));
        pushRing(out, pos, a0, radius * s0.m, colour, s0.j, 0.f);
        pushRing(out, pos, a1, radius * s1.m, colour, s1.j, 0.f);
      }
      return;
    }
    const float r0 = inner > 0.f ? radius * inner : 0.f;
    for (int k = 0; k < count; ++k) {
      const float fa = float(k) / float(count);
      const float fb = float(k + 1) / float(count);
      auto bandAlpha = [&](float f) {
        if (inner > 0.f)
          return alpha * std::pow(4.0f * f * (1.0f - f), 0.8f);
        return alpha * std::pow(1.0f - f, 1.4f);
      };
      // Triangle LIST, not a strip: a strip draws one quad per segment, but the band's inner and
      // outer vertices are separate runs, so a strip pairs outer(i) with inner(i+1) and the whole
      // shell renders as radial spokes. Two explicit triangles per segment.
      for (int i = 0; i < n; ++i) {
        const Sample s0 = at(i), s1 = at(i + 1);
        const float a0 = float(i) / float(n) * kTau;
        const float a1 = float(i + 1) / float(n) * kTau;
        const float r0i = r0 + (radius * s0.m - r0) * fa;
        const float r1i = r0 + (radius * s1.m - r0) * fa;
        const float r0o = r0 + (radius * s0.m - r0) * fb;
        const float r1o = r0 + (radius * s1.m - r0) * fb;
        const float alphaIn = std::min(1.f, bandAlpha(fa));
        const float alphaOut = std::min(1.f, bandAlpha(fb));
        Vertex in0{}, in1{}, out0{}, out1{};
        ringVertex(in0, pos, a0, r0i, colour, s0.j, alphaIn);
        ringVertex(in1, pos, a1, r1i, colour, s1.j, alphaIn);
        ringVertex(out0, pos, a0, r0o, colour, s0.j, alphaOut);
        ringVertex(out1, pos, a1, r1o, colour, s1.j, alphaOut);
        out.push_back(in0);
        out.push_back(in1);
        out.push_back(out0);
        out.push_back(out0);
        out.push_back(in1);
        out.push_back(out1);
      }
    }
  }

  // renderer.py::_draw_shock_shell - two strips, faint inside, bright mid, near-zero outer edge.
  void shockShell(const float pos[3], float radius, const std::array<float, 3>& colour, float alpha,
                  float thickness, const std::vector<Sample>& ring, int rot = 0) {
    if (radius <= 0.f || alpha <= 0.f || ring.empty())
      return;
    const int n = int(ring.size());
    constexpr float kTau = 6.28318f;
    auto at = [&](int i) { return ring[size_t(((i + rot) % n + n) % n)]; };
    for (int pass = 0; pass < 2; ++pass) {
      const float f0 = pass == 0 ? 0.f : 1.f;
      const float f1 = pass == 0 ? 1.f : 2.f;
      const float a0s = pass == 0 ? 0.13f : 0.55f;
      const float a1s = pass == 0 ? 0.55f : 0.10f;
      for (int i = 0; i < n; ++i) {
        const Sample s0 = at(i), s1 = at(i + 1);
        const float ang0 = float(i) / float(n) * kTau;
        const float ang1 = float(i + 1) / float(n) * kTau;
        Vertex in0{}, in1{}, out0{}, out1{};
        shockVertex(in0, pos, ang0, radius, thickness, s0.m, f0, colour, alpha * a0s);
        shockVertex(in1, pos, ang1, radius, thickness, s1.m, f0, colour, alpha * a0s);
        shockVertex(out0, pos, ang0, radius, thickness, s0.m, f1, colour, alpha * a1s);
        shockVertex(out1, pos, ang1, radius, thickness, s1.m, f1, colour, alpha * a1s);
        additive_.push_back(in0);
        additive_.push_back(in1);
        additive_.push_back(out0);
        additive_.push_back(out0);
        additive_.push_back(in1);
        additive_.push_back(out1);
      }
    }
  }

  // renderer.py::_fx_streak - a camera-facing quad along the debris direction.
  void streak(const float pos[3], const float direction[3], float length, float width,
              const std::array<float, 3>& colour, float alpha, const float eye[3]) {
    float d[3] = {direction[0], direction[1], direction[2]};
    const float dlen = std::sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
    if (dlen < 1e-9f)
      return;
    for (float& value : d)
      value /= dlen;
    const float view[3] = {pos[0] - eye[0], pos[1] - eye[1], pos[2] - eye[2]};
    float px = d[1] * view[2] - d[2] * view[1];
    float py = d[2] * view[0] - d[0] * view[2];
    float pz = d[0] * view[1] - d[1] * view[0];
    const float plen = std::sqrt(px * px + py * py + pz * pz);
    if (plen < 1e-6f)
      return;
    const float hw = width * 0.5f;
    px = px / plen * hw;
    py = py / plen * hw;
    pz = pz / plen * hw;
    const float a[3] = {pos[0] - d[0] * length * 0.5f, pos[1] - d[1] * length * 0.5f,
                        pos[2] - d[2] * length * 0.5f};
    const float b[3] = {pos[0] + d[0] * length * 0.5f, pos[1] + d[1] * length * 0.5f,
                        pos[2] + d[2] * length * 0.5f};
    push(additive_, a[0] - px, a[1] - py, a[2] - pz, colour, alpha);
    push(additive_, b[0] - px, b[1] - py, b[2] - pz, colour, alpha);
    push(additive_, b[0] + px, b[1] + py, b[2] + pz, colour, alpha);
    push(additive_, a[0] - px, a[1] - py, a[2] - pz, colour, alpha);
    push(additive_, b[0] + px, b[1] + py, b[2] + pz, colour, alpha);
    push(additive_, a[0] + px, a[1] + py, a[2] + pz, colour, alpha);
  }

 private:
  static void push(std::vector<Vertex>& out, float x, float y, float z,
                   const std::array<float, 3>& colour, float alpha) {
    out.push_back({x, y, z, colour[0], colour[1], colour[2], alpha});
  }

  void ringVertex(Vertex& out, const float pos[3], float angle, float radius,
                  const std::array<float, 3>& colour, float jitter, float alpha) const {
    const float ca = std::cos(angle), sa = std::sin(angle);
    const float ix = right_[0] * ca + up_[0] * sa;
    const float iy = right_[1] * ca + up_[1] * sa;
    const float iz = right_[2] * ca + up_[2] * sa;
    out = {pos[0] + ix * radius, pos[1] + iy * radius, pos[2] + iz * radius,
           colour[0] * jitter, colour[1] * jitter, colour[2] * jitter, alpha};
  }

  void pushRing(std::vector<Vertex>& out, const float pos[3], float angle, float radius,
                const std::array<float, 3>& colour, float jitter, float alpha) const {
    Vertex v{};
    ringVertex(v, pos, angle, radius, colour, jitter, alpha);
    out.push_back(v);
  }

  void shockVertex(Vertex& out, const float pos[3], float angle, float radius, float thickness,
                   float m, float step, const std::array<float, 3>& colour, float alpha) const {
    const float rm = radius * m;
    const float inner = rm - thickness * m;
    const float mid = inner + (rm - inner) * 0.55f;
    float r = mid;
    if (step == 0.f)
      r = inner;
    else if (step == 2.f)
      r = rm + thickness * 0.85f * m;
    const float ca = std::cos(angle), sa = std::sin(angle);
    out = {pos[0] + (right_[0] * ca + up_[0] * sa) * r,
           pos[1] + (right_[1] * ca + up_[1] * sa) * r,
           pos[2] + (right_[2] * ca + up_[2] * sa) * r, colour[0], colour[1], colour[2], alpha};
  }

  std::vector<Vertex>& additive_;
  std::vector<Vertex>& alpha_;
  const float* right_;
  const float* up_;
};

// renderer.py::_draw_explosion
inline void appendExplosion(std::vector<Vertex>& additive, std::vector<Vertex>& alphaBlend,
                            const float pos[3],  float size, float t, uint32_t seed,
                            const float right[3], const float up[3], const float eye[3],
                            std::vector<double>* counters = nullptr) {
  const float life = 1.5f;
  const float age = t / life;
  if (age >= 1.f || age < 0.f)
    return;
  constexpr float kTau = 6.28318f;
  const float r = std::max(16.f, size);
  const uint32_t h = (seed * 2654435761u) & 0xFFFFFFFFu;
  const float spin = age * 3.4f;
  Emitter emit(additive, alphaBlend, right, up);
  // Returned by value: at -O3 a write-through-array-pointer helper here was optimised into a
  // zero centre (measured: every fireball shell landed at the world origin at radius 16 while the
  // same code at -O1 was correct). Returning the value removes the aliasing question entirely.
  auto posAt = [](const float base[3], float dx, float dy, float dz) {
    return std::array<float, 3>{base[0] + dx, base[1] + dy, base[2] + dz};
  };
  auto colour3 = [](float cr, float cg, float cb) { return std::array<float, 3>{cr, cg, cb}; };

  // 1. flash - a lumpy ring, not a blob, so there is no saturated solid core.
  if (age < 0.14f) {
    const float fa = 1.f - age / 0.14f;
    emit.glowRing(pos, r * (1.1f + 2.0f * age), colour3(1.f, 1.f, 0.96f), fa * 0.40f,
                  fxRing(seed + 900u, spin, 4, 0.40f, 26), 2, true, 0.40f, 3);
  }

  // 2. fireball - seven lumpy shells that disagree on shape via `rot`.
  const std::array<float, 3> cool = fxRamp(age / 0.85f);
  const float fade = std::pow(std::max(0.f, 1.f - age), 1.25f);
  const float grow = r * (0.90f + 2.10f * std::sqrt(age));
  const std::vector<Sample> ringBig = fxRing(seed, spin, 5, 0.34f, 34);
  // clang 16 at -O3 miscompiles these fixed-count loops once they are fully unrolled: every
  // fireball shell came out at the world origin with a sixteenth of its radius, while -O2, -O0 and
  // -fno-unroll-loops were all correct. Keeping the loops rolled is the workaround; the check in
  // render_cpp/tests/test_explosion.cpp ("no vertex escapes the blast") fails loudly if this ever
  // regresses, because it runs at the project's own -O3 settings.
#pragma clang loop unroll(disable)
  for (int i = 0; i < 7; ++i) {
    const float ang = (float(i) / 7.f) * kTau + rnd(h, i) * 1.3f + spin * 0.5f;
    const float off = r * (0.20f + 0.30f * rnd(h, 10 + i)) * (0.4f + age);
    // Spelled out rather than through a helper: at -O3 clang folded the helper's result into a
    // zero centre here (-O2 and -O0 were correct), so every fireball shell drew at the world
    // origin at a sixteenth of its radius. The regression shows up as `test_explosion`'s "no
    // vertex escapes the blast" failing at the project's own -O3 settings.
    const float cx = pos[0] + std::cos(ang) * off;
    const float cy = pos[1] + (rnd(h, 30 + i) - 0.5f) * off;
    const float cz = pos[2] + std::sin(ang) * off;
    const float centre[3] = {cx, cy, cz};
    const float shell = grow * (0.55f + 0.42f * rnd(h, 20 + i));
    emit.glowRing(centre, shell, cool, 0.16f * fade, ringBig, i * 7, true, 0.f, 1);
  }
  if (age < 0.75f) {
    const float hot = std::max(0.f, 1.f - age / 0.75f);
    emit.glowRing(pos, r * (0.50f + 1.30f * std::pow(age, 0.6f)),
                  colour3(1.f, 0.70f + 0.28f * hot, 0.28f + 0.35f * hot),
                  0.34f * std::pow(hot, 1.1f), fxRing(seed + 77u, -spin * 0.8f, 4, 0.26f, 26), 3,
                  true, 0.f, 1);
  }
  if (age < 0.30f) {
    const float hc = 1.f - age / 0.30f;
    emit.glowRing(pos, r * (0.35f + 0.75f * hc), colour3(1.f, 0.98f, 0.92f), 0.34f * hc,
                  fxRing(seed + 99u, spin * 1.4f, 3, 0.18f, 18), 1, true, 0.f, 1);
  }

  // 3. shock front - thin, faint, short-lived; a crisp ring here is a drawn donut.
  if (age < 0.34f) {
    const float sa = age / 0.34f;
    emit.shockShell(pos, r * (1.10f + 1.30f * std::pow(sa, 0.62f)),
                    colour3(1.f, 0.88f, 0.70f), std::pow(1.f - sa, 2.2f) * 0.20f, r * 0.22f,
                    fxRing(seed + 5u, sa * 2.2f, 4, 0.34f, 40), 0);
  }

  // 4. smoke - many faint overlapping puffs, sqrt-spread over the disc, alpha blended.
  if (age > 0.08f) {
    const float sm = std::min(1.f, (age - 0.08f) / 0.35f);
    const float sfade = std::max(0.f, 1.f - std::max(0.f, (age - 0.40f) / 0.60f));
    const std::array<float, 3> smoke = colour3(cool[0] * 0.10f, cool[1] * 0.10f, cool[2] * 0.10f);
    const std::vector<Sample> ringSm = fxRing(seed + 40u, age * 1.6f, 4, 0.18f, 28);
#pragma clang loop unroll(disable)
    for (int k = 0; k < 9; ++k) {
      const float ang = (float(k) / 9.f) * kTau + rnd(h, k) * 1.4f;
      const float spread = std::sqrt(0.05f + 0.95f * rnd(h, 10 + k));
      const float drift = r * (0.9f + 2.8f * age) * spread;
      const std::array<float, 3> centre =
          posAt(pos, std::cos(ang) * drift * 0.9f, r * 0.45f * age + drift * 0.25f,
                std::sin(ang) * drift * 0.9f);
      emit.glowRing(centre.data(), r * (0.95f + 2.1f * age) * (0.70f + 0.60f * rnd(h, 20 + k)),
                    smoke, 0.13f * sm * sfade, ringSm, k * 3, false, 0.f, 1);
    }
  }

  // 5. embers and debris on ballistic arcs
  if (age < 0.95f) {
    const float ea = std::max(0.f, 1.f - age / 0.95f);
    const int n = 18;
    const std::vector<Sample> ringDeb = fxRing(seed + 200u, spin * 2.0f, 3, 0.45f, 12);
    const std::array<float, 3> ember = fxRamp(std::min(1.f, age * 1.5f + 0.25f));
#pragma clang loop unroll(disable)
    for (int i = 0; i < n; ++i) {
      const float ang = (float(i) / float(n)) * kTau + rnd(h, i) * 0.9f;
      const float elev = (rnd(h, 60 + i) - 0.5f) * 1.1f;
      const float sp = r * (1.1f + 4.2f * age) * (0.55f + 0.9f * rnd(h, 40 + i));
      const float vel[3] = {std::cos(ang) * std::cos(elev), std::sin(elev),
                            std::sin(ang) * std::cos(elev)};
      const std::array<float, 3> p = posAt(pos, vel[0] * sp, vel[1] * sp, vel[2] * sp);
      const bool big = (i % 4) == 0;
      emit.glowRing(p.data(), (4.f + 7.f * rnd(h, 80 + i)) * (0.4f + ea) * (big ? 1.8f : 1.0f),
                    ember, 0.80f * ea, ringDeb, i, true, 0.f, 1);
      if ((big || i % 3 == 0) && ea > 0.30f && sp > r * 1.4f) {
        const std::array<float, 3> head = {p[0] + vel[0] * r * 0.30f, p[1] + vel[1] * r * 0.30f,
                                           p[2] + vel[2] * r * 0.30f};
        emit.streak(head.data(), vel, r * 0.65f * (0.5f + ea), 2.2f, ember, 0.40f * ea, eye);
      }
    }
  }

  if (counters) {
    counters->assign(6, 0.0);
    (*counters)[0] = double(emit.calls);
    (*counters)[1] = emit.alphaSum;
    (*counters)[2] = double(additive.size());
    (*counters)[3] = double(alphaBlend.size());
    (*counters)[4] = double(r);
    (*counters)[5] = double(age);
  }

  // 6. secondaries - staggered pops inside the fireball
#pragma clang loop unroll(disable)
  for (int k = 0; k < 3; ++k) {
    const float t0 = 0.14f + 0.13f * float(k) + 0.10f * rnd(h, k);
    const float sub = age - t0;
    if (sub >= 0.f && sub < 0.24f) {
      const float frac = sub / 0.24f;
      const float ang = rnd(h, 70 + k) * kTau;
      const float off = r * 0.75f * (0.4f + rnd(h, 90 + k));
      const std::array<float, 3> centre =
          posAt(pos, std::cos(ang) * off, (rnd(h, 100 + k) - 0.5f) * off * 0.6f,
                std::sin(ang) * off);
      emit.glowRing(centre.data(), r * (0.35f + 0.80f * frac), fxRamp(frac),
                    0.85f * (1.f - frac),
                    fxRing(seed + 300u + uint32_t(k), frac * 3.0f, 4, 0.38f, 22), k * 5, true,
                    0.f, 1);
    }
  }
}

}  // namespace fx
}  // namespace armada
