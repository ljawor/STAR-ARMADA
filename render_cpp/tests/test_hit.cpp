// W05 slice 3c: the contact geometry and the seeded fragments must be identical on both sides.
//
// The hard assertion is the RNG: `random.Random(<int>)` in CPython seeds MT19937 through
// init_by_array, so a port has to match it draw for draw or every spark points somewhere else. The
// expected values below were printed by CPython itself, not by this file.
#include <cmath>
#include <cstdio>
#include <vector>

#include "../include/hit_effects.hpp"

namespace {

int failures = 0;

void check(bool ok, const char* what) {
  if (!ok) {
    std::printf("FAIL %s\n", what);
    ++failures;
  }
}

void near(double got, double want, double tolerance, const char* what) {
  if (!(std::fabs(got - want) <= tolerance)) {
    std::printf("FAIL %s: got %.17g want %.17g\n", what, got, want);
    ++failures;
  }
}

double length(const double v[3]) { return std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]); }

void testRandomMatchesCpython() {
  // python: random.Random(seed).random() x4
  struct Sample {
    uint32_t seed;
    double first[4];
  } samples[] = {
      {0, {0.8444218515250481, 0.7579544029403025, 0.4205715808308450, 0.25891675029296335}},
      {7, {0.32383276483316237, 0.15084917392450192, 0.6509344730398537, 0.07243628666754276}},
      {11, {0.4523795535098186, 0.5597723860804960, 0.9242105840237294, 0.4656500700997733}},
      {65535, {0.03704661600456849, 0.8443363850780575, 0.4404429847810353, 0.1254217405423902}},
  };
  for (const auto& sample : samples) {
    armada::fx::PyRandom rng(sample.seed);
    for (int i = 0; i < 4; ++i)
      near(rng.random(), sample.first[i], 1e-16, "PyRandom::random matches CPython");
  }
}

void testFragmentsMatchPython() {
  // python: hit_effects._fragments(seed) - first and last fragment, all four numbers.
  struct Sample {
    uint32_t seed;
    double first[4];
    double last[4];
  } samples[] = {
      {0, {5.305658970563565, 0.8184658022052269, 0.5654286856231338, 0.7589167502929633},
       {1.6367214572880235, 0.8537708702597667, 0.661524477876692, 0.514041700164019}},
      {7, {2.034701269983068, 0.36313688044337644, 0.7382008547798903, 0.5724362866675428},
       {3.441579979035226, 0.29709173122999233, 0.2947008774746745, 0.7059587128193265}},
      {11, {2.8423845638813536, 0.6698292895603719, 0.943157938017797, 0.9656500700997733},
       {3.1401673268685400, 0.7468371489177761, 0.5929974111996683, 0.7781628996638859}},
      {65535, {0.23277075336062883, 0.8832522888085431, 0.5803322385857764, 0.6254217405423902},
       {4.848939866306346, 0.3224610025889428, 0.5333575661598636, 1.283088749660767}},
  };
  for (const auto& sample : samples) {
    const auto fragments = armada::fx::hitFragments(sample.seed);
    const double got[8] = {fragments[0].angle, fragments[0].speed, fragments[0].lift,
                           fragments[0].jitter, fragments[8].angle, fragments[8].speed,
                           fragments[8].lift, fragments[8].jitter};
    for (int i = 0; i < 4; ++i)
      near(got[i], sample.first[i], 1e-9, "fragment[0] matches CPython");
    for (int i = 0; i < 4; ++i)
      near(got[4 + i], sample.last[i], 1e-9, "fragment[8] matches CPython");
  }
}

void testShieldCapSitsOnTheShell() {
  const double centre[3] = {1200.0, -300.0, 44.0};
  const double normal[3] = {0.0, 0.0, 1.0};
  const double right[3] = {1.0, 0.0, 0.0};
  const double up[3] = {0.0, 1.0, 0.0};
  std::vector<armada::fx::HitVertex> triangles, smoke;
  armada::fx::HitCounters counters;
  armada::fx::appendHit(true, centre, normal, 250.0, 12.0, 0.08, 7, false, 0.5, right, up,
                        triangles, smoke, &counters);
  check(counters.capTriangles == 12, "shield cap is 12 triangles");
  check(counters.rippleTriangles == 32, "two ripples of 16 segments");
  check(counters.smokeTriangles == 0, "shield contacts emit no smoke");
  // The cap and its ripples are surface markings: every one of their vertices sits on the sphere of
  // radius 250, including the fan centre, which is one radius out along the normal. Sparks fly off
  // the surface afterwards and are not part of the shell.
  const size_t shellVertices = (counters.capTriangles + counters.rippleTriangles) * 3;
  check(shellVertices == 132, "cap is 12 triangles, one ripple of 32 at 80 ms");
  size_t onShell = 0;
  for (size_t i = 0; i < shellVertices && i < triangles.size(); ++i) {
    const auto& vertex = triangles[i];
    const double offset[3] = {vertex.x - centre[0], vertex.y - centre[1], vertex.z - centre[2]};
    if (std::fabs(length(offset) - 250.0) < 1e-6)
      ++onShell;
  }
  check(onShell == shellVertices, "every cap and ripple vertex lies exactly on the shield sphere");
  // The contact point is the shell centre plus one radius along the normal.
  near(triangles[0].z, 44.0 + 250.0, 1e-6, "contact point is one radius along the normal");
}

