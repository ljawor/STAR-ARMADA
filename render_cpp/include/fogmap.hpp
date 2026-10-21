// W05 slice 4: the fog mask the Python renderer classified, decoded natively.
//
// The mask is square (cells x cells), one texel per visibility cell, and carries its own colour and
// alpha. Nothing here decides visibility - a cell is visible, charted or unexplored because the
// simulation said so. Refusing a doubtful blob whole matters more here than anywhere else: a
// half-decoded mask would reveal ground the player has never seen, which is a game-state leak and
// not just a visual bug.
#pragma once

#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace armada {
namespace fogmap {

constexpr char kMagic[8] = {'A', 'R', 'M', 'F', 'O', 'G', '0', '1'};
constexpr uint16_t kVersion = 1;
constexpr size_t kHeaderBytes = 28;
constexpr int kMaxCells = 2048;

struct Mask {
  int cells = 0;
  float cell = 0.f;
  float bounds = 0.f;
  uint32_t generation = 0;
  std::vector<uint8_t> rgba;
};

class FogMapError : public std::runtime_error {
 public:
  explicit FogMapError(const std::string& what) : std::runtime_error(what) {}
};

inline uint16_t read16(const uint8_t* at) {
  return uint16_t(at[0]) | uint16_t(at[1]) << 8;
}

inline uint32_t read32(const uint8_t* at) {
  return uint32_t(at[0]) | uint32_t(at[1]) << 8 | uint32_t(at[2]) << 16 | uint32_t(at[3]) << 24;
}

inline float readFloat(const uint8_t* at) {
  const uint32_t bits = read32(at);
  float value = 0.f;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

// crc32 as the bridge writes it (IEEE, reflected), so a truncated write is caught here rather than
// painted across half the map.
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
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < size; ++i)
    crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
  return crc ^ 0xFFFFFFFFu;
}

inline Mask decode(const uint8_t* data, size_t size) {
  if (size < kHeaderBytes)
    throw FogMapError("short header");
  if (std::memcmp(data, kMagic, 8) != 0)
    throw FogMapError("bad magic");
  const uint16_t version = read16(data + 8);
  if (version != kVersion)
    throw FogMapError("unsupported version");
  const uint16_t cells = read16(data + 10);
  if (cells < 1 || cells > kMaxCells)
    throw FogMapError("cells out of range");
  const size_t expected = size_t(cells) * size_t(cells) * 4u;
  if (size - kHeaderBytes != expected)
    throw FogMapError("pixel count does not match the header");
  const uint32_t stored = read32(data + 24);
  if (crc32(data + kHeaderBytes, expected) != stored)
    throw FogMapError("crc mismatch");
  Mask mask;
  mask.cells = int(cells);
  mask.cell = readFloat(data + 12);
  mask.bounds = readFloat(data + 16);
  mask.generation = read32(data + 20);
  mask.rgba.assign(data + kHeaderBytes, data + kHeaderBytes + expected);
  return mask;
}

inline Mask decode(const std::vector<uint8_t>& blob) {
  return decode(blob.data(), blob.size());
}

}  // namespace fogmap
}  // namespace armada
