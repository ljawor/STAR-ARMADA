// W05: planet textures crossing the bridge.
//
// A planet in the Python renderer is a textured sphere. The texture is the procedural part
// (`render/textures.py::planet_texture`, seeded from the planet's name so a reload cannot change the
// world) and it is static for the life of a match, so it is published once per distinct planet and
// kept in a table here. The sphere is drawn from the frame's instance matrix, whose scale is the
// planet's radius.
//
// Wire format (see render_bridge/planets.py):
//
//     u8[8] magic "ARMPLN01" | u16 version | u16 width | u16 height | u16 name length | u32 crc32
//     name (utf-8) | width*height*4 RGBA, top row first
//
// Every check fails loudly: a half-decoded texture paints a corrupt planet, which is harder to
// attribute than a refusal.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace armada {
namespace planet {

constexpr char kMagic[8] = {'A', 'R', 'M', 'P', 'L', 'N', '0', '1'};
constexpr uint16_t kVersion = 1;
constexpr size_t kHeaderBytes = 20;
constexpr size_t kMaxDim = 2048;
constexpr size_t kMaxName = 128;
constexpr const char* kBindingPrefix = "planet:";

class PlanetError : public std::runtime_error {
public:
  explicit PlanetError(const std::string& what) : std::runtime_error(what) {}
};

struct Blob {
  std::string name;
  uint16_t width = 0;
  uint16_t height = 0;
  const uint8_t* rgba = nullptr;   // points into the ring payload; valid until it changes
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

//: Validate one blob. The returned pointer is into `buffer`, so the caller must copy or upload it
//: before the ring slot is reused.
inline Blob decode(const uint8_t* buffer, size_t size) {
  if (size < kHeaderBytes)
    throw PlanetError("shorter than the blob header");
  if (std::memcmp(buffer, kMagic, 8) != 0)
    throw PlanetError("bad blob magic");
  if (get16(buffer + 8) != kVersion)
    throw PlanetError("unsupported blob version");
  const uint16_t width = get16(buffer + 10), height = get16(buffer + 12);
  const uint16_t nameLength = get16(buffer + 14);
  const uint32_t crc = get32(buffer + 16);
  if (width == 0 || height == 0 || width > kMaxDim || height > kMaxDim)
    throw PlanetError("texture dimensions outside the allowed range");
  if (nameLength == 0 || nameLength > kMaxName)
    throw PlanetError("name length outside the allowed range");
  const size_t expected = kHeaderBytes + nameLength + size_t(width) * height * 4;
  if (size != expected)
    throw PlanetError("length does not match the header");
  const uint8_t* body = buffer + kHeaderBytes;
  if (crc32(body, size - kHeaderBytes) != crc)
    throw PlanetError("blob crc mismatch");
  Blob blob;
  blob.name.assign(reinterpret_cast<const char*>(body), nameLength);
  blob.width = width;
  blob.height = height;
  blob.rgba = body + nameLength;
  return blob;
}

//: True when a table binding names a planet rather than an asset mesh.
inline bool isPlanetBinding(const std::string& binding) {
  return binding.rfind(kBindingPrefix, 0) == 0;
}

//: The texture name a planet binding refers to (`planet:<kind>:<name>` -> `<name>`).
//: The name is everything after the *last* colon, because the middle field is the planet kind
//: ("temperate", "industrial", ...), not an asset id.
inline std::string planetKind(const std::string& binding) {
  if (!isPlanetBinding(binding))
    throw PlanetError("not a planet binding: " + binding);
  const size_t last = binding.rfind(':');
  if (last == std::string::npos || last <= std::strlen(kBindingPrefix))
    throw PlanetError("malformed planet binding: " + binding);
  return binding.substr(std::strlen(kBindingPrefix),
                        last - std::strlen(kBindingPrefix));
}

inline std::string planetTextureName(const std::string& binding) {
  planetKind(binding);              // an empty kind is malformed, not a planet called anything
  const size_t last = binding.rfind(':');
  if (last == std::string::npos || last + 1 >= binding.size() || last < std::strlen(kBindingPrefix))
    throw PlanetError("malformed planet binding: " + binding);
  return binding.substr(last + 1);
}

}  // namespace planet
}  // namespace armada
