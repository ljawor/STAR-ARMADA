#include "top_hud.hpp"
#include <cassert>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <set>
#include <stdexcept>
using namespace armada::top_hud;
using nlohmann::json;
namespace {
#ifndef ARMADA_ASSET_ROOT
#define ARMADA_ASSET_ROOT "."
#endif
const std::filesystem::path assetRoot = ARMADA_ASSET_ROOT;
const std::filesystem::path fontPath =
    assetRoot / "assets/fonts/NotoSans-Regular.ttf";
json fixture() {
  json j = {{"version", 1},
            {"active", true},
            {"clock", "00:00"},
            {"paused", reinterpret_cast<const char *>(u8"\u041f\u0410\u0423\u0417\u0410")},
            {"fps", "60 FPS"}};
  j["cells"] = json::array();
  for (int i = 0; i < 5; ++i)
    j["cells"].push_back({{"label", "CR"},
                          {"value", "1,000"},
                          {"rate", "1.0/s"},
                          {"color", {10, 200, 90}},
                          {"rate_color", {70, 80, 90}}});
  return j;
}
Model parse(const json &j) {
  auto s = j.dump();
  return decode({s.begin(), s.end()});
}
void rejectBytes(const std::string &s) {
  try {
    decode({s.begin(), s.end()});
  } catch (const std::invalid_argument &) {
    return;
  }
  throw std::runtime_error("invalid bytes accepted");
}
void reject(const json &j) { rejectBytes(j.dump()); }
void testRawNulBoundary() {
  const auto valid = fixture().dump();
  assert(decode({valid.begin(), valid.end()}).active);
  rejectBytes(std::string(1, '\0') + valid);
  auto interior = valid;
  interior.insert(1, 1, '\0');
  rejectBytes(interior);
  auto escaped = fixture();
  escaped["paused"] = std::string(1, '\0');
  reject(escaped); // JSON-escaped \u0000 still reaches decoded-string validation.

  bool allRejected = true;
  for (const auto &suffix : {std::string(1, '\0'), std::string("\0junk", 5),
                             std::string("\0\xff", 2)}) {
    const auto payload = valid + suffix;
    bool rejected = false;
    try {
      decode({payload.begin(), payload.end()});
    } catch (const std::invalid_argument &) {
      rejected = true;
    }
    if (!rejected)
      std::cerr << "raw-NUL suffix accepted (" << suffix.size() << " bytes)\n";
    allRejected &= rejected;
  }
  assert(allRejected && "raw-NUL suffixes must not terminate bounded JSON input");
  std::cout << "raw-NUL boundary / escaped NUL / valid control: PASS\n";
}
void testDecode() {
  auto m = parse(fixture());
  assert(m.active && m.cells.size() == 5);
  assert(m.cells[0].value == "1,000" && m.cells[0].color[1] == 200);
  auto inactive = fixture();
  inactive["active"] = false;
  assert(!parse(inactive).active);
  for (auto v : std::vector<json>{2, 0, -1, 1.0, true, "1", nullptr}) {
    auto j = fixture();
    j["version"] = v;
    reject(j);
  }
  for (auto v : std::vector<json>{0, "true", nullptr}) {
    auto j = fixture();
    j["active"] = v;
    reject(j);
  }
  for (const char *key :
       {"version", "active", "cells", "clock", "paused", "fps"}) {
    auto j = fixture();
    j["active"] = false;
    j.erase(key);
    reject(j);
  }
  for (const char *key : {"label", "value", "rate", "color", "rate_color"}) {
    auto j = fixture();
    j["cells"][0].erase(key);
    reject(j);
  }
  for (int count : {0, 4, 6}) {
    auto j = fixture();
    j["cells"] = json::array();
    for (int i = 0; i < count; ++i)
      j["cells"].push_back(fixture()["cells"][0]);
    reject(j);
  }
  for (auto bad : std::vector<json>{-1, 256, 1.5, true, "2", nullptr})
    for (const char *key : {"color", "rate_color"}) {
      auto j = fixture();
      j["cells"][0][key][0] = bad;
      reject(j);
    }
  for (auto bad : std::vector<json>{json::array({0, 1}),
                                    json::array({0, 1, 2, 3}), "rgb"}) {
    auto j = fixture();
    j["cells"][0]["color"] = bad;
    reject(j);
  }
  for (const char *key : {"label", "value", "rate"}) {
    auto j = fixture();
    size_t limit = std::string(key) == "label" ? 16 : 96;
    j["cells"][0][key] = std::string(limit, '9');
    parse(j);
    j["cells"][0][key] = std::string(limit + 1, '9');
    reject(j);
    j["cells"][0][key] = 7;
    reject(j);
  }
  for (const char *key : {"clock", "paused", "fps"}) {
    auto j = fixture();
    j[key] = std::string(96, 'x');
    parse(j);
    j[key] = std::string(97, 'x');
    reject(j);
    j[key] = false;
    reject(j);
  }
  for (int c = 0; c < 160; ++c)
    if (c < 32 || c >= 127) {
      auto j = fixture();
      std::string s;
      if (c < 128)
        s += char(c);
      else {
        s += char(0xc2);
        s += char(c);
      }
      j["paused"] = s;
      reject(j);
    }
  for (auto bad : std::vector<std::string>{"\xff", "\xc0\xaf", "\xed\xa0\x80",
                                           "\xf4\x90\x80\x80", "\xe2\x82"}) {
    auto s = fixture().dump();
    s.replace(s.find("00:00"), 5, bad);
    rejectBytes(s);
  }
  for (const auto &bad :
       std::vector<std::string>{"{", "", std::string(16385, ' '), "[]", "null",
                                "{\"x\":\"\\ud800\"}"})
    rejectBytes(bad);
  auto duplicate = fixture().dump();
  duplicate.insert(1, "\"version\":1,");
  rejectBytes(duplicate);
  auto j = fixture();
  j["extra"] = true;
  reject(j);
  j = fixture();
  j["cells"][0]["extra"] = true;
  reject(j);
  auto padded = fixture().dump();
  padded.resize(16384, ' ');
  decode({padded.begin(), padded.end()});
  padded += ' ';
  rejectBytes(padded);
  rejectBytes(std::string(100, '[') + std::string(100, ']'));
  std::cout
      << "decode strict schema / limits / UTF8 / controls / duplicates: PASS\n";
}
void testFont() {
  FontAtlas font(fontPath, 1440);
  assert(font.pixels().size() == size_t(font.width() * font.height() * 4));
  assert(font.pixels()[3] == 255);
  // The solid panel texel must not overwrite any packed glyph.
  assert(font.glyph('!').y0 >= 2);
  for (size_t i = 0; i < font.pixels().size(); i += 4)
    assert(font.pixels()[i] == 255 && font.pixels()[i + 1] == 255 &&
           font.pixels()[i + 2] == 255);
  std::set<std::vector<uint8_t>> masks;
  for (uint32_t cp : {0x041fu, 0x0410u, 0x0105u, 0x0142u, 0x00f6u, 0x00dfu}) {
    auto g = font.glyph(cp);
    assert(g.codepoint == int(cp));
    assert(g.x1 > g.x0 && g.y1 > g.y0);
    int alpha = 0;
    std::vector<uint8_t> mask;
    for (int y = g.y0; y < g.y1; ++y)
      for (int x = g.x0; x < g.x1; ++x) {
        auto a = font.pixels()[(y * font.width() + x) * 4 + 3];
        alpha += a;
        mask.push_back(a);
      }
    assert(alpha > 0);
    assert(masks.insert(mask).second);
  }
  assert(font.measure("WWW", 29) > font.measure("iii", 29));
  assert(font.glyph(0x1f600).codepoint == '?');
  std::ifstream in(fontPath, std::ios::binary);
  std::vector<char> bytes((std::istreambuf_iterator<char>(in)), {});
  assert(!bytes.empty());
  bytes[bytes.size() / 2] ^= 1;
  auto path =
      std::filesystem::temp_directory_path() /
      ("armada-hud-corrupt-" +
       std::to_string(
           std::chrono::steady_clock::now().time_since_epoch().count()) +
       ".ttf");
  {
    std::ofstream out(path, std::ios::binary);
    out.write(bytes.data(), bytes.size());
  }
  bool rejected = false;
  try {
    FontAtlas bad(path, 1440);
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  std::filesystem::remove(path);
  assert(rejected);
  for (const auto &p :
       std::vector<std::filesystem::path>{assetRoot / "assets/fonts/OFL.txt",
                                          assetRoot / "does-not-exist.ttf"}) {
    rejected = false;
    try {
      FontAtlas bad(p, 1440);
    } catch (const std::invalid_argument &) {
      rejected = true;
    }
    assert(rejected);
  }
  std::cout << "font white RGBA / distinct Cyrillic-Polish-German / "
               "corruption: PASS\n";
}
void checkMesh(const Mesh &mesh, const Model &model, int width, int height) {
  assert(mesh.header_height == int(std::round(34. * height / 800)));
  assert(!mesh.vertices.empty());
  int stocks = 0;
  for (const auto &b : mesh.text_bounds) {
    if (b.role == "value") {
      assert(b.text == model.cells[b.cell].value);
      ++stocks;
    }
    assert(b.x >= -.01 && b.y >= -.01 && b.x + b.width <= width + .01 &&
           b.y + b.height <= mesh.header_height + .01);
  }
  assert(stocks == 5);
  for (size_t a = 0; a < mesh.text_bounds.size(); ++a)
    for (size_t b = a + 1; b < mesh.text_bounds.size(); ++b) {
      const auto &x = mesh.text_bounds[a];
      const auto &y = mesh.text_bounds[b];
      assert(x.x + x.width <= y.x + .01 || y.x + y.width <= x.x + .01 ||
             x.y + x.height <= y.y + .01 || y.y + y.height <= x.y + .01);
    }
  for (const auto &v : mesh.vertices) {
    assert(std::isfinite(v.x) && std::isfinite(v.y));
    assert(v.x >= -1.00001 && v.x <= 1.00001 && v.y >= -1.00001 &&
           v.y <= 1.00001);
    assert(v.u >= 0 && v.u <= 1 && v.v >= 0 && v.v <= 1);
    assert(v.z == 0);
  }
  for (auto i : mesh.indices)
    assert(i < mesh.vertices.size());
  assert(mesh.indices.size() % 6 == 0);
  assert(mesh.vertices.front().x == -1 && mesh.vertices.front().y == 1);
  assert(std::abs((1 - mesh.vertices[2].y) * height / 2 - mesh.header_height) <
         .01);
}
void testLayout() {
  for (auto size : std::vector<std::pair<int, int>>{{320, 200},
                                                    {640, 480},
                                                    {1280, 720},
                                                    {1280, 800},
                                                    {1920, 1080},
                                                    {1920, 1200},
                                                    {2560, 1440},
                                                    {2560, 1600},
                                                    {3840, 2160}}) {
    FontAtlas f(fontPath, size.second);
    for (int variant = 0; variant < 3; ++variant) {
      auto model = parse(fixture());
      if (variant) {
        for (auto &c : model.cells) {
          c.label = reinterpret_cast<const char *>(u8"\u017b\u00d3\u0141\u0106");
          c.value = variant == 2 ? std::string(96, '9') : "9,999,999,999";
          c.rate = "-999,999.9/s";
        }
        model.paused = reinterpret_cast<const char *>(
            u8"\u041f\u0410\u0423\u0417\u0410 \u2014 "
            u8"\u017b\u00f3\u0142\u0107 Gr\u00fc\u00dfe");
      }
      auto mesh = layout(model, size.first, size.second, f);
      checkMesh(mesh, model, size.first, size.second);
      if (variant == 2)
        for (const auto &b : mesh.text_bounds)
          assert(b.role != "fps" && b.role != "rate");
      if (!variant) {
        bool valueColor = false, rateColor = false;
        for (const auto &v : mesh.vertices) {
          valueColor |= v.color == 0xff5ac80au;
          rateColor |= v.color == 0xff5a5046u;
        }
        assert(valueColor && rateColor);
      }
    }
  }
  FontAtlas f(fontPath, 1440);
  auto model = parse(fixture());
  model.active = false;
  auto empty = layout(model, 1280, 800, f);
  assert(empty.vertices.empty() && empty.indices.empty() &&
         empty.text_bounds.empty());
  auto mesh = layout(parse(fixture()), 2560, 1440, f);
  for (const auto &b : mesh.text_bounds)
    if (b.role == "value")
      assert(b.height >= 24 && b.height < 34);
  std::cout << "layout 9 resolutions x normal/large/max / bounds / colors / "
               "inactive: PASS\n";
}
} // namespace
int main() {
  testRawNulBoundary();
  testDecode();
  testFont();
  testLayout();
  std::cout << "ALL TOP HUD CPU TESTS PASSED\n";
}
