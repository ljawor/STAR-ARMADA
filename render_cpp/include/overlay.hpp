// W03 overlay payload: the composed HUD surface, dirty-rected, from the Python producer.
//
// Design A (render-w03-design-a-overlay-transport-2026-10-21) sends the surface the Python UI
// already paints rather than re-implementing its text and geometry here. Python decides which rects
// changed (render/overlay_upload.py) and packs them with render_bridge/overlay.py; this decodes
// them and refuses anything malformed, exactly like the frame v2 decoder.
//
// Layout (little-endian):
//   header, 28 bytes: <8s magic 'ARMOVL01'><H version><H flags><H width><H height><H rects>
//                     <H reserved><I payload bytes><I crc32>
//   flags bit 0: the payload is the whole surface, and the rect list is empty.
//   then `rects` x <HHHH> (x, y, w, h) followed by the RGBA bytes of each rect in order.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

#include "frame_v2.hpp"

namespace armada::overlay {

inline constexpr char kMagic[8] = {'A', 'R', 'M', 'O', 'V', 'L', '0', '1'};
inline constexpr uint16_t kVersion = 1;
inline constexpr uint16_t kFlagFull = 1;
inline constexpr size_t kHeaderBytes = 28;
inline constexpr size_t kRectBytes = 8;
inline constexpr uint16_t kMaxDimension = 8192;
inline constexpr uint16_t kMaxRects = 4096;
inline constexpr uint32_t kMaxPayload = 8u << 20;

struct Rect {
  uint16_t x = 0, y = 0, w = 0, h = 0;
};

struct Patch {
  Rect rect;
  std::vector<uint8_t> rgba;   // w * h * 4, rows top to bottom
};

struct Frame {
  uint16_t width = 0, height = 0;
  bool full = false;
  std::vector<Patch> patches;  // one entry for a full frame holding the whole surface
};

class OverlayError : public std::runtime_error {
public:
  explicit OverlayError(const std::string &what) : std::runtime_error(what) {}
};

namespace local {
inline void require(bool ok, const char *message) {
  if (!ok)
    throw OverlayError(message);
}
} // namespace local

// Decodes one payload. Refuses: wrong magic/version, unknown flags or reserved bits, dimensions
// outside 1..8192, more than 4096 rects, a payload over 8 MiB, a length that disagrees with the
// rects, a rect outside the surface, and a CRC mismatch.
inline Frame decode(const std::vector<uint8_t> &raw) {
  using armada::bridge::detail::crc32;
  using armada::bridge::detail::read_le;
  local::require(raw.size() >= kHeaderBytes, "overlay shorter than its header");
  local::require(std::memcmp(raw.data(), kMagic, 8) == 0, "overlay magic mismatch");
  const uint16_t version = read_le<uint16_t>(raw.data() + 8);
  const uint16_t flags = read_le<uint16_t>(raw.data() + 10);
  const uint16_t width = read_le<uint16_t>(raw.data() + 12);
  const uint16_t height = read_le<uint16_t>(raw.data() + 14);
  const uint16_t count = read_le<uint16_t>(raw.data() + 16);
  const uint16_t reserved = read_le<uint16_t>(raw.data() + 18);
  const uint32_t length = read_le<uint32_t>(raw.data() + 20);
  const uint32_t crc = read_le<uint32_t>(raw.data() + 24);
  local::require(version == kVersion, "unknown overlay version");
  local::require((flags & ~kFlagFull) == 0, "unknown overlay flags");
  local::require(reserved == 0, "overlay reserved field is not zero");
  local::require(width >= 1 && width <= kMaxDimension && height >= 1 && height <= kMaxDimension,
               "overlay dimensions out of range");
  local::require(count <= kMaxRects, "overlay rect count out of range");
  local::require(length <= kMaxPayload, "overlay payload too large");
  const bool full = (flags & kFlagFull) != 0;
  local::require(!(full && count != 0), "a full overlay must not carry rects");
  const size_t expected = kHeaderBytes + size_t(count) * kRectBytes + length;
  local::require(raw.size() == expected, "overlay length disagrees with its header");

  Frame frame;
  frame.width = width;
  frame.height = height;
  frame.full = full;

  size_t area = 0;
  std::vector<Rect> rects;
  rects.reserve(count);
  for (uint16_t i = 0; i < count; ++i) {
    const uint8_t *at = raw.data() + kHeaderBytes + size_t(i) * kRectBytes;
    Rect r{read_le<uint16_t>(at), read_le<uint16_t>(at + 2), read_le<uint16_t>(at + 4),
           read_le<uint16_t>(at + 6)};
    local::require(r.w != 0 && r.h != 0, "overlay rect has no area");
    local::require(uint32_t(r.x) + r.w <= width && uint32_t(r.y) + r.h <= height,
                 "overlay rect outside the surface");
    area += size_t(r.w) * r.h;
    rects.push_back(r);
  }
  const size_t want = full ? size_t(width) * height : area;
  local::require(size_t(length) == want * 4, "overlay payload does not match its rects");
  const uint8_t *payload = raw.data() + kHeaderBytes + size_t(count) * kRectBytes;
  local::require(crc32(payload, length) == crc, "overlay CRC32 mismatch");

  if (full) {
    Patch whole;
    whole.rect = Rect{0, 0, width, height};
    whole.rgba.assign(payload, payload + length);
    frame.patches.push_back(std::move(whole));
    return frame;
  }
  size_t offset = 0;
  for (const Rect &r : rects) {
    Patch patch;
    patch.rect = r;
    const size_t bytes = size_t(r.w) * r.h * 4;
    patch.rgba.assign(payload + offset, payload + offset + bytes);
    offset += bytes;
    frame.patches.push_back(std::move(patch));
  }
  return frame;
}

} // namespace armada::overlay
