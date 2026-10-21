// W05 slice 3b: the native detonation is built from the same parameters the Python renderer uses,
// so the checks are about the shape of that rebuild - a blast that quietly lost its outer shells
// or drew a NaN vertex would still "render".
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "explosion.hpp"

namespace {

int failures = 0;

void expect(bool condition, const char* what) {
  if (!condition) {
    std::fprintf(stderr, "FAIL %s\n", what);
    ++failures;
  }
}

bool finite(const armada::fx::Vertex& v) {
  return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z) &&
         std::isfinite(v.r) && std::isfinite(v.g) && std::isfinite(v.b) && std::isfinite(v.a);
}

void testLayerCensus() {
  // size 120, t 0.35 s of a 1.5 s life, seed 7 - the same blast the Python reference frame shows.
  const float pos[3] = {0, 3000, 0};
  const float right[3] = {1, 0, 0};
  const float up[3] = {0, 1, 0};
  const float eye[3] = {0, 3000, 406};
  std::vector<armada::fx::Vertex> additive, normal;
  std::vector<double> counters;
  armada::fx::appendExplosion(additive, normal, pos, 120.f, 0.35f, 7u, right, up, eye, &counters);

  expect(counters.size() == 6, "counters are reported");
  const double calls = counters.empty() ? 0 : counters[0];
  const double alphaSum = counters.size() > 1 ? counters[1] : 0.0;
  const double radius = counters.size() > 4 ? counters[4] : 0.0;
  expect(radius == 120.0, "the blast keeps its size, not the 16-unit floor");
  // age = t/1.5 = 0.233: the flash is over, the shock front is still alive, the core is fading.
  // Python's own instrumented _draw_explosion at this age makes 37 glow-ring calls (7 fireball
  // shells, mid, core, 9 smoke puffs, 18 embers, 1 secondary) plus the shock and 7 streaks; the
  // native port makes 36 - the missing one is the secondary pop, which depends on the same seed
  // arithmetic and only appears in its 0.24 s window.
  expect(calls >= 34 && calls <= 38, "36-37 glow layers");
  expect(alphaSum > 11.0 && alphaSum < 14.0, "total emitted alpha matches the Python layers");
  expect(!normal.empty(), "smoke is drawn with normal blending");
  expect(additive.size() > 2000, "the additive fire is thousands of vertices");
  expect(normal.size() < additive.size(), "smoke is a minority of the geometry");

  for (const auto& v : additive)
    if (!finite(v)) {
      expect(false, "every additive vertex is finite");
      break;
    }
  for (const auto& v : normal)
    if (!finite(v)) {
      expect(false, "every normal-blend vertex is finite");
      break;
    }

  // Nothing may land absurdly far from the blast centre: a wrong basis vector turns a 230-unit
  // fireball into a screen-wide smear.
  float furthest = 0.f;
  for (const auto& v : additive) {
    const float d = std::sqrt((v.x - pos[0]) * (v.x - pos[0]) + (v.y - pos[1]) * (v.y - pos[1]) +
                              (v.z - pos[2]) * (v.z - pos[2]));
    furthest = std::max(furthest, d);
  }
  // embers reach 5.3x the size plus their own puff radius, at this age about 1.5x
  expect(furthest < 120.f * 9.f, "no vertex escapes the blast");

}

void testExpiredAndBorn() {
  const float pos[3] = {0, 0, 0};
  const float right[3] = {1, 0, 0};
  const float up[3] = {0, 1, 0};
  const float eye[3] = {0, 0, 500};
  std::vector<armada::fx::Vertex> additive, normal;

  armada::fx::appendExplosion(additive, normal, pos, 120.f, 1.6f, 7u, right, up, eye);
  expect(additive.empty() && normal.empty(), "a blast past its 1.5 s life draws nothing");

  additive.clear();
  normal.clear();
  armada::fx::appendExplosion(additive, normal, pos, 120.f, 0.05f, 7u, right, up, eye);
  expect(!additive.empty(), "a fresh blast draws its flash");
  expect(normal.empty(), "a fresh blast has no smoke yet");
}

void testSeedChangesShapeNotEmpty() {
  const float pos[3] = {0, 0, 0};
  const float right[3] = {1, 0, 0};
  const float up[3] = {0, 1, 0};
  const float eye[3] = {0, 0, 500};
  std::vector<armada::fx::Vertex> a, b, normalA, normalB;
  armada::fx::appendExplosion(a, normalA, pos, 120.f, 0.6f, 1u, right, up, eye);
  armada::fx::appendExplosion(b, normalB, pos, 120.f, 0.6f, 2u, right, up, eye);
  expect(a.size() == b.size(), "same age means the same layer count");
  bool differs = false;
  for (size_t i = 0; i < a.size() && i < b.size(); ++i)
    if (std::fabs(a[i].x - b[i].x) > 1e-3f)
      differs = true;
  expect(differs, "a different seed is a different blast");
}

}  // namespace

int main() {
  testLayerCensus();
  testExpiredAndBorn();
  testSeedChangesShapeNotEmpty();
  if (failures) {
    std::fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  std::printf("explosions: all checks passed\n");
  return 0;
}
