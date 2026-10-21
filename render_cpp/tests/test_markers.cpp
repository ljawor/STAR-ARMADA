// W05 slice 2: the native cue decoder must agree with the Python encoder byte for byte, and must
// refuse a batch it cannot trust whole.
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "marker_ring.hpp"

namespace {

std::vector<uint8_t> readFile(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream)
    throw std::runtime_error("cannot open " + path.string());
  return std::vector<uint8_t>(std::istreambuf_iterator<char>(stream),
                              std::istreambuf_iterator<char>());
}

void put16(std::vector<uint8_t>& at, size_t offset, uint16_t value) {
  at[offset] = uint8_t(value & 0xFF);
  at[offset + 1] = uint8_t(value >> 8);
}

std::vector<uint8_t> encode(const std::vector<armada::marker::Primitive>& primitives) {
  std::vector<uint8_t> out(armada::marker::kHeaderBytes +
                               primitives.size() * armada::marker::kRecordBytes,
                           0);
  std::memcpy(out.data(), armada::marker::kMagic, 8);
  put16(out, 8, armada::marker::kVersion);
  put16(out, 10, uint16_t(primitives.size()));
  for (size_t index = 0; index < primitives.size(); ++index) {
    const auto& p = primitives[index];
    uint8_t* at = out.data() + armada::marker::kHeaderBytes + index * armada::marker::kRecordBytes;
    at[0] = p.kind;
    at[1] = p.shape;
    put16(out, size_t(at - out.data()) + 2, p.flags);
    std::memcpy(at + 4, p.colour.data(), 4);
    std::memcpy(at + 8, p.centre.data(), 12);
    std::memcpy(at + 20, &p.size, 4);
    std::memcpy(at + 24, &p.width, 4);
    put16(out, size_t(at - out.data()) + 28, p.segments);
    put16(out, size_t(at - out.data()) + 30, 0);
  }
  const uint32_t crc = armada::marker::crc32(out.data() + armada::marker::kHeaderBytes,
                                             out.size() - armada::marker::kHeaderBytes);
  out[16] = uint8_t(crc & 0xFF);
  out[17] = uint8_t((crc >> 8) & 0xFF);
  out[18] = uint8_t((crc >> 16) & 0xFF);
  out[19] = uint8_t((crc >> 24) & 0xFF);
  return out;
}

void check(bool condition, const std::string& what) {
  if (!condition)
    throw std::runtime_error(what);
}

}  // namespace

int main() {
  const char* dir = std::getenv("ARMADA_MARKER_FIXTURE_DIR");
  if (dir == nullptr) {
    std::cerr << "ARMADA_MARKER_FIXTURE_DIR is not set\n";
    return 1;
  }
  const std::filesystem::path root(dir);
  int failures = 0;
  auto run = [&](const char* name, auto&& body) {
    try {
      body();
      std::cout << "ok   " << name << "\n";
    } catch (const std::exception& error) {
      std::cout << "FAIL " << name << ": " << error.what() << "\n";
      ++failures;
    }
  };

  run("decode", [&] {
    const auto bytes = readFile(root / "cues.bin");
    const auto primitives = armada::marker::decode(bytes.data(), bytes.size());
    check(primitives.size() == 3, "expected three primitives");
    const auto& ring = primitives[0];
    check(ring.kind == armada::marker::kCircle, "first primitive should be a circle");
    check(ring.shape == armada::marker::kShapeFlat, "first circle should lie flat");
    check(!ring.depth(), "selection rings are drawn on top");
    check(ring.segments == 28, "selection ring has 28 segments");
    check(ring.colour[3] == 229 || ring.colour[3] == 230, "alpha is 0.9");
    check(ring.size > 134.9f && ring.size < 135.1f, "radius is the drawn scale x 1.35");
    const auto& owner = primitives[1];
    check(owner.depth(), "planet owner rings are depth tested");
    check(owner.segments == 40, "planet ring has 40 segments");
    check(owner.size > 719.9f && owner.size < 720.1f, "radius + 120");
    const auto& marker = primitives[2];
    check(marker.kind == armada::marker::kMarkerPrimitive, "third primitive should be a marker");
    check(marker.shape == armada::marker::kShapeDiamond, "an enemy marker is a diamond");
    check(marker.size > 39.9f && marker.size < 40.1f, "marker carries the hull radius");
  });

  run("re-encode is byte identical", [&] {
    const auto bytes = readFile(root / "cues.bin");
    const auto again = encode(armada::marker::decode(bytes.data(), bytes.size()));
    check(again.size() == bytes.size(), "re-encoded length differs");
    check(std::memcmp(again.data(), bytes.data(), bytes.size()) == 0,
          "re-encoded bytes differ from the Python encoder");
  });

  for (const char* name : {"bad-crc.bin", "bad-magic.bin", "truncated.bin", "bad-count.bin",
                           "reserved.bin"}) {
    run(name, [&] {
      const auto bytes = readFile(root / name);
      try {
        (void)armada::marker::decode(bytes.data(), bytes.size());
      } catch (const armada::marker::MarkerError&) {
        return;                                  // refused, as it must be
      }
      throw std::runtime_error("a damaged batch was accepted");
    });
  }

  if (failures != 0) {
    std::cout << failures << " failure(s)\n";
    return 1;
  }
  std::cout << "all marker checks passed\n";
  return 0;
}
