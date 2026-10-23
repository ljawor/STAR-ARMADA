#include "vector_hud.hpp"
#include <algorithm>
#include <cmath>
#include <nlohmann/json.hpp>
#include <set>
#include <stdexcept>
namespace armada::vector_hud {
namespace {
using nlohmann::json;
[[noreturn]] void invalid() {
  throw std::invalid_argument("invalid vector HUD snapshot or mesh budget");
}
std::vector<uint32_t> cps(const std::string &s) {
  std::vector<uint32_t> out;
  for (size_t i = 0; i < s.size();) {
    uint32_t c = uint8_t(s[i++]), min = 0;
    int n = 0;
    if (c >= 0xc2 && c <= 0xdf) {
      c &= 31;
      n = 1;
      min = 128;
    } else if (c >= 0xe0 && c <= 0xef) {
      c &= 15;
      n = 2;
      min = 2048;
    } else if (c >= 0xf0 && c <= 0xf4) {
      c &= 7;
      n = 3;
      min = 65536;
    } else if (c >= 128)
      invalid();
    while (n--) {
      if (i == s.size() || (uint8_t(s[i]) & 192) != 128)
        invalid();
      c = (c << 6) | (uint8_t(s[i++]) & 63);
    }
    if (c < min || c > 0x10ffff || (c >= 0xd800 && c <= 0xdfff) || c < 32 ||
        (c >= 127 && c <= 159) || c == 0x2028 || c == 0x2029 ||
        (c >= 0x202a && c <= 0x202e) || (c >= 0x2066 && c <= 0x2069))
      invalid();
    out.push_back(c);
  }
  return out;
}
void keys(const json &j, std::initializer_list<const char *> names) {
  if (!j.is_object() || j.size() != names.size())
    invalid();
  for (auto n : names)
    if (!j.contains(n))
      invalid();
}
float number(const json &j, float lo = -65536, float hi = 65536) {
  if (!j.is_number())
    invalid();
  double x = j.get<double>();
  if (!std::isfinite(x) || x < lo || x > hi)
    invalid();
  return float(x);
}
int integer(const json &j, int lo, int hi) {
  if (!j.is_number_integer())
    invalid();
  return int(number(j, float(lo), float(hi)));
}
template <size_t N> std::array<float, N> coords(const json &j) {
  if (!j.is_array() || j.size() != N)
    invalid();
  std::array<float, N> a;
  for (size_t i = 0; i < N; ++i)
    a[i] = number(j[i]);
  return a;
}
Rect rect(const json &j) {
  auto a = coords<4>(j);
  if (a[2] < 0 || a[3] < 0)
    invalid();
  return a;
}
std::string string(const json &j, size_t max) {
  if (!j.is_string())
    invalid();
  auto s = j.get<std::string>();
  if (s.size() > max)
    invalid();
  cps(s);
  return s;
}
} // namespace
Model decode(const std::vector<uint8_t> &bytes) {
  if (bytes.empty() || bytes.size() > 5 * 1024 * 1024 ||
      std::find(bytes.begin(), bytes.end(), 0) != bytes.end())
    invalid();
  try {
    std::vector<std::set<std::string>> seen;
    auto cb = [&](int depth, json::parse_event_t e, json &p) {
      if (depth > 12)
        invalid();
      if (e == json::parse_event_t::object_start)
        seen.emplace_back();
      if (e == json::parse_event_t::key &&
          !seen.back().insert(p.get<std::string>()).second)
        invalid();
      if (e == json::parse_event_t::object_end)
        seen.pop_back();
      return true;
    };
    auto j = json::parse(bytes, cb);
    keys(j, {"version", "active", "logical_size", "ops", "fog"});
    if (integer(j.at("version"), 1, 1) != 1 || !j.at("active").is_boolean())
      invalid();
    Model m;
    m.active = j.at("active");
    auto &sz = j.at("logical_size");
    if (!sz.is_array() || sz.size() != 2)
      invalid();
    for (int i = 0; i < 2; ++i)
      m.logical_size[i] = integer(sz[i], 64, 16384);
    const auto &fog = j.at("fog");
    if (!fog.is_null()) {
      keys(fog, {"cells", "states"});
      m.fogCells = integer(fog.at("cells"), 1, 2048);
      m.fogStates = string(fog.at("states"), 2048 * 2048);
      if (m.fogStates.size() != size_t(m.fogCells) * m.fogCells ||
          m.fogStates.find_first_not_of("012") != std::string::npos)
        invalid();
    }
    const auto &ops = j.at("ops");
    if (!ops.is_array() || ops.size() > 4096)
      invalid();
    size_t total = 0;
    for (const auto &v : ops) {
      Op o;
      o.kind = string(v.at("kind"), 16);
      o.clip = rect(v.at("clip"));
      if (o.kind == "text") {
        keys(v,
             {"kind", "clip", "pos", "size", "text", "color", "bounds", "fit"});
        o.pos = coords<2>(v.at("pos"));
        o.bounds = rect(v.at("bounds"));
        o.size = number(v.at("size"), 0, 256);
        if (o.size <= 0)
          invalid();
        o.text = string(v.at("text"), 4096);
        total += o.text.size();
        if (total > 65536)
          invalid();
        o.fit = string(v.at("fit"), 6);
        if (o.fit != "shrink" && o.fit != "clip")
          invalid();
      } else if (o.kind == "rect") {
        keys(v, {"kind", "clip", "rect", "color", "stroke", "radius"});
        o.radius = number(v.at("radius"), 0);
        o.rect = rect(v.at("rect"));
      } else if (o.kind == "ellipse") {
        keys(v, {"kind", "clip", "rect", "color", "stroke"});
        o.rect = rect(v.at("rect"));
      } else if (o.kind == "circle") {
        keys(v, {"kind", "clip", "center", "radius", "color", "stroke"});
        o.center = coords<2>(v.at("center"));
        o.radius = number(v.at("radius"), 0);
      } else if (o.kind == "line" || o.kind == "polygon") {
        keys(v, {"kind", "clip", "points", "color", "stroke"});
        auto &a = v.at("points");
        if (!a.is_array() || a.size() > 256 ||
            (o.kind == "line" ? a.size() != 2 : a.size() < 3))
          invalid();
        for (auto &p : a)
          o.points.push_back(coords<2>(p));
      } else if (o.kind == "fog") {
        keys(v, {"kind", "clip", "rect"});
        o.rect = rect(v.at("rect"));
        if (!m.fogCells)
          invalid();
      } else
        invalid();
      if (o.kind != "fog") {
        auto &a = v.at("color");
        if (!a.is_array() || a.size() != 4)
          invalid();
        for (int i = 0; i < 4; ++i)
          o.color[i] = uint8_t(integer(a[i], 0, 255));
        if (o.kind != "text")
          o.stroke = number(v.at("stroke"), 0, 64);
      }
      m.ops.push_back(std::move(o));
    }
    return m;
  } catch (const json::exception &) {
    invalid();
  }
}
namespace {
uint32_t packed(Color c) {
  return uint32_t(c[0]) | (uint32_t(c[1]) << 8) | (uint32_t(c[2]) << 16) |
         (uint32_t(c[3]) << 24);
}
Rect intersect(Rect a, Rect b) {
  float x = std::max(a[0], b[0]), y = std::max(a[1], b[1]);
  return {x, y, std::max(0.f, std::min(a[0] + a[2], b[0] + b[2]) - x),
          std::max(0.f, std::min(a[1] + a[3], b[1] + b[3]) - y)};
}
struct Builder {
  DrawList out;
  Rect clip;
  float sx, sy;
  int width, height;
  const top_hud::FontAtlas &font;
  uint8_t texture = 0;
  uint32_t color = 0;
  // Cumulative, output-independent tessellation allowance per complete layout.
  // Reserve before pair tests, sorting and slab processing, including clipped
  // or degenerate geometry. Overflow rejects the whole candidate, not a suffix.
  size_t workRemaining = 4000000;
  void work(size_t count) {
    if (count > workRemaining)
      invalid();
    workRemaining -= count;
  }
  static size_t sortCost(size_t n) {
    size_t log = 0;
    for (size_t k = n; k > 1; k = (k + 1) / 2)
      ++log;
    return n * log;
  }
  bool visible(const std::vector<Point> &pts, float margin = 0) const {
    if (pts.empty())
      return false;
    float l = pts[0][0], r = l, t = pts[0][1], b = t;
    for (auto p : pts) {
      l = std::min(l, p[0]); r = std::max(r, p[0]);
      t = std::min(t, p[1]); b = std::max(b, p[1]);
    }
    return (r + margin) * sx > clip[0] &&
           (l - margin) * sx < clip[0] + clip[2] &&
           (b + margin) * sy > clip[1] &&
           (t - margin) * sy < clip[1] + clip[3];
  }
  top_hud::Vertex vertex(float x, float y, float u = -1, float v = -1) {
    if (u < 0) {
      u = .5f / font.width();
      v = .5f / font.height();
    }
    return {x, y, 0, u, v, color};
  }
  void tri(top_hud::Vertex a, top_hud::Vertex b, top_hud::Vertex c) {
    std::vector<top_hud::Vertex> p = {a, b, c};
    for (int edge = 0; edge < 4 && !p.empty(); ++edge) {
      std::vector<top_hud::Vertex> q;
      auto dist = [&](const top_hud::Vertex &t) {
        return edge == 0   ? t.x - clip[0]
               : edge == 1 ? clip[0] + clip[2] - t.x
               : edge == 2 ? t.y - clip[1]
                           : clip[1] + clip[3] - t.y;
      };
      auto prev = p.back();
      float pd = dist(prev);
      for (auto cur : p) {
        float cd = dist(cur);
        if ((pd >= 0) != (cd >= 0)) {
          float t = pd / (pd - cd);
          auto mix = [&](float x, float y) { return x + t * (y - x); };
          auto v = vertex(mix(prev.x, cur.x), mix(prev.y, cur.y),
                          mix(prev.u, cur.u), mix(prev.v, cur.v));
          v.z = mix(prev.z, cur.z);
          v.color = 0;
          for (int k = 0; k < 4; ++k)
            v.color |=
                uint32_t(std::lround(mix(float((prev.color >> (8 * k)) & 255),
                                         float((cur.color >> (8 * k)) & 255))))
                << (8 * k);
          q.push_back(v);
        }
        if (cd >= 0)
          q.push_back(cur);
        prev = cur;
        pd = cd;
      }
      p = std::move(q);
    }
    if (p.size() < 3)
      return;
    float area = 0;
    for (size_t i = 1; i + 1 < p.size(); ++i)
      area += std::abs((p[i].x - p[0].x) * (p[i + 1].y - p[0].y) -
                       (p[i].y - p[0].y) * (p[i + 1].x - p[0].x));
    if (area < 1e-9f)
      return;
    size_t count = (p.size() - 2) * 3;
    bool batch =
        out.batches.empty() || out.batches.back().textureKind != texture;
    if (out.vertices.size() + p.size() > 65536 ||
        out.indices.size() + count > 393216 ||
        (batch && out.batches.size() >= 8192))
      invalid();
    if (batch)
      out.batches.push_back({texture, uint32_t(out.indices.size()), 0});
    auto base = out.vertices.size();
    for (auto v : p) {
      v.x = 2 * v.x / width - 1;
      v.y = 1 - 2 * v.y / height;
      out.vertices.push_back(v);
    }
    for (size_t i = 1; i + 1 < p.size(); ++i) {
      out.indices.push_back(uint16_t(base));
      out.indices.push_back(uint16_t(base + i));
      out.indices.push_back(uint16_t(base + i + 1));
    }
    out.batches.back().indexCount += uint32_t(count);
  }
  void quad(float x, float y, float w, float h, float u0 = -1, float v0 = -1,
            float u1 = -1, float v1 = -1) {
    if (w <= 0 || h <= 0)
      return;
    auto a = vertex(x, y, u0, v0), b = vertex(x + w, y, u1, v0),
         c = vertex(x + w, y + h, u1, v1), d = vertex(x, y + h, u0, v1);
    tri(a, b, c);
    tri(a, c, d);
  }
  void segment(Point a, Point b, float stroke) {
    float dx = b[0] - a[0], dy = b[1] - a[1], len = std::hypot(dx, dy);
    if (len <= 0 || stroke <= 0)
      return;
    float nx = -dy / len * stroke / 2, ny = dx / len * stroke / 2;
    auto v0 = vertex((a[0] + nx) * sx, (a[1] + ny) * sy),
         v1 = vertex((b[0] + nx) * sx, (b[1] + ny) * sy),
         v2 = vertex((b[0] - nx) * sx, (b[1] - ny) * sy),
         v3 = vertex((a[0] - nx) * sx, (a[1] - ny) * sy);
    tri(v0, v1, v2);
    tri(v0, v2, v3);
  }
  void outline(const std::vector<Point> &input, float stroke) {
    if (!visible(input, stroke * 2))
      return;
    std::vector<Point> pts;
    for (auto p : input)
      if (pts.empty() || p != pts.back())
        pts.push_back(p);
    if (pts.size() > 1 && pts.front() == pts.back())
      pts.pop_back();
    if (pts.size() < 3)
      return;
    std::vector<Point> outer, inner;
    for (size_t i = 0; i < pts.size(); ++i) {
      auto prev = pts[(i + pts.size() - 1) % pts.size()], p = pts[i],
           next = pts[(i + 1) % pts.size()];
      float ax = p[0] - prev[0], ay = p[1] - prev[1], bx = next[0] - p[0],
            by = next[1] - p[1], al = std::hypot(ax, ay),
            bl = std::hypot(bx, by);
      float nx = -ay / al - by / bl, ny = ax / al + bx / bl,
            len = std::hypot(nx, ny);
      if (len < 1e-6f) {
        nx = -ay / al;
        ny = ax / al;
      } else {
        nx /= len;
        ny /= len;
      }
      float dot = nx * (-ay / al) + ny * (ax / al),
            miter = std::min(stroke * 2,
                             stroke * .5f / std::max(.25f, std::abs(dot)));
      outer.push_back({p[0] + nx * miter, p[1] + ny * miter});
      inner.push_back({p[0] - nx * miter, p[1] - ny * miter});
    }
    // Keep the existing joined stroke footprint, but tessellate the UNION of
    // its triangles. Inward offsets may cross or collapse at large widths;
    // drawing those strips independently would repeatedly blend their alpha.
    std::vector<std::vector<Point>> pieces;
    for (size_t i = 0; i < pts.size(); ++i) {
      size_t j = (i + 1) % pts.size();
      pieces.push_back({outer[i], outer[j], inner[j]});
      pieces.push_back({outer[i], inner[j], inner[i]});
    }
    tessellate(pieces, true);
  }
  void rounded(const Op &o) {
    float x = o.rect[0], y = o.rect[1], w = o.rect[2], h = o.rect[3];
    if (w <= 0 || h <= 0)
      return;
    float r = std::min(o.radius, std::min(w, h) / 2),
          s = std::min(o.stroke, std::min(w, h) / 2);
    auto contour = [&](float inset) {
      std::vector<top_hud::Vertex> p;
      float radius = std::max(0.f, r - inset), l = x + inset, t = y + inset,
            rgt = x + w - inset, bot = y + h - inset;
      for (int k = 0; k < 4; ++k) {
        float cx = k == 0 || k == 1 ? rgt - radius : l + radius,
              cy = k < 2 ? (k == 0 ? t + radius : bot - radius)
                         : (k == 2 ? bot - radius : t + radius);
        for (int i = 0; i <= 8; ++i) {
          float a = (-1.f + k) * 1.57079632679f + float(i) * 1.57079632679f / 8;
          p.push_back(vertex((cx + radius * std::cos(a)) * sx,
                             (cy + radius * std::sin(a)) * sy));
        }
      }
      return p;
    };
    auto outer = contour(0);
    if (s <= 0) {
      auto c = vertex((x + w / 2) * sx, (y + h / 2) * sy);
      for (size_t i = 0; i < outer.size(); ++i)
        tri(c, outer[i], outer[(i + 1) % outer.size()]);
    } else {
      auto inner = contour(s);
      for (size_t i = 0; i < outer.size(); ++i) {
        size_t j = (i + 1) % outer.size();
        tri(outer[i], outer[j], inner[j]);
        tri(outer[i], inner[j], inner[i]);
      }
    }
  }
  bool icon(uint32_t cp) const {
    return cp == 0x25b2 || cp == 0x25bc || cp == 0x25b8 || cp == 0x2715 ||
           cp == 0x2192;
  }
  void text(const Op &o) {
    clip = intersect(clip, {o.bounds[0] * sx, o.bounds[1] * sy,
                            o.bounds[2] * sx, o.bounds[3] * sy});
    if (clip[2] <= 0 || clip[3] <= 0 || o.text.empty())
      return;
    auto codes = cps(o.text);
    float left = 0, right = 0, top = 0, bottom = 0, pen = 0,
          ph = font.pixel_height();
    for (auto cp : codes) {
      if (icon(cp)) {
        right = std::max(right, pen + ph * .8f);
        top = std::min(top, -ph * .8f);
        pen += ph * .9f;
      } else {
        auto &g = font.glyph(cp);
        left = std::min(left, pen + g.xoff);
        right = std::max(right, pen + g.xoff + g.x1 - g.x0);
        top = std::min(top, g.yoff);
        bottom = std::max(bottom, g.yoff + g.y1 - g.y0);
        pen += g.advance;
      }
    }
    right = std::max(right, pen);
    float scale = o.size * sy / ph, w = (right - left) * scale,
          h = (bottom - top) * scale;
    float x = o.pos[0] * sx, y = o.pos[1] * sy;
    if (o.fit == "shrink") {
      float aw = std::max(0.f, (o.bounds[0] + o.bounds[2]) * sx -
                                   std::max(x, o.bounds[0] * sx)),
            ah = std::max(0.f, (o.bounds[1] + o.bounds[3]) * sy -
                                   std::max(y, o.bounds[1] * sy));
      float fit =
          std::min(1.f, std::min(w > 0 ? aw / w : 1.f, h > 0 ? ah / h : 1.f));
      scale *= fit;
      w *= fit;
      h *= fit;
    }
    if (scale <= 0)
      return;
    out.textBounds.push_back({o.text, x, y, w, h});
    pen = x - left * scale;
    float baseline = y - top * scale;
    for (auto cp : codes) {
      if (icon(cp)) {
        float z = ph * scale, ix = pen, iy = baseline - z * .8f;
        auto p = [&](float a, float b) {
          return vertex(ix + a * z, iy + b * z);
        };
        if (cp == 0x25b2)
          tri(p(.4f, 0), p(.8f, .8f), p(0, .8f));
        else if (cp == 0x25bc)
          tri(p(0, 0), p(.8f, 0), p(.4f, .8f));
        else if (cp == 0x25b8)
          tri(p(0, 0), p(.8f, .4f), p(0, .8f));
        else {
          std::vector<Point> shape =
              cp == 0x2192
                  ? std::vector<Point>{{0, .34f},  {.5f, .34f}, {.5f, .1f},
                                       {.8f, .4f}, {.5f, .7f},  {.5f, .46f},
                                       {0, .46f}}
                  : std::vector<Point>{{.1f, 0},   {.4f, .3f}, {.7f, 0},
                                       {.8f, .1f}, {.5f, .4f}, {.8f, .7f},
                                       {.7f, .8f}, {.4f, .5f}, {.1f, .8f},
                                       {0, .7f},   {.3f, .4f}, {0, .1f}};
          for (auto &v : shape) {
            v[0] = (ix + v[0] * z) / sx;
            v[1] = (iy + v[1] * z) / sy;
          }
          polygon(shape);
        }
        pen += ph * .9f * scale;
      } else {
        auto &g = font.glyph(cp);
        quad(pen + g.xoff * scale, baseline + g.yoff * scale,
             (g.x1 - g.x0) * scale, (g.y1 - g.y0) * scale,
             float(g.x0) / font.width(), float(g.y0) / font.height(),
             float(g.x1) / font.width(), float(g.y1) / font.height());
        pen += g.advance * scale;
      }
    }
  }
  void polygon(const std::vector<Point> &pts) {
    if (pts.size() >= 3 && visible(pts))
      tessellate({pts}, false);
  }
  void tessellate(const std::vector<std::vector<Point>> &contours, bool unite) {
    // Split at vertices AND intersections: crossing order is fixed per slab.
    // Fill polygons use even-odd parity. Stroke pieces use nonzero winding,
    // with each triangle normalized to the same orientation, giving a union.
    struct Edge { double x, y, dx, dy; int winding; };
    std::vector<Edge> edges;
    std::vector<double> levels;
    for (const auto &pts : contours) {
      double area = 0;
      if (unite) {
        for (size_t i = 0; i < pts.size(); ++i) {
          auto a = pts[i], b = pts[(i + 1) % pts.size()];
          area += double(a[0]) * b[1] - double(a[1]) * b[0];
        }
        if (area == 0)
          continue;
      }
      for (size_t i = 0; i < pts.size(); ++i) {
        auto a = pts[i], b = pts[(i + 1) % pts.size()];
        levels.push_back(a[1]);
        if (a[1] != b[1])
          edges.push_back({a[0], a[1], double(b[0]) - a[0],
                           double(b[1]) - a[1],
                           (b[1] > a[1] ? 1 : -1) * (area < 0 ? -1 : 1)});
      }
    }
    work(edges.size() * (edges.size() ? edges.size() - 1 : 0) / 2);
    for (size_t i = 0; i < edges.size(); ++i)
      for (size_t j = i + 1; j < edges.size(); ++j) {
        auto a = edges[i], b = edges[j];
        double det = a.dx * b.dy - a.dy * b.dx;
        if (det == 0)
          continue;
        double x = b.x - a.x, y = b.y - a.y,
               t = (x * b.dy - y * b.dx) / det,
               u = (x * a.dy - y * a.dx) / det;
        if (t > 0 && t < 1 && u > 0 && u < 1)
          levels.push_back(a.y + t * a.dy);
      }
    work(sortCost(levels.size()));
    std::sort(levels.begin(), levels.end());
    levels.erase(std::unique(levels.begin(), levels.end()), levels.end());
    // Conservative allowance: scan, sort all edges and up to two clipped
    // triangles per crossing. Charge all slabs before processing any of them.
    work((levels.empty() ? 0 : levels.size() - 1) *
         (sortCost(edges.size()) + 32 * edges.size()));
    auto at = [](const Edge &e, double y) {
      return e.x + (y - e.y) * e.dx / e.dy;
    };
    for (size_t i = 1; i < levels.size(); ++i) {
      double lo = levels[i - 1], hi = levels[i], mid = (lo + hi) / 2;
      std::vector<const Edge *> active;
      for (const auto &e : edges)
        if (mid > std::min(e.y, e.y + e.dy) &&
            mid < std::max(e.y, e.y + e.dy))
          active.push_back(&e);
      std::sort(active.begin(), active.end(), [&](auto a, auto b) {
        return at(*a, mid) < at(*b, mid);
      });
      int winding = 0;
      const Edge *l = nullptr;
      for (auto r : active) {
        int next = unite ? winding + r->winding : winding ^ 1;
        if (winding == 0 && next != 0)
          l = r;
        if (winding == 0 || next != 0) {
          winding = next;
          continue;
        }
        winding = next;
        auto a = vertex(float(at(*l, lo)) * sx, float(lo) * sy),
             b = vertex(float(at(*r, lo)) * sx, float(lo) * sy),
             c = vertex(float(at(*r, hi)) * sx, float(hi) * sy),
             d = vertex(float(at(*l, hi)) * sx, float(hi) * sy);
        tri(a, b, c);
        tri(a, c, d);
      }
    }
  }
};
} // namespace
DrawList layout(const Model &m, int width, int height,
                const top_hud::FontAtlas &font) {
  if (width < 1 || height < 1 || width > 32768 || height > 16384 ||
      m.logical_size[0] < 64 || m.logical_size[1] < 64 ||
      m.logical_size[0] > 16384 || m.logical_size[1] > 16384)
    invalid();
  Builder b{{},
            {},
            float(width) / m.logical_size[0],
            float(height) / m.logical_size[1],
            width,
            height,
            font};
  if (!m.active)
    return b.out;
  if (m.fogCells) {
    if (m.fogCells < 1 || m.fogCells > 2048 ||
        m.fogStates.size() != size_t(m.fogCells) * m.fogCells)
      invalid();
    b.out.fogWidth = b.out.fogHeight = m.fogCells;
    for (char s : m.fogStates) {
      if (s < '0' || s > '2')
        invalid();
      Color c = s == '0'   ? Color{3, 6, 13, 255}
                : s == '1' ? Color{12, 22, 38, 155}
                           : Color{12, 22, 38, 0};
      b.out.fogPixels.insert(b.out.fogPixels.end(), c.begin(), c.end());
    }
  }
  for (const auto &o : m.ops) {
    b.clip = intersect({o.clip[0] * b.sx, o.clip[1] * b.sy, o.clip[2] * b.sx,
                        o.clip[3] * b.sy},
                       {0, 0, float(width), float(height)});
    if (b.clip[2] <= 0 || b.clip[3] <= 0)
      continue;
    b.texture = o.kind == "fog" ? 1 : 0;
    b.color = packed(o.color);
    if (o.kind == "text") {
      b.text(o);
    } else if (o.kind == "fog") {
      b.color = 0xffffffff;
      b.quad(o.rect[0] * b.sx, o.rect[1] * b.sy, o.rect[2] * b.sx,
             o.rect[3] * b.sy, 0, 0, 1, 1);
    } else if (o.kind == "rect" && o.radius > 0) {
      b.rounded(o);
    } else if (o.kind == "rect") {
      if (o.stroke == 0)
        b.quad(o.rect[0] * b.sx, o.rect[1] * b.sy, o.rect[2] * b.sx,
               o.rect[3] * b.sy);
      else {
        float x = o.rect[0], y = o.rect[1], w = o.rect[2], h = o.rect[3],
              s = std::min(o.stroke, std::min(w, h) / 2);
        b.quad(x * b.sx, y * b.sy, w * b.sx, s * b.sy);
        b.quad(x * b.sx, (y + h - s) * b.sy, w * b.sx, s * b.sy);
        b.quad(x * b.sx, (y + s) * b.sy, s * b.sx, (h - 2 * s) * b.sy);
        b.quad((x + w - s) * b.sx, (y + s) * b.sy, s * b.sx,
               (h - 2 * s) * b.sy);
      }
    } else if (o.kind == "line") {
      b.segment(o.points.at(0), o.points.at(1), o.stroke);
    } else if (o.kind == "polygon") {
      if (o.stroke == 0)
        b.polygon(o.points);
      else
        b.outline(o.points, o.stroke);
    } else if (o.kind == "ellipse" || o.kind == "circle") {
      float cx = o.kind == "circle" ? o.center[0] : o.rect[0] + o.rect[2] / 2,
            cy = o.kind == "circle" ? o.center[1] : o.rect[1] + o.rect[3] / 2,
            rx = o.kind == "circle" ? o.radius : o.rect[2] / 2,
            ry = o.kind == "circle" ? o.radius : o.rect[3] / 2;
      constexpr int N = 48;
      for (int i = 0; i < N; ++i) {
        float a = float(i) * 6.28318530718f / N,
              c = float(i + 1) * 6.28318530718f / N;
        auto p = b.vertex((cx + rx * std::cos(a)) * b.sx,
                          (cy + ry * std::sin(a)) * b.sy),
             q = b.vertex((cx + rx * std::cos(c)) * b.sx,
                          (cy + ry * std::sin(c)) * b.sy);
        if (o.stroke <= 0)
          b.tri(b.vertex(cx * b.sx, cy * b.sy), p, q);
        else {
          float ix = std::max(0.f, rx - o.stroke),
                iy = std::max(0.f, ry - o.stroke);
          auto r = b.vertex((cx + ix * std::cos(a)) * b.sx,
                            (cy + iy * std::sin(a)) * b.sy),
               s = b.vertex((cx + ix * std::cos(c)) * b.sx,
                            (cy + iy * std::sin(c)) * b.sy);
          b.tri(p, q, s);
          b.tri(p, s, r);
        }
      }
    }
  }
  return b.out;
}
} // namespace armada::vector_hud
