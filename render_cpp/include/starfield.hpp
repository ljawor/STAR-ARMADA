// Static direction-sphere stars; no bgfx, GPU, camera state or mutable global RNG.
#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <type_traits>
#include <vector>

namespace armada { namespace sky {
constexpr std::size_t kStarCount = 1400;
constexpr float kStarSphereRadius = 90000.0f;

// EXACT GPU layout (28 bytes, no padding; all Float attrs unnormalized):
//   offset  0: Position  3 Float  -> a_position.xyz, unit sky direction
//   offset 12: TexCoord0 2 Float  -> a_texcoord0.xy, quad corners -1..+1
//   offset 20: Color0    4 Uint8 normalized=true -> a_color0.rgba
//   offset 24: Color1    1 Float  -> a_color1.x, radius in framebuffer pixels
// These four attributes already exist in varying.def.sc. Do not normalize Color1.
// All six vertices of a star share direction/color/radius; only UV differs.
// Use a static VBO (8400 vertices), no index buffer, no culling.
struct StarVertex {
    float x, y, z;
    float u, v;
    std::uint8_t rgba[4];
    float radiusPx;
};
static_assert(std::is_standard_layout<StarVertex>::value, "GPU layout must be standard");
static_assert(sizeof(StarVertex) == 28 && offsetof(StarVertex, u) == 12 &&
              offsetof(StarVertex, rgba) == 20 && offsetof(StarVertex, radiusPx) == 24,
              "StarVertex must match the documented bgfx VertexLayout");

inline std::vector<StarVertex> buildStarfield() {
    std::vector<StarVertex> out;
    out.reserve(kStarCount * 6);
    // Specified integer RNG avoids implementation-dependent std::uniform distributions.
    // A fresh seed per call makes rebuilding independent of every other renderer system.
    std::uint32_t state = 0x53a9b4d1u;
    const auto unit = [&state]() {
        state = state * 1664525u + 1013904223u;
        return float(state >> 8) * (1.0f / 16777216.0f);
    };
    const float uv[6][2] = {{-1,-1},{1,-1},{1,1},{-1,-1},{1,1},{-1,1}};
    for (std::size_t i = 0; i < kStarCount; ++i) {
        const double y = 2.0 * unit() - 1.0;
        const double angle = 6.2831853071795864769 * unit();
        const double equator = std::sqrt(1.0 - y*y);
        const float light = unit();
        const float temperature = unit();
        const bool bright = i % 100 == 0; // exactly 1% uncommon, slightly brighter stars
        StarVertex vertex{};
        vertex.x = float(equator * std::cos(angle));
        vertex.y = float(y);
        vertex.z = float(equator * std::sin(angle));
        vertex.radiusPx = bright ? 1.4f + 0.2f * light : 0.5f + 0.9f * light;
        vertex.rgba[0] = std::uint8_t(205.0f + 28.0f * temperature);
        vertex.rgba[1] = std::uint8_t(215.0f + 12.0f * temperature);
        vertex.rgba[2] = std::uint8_t(236.0f - 25.0f * temperature);
        vertex.rgba[3] = std::uint8_t(255.0f *
            (bright ? 0.50f + 0.18f * light : 0.12f + 0.34f * light * light));
        for (const auto& corner : uv) {
            vertex.u = corner[0]; vertex.v = corner[1];
            out.push_back(vertex);
        }
    }
    return out;
}
// CPU oracle/support for vs_star.sc. Matrices are column-major, identical to the
// supplied bgfx view/projection matrices. No API-specific projection construction:
// multiply the caller's projection, then force far depth z=w (both GL and 0..1).
// Preserve the ENTIRE view 3x3 (including inclination), ignore its translation.
// Width/height must describe the active view's framebuffer pixel dimensions.
struct StarClip { float x, y, z, w; };
inline StarClip projectStarVertex(const StarVertex& v, const float* view,
                                  const float* proj, float width, float height) {
    const float x = kStarSphereRadius * (view[0]*v.x + view[4]*v.y + view[8]*v.z);
    const float y = kStarSphereRadius * (view[1]*v.x + view[5]*v.y + view[9]*v.z);
    const float z = kStarSphereRadius * (view[2]*v.x + view[6]*v.y + view[10]*v.z);
    StarClip clip{};
    clip.x = proj[0]*x + proj[4]*y + proj[8]*z + proj[12];
    clip.y = proj[1]*x + proj[5]*y + proj[9]*z + proj[13];
    clip.w = proj[3]*x + proj[7]*y + proj[11]*z + proj[15];
    clip.x += v.u * v.radiusPx * 2.0f / std::fmax(width, 1.0f) * clip.w;
    clip.y += v.v * v.radiusPx * 2.0f / std::fmax(height, 1.0f) * clip.w;
    clip.z = clip.w;
    return clip;
}
// CPU oracle for fs_star.sc. Straight RGB + this alpha requires SRC_ALPHA, ONE,
// NOT bgfx BLEND_ADD (ONE, ONE). No texture, point sprite, derivative or hard rim.
inline float starDiscAlpha(float u, float v, float alpha) {
    const float falloff = std::fmax(0.0f, 1.0f - (u*u + v*v));
    return alpha * falloff * falloff;
}
}} // namespace armada::sky