void testHullFlashAndSmoke() {
  const double point[3] = {10.0, 20.0, 30.0};
  const double normal[3] = {1.0, 0.0, 0.0};
  const double right[3] = {0.0, 1.0, 0.0};
  const double up[3] = {0.0, 0.0, 1.0};
  std::vector<armada::fx::HitVertex> triangles, smoke;
  armada::fx::HitCounters counters;
  // 0.01s in: flash only.
  armada::fx::appendHit(false, point, normal, 6.0, 6.0, 0.01, 11, false, 0.05, right, up,
                        triangles, smoke, &counters);
  check(counters.sparkTriangles == 10 + 9 + 4, "flash fan plus spark ribbons and slivers");
  check(counters.smokeTriangles == 0, "no smoke before 25 ms");

  triangles.clear();
  smoke.clear();
  counters = armada::fx::HitCounters{};
  armada::fx::appendHit(false, point, normal, 6.0, 6.0, 0.30, 11, false, 0.05, right, up,
                        triangles, smoke, &counters);
  check(counters.smokeTriangles == 12, "smoke appears once the contact is 25 ms old");
  // Fade: the same contact late in its life is strictly dimmer at the flash centre.
  armada::fx::HitCounters early;
  std::vector<armada::fx::HitVertex> earlyTriangles, earlySmoke;
  armada::fx::appendHit(false, point, normal, 6.0, 6.0, 0.02, 11, false, 0.05, right, up,
                        earlyTriangles, earlySmoke, &early);
  check(earlyTriangles[0].a > triangles[0].a, "the flash fades with age");
}

void testDeadContactDrawsNothing() {
  const double point[3] = {0.0, 0.0, 0.0};
  const double normal[3] = {0.0, 1.0, 0.0};
  const double right[3] = {1.0, 0.0, 0.0};
  const double up[3] = {0.0, 0.0, 1.0};
  std::vector<armada::fx::HitVertex> triangles, smoke;
  armada::fx::HitCounters counters;
  armada::fx::appendHit(false, point, normal, 5.0, 5.0, 0.42, 3, false, 1.0, right, up, triangles,
                        smoke, &counters);
  check(triangles.empty() && smoke.empty(), "a contact at the end of its life emits nothing");
  armada::fx::appendHit(true, point, normal, 100.0, 5.0, 0.55, 3, false, 1.0, right, up, triangles,
                        smoke, &counters);
  check(triangles.empty(), "a shield contact at the end of its life emits nothing");
}

void testPixelFloorAndVisualContact() {
  const double point[3] = {0.0, 0.0, 0.0};
  const double normal[3] = {0.0, 0.0, 1.0};
  const double right[3] = {1.0, 0.0, 0.0};
  const double up[3] = {0.0, 1.0, 0.0};
  // ppw 0.2 -> the 7 px floor is 35 world units, far above the effect's own size of 6.
  auto extent = [&](bool visualContact) {
    std::vector<armada::fx::HitVertex> triangles, smoke;
    armada::fx::HitCounters counters;
    armada::fx::appendHit(false, point, normal, 6.0, 6.0, 0.05, 5, visualContact, 0.2, right, up,
                          triangles, smoke, &counters);
    double furthest = 0.0;
    for (const auto& vertex : triangles) {
      const double at[3] = {vertex.x, vertex.y, vertex.z};
      furthest = std::max(furthest, length(at));
    }
    return furthest;
  };
  const double floored = extent(false);
  const double own = extent(true);
  check(floored > 6.0, "the 7 px floor enlarges a distant contact");
  check(own <= 6.0 + 1e-9, "a visually resolved contact keeps its own size");
}

}  // namespace

int main() {
  testRandomMatchesCpython();
  testFragmentsMatchPython();
  testShieldCapSitsOnTheShell();
  testHullFlashAndSmoke();
  testDeadContactDrawsNothing();
  testPixelFloorAndVisualContact();
  if (failures == 0)
    std::printf("test_hit: all checks passed\n");
  return failures == 0 ? 0 : 1;
}
