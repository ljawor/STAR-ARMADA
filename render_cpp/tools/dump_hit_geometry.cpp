// Dump the contact geometry the window builds from a contact batch, so it can be compared with
// Python's own `hit_geometry` vertex for vertex.
//
// The bridge is the input: `hits.bin` is decoded by the real decoder, and every record is rebuilt by
// `appendHit` with a fixed `pxPerWorld` and the same camera basis the comparison script uses. Lines
// beginning with "T" are the contact triangles, "S" the smoke triangles.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "../include/emissive.hpp"
#include "../include/hit_effects.hpp"

int main(int argc, char** argv) {
  if (argc < 3) {
    std::fprintf(stderr, "usage: %s BATCH.bin PX_PER_WORLD\n", argv[0]);
    return 2;
  }
  const double pxPerWorld = std::atof(argv[2]);
  std::vector<uint8_t> bytes;
  if (FILE* file = std::fopen(argv[1], "rb")) {
    uint8_t chunk[4096];
    size_t got;
    while ((got = std::fread(chunk, 1, sizeof chunk, file)) > 0)
      bytes.insert(bytes.end(), chunk, chunk + got);
    std::fclose(file);
  } else {
    std::fprintf(stderr, "cannot read %s\n", argv[1]);
    return 2;
  }

  std::vector<armada::emissive::Primitive> primitives;
  try {
    primitives = armada::emissive::decode(bytes.data(), bytes.size());
  } catch (const std::exception& error) {
    std::fprintf(stderr, "decode failed: %s\n", error.what());
    return 1;
  }

  const double right[3] = {1.0, 0.0, 0.0};
  const double up[3] = {0.0, 1.0, 0.0};
  for (const auto& primitive : primitives) {
    const bool shield = primitive.kind == armada::emissive::kShieldHit;
    if (!shield && primitive.kind != armada::emissive::kHullHit)
      continue;
    const double centre[3] = {primitive.a[0], primitive.a[1], primitive.a[2]};
    const double normal[3] = {primitive.b[0], primitive.b[1], primitive.b[2]};
    const double size = shield ? double(primitive.shape) / 10.0 : double(primitive.radius);
    std::vector<armada::fx::HitVertex> triangles, smoke;
    armada::fx::HitCounters counters;
    armada::fx::appendHit(shield, centre, normal, double(primitive.radius), size,
                          double(primitive.width), uint32_t(primitive.segments),
                          (primitive.flags & armada::emissive::kFlagVisualContact) != 0, pxPerWorld,
                          right, up, triangles, smoke, &counters);
    for (const auto& v : triangles)
      std::printf("T %.9f %.9f %.9f %.9f %.9f %.9f %.9f\n", v.x, v.y, v.z, v.r, v.g, v.b, v.a);
    for (const auto& v : smoke)
      std::printf("S %.9f %.9f %.9f %.9f %.9f %.9f %.9f\n", v.x, v.y, v.z, v.r, v.g, v.b, v.a);
  }
  return 0;
}
