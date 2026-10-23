#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
namespace armada::top_hud {
using Color = std::array<uint8_t, 3>;
struct Cell {
  std::string label, value, rate;
  Color color{}, rate_color{};
};
struct Model {
  bool active = false;
  std::array<Cell, 5> cells{};
  std::string clock, paused, fps;
};
// Invalid messages throw std::invalid_argument; no partial model is returned.
Model decode(const std::vector<uint8_t> &bytes);
struct Vertex {
  float x, y, z, u, v;
  uint32_t color;
};
static_assert(sizeof(Vertex) == 24, "GPU vertex stride");
struct TextBounds {
  std::string text, role;
  float x, y, width, height;
  int cell = -1;
};
struct Mesh {
  std::vector<Vertex> vertices;
  std::vector<uint16_t> indices;
  std::vector<TextBounds> text_bounds;
  int header_height = 0;
};
struct Glyph {
  int codepoint = 0, x0 = 0, y0 = 0, x1 = 0, y1 = 0;
  float xoff = 0, yoff = 0, advance = 0;
};
class FontAtlas {
public:
  explicit FontAtlas(const std::filesystem::path &pathToFont,
                     int framebufferHeight);
  int width() const { return width_; }
  int height() const { return height_; }
  const std::vector<uint8_t> &pixels() const { return pixels_; }
  const Glyph &glyph(uint32_t codepoint) const;
  float pixel_height() const { return pixel_height_; }
  float measure(const std::string &text, float pixelHeight) const;

private:
  int width_ = 1024, height_ = 1024;
  float pixel_height_ = 0;
  std::vector<uint8_t> pixels_;
  std::vector<Glyph> glyphs_;
};
// Pixel-space debug bounds include complete text advances. UV row zero is top.
// RGBA8 color packs R in bits 0..7, A in bits 24..31 (little-endian upload).
Mesh layout(const Model &, int framebufferWidth, int framebufferHeight,
            const FontAtlas &);
} // namespace armada::top_hud
