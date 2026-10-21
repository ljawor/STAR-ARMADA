// W05 slice 4: the native side of the fog mask.
//
// The fixtures come from the Python encoder, so this checks agreement with the producer rather than
// self-consistency. The refusal cases matter more than they do elsewhere: a half-decoded mask shows
// ground the player has never seen, which is a state leak rather than a cosmetic slip.
#include "fogmap.hpp"

#include <cstdlib>
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
  } catch (const armada::fogmap::FogMapError&) {
    return;
  }
  std::cerr << "FAIL " << what << " was not refused" << std::endl;
  ++failures;
}

}  // namespace

int main() {
  using namespace armada::fogmap;

  const char* dir = std::getenv("ARMADA_FOG_FIXTURE_DIR");
  const std::filesystem::path fixtures =
      dir ? std::filesystem::path(dir) : std::filesystem::path(ARMADA_FOG_FIXTURE_DIR);

  const auto bytes = read(fixtures / "skirmish.bin");
  const Mask mask = decode(bytes.data(), bytes.size());
  check(mask.cells == 6, "cell count");
  check(mask.cell == 500.f, "cell size");
  check(mask.bounds == 3000.f, "bounds");
  check(mask.generation == 9, "generation");
  check(mask.rgba.size() == 6 * 6 * 4, "pixel count");
  // Row 0, texel 0 is the visible column: alpha 0 means "the team can see this cell".
  check(mask.rgba[3] == 0, "first texel is visible");
  // Rows are z, columns are x: texel (x, z) sits at (z * cells + x) * 4. That is the order
  // pygame.image.tobytes produces and the order the quad's texcoords expect, so the mask cannot
  // arrive transposed.
  check(mask.rgba[4 + 3] == 255, "texel (1,0) is unexplored");
  const size_t charted = (1 * 6 + 1) * 4;
  check(mask.rgba[charted + 3] == 155 && mask.rgba[charted] == 12, "texel (1,1) is charted");
  // The whole visible column (x = 0) must be see-through at every z.
  for (int z = 0; z < 6; ++z)
    check(mask.rgba[(z * 6) * 4 + 3] == 0, "visible column alpha at z=" + std::to_string(z));

  refuses([&] { decode(bytes.data(), bytes.size() - 4); }, "short pixel budget");

  {
    auto damaged = bytes;
    damaged[0] = 'X';
    refuses([&] { decode(damaged.data(), damaged.size()); }, "bad magic");
  }
  {
    auto damaged = bytes;
    damaged[kHeaderBytes] ^= 0xFF;  // one texel flipped, header intact
    refuses([&] { decode(damaged.data(), damaged.size()); }, "crc mismatch");
  }
  {
    auto damaged = bytes;
    damaged[10] = 0;
    damaged[11] = 0;  // zero cells
    refuses([&] { decode(damaged.data(), damaged.size()); }, "zero cells");
  }

  // Encoding agreement: the mask must survive an encode/decode cycle byte for byte, so a
  // re-published generation cannot differ from the one it replaced by accident.
  const Mask again = decode(bytes);
  check(again.rgba == mask.rgba && again.generation == mask.generation, "repeat decode is stable");

  if (failures == 0)
    std::cout << "fog mask: all checks passed" << std::endl;
  return failures == 0 ? 0 : 1;
}
