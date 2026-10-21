// W05 slice 2: selection rings, ownership markers and planet owner rings.
//
// The Python renderer decides all of these (who is selected, who owns what, which relation, which
// hull severity); the window draws them. The wire format is in render_bridge/markers.py:
//
//   header <8sHHII>  20 B  magic "ARMARK01", version, count, reserved, crc32(records)
//   record <BBH4B3ffHH> 32 B
//     kind B     1 circle, 2 marker
//     shape B    circle: 0 flat (XZ), 1 upright (XY after -90 about X)
//                marker: 0 chevron, 1 diamond
//     flags H    bit0 depth test, bit1 alpha blend
//     colour 4B  rgba
//     centre 3f  world position
//     size f     circle: world radius; marker: hull world radius
//     width f    line width in pixels
//     segments H circle segments (0 = 28)
//     reserved H must be 0
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace armada {
namespace marker {

constexpr char kMagic[8] = {'A', 'R', 'M', 'A', 'R', 'K', '0', '1'};
constexpr uint16_t kVersion = 1;
constexpr size_t kHeaderBytes = 20;
constexpr size_t kRecordBytes = 32;
constexpr size_t kMaxRecords = 1024;

constexpr uint8_t kCircle = 1;
constexpr uint8_t kMarkerPrimitive = 2;

constexpr uint8_t kShapeFlat = 0;
constexpr uint8_t kShapeUpright = 1;
constexpr uint8_t kShapeChevron = 0;
constexpr uint8_t kShapeDiamond = 1;

constexpr uint16_t kFlagDepth = 0x01;
constexpr uint16_t kFlagBlend = 0x02;

class MarkerError : public std::runtime_error {
public:
  explicit MarkerError(const std::string& what) : std::runtime_error(what) {}
};

struct Primitive {
  uint8_t kind = 0;
  uint8_t shape = 0;
  uint16_t flags = 0;
  std::array<uint8_t, 4> colour{};
  std::array<float, 3> centre{};
  float size = 0.f;
  float width = 0.f;
  uint16_t segments = 0;

  bool depth() const { return (flags & kFlagDepth) != 0; }
  bool blend() const { return (flags & kFlagBlend) != 0; }
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
      uint32_t value = i;
      for (int bit = 0; bit < 8; ++bit)
        value = (value & 1u) ? (0xEDB88320u ^ (value >> 1)) : (value >> 1);
      table[i] = value;
    }
    ready = true;
  }
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < size; ++i)
    crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
  return crc ^ 0xFFFFFFFFu;
}

inline std::vector<Primitive> decode(const uint8_t* data, size_t size) {
  if (size < kHeaderBytes)
    throw MarkerError("shorter than the batch header");
  if (std::memcmp(data, kMagic, 8) != 0)
    throw MarkerError("bad batch magic");
  if (get16(data + 8) != kVersion)
    throw MarkerError("unsupported batch version");
  const uint16_t count = get16(data + 10);
  if (get32(data + 12) != 0)
    throw MarkerError("reserved header field must be zero");
  if (count > kMaxRecords)
    throw MarkerError("batch exceeds the primitive ceiling");
  const size_t expected = kHeaderBytes + size_t(count) * kRecordBytes;
  if (size != expected)
    throw MarkerError("length does not match the declared count");
  const uint32_t crc = get32(data + 16);
  if (crc32(data + kHeaderBytes, size - kHeaderBytes) != crc)
    throw MarkerError("batch crc mismatch");
  std::vector<Primitive> out;
  out.reserve(count);
  for (size_t index = 0; index < count; ++index) {
    const uint8_t* at = data + kHeaderBytes + index * kRecordBytes;
    Primitive primitive;
    primitive.kind = at[0];
    primitive.shape = at[1];
    primitive.flags = get16(at + 2);
    std::memcpy(primitive.colour.data(), at + 4, 4);
    std::memcpy(primitive.centre.data(), at + 8, 12);
    std::memcpy(&primitive.size, at + 20, 4);
    std::memcpy(&primitive.width, at + 24, 4);
    primitive.segments = get16(at + 28);
    if (primitive.kind != kCircle && primitive.kind != kMarkerPrimitive)
      throw MarkerError("unknown primitive kind");
    if (get16(at + 30) != 0)
      throw MarkerError("reserved record field must be zero");
    if (!(primitive.size >= 0.f) || !(primitive.width >= 0.f))
      throw MarkerError("primitive has a non-finite size");
    out.push_back(primitive);
  }
  return out;
}

}  // namespace marker
}  // namespace armada
