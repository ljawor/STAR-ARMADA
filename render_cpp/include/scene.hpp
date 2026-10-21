#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <nlohmann/json.hpp>
#include <picosha2.h>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
namespace armada {
using Json = nlohmann::json;
struct ProtocolError : std::runtime_error {
  using std::runtime_error::runtime_error;
};
namespace detail {
inline void require(bool ok, const char *message) {
  if (!ok)
    throw ProtocolError(message);
}
inline std::string read_file(const std::filesystem::path &p, size_t limit) {
  std::ifstream in(p, std::ios::binary | std::ios::ate);
  require(bool(in), "cannot open input");
  auto length = in.tellg();
  require(length >= 0 && uint64_t(length) <= limit, "input size limit");
  std::string s(size_t(length), '\0');
  in.seekg(0);
  if (!s.empty())
    in.read(&s[0], std::streamsize(s.size()));
  require(bool(in), "cannot read input");
  return s;
}
inline uint32_t crc32(const std::string &s) {
  uint32_t c = ~0u;
  for (unsigned char b : s) {
    c ^= b;
    for (int i = 0; i < 8; ++i)
      c = (c >> 1) ^ ((c & 1) ? 0xedb88320u : 0);
  }
  return ~c;
}
} // namespace detail
// Bounded binary-safe byte reader; string retains embedded NUL bytes.
inline std::string read_bytes(const std::filesystem::path &path) {
  try {
    return detail::read_file(path, 32 + 64 * 1024 * 1024);
  } catch (const ProtocolError &) {
    throw;
  } catch (const std::exception &e) {
    throw ProtocolError(e.what());
  }
}
struct Vertex {
  float x, y, z, nx, ny, nz, r, g, b, emission, paint;
};
struct Mesh {
  std::vector<Vertex> vertices;
  size_t source_vertices = 0, triangles = 0;
  std::string binding;
  std::array<float, 3> lo{}, hi{};
};
namespace detail {
inline float number(const Json &j) {
  require(j.is_number(), "expected finite number");
  double v = j.get<double>();
  require(std::isfinite(v) && std::abs(v) <= std::numeric_limits<float>::max(),
          "number outside finite float range");
  return static_cast<float>(v);
}
inline size_t integer(const Json &j, size_t limit) {
  require(j.is_number_integer(), "expected integer");
  if (j.is_number_unsigned()) {
    auto n = j.get<uint64_t>();
    require(n <= limit, "integer limit");
    return size_t(n);
  }
  auto n = j.get<int64_t>();
  require(n >= 0 && uint64_t(n) <= limit, "integer limit");
  return size_t(n);
}
inline void vector(const Json &j, size_t count) {
  require(j.is_array() && j.size() == count, "vector dimensions");
  for (const auto &n : j)
    number(n);
}
inline std::string text(const Json &j) {
  require(j.is_string() && !j.get_ref<const std::string &>().empty(),
          "expected nonempty string");
  return j.get<std::string>();
}
inline std::string digest(const Json &j) {
  auto s = text(j);
  require(s.size() == 64 &&
              s.find_first_not_of("0123456789abcdef") == std::string::npos,
          "invalid SHA256");
  return s;
}
inline void asset_record(const Json &a) {
  text(a.at("binding"));
  text(a.at("path"));
  digest(a.at("sha256"));
  integer(a.at("vertex_count"), 10000);
  integer(a.at("triangle_count"), 12000);
}
} // namespace detail
inline Mesh load_mesh(const std::filesystem::path &asset_root,
                      const Json &record) {
  try {
    detail::asset_record(record);
    std::filesystem::path relative = record.at("path").get<std::string>();
    detail::require(!relative.is_absolute() && relative.extension() == ".json",
                    "invalid mesh path");
    for (const auto &part : relative)
      detail::require(part != "..", "parent mesh path");
    auto root = std::filesystem::canonical(asset_root),
         path = std::filesystem::canonical(root / relative);
    auto r = root.begin(), p = path.begin();
    for (; r != root.end() && p != path.end() && *r == *p; ++r, ++p) {
    }
    detail::require(r == root.end() && p != path.end(),
                    "mesh outside asset root");
    auto source = detail::read_file(path, 2 * 1024 * 1024);
    detail::require(picosha2::hash256_hex_string(source) == record.at("sha256"),
                    "mesh SHA256 mismatch");
    auto j = Json::parse(source);
    detail::require(j.is_object() && detail::integer(j.at("schema"), 1) == 1,
                    "unsupported mesh schema");
    auto &points = j.at("vertices");
    auto &batches = j.at("batches");
    detail::require(points.is_array() && points.size() <= 10000 &&
                        batches.is_object(),
                    "invalid mesh arrays");
    Mesh mesh;
    mesh.source_vertices = points.size();
    mesh.binding = record.at("binding");
    detail::require(mesh.source_vertices ==
                        detail::integer(record.at("vertex_count"), 10000),
                    "vertex count mismatch");
    bool first = true;
    for (const auto &point : points) {
      detail::vector(point, 3);
      for (size_t c = 0; c < 3; ++c) {
        float v = detail::number(point[c]);
        if (first)
          mesh.lo[c] = mesh.hi[c] = v;
        else {
          mesh.lo[c] = std::min(mesh.lo[c], v);
          mesh.hi[c] = std::max(mesh.hi[c], v);
        }
      }
      first = false;
    }
    for (auto it = batches.begin(); it != batches.end(); ++it) {
      std::array<float, 3> color;
      float emission = 0, paint = 0;
      const auto &role = it.key();
      if (role == "base")
        color = {.42f, .49f, .58f};
      else if (role == "dark")
        color = {.09f, .13f, .19f};
      else if (role == "trim")
        color = {.65f, .72f, .78f};
      else if (role == "accent") {
        color = {.9f, .9f, .9f};
        paint = 1;
      } else if (role == "lit") {
        color = {1, .67f, .18f};
        emission = 1;
      } else if (role == "cool") {
        color = {.18f, .65f, 1};
        emission = 1;
      } else
        throw ProtocolError("unknown mesh role");
      detail::require(it.value().is_array(), "invalid triangle batch");
      for (const auto &row : it.value()) {
        detail::require(row.is_array() && row.size() == 6,
                        "invalid triangle row");
        float nx = detail::number(row[0]), ny = detail::number(row[1]),
              nz = detail::number(row[2]);
        detail::require(++mesh.triangles <= 12000, "triangle limit");
        for (size_t c = 3; c < 6; ++c) {
          auto index = detail::integer(row[c], 10000);
          detail::require(index < points.size(), "triangle index out of range");
          const auto &v = points[index];
          mesh.vertices.push_back({detail::number(v[0]), detail::number(v[1]),
                                   detail::number(v[2]), nx, ny, nz, color[0],
                                   color[1], color[2], emission, paint});
        }
      }
    }
    detail::require(mesh.triangles ==
                            detail::integer(j.at("triangle_count"), 12000) &&
                        mesh.triangles ==
                            detail::integer(record.at("triangle_count"), 12000),
                    "triangle count mismatch");
    return mesh;
  } catch (const ProtocolError &) {
    throw;
  } catch (const std::exception &e) {
    throw ProtocolError(e.what());
  }
}
// Validate world metadata independently from loading any referenced file.
inline void validate_world(const Json &j) {
  detail::require(detail::integer(j.at("schema"), 1) == 1,
                  "unsupported world schema");
  detail::text(j.at("fixture"));
  detail::digest(j.at("state_sha256"));
  detail::require(j.at("metadata").is_object(), "invalid metadata");
  const auto &camera = j.at("camera");
  detail::vector(camera.at("target"), 3);
  detail::number(camera.at("yaw"));
  detail::number(camera.at("pitch"));
  detail::require(detail::number(camera.at("distance")) > 0,
                  "invalid camera distance");
  auto fov = detail::number(camera.at("fov"));
  detail::require(fov > 1 && fov < 179, "invalid camera fov");
  const auto &assets = j.at("assets");
  const auto &instances = j.at("instances");
  detail::require(assets.is_array() && assets.size() <= 4096 &&
                      instances.is_array() && instances.size() <= 100000,
                  "snapshot array limit");
  std::set<std::string> bindings;
  for (const auto &a : assets) {
    detail::asset_record(a);
    detail::require(bindings.insert(detail::text(a.at("binding"))).second,
                    "duplicate asset binding");
  }
  std::set<size_t> entity_ids;
  for (const auto &instance : instances) {
    auto entity_id = detail::integer(instance.at("entity_id"),
                                     std::numeric_limits<int64_t>::max());
    detail::require(entity_ids.insert(entity_id).second, "duplicate entity ID");
    detail::require(bindings.count(detail::text(instance.at("binding"))) == 1,
                    "unknown instance binding");
    detail::vector(instance.at("position"), 3);
    detail::number(instance.at("yaw"));
    detail::require(detail::number(instance.at("scale")) > 0,
                    "invalid instance scale");
    detail::vector(instance.at("tint"), 4);
    for (const auto &n : instance.at("tint")) {
      auto v = n.get<double>();
      detail::require(v >= 0 && v <= 1, "invalid tint");
    }
    detail::text(instance.at("category"));
  }
}
inline Json read_snapshot(const std::filesystem::path &path,
                          uint16_t expected_kind = 0) {
  try {
    auto s = detail::read_file(path, 32 + 64 * 1024 * 1024);
    detail::require(s.size() >= 32, "truncated header");
    auto le = [&](size_t at, size_t count) {
      uint64_t n = 0;
      for (size_t i = 0; i < count; ++i)
        n |= uint64_t(static_cast<unsigned char>(s[at + i])) << (i * 8);
      return n;
    };
    detail::require(s.compare(0, 8, std::string("ARMADAS\0", 8)) == 0,
                    "bad magic");
    detail::require(le(8, 2) == 1, "unsupported protocol version");
    detail::require(le(10, 2) == 1 || le(10, 2) == 2,
                    "unsupported snapshot kind");
    detail::require(expected_kind == 0 || le(10, 2) == expected_kind,
                    "wrong snapshot kind for consumer");
    detail::require(le(24, 4) <= 64 * 1024 * 1024 && s.size() == 32 + le(24, 4),
                    "payload length mismatch");
    auto body = s.substr(32);
    detail::require(detail::crc32(body) == le(28, 4), "CRC mismatch");
    std::vector<std::set<std::string>> keys;
    auto j =
        Json::parse(body, [&](int, Json::parse_event_t event, Json &value) {
          if (event == Json::parse_event_t::object_start)
            keys.emplace_back();
          else if (event == Json::parse_event_t::object_end)
            keys.pop_back();
          else if (event == Json::parse_event_t::key)
            detail::require(keys.back().insert(value.get<std::string>()).second,
                            "duplicate JSON key");
          return true;
        });
    detail::require(j.is_object(), "payload must be object");
    detail::require(detail::integer(j.at("schema"), 1) == 1,
                    "unsupported payload schema");
    if (le(10, 2) == 1)
      validate_world(j);
    return j;
  } catch (const ProtocolError &) {
    throw;
  } catch (const std::exception &e) {
    throw ProtocolError(e.what());
  }
}
} // namespace armada
