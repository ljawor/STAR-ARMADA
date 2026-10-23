#pragma once
#include "top_hud.hpp"
#include <array>
#include <string>
#include <vector>
namespace armada::vector_hud {
// RGBA bytes; rectangles are {x,y,width,height} in final producer logical
// coordinates (including the producer's side-panel transform).
using Color = std::array<uint8_t, 4>;
using Rect = std::array<float, 4>;
using Point = std::array<float, 2>;
struct Op {
  std::string kind;
  Rect clip{}, rect{}, bounds{};
  Point center{}, pos{};
  std::vector<Point> points;
  Color color{255, 255, 255, 255};
  float stroke = 0, radius = 0, size = 0;
  std::string text, fit;
};
struct Model {
  bool active = false;
  std::array<int, 2> logical_size{800, 600};
  std::vector<Op> ops;
  int fogCells = 0;
  std::string fogStates;
};
struct Batch {
  uint8_t textureKind = 0;
  uint32_t firstIndex = 0, indexCount = 0;
};
struct TextBounds {
  std::string text;
  float x = 0, y = 0, width = 0, height = 0;
};
// Font vertices use top_hud's NDC position/24-byte layout. Texture kind 0 is
// the shared atlas (including its white patch); kind 1 is nearest/clamp fog.
// Batches remain in operation order and are already CPU-clipped.
struct DrawList {
  std::vector<top_hud::Vertex> vertices;
  std::vector<uint16_t> indices;
  std::vector<Batch> batches;
  std::vector<uint8_t> fogPixels;
  int fogWidth = 0, fogHeight = 0;
  std::vector<TextBounds> textBounds;
};
// Untrusted snapshots MUST enter through decode. Malformed snapshots and mesh
// overflow throw std::invalid_argument; callers install only complete results.
// Polygon/stroke tessellation also shares a 4,000,000-unit layout work budget:
// E*(E-1)/2 pair tests, L*ceil(log2 L) sorting units, then (Lunique-1)*
// (E*ceil(log2 E)+32*E) slab units, reserved BEFORE each corresponding phase.
// Off-clip polygon bounds are rejected before intersection processing.
// This allowance is independent of emitted vertices and rejects whole layouts.
// Directly constructed models are trusted test inputs. layout validates
// viewport and logical dimensions even for inactive models. Text bounds are
// drawable px.
Model decode(const std::vector<uint8_t> &);
DrawList layout(const Model &, int drawableWidth, int drawableHeight,
                const top_hud::FontAtlas &);
} // namespace armada::vector_hud
