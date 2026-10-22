// GPU-free: compile with -std=c++17 -O3 -DNDEBUG -Irender_cpp/include.
#include "starfield.hpp"
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <iostream>
#include <vector>

namespace {
int failures = 0;
void check(bool ok, const char* message) {
    if (!ok) { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}
void testGeometry() {
    using namespace armada::sky;
    const auto mesh = buildStarfield();
    const auto again = buildStarfield();
    check(mesh.size() == 1400 * 6, "exactly 1400 stars, six triangle-list vertices each");
    check(mesh.size() == again.size() && !mesh.empty() &&
          std::memcmp(mesh.data(), again.data(), mesh.size() * sizeof(StarVertex)) == 0,
          "default geometry is byte-deterministic, including padding");
    check(sizeof(StarVertex) == 28 && offsetof(StarVertex, rgba) == 20 &&
          offsetof(StarVertex, radiusPx) == 24, "documented 28-byte GPU layout");
    if (mesh.size() != 1400 * 6) return;
    bool sphere = true, bounded = true, quads = true, winding = true;
    int large = 0, dim = 0, north = 0;
    double alphaSum = 0, ySum = 0;
    float minRadius = 10, maxRadius = 0;
    int minAlpha = 255, maxAlpha = 0;
    const float uv[6][2] = {{-1,-1},{1,-1},{1,1},{-1,-1},{1,1},{-1,1}};
    for (std::size_t i = 0; i < mesh.size(); i += 6) {
        const auto& a = mesh[i];
        const double length = std::sqrt(double(a.x)*a.x + double(a.y)*a.y + double(a.z)*a.z);
        sphere &= std::isfinite(length) && std::abs(length - 1.0) < 2e-6;
        bounded &= std::isfinite(a.radiusPx) && a.radiusPx >= 0.5f && a.radiusPx <= 1.6f;
        large += a.radiusPx > 1.4f;
        dim += a.rgba[3] <= 76;
        north += a.y > 0;
        ySum += a.y;
        alphaSum += a.rgba[3] / 255.0;
        minRadius = std::min(minRadius, a.radiusPx); maxRadius = std::max(maxRadius, a.radiusPx);
        minAlpha = std::min(minAlpha, int(a.rgba[3])); maxAlpha = std::max(maxAlpha, int(a.rgba[3]));
        bounded &= a.rgba[3] >= 25 && a.rgba[3] <= 179;
        bounded &= a.rgba[0] >= 150 && a.rgba[1] >= 150 && a.rgba[2] >= 150;
        for (int j = 0; j < 6; ++j) {
            const auto& b = mesh[i+j];
            quads &= a.x == b.x && a.y == b.y && a.z == b.z &&
                     a.radiusPx == b.radiusPx && std::memcmp(a.rgba,b.rgba,4) == 0;
            winding &= b.u == uv[j][0] && b.v == uv[j][1];
        }
    }
    check(sphere, "finite unit directions, not translated world-space billboards");
    check(quads && winding, "each star shares one direction/radius/color and two consistent UV triangles");
    check(bounded, "finite 0.5..1.6 pixel radii, restrained alpha and near-neutral RGB");
    check(large > 0 && large <= 28, "at most two percent of stars exceed the usual 1.4 px radius");
    check(dim > 980 && alphaSum/1400 < 0.30, "most stars are dim and mean alpha is restrained");
    check(maxRadius-minRadius > 0.8f && maxAlpha-minAlpha > 70, "radius and brightness actually vary");
    check(north > 600 && north < 800 && std::abs(ySum/1400) < 0.06, "directions cover both sphere hemispheres");
}
void testProjection() {
    using namespace armada::sky;
    float view[16] = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
    float proj[16] = {2,0,0,0, 0,3,0,0, 0,0,-1,-1, 0,0,-2,0};
    StarVertex center{};
    center.z = -1; center.radiusPx = 1.25f;
    const auto c = projectStarVertex(center, view, proj, 1280, 800);
    check(c.x == 0 && c.y == 0 && c.z == c.w && c.w > 0,
          "perspective-projected front direction is at clip far plane");
    view[12] = 1000000; view[13] = -200000; view[14] = 80000;
    const auto translated = projectStarVertex(center, view, proj, 1280, 800);
    check(c.x == translated.x && c.y == translated.y && c.z == translated.z && c.w == translated.w,
          "camera translation causes exactly zero parallax");
    StarVertex corner = center; corner.u = 1; corner.v = -1;
    for (const auto& viewport : {std::pair<float,float>{1280,800}, {2560,1600}, {640,400}}) {
        const auto a = projectStarVertex(center, view, proj, viewport.first, viewport.second);
        const auto b = projectStarVertex(corner, view, proj, viewport.first, viewport.second);
        check(std::abs((b.x/b.w-a.x/a.w)*viewport.first/2 - 1.25f) < 1e-5f &&
              std::abs((b.y/b.w-a.y/a.w)*viewport.second/2 + 1.25f) < 1e-5f,
              "quad offset stays pixel-sized independently of framebuffer size");
    }
    const float angle = 0.4f;
    view[5] = std::cos(angle); view[6] = std::sin(angle);
    view[9] = -std::sin(angle); view[10] = std::cos(angle);
    const auto inclined = projectStarVertex(center, view, proj, 1280, 800);
    check(std::abs(inclined.y/inclined.w - 3*std::tan(angle)) < 1e-6f,
          "full view rotation preserves camera inclination");
    check(inclined.z == inclined.w, "inclination never pulls stars into world depth");
    center.z = 1;
    const auto behind = projectStarVertex(center, view, proj, 1280, 800);
    check(behind.w < 0, "directions behind the eye remain behind for homogeneous clipping");
    proj[10] = 0.125f; proj[14] = 8;
    const auto otherDepth = projectStarVertex(corner, view, proj, 1280, 800);
    check(otherDepth.z == otherDepth.w, "far-depth override does not assume projection depth coefficients");
}
void testSoftDisc() {
    using namespace armada::sky;
    check(starDiscAlpha(0,0,0.4f) == 0.4f, "soft disc retains authored center alpha");
    check(starDiscAlpha(1,0,0.4f) == 0 && starDiscAlpha(1,1,0.4f) == 0 &&
          starDiscAlpha(-1,-1,0.4f) == 0, "quad edges and corners are transparent, never filled squares");
    check(std::abs(starDiscAlpha(0.5f,0,0.4f) - 0.225f) < 1e-6f,
          "disc uses smooth squared radial falloff rather than hard clipping");
    float previous = 1;
    bool monotonic = true, radial = true;
    for (int i=0; i<=100; ++i) {
        const float r = float(i)/100;
        const float alpha = starDiscAlpha(r,0,0.4f);
        monotonic &= std::isfinite(alpha) && alpha >= 0 && alpha <= previous;
        radial &= std::abs(alpha-starDiscAlpha(0,-r,0.4f)) < 1e-6f;
        previous = alpha;
    }
    check(monotonic && radial, "falloff is finite, radial, nonnegative and monotonic");
    check(starDiscAlpha(0.2f,0.3f,0) == 0, "zero alpha contributes no additive light");
}
}
int main() {
    testGeometry();
    testProjection();
    testSoftDisc();
    if (!failures) std::cout << "starfield: all checks passed\n";
    return failures ? 1 : 0;
}
