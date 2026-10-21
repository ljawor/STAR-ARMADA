// W03 overlay decoder test: decodes payloads authored by tools/render/write_frame_fixtures.py and
// refuses every malformed variant it ships. Header-only and GPU-free, so the risky half (refusing
// bytes) is tested without a device.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "overlay.hpp"

namespace {
int failures = 0;

void check(bool ok, const std::string &what) {
  if (!ok) {
    std::cerr << "FAIL " << what << "\n";
    ++failures;
  }
}

std::vector<uint8_t> load(const std::string &name) {
  std::ifstream in(std::string(ARMADA_FIXTURE_DIR) + "/" + name, std::ios::binary);
  if (!in)
    throw std::runtime_error("missing fixture " + name);
  return std::vector<uint8_t>(std::istreambuf_iterator<char>(in),
                              std::istreambuf_iterator<char>());
}

uint8_t pixel(uint16_t x, uint16_t y, int channel) {
  switch (channel) {
  case 0: return uint8_t((x * 16) & 0xFF);
  case 1: return uint8_t((y * 32) & 0xFF);
  case 2: return uint8_t(((x + y) * 7) & 0xFF);
  default: return 255;
  }
}

bool refuse(const std::vector<uint8_t> &payload, const char *what) {
  try {
    (void)armada::overlay::decode(payload);
    std::cerr << "FAIL accepted malformed payload: " << what << "\n";
    ++failures;
    return false;
  } catch (const armada::overlay::OverlayError &) {
    return true;
  }
}

void test_full_frame() {
  const auto frame = armada::overlay::decode(load("overlay-full-v1.bin"));
  check(frame.full, "full frame is flagged full");
  check(frame.width == 8 && frame.height == 4, "full frame dimensions");
  check(frame.patches.size() == 1, "full frame carries one patch");
  const auto &patch = frame.patches[0];
  check(patch.rect.x == 0 && patch.rect.y == 0 && patch.rect.w == 8 && patch.rect.h == 4,
        "full frame patch covers the surface");
  check(patch.rgba.size() == size_t(8 * 4 * 4), "full frame patch size");
  bool pixels_match = true;
  for (uint16_t y = 0; y < 4; ++y)
    for (uint16_t x = 0; x < 8; ++x)
      for (int c = 0; c < 4; ++c)
        pixels_match = pixels_match &&
                       patch.rgba[(size_t(y) * 8 + x) * 4 + c] == pixel(x, y, c);
  check(pixels_match, "full frame pixels match the authored pattern");
}

void test_patch_frame() {
  const auto frame = armada::overlay::decode(load("overlay-patch-v1.bin"));
  check(!frame.full, "patch frame is not flagged full");
  check(frame.patches.size() == 2, "patch frame carries two patches");
  const armada::overlay::Rect want[2] = {{2, 1, 3, 2}, {6, 0, 2, 3}};
  for (size_t i = 0; i < frame.patches.size() && i < 2; ++i) {
    const auto &r = frame.patches[i].rect;
    check(r.x == want[i].x && r.y == want[i].y && r.w == want[i].w && r.h == want[i].h,
          "patch " + std::to_string(i) + " rect matches the producer");
    check(frame.patches[i].rgba.size() == size_t(r.w) * r.h * 4,
          "patch " + std::to_string(i) + " byte count");
    bool ok = true;
    for (uint16_t y = 0; y < r.h; ++y)
      for (uint16_t x = 0; x < r.w; ++x)
        for (int c = 0; c < 4; ++c)
          ok = ok && frame.patches[i].rgba[(size_t(y) * r.w + x) * 4 + c] ==
                         pixel(r.x + x, r.y + y, c);
    check(ok, "patch " + std::to_string(i) + " pixels match the authored pattern");
  }
}

void test_refusals() {
  refuse(load("overlay-bad-magic.bin"), "bad magic");
  refuse(load("overlay-bad-version.bin"), "bad version");
  refuse(load("overlay-bad-flags.bin"), "unknown flags");
  refuse(load("overlay-truncated.bin"), "truncated payload");
  refuse(load("overlay-bad-crc.bin"), "crc mismatch");
  refuse(load("overlay-rect-outside.bin"), "rect outside the surface");
  refuse(load("overlay-full-with-rects.bin"), "full frame carrying rects");
  refuse(load("overlay-count-too-high.bin"), "rect count above the ceiling");
  refuse({}, "empty payload");
  // A payload that is one byte too long must be refused rather than half-applied.
  auto longer = load("overlay-patch-v1.bin");
  longer.push_back(0);
  refuse(longer, "one byte too long");
}

} // namespace

int main() {
  try {
    test_full_frame();
    test_patch_frame();
    test_refusals();
  } catch (const std::exception &e) {
    std::cerr << "FAIL exception: " << e.what() << "\n";
    return 1;
  }
  if (failures) {
    std::cerr << failures << " check(s) failed\n";
    return 1;
  }
  std::cout << "overlay: all checks passed\n";
  return 0;
}
