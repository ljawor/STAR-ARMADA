// W05 slice 5: the shield shell.
//
// What is checked here is the part that would silently go wrong: the mesh must be a hemisphere
// facing the camera (not a full ball, which doubles the cost for pixels the ship hides), every
// vertex must sit on the unit sphere, the baked latitude terms must match the constants the Python
// renderer bakes into its display list, the detail thresholds must match Python's own <20 / <40 px
// rule, and the instance record must place a shell at the right view-space centre and radius.
#include "shield.hpp"

#include <cmath>
#include <iostream>
#include <string>
#include <vector>

namespace {

int failures = 0;

void check(bool condition, const std::string& what) {
  if (!condition) {
    std::cerr << "FAIL " << what << std::endl;
    ++failures;
  }
}

}  // namespace

int main() {
  using namespace armada::fx;

  for (int level = 0; level < 3; ++level) {
    const int* grid = level == 0 ? kShieldLow : (level == 1 ? kShieldMedium : kShieldHigh);
    std::vector<ShellVertex> mesh;
    buildShellMesh(mesh, grid[0], grid[1]);

    const std::string tag = level == 0 ? "low" : (level == 1 ? "medium" : "high");
    check(mesh.size() == size_t(grid[0]) * size_t(grid[1]) * 6,
          tag + ": two triangles per lat/lon cell");

    bool onSphere = true, facing = true, bounded = true, limbWhiter = true;
    double minAlpha = 1e9, maxAlpha = -1e9, poleWhiten = 0.0, limbWhiten = -1e9;
    for (const auto& v : mesh) {
      const double distance = std::sqrt(double(v.x) * v.x + double(v.y) * v.y +
                                        double(v.z) * v.z);
      if (std::abs(distance - 1.0) > 1e-6)
        onSphere = false;
      // +Z is the eye axis, so every emitted vertex is on the near hemisphere
      if (v.z < -1e-6f)
        facing = false;
      if (!(v.alpha >= 0.0f && v.alpha <= 1.0f && v.whiten >= 0.0f && v.whiten <= 1.0f))
        bounded = false;
      minAlpha = std::min<double>(minAlpha, v.alpha);
      maxAlpha = std::max<double>(maxAlpha, v.alpha);
      if (v.z > 0.999f)
        poleWhiten = v.whiten;
      limbWhiten = std::max<double>(limbWhiten, v.whiten);
    }
    check(onSphere, tag + ": every vertex sits on the unit sphere");
    check(facing, tag + ": only the camera-facing hemisphere is emitted");
    check(bounded, tag + ": baked terms stay in 0..1");
    // the pole is the interior wash, the silhouette carries the full rim term
    // the mesh stores floats, so compare at float precision
    check(std::abs(minAlpha - kShieldBaseAlpha) < 1e-6, tag + ": the interior alpha is the wash");
    check(std::abs(maxAlpha - (kShieldBaseAlpha + kShieldRimAlpha)) < 1e-6,
          tag + ": the silhouette alpha is the full rim term");
    check(poleWhiten == 0.0 && std::abs(limbWhiten - kShieldRimWhite) < 1e-6,
          tag + ": whitening is zero at the pole and capped at the limb");
    (void)limbWhiter;
  }

  // Detail thresholds are the renderer's own: <20 px low, <40 px medium, else high.
  check(shieldDetail(19.9) == 0 && shieldDetail(20.0) == 1 && shieldDetail(39.9) == 1 &&
            shieldDetail(40.0) == 2,
        "detail follows apparent size with Python's thresholds");

  // The instance record converts a world centre into view space. A camera looking down -Z from
  // +Z ten units back puts a world origin at view (0, 0, -10).
  const float view[16] = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, -10, 1};
  const double centre[3] = {0.0, 0.0, 0.0};
  const double tint[3] = {0.3, 0.55, 1.0};
  const ShellInstance shell = shellInstance(centre, 42.0, tint, 0.4, view);
  check(std::abs(shell.centre[0]) < 1e-6f && std::abs(shell.centre[1]) < 1e-6f &&
            std::abs(shell.centre[2] + 10.0f) < 1e-6f,
        "the instance centre is transformed into view space");
  check(shell.radius == 42.0f, "the instance carries the shell radius");
  check(std::abs(shell.tint[1] - 0.55f) < 1e-6f && std::abs(shell.fade - 0.4f) < 1e-6f,
        "the instance carries the tint and fade Python decided");

  if (failures == 0)
    std::cout << "shield shell: all checks passed" << std::endl;
  return failures == 0 ? 0 : 1;
}
