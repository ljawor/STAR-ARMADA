// W05 slice 3: emissive primitives - weapon fire, beams, glows and jump rings.
//
// The Python renderer decides which effects are visible, how a beam is layered and how big a bolt
// is; the window draws. Wire format is render_bridge/emissive.py:
//
//   header <8sHHII>          20 B  magic "ARMEMIT1", version, count, reserved, crc32(records)
//   record <BBH4B3f3fffHH>   44 B
//     kind B     1 ribbon, 2 disc, 3 ring, 4 bolt
//     shape B    ribbon: 0 camera-facing, 1 flat
//                disc/ring: 0 billboard, 1 flat
//                bolt: 0 elongated along its axis, 1 square
//     flags H    bit0 depth test, bit1 additive blend
//     colour 4B  rgba
//     a 3f       ribbon start | disc/ring centre | bolt position
//     b 3f       ribbon end   | unused            | bolt heading (unit)
//     radius f   disc/ring world radius | bolt half-length in pixels
//     width f    ribbon half-width (world) | ring stroke half-width | bolt half-width (pixels)
//     segments H disc fan segments (0 = 24) | ring segments (0 = 32)
//     reserved H must be 0
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace armada {
namespace emissive {

constexpr char kMagic[8] = {'A', 'R', 'M', 'E', 'M', 'I', 'T', '1'};
constexpr uint16_t kVersion = 1;
constexpr size_t kHeaderBytes = 20;
constexpr size_t kRecordBytes = 44;
constexpr size_t kMaxRecords = 4096;

constexpr uint8_t kRibbon = 1;
constexpr uint8_t kDisc = 2;
constexpr uint8_t kRing = 3;
constexpr uint8_t kBolt = 4;
constexpr uint8_t kExplosion = 5;    // a blast carried as parameters (see explosion.hpp)
constexpr uint8_t kShield = 6;       // a standing shield shell (see shield.hpp)

constexpr uint8_t kShapeCamera = 0;
constexpr uint8_t kShapeFlat = 1;
constexpr uint8_t kShapeElongated = 0;
constexpr uint8_t kShapeSquare = 1;

constexpr uint16_t kFlagDepth = 0x01;
constexpr uint16_t kFlagAdditive = 0x02;

class EmissiveError : public std::runtime_error {
 public:
  explicit EmissiveError(const std::string& what) : std::runtime_error(what) {}
};

struct Primitive {
  uint8_t kind = 0;
  uint8_t shape = 0;
  uint16_t flags = 0;
  std::array<uint8_t, 4> colour{};
  std::array<float, 3> a{};
  std::array<float, 3> b{};
  float radius = 0.f;
  float width = 0.f;
  uint16_t segments = 0;

  bool depth() const { return (flags & kFlagDepth) != 0; }
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
    throw EmissiveError("shorter than the batch header");
  if (std::memcmp(data, kMagic, 8) != 0)
    throw EmissiveError("bad batch magic");
  if (get16(data + 8) != kVersion)
    throw EmissiveError("unsupported batch version");
  const uint16_t count = get16(data + 10);
  if (get32(data + 12) != 0)
    throw EmissiveError("reserved header field must be zero");
  if (count > kMaxRecords)
    throw EmissiveError("batch exceeds the primitive ceiling");
  if (size != kHeaderBytes + size_t(count) * kRecordBytes)
    throw EmissiveError("length does not match the declared count");
  if (crc32(data + kHeaderBytes, size - kHeaderBytes) != get32(data + 16))
    throw EmissiveError("batch crc mismatch");
  std::vector<Primitive> out;
  out.reserve(count);
  for (size_t index = 0; index < count; ++index) {
    const uint8_t* at = data + kHeaderBytes + index * kRecordBytes;
    Primitive primitive;
    primitive.kind = at[0];
    primitive.shape = at[1];
    primitive.flags = get16(at + 2);
    std::memcpy(primitive.colour.data(), at + 4, 4);
    std::memcpy(primitive.a.data(), at + 8, 12);
    std::memcpy(primitive.b.data(), at + 20, 12);
    std::memcpy(&primitive.radius, at + 32, 4);
    std::memcpy(&primitive.width, at + 36, 4);
    primitive.segments = get16(at + 40);
    if (primitive.kind < kRibbon || primitive.kind > kShield)
      throw EmissiveError("unknown emissive kind");
    if (get16(at + 42) != 0)
      throw EmissiveError("reserved record field must be zero");
    if (!(primitive.radius >= 0.f) || !(primitive.width >= 0.f))
      throw EmissiveError("primitive has a non-finite extent");
    out.push_back(primitive);
  }
  return out;
}

}  // namespace emissive
}  // namespace armada
