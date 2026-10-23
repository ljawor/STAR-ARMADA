#include "vector_hud.hpp"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <random>
#include <cmath>
#include <iostream>
#include <nlohmann/json.hpp>
#include <stdexcept>
using namespace armada::vector_hud;
using nlohmann::json;
json fixture() {
  return {{"version", 1},
          {"active", false},
          {"logical_size", {800, 600}},
          {"ops", json::array()},
          {"fog", nullptr}};
}
Model parse(const json &j) {
  auto s = j.dump();
  return decode({s.begin(), s.end()});
}
void rejectBytes(const std::string &s) {
  bool bad = false;
  try {
    decode({s.begin(), s.end()});
  } catch (const std::invalid_argument &) {
    bad = true;
  }
  assert(bad);
}
void reject(const json &j) { rejectBytes(j.dump()); }
void decoder() {
  assert(!parse(fixture()).active);
  auto j = fixture();
  j["extra"] = 1;
  reject(j);
  j = fixture();
  j["version"] = 2;
  reject(j);
  j = fixture();
  j["active"] = 1;
  reject(j);
  j = fixture();
  j["logical_size"] = {63, 600};
  reject(j);
  j = fixture();
  j["logical_size"] = {800, 16385};
  reject(j);
  rejectBytes(fixture().dump() + std::string("\0junk", 5));
  rejectBytes(
      R"({"version":1,"version":1,"active":false,"logical_size":[800,600],"ops":[],"fog":null})");
  rejectBytes(std::string(5 * 1024 * 1024 + 1, ' '));
  j = fixture();
  j["fog"] = {{"cells", 2}, {"states", "0120"}};
  assert(parse(j).fogStates == "0120");
  j["fog"]["states"] = "012";
  reject(j);
  j["fog"]["states"] = "0123";
  reject(j);
  j = fixture();
  j["ops"].push_back({{"kind", "text"},
                      {"clip", {0, 0, 100, 100}},
                      {"pos", {0, 0}},
                      {"bounds", {0, 0, 100, 100}},
                      {"size", 12},
                      {"text", "hello"},
                      {"color", {1, 2, 3, 4}},
                      {"fit", "shrink"}});
  assert(parse(j).ops[0].text == "hello");
  for (const auto &field : {"extra", "stroke"}) {
    auto bad = j;
    bad["ops"][0][field] = 1;
    reject(bad);
  }
  auto bad = j;
  bad["ops"][0].erase("clip");
  reject(bad);
  bad = j;
  bad["ops"][0]["bounds"] = {0, 0, -1, 1};
  reject(bad);
  bad = j;
  bad["ops"][0]["size"] = 0;
  reject(bad);
  bad = j;
  bad["ops"][0]["pos"] = {65537, 0};
  reject(bad);
  bad = j;
  bad["ops"][0]["color"] = {1.5, 2, 3, 4};
  reject(bad);
  bad = j;
  bad["ops"][0]["fit"] = "stretch";
  reject(bad);
  for (const auto &bytes : {std::string("\x80", 1), std::string("\xc0\x80", 2),
                            std::string("\xed\xa0\x80", 3),
                            std::string("\xf4\x90\x80\x80", 4),
                            std::string("\xe2\x82", 2)}) {
    auto wire = j.dump();
    wire.replace(wire.find("hello"), 5, bytes);
    rejectBytes(wire);
  }
  for (const auto &control : {"\n", "\t", "\x7f", "\xc2\x85",
                              "\xe2\x80\xa8", "\xe2\x80\xae",
                              "\xe2\x81\xa6"}) {
    bad = j;
    bad["ops"][0]["text"] = control;
    reject(bad);
  }
  rejectBytes(j.dump() + " garbage");
  rejectBytes(
      R"({"version":1,"active":false,"logical_size":[800,600],"ops":[],"fog":{"cells":1,"cells":1,"states":"0"}})");
  auto maxPayload = fixture().dump();
  maxPayload.resize(5 * 1024 * 1024, ' ');
  assert(!decode({maxPayload.begin(), maxPayload.end()}).active);
  for (auto s : {std::string(1, '\0'), std::string("\xc2\x85", 2)}) {
    j["ops"][0]["text"] = s;
    rejectBytes(j.dump(-1, ' ', false, json::error_handler_t::replace));
  }
  j["ops"][0]["text"] = std::string(4097, 'x');
  reject(j);
  j["ops"][0]["text"] = "ok";
  j["ops"][0]["color"] = {1, 2, 3, 256};
  reject(j);
  j["ops"][0]["color"] = {1, 2, 3, 4};
  j["ops"][0]["size"] = 257;
  reject(j);
  std::cout << "decoder strict schema PASS\n";
}
void geometry() {
  armada::top_hud::FontAtlas font(std::string(ARMADA_ASSET_ROOT) +
                                      "/assets/fonts/NotoSans-Regular.ttf",
                                  600);
  Model m;
  m.active = true;
  m.logical_size = {800, 600};
  Op o;
  o.kind = "rect";
  o.clip = {20, 30, 40, 50};
  o.rect = {0, 0, 100, 100};
  o.color = {10, 20, 30, 70};
  m.ops = {o};
  auto d = layout(m, 800, 600, font);
  assert(!d.vertices.empty());
  assert(d.batches.size() == 1 && d.batches[0].textureKind == 0);
  for (auto v : d.vertices) {
    float x = (v.x + 1) * 400, y = (1 - v.y) * 300;
    assert(x >= 19.999 && x <= 60.001 && y >= 29.999 && y <= 80.001);
    assert(v.color == 0x461e140a);
  }
  m.ops[0].clip[2] = 0;
  assert(layout(m, 800, 600, font).vertices.empty());
  m.ops = {o};
  m.ops[0].kind = "fog";
  m.fogCells = 2;
  m.fogStates = "0120";
  m.ops.push_back(o);
  d = layout(m, 800, 600, font);
  assert(d.fogWidth == 2 && d.fogHeight == 2);
  assert(d.fogPixels == std::vector<uint8_t>({3, 6, 13, 255, 12, 22, 38, 155,
                                              12, 22, 38, 0, 3, 6, 13, 255}));
  assert(d.batches.size() == 2 && d.batches[0].textureKind == 1 &&
         d.batches[1].textureKind == 0);
  for (uint32_t i = 0; i < d.batches[0].indexCount; ++i) {
    auto v = d.vertices[d.indices[i]];
    assert(std::abs(v.u - ((v.x + 1) * 400 / 100)) < .00001);
    assert(std::abs(v.v - ((1 - v.y) * 300 / 100)) < .00001);
  }
  bool bad = false;
  try {
    layout(m, 0, 600, font);
  } catch (const std::invalid_argument &) {
    bad = true;
  }
  assert(bad);
  std::cout << "clipped geometry / semantic fog / batch order PASS\n";
}
void text() {
  armada::top_hud::FontAtlas f(std::string(ARMADA_ASSET_ROOT) +
                                   "/assets/fonts/NotoSans-Regular.ttf",
                               600);
  Model m;
  m.active = true;
  Op o;
  o.kind = "text";
  o.pos = {10, 20};
  o.clip = {0, 0, 800, 600};
  o.bounds = {10, 20, 200, 60};
  o.size = 24;
  o.text = reinterpret_cast<const char *>(u8"Zażółć Привет");
  o.fit = "shrink";
  o.color = {11, 22, 33, 99};
  m.ops = {o};
  auto d = layout(m, 800, 600, f);
  assert(d.textBounds.size() == 1 && !d.vertices.empty());
  auto t = d.textBounds[0];
  assert(t.text == o.text && t.x == 10 && t.y == 20 && t.width <= 200.001 &&
         t.height <= 60.001);
  for (auto v : d.vertices)
    assert(v.color == 0x6321160b);
  auto g = f.glyph('M');
  o.text = "M";
  o.fit = "clip";
  o.bounds = {10, 20, 200, 60};
  m.ops = {o};
  auto full = layout(m, 800, 600, f);
  assert(!full.vertices.empty());
  float edge = 10 + f.measure("M", 24) / 2;
  m.ops[0].clip = {edge, 0, 100, 100};
  d = layout(m, 800, 600, f);
  assert(!d.vertices.empty());
  bool partial = false;
  for (auto v : d.vertices) {
    assert((v.x + 1) * 400 >= edge - .001);
    if (v.u > float(g.x0) / f.width() + .00001 &&
        v.u < float(g.x1) / f.width() - .00001)
      partial = true;
  }
  assert(partial);
  m.ops[0].clip = {0, 0, 0, 100};
  assert(layout(m, 800, 600, f).textBounds.empty());
  for (auto s : {u8"▲", u8"▼", u8"▸", u8"✕", u8"→"}) {
    o.text = reinterpret_cast<const char *>(s);
    m.ops = {o};
    d = layout(m, 800, 600, f);
    assert(!d.vertices.empty());
    for (auto v : d.vertices)
      assert(v.u == .5f / f.width());
  }
  o.text = std::string(4096, 'M');
  o.size = 1;
  o.bounds = {0, 0, 65536, 65536};
  o.pos = {0, 0};
  o.clip = {0, 0, 65536, 65536};
  o.fit = "clip";
  m.ops.assign(16, o);
  bool bad = false;
  try {
    layout(m, 32768, 16384, f);
  } catch (const std::invalid_argument &) {
    bad = true;
  }
  assert(bad);
  for (auto size :
       std::vector<Point>{{320, 240}, {800, 600}, {1920, 1080}, {3840, 2160}}) {
    o.text = reinterpret_cast<const char *>(u8"Zażółć ▲");
    o.size = 12;
    o.bounds = {10, 20, 120, 30};
    o.pos = {10, 20};
    o.clip = {0, 0, 800, 600};
    o.fit = "shrink";
    m.ops = {o};
    armada::top_hud::FontAtlas resized(std::string(ARMADA_ASSET_ROOT) +
                                           "/assets/fonts/NotoSans-Regular.ttf",
                                       int(size[1]));
    assert(resized.glyph(0x17c).codepoint == 0x17c &&
           resized.glyph(0x41f).codepoint == 0x41f);
    auto out = layout(m, int(size[0]), int(size[1]), resized);
    for (auto idx : out.indices)
      assert(idx < out.vertices.size());
    for (auto t : out.textBounds)
      assert(std::isfinite(t.width) && std::isfinite(t.height));
    for (auto v : out.vertices)
      assert(std::isfinite(v.x) && std::isfinite(v.y) &&
             std::abs(v.x) <= 1.0001 && std::abs(v.y) <= 1.0001);
  }
  std::cout << "measured text / alpha / glyph UV clip / control icons / glyph "
               "budget / resize PASS\n";
}
void roundedAndLimits() {
  armada::top_hud::FontAtlas f(std::string(ARMADA_ASSET_ROOT) +
                                   "/assets/fonts/NotoSans-Regular.ttf",
                               600);
  Model m;
  m.active = true;
  Op o;
  o.kind = "rect";
  o.rect = {10, 10, 100, 80};
  o.clip = {0, 0, 800, 600};
  o.radius = 20;
  m.ops = {o};
  auto d = layout(m, 800, 600, f);
  assert(!d.vertices.empty());
  for (auto v : d.vertices)
    assert(!((std::abs((v.x + 1) * 400 - 10) < .001) &&
             (std::abs((1 - v.y) * 300 - 10) < .001)));
  o.stroke = 5;
  m.ops = {o};
  d = layout(m, 800, 600, f);
  for (auto v : d.vertices)
    assert(std::isfinite(v.x) && std::isfinite(v.y));
  for (auto kind : {"circle", "ellipse", "line", "polygon"}) {
    o.kind = kind;
    o.center = {50, 50};
    o.radius = 20;
    o.points = {{10, 10}, {90, 10}, {50, 40}, {90, 90}, {10, 90}};
    if (o.kind == "line")
      o.points.resize(2);
    m.ops = {o};
    assert(!layout(m, 800, 600, f).vertices.empty());
    m.ops[0].stroke = 0;
    if (o.kind != "line")
      assert(!layout(m, 800, 600, f).vertices.empty());
  }
  o.kind = "rect";
  o.radius = 0;
  o.stroke = 0;
  m.fogCells = 1;
  m.fogStates = "0";
  m.ops.clear();
  for (int i = 0; i < 8192; ++i) {
    o.kind = i % 2 ? "fog" : "rect";
    m.ops.push_back(o);
  }
  d = layout(m, 800, 600, f);
  assert(d.batches.size() == 8192);
  m.ops.push_back(m.ops[0]);
  bool bad = false;
  try {
    layout(m, 800, 600, f);
  } catch (const std::invalid_argument &) {
    bad = true;
  }
  assert(bad);
  assert(d.batches.size() == 8192 && d.vertices.size() == 49152);
  // Trusted direct models isolate the uint16 boundary independently of the
  // wire's lower op limit. A clipped triangle contributes four vertices.
  o.kind = "rect";
  m.ops.assign(10922, o);
  Op triangle;
  triangle.kind = "polygon";
  triangle.points = {{10, 10}, {30, 10}, {30, 30}};
  triangle.clip = {20, 0, 100, 100};
  m.ops.push_back(triangle);
  d = layout(m, 800, 600, f);
  assert(d.vertices.size() == 65536);
  assert(*std::max_element(d.indices.begin(), d.indices.end()) == 65535);
  m.ops.push_back(o);
  bad = false;
  try {
    layout(m, 800, 600, f);
  } catch (const std::invalid_argument &) {
    bad = true;
  }
  assert(bad && d.vertices.size() == 65536);
  m.active = false;
  d = layout(m, 800, 600, f);
  assert(d.vertices.empty() && d.fogPixels.empty() && d.batches.empty());
  m.logical_size = {0, 0};
  bad = false;
  try {
    layout(m, 800, 600, f);
  } catch (const std::invalid_argument &) {
    bad = true;
  }
  assert(bad);
  auto j = fixture();
  json r = {{"kind", "rect"},         {"clip", {0, 0, 10, 10}},
            {"rect", {0, 0, 10, 10}}, {"color", {1, 2, 3, 4}},
            {"stroke", 64},           {"radius", 65536}};
  j["ops"] = json::array();
  for (int i = 0; i < 4096; ++i)
    j["ops"].push_back(r);
  assert(parse(j).ops.size() == 4096);
  j["ops"].push_back(r);
  reject(j);
  j = fixture();
  j["fog"] = {{"cells", 2048}, {"states", std::string(2048 * 2048, '2')}};
  assert(parse(j).fogCells == 2048);
  j["fog"]["cells"] = 2049;
  reject(j);
  j = fixture();
  r = {{"kind", "text"},
       {"clip", {0, 0, 100, 100}},
       {"pos", {0, 0}},
       {"bounds", {0, 0, 100, 100}},
       {"size", 12},
       {"text", std::string(4096, 'x')},
       {"color", {1, 2, 3, 4}},
       {"fit", "clip"}};
  for (int i = 0; i < 16; ++i)
    j["ops"].push_back(r);
  assert(parse(j).ops.size() == 16);
  r["text"] = "x";
  j["ops"].push_back(r);
  reject(j);
  rejectBytes("{\"x\":\"" + std::string("\xc0\x80", 2) + "\"}");
  rejectBytes(std::string(14, '[') + std::string(14, ']'));
  std::cout << "rounded rect / primitive coverage / batch budget / wire "
               "maximums PASS\n";
}
double coverage(const DrawList &d, float x, float y, int width = 800,
                int height = 600) {
  double count = 0;
  for (size_t i = 0; i < d.indices.size(); i += 3) {
    auto a = d.vertices[d.indices[i]], b = d.vertices[d.indices[i + 1]],
         c = d.vertices[d.indices[i + 2]];
    auto cross = [&](auto v, auto w) {
      return ((w.x - v.x) * width / 2) * (y - (1 - v.y) * height / 2) -
             ((v.y - w.y) * height / 2) * (x - (v.x + 1) * width / 2);
    };
    auto u = cross(a, b), v = cross(b, c), w = cross(c, a);
    if ((u > 1e-5 && v > 1e-5 && w > 1e-5) ||
        (u < -1e-5 && v < -1e-5 && w < -1e-5))
      count++;
  }
  return count;
}
void iconAlpha() {
  armada::top_hud::FontAtlas f(std::string(ARMADA_ASSET_ROOT) +
                                   "/assets/fonts/NotoSans-Regular.ttf",
                               600);
  Model m;
  m.active = true;
  Op o;
  o.kind = "text";
  o.pos = {10, 20};
  o.clip = o.bounds = {0, 0, 800, 600};
  o.size = 24;
  o.fit = "clip";
  o.text = reinterpret_cast<const char *>(u8"✕");
  m.ops = {o};
  auto d = layout(m, 800, 600, f);
  assert(coverage(d, 10 + 24 * .405f, 20 + 24 * .395f) == 1);
  std::cout << "control icon translucent union PASS\n";
}
void strokeAlpha() {
  armada::top_hud::FontAtlas f(std::string(ARMADA_ASSET_ROOT) +
                                   "/assets/fonts/NotoSans-Regular.ttf",
                               600);
  Model m;
  m.active = true;
  Op o;
  o.kind = "polygon";
  o.clip = {0, 0, 800, 600};
  o.points = {{10, 10}, {100, 10}, {100, 100}, {10, 100}};
  o.stroke = 10;
  m.ops = {o};
  auto d = layout(m, 800, 600, f);
  assert(coverage(d, 12, 13) == 1);
  assert(coverage(d, 50, 50) == 0);
  std::cout << "joined polygon stroke alpha PASS\n";
}
void crossedPolygon() {
  armada::top_hud::FontAtlas f(std::string(ARMADA_ASSET_ROOT) +
                                 "/assets/fonts/NotoSans-Regular.ttf", 600);
  Model m;
  m.active = true;
  Op o;
  o.kind = "polygon";
  o.clip = {0, 0, 800, 600};
  o.points = {{10, 10}, {100, 100}, {10, 100}, {100, 10}};
  m.ops = {o};
  auto d = layout(m, 800, 600, f);
  assert(coverage(d, 55, 20) == 1);
  assert(coverage(d, 55, 90) == 1);
  assert(coverage(d, 20, 50) == 0);
  // Compare a reference ray-crossing fill with actual triangle coverage,
  // avoiding triangle boundaries, for both windings and repeated endpoints.
  for (auto points : std::vector<std::vector<Point>>{
           o.points, {{10, 10}, {100, 10}, {50, 40}, {100, 100}, {10, 100}},
           {{10, 10}, {100, 10}, {100, 100}, {10, 100}, {10, 10}}}) {
    for (int winding = 0; winding < 2; ++winding) {
      o.points = points;
      m.ops = {o};
      d = layout(m, 800, 600, f);
      for (float y = 12.371f; y < 100; y += 7.11f)
        for (float x = 12.193f; x < 100; x += 7.07f) {
          bool inside = false;
          for (size_t i = 0; i < points.size(); ++i) {
            auto a = points[i], b = points[(i + 1) % points.size()];
            if ((a[1] > y) != (b[1] > y) &&
                x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
              inside = !inside;
          }
          assert(coverage(d, x, y) == (inside ? 1 : 0));
        }
      std::reverse(points.begin(), points.end());
    }
  }
  std::cout << "crossed / concave / reversed polygon even-odd fill PASS\n";
}
void thickStrokeAlpha() {
  armada::top_hud::FontAtlas f(std::string(ARMADA_ASSET_ROOT) +
                                 "/assets/fonts/NotoSans-Regular.ttf", 600);
  Model m;
  m.active = true;
  Op o;
  o.kind = "polygon";
  o.clip = {0, 0, 800, 600};
  o.color = {25, 50, 75, 128};
  for (auto points : std::vector<std::vector<Point>>{
           {{10, 10}, {20, 10}, {20, 20}, {10, 20}},
           {{10, 10}, {100, 10}, {100, 100}, {55, 40}, {10, 100}}}) {
    for (int reversed = 0; reversed < 2; ++reversed) {
      for (float stroke : {1.f, 20.f, 64.f}) {
        o.points = points;
        o.stroke = stroke;
        m.ops = {o};
        auto d = layout(m, 800, 600, f);
        assert(!d.vertices.empty());
        for (auto v : d.vertices)
          assert(v.color == 0x804b3219);
        if (points.size() == 4) {
          auto count = coverage(d, 14.137f, 15.731f);
          std::cout << "square stroke=" << stroke << " reversed=" << reversed
                    << " sample coverage=" << count << std::endl;
          assert(count == (stroke == 1 ? 0 : 1));
          assert(coverage(d, 14.137f, 10.173f) == 1);
        }
        for (float y = .371f; y < 135; y += 2.711f)
          for (float x = .193f; x < 135; x += 2.707f)
            assert(coverage(d, x, y) <= 1);
        // Nonuniform drawable scaling and CPU clipping must preserve the same
        // single-covered union, not introduce doubled alpha along clip edges.
        m.ops[0].clip = {12, 11, 60, 80};
        auto clipped = layout(m, 1600, 900, f);
        for (float y = 11.371f; y < 91; y += 5.711f)
          for (float x = 12.193f; x < 72; x += 5.707f)
            assert(coverage(clipped, x * 2, y * 1.5f, 1600, 900) ==
                   coverage(d, x, y));
      }
      std::reverse(points.begin(), points.end());
    }
  }
  std::cout << "thin / collapsed thick / concave / reversed translucent stroke union PASS\n";
}
void workBudget() {
  armada::top_hud::FontAtlas f(std::string(ARMADA_ASSET_ROOT) +
                                 "/assets/fonts/NotoSans-Regular.ttf", 600);
  auto j = fixture();
  j["active"] = true;
  std::mt19937 rng(93245);
  json points = json::array();
  for (int i = 0; i < 256; ++i)
    points.push_back({2000 + (rng() % 10000) / 10.0,
                      (rng() % 6000) / 10.0});
  json op = {{"kind", "polygon"}, {"clip", {0, 0, 800, 600}},
             {"points", points}, {"color", {255, 255, 255, 128}}, {"stroke", 0}};
  for (int i = 0; i < 128; ++i)
    j["ops"].push_back(op);
  auto m = parse(j);
  auto start = std::chrono::steady_clock::now();
  assert(layout(m, 800, 600, f).vertices.empty());
  double seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start).count();
  std::cout << "offscreen 128x256 points seconds=" << seconds << std::endl;
  bool offscreenFast = seconds < 1.0;

  // Bounding boxes intersect the clip, but these retraced edges cancel and
  // produce no mesh. A per-op or mesh-only cap cannot bound the whole layout.
  points = json::array();
  for (int i = 0; i < 128; ++i) {
    points.push_back({-100, -100});
    points.push_back({2000, 400});
  }
  op["points"] = points;
  op["clip"] = {0, 300, 10, 10};
  j["ops"] = json::array({op});
  assert(layout(parse(j), 800, 600, f).vertices.empty());
  // This fixture costs 32,640 pair tests + 2,048 level-sort units +
  // 10,240 slab units = 44,928: 89 fit (3,998,592), 90 do not.
  for (int i = 1; i < 89; ++i)
    j["ops"].push_back(op);
  assert(layout(parse(j), 800, 600, f).vertices.empty());
  j["ops"].push_back(op);
  bool boundaryRejected = false;
  try { layout(parse(j), 800, 600, f); }
  catch (const std::invalid_argument &) { boundaryRejected = true; }
  assert(boundaryRejected);
  std::cout << "zero-output work boundary: 89 accepted, 90 rejected"
               " (44928 units/op, 4000000 limit)" << std::endl;
  for (int i = 90; i < 128; ++i)
    j["ops"].push_back(op);
  bool bad = false;
  start = std::chrono::steady_clock::now();
  try { layout(parse(j), 800, 600, f); }
  catch (const std::invalid_argument &) { bad = true; }
  seconds = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - start).count();
  std::cout << "cumulative zero-output rejection=" << bad
            << " seconds=" << seconds << std::endl;
  assert(bad && seconds < 1.0);
  assert(offscreenFast);
  std::cout << "offscreen rejection / cumulative CPU work budget PASS\n";
}
int main(int argc, char **argv) {
  if (argc > 1 && std::string(argv[1]) == "work") { workBudget(); return 0; }
  if (argc > 1 && std::string(argv[1]) == "stroke") { thickStrokeAlpha(); return 0; }
  decoder();
  geometry();
  text();
  roundedAndLimits();
  iconAlpha();
  strokeAlpha();
  crossedPolygon();
  thickStrokeAlpha();
  workBudget();
  return 0;
}
