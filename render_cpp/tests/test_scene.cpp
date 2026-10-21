#include "scene.hpp"
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
using namespace armada;
namespace fs = std::filesystem;
static fs::path temp;
static void check(bool ok, const char *text) {
  if (!ok)
    throw std::runtime_error(text);
}
static void rejects(const std::function<void()> &f) {
  try {
    f();
  } catch (const ProtocolError &) {
    return;
  }
  throw std::runtime_error("expected ProtocolError");
}
static void put(const fs::path &p, const std::string &s) {
  std::ofstream out(p, std::ios::binary);
  out.write(s.data(), s.size());
}
static uint32_t crc(const std::string &s) {
  uint32_t c = ~0u;
  for (unsigned char b : s) {
    c ^= b;
    for (int i = 0; i < 8; ++i)
      c = (c >> 1) ^ ((c & 1) ? 0xedb88320u : 0);
  }
  return ~c;
}
static std::string packet_body(const std::string &body, unsigned kind = 1) {
  std::string h("ARMADAS\0", 8);
  auto le = [&](uint64_t n, int bytes) {
    for (int i = 0; i < bytes; ++i)
      h.push_back(char(n >> (8 * i)));
  };
  le(1, 2);
  le(kind, 2);
  le(7, 4);
  le(9, 8);
  le(body.size(), 4);
  le(crc(body), 4);
  return h + body;
}
static std::string packet(const Json &j, unsigned kind = 1) {
  return packet_body(j.dump(), kind);
}
static Json world() {
  return {{"schema", 1},
          {"fixture", "tiny"},
          {"state_sha256", std::string(64, 'a')},
          {"camera",
           {{"target", {0, 0, 0}},
            {"distance", 10},
            {"yaw", 0},
            {"pitch", 0},
            {"fov", 60}}},
          {"instances", Json::array()},
          {"assets", Json::array()},
          {"metadata", Json::object()}};
}
static void protocol() {
  auto p = temp / "scene.bin";
  auto bytes = packet(world());
  put(p, bytes);
  check(read_snapshot(p) == world(), "world decode");
  for (size_t offset :
       {size_t(0), size_t(8), size_t(10), size_t(28), size_t(32)}) {
    auto bad = bytes;
    bad[offset] ^= char(127);
    put(p, bad);
    rejects([&] { read_snapshot(p); });
  }
  put(p, bytes + "x");
  rejects([&] { read_snapshot(p); });
  put(p, bytes.substr(0, 31));
  rejects([&] { read_snapshot(p); });
  auto bad = bytes;
  bad[24] = 0;
  bad[25] = 0;
  bad[26] = 0;
  bad[27] = 5;
  put(p, bad);
  rejects([&] { read_snapshot(p); });
  auto duplicate = world().dump();
  duplicate.insert(1, "\"schema\":1,");
  put(p, packet_body(duplicate));
  rejects([&] { read_snapshot(p); });
  put(p, packet(Json::array()));
  rejects([&] { read_snapshot(p); });
  put(p, packet(Json{{"schema", 1}, {"widgets", Json::array()}}, 2));
  check(read_snapshot(p)["schema"] == 1, "UI envelope decode");
  rejects([&] { read_snapshot(p, 1); });
  put(p, packet(world(), 2));
  rejects([&] { read_snapshot(p, 1); });
  put(p, packet(Json{{"schema", 2}}, 2));
  rejects([&] { read_snapshot(p); });
}
static Json tiny_mesh() {
  Json batches = Json::object();
  for (const char *role : {"base", "dark", "trim", "accent", "lit", "cool"})
    batches[role] = Json::array({Json::array({0, 2, 0, 0, 1, 2})});
  return {{"schema", 1},
          {"vertices", {{0, 0, 0}, {2, 0, 0}, {0, 0, 3}}},
          {"batches", batches},
          {"triangle_count", 6}};
}
static Json asset(const Json &mesh) {
  auto s = mesh.dump();
  put(temp / "tiny.json", s);
  return {{"binding", "tiny"},
          {"path", "tiny.json"},
          {"sha256", picosha2::hash256_hex_string(s)},
          {"vertex_count", 3},
          {"triangle_count", 6}};
}
static void mesh_correctness() {
  auto m = tiny_mesh();
  auto a = asset(m);
  check(read_bytes(temp / "tiny.json") == m.dump(), "public read_bytes");
  auto got = load_mesh(temp, a);
  check(got.source_vertices == 3 && got.triangles == 6 &&
            got.vertices.size() == 18,
        "expand all triangles");
  check(got.binding == "tiny" && got.lo[0] == 0 && got.hi[0] == 2 &&
            got.hi[2] == 3,
        "mesh bounds");
  size_t painted = 0, emissive = 0;
  for (const auto &v : got.vertices) {
    check(v.nx == 0 && v.ny == 2 && v.nz == 0,
          "retain unnormalized flat normals");
    painted += v.paint == 1;
    emissive += v.emission == 1;
  }
  check(painted == 3 && emissive == 6, "role flags");
  auto modern = m;
  modern.erase("schema");
  modern["contract"] = "star-armada/mesh-export";
  modern["contract_major"] = 1;
  modern["asset"] = "prototype:test/mesh";
  auto modern_record = asset(modern);
  modern_record["manifest_asset"] = "prototype:test/mesh";
  check(load_mesh(temp, modern_record).triangles == 6, "modern mesh contract");
  auto wrong_identity = modern_record;
  wrong_identity["manifest_asset"] = "prototype:test/other";
  rejects([&] { load_mesh(temp, wrong_identity); });
  for (const auto &field : {"contract", "contract_major"}) {
    auto bad_contract = modern;
    if (std::string(field) == "contract")
      bad_contract[field] = "unsupported/mesh";
    else
      bad_contract[field] = 2;
    auto bad_record = asset(bad_contract);
    bad_record["manifest_asset"] = "prototype:test/mesh";
    rejects([&] { load_mesh(temp, bad_record); });
  }
  a = asset(m);
  static_assert(sizeof(Vertex) == 44, "viewer vertex stride");
  const std::array<std::array<float, 3>, 6> colors = {{{.9f, .9f, .9f},
                                                       {.42f, .49f, .58f},
                                                       {.18f, .65f, 1},
                                                       {.09f, .13f, .19f},
                                                       {1, .67f, .18f},
                                                       {.65f, .72f, .78f}}};
  for (size_t role = 0; role < 6; ++role)
    for (size_t corner = 0; corner < 3; ++corner) {
      const auto &v = got.vertices[role * 3 + corner];
      check(v.r == colors[role][0] && v.g == colors[role][1] &&
                v.b == colors[role][2],
            "explicit role palette");
      check(v.x == (corner == 1 ? 2 : 0) && v.y == 0 &&
                v.z == (corner == 2 ? 3 : 0),
            "authored corner order");
    }
  auto bad = a;
  bad["sha256"] = std::string(64, '0');
  rejects([&] { load_mesh(temp, bad); });
  bad = a;
  bad["vertex_count"] = 4;
  rejects([&] { load_mesh(temp, bad); });
  bad = a;
  bad["triangle_count"] = 7;
  rejects([&] { load_mesh(temp, bad); });
  auto reject_mesh = [&](Json j) {
    auto record = asset(j);
    rejects([&] { load_mesh(temp, record); });
  };
  auto j = m;
  j["batches"]["base"][0][3] = 3;
  reject_mesh(j);
  j = m;
  j["batches"]["base"][0][3] = 0.5;
  reject_mesh(j);
  j = m;
  j["batches"]["base"][0][0] = "nan";
  reject_mesh(j);
  j = m;
  j["vertices"][0][0] = nullptr;
  reject_mesh(j);
  j = m;
  j["batches"]["unknown"] = j["batches"]["base"];
  reject_mesh(j);
  j = m;
  j["triangle_count"] = 5;
  reject_mesh(j);
  j = m;
  j["vertices"][0][0] = 1e100;
  reject_mesh(j);
  // Raw nonfinite overflow must be rejected by the JSON parser.
  auto s = std::string("{\"schema\":1,\"vertices\":[[1e999,0,0]],\"batches\":{}"
                       ",\"triangle_count\":0}");
  put(temp / "tiny.json", s);
  a["sha256"] = picosha2::hash256_hex_string(s);
  rejects([&] { load_mesh(temp, a); });
}
static void containment_and_refs() {
  auto m = tiny_mesh(), a = asset(m);
  fs::create_directory(temp / "root");
  put(temp / "root" / "good.json", m.dump());
  auto bad = a;
  for (const char *path : {"../tiny.json", "tiny.txt", "/absolute.json"}) {
    bad["path"] = path;
    rejects([&] { load_mesh(temp / "root", bad); });
  }
  fs::create_symlink(temp / "tiny.json", temp / "root" / "escape.json");
  bad["path"] = "escape.json";
  rejects([&] { load_mesh(temp / "root", bad); });
  put(temp / "root" / "huge.json", std::string(2 * 1024 * 1024 + 1, ' '));
  bad["path"] = "huge.json";
  rejects([&] { load_mesh(temp / "root", bad); });
  auto w = world();
  w["assets"] = Json::array({a});
  Json instance = {
      {"entity_id", 1},    {"binding", "tiny"}, {"position", {0, 0, 0}},
      {"yaw", 0},          {"scale", 1},        {"tint", {1, 1, 1, 1}},
      {"category", "ship"}};
  w["instances"] = Json::array({instance});
  auto p = temp / "world.bin";
  put(p, packet(w));
  check(read_snapshot(p) == w, "valid refs");
  auto reject_world = [&](Json j) {
    put(p, packet(j));
    rejects([&] { read_snapshot(p); });
  };
  auto j = w;
  j["instances"][0]["binding"] = "missing";
  reject_world(j);
  j = w;
  j["assets"].push_back(a);
  reject_world(j);
  j = w;
  j["instances"].push_back(j["instances"][0]);
  reject_world(j);
  j = w;
  j["instances"][0]["entity_id"] = -1;
  reject_world(j);
  j = w;
  j["instances"][0]["entity_id"] = 0.5;
  reject_world(j);
  j = w;
  j["instances"][0]["scale"] = 0;
  reject_world(j);
  j = w;
  j["instances"][0]["tint"][0] = 1.1;
  reject_world(j);
  j = w;
  j["instances"][0]["tint"][0] = 1.0000000001;
  reject_world(j);
  j = w;
  j["instances"][0]["yaw"] = nullptr;
  reject_world(j);
  j = w;
  j["instances"][0]["position"] = {1, 2};
  reject_world(j);
  j = w;
  j["camera"]["distance"] = 0;
  reject_world(j);
  j = w;
  j["camera"]["fov"] = 179;
  reject_world(j);
  j = w;
  j["camera"]["pitch"] = "nan";
  reject_world(j);
  j = w;
  j["camera"]["target"][0] = 1e100;
  reject_world(j);
  j = w;
  j["schema"] = 2;
  reject_world(j);
  j = w;
  j["state_sha256"] = "bad";
  reject_world(j);
  j = w;
  j["metadata"] = nullptr;
  reject_world(j);
  j = w;
  j["assets"][0]["vertex_count"] = 10001;
  reject_world(j);
  j = w;
  j["assets"] = Json::array();
  for (size_t i = 0; i < 4097; ++i) {
    auto b = a;
    b["binding"] = std::to_string(i);
    j["assets"].push_back(b);
  }
  reject_world(j);
}
int main() {
  try {
    const char *root = std::getenv("TMPDIR");
    if (!root)
      throw std::runtime_error("TMPDIR required");
    temp = fs::path(root) /
           ("armada-scene-" +
            std::to_string(std::chrono::high_resolution_clock::now()
                               .time_since_epoch()
                               .count()));
    fs::create_directories(temp);
    protocol();
    std::cout << "PASS protocol\n";
    mesh_correctness();
    std::cout << "PASS mesh_correctness\n";
    containment_and_refs();
    std::cout << "PASS containment_and_refs\n";
    fs::remove_all(temp);
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "FAIL " << e.what() << '\n';
    if (!temp.empty())
      fs::remove_all(temp);
    return 1;
  }
}
