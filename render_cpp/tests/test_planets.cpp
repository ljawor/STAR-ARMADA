// W05: the native side of the planet texture format.
//
// The fixtures come from the Python encoder, so this checks agreement rather than
// self-consistency: fields, the crc, the binding convention, and that a damaged blob is refused
// whole (a half-decoded texture paints a corrupt planet, which is harder to attribute than a
// refusal).
#include "planets.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

namespace {

int failures = 0;

void check(bool condition, const std::string& what) {
  if (!condition) {
    std::cerr << "FAIL " << what << std::endl;
    ++failures;
  }
}

std::vector<uint8_t> read(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream)
    throw std::runtime_error("cannot read " + path.string());
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

template <typename Callable>
void refuses(Callable call, const std::string& what) {
  try {
    call();
  } catch (const armada::planet::PlanetError&) {
    return;
  }
  std::cerr << "FAIL " << what << " was not refused" << std::endl;
  ++failures;
}

}  // namespace

int main() {
  using namespace armada::planet;

  const char *dir = std::getenv("ARMADA_PLANET_FIXTURE_DIR");
  const std::filesystem::path fixtures =
      dir ? std::filesystem::path(dir) : std::filesystem::path(ARMADA_PLANET_FIXTURE_DIR);

  const auto bytes = read(fixtures / "temperate.bin");
  const Blob blob = decode(bytes.data(), bytes.size());
  check(blob.name == "p1-3500", "blob name");
  check(blob.width == 4 && blob.height == 4, "blob dimensions");
  check(bytes.size() == kHeaderBytes + blob.name.size() + 4u * 4u * 4u, "blob length");
  // The pixel block starts after the name and is top-row-first RGBA.
  check(blob.rgba[0] == 0 && blob.rgba[1] == 0 && blob.rgba[2] == 0, "first pixel");
  check(blob.rgba[4 * 4 * 4 - 1] == 255, "last alpha");

  // Re-encoding must produce the identical bytes: two encoders can round-trip through themselves
  // and still disagree on padding, endianness or crc coverage.
  std::vector<uint8_t> again(bytes.size());
  std::memcpy(again.data(), kMagic, 8);
  auto put16 = [&](size_t at, uint16_t value) {
    again[at] = uint8_t(value & 0xFF);
    again[at + 1] = uint8_t(value >> 8);
  };
  auto put32 = [&](size_t at, uint32_t value) {
    for (int i = 0; i < 4; ++i)
      again[at + i] = uint8_t((value >> (8 * i)) & 0xFF);
  };
  put16(8, kVersion);
  put16(10, blob.width);
  put16(12, blob.height);
  put16(14, uint16_t(blob.name.size()));
  std::memcpy(again.data() + kHeaderBytes, blob.name.data(), blob.name.size());
  std::memcpy(again.data() + kHeaderBytes + blob.name.size(), blob.rgba, 4u * 4u * 4u);
  put32(16, crc32(again.data() + kHeaderBytes, again.size() - kHeaderBytes));
  check(again == bytes, "re-encoded blob is byte-identical");

  refuses([&] { decode(read(fixtures / "bad-crc.bin").data(), read(fixtures / "bad-crc.bin").size()); },
          "blob with a flipped pixel");
  refuses([&] { const auto b = read(fixtures / "bad-length.bin"); decode(b.data(), b.size()); },
          "blob with a truncated payload");
  refuses([&] { const auto b = read(fixtures / "bad-magic.bin"); decode(b.data(), b.size()); },
          "blob with the wrong magic");
  refuses([&] { const auto b = read(fixtures / "bad-size.bin"); decode(b.data(), b.size()); },
          "blob with a zero width");
  refuses([&] { const std::vector<uint8_t> tiny(8, 0); decode(tiny.data(), tiny.size()); },
          "a blob shorter than the header");

  // Bindings: `planet:<kind>:<name>` -> texture name, kind, and refusal of anything else.
  check(planetTextureName("planet:temperate:p1-3500") == "p1-3500", "texture name");
  check(planetKind("planet:temperate:p1-3500") == "temperate", "planet kind");
  check(planetTextureName("planet:industrial:shipyard-world") == "shipyard-world",
        "name with a dash");
  check(!isPlanetBinding("imperial:cruiser"), "an asset binding is not a planet");
  refuses([&] { planetTextureName("planet:temperate"); }, "binding without a name");
  refuses([&] { planetTextureName("planet::name"); }, "binding without a kind");
  refuses([&] { planetKind("imperial:cruiser"); }, "kind read from an asset binding");

  if (failures) {
    std::cerr << failures << " planet codec checks failed" << std::endl;
    return 1;
  }
  std::cout << "planet codec: fields, byte agreement and refusals OK" << std::endl;
  return 0;
}
