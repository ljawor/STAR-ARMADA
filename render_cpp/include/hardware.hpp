// W05: an authored mesh the producer publishes because the window's catalogue cannot hold it.
//
// The window's meshes come from the offline snapshot's asset list, which only names assets of
// entities that were on the map when the snapshot was taken. Surface hardware is built during a
// match, so its mesh is published beside the frame: one blob per binding, sent once.
//
// Wire format (see render_bridge/hardware.py):
//
//     u8[8] magic "ARMHWR01" | u16 version | u16 name length | u16 triangles
//     u16 role blocks | u32 crc32 | name (utf-8)
//     per block: u8 role | u16 count | count * (n xyz, 3 vertices xyz) as float32
//
// Role colours are NOT on the wire. `base`, `dark`, `trim`, `accent`, `lit` and `cool` already mean
// the same material on both sides - the palette in scene.hpp has been the shared one since W01 - so
// a colour field would be a second copy of a decision made elsewhere. Only the silhouette travels.
//
// Everything is refused rather than half-accepted: a mesh that decodes to a plausible but wrong
// shape renders as a building nobody can attribute.
#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

#include "scene.hpp"

namespace armada {
namespace hardware {

constexpr char kMagic[8] = {'A', 'R', 'M', 'H', 'W', 'R', '0', '1'};
constexpr uint16_t kVersion = 1;
constexpr size_t kHeaderBytes = 20;
constexpr size_t kBlockBytes = 3;
constexpr size_t kRowBytes = 12 * sizeof(float);
constexpr size_t kMaxTriangles = 12000;
constexpr size_t kMaxName = 96;

class HardwareError : public std::runtime_error {
public:
  explicit HardwareError(const std::string& what) : std::runtime_error(what) {}
};

inline uint16_t get16(const uint8_t* at) {
  return uint16_t(at[0]) | uint16_t(at[1]) << 8;
}

inline uint32_t get32(const uint8_t* at) {
  return uint32_t(at[0]) | uint32_t(at[1]) << 8 | uint32_t(at[2]) << 16 |
         uint32_t(at[3]) << 24;
}

inline uint32_t crc32(const uint8_t* data, size_t size) {
  static uint32_t table[256];
  static bool ready = false;
  if (!ready) {
    for (uint32_t i = 0; i < 256; ++i) {
      uint32_t c = i;
      for (int k = 0; k < 8; ++k)
        c = (c & 1u) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      table[i] = c;
    }
    ready = true;
  }
  uint32_t c = 0xFFFFFFFFu;
  for (size_t i = 0; i < size; ++i)
    c = table[(c ^ data[i]) & 0xFFu] ^ (c >> 8);
  return c ^ 0xFFFFFFFFu;
}

// The order render_bridge/hardware.py::ROLES uses, and the material each index selects.
struct Role {
  const char* name;
  std::array<float, 3> colour;
  float emission;
  float paint;
};

inline const Role& role(uint8_t index) {
  static const Role roles[6] = {
      {"base", {.42f, .49f, .58f}, 0.0f, 0.0f},
      {"dark", {.09f, .13f, .19f}, 0.0f, 0.0f},
      {"trim", {.65f, .72f, .78f}, 0.0f, 0.0f},
      {"accent", {.9f, .9f, .9f}, 0.0f, 1.0f},
      {"lit", {1.0f, .67f, .18f}, 1.0f, 0.0f},
      {"cool", {.18f, .65f, 1.0f}, 1.0f, 0.0f},
  };
  if (index >= 6)
    throw HardwareError("role index outside the palette");
  return roles[index];
}

inline float number(const uint8_t* at) {
  float value = 0.0f;
  std::memcpy(&value, at, sizeof(value));
  if (!std::isfinite(value))
    throw HardwareError("a mesh coordinate is not finite");
  return value;
}

// Decode one blob into the window's own Mesh. Vertices are expanded per triangle corner exactly as
// scene.hpp::load_mesh does, because a role batch is flat-shaded.
inline Mesh decode(const uint8_t* data, size_t size, const std::string& fallback_binding = {}) {
  try {
    if (size < kHeaderBytes)
      throw HardwareError("blob shorter than its header");
    if (std::memcmp(data, kMagic, 8) != 0)
      throw HardwareError("not a hardware mesh blob");
    const uint16_t version = get16(data + 8);
    if (version != kVersion)
      throw HardwareError("unsupported version " + std::to_string(version));
    const uint16_t name_length = get16(data + 10);
    const uint16_t triangles = get16(data + 12);
    const uint16_t blocks = get16(data + 14);
    const uint32_t crc = get32(data + 16);
    if (name_length == 0 || name_length > kMaxName)
      throw HardwareError("invalid name length");
    if (triangles > kMaxTriangles)
      throw HardwareError("triangle limit");
    if (crc32(data + kHeaderBytes, size - kHeaderBytes) != crc)
      throw HardwareError("crc32 mismatch");
    if (size < kHeaderBytes + name_length)
      throw HardwareError("blob ends inside its name");
    Mesh mesh;
    mesh.binding = std::string(reinterpret_cast<const char*>(data + kHeaderBytes), name_length);
    if (mesh.binding.empty())
      mesh.binding = fallback_binding;
    size_t cursor = kHeaderBytes + name_length;
    size_t seen = 0;
    bool first = true;
    for (uint16_t block = 0; block < blocks; ++block) {
      if (cursor + kBlockBytes > size)
        throw HardwareError("blob ends inside a role block");
      const uint8_t index = data[cursor];
      const uint16_t count = get16(data + cursor + 1);
      cursor += kBlockBytes;
      const Role& material = role(index);
      if (cursor + size_t(count) * kRowBytes > size)
        throw HardwareError("blob ends inside a role block");
      for (uint16_t row = 0; row < count; ++row) {
        const uint8_t* at = data + cursor;
        const float nx = number(at), ny = number(at + 4), nz = number(at + 8);
        ++mesh.triangles;
        for (size_t corner = 0; corner < 3; ++corner) {
          const uint8_t* point = at + 12 + corner * 12;
          const auto x = number(point), y = number(point + 4), z = number(point + 8);
          if (first) {
            mesh.lo = {x, y, z};
            mesh.hi = {x, y, z};
            first = false;
          } else {
            mesh.lo = {std::min(mesh.lo[0], x), std::min(mesh.lo[1], y), std::min(mesh.lo[2], z)};
            mesh.hi = {std::max(mesh.hi[0], x), std::max(mesh.hi[1], y), std::max(mesh.hi[2], z)};
          }
          mesh.vertices.push_back({x, y, z, nx, ny, nz, material.colour[0], material.colour[1],
                                   material.colour[2], material.emission, material.paint});
        }
        cursor += kRowBytes;
      }
      seen += count;
    }
    if (cursor != size)
      throw HardwareError("blob has trailing bytes");
    if (seen != triangles)
      throw HardwareError("header says " + std::to_string(triangles) + " triangles, blocks hold " +
                          std::to_string(seen));
    mesh.source_vertices = mesh.vertices.size();
    return mesh;
  } catch (const HardwareError&) {
    throw;
  } catch (const std::exception& error) {
    throw HardwareError(error.what());
  }
}

}  // namespace hardware
}  // namespace armada
