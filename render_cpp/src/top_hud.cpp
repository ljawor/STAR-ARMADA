#include "top_hud.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <nlohmann/json.hpp>
#include <picosha2.h>
#include <stdexcept>
#define STB_TRUETYPE_IMPLEMENTATION
#include "../third_party/stb_truetype.h"
namespace armada::top_hud {
namespace {
using nlohmann::json;
[[noreturn]] void invalid() {
  throw std::invalid_argument("invalid top HUD payload");
}
std::vector<uint32_t> codepoints(const std::string &s) {
  std::vector<uint32_t> out;
  for (size_t i = 0; i < s.size();) {
    uint8_t b = uint8_t(s[i++]);
    uint32_t cp = b;
    int n = 0;
    uint32_t min = 0;
    if (b >= 0xc2 && b <= 0xdf) {
      cp = b & 31;
      n = 1;
      min = 0x80;
    } else if (b >= 0xe0 && b <= 0xef) {
      cp = b & 15;
      n = 2;
      min = 0x800;
    } else if (b >= 0xf0 && b <= 0xf4) {
      cp = b & 7;
      n = 3;
      min = 0x10000;
    } else if (b >= 0x80)
      invalid();
    for (int k = 0; k < n; ++k) {
      if (i == s.size() || (uint8_t(s[i]) & 0xc0) != 0x80)
        invalid();
      cp = (cp << 6) | (uint8_t(s[i++]) & 63);
    }
    if (cp < min || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff) ||
        cp < 32 || (cp >= 0x7f && cp <= 0x9f) || cp == 0x2028 || cp == 0x2029 ||
        (cp >= 0x202a && cp <= 0x202e) || (cp >= 0x2066 && cp <= 0x2069))
      invalid();
    out.push_back(cp);
  }
  return out;
}
std::string text(const json &j, size_t max) {
  if (!j.is_string())
    invalid();
  auto s = j.get<std::string>();
  if (s.size() > max)
    invalid();
  codepoints(s);
  return s;
}
Color color(const json &j) {
  if (!j.is_array() || j.size() != 3)
    invalid();
  Color c;
  for (int i = 0; i < 3; ++i) {
    if (!j[i].is_number_integer() || j[i] < 0 || j[i] > 255)
      invalid();
    c[i] = j[i].get<uint8_t>();
  }
  return c;
}
} // namespace
Model decode(const std::vector<uint8_t> &bytes) {
  if (bytes.empty() || bytes.size() > 16384)
    invalid();
  // The JSON parser treats raw NUL as EOF, even within a bounded input range.
  if (std::find(bytes.begin(), bytes.end(), uint8_t{0}) != bytes.end())
    invalid();
  try {
    std::vector<std::vector<std::string>> keys;
    auto callback = [&](int depth, json::parse_event_t event, json &parsed) {
      if (depth > 8)
        invalid();
      if (event == json::parse_event_t::object_start)
        keys.emplace_back();
      if (event == json::parse_event_t::key) {
        auto key = parsed.get<std::string>();
        auto &seen = keys.back();
        if (std::find(seen.begin(), seen.end(), key) != seen.end())
          invalid();
        seen.push_back(key);
      }
      if (event == json::parse_event_t::object_end)
        keys.pop_back();
      return true;
    };
    auto j = json::parse(bytes, callback);
    if (!j.is_object() || j.size() != 6 ||
        !j.at("version").is_number_integer() || j.at("version") != 1 ||
        !j.at("active").is_boolean())
      invalid();
    Model m;
    m.active = j.at("active").get<bool>();
    auto &cells = j.at("cells");
    if (!cells.is_array() || cells.size() != 5)
      invalid();
    for (int i = 0; i < 5; ++i) {
      auto &c = m.cells[i];
      auto &v = cells[i];
      if (!v.is_object() || v.size() != 5)
        invalid();
      c.label = text(v.at("label"), 16);
      c.value = text(v.at("value"), 96);
      c.rate = text(v.at("rate"), 96);
      c.color = color(v.at("color"));
      c.rate_color = color(v.at("rate_color"));
    }
    m.clock = text(j.at("clock"), 96);
    m.paused = text(j.at("paused"), 96);
    m.fps = text(j.at("fps"), 96);
    return m;
  } catch (const json::exception &) {
    invalid();
  }
}
FontAtlas::FontAtlas(const std::filesystem::path &path, int framebufferHeight) {
  if (framebufferHeight < 1 || framebufferHeight > 16384)
    throw std::invalid_argument("invalid font framebuffer height");
  std::ifstream in(path, std::ios::binary | std::ios::ate);
  if (!in)
    throw std::invalid_argument("cannot open bundled HUD font");
  auto length = in.tellg();
  if (length <= 0 || length > 1024 * 1024)
    throw std::invalid_argument("HUD font exceeds size limit");
  std::vector<uint8_t> data(static_cast<size_t>(length));
  in.seekg(0);
  if (!in.read(reinterpret_cast<char *>(data.data()), length))
    throw std::invalid_argument("HUD font read failed");
  // stb's font reader is not a security boundary. Authenticate bytes BEFORE any
  // stb call.
  if (picosha2::hash256_hex_string(data) !=
      "b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5")
    throw std::invalid_argument("HUD font SHA256 mismatch");
  pixel_height_ = std::clamp(38.f * framebufferHeight / 1440.f, 8.f, 120.f);
  width_ = height_ = pixel_height_ > 48 ? 2048 : 1024;
  std::vector<int> cps;
  for (int i = 32; i <= 0x17f; ++i)
    cps.push_back(i);
  for (int i = 0x400; i <= 0x4ff; ++i)
    cps.push_back(i);
  for (int i : {0x2013, 0x2014, 0x2026})
    cps.push_back(i);
  std::vector<stbtt_packedchar> packed(cps.size());
  std::vector<uint8_t> alpha(width_ * height_);
  stbtt_pack_context ctx;
  if (!stbtt_PackBegin(&ctx, alpha.data() + 2 * width_, width_, height_ - 2, 0,
                       1, nullptr))
    throw std::runtime_error("font pack allocation failed");
  stbtt_pack_range range{};
  range.font_size = pixel_height_;
  range.array_of_unicode_codepoints = cps.data();
  range.num_chars = int(cps.size());
  range.chardata_for_range = packed.data();
  int ok = stbtt_PackFontRanges(&ctx, data.data(), 0, &range, 1);
  stbtt_PackEnd(&ctx);
  if (!ok)
    throw std::runtime_error("HUD atlas capacity exceeded");
  for (size_t i = 0; i < cps.size(); ++i) {
    const auto &p = packed[i];
    glyphs_.push_back(
        {cps[i], p.x0, p.y0 + 2, p.x1, p.y1 + 2, p.xoff, p.yoff, p.xadvance});
  }
  pixels_.resize(alpha.size() * 4);
  for (size_t i = 0; i < alpha.size(); ++i) {
    pixels_[4 * i] = pixels_[4 * i + 1] = pixels_[4 * i + 2] = 255;
    pixels_[4 * i + 3] = alpha[i];
  }
  // Two rows were reserved above. A 2x2 white patch survives linear
  // filtering.
  for (int y = 0; y < 2; ++y)
    for (int x = 0; x < 2; ++x)
      pixels_[(y * width_ + x) * 4 + 3] = 255;
}
const Glyph &FontAtlas::glyph(uint32_t cp) const {
  auto it =
      std::lower_bound(glyphs_.begin(), glyphs_.end(), int(cp),
                       [](const Glyph &g, int c) { return g.codepoint < c; });
  if (it != glyphs_.end() && it->codepoint == int(cp))
    return *it;
  return *std::lower_bound(
      glyphs_.begin(), glyphs_.end(), int('?'),
      [](const Glyph &g, int c) { return g.codepoint < c; });
}
namespace {
struct Extent {
  float left = 0, right = 0, top = 0, bottom = 0;
};
Extent extent(const FontAtlas &f, const std::string &text) {
  Extent e;
  float pen = 0;
  for (auto cp : codepoints(text)) {
    auto &g = f.glyph(cp);
    e.left = std::min(e.left, pen + g.xoff);
    e.right = std::max(e.right, pen + g.xoff + g.x1 - g.x0);
    e.top = std::min(e.top, g.yoff);
    e.bottom = std::max(e.bottom, g.yoff + g.y1 - g.y0);
    pen += g.advance;
  }
  e.right = std::max(e.right, pen);
  return e;
}
uint32_t rgba(Color c, uint8_t a = 255) {
  return uint32_t(c[0]) | (uint32_t(c[1]) << 8) | (uint32_t(c[2]) << 16) |
         (uint32_t(a) << 24);
}
} // namespace
float FontAtlas::measure(const std::string &text, float pixelHeight) const {
  auto e = extent(*this, text);
  return (e.right - e.left) * pixelHeight / pixel_height_;
}
Mesh layout(const Model &model, int width, int height, const FontAtlas &font) {
  Mesh out;
  if (!model.active)
    return out;
  if (width < 1 || height < 1 || width > 32768 || height > 16384)
    throw std::invalid_argument("invalid HUD viewport");
  out.header_height = int(std::round(34. * height / 800.));
  if (!out.header_height)
    return out;
  float unit = height / 1440.f;
  constexpr float labelSize = 22, valueSize = 38, rateSize = 22;
  constexpr float clockSize = 28, pauseSize = 24, fpsSize = 20;
  bool fps = !model.fps.empty(), rates = true;
  auto total = [&](float s) {
    float w = 24 * s;
    for (auto &c : model.cells)
      w +=
          20 * s + font.measure(c.label, labelSize * s) + 8 * s +
          font.measure(c.value, valueSize * s) +
          (rates && !c.rate.empty() ? 8 * s + font.measure(c.rate, rateSize * s) : 0);
    for (auto &t : std::vector<std::pair<std::string, float>>{
             {model.clock, clockSize}, {model.paused, pauseSize}, {fps ? model.fps : "", fpsSize}})
      if (!t.first.empty())
        w += 12 * s + font.measure(t.first, t.second * s);
    return w;
  };
  if (total(unit) > width)
    fps = false;
  if (total(unit) > width)
    rates = false;
  if (total(unit) > width)
    unit *= width / total(unit);
  auto quad = [&](float x, float y, float w, float h, float u0, float v0,
                  float u1, float v1, uint32_t color) {
    if (w <= 0 || h <= 0)
      return;
    if (out.vertices.size() + 4 > 65536)
      throw std::length_error("HUD index capacity");
    auto base = uint16_t(out.vertices.size());
    out.vertices.push_back(
        {2 * x / width - 1, 1 - 2 * y / height, 0, u0, v0, color});
    out.vertices.push_back(
        {2 * (x + w) / width - 1, 1 - 2 * y / height, 0, u1, v0, color});
    out.vertices.push_back(
        {2 * (x + w) / width - 1, 1 - 2 * (y + h) / height, 0, u1, v1, color});
    out.vertices.push_back(
        {2 * x / width - 1, 1 - 2 * (y + h) / height, 0, u0, v1, color});
    for (int i : {0, 1, 2, 0, 2, 3})
      out.indices.push_back(uint16_t(base + i));
  };
  auto panel = [&](float x, float y, float w, float h, Color c, uint8_t a) {
    float u = 0.5f / font.width(), v = 0.5f / font.height();
    quad(x, y, w, h, u, v, u, v, rgba(c, a));
  };
  panel(0, 0, float(width), float(out.header_height), {10, 17, 25}, 245);
  panel(0, float(out.header_height - 1), float(width), 1, {54, 77, 91}, 255);
  auto text = [&](const std::string &str, const char *role, int cell, float x,
                  float pixels, Color color) {
    if (str.empty())
      return 0.f;
    auto e = extent(font, str);
    float scale = pixels / font.pixel_height();
    float w = (e.right - e.left) * scale, h = (e.bottom - e.top) * scale;
    float y = (out.header_height - h) / 2;
    out.text_bounds.push_back({str, role, x, y, w, h, cell});
    float pen = x - e.left * scale, baseline = y - e.top * scale;
    for (auto cp : codepoints(str)) {
      const auto &g = font.glyph(cp);
      quad(pen + g.xoff * scale, baseline + g.yoff * scale,
           (g.x1 - g.x0) * scale, (g.y1 - g.y0) * scale,
           float(g.x0) / font.width(), float(g.y0) / font.height(),
           float(g.x1) / font.width(), float(g.y1) / font.height(),
           rgba(color));
      pen += g.advance * scale;
    }
    return w;
  };
  // Surplus width separates cells; only optional FPS and rates may be removed.
  float extra = std::max(0.f, float(width) - total(unit)) / 5.f;
  float x = 12 * unit;
  for (int i = 0; i < 5; ++i) {
    auto &c = model.cells[i];
    x += 10 * unit;
    x += text(c.label, "label", i, x, labelSize * unit, {146, 161, 170});
    x += 8 * unit;
    x += text(c.value, "value", i, x, valueSize * unit, c.color);
    if (rates && !c.rate.empty()) {
      x += 8 * unit;
      x += text(c.rate, "rate", i, x, rateSize * unit, c.rate_color);
    }
    x += 10 * unit + extra;
    panel(x - unit, (out.header_height - 20 * unit) / 2, unit, 20 * unit,
          {52, 69, 80}, 255);
  }
  for (auto &t : std::vector<std::pair<std::string, float>>{
           {model.clock, clockSize}, {model.paused, pauseSize}, {fps ? model.fps : "", fpsSize}}) {
    if (t.first.empty())
      continue;
    x += 12 * unit;
    const char *role = t.second == clockSize ? "clock"
                       : t.second == pauseSize ? "paused"
                                        : "fps";
    x += text(t.first, role, -1, x, t.second * unit,
              t.second == pauseSize ? Color{235, 192, 112} : Color{174, 189, 199});
  }
  return out;
}
} // namespace armada::top_hud
