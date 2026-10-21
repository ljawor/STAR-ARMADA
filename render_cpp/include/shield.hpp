// W05 slice 5: the standing shield shell, ported from renderer.py::_shield_shell_list.
//
// The Python shell is a lat/lon hemisphere whose per-vertex alpha bakes the rim falloff ("Fresnel at
// the silhouette"), built VIEW-ALIGNED so the grazing angle is a pure function of latitude. That is
// why Python can cache one display list per strength octant for the whole game: in view space the
// geometry is identical for every shell at every heading.
//
// This file takes the same observation one step further. Rather than rebuilding 2,400 vertices per
// shielded unit per frame on the CPU (622 bubbles at battle scale is ~1.5M vertices, more than a
// transient vertex buffer holds, and it measured as 155 chunked submits per frame), the mesh is
// built ONCE per detail level in view space and drawn instanced: one instance record per shell
// carries its view-space centre, radius, tint and fade. The baked latitude terms - the white limb
// and the alpha ramp - live in the mesh exactly as Python bakes them into its display list.
//
// What is Python's: whether the unit has a shield, how strong it is (the hue and the fade alpha),
// and where it is in the world. What is this window's: the detail level (from apparent size, like
// Python's own <20 / <40 px thresholds) and the readability floor, both of which need the camera.
#pragma once

#include <cmath>
#include <cstddef>
#include <vector>

namespace armada {
namespace fx {

constexpr double kShieldBaseAlpha = 0.001;   // the soft wash inside the bubble
constexpr double kShieldRimAlpha = 0.18;     // the term that dominates at the silhouette
constexpr double kShieldRimWhite = 0.18;     // capped whitening: the limb keeps its hue
constexpr int kShieldLow[2] = {20, 5};       // lons, lats per detail level (renderer.py)
constexpr int kShieldMedium[2] = {30, 8};
constexpr int kShieldHigh[2] = {40, 10};

// One mesh vertex, in view space: the unit hemisphere sits at the origin with +Z toward the eye.
// `whiten` and `alpha` are the baked latitude terms, before the instance's tint and fade.
struct ShellVertex {
  float x, y, z;
  float whiten;   // how far this latitude is pulled toward white
  float alpha;    // the rim falloff, at full strength
};

// One instanced shell: where its centre is in view space, how big it is, what colour and fade.
struct ShellInstance {
  float centre[3];
  float radius;
  float tint[3];
  float fade;
};

// Build the camera-facing hemisphere for one detail level. Two triangles per lat/lon cell; only the
// near half is emitted because the shell is additive and its rim lands on the shared silhouette, so
// the far half would add identical pixels at twice the vertex cost.
inline void buildShellMesh(std::vector<ShellVertex>& out, int lons, int lats) {
  out.clear();
  out.reserve(size_t(lons) * size_t(lats) * 6);
  const double pi = 3.14159265358979323846;
  for (int i = 0; i < lons; ++i) {
    const double lon0 = 2.0 * pi * i / lons;
    const double lon1 = 2.0 * pi * (i + 1) / lons;
    for (int j = 0; j < lats; ++j) {
      const double lat0 = pi * 0.5 * j / lats;
      const double lat1 = pi * 0.5 * (j + 1) / lats;
      const double la[4] = {lat0, lat1, lat1, lat0};
      const double lo[4] = {lon0, lon0, lon1, lon1};
      ShellVertex quad[4];
      for (int k = 0; k < 4; ++k) {
        const double sl = std::sin(la[k]), cl = std::cos(la[k]);
        const double sn = std::sin(lo[k]), cn = std::cos(lo[k]);
        const double graze = 1.0 - std::abs(cl);
        quad[k].x = float(sl * sn);
        quad[k].y = float(sl * cn);
        quad[k].z = float(cl);
        quad[k].whiten = float(kShieldRimWhite * graze * graze * graze);
        quad[k].alpha = float(std::fmin(1.0, kShieldBaseAlpha + kShieldRimAlpha * graze * graze));
      }
      out.push_back(quad[0]);
      out.push_back(quad[1]);
      out.push_back(quad[2]);
      out.push_back(quad[0]);
      out.push_back(quad[2]);
      out.push_back(quad[3]);
    }
  }
}

// The renderer picks a coarser shell for small on-screen bubbles: the rim still reads at the same
// silhouette and the player gets the same strength cue. `apparentPx` is the bubble's diameter on
// screen at this camera.
inline int shieldDetail(double apparentPx) {
  if (apparentPx < 20.0)
    return 0;                                 // low
  if (apparentPx < 40.0)
    return 1;                                 // medium
  return 2;                                   // high
}

// The world-space centre converted into view space, where the shell is drawn.
inline ShellInstance shellInstance(const double centreWorld[3], double radius, const double tint[3],
                                   double fade, const float view[16]) {
  ShellInstance shell{};
  shell.centre[0] = float(view[0] * centreWorld[0] + view[4] * centreWorld[1] +
                           view[8] * centreWorld[2] + view[12]);
  shell.centre[1] = float(view[1] * centreWorld[0] + view[5] * centreWorld[1] +
                           view[9] * centreWorld[2] + view[13]);
  shell.centre[2] = float(view[2] * centreWorld[0] + view[6] * centreWorld[1] +
                           view[10] * centreWorld[2] + view[14]);
  shell.radius = float(radius);
  shell.tint[0] = float(tint[0]);
  shell.tint[1] = float(tint[1]);
  shell.tint[2] = float(tint[2]);
  shell.fade = float(fade);
  return shell;
}

}  // namespace fx
}  // namespace armada
