// The hardware mesh blob is a second way for geometry to reach the window, so it gets the same
// treatment as the asset loader: decode a real blob, check the mesh that comes out, and refuse
// every malformed variant rather than half-accepting it.
#include "hardware.hpp"

#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {

int failures = 0;

void check(bool condition, const std::string &what) {
  if (!condition) {
    std::cerr << "FAIL " << what << "\n";
    ++failures;
  }
}

std::vector<uint8_t> read(const std::string &path) {
  std::ifstream in(path, std::ios::binary | std::ios::ate);
  if (!in) {
    std::cerr << "missing fixture " << path << "\n";
    std::exit(2);
  }
  const auto size = in.tellg();
  std::vector<uint8_t> bytes(static_cast<size_t>(size));
  in.seekg(0);
  if (!bytes.empty())
    in.read(reinterpret_cast<char *>(bytes.data()), size);
  return bytes;
}

bool refused(const std::vector<uint8_t> &blob) {
  try {
    armada::hardware::decode(blob.data(), blob.size());
    return false;
  } catch (const armada::hardware::HardwareError &) {
    return true;
  }
}

float length(float x, float y, float z) { return std::sqrt(x * x + y * y + z * z); }

}  // namespace

int main(int argc, char **argv) {
  const std::string dir = argc > 1 ? argv[1] : "fixtures/hardware";

  // `--dump` prints the decoded vertices instead of asserting, so the same blob can be compared
  // against the mesh Python built from the same catalogue, vertex for vertex. A count that matches
  // proves nothing about a silhouette.
  if (argc > 2 && std::string(argv[2]) == "--dump") {
    const std::string path = argc > 3 ? argv[3] : dir + "/imperial_planet_extractor.bin";
    const auto bytes = read(path);
    const auto mesh = armada::hardware::decode(bytes.data(), bytes.size());
    std::cout << "binding " << mesh.binding << "\n";
    std::cout << "triangles " << mesh.triangles << "\n";
    std::cout << std::setprecision(9);
    for (const auto &v : mesh.vertices)
      std::cout << "V " << v.x << ' ' << v.y << ' ' << v.z << ' ' << v.nx << ' ' << v.ny << ' '
                << v.nz << '\n';
    return 0;
  }

  // A real blob from the approved catalogue: the imperial extractor.
  const auto bytes = read(dir + "/imperial_planet_extractor.bin");
  const auto mesh = armada::hardware::decode(bytes.data(), bytes.size());
  check(mesh.binding == "imperial:planet_extractor", "binding arrives with the mesh");
  check(mesh.triangles == 2500, "the authored extractor is 2500 triangles, got " +
                                    std::to_string(mesh.triangles));
  check(mesh.vertices.size() == mesh.triangles * 3, "every triangle expands to three vertices");
  check(mesh.hi[1] > mesh.lo[1], "the mesh has height");
  check(mesh.hi[0] > mesh.lo[0] && mesh.hi[2] > mesh.lo[2], "the mesh has width and depth");

  // Normals must be unit length: they are the flat-shaded face normal the asset carries.
  float worst_normal = 0.0f;
  for (const auto &vertex : mesh.vertices)
    worst_normal = std::max(
        worst_normal, std::abs(length(vertex.nx, vertex.ny, vertex.nz) - 1.0f));
  check(worst_normal < 1e-3f, "every vertex normal is unit length, worst " +
                                  std::to_string(worst_normal));

  // Six roles, six colours: the palette is not on the wire, so a role index that collapses would
  // silently paint the whole building one material.
  std::vector<std::array<float, 3>> colours;
  std::vector<float> emissions;
  for (const auto &vertex : mesh.vertices) {
    std::array<float, 3> colour{vertex.r, vertex.g, vertex.b};
    bool seen = false;
    for (const auto &known : colours)
      seen = seen || (known == colour);
    if (!seen) {
      colours.push_back(colour);
      emissions.push_back(vertex.emission);
    }
  }
  check(colours.size() == 6, "the extractor uses all six roles, found " +
                                 std::to_string(colours.size()));
  size_t lit = 0;
  for (const auto vertex : mesh.vertices)
    lit += vertex.emission > 0.5f ? 1 : 0;
  check(lit > 0, "the emissive roles are marked emissive");

  // Refusals.
  check(refused(std::vector<uint8_t>(bytes.begin(), bytes.begin() + 8)), "a short blob is refused");
  auto foreign = bytes;
  foreign[0] = 'X';
  check(refused(foreign), "a foreign magic is refused");
  auto flipped = bytes;
  flipped.back() ^= 0xFF;
  check(refused(flipped), "a flipped payload byte is refused by the crc");
  check(refused(std::vector<uint8_t>(bytes.begin(), bytes.end() - 8)), "a truncated blob is refused");
  auto trailing = bytes;
  trailing.push_back(0);
  check(refused(trailing), "trailing bytes are refused");

  // The shield generator too, because a second kind proves the header is read rather than assumed.
  const auto other = read(dir + "/imperial_planet_shield_generator.bin");
  const auto second = armada::hardware::decode(other.data(), other.size());
  check(second.binding == "imperial:planet_shield_generator", "the second binding is its own");
  check(second.triangles != mesh.triangles, "two kinds are two meshes");

  if (failures == 0)
    std::cout << "hardware: " << mesh.binding << " " << mesh.triangles << " triangles, "
              << colours.size() << " roles, " << second.triangles << " in the second kind\n";
  return failures == 0 ? 0 : 1;
}
