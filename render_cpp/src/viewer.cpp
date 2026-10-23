// Standalone W01 viewer: no authoritative game state and no Python runtime.
#include "camera.hpp"
#include "frame_v2.hpp"
#include "emissive.hpp"
#include "explosion.hpp"
#include "fogmap.hpp"
#include "hardware.hpp"
#include "starfield.hpp"
#include "embedded.hpp"
#include "shield.hpp"
#include "hit_effects.hpp"
#include "input_ring.hpp"
#include "marker_ring.hpp"
#include "overlay.hpp"
#include "top_hud.hpp"
#include "vector_hud.hpp"
#include "planets.hpp"
#include "scene.hpp"
#include <SDL3/SDL.h>
#ifdef __APPLE__
#include <SDL3/SDL_metal.h>
#endif
#include <algorithm>
#include <atomic>
#include <bgfx/bgfx.h>
#include <bx/math.h>
#include <chrono>
#include <cstdarg>
#include <cstdio>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <numeric>
#include <optional>
#include <thread>
#include <unordered_map>
namespace fs = std::filesystem;
// `overlay` is also the debug-text toggle's variable name inside main(), which shadows the
// namespace there; a file-scope alias keeps the decoder reachable.
namespace hud = armada::overlay;
namespace input_ring = armada::input;
namespace planets = armada::planet;
namespace cues = armada::marker;
namespace emit = armada::emissive;
namespace fx = armada::fx;
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;

// A small PNG writer using stored DEFLATE blocks. No platform image dependency.
static uint32_t crc(const uint8_t *p, size_t n) {
  uint32_t v = ~0u;
  for (size_t i = 0; i < n; i++) {
    v ^= p[i];
    for (int b = 0; b < 8; b++)
      v = (v >> 1) ^ (0xedb88320u & uint32_t(-int(v & 1)));
  }
  return ~v;
}
static void be32(std::vector<uint8_t> &v, uint32_t n) {
  for (int s = 24; s >= 0; s -= 8)
    v.push_back(uint8_t(n >> s));
}
static void chunk(std::vector<uint8_t> &out, const char *kind,
                  const std::vector<uint8_t> &data) {
  be32(out, uint32_t(data.size()));
  const auto pos = out.size();
  out.insert(out.end(), kind, kind + 4);
  out.insert(out.end(), data.begin(), data.end());
  be32(out, crc(out.data() + pos, data.size() + 4));
}
static void png(const fs::path &path, uint32_t w, uint32_t h, uint32_t pitch,
                const uint8_t *data, bool flip, bool bgra) {
  std::vector<uint8_t> raw;
  raw.reserve(size_t(h) * (1 + 4 * w));
  for (uint32_t y = 0; y < h; y++) {
    raw.push_back(0);
    const auto *row = data + (flip ? h - 1 - y : y) * pitch;
    for (uint32_t x = 0; x < w; x++) {
      raw.push_back(row[4 * x + (bgra ? 2 : 0)]);
      raw.push_back(row[4 * x + 1]);
      raw.push_back(row[4 * x + (bgra ? 0 : 2)]);
      raw.push_back(255);
    }
  }
  std::vector<uint8_t> z{0x78, 0x01};
  uint32_t a = 1, b = 0;
  for (auto v : raw) {
    a = (a + v) % 65521;
    b = (b + a) % 65521;
  }
  for (size_t i = 0; i < raw.size();) {
    const uint16_t n = uint16_t(std::min<size_t>(65535, raw.size() - i));
    z.push_back(i + n == raw.size() ? 1 : 0);
    z.push_back(n & 255);
    z.push_back(n >> 8);
    z.push_back((~n) & 255);
    z.push_back((~n) >> 8);
    z.insert(z.end(), raw.begin() + i, raw.begin() + i + n);
    i += n;
  }
  be32(z, (b << 16) | a);
  std::vector<uint8_t> out{137, 80, 78, 71, 13, 10, 26, 10}, ihdr;
  be32(ihdr, w);
  be32(ihdr, h);
  ihdr.insert(ihdr.end(), {8, 6, 0, 0, 0});
  chunk(out, "IHDR", ihdr);
  chunk(out, "IDAT", z);
  chunk(out, "IEND", {});
  if (!path.parent_path().empty())
    fs::create_directories(path.parent_path());
  std::ofstream f(path, std::ios::binary);
  f.write(reinterpret_cast<char *>(out.data()), std::streamsize(out.size()));
  if (!f)
    throw std::runtime_error("Cannot write PNG: " + path.string());
}
struct DeviceError : std::runtime_error {
  using std::runtime_error::runtime_error;
};
struct Callbacks final : bgfx::CallbackI {
  std::atomic<int> shots{0}, errors{0};
  void fatal(const char *, uint16_t, bgfx::Fatal::Enum,
             const char *msg) override {
    std::fprintf(stderr, "BGFX_FATAL %s\n", msg);
    // Unrecoverable backend callback: do not throw across the driver thread.
    std::fflush(stderr);
    std::_Exit(4);
  }
  void traceVargs(const char *, uint16_t, const char *fmt,
                  va_list args) override {
    std::vfprintf(stderr, fmt, args);
  }
  void profilerBegin(const char *, uint32_t, const char *, uint16_t) override {}
  void profilerBeginLiteral(const char *, uint32_t, const char *,
                            uint16_t) override {}
  void profilerEnd() override {}
  uint32_t cacheReadSize(uint64_t) override { return 0; }
  bool cacheRead(uint64_t, void *, uint32_t) override { return false; }
  void cacheWrite(uint64_t, const void *, uint32_t) override {}
  void screenShot(const char *path, uint32_t w, uint32_t h, uint32_t pitch,
                  bgfx::TextureFormat::Enum format, const void *data, uint32_t,
                  bool flip) override {
    try {
      png(path, w, h, pitch, static_cast<const uint8_t *>(data), flip,
          format == bgfx::TextureFormat::BGRA8);
      shots++;
      std::cout << "SCREENSHOT " << path << " " << w << "x" << h << std::endl;
    } catch (const std::exception &e) {
      errors++;
      std::cerr << e.what() << std::endl;
    }
  }
  void captureBegin(uint32_t, uint32_t, uint32_t, bgfx::TextureFormat::Enum,
                    bool) override {}
  void captureEnd() override {}
  void captureFrame(const void *, uint32_t) override {}
};
struct Options {
  fs::path snapshot, assets, shaders = ARMADA_SHADER_DIR, shot, report, ring, tables, overlayRing,
      inputRing, planetRing, markerRing, emitRing, fogRing, meshRing, cameraRing, fxDemo, topHudRing,
      vectorHudRing;
  std::array<float, 3> focus{};
  bool hasFocus = false;
  // The map's star lights every planet (render/renderer.py sets GL_LIGHT0 to the star position,
  // with y raised to at least 2000 so a system in the ecliptic still has a day side).
  std::array<float, 3> star{0.f, 2000.f, 0.f};
  int inputSlots = 8;
  bool inputExercise = false;
  bool cameraExercise = false;
  bool hudOnly = false;
  int width = 1280, height = 800, frames = 0, warmup = 30, preset = 1, msaa = 4;
  double seconds = 0.0, distance = 0.0, pitch = 0.0, yaw = 0.0;
  // `> 0` cannot express "a level camera" or "yaw 0", so a requested 0 silently fell back to the
  // stock 12/90. NaN means "not given".
  bool pitchGiven = false, yawGiven = false;
  // The whole report on stdout floods the player's terminal (the frame-time sample arrays alone
  // are one float per frame), and nothing reads it: the host never parses the viewer's stdout and
  // the separate-window launcher discards it. `--report` is the file route a tool wants; this is
  // the opt-in for a tool that pipes stdout.
  bool stdoutReport = false;
  bool shadows = true, validate = false, exercise = false,
       // The debug text is a development aid, never part of the game's window: it is off unless a
       // tool asks for it, and the game never asks. `F` used to toggle it and was in the player's
       // way on a key the game already owns.
       overlay = false;
};
static Options options(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; i++) {
    std::string k = argv[i];
    auto value = [&]() {
      if (++i >= argc)
        throw std::runtime_error("Missing value for " + k);
      return std::string(argv[i]);
    };
    if (k == "--snapshot")
      o.snapshot = value();
    else if (k == "--assets")
      o.assets = value();
    else if (k == "--shaders")
      o.shaders = value();
    else if (k == "--screenshot")
      o.shot = value();
    else if (k == "--report")
      o.report = value();
    else if (k == "--frames")
      o.frames = std::stoi(value());
    else if (k == "--ring")
      o.ring = value();
    else if (k == "--tables")
      o.tables = value();
    else if (k == "--overlay-ring")
      o.overlayRing = value();
    else if (k == "--top-hud-ring")
      o.topHudRing = value();
    else if (k == "--vector-hud-ring")
      o.vectorHudRing = value();
    else if (k == "--input-ring")
      o.inputRing = value();
    else if (k == "--planet-ring")
      o.planetRing = value();
    else if (k == "--fog-ring")
      o.fogRing = value();
    else if (k == "--marker-ring")
      o.markerRing = value();
    else if (k == "--mesh-ring")
      o.meshRing = value();
    else if (k == "--emit-ring")
      o.emitRing = value();
    else if (k == "--camera-ring")
      // The game's camera pose, published every frame. With it the window looks where the player
      // looks; without it the window keeps its own camera (every fixture run).
      o.cameraRing = value();
    else if (k == "--fx-demo")
      // Diagnostic only: one detonation in open space at a fixed age and seed, so the port can be
      // compared with the Python reference frame. Not a simulation effect.
      o.fxDemo = value();
    else if (k == "--star") {
      const std::string text = value();
      std::array<float, 3> point{};
      if (std::sscanf(text.c_str(), "%f,%f,%f", &point[0], &point[1], &point[2]) != 3)
        throw std::runtime_error("--star expects x,y,z");
      o.star = point;
    }
    else if (k == "--focus") {
      // Look at a world point rather than the scene's own target: a planet sits tens of thousands
      // of units out, so comparing it against the Python renderer needs the camera aimed at it.
      const std::string text = value();
      std::array<float, 3> point{};
      if (std::sscanf(text.c_str(), "%f,%f,%f", &point[0], &point[1], &point[2]) != 3)
        throw std::runtime_error("--focus expects x,y,z");
      o.focus = point;
      o.hasFocus = true;
    }
    else if (k == "--input-slots")
      o.inputSlots = std::stoi(value());
    else if (k == "--input-exercise")
      o.inputExercise = true;
    else if (k == "--camera-exercise")
      o.cameraExercise = true;
    else if (k == "--hud-only")
      o.hudOnly = true;
    else if (k == "--seconds")
      o.seconds = std::stod(value());
    else if (k == "--distance")
      o.distance = std::stod(value());
    else if (k == "--pitch") {
      o.pitch = std::stod(value());
      o.pitchGiven = true;
    } else if (k == "--yaw") {
      o.yaw = std::stod(value());
      o.yawGiven = true;
    } else if (k == "--warmup")
      o.warmup = std::stoi(value());
    else if (k == "--width")
      o.width = std::stoi(value());
    else if (k == "--height")
      o.height = std::stoi(value());
    else if (k == "--preset")
      o.preset = std::stoi(value());
    else if (k == "--msaa")
      o.msaa = std::stoi(value());
    else if (k == "--no-shadows")
      o.shadows = false;
    else if (k == "--debug-overlay")
      o.overlay = true;
    else if (k == "--no-overlay")
      o.overlay = false; // Retain the existing diagnostic launchers' explicit opt-out.
    else if (k == "--stdout-report")
      o.stdoutReport = true;
    else if (k == "--validate-only")
      o.validate = true;
    else if (k == "--exercise-controls")
      o.exercise = true;
    else if (k == "--help") {
      std::cout
          << "armada_viewer --snapshot scene.snap --assets assets [--frames "
             "180 --report timing.json --screenshot fleet.png]\nMouse drag "
             "orbit | wheel zoom | WASD pan | 1 fleet | 2 capital | 3 station "
             "| S screenshot | H shadows | Esc quit\n"
             "Live mode: --ring ring.bin [--tables ring.bin.tables] [--seconds 10]\n"
             "HUD (W03): --overlay-ring hud.bin  (the Python producer publishes the composed "
             "HUD surface; dirty rects only after the first frame; the window waits for a "
             "full frame so a late attach never shows a half-texture)\n"
             "           --hud-only draws only that quad, unblended, so --screenshot is the HUD "
             "texture's own pixels (bgfx screenshots a swapchain only, never a render target)\n"
             "Input (W04): --input-ring input.bin [--input-slots 8] publishes the window's "
             "pointer and keyboard events as ARMINP01 batches for the simulation to consume; "
             "the window still decides nothing\n"
             "           --input-exercise pushes a scripted click/key sequence through the real "
             "SDL pump so the return path can be replayed end to end (synthetic input, labelled "
             "as such in the report)\n"
             "Planets (W05): --planet-ring planets.bin carries one ARMPLN01 texture per distinct "
             "planet; the body itself is drawn from the frame instance whose binding names that "
             "texture, scaled by the planet's radius\n"
             "Report (stdout): --stdout-report prints the whole JSON report as ONE line before "
             "exit. Off by default: it is a diagnostic dump, the game's window inherits stdout, "
             "and the frame-time sample arrays are one float per frame. Use --report for a file.\n";
      std::exit(0);
    } else
      throw std::runtime_error("Unknown option: " + k);
  }
  if (o.snapshot.empty() || o.assets.empty())
    throw std::runtime_error("--snapshot and --assets are required");
  if (o.width < 320 || o.height < 240 || o.width > 7680 || o.height > 4320 ||
      o.frames < 0 || o.warmup < 0 || o.preset < 1 || o.preset > 3 ||
      (o.msaa != 0 && o.msaa != 4) || o.seconds < 0.0 || o.inputSlots < 1 ||
      o.inputSlots > 4096)
    throw std::runtime_error("Invalid viewer limits");
  return o;
}
// SDL keycode -> the bridge's own key code. Printable keys keep their ASCII value, so a letter
// is the same number on both sides; everything else is one of the shared input::kKey constants.
// Returns 0 for a key the simulation has no business seeing.
static uint16_t wireKey(SDL_Keycode key) {
  if (key >= 0x20 && key <= 0x7E)
    return uint16_t(key);
  switch (key) {
  case SDLK_ESCAPE: return input_ring::kCodeEscape;
  case SDLK_RETURN: return input_ring::kCodeReturn;
  case SDLK_KP_ENTER: return input_ring::kCodeReturn;
  case SDLK_TAB: return input_ring::kCodeTab;
  case SDLK_BACKSPACE: return input_ring::kCodeBackspace;
  case SDLK_DELETE: return input_ring::kCodeDelete;
  case SDLK_INSERT: return input_ring::kCodeInsert;
  case SDLK_SPACE: return input_ring::kCodeSpace;
  case SDLK_LEFT: return input_ring::kCodeLeft;
  case SDLK_RIGHT: return input_ring::kCodeRight;
  case SDLK_UP: return input_ring::kCodeUp;
  case SDLK_DOWN: return input_ring::kCodeDown;
  case SDLK_HOME: return input_ring::kCodeHome;
  case SDLK_END: return input_ring::kCodeEnd;
  case SDLK_PAGEUP: return input_ring::kCodePageUp;
  case SDLK_PAGEDOWN: return input_ring::kCodePageDown;
  case SDLK_LSHIFT: return input_ring::kCodeLShift;
  case SDLK_RSHIFT: return input_ring::kCodeRShift;
  case SDLK_LCTRL: return input_ring::kCodeLCtrl;
  case SDLK_RCTRL: return input_ring::kCodeRCtrl;
  case SDLK_LALT: return input_ring::kCodeLAlt;
  case SDLK_RALT: return input_ring::kCodeRAlt;
  case SDLK_F1: return input_ring::kCodeF1;
  case SDLK_F2: return uint16_t(input_ring::kCodeF1 + 1);
  case SDLK_F3: return uint16_t(input_ring::kCodeF1 + 2);
  case SDLK_F4: return uint16_t(input_ring::kCodeF1 + 3);
  case SDLK_F5: return uint16_t(input_ring::kCodeF1 + 4);
  case SDLK_F6: return uint16_t(input_ring::kCodeF1 + 5);
  case SDLK_F7: return uint16_t(input_ring::kCodeF1 + 6);
  case SDLK_F8: return uint16_t(input_ring::kCodeF1 + 7);
  case SDLK_F9: return uint16_t(input_ring::kCodeF1 + 8);
  case SDLK_F10: return uint16_t(input_ring::kCodeF1 + 9);
  case SDLK_F11: return uint16_t(input_ring::kCodeF1 + 10);
  case SDLK_F12: return uint16_t(input_ring::kCodeF1 + 11);
  default: return 0;
  }
}

static uint8_t wireMod(SDL_Keymod mod) {
  uint8_t bits = 0;
  if (mod & SDL_KMOD_LSHIFT) bits |= input_ring::kModShiftLeft;
  if (mod & SDL_KMOD_RSHIFT) bits |= input_ring::kModShiftRight;
  if (mod & SDL_KMOD_CTRL) bits |= input_ring::kModCtrl;
  if (mod & SDL_KMOD_ALT) bits |= input_ring::kModAlt;
  if (mod & SDL_KMOD_GUI) bits |= input_ring::kModGui;
  return bits;
}

// W05: a unit sphere with equirectangular texture coordinates. The Python renderer draws planets
// as textured spheres; this is the same body, built once, so a planet costs a matrix and a bind
// rather than a mesh load.
struct Sphere {
  std::vector<float> vertices;      // pos(3) normal(3) uv(2)
  std::vector<uint16_t> indices;
};

static Sphere unitSphere(int segments = 48, int rings = 24) {
  Sphere sphere;
  for (int ring = 0; ring <= rings; ++ring) {
    const float v = float(ring) / float(rings);
    const float phi = v * float(M_PI);
    for (int segment = 0; segment <= segments; ++segment) {
      const float u = float(segment) / float(segments);
      const float theta = u * 2.f * float(M_PI);
      const float nx = std::sin(phi) * std::cos(theta);
      const float ny = std::cos(phi);
      const float nz = std::sin(phi) * std::sin(theta);
      sphere.vertices.insert(sphere.vertices.end(), {nx, ny, nz, nx, ny, nz, u, 1.f - v});
    }
  }
  const int stride = segments + 1;
  for (int ring = 0; ring < rings; ++ring) {
    for (int segment = 0; segment < segments; ++segment) {
      const uint16_t a = uint16_t(ring * stride + segment);
      const uint16_t b = uint16_t(a + 1);
      const uint16_t c = uint16_t(a + stride);
      const uint16_t d = uint16_t(c + 1);
      sphere.indices.insert(sphere.indices.end(), {a, c, b, b, c, d});
    }
  }
  return sphere;
}

// W05: the planet textures the window holds, keyed by the name the frame binding carries.
struct PlanetTextures {
  std::unordered_map<std::string, bgfx::TextureHandle> byName;
  bgfx::TextureHandle fallback = BGFX_INVALID_HANDLE;
  size_t uploaded = 0, reused = 0, failures = 0, bytes = 0;

  bool apply(const armada::planet::Blob &blob) {
    if (byName.count(blob.name)) {
      ++reused;
      return false;
    }
    const uint32_t count = uint32_t(blob.width) * uint32_t(blob.height) * 4u;
    const bgfx::Memory *memory = bgfx::copy(blob.rgba, count);
    const bgfx::TextureHandle handle = bgfx::createTexture2D(
        blob.width, blob.height, false, 1, bgfx::TextureFormat::RGBA8,
        // Linear minification/magnification is the default; only clamp V, because an
        // equirectangular texture has to wrap across the seam at U = 0/1.
        BGFX_SAMPLER_V_CLAMP,
        memory);
    if (!bgfx::isValid(handle)) {
      ++failures;
      return false;
    }
    byName.emplace(blob.name, handle);
    ++uploaded;
    bytes += count;
    return true;
  }

  bgfx::TextureHandle handleFor(const std::string &name) const {
    const auto it = byName.find(name);
    return it == byName.end() ? fallback : it->second;
  }

  void destroy() {
    for (auto &entry : byName)
      if (bgfx::isValid(entry.second))
        bgfx::destroy(entry.second);
    byName.clear();
    if (bgfx::isValid(fallback))
      bgfx::destroy(fallback);
    fallback = BGFX_INVALID_HANDLE;
  }
};

// W05 slice 2: ownership cues. The shapes are the Python ones (render/markers.py), copied rather
// than approximated because a chevron that reads as a house is a different cue.
struct CueVertex {
  float x, y, z, r, g, b, a;
};

static const float kChevronPts[6][2] = {{-1.00f, 0.62f}, {-0.46f, 0.62f}, {0.00f, -0.18f},
                                       {0.46f, 0.62f}, {1.00f, 0.62f}, {0.00f, -1.00f}};
static const float kDiamondPts[6][2] = {{0.00f, 1.00f}, {0.72f, 0.20f}, {0.72f, -0.20f},
                                       {0.00f, -1.00f}, {-0.72f, -0.20f}, {-0.72f, 0.20f}};

static void pushCue(std::vector<CueVertex> &out, const float *point,
                    const std::array<uint8_t, 4> &colour) {
  out.push_back({point[0], point[1], point[2], colour[0] / 255.f, colour[1] / 255.f,
                 colour[2] / 255.f, colour[3] / 255.f});
}

// bgfx has no line width, so a 1 px line is the only line it can draw — and a 1 px selection ring
// beside Python's 2-3 px ring reads as a different cue, not a thinner one. Line segments are
// therefore widened into screen-aligned quads on the CPU: the offset is perpendicular to the
// segment inside the camera plane, `halfWorld` wide, and callers size it from the segment's own
// depth so the result is a constant number of pixels at any zoom.
static void pushThickSegment(std::vector<CueVertex> &out, const float *a, const float *b,
                             const std::array<uint8_t, 4> &colour, float halfWorld,
                             const float *forward) {
  const float dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
  float px = dy * forward[2] - dz * forward[1];
  float py = dz * forward[0] - dx * forward[2];
  float pz = dx * forward[1] - dy * forward[0];
  const float len = std::sqrt(px * px + py * py + pz * pz);
  if (!(len > 1e-6f))
    return;                       // a zero-length segment has no direction to widen along
  px *= halfWorld / len;
  py *= halfWorld / len;
  pz *= halfWorld / len;
  const float a0[3] = {a[0] + px, a[1] + py, a[2] + pz};
  const float a1[3] = {a[0] - px, a[1] - py, a[2] - pz};
  const float b0[3] = {b[0] + px, b[1] + py, b[2] + pz};
  const float b1[3] = {b[0] - px, b[1] - py, b[2] - pz};
  pushCue(out, a0, colour); pushCue(out, a1, colour); pushCue(out, b1, colour);
  pushCue(out, a0, colour); pushCue(out, b1, colour); pushCue(out, b0, colour);
}

static bgfx::ShaderHandle shader(const fs::path &p) {
  std::ifstream f(p, std::ios::binary | std::ios::ate);
  if (!f)
    throw DeviceError("Missing shader: " + p.string());
  auto n = f.tellg();
  if (n <= 0 || n > 4 * 1024 * 1024)
    throw DeviceError("Invalid shader size");
  auto *m = bgfx::alloc(uint32_t(n));
  f.seekg(0);
  f.read(reinterpret_cast<char *>(m->data), n);
  auto h = bgfx::createShader(m);
  if (!bgfx::isValid(h))
    throw DeviceError("Shader rejected: " + p.string());
  return h;
}
struct Group {
  armada::Mesh mesh;
  bgfx::VertexBufferHandle vbo = BGFX_INVALID_HANDLE;
  std::vector<float> instances;
};
static Json stats(std::vector<double> v) {
  if (v.empty())
    return Json{{"samples", 0}};
  double sum = std::accumulate(v.begin(), v.end(), 0.0);
  std::sort(v.begin(), v.end());
  auto pct = [&](double q) { return v[size_t(std::ceil(q * v.size())) - 1]; };
  return Json{{"samples", v.size()},
              {"mean_ms", sum / v.size()},
              {"median_ms", pct(.5)},
              {"p95_ms", pct(.95)},
              {"p99_ms", pct(.99)}};
}
struct Cleanup {
  std::vector<std::function<void()>> actions;
  void run() noexcept {
    for (auto it = actions.rbegin(); it != actions.rend(); ++it) {
      try {
        (*it)();
      } catch (...) {
      }
    }
    actions.clear();
  }
  ~Cleanup() { run(); }
};
// Live mode: the same draw path as the offline scene, but the instances come from the
// producer's ring every frame instead of from the snapshot.
struct Live {
  armada::bridge::RingReader reader;
  armada::bridge::Tables tables;
  std::unordered_map<std::string, size_t> group_of;
  std::optional<armada::bridge::Frame> previous, current;
  uint64_t previous_sequence = 0, current_sequence = 0;
  std::chrono::steady_clock::time_point current_at{};
  bool have_current_at = false;
  double period = 1.0 / 60.0;
  uint64_t adopted = 0, dropped = 0, decode_failures = 0, empty_draws = 0;
  std::vector<double> decode_ms, age_frames, alphas;
  //: W05 planet bodies for this frame: texture name, world position, radius.
  struct PlanetBody {
    std::string texture;
    std::array<float, 3> position{};
    float radius = 1.f;
    bool atmosphere = true;   // the Python renderer lights a barren planet without a shell
  };
  std::vector<PlanetBody> planets;
  size_t planet_pose_failures = 0;
  //: W05 surface hardware for this frame. Its binding names a mesh the producer published, and its
  //: matrix is used as given: a building does not move, so there is nothing to interpolate.
  struct SurfaceInstance {
    std::string binding;
    std::array<float, 12> matrix{};
    std::array<uint8_t, 4> tint{255, 255, 255, 255};
  };
  std::vector<SurfaceInstance> surface;
  size_t surface_unmeshed = 0;

  Live(const fs::path &ring_path, const fs::path &tables_path,
       const std::vector<Group> &groups)
      : reader(ring_path), tables(armada::bridge::Tables::parse(
            [&] {
              std::ifstream in(tables_path, std::ios::binary | std::ios::ate);
              if (!in)
                throw armada::bridge::FrameError(
                    "table file missing: " + tables_path.string());
              const auto size = in.tellg();
              std::vector<uint8_t> bytes(static_cast<size_t>(size));
              in.seekg(0);
              if (!bytes.empty())
                in.read(reinterpret_cast<char *>(bytes.data()), size);
              return bytes;
            }())) {
    for (size_t i = 0; i < groups.size(); ++i)
      group_of.emplace(groups[i].mesh.binding, i);
  }

  // Adopt the newest complete frame if it is new, then write interpolated instances into
  // the draw groups. Returns false when nothing has been published yet.
  bool step(std::vector<Group> &groups) {
    std::vector<uint8_t> bytes;
    uint64_t sequence = 0;
    const auto started = Clock::now();
    if (!reader.latest(bytes, &sequence))
      return false;
    if (!current || sequence != current_sequence) {
      try {
        auto frame = armada::bridge::decode(bytes, tables);
        decode_ms.push_back(std::chrono::duration<double, std::milli>(
                                Clock::now() - started)
                                .count());
        previous = std::move(current);
        previous_sequence = current_sequence;
        current = std::move(frame);
        const uint64_t skipped = current_sequence == 0 && !previous
                                     ? 0
                                     : reader.dropped_since(current_sequence);
        dropped += skipped;
        current_sequence = sequence;
        const auto now = Clock::now();
        if (have_current_at) {
          const double delta = std::chrono::duration<double>(now - current_at).count();
          if (delta > 0.0005 && delta < 0.5)
            period = period * 0.8 + delta * 0.2;
        }
        current_at = now;
        have_current_at = true;
        ++adopted;
      } catch (const armada::bridge::FrameError &) {
        ++decode_failures;
        return false;
      }
    }
    const double elapsed =
        have_current_at ? std::chrono::duration<double>(Clock::now() - current_at).count()
                        : 0.0;
    const float alpha = float(std::clamp(elapsed / period, 0.0, 1.0));
    alphas.push_back(alpha);

    for (auto &group : groups)
      group.instances.clear();
    std::unordered_map<uint32_t, const armada::bridge::Instance *> old;
    if (previous)
      for (const auto &record : previous->instances)
        old.emplace(record.entity_id, &record);

    std::vector<float> scratch(20);
    planets.clear();
    surface.clear();
    for (const auto &record : current->instances) {
      const std::string &binding = tables.bindings.at(record.binding_id);
      if ((record.flags & (armada::bridge::kFlagSurfaceFrame |
                           armada::bridge::kFlagDynamicMesh)) != 0) {
        // Verbatim: the frame's 12 floats are the surface basis the producer computed.
        surface.push_back({binding, record.matrix, record.tint});
        continue;
      }
      // W05: a planet is not a mesh. Its binding names the texture the window already holds, and
      // the instance matrix is its position and radius, so it is collected instead of grouped.
      if (planets::isPlanetBinding(binding)) {
        try {
          const auto pose = armada::bridge::pose_from_matrix(record.matrix);
          const std::string kind = planets::planetKind(binding);
          planets.push_back({planets::planetTextureName(binding),
                             {pose.position[0], pose.position[1], pose.position[2]},
                             pose.scale, kind != "barren"});
        } catch (const armada::bridge::FrameError &) {
          ++planet_pose_failures;
        }
        continue;
      }
      const auto it = group_of.find(binding);
      if (it == group_of.end())
        continue;
      auto pose = armada::bridge::pose_from_matrix(record.matrix);
      if (const auto prior = old.find(record.entity_id); prior != old.end()) {
        try {
          const auto before = armada::bridge::pose_from_matrix(prior->second->matrix);
          pose.yaw = armada::bridge::lerp_angle(before.yaw, pose.yaw, alpha);
          pose.scale = before.scale + (pose.scale - before.scale) * alpha;
          for (size_t axis = 0; axis < 3; ++axis)
            pose.position[axis] =
                before.position[axis] + (pose.position[axis] - before.position[axis]) * alpha;
        } catch (const armada::bridge::FrameError &) {
          // keep the newest pose when the older record cannot be decomposed
        }
      }
      armada::bridge::write_instance(scratch.data(), pose, record.tint);
      auto &target = groups[it->second].instances;
      target.insert(target.end(), scratch.begin(), scratch.end());
    }
    return true;
  }

  // How many frames the producer advanced while this one was being drawn: the gate is
  // stated in frames, so this is the number it is stated against.
  void after_frame() {
    if (!current)
      return;
    const uint64_t available = reader.published();
    if (available > current_sequence)
      age_frames.push_back(double(available - 1 - current_sequence));
    else
      age_frames.push_back(0.0);
  }
};

static int run(const Options &o, EmbeddedState *host = nullptr) {
  Callbacks callback;
  Cleanup cleanup;
  auto scene = armada::read_snapshot(o.snapshot, 1);
  armada::validate_world(scene);
  std::vector<Group> groups;
  size_t triangles = 0, drawnTriangles = 0;
  for (const auto &a : scene.at("assets")) {
    Group g;
    g.mesh = armada::load_mesh(o.assets, a);
    triangles += g.mesh.triangles;
    const std::string binding = a.at("binding");
    for (const auto &e : scene.at("instances")) {
      if (e.at("binding") != binding)
        continue;
      const float y = e.at("yaw"), s = e.at("scale"), c = std::cos(y) * s,
                  t = std::sin(y) * s;
      auto p = e.at("position").get<std::array<float, 3>>();
      auto tint = e.at("tint").get<std::array<float, 4>>();
      float d[20] = {c,    0, -t,      0,       0,       s,      0,
                     0,    t, 0,       c,       0,       p[0],   p[1],
                     p[2], 1, tint[0], tint[1], tint[2], tint[3]};
      g.instances.insert(g.instances.end(), d, d + 20);
      drawnTriangles += g.mesh.triangles;
    }
    groups.push_back(std::move(g));
  }
  std::optional<Live> live;
  if (!o.ring.empty()) {
    const fs::path tables = o.tables.empty() ? fs::path(o.ring.string() + ".tables") : o.tables;
    live.emplace(o.ring, tables, groups);
    if (o.snapshot.empty())
      throw std::runtime_error("live mode still needs --snapshot for the mesh catalogue");
  }
  Json report{{"profile", live ? "W02-live-ring" : "W01-offline-mesh-only"},
              {"fixture", scene.at("fixture")},
              {"state_sha256", scene.at("state_sha256")},
              {"metadata", scene.value("metadata", Json::object())},
              {"snapshot_sha256",
               picosha2::hash256_hex_string(armada::read_bytes(o.snapshot))},
              {"unique_meshes", groups.size()},
              {"unique_triangles", triangles},
              {"snapshot_instances", scene.at("instances").size()},
              {"submitted_triangles_per_pass", drawnTriangles},
              {"full_game_performance", false},
              {"quality",
               {{"msaa_requested", o.msaa},
                {"shadow_map", o.shadows ? 2048 : 0},
                {"all_mesh_roles", true},
                {"mesh_lod", false}}}};
  if (o.validate) {
    std::cout << report.dump(2) << "\nVALIDATE_OK\n";
    if (!o.report.empty()) {
      if (!o.report.parent_path().empty())
        fs::create_directories(o.report.parent_path());
      std::ofstream(o.report) << report.dump(2) << '\n';
    }
    return 0;
  }
  SDL_Window *window = nullptr;
  void *nativeWindow = nullptr;
  if (!host) {
  if (!SDL_Init(SDL_INIT_VIDEO))
    throw DeviceError(SDL_GetError());
  cleanup.actions.push_back([] { SDL_Quit(); });
  window = SDL_CreateWindow(
      "STAR ARMADA | W01 offline native viewer", o.width, o.height,
      SDL_WINDOW_RESIZABLE
#ifdef __APPLE__
          | SDL_WINDOW_METAL
#endif
  );
  if (!window)
    throw DeviceError(SDL_GetError());
  cleanup.actions.push_back([window] { SDL_DestroyWindow(window); });
#ifdef __APPLE__
  SDL_MetalView metal = SDL_Metal_CreateView(window);
  if (!metal)
    throw DeviceError(SDL_GetError());
  cleanup.actions.push_back([metal] { SDL_Metal_DestroyView(metal); });
  nativeWindow = SDL_Metal_GetLayer(metal);
#elif defined(_WIN32)
  nativeWindow =
      SDL_GetPointerProperty(SDL_GetWindowProperties(window),
                             SDL_PROP_WINDOW_WIN32_HWND_POINTER, nullptr);
#else
#error "W01 currently targets macOS and Windows"
#endif
  }
  bgfx::renderFrame();
  bgfx::Init init;
  init.callback = &callback;
  init.fallback = false;
#ifdef __APPLE__
  init.type = bgfx::RendererType::Metal;
#else
  init.type = bgfx::RendererType::Direct3D12;
#endif
  int pixelWidth = o.width, pixelHeight = o.height;
  if (!host) SDL_GetWindowSizeInPixels(window, &pixelWidth, &pixelHeight);
  init.swapChain.nwh = nativeWindow;
  init.swapChain.width = host ? 0 : pixelWidth;
  init.swapChain.height = host ? 0 : pixelHeight;
  init.swapChain.flags =
      o.msaa == 4 ? BGFX_SWAP_CHAIN_MSAA_X4 : BGFX_SWAP_CHAIN_NONE;
  if (!bgfx::init(init))
    throw DeviceError("bgfx initialization failed (requested native "
                      "backend, no silent fallback)");
  cleanup.actions.push_back([] { bgfx::shutdown(); });
  bgfx::FrameBufferHandle outputFB = BGFX_INVALID_HANDLE;
  bgfx::TextureHandle outputColor = BGFX_INVALID_HANDLE, outputRead = BGFX_INVALID_HANDLE;
  if (host) {
    const uint64_t samples = o.msaa == 4 ? BGFX_TEXTURE_RT_MSAA_X4 : BGFX_TEXTURE_RT;
    outputColor = bgfx::createTexture2D(pixelWidth, pixelHeight, false, 1,
                                      bgfx::TextureFormat::BGRA8, samples);
    const auto outputDepth = bgfx::createTexture2D(pixelWidth, pixelHeight, false, 1,
                                   bgfx::TextureFormat::D24S8, samples | BGFX_TEXTURE_RT_WRITE_ONLY);
    const bgfx::TextureHandle attachments[] = {outputColor, outputDepth};
    outputFB = bgfx::createFrameBuffer(2, attachments, true);
    outputRead = bgfx::createTexture2D(pixelWidth, pixelHeight, false, 1,
                     bgfx::TextureFormat::BGRA8, BGFX_TEXTURE_BLIT_DST | BGFX_TEXTURE_READ_BACK);
    if (!bgfx::isValid(outputColor) || !bgfx::isValid(outputFB) || !bgfx::isValid(outputRead))
      throw DeviceError("Embedded render target creation failed");
    cleanup.actions.push_back([outputFB] { bgfx::destroy(outputFB); });
    cleanup.actions.push_back([outputRead] { bgfx::destroy(outputRead); });
    host->pixels.resize(size_t(pixelWidth) * pixelHeight * 4);
    bgfx::setViewFrameBuffer(1, outputFB);
    bgfx::setViewFrameBuffer(2, outputFB);
    bgfx::setViewFrameBuffer(3, outputFB);
    bgfx::setViewFrameBuffer(4, outputFB);
  }
  // Instancing is baseline in this pinned bgfx API; buffer availability is
  // checked per draw.
  report["backend"] = bgfx::getRendererName(bgfx::getRendererType());
  report["gpu_vendor_id"] = bgfx::getCaps()->vendorId;
  report["gpu_device_id"] = bgfx::getCaps()->deviceId;
  report["drawable"] = {pixelWidth, pixelHeight};
  report["vsync"] = false;
  bgfx::VertexLayout layout;
  layout.begin()
      .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::Normal, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::Color0, 4, bgfx::AttribType::Float)
      .add(bgfx::Attrib::Color1, 1, bgfx::AttribType::Float)
      .end();
  if (sizeof(armada::Vertex) != layout.getStride())
    throw std::runtime_error("Vertex layout mismatch");
  for (auto &g : groups) {
    g.vbo = bgfx::createVertexBuffer(
        bgfx::copy(g.mesh.vertices.data(),
                   uint32_t(g.mesh.vertices.size() * sizeof(armada::Vertex))),
        layout);
    if (!bgfx::isValid(g.vbo))
      throw DeviceError("GPU mesh upload failed");
    const auto handle = g.vbo;
    cleanup.actions.push_back([handle] { bgfx::destroy(handle); });
  }
  auto program = bgfx::createProgram(shader(o.shaders / "vs_fleet.bin"),
                                     shader(o.shaders / "fs_fleet.bin"), true);
  if (!bgfx::isValid(program))
    throw DeviceError("Fleet program creation failed");
  cleanup.actions.push_back([program] { bgfx::destroy(program); });
  auto shadowProgram =
      bgfx::createProgram(shader(o.shaders / "vs_shadow.bin"),
                          shader(o.shaders / "fs_shadow.bin"), true);
  if (!bgfx::isValid(shadowProgram))
    throw DeviceError("Shadow program creation failed");
  cleanup.actions.push_back([shadowProgram] { bgfx::destroy(shadowProgram); });
  // W03: the HUD is a texture drawn as one fullscreen quad over the world. It carries display
  // colours with straight alpha, so the pass disables depth and blends src-alpha/one-minus-src-alpha.
  struct UiVertex {
    float x, y, z, u, v;
  };
  auto uiProgram = bgfx::createProgram(shader(o.shaders / "vs_ui.bin"),
                                       shader(o.shaders / "fs_ui.bin"), true);
  if (!bgfx::isValid(uiProgram))
    throw DeviceError("UI program creation failed");
  cleanup.actions.push_back([uiProgram] { bgfx::destroy(uiProgram); });
  bgfx::VertexLayout uiLayout;
  uiLayout.begin()
      .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
      .end();
  // Texture row 0 is the surface's top row (bgfx uploads rows in the order given), so v = 0 is the
  // top of the HUD and the quad puts v = 0 at NDC y = +1.
  const UiVertex uiVertices[4] = {{-1.f, -1.f, 0.f, 0.f, 1.f},
                                  {1.f, -1.f, 0.f, 1.f, 1.f},
                                  {1.f, 1.f, 0.f, 1.f, 0.f},
                                  {-1.f, 1.f, 0.f, 0.f, 0.f}};
  const bgfx::VertexBufferHandle uiVbo = bgfx::createVertexBuffer(
      bgfx::copy(uiVertices, sizeof(uiVertices)), uiLayout);
  if (!bgfx::isValid(uiVbo))
    throw DeviceError("UI vertex buffer creation failed");
  cleanup.actions.push_back([uiVbo] { bgfx::destroy(uiVbo); });
  static const uint16_t uiIndices[6] = {0, 1, 2, 0, 2, 3};
  const bgfx::IndexBufferHandle uiIbo =
      bgfx::createIndexBuffer(bgfx::copy(uiIndices, sizeof(uiIndices)));
  if (!bgfx::isValid(uiIbo))
    throw DeviceError("UI index buffer creation failed");
  cleanup.actions.push_back([uiIbo] { bgfx::destroy(uiIbo); });
  const bgfx::UniformHandle uiSampler =
      bgfx::createUniform("s_overlay", bgfx::UniformType::Sampler);
  if (!bgfx::isValid(uiSampler))
    throw DeviceError("UI sampler creation failed");
  cleanup.actions.push_back([uiSampler] { bgfx::destroy(uiSampler); });
  // The upper HUD is native measured text/geometry, not an enlarged Python surface.
  // View 2 is below view 3's remaining HUD/application overlays and above the world.
  bgfx::VertexLayout topLayout;
  topLayout.begin().add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
      .add(bgfx::Attrib::Color0, 4, bgfx::AttribType::Uint8, true).end();
  if (topLayout.getStride() != sizeof(armada::top_hud::Vertex))
    throw DeviceError("Native HUD vertex layout mismatch");
  bgfx::ProgramHandle topProgram = BGFX_INVALID_HANDLE;
  bgfx::UniformHandle topSampler = BGFX_INVALID_HANDLE;
  if (!o.topHudRing.empty() || !o.vectorHudRing.empty()) {
    topProgram = bgfx::createProgram(shader(o.shaders / "vs_top_hud.bin"),
                                    shader(o.shaders / "fs_top_hud.bin"), true);
    if (!bgfx::isValid(topProgram)) throw DeviceError("Native HUD program creation failed");
    cleanup.actions.push_back([topProgram] { bgfx::destroy(topProgram); });
    topSampler = bgfx::createUniform("s_top_hud", bgfx::UniformType::Sampler);
    if (!bgfx::isValid(topSampler)) throw DeviceError("Native HUD sampler creation failed");
    cleanup.actions.push_back([topSampler] { bgfx::destroy(topSampler); });
  }
  // W05 planet pass: sphere geometry, one program, one texture table fed by the planet ring.
  Sphere sphere = unitSphere();
  bgfx::VertexLayout planetLayout;
  planetLayout.begin()
      .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::Normal, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
      .end();
  const bgfx::VertexBufferHandle sphereVbo = bgfx::createVertexBuffer(
      bgfx::copy(sphere.vertices.data(), uint32_t(sphere.vertices.size() * sizeof(float))),
      planetLayout);
  const bgfx::IndexBufferHandle sphereIbo = bgfx::createIndexBuffer(
      bgfx::copy(sphere.indices.data(), uint32_t(sphere.indices.size() * sizeof(uint16_t))));
  if (!bgfx::isValid(sphereVbo) || !bgfx::isValid(sphereIbo))
    throw DeviceError("Planet sphere buffer creation failed");
  cleanup.actions.push_back([sphereVbo] { bgfx::destroy(sphereVbo); });
  cleanup.actions.push_back([sphereIbo] { bgfx::destroy(sphereIbo); });
  const bgfx::ProgramHandle planetProgram =
      bgfx::createProgram(shader(o.shaders / "vs_planet.bin"),
                          shader(o.shaders / "fs_planet.bin"), true);
  if (!bgfx::isValid(planetProgram))
    throw DeviceError("Planet program creation failed");
  cleanup.actions.push_back([planetProgram] { bgfx::destroy(planetProgram); });
  const bgfx::UniformHandle planetSampler =
      bgfx::createUniform("s_planet", bgfx::UniformType::Sampler);
  const bgfx::UniformHandle planetModel =
      bgfx::createUniform("u_planet_model", bgfx::UniformType::Mat4);
  const bgfx::UniformHandle planetFlags =
      bgfx::createUniform("u_planet_flags", bgfx::UniformType::Vec4);
  const bgfx::UniformHandle planetStar =
      bgfx::createUniform("u_star", bgfx::UniformType::Vec4);
  for (auto handle : {planetSampler, planetModel, planetFlags, planetStar}) {
    if (!bgfx::isValid(handle))
      throw DeviceError("Planet uniform creation failed");
    cleanup.actions.push_back([handle] { bgfx::destroy(handle); });
  }
  // W05 slice 2: unlit cue pass - world-space lines and billboards the game already decided.
  bgfx::VertexLayout cueLayout;
  cueLayout.begin()
      .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::Color0, 4, bgfx::AttribType::Float)
      .end();
  const bgfx::ProgramHandle cueProgram =
      bgfx::createProgram(shader(o.shaders / "vs_mark.bin"),
                          shader(o.shaders / "fs_mark.bin"), true);
  if (!bgfx::isValid(cueProgram))
    throw DeviceError("Cue program creation failed");
  cleanup.actions.push_back([cueProgram] { bgfx::destroy(cueProgram); });

  // Camera-translation-free soft points at far depth; never painted over the world.
  const auto starVerts = armada::sky::buildStarfield();
  bgfx::VertexLayout starLayout;
  starLayout.begin().add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
      .add(bgfx::Attrib::Color0, 4, bgfx::AttribType::Uint8, true)
      .add(bgfx::Attrib::Color1, 1, bgfx::AttribType::Float).end();
  if (starLayout.getStride() != sizeof(armada::sky::StarVertex))
    throw DeviceError("Star layout mismatch");
  const auto starProgram = bgfx::createProgram(shader(o.shaders / "vs_star.bin"),
                                              shader(o.shaders / "fs_star.bin"), true);
  const auto starViewport = bgfx::createUniform("u_star_viewport", bgfx::UniformType::Vec4);
  const auto starVbo = bgfx::createVertexBuffer(
      bgfx::copy(starVerts.data(), uint32_t(starVerts.size() * sizeof(armada::sky::StarVertex))), starLayout);
  if (!bgfx::isValid(starVbo) || !bgfx::isValid(starProgram) || !bgfx::isValid(starViewport))
    throw DeviceError("Star resource creation failed");
  cleanup.actions.push_back([starVbo] { bgfx::destroy(starVbo); });
  cleanup.actions.push_back([starProgram] { bgfx::destroy(starProgram); });
  cleanup.actions.push_back([starViewport] { bgfx::destroy(starViewport); });
  // W05 slice 5: the shield shell mesh. One view-space hemisphere per detail level, built once;
  // every bubble in the frame is then an instance record of eight floats. The baked latitude terms
  // (whiten, alpha) are the ones renderer.py::_shield_shell_list bakes into its display list.
  bgfx::VertexLayout shieldLayout;
  shieldLayout.begin()
      .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
      .end();
  bgfx::VertexBufferHandle shieldMesh[3] = {BGFX_INVALID_HANDLE, BGFX_INVALID_HANDLE,
                                            BGFX_INVALID_HANDLE};
  uint32_t shieldMeshVertices[3] = {0, 0, 0};
  {
    const int* grids[3] = {armada::fx::kShieldLow, armada::fx::kShieldMedium,
                           armada::fx::kShieldHigh};
    for (int level = 0; level < 3; ++level) {
      std::vector<armada::fx::ShellVertex> mesh;
      armada::fx::buildShellMesh(mesh, grids[level][0], grids[level][1]);
      std::vector<float> packed;
      packed.reserve(mesh.size() * 5);
      for (const auto& v : mesh)
        packed.insert(packed.end(), {v.x, v.y, v.z, v.whiten, v.alpha});
      shieldMeshVertices[level] = uint32_t(mesh.size());
      shieldMesh[level] = bgfx::createVertexBuffer(
          bgfx::copy(packed.data(), uint32_t(packed.size() * sizeof(float))), shieldLayout);
      if (!bgfx::isValid(shieldMesh[level]))
        throw DeviceError("Shield mesh creation failed");
      cleanup.actions.push_back([handle = shieldMesh[level]] { bgfx::destroy(handle); });
    }
  }
  const bgfx::ProgramHandle shieldProgram =
      bgfx::createProgram(shader(o.shaders / "vs_shield.bin"), shader(o.shaders / "fs_shield.bin"),
                          true);
  if (!bgfx::isValid(shieldProgram))
    throw DeviceError("Shield program creation failed");
  cleanup.actions.push_back([shieldProgram] { bgfx::destroy(shieldProgram); });
  // W05 slice 3: emissive pass. Same vertex layout and program as the cues - unlit world-space
  // triangles - but additive blending, so fire adds to the scene instead of covering it.
  std::unique_ptr<armada::bridge::RingReader> emitRing;
  uint64_t emitSequence = 0;
  size_t emitBatches = 0, emitDecodeFailures = 0, emitPrimitives = 0, emitTriangles = 0,
         emitDropped = 0;
  // W05 slice 5: shield shells are counted across the run - they are the only emissive primitive
  // whose cost scales with the number of shielded ships rather than with the number of shots.
  size_t shieldShells = 0, shieldVertices = 0;
  size_t shieldByDetail[3] = {0, 0, 0};
  double shieldFade = 0.0;
  // W05 slice 3c: damage contacts. Rebuilt geometry, so they are counted in triangles rather than
  // in draws; the smoke list is separate because a dark mass may not be drawn additively.
  size_t hitContacts = 0, hitShieldContacts = 0, hitHullContacts = 0, hitTrianglesCount = 0,
         hitSmokeTris = 0, hitSparks = 0;
  std::vector<uint8_t> emitPayload;
  std::vector<emit::Primitive> emitList;
  if (!o.emitRing.empty())
    emitRing = std::make_unique<armada::bridge::RingReader>(o.emitRing);
  float projScale = 0.f;    // proj[5] of the last frame, for the report's projection block
  std::unique_ptr<armada::bridge::RingReader> cameraRing;
  size_t cameraPoses = 0, cameraDecodeFailures = 0, cameraTorn = 0;
  if (!o.cameraRing.empty())
    cameraRing = std::make_unique<armada::bridge::RingReader>(o.cameraRing);
  std::unique_ptr<armada::bridge::RingReader> markerRing;
  uint64_t markerSequence = 0;
  size_t cueBatches = 0, cueDecodeFailures = 0, cueCircles = 0, cueMarkers = 0,
         cueVertices = 0, cueDropped = 0;
  std::vector<uint8_t> markerPayload;
  std::vector<cues::Primitive> cuePrimitives;
  if (!o.markerRing.empty())
    markerRing = std::make_unique<armada::bridge::RingReader>(o.markerRing);
  PlanetTextures planetTextures;
  cleanup.actions.push_back([&planetTextures] { planetTextures.destroy(); });
  {
    const uint32_t grey = 0x404040ff;
    const bgfx::Memory *memory = bgfx::copy(&grey, sizeof(grey));
    planetTextures.fallback = bgfx::createTexture2D(
        1, 1, false, 1, bgfx::TextureFormat::RGBA8, BGFX_SAMPLER_NONE, memory);
  }
  // W05 slice 4: fog. Python classifies one texel per visibility cell and the window samples it;
  // the quad is the only geometry this pass owns.
  struct FogVertex {
    float x, y, z;
    float u, v;
  };
  bgfx::VertexLayout fogLayout;
  fogLayout.begin()
      .add(bgfx::Attrib::Position, 3, bgfx::AttribType::Float)
      .add(bgfx::Attrib::TexCoord0, 2, bgfx::AttribType::Float)
      .end();
  const bgfx::ProgramHandle fogProgram =
      bgfx::createProgram(shader(o.shaders / "vs_fog.bin"),
                          shader(o.shaders / "fs_fog.bin"), true);
  if (!bgfx::isValid(fogProgram))
    throw DeviceError("Fog program creation failed");
  cleanup.actions.push_back([fogProgram] { bgfx::destroy(fogProgram); });
  const bgfx::UniformHandle fogSampler =
      bgfx::createUniform("s_fog", bgfx::UniformType::Sampler);
  if (!bgfx::isValid(fogSampler))
    throw DeviceError("Fog uniform creation failed");
  cleanup.actions.push_back([fogSampler] { bgfx::destroy(fogSampler); });
  bgfx::TextureHandle fogTexture = BGFX_INVALID_HANDLE;
  int fogTextureCells = 0;
  bgfx::VertexBufferHandle fogVbo = BGFX_INVALID_HANDLE;
  uint32_t fogGeneration = 0;
  float fogBounds = 0.f;
  cleanup.actions.push_back([&fogTexture] {
    if (bgfx::isValid(fogTexture))
      bgfx::destroy(fogTexture);
  });
  cleanup.actions.push_back([&fogVbo] {
    if (bgfx::isValid(fogVbo))
      bgfx::destroy(fogVbo);
  });
  std::unique_ptr<armada::bridge::RingReader> fogRing;
  uint64_t fogSequence = 0;
  size_t fogMasks = 0, fogDecodeFailures = 0, fogFramesDrawn = 0;
  std::vector<uint8_t> fogPayload;
  if (!o.fogRing.empty())
    fogRing = std::make_unique<armada::bridge::RingReader>(o.fogRing);
  // W05 slice 3e: surface hardware. The window's catalogue comes from the offline snapshot, which
  // cannot name a building that is constructed later, so the producer publishes the mesh itself.
  struct HardwareMesh {
    std::string binding;
    armada::Mesh mesh;
    bgfx::VertexBufferHandle vbo = BGFX_INVALID_HANDLE;
  };
  std::vector<HardwareMesh> hardwareMeshes;
  std::unique_ptr<armada::bridge::RingReader> meshRing;
  uint64_t meshSequence = 0;
  size_t hardwareBlobs = 0, hardwareDecodeFailures = 0, hardwareInstances = 0,
         hardwareDropped = 0;
  // Placement previews: fleet instances whose tint alpha is below 1 (the station ghost the
  // producer publishes while a build is being sited). Counted so a frame that silently lost
  // its preview is visible in the report rather than in a screenshot nobody takes.
  size_t previewInstances = 0, previewDropped = 0;
  std::vector<uint8_t> meshPayload;
  if (!o.meshRing.empty())
    meshRing = std::make_unique<armada::bridge::RingReader>(o.meshRing);
  std::unique_ptr<armada::bridge::RingReader> planetRing;
  uint64_t planetSequence = 0;
  size_t planetBlobs = 0, planetDecodeFailures = 0, planetBodiesDrawn = 0,
         planetUntextured = 0, planetFramesWithBodies = 0;
  std::vector<uint8_t> planetPayload;
  if (!o.planetRing.empty())
    planetRing = std::make_unique<armada::bridge::RingReader>(o.planetRing);
  auto lightUniform =
           bgfx::createUniform("u_lightMatrix", bgfx::UniformType::Mat4),
       eyeUniform = bgfx::createUniform("u_eye", bgfx::UniformType::Vec4),
       optionsUniform =
           bgfx::createUniform("u_options", bgfx::UniformType::Vec4),
       shadowSampler =
           bgfx::createUniform("s_shadow", bgfx::UniformType::Sampler);
  for (auto handle :
       {lightUniform, eyeUniform, optionsUniform, shadowSampler}) {
    if (!bgfx::isValid(handle))
      throw DeviceError("Uniform creation failed");
    cleanup.actions.push_back([handle] { bgfx::destroy(handle); });
  }
  auto depth =
      bgfx::createTexture2D(2048, 2048, false, 1, bgfx::TextureFormat::D16,
                            BGFX_TEXTURE_RT | BGFX_SAMPLER_COMPARE_LEQUAL |
                                BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP);
  if (!bgfx::isValid(depth))
    throw DeviceError("Shadow depth texture creation failed");
  cleanup.actions.push_back([depth] { bgfx::destroy(depth); });
  auto shadowFB = bgfx::createFrameBuffer(1, &depth, false);
  if (!bgfx::isValid(shadowFB))
    throw DeviceError("Shadow framebuffer creation failed");
  cleanup.actions.push_back([shadowFB] { bgfx::destroy(shadowFB); });
  // W03 overlay: its own ring, decoded with armada::overlay::decode, uploaded into one texture.
  std::unique_ptr<armada::bridge::RingReader> uiRing;
  if (!o.overlayRing.empty())
    uiRing = std::make_unique<armada::bridge::RingReader>(o.overlayRing);
  std::unique_ptr<armada::bridge::RingReader> topRing;
  if (!o.topHudRing.empty())
    topRing = std::make_unique<armada::bridge::RingReader>(o.topHudRing);
  std::unique_ptr<armada::top_hud::FontAtlas> topFont;
  std::optional<armada::top_hud::Model> topModel;
  armada::top_hud::Mesh topMesh;
  auto topTexture = std::make_shared<bgfx::TextureHandle>(bgfx::TextureHandle{bgfx::kInvalidHandle});
  cleanup.actions.push_back([topTexture] {
    if (bgfx::isValid(*topTexture)) bgfx::destroy(*topTexture);
  });
  uint64_t topSequence = 0;
  size_t topFrames = 0, topDecodeFailures = 0, topDrawn = 0, topAtlasUploads = 0;
  int topWidth = 0, topHeight = 0;
  int topFontHeight = 0;
  bool topDirty = false;
  std::vector<uint8_t> topPayload, topPrevious;
  auto ensureHudAtlas = [&](int drawableHeight) {
    if (topFont && topFontHeight == drawableHeight) return;
    auto atlas = std::make_unique<armada::top_hud::FontAtlas>(
        o.assets / "assets/fonts/NotoSans-Regular.ttf", drawableHeight);
    const auto texture = bgfx::createTexture2D(uint16_t(atlas->width()), uint16_t(atlas->height()),
        false, 1, bgfx::TextureFormat::RGBA8, BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP,
        bgfx::copy(atlas->pixels().data(), uint32_t(atlas->pixels().size())));
    if (!bgfx::isValid(texture)) throw DeviceError("Native HUD atlas upload failed");
    if (bgfx::isValid(*topTexture)) bgfx::destroy(*topTexture);
    *topTexture = texture;
    topFont = std::move(atlas);
    topFontHeight = drawableHeight;
    ++topAtlasUploads;
    topDirty = true;
  };
  std::unique_ptr<armada::bridge::RingReader> vectorRing;
  if (!o.vectorHudRing.empty())
    vectorRing = std::make_unique<armada::bridge::RingReader>(o.vectorHudRing);
  std::optional<armada::vector_hud::Model> vectorModel;
  armada::vector_hud::DrawList vectorMesh;
  auto vectorFogTexture = std::make_shared<bgfx::TextureHandle>(bgfx::TextureHandle{bgfx::kInvalidHandle});
  cleanup.actions.push_back([vectorFogTexture] {
    if (bgfx::isValid(*vectorFogTexture)) bgfx::destroy(*vectorFogTexture);
  });
  uint64_t vectorSequence = 0;
  size_t vectorFrames = 0, vectorDecodeFailures = 0, vectorDrawn = 0;
  size_t vectorFogUploads = 0, vectorTransientDrops = 0;
  int vectorWidth = 0, vectorHeight = 0;
  std::vector<uint8_t> vectorPayload, vectorPrevious;
  // W04: the same ring layout, written by this window and read by the simulation. The first
  // batch carries the window size so the consumer can map pointer pixels without guessing; it
  // never resizes the HUD, it only tells the game what the pointer is measured against.
  std::unique_ptr<input_ring::RingWriter> inputOut;
  size_t inputBatches = 0, inputEvents = 0, inputUnmappedKeys = 0;
  std::vector<input_ring::Event> inputPending;
  if (!o.inputRing.empty()) {
    inputOut = std::make_unique<input_ring::RingWriter>(o.inputRing, uint16_t(o.inputSlots),
                                                        1u << 16);
  }
  bgfx::TextureHandle uiTexture = BGFX_INVALID_HANDLE;
  uint16_t uiWidth = 0, uiHeight = 0;
  uint64_t uiSequence = 0;
  uint64_t uiSequenceAtShot = 0;
  size_t uiFrames = 0, uiPatches = 0, uiBytes = 0, uiFullFrames = 0, uiDecodeFailures = 0;
  size_t uiSkippedPatches = 0;
  // --hud-only presents the HUD quad alone so a screenshot is the texture's own pixels; bgfx's
  // Metal backend can only screenshot a swapchain framebuffer, so an offscreen dump target
  // silently produces nothing.
  std::vector<uint8_t> uiPayload;
  cleanup.actions.push_back([&uiTexture] {
    if (bgfx::isValid(uiTexture))
      bgfx::destroy(uiTexture);
  });
  armada::Camera original, camera;
  auto jc = scene.at("camera");
  original.target = jc.at("target").get<std::array<float, 3>>();
  original.distance = jc.at("distance");
  original.yaw = jc.at("yaw");
  original.pitch = jc.at("pitch");
  original.fov = jc.at("fov");
  std::string inspectionBinding;
  auto preset = [&](int which) {
    camera = original;
    inspectionBinding.clear();
    if (which == 1)
      return;
    const Json *best = nullptr;
    float bestExtent = -1;
    for (const auto &e : scene.at("instances")) {
      const auto category = e.at("category").get<std::string>();
      const bool station = category.find("station") != std::string::npos;
      if ((which == 3) != station || (which == 2 && category != "combat_ships"))
        continue;
      for (const auto &g : groups)
        if (g.mesh.binding == e.at("binding")) {
          const float extent = std::max({g.mesh.hi[0] - g.mesh.lo[0],
                                         g.mesh.hi[1] - g.mesh.lo[1],
                                         g.mesh.hi[2] - g.mesh.lo[2]}) *
                               e.at("scale").get<float>();
          if (extent > bestExtent) {
            best = &e;
            bestExtent = extent;
          }
        }
    }
    if (best) {
      camera.target = best->at("position").get<std::array<float, 3>>();
      camera.distance = bestExtent * 2.1f;
      camera.pitch = 28;
      camera.yaw = 145;
      inspectionBinding = best->at("binding");
    }
  };
  preset(o.preset);
  bool running = true, overlay = o.overlay, shadows = o.shadows;
  int width = pixelWidth, height = pixelHeight, frame = 0;
  std::vector<double> wall, cpu, gpu;
  std::vector<uint32_t> draws;
  // Capture framing only; never touches simulation state.
  if (o.hasFocus) {
    camera.target = o.focus;
    camera.pitch = 12;
    camera.yaw = 90;
  }
  if (o.distance > 0)
    camera.distance = float(o.distance);
  if (o.pitchGiven)
    camera.pitch = float(o.pitch);
  if (o.yawGiven)
    camera.yaw = float(o.yaw);
  auto previous = Clock::now();
  const auto live_start = Clock::now();
  // The Python renderer spins a planet at 1.2 rad/s about its own axis (glRotatef(time * 1.2)).
  double planetSeconds = 0.0;
  if (inputOut) {
    // First batch tells the consumer what the pointer is measured against, so it can map
    // window pixels onto the HUD surface without assuming a size.
    inputOut->publish(input_ring::encodeBatch(
        {{input_ring::kResize, 0, 0, 0, 0, (uint32_t(width) << 16) | uint32_t(height)}}));
    inputBatches = 1;
    inputEvents = 1;
  }
  std::array<float, 3> lightTarget = original.target;
  int screenshotExpected = 0;
  bool shot_taken = false;
  std::vector<Json> controlStates;
  while (running && (o.frames == 0 || frame < o.frames + o.warmup)) {
    if (host && !host->beginFrame()) break;
    const auto start = Clock::now();
    const float dt = std::chrono::duration<float>(start - previous).count();
    previous = start;
    planetSeconds += dt;
    const float planetSpin = float(planetSeconds * 1.2);
    if (live)
      live->step(groups);   // no frame yet leaves the groups empty on purpose
    if (live && o.seconds > 0.0 &&
        std::chrono::duration<double>(start - live_start).count() >= o.seconds)
      running = false;
    if (o.exercise && (frame == 5 || frame == 10 || frame == 15)) {
      SDL_Event event{};
      if (frame == 5) {
        event.type = SDL_EVENT_MOUSE_MOTION;
        event.motion.state = SDL_BUTTON_LMASK;
        event.motion.xrel = 120;
        event.motion.yrel = -35;
      } else if (frame == 10) {
        event.type = SDL_EVENT_MOUSE_WHEEL;
        event.wheel.y = 2;
      } else {
        event.type = SDL_EVENT_KEY_DOWN;
        event.key.key = SDLK_2;
      }
      SDL_PushEvent(&event);
    }
    if (o.inputExercise) {
      if (frame == 40) {
        SDL_Event down{};
        down.type = SDL_EVENT_KEY_DOWN;
        down.key.key = SDLK_SPACE;
        SDL_PushEvent(&down);
        SDL_Event up{};
        up.type = SDL_EVENT_KEY_UP;
        up.key.key = SDLK_SPACE;
        SDL_PushEvent(&up);
      } else if (frame == 41) {
        SDL_Event down{};
        down.type = SDL_EVENT_KEY_DOWN;
        down.key.key = SDLK_Q;
        SDL_PushEvent(&down);
      } else if (frame == 44) {
        SDL_Event up{};
        up.type = SDL_EVENT_KEY_UP;
        up.key.key = SDLK_Q;
        SDL_PushEvent(&up);
      } else if (frame == 46) {
        SDL_Event click{};
        click.type = SDL_EVENT_MOUSE_BUTTON_DOWN;
        click.button.button = SDL_BUTTON_LEFT;
        click.button.x = 640;
        click.button.y = 400;
        SDL_PushEvent(&click);
        SDL_Event release{};
        release.type = SDL_EVENT_MOUSE_BUTTON_UP;
        release.button.button = SDL_BUTTON_LEFT;
        release.button.x = 640;
        release.button.y = 400;
        SDL_PushEvent(&release);
      } else if (frame == 48) {
        SDL_Event wheel{};
        wheel.type = SDL_EVENT_MOUSE_WHEEL;
        wheel.wheel.y = -1.f;
        SDL_PushEvent(&wheel);
      }
    }
    if (o.cameraExercise) {
      // Bounded integration probe: travel through the real SDL event pump and input ring.
      // It is deliberately separate from offline camera controls and never used by the game.
      SDL_Event gesture{};
      if (frame == 80 || frame == 100) {
        gesture.type = frame == 80 ? SDL_EVENT_MOUSE_BUTTON_DOWN : SDL_EVENT_MOUSE_BUTTON_UP;
        gesture.button.button = SDL_BUTTON_RIGHT;
        gesture.button.x = frame == 80 ? 600.f : 760.f;
        gesture.button.y = frame == 80 ? 400.f : 500.f;
        SDL_PushEvent(&gesture);
      } else if (frame == 90) {
        gesture.type = SDL_EVENT_MOUSE_MOTION;
        gesture.motion.state = SDL_BUTTON_RMASK;
        gesture.motion.x = 760.f;
        gesture.motion.y = 500.f;
        gesture.motion.xrel = 160.f;
        gesture.motion.yrel = 100.f;
        SDL_PushEvent(&gesture);
      } else if (frame == 110 || frame == 111) {
        gesture.type = frame == 110 ? SDL_EVENT_KEY_DOWN : SDL_EVENT_KEY_UP;
        gesture.key.key = SDLK_ESCAPE;
        SDL_PushEvent(&gesture);
      }
    }
    SDL_Event ev;
    while (!host && SDL_PollEvent(&ev)) {
      if (inputOut) {
        float mx = 0.f, my = 0.f;
        switch (ev.type) {
        case SDL_EVENT_MOUSE_MOTION:
          inputPending.push_back({input_ring::kMotion,
                                  uint8_t(ev.motion.state & 0xFF), 0,
                                  int32_t(ev.motion.x), int32_t(ev.motion.y), 0});
          break;
        case SDL_EVENT_MOUSE_BUTTON_DOWN:
        case SDL_EVENT_MOUSE_BUTTON_UP:
          inputPending.push_back({ev.type == SDL_EVENT_MOUSE_BUTTON_DOWN
                                      ? input_ring::kButtonDown
                                      : input_ring::kButtonUp,
                                  uint8_t(ev.button.button), 0,
                                  int32_t(ev.button.x), int32_t(ev.button.y), 0});
          break;
        case SDL_EVENT_MOUSE_WHEEL:
          SDL_GetMouseState(&mx, &my);
          inputPending.push_back({input_ring::kWheel, uint8_t(ev.wheel.y > 0.f ? 1 : 0), 0,
                                  int32_t(mx), int32_t(my), 0});
          break;
        case SDL_EVENT_KEY_DOWN:
        case SDL_EVENT_KEY_UP: {
          const uint16_t code = wireKey(ev.key.key);
          if (code == 0) {
            ++inputUnmappedKeys;
            break;
          }
          inputPending.push_back({ev.type == SDL_EVENT_KEY_DOWN ? input_ring::kKeyDownEvent
                                                                 : input_ring::kKeyUpEvent,
                                  wireMod(ev.key.mod), code, 0, 0, 0});
          break;
        }
        case SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED:
          inputPending.push_back({input_ring::kResize, 0, 0, 0, 0,
                                  (uint32_t(ev.window.data1) << 16) |
                                      uint32_t(ev.window.data2)});
          break;
        case SDL_EVENT_WINDOW_FOCUS_LOST:
          inputPending.push_back({input_ring::kFocusLost, 0, 0, 0, 0, 0});
          break;
        case SDL_EVENT_QUIT:
          inputPending.push_back({input_ring::kQuit, 0, 0, 0, 0, 0});
          break;
        default:
          break;
        }
      }
      if (ev.type == SDL_EVENT_QUIT)
        running = false;
      else if (ev.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) {
        width = std::max(1, ev.window.data1);
        height = std::max(1, ev.window.data2);
        init.swapChain.width = width;
        init.swapChain.height = height;
        bgfx::reset(BGFX_RESET_NONE, &init.swapChain);
      } else if (inputOut) {
        // In a live game Python owns every shortcut, including Escape (cancel first),
        // F (fleet), H and camera motion. Offline inspection controls must not also act.
        continue;
      } else if (ev.type == SDL_EVENT_MOUSE_MOTION &&
                 (ev.motion.state & SDL_BUTTON_LMASK))
        camera.orbit(-ev.motion.xrel * .25f, ev.motion.yrel * .2f);
      else if (ev.type == SDL_EVENT_MOUSE_WHEEL)
        camera.zoom(ev.wheel.y);
      else if (ev.type == SDL_EVENT_KEY_DOWN) {
        switch (ev.key.key) {
        case SDLK_ESCAPE:
          running = false;
          break;
        case SDLK_1:
          preset(1);
          break;
        case SDLK_2:
          preset(2);
          break;
        case SDLK_3:
          preset(3);
          break;
        case SDLK_H:
          shadows = !shadows;
          break;
        case SDLK_S:
          if ((ev.key.mod & SDL_KMOD_SHIFT) != 0) {
            bgfx::requestScreenShot(BGFX_INVALID_HANDLE, "armada-viewer.png");
            screenshotExpected++;
          }
          break;
        default:
          break;
        }
      }
    }
    if (inputOut && !inputPending.empty()) {
      inputOut->publish(input_ring::encodeBatch(inputPending));
      ++inputBatches;
      inputEvents += inputPending.size();
      inputPending.clear();
    }
    if (!host && !inputOut) {
      const bool *keys = SDL_GetKeyboardState(nullptr);
      camera.pan(float(keys[SDL_SCANCODE_D]) - float(keys[SDL_SCANCODE_A]),
                 float(keys[SDL_SCANCODE_W]) - float(keys[SDL_SCANCODE_S]), dt);
    }
    if (o.exercise && (frame == 0 || frame == 5 || frame == 10 || frame == 15))
      controlStates.push_back(Json{{"frame", frame},
                                   {"target", camera.target},
                                   {"distance", camera.distance},
                                   {"yaw", camera.yaw},
                                   {"pitch", camera.pitch}});
    // The game's camera, applied before the view matrix is built. `ARMCAM01`: 20-byte header then
    // six float32 - target xyz, distance, yaw, pitch - all in the game's units and degrees. The pose
    // is used exactly as sent: with the projection fixed there is no compensation to apply, and the
    // window and the game frame the same battle at the same distance.
    if (cameraRing) {
      const uint64_t poseSeq = cameraRing->published();
      static std::vector<uint8_t> posePayload;
      if (poseSeq && cameraRing->read_at_sequence(poseSeq - 1, poseSeq, posePayload)) {
        constexpr size_t kHeader = 20, kPose = 24;
        if (posePayload.size() == kHeader + kPose) {
          float v[6];
          std::memcpy(v, posePayload.data() + kHeader, sizeof(v));
          // Length is checked above; the header's own crc is the producer's to validate (`decode`
          // refuses a bad pose), and the ring's seqlock has already rejected a torn slot.
          camera.target = {v[0], v[1], v[2]};
          camera.distance = v[3];
          camera.yaw = v[4];
          camera.pitch = v[5];
          ++cameraPoses;
        } else {
          ++cameraDecodeFailures;
        }
      } else {
        ++cameraTorn;
      }
    }
    auto eye = camera.eye();
    float view[16], proj[16], lightView[16], lightProj[16], lightVP[16],
        lightMtx[16];
    bx::mtxLookAt(view, {eye[0], eye[1], eye[2]},
                  {camera.target[0], camera.target[1], camera.target[2]},
                  {0, 1, 0}, bx::Handedness::Right);
    // W06: `camera.fov` is DEGREES and must stay degrees. `bx::math.h` documents `_fovy` as radians,
    // but this bx version's `mtxProj` applies `toRad()` itself (bx_source-src/src/math.cpp:90:
    // `height = 1.0f/tan(toRad(_fovy)*0.5f)`), so passing radians yields a ~1 deg field of view and
    // a frame full of clipped geometry. Measured: `proj[5]` is 1.9209 for 55 deg as degrees (what the
    // Python renderer uses) and 119.37 for 55 deg converted here. The report's `projection` block
    // carries both `proj_scale` and `expected_scale` so this can never drift silently again.
    bx::mtxProj(proj, camera.fov, float(width) / height, .5f, 150000.f,
                bgfx::getCaps()->homogeneousDepth, bx::Handedness::Right);
    projScale = proj[5];
    const float radius =
        std::max(300.f, std::min(camera.distance * .85f, 14000.f));
    lightTarget = camera.target;
    bx::mtxLookAt(lightView,
                  {lightTarget[0] - radius * .9f,
                   lightTarget[1] + radius * 1.6f,
                   lightTarget[2] + radius * .8f},
                  {lightTarget[0], lightTarget[1], lightTarget[2]}, {0, 1, 0},
                  bx::Handedness::Right);
    bx::mtxOrtho(lightProj, -radius, radius, -radius, radius, 1.f, radius * 5,
                 0, bgfx::getCaps()->homogeneousDepth, bx::Handedness::Right);
    bx::mtxMul(lightVP, lightView, lightProj);
    const bool hd = bgfx::getCaps()->homogeneousDepth;
    const float bias[16] = {.5f,
                            0,
                            0,
                            0,
                            0,
                            bgfx::getCaps()->originBottomLeft ? .5f : -.5f,
                            0,
                            0,
                            0,
                            0,
                            hd ? .5f : 1.f,
                            0,
                            .5f,
                            .5f,
                            hd ? .5f : 0.f,
                            1};
    bx::mtxMul(lightMtx, lightVP, bias);
    if (o.hudOnly) {
      // Diagnostic mode: the HUD quad alone over opaque black, no blending, no debug text. The
      // backbuffer screenshot is then the HUD texture's own RGB, comparable with the Python
      // surface pixel for pixel.
      bgfx::setViewClear(1, BGFX_CLEAR_COLOR, 0x000000ff, 1.f, 0);
      bgfx::touch(1);
    }
    bgfx::setViewClear(0, BGFX_CLEAR_DEPTH, 0, 1.f);
    bgfx::setViewFrameBuffer(0, shadowFB);
    bgfx::setViewRect(0, 0, 0, 2048, 2048);
    bgfx::setViewTransform(0, lightView, lightProj);
    bgfx::setViewClear(1, BGFX_CLEAR_COLOR | BGFX_CLEAR_DEPTH, 0x080e1bff, 1.f);
    // Sorting can submit sky after opaque draws: far-plane depth testing is mandatory.
    if (!o.hudOnly) {
      const float viewport[4] = {float(width), float(height), 0.f, 0.f};
      bgfx::setVertexBuffer(0, starVbo);
      bgfx::setUniform(starViewport, viewport);
      bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_MSAA | BGFX_STATE_DEPTH_TEST_LEQUAL |
                    BGFX_STATE_BLEND_FUNC(BGFX_STATE_BLEND_SRC_ALPHA, BGFX_STATE_BLEND_ONE));
      bgfx::submit(1, starProgram);
    }
    bgfx::setViewRect(1, 0, 0, uint16_t(width), uint16_t(height));
    bgfx::setViewTransform(1, view, proj);
    bgfx::touch(1);
    const float eyeData[4] = {eye[0], eye[1], eye[2], 1},
                optionData[4] = {shadows ? 1.f : 0.f, 0, 0, 0};
    // Every translucent row - a fleet instance or a station whose mesh arrived on the mesh ring -
    // is drawn by this one path, so the preview behaves the same however the station is meshed.
    // Alpha comes from the instance row, not a per-draw uniform: one binding's group can hold
    // both opaque hulls and a ghost, and several previews must still blend independently.
    // Shadowing stays whatever the opaque pass uses, so the only difference between the preview
    // and a solid station is its alpha - otherwise the two images differ by lighting too and a
    // measured blend proves nothing.
    const float previewOptions[4] = {shadows ? 1.f : 0.f, 1.f, 1.f, 0.f};
    struct PreviewDraw {
      bgfx::VertexBufferHandle vbo;
      std::vector<float> rows;
    };
    std::vector<PreviewDraw> previewDraws;
    // The preview rides the ordinary world view. A separate view id has to be declared in the
    // window's view order, and getting that order wrong silently cost the whole HUD, so the ghost
    // is queued here and drawn as one extra blended submit at the end of the world instead.
    auto queuePreviews = [&](bgfx::VertexBufferHandle vbo, const std::vector<float> &rows) {
      if (!rows.empty())
        previewDraws.push_back({vbo, rows});
    };
    auto flushPreviews = [&]() {
      for (const auto &draw : previewDraws) {
        const uint32_t count = uint32_t(draw.rows.size() / 20);
        if (!count)
          continue;
        if (bgfx::getAvailInstanceDataBuffer(count, 80) < count) {
          previewDropped += count;
          continue;
        }
        bgfx::InstanceDataBuffer buffer;
        bgfx::allocInstanceDataBuffer(&buffer, count, 80);
        std::memcpy(buffer.data, draw.rows.data(), draw.rows.size() * sizeof(float));
        bgfx::setVertexBuffer(0, draw.vbo);
        bgfx::setInstanceDataBuffer(&buffer);
        bgfx::setUniform(lightUniform, lightMtx);
        bgfx::setUniform(eyeUniform, eyeData);
        bgfx::setUniform(optionsUniform, previewOptions);
        bgfx::setTexture(0, shadowSampler, depth);
        // Two submits, no extra view: a station mesh overlaps itself many times and its triangle
        // order is arbitrary, so a single blended draw composites whichever nearer triangle
        // happens to come last on top of the previous one - measured at alpha 0.55 that produced
        // 0.81, i.e. a solid-looking hull. Depth-only first, then colour at EQUAL depth: the
        // front-most surface composites exactly once at the alpha on the wire.
        bgfx::setState(BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS);
        bgfx::submit(1, program);
        bgfx::setVertexBuffer(0, draw.vbo);
        bgfx::setInstanceDataBuffer(&buffer);
        bgfx::setUniform(lightUniform, lightMtx);
        bgfx::setUniform(eyeUniform, eyeData);
        bgfx::setUniform(optionsUniform, previewOptions);
        bgfx::setTexture(0, shadowSampler, depth);
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A |
                       BGFX_STATE_DEPTH_TEST_LEQUAL | BGFX_STATE_MSAA | BGFX_STATE_BLEND_ALPHA);
        bgfx::submit(1, program);
        previewInstances += count;
      }
      previewDraws.clear();
    };
    auto submitPreviews = [&](bgfx::VertexBufferHandle vbo, const std::vector<float> &rows) {
      queuePreviews(vbo, rows);
    };
    // Split each binding's rows: opaque rows keep the existing state, preview rows (alpha < 1)
    // are deferred to view 3. Keeping the opaque path byte-for-byte unchanged matters - the
    // approved reference frames are captured from it.
    std::vector<std::vector<float>> previewRows(groups.size());
    std::vector<float> opaqueRows;
    for (size_t gi = 0; gi < groups.size(); ++gi) {
      const auto &g = groups[gi];
      opaqueRows.clear();
      opaqueRows.reserve(g.instances.size());
      for (size_t i = 0; i + 19 < g.instances.size(); i += 20) {
        auto &bucket = g.instances[i + 19] < 0.999f ? previewRows[gi] : opaqueRows;
        bucket.insert(bucket.end(), &g.instances[i], &g.instances[i] + 20);
      }
      const uint32_t count = uint32_t(opaqueRows.size() / 20);
      if (!count) {
        // A binding whose only instance is the preview (the station being placed has no other
        // hull yet) must still reach its own draw: skipping the opaque submit must not skip it.
        submitPreviews(g.vbo, previewRows[gi]);
        continue;
      }
      if (bgfx::getAvailInstanceDataBuffer(count, 80) < count)
        throw DeviceError("Instance buffer exhausted; refusing partial fleet");
      bgfx::InstanceDataBuffer buffer;
      bgfx::allocInstanceDataBuffer(&buffer, count, 80);
      std::memcpy(buffer.data, opaqueRows.data(), opaqueRows.size() * sizeof(float));
      if (shadows) {
        bgfx::setVertexBuffer(0, g.vbo);
        bgfx::setInstanceDataBuffer(&buffer);
        bgfx::setState(BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS);
        bgfx::submit(0, shadowProgram);
      }
      bgfx::setVertexBuffer(0, g.vbo);
      bgfx::setInstanceDataBuffer(&buffer);
      bgfx::setUniform(lightUniform, lightMtx);
      bgfx::setUniform(eyeUniform, eyeData);
      bgfx::setUniform(optionsUniform, optionData);
      bgfx::setTexture(0, shadowSampler, depth);
      bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A |
                     BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS |
                     BGFX_STATE_MSAA);
      bgfx::submit(1, program);
      submitPreviews(g.vbo, previewRows[gi]);
    }
    // W05 slice 3e: take in any surface-hardware mesh published since the last frame, then draw the
    // buildings the frame placed. A building whose mesh has not arrived is counted and skipped - the
    // producer publishes each binding once, so it appears on the next frame, not never.
    if (meshRing) {
      const uint64_t available = meshRing->published();
      while (meshSequence < available) {
        if (meshRing->read_at_sequence(meshSequence, available, meshPayload)) {
          try {
            auto mesh = armada::hardware::decode(meshPayload.data(), meshPayload.size());
            bool known = false;
            for (const auto &existing : hardwareMeshes)
              known = known || existing.binding == mesh.binding;
            if (!known) {
              HardwareMesh entry;
              entry.binding = mesh.binding;
              entry.mesh = std::move(mesh);
              entry.vbo = bgfx::createVertexBuffer(
                  bgfx::copy(entry.mesh.vertices.data(),
                             uint32_t(entry.mesh.vertices.size() * sizeof(armada::Vertex))),
                  layout);
              if (!bgfx::isValid(entry.vbo))
                throw DeviceError("hardware mesh upload failed");
              const auto handle = entry.vbo;
              cleanup.actions.push_back([handle] { bgfx::destroy(handle); });
              hardwareMeshes.push_back(std::move(entry));
              ++hardwareBlobs;
            }
          } catch (const armada::hardware::HardwareError &) {
            ++hardwareDecodeFailures;
          }
        }
        ++meshSequence;
      }
    }
    if (live && !live->surface.empty()) {
      live->surface_unmeshed = 0;
      for (const auto &h : hardwareMeshes) {
        std::vector<float> instances;
        std::vector<float> translucent;
        for (const auto &building : live->surface) {
          if (building.binding != h.binding)
            continue;
          float row[20] = {building.matrix[0], building.matrix[1], building.matrix[2], 0.f,
                           building.matrix[3], building.matrix[4], building.matrix[5], 0.f,
                           building.matrix[6], building.matrix[7], building.matrix[8], 0.f,
                           building.matrix[9], building.matrix[10], building.matrix[11], 1.f,
                           building.tint[0] / 255.f, building.tint[1] / 255.f,
                           building.tint[2] / 255.f, building.tint[3] / 255.f};
          auto &bucket = building.tint[3] < 255 ? translucent : instances;
          bucket.insert(bucket.end(), row, row + 20);
        }
        const uint32_t count = uint32_t(instances.size() / 20);
        if (!count) {
          submitPreviews(h.vbo, translucent);
          continue;
        }
        if (bgfx::getAvailInstanceDataBuffer(count, 80) < count) {
          hardwareDropped += count;
          submitPreviews(h.vbo, translucent);
          continue;
        }
        bgfx::InstanceDataBuffer buffer;
        bgfx::allocInstanceDataBuffer(&buffer, count, 80);
        std::memcpy(buffer.data, instances.data(), instances.size() * sizeof(float));
        if (shadows) {
          bgfx::setVertexBuffer(0, h.vbo);
          bgfx::setInstanceDataBuffer(&buffer);
          bgfx::setState(BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS);
          bgfx::submit(0, shadowProgram);
        }
        bgfx::setVertexBuffer(0, h.vbo);
        bgfx::setInstanceDataBuffer(&buffer);
        bgfx::setUniform(lightUniform, lightMtx);
        bgfx::setUniform(eyeUniform, eyeData);
        bgfx::setUniform(optionsUniform, optionData);
        bgfx::setTexture(0, shadowSampler, depth);
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A |
                       BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS |
                       BGFX_STATE_MSAA);
        bgfx::submit(1, program);
        hardwareInstances += count;
        submitPreviews(h.vbo, translucent);
      }
      for (const auto &building : live->surface) {
        bool meshed = false;
        for (const auto &h : hardwareMeshes)
          meshed = meshed || h.binding == building.binding;
        if (!meshed)
          ++live->surface_unmeshed;
      }
    }
    flushPreviews();
    // W05: take in any planet texture published since the last frame, then draw the bodies the
    // frame asked for. A planet whose texture has not arrived yet draws with the grey fallback and
    // is counted, never silently dropped.
    if (planetRing) {
      const uint64_t available = planetRing->published();
      while (planetSequence < available) {
        if (planetRing->read_at_sequence(planetSequence, available, planetPayload)) {
          try {
            const auto blob = planets::decode(planetPayload.data(), planetPayload.size());
            if (planetTextures.apply(blob))
              ++planetBlobs;
          } catch (const planets::PlanetError &) {
            ++planetDecodeFailures;
          }
        }
        ++planetSequence;
      }
    }
    if (live && !live->planets.empty()) {
      ++planetFramesWithBodies;
      bgfx::setUniform(eyeUniform, eyeData);
      const float starData[4] = {o.star[0], std::max(o.star[1], 2000.f), o.star[2], 1.f};
      bgfx::setUniform(planetStar, starData);
      for (const auto &body : live->planets) {
        const float px = body.position[0], py = body.position[1], pz = body.position[2];
        const float pr = body.radius;
        // Build the body matrix through the same helper the fleet's instances use: bx::mtxMul's
        // operand order is easy to get wrong (it produced a translation of radius * distance
        // instead of distance), and this path is already exercised by 638 ships.
        float model[20];
        armada::bridge::Pose bodyPose;
        bodyPose.position = {px, py, pz};
        bodyPose.scale = pr;
        bodyPose.yaw = planetSpin;
        armada::bridge::write_instance(model, bodyPose, {{255, 255, 255, 255}});
        // bgfx clears the draw state after every submit, so each body rebinds geometry and state.
        // The matrix travels as an instance (as the fleet's does) rather than through u_model.
        bgfx::setVertexBuffer(0, sphereVbo);
        bgfx::setIndexBuffer(sphereIbo);
        bgfx::setUniform(planetModel, model);
        const float flags[4] = {body.atmosphere ? 1.f : 0.f, 0.f, 0.f, 0.f};
        bgfx::setUniform(planetFlags, flags);
        const bgfx::TextureHandle texture = planetTextures.handleFor(body.texture);
        if (!bgfx::isValid(texture) || texture.idx == planetTextures.fallback.idx)
          ++planetUntextured;
        bgfx::setTexture(0, planetSampler, texture);
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_Z |
                       BGFX_STATE_DEPTH_TEST_LESS | BGFX_STATE_MSAA);
        bgfx::submit(1, planetProgram);
        ++planetBodiesDrawn;
      }
    }
    // W05 slice 4: the fog mask. Drawn after the bodies and with depth testing off, because in the
    // Python renderer the mask is a picture of what the player knows rather than geometry in the
    // world: it covers unexplored space, and the ships in it.
    if (fogRing) {
      const uint64_t available = fogRing->published();
      while (fogSequence < available) {
        if (fogRing->read_at_sequence(fogSequence, available, fogPayload)) {
          try {
            const auto mask = armada::fogmap::decode(fogPayload);
            if (mask.generation != fogGeneration || mask.cells != fogTextureCells) {
              const uint32_t side = uint32_t(mask.cells);
              const bgfx::Memory *pixels =
                  bgfx::copy(mask.rgba.data(), uint32_t(mask.rgba.size()));
              if (bgfx::isValid(fogTexture) && mask.cells == fogTextureCells) {
                bgfx::updateTexture2D(fogTexture, 0, 0, 0, 0, side, side, pixels);
              } else {
                if (bgfx::isValid(fogTexture))
                  bgfx::destroy(fogTexture);
                fogTexture = bgfx::createTexture2D(
                    uint16_t(side), uint16_t(side), false, 1,
                    bgfx::TextureFormat::RGBA8,
                    BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP |
                        BGFX_SAMPLER_MIN_POINT | BGFX_SAMPLER_MAG_POINT |
                        BGFX_SAMPLER_MIP_POINT,
                    pixels);
                fogTextureCells = mask.cells;
              }
              if (mask.bounds != fogBounds) {
                fogBounds = mask.bounds;
                const float h = fogBounds * 0.5f;
                const FogVertex quad[6] = {{-h, 0.f, -h, 0.f, 0.f}, {h, 0.f, -h, 1.f, 0.f},
                                           {h, 0.f, h, 1.f, 1.f},  {-h, 0.f, -h, 0.f, 0.f},
                                           {h, 0.f, h, 1.f, 1.f},  {-h, 0.f, h, 0.f, 1.f}};
                if (bgfx::isValid(fogVbo))
                  bgfx::destroy(fogVbo);
                fogVbo = bgfx::createVertexBuffer(
                    bgfx::copy(quad, sizeof(quad)), fogLayout);
              }
              fogGeneration = mask.generation;
              ++fogMasks;
            }
          } catch (const armada::fogmap::FogMapError &) {
            ++fogDecodeFailures;
          }
        }
        ++fogSequence;
      }
    }
    if (bgfx::isValid(fogTexture) && bgfx::isValid(fogVbo)) {
      bgfx::setVertexBuffer(0, fogVbo);
      bgfx::setTexture(0, fogSampler, fogTexture);
      bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A | BGFX_STATE_BLEND_ALPHA);
      bgfx::submit(1, fogProgram);
      ++fogFramesDrawn;
    }
    // W05 slice 2: ownership cues. A batch is a few hundred primitives, so the geometry is rebuilt
    // on the CPU each frame and drawn unlit: rings as line segments, markers as billboards.
    if (markerRing) {
      const uint64_t available = markerRing->published();
      if (available > markerSequence &&
          markerRing->read_at_sequence(available - 1, available, markerPayload)) {
        markerSequence = available;
        try {
          cuePrimitives = cues::decode(markerPayload.data(), markerPayload.size());
          ++cueBatches;
        } catch (const cues::MarkerError &) {
          ++cueDecodeFailures;      // a damaged batch must not half-draw: keep the last good one
        }
      }
    }
    if (!cuePrimitives.empty()) {
      std::vector<CueVertex> flatLines, depthLines, fill;
      // Lines widened into quads (see pushThickSegment): circles and marker outlines go here, so a
      // selection ring is the same weight on screen as Python's.
      std::vector<CueVertex> flatQuads, depthQuads;
      const float cueForward[3] = {view[2], view[6], view[10]};
      // Billboard basis: rows 0 and 1 of the view rotation, which is what the Python markers use.
      const float rx = view[0], ry = view[4], rz = view[8];
      const float ux = view[1], uy = view[5], uz = view[9];
      const float focal = float(height) * 0.5f /
                          std::tan(camera.fov * 0.5f * float(M_PI) / 180.f);
      for (const auto &primitive : cuePrimitives) {
        if (primitive.kind == cues::kCircle) {
          const int segments = primitive.segments ? int(primitive.segments) : 28;
          // A ring at the frame's catalogue scale is a hairline when the camera is far away (a
          // convoy hull is ~1.5 world units), so the radius is lifted to a legible floor on
          // screen. Same rule and same reason as marker_px: what crosses is the decision, the
          // window keeps the cue readable at any zoom.
          const float viewZ = view[2] * primitive.centre[0] + view[6] * primitive.centre[1] +
                              view[10] * primitive.centre[2] + view[14];
          const float depth = std::max(1.f, -viewZ);
          const float projected = primitive.size * focal / depth;
          float ringSize = primitive.size;
          if (projected > 0.f && projected < 9.f)
            ringSize *= 9.f / projected;
          std::vector<CueVertex> &out = primitive.depth() ? depthQuads : flatQuads;
          // 2.5 px wide at this ring's own depth: half the width, converted from pixels to world.
          const float halfWorld = 1.25f * depth / focal;
          for (int i = 0; i < segments; ++i) {
            const float a0 = float(i) / float(segments) * 2.f * float(M_PI);
            const float a1 = float(i + 1) / float(segments) * 2.f * float(M_PI);
            const float s0 = std::sin(a0) * ringSize, c0 = std::cos(a0) * ringSize;
            const float s1 = std::sin(a1) * ringSize, c1 = std::cos(a1) * ringSize;
            float start[3], end[3];
            if (primitive.shape == cues::kShapeUpright) {
              start[0] = primitive.centre[0] + s0; start[1] = primitive.centre[1] + c0;
              start[2] = primitive.centre[2];
              end[0] = primitive.centre[0] + s1; end[1] = primitive.centre[1] + c1;
              end[2] = primitive.centre[2];
            } else {
              start[0] = primitive.centre[0] + s0; start[1] = primitive.centre[1];
              start[2] = primitive.centre[2] + c0;
              end[0] = primitive.centre[0] + s1; end[1] = primitive.centre[1];
              end[2] = primitive.centre[2] + c1;
            }
            pushThickSegment(out, start, end, primitive.colour, halfWorld, cueForward);
          }
          ++cueCircles;
          continue;
        }
        // A marker's footprint comes from this camera, exactly as render/markers.py does it, so the
        // icon stays 9-15 px whatever the window's zoom is.
        const float viewZ = view[2] * primitive.centre[0] + view[6] * primitive.centre[1] +
                            view[10] * primitive.centre[2] + view[14];
        const float depth = std::max(1.f, -viewZ);
        const float apparent = 2.f * primitive.size * focal / depth;
        const float px = std::max(9.f, std::min(15.f, 9.f + std::max(0.f, apparent) * 0.12f));
        const float radius = (px * 0.5f) * depth / focal;
        const float *polygon = primitive.shape == cues::kShapeDiamond ? &kDiamondPts[0][0]
                                                                     : &kChevronPts[0][0];
        const float anchor[3] = {primitive.centre[0] + ux * radius * 1.55f,
                                 primitive.centre[1] + uy * radius * 1.55f,
                                 primitive.centre[2] + uz * radius * 1.55f};
        float points[6][3];
        for (int i = 0; i < 6; ++i) {
          points[i][0] = anchor[0] + rx * polygon[i * 2] * radius + ux * polygon[i * 2 + 1] * radius;
          points[i][1] = anchor[1] + ry * polygon[i * 2] * radius + uy * polygon[i * 2 + 1] * radius;
          points[i][2] = anchor[2] + rz * polygon[i * 2] * radius + uz * polygon[i * 2 + 1] * radius;
        }
        for (int i = 1; i + 1 < 6; ++i) {          // triangle fan over the outline
          pushCue(fill, points[0], primitive.colour);
          pushCue(fill, points[i], primitive.colour);
          pushCue(fill, points[i + 1], primitive.colour);
        }
        const std::array<uint8_t, 4> outline = {5, 8, 13, primitive.colour[3]};
        const float outlineHalf = 1.0f * depth / focal;      // a 2 px outline, like the marker
        for (int i = 0; i < 6; ++i)
          pushThickSegment(flatQuads, points[i], points[(i + 1) % 6], outline, outlineHalf,
                           cueForward);
        ++cueMarkers;
      }
      auto submitCues = [&](const std::vector<CueVertex> &verts, uint64_t primitive,
                            bool depthTest) {
        if (verts.empty())
          return;
        const uint32_t count = uint32_t(verts.size());
        if (bgfx::getAvailTransientVertexBuffer(count, cueLayout) < count) {
          cueDropped += count;      // counted, not silently squeezed
          return;
        }
        bgfx::TransientVertexBuffer tvb;
        bgfx::allocTransientVertexBuffer(&tvb, count, cueLayout);
        std::memcpy(tvb.data, verts.data(), count * sizeof(CueVertex));
        bgfx::setVertexBuffer(0, &tvb);
        uint64_t state = BGFX_STATE_WRITE_RGB | BGFX_STATE_MSAA | primitive |
                         BGFX_STATE_BLEND_ALPHA;
        if (depthTest)
          state |= BGFX_STATE_WRITE_Z | BGFX_STATE_DEPTH_TEST_LESS;
        bgfx::setState(state);
        bgfx::submit(1, cueProgram);
        cueVertices += count;
      };
      submitCues(depthQuads, 0, true);
      submitCues(flatQuads, 0, false);
      submitCues(depthLines, BGFX_STATE_PT_LINES, true);
      submitCues(flatLines, BGFX_STATE_PT_LINES, false);
      submitCues(fill, 0, false);   // triangle lists are bgfx's default primitive type
    }
    // W05 slice 3: emissive pass - beams, glows, rings and bolts. The batch is small, so the
    // geometry is built on the CPU, and everything blends additively: fire adds light to a scene
    // rather than covering it.
    if (emitRing) {
      const uint64_t available = emitRing->published();
      if (available > emitSequence &&
          emitRing->read_at_sequence(available - 1, available, emitPayload)) {
        emitSequence = available;
        try {
          emitList = emit::decode(emitPayload.data(), emitPayload.size());
          ++emitBatches;
        } catch (const emit::EmissiveError &) {
          ++emitDecodeFailures;      // keep the last good batch rather than half-draw a volley
        }
      }
    }
    if (!o.fxDemo.empty() && emitList.empty()) {
      // size,age,seed
      float size = 120.f, age = 0.35f;
      unsigned seed = 7;
      std::sscanf(o.fxDemo.c_str(), "%f,%f,%u", &size, &age, &seed);
      emit::Primitive demo{};
      // "disc:SIZE,ALPHA" is a single-primitive alpha probe: one flat red disc whose on-screen
      // value must equal ALPHA over the background. It is how the blend state is checked.
      demo.kind = emit::kExplosion;
      const std::string demoSpec = o.fxDemo.string();
      if (demoSpec.rfind("disc:", 0) == 0) {
        float dsize = 100.f, dalpha = 0.5f;
        std::sscanf(demoSpec.c_str() + 5, "%f,%f", &dsize, &dalpha);
        demo.kind = emit::kDisc;
        demo.a = {camera.target[0], camera.target[1], camera.target[2]};
        demo.radius = dsize;
        demo.colour = {255, 0, 0, uint8_t(std::lround(dalpha * 255.f))};
        emitList.assign(1, demo);
      }
      demo.a = {camera.target[0], camera.target[1], camera.target[2]};
      demo.radius = size;
      demo.width = age;
      demo.segments = uint16_t(seed & 0xFFFFu);
      emitList.assign(1, demo);
    }
    if (!emitList.empty()) {
      std::vector<CueVertex> nearTriangles, farTriangles, smokeTriangles;
      // Contacts are alpha-blended surface markings, not light: they ride their own submitted pair
      // (triangles then smoke) so a fireball's additive pass cannot saturate them.
      std::vector<CueVertex> hitTriangles, hitSmokeVerts;
      size_t fxLayers = 0, fxVertexCount = 0;
      double fxAlphaSum = 0.0;
      const float kShieldMinPx = 74.f;   // renderer.py::SHIELD_MIN_PX, applied at this camera
      const float rx = view[0], ry = view[4], rz = view[8];
      const float ux = view[1], uy = view[5], uz = view[9];
      const float rightVec[3] = {rx, ry, rz};
      const float upVec[3] = {ux, uy, uz};
      const float eyeVec[3] = {float(eye[0]), float(eye[1]), float(eye[2])};
      const float focal = float(height) * 0.5f /
                          std::tan(camera.fov * 0.5f * float(M_PI) / 180.f);
      auto eyeDepth = [&](const float *p) {
        return std::max(1.f, -(view[2] * p[0] + view[6] * p[1] + view[10] * p[2] + view[14]));
      };
      auto tint = [](const std::array<uint8_t, 4> &c, float alpha) {
        return std::array<float, 4>{c[0] / 255.f, c[1] / 255.f, c[2] / 255.f,
                                    (c[3] / 255.f) * alpha};
      };
      auto push = [](std::vector<CueVertex> &out, const float *p, const std::array<float, 4> &c) {
        out.push_back({p[0], p[1], p[2], c[0], c[1], c[2], c[3]});
      };
      auto triangle = [&](std::vector<CueVertex> &out, const float *a, const float *b,
                          const float *c, const std::array<float, 4> &colour) {
        push(out, a, colour); push(out, b, colour); push(out, c, colour);
        emitTriangles += 1;
      };
      auto quad = [&](std::vector<CueVertex> &out, const float *a, const float *b, const float *c,
                      const float *d, const std::array<float, 4> &colour) {
        triangle(out, a, b, c, colour);
        triangle(out, a, c, d, colour);
      };
      // W05 slice 5: one bucket of instance records per detail level. Three instanced draws per
      // frame replace ~2,400 CPU-built vertices per shielded unit.
      std::vector<float> shieldInstances[3];
      for (const auto &primitive : emitList) {
        std::vector<CueVertex> &out = primitive.depth() ? farTriangles : nearTriangles;
        ++emitPrimitives;
        const std::array<float, 4> colour = tint(primitive.colour, 1.f);
        if (primitive.kind == emit::kRibbon) {
          // Camera-facing ribbon: the perpendicular is the beam axis crossed with the eye vector,
          // exactly as renderer.py::_beam_ribbon builds it.
          const float axis[3] = {primitive.b[0] - primitive.a[0], primitive.b[1] - primitive.a[1],
                                 primitive.b[2] - primitive.a[2]};
          const float lengthSq = axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2];
          if (lengthSq < 1e-12f)
            continue;
          const float mid[3] = {(primitive.a[0] + primitive.b[0]) * 0.5f,
                                (primitive.a[1] + primitive.b[1]) * 0.5f,
                                (primitive.a[2] + primitive.b[2]) * 0.5f};
          const float length = std::sqrt(lengthSq);
          const float nx = axis[0] / length, ny = axis[1] / length, nz = axis[2] / length;
          const float vx = mid[0] - float(eye[0]), vy = mid[1] - float(eye[1]),
                      vz = mid[2] - float(eye[2]);
          float px = ny * vz - nz * vy, py = nz * vx - nx * vz, pz = nx * vy - ny * vx;
          const float plen = std::sqrt(px * px + py * py + pz * pz);
          if (plen < 1e-6f)
            continue;                    // a beam pointing at the eye has no on-screen width
          px = px / plen * primitive.width;
          py = py / plen * primitive.width;
          pz = pz / plen * primitive.width;
          const float a0[3] = {primitive.a[0] - px, primitive.a[1] - py, primitive.a[2] - pz};
          const float a1[3] = {primitive.a[0] + px, primitive.a[1] + py, primitive.a[2] + pz};
          const float b0[3] = {primitive.b[0] - px, primitive.b[1] - py, primitive.b[2] - pz};
          const float b1[3] = {primitive.b[0] + px, primitive.b[1] + py, primitive.b[2] + pz};
          quad(out, a0, b0, b1, a1, colour);
        } else if (primitive.kind == emit::kDisc) {
          // Glow: hot centre, transparent rim - the falloff rides in the vertex colour.
          const int segments = primitive.segments ? int(primitive.segments) : 24;
          const std::array<float, 4> centre = tint(primitive.colour, 1.f);
          const std::array<float, 4> rim = tint(primitive.colour, 0.f);
          const float *origin = primitive.a.data();
          for (int i = 0; i < segments; ++i) {
            const float t0 = float(i) / segments * 2.f * float(M_PI);
            const float t1 = float(i + 1) / segments * 2.f * float(M_PI);
            float p0[3], p1[3];
            if (primitive.shape == emit::kShapeFlat) {
              p0[0] = origin[0] + std::sin(t0) * primitive.radius; p0[1] = origin[1];
              p0[2] = origin[2] + std::cos(t0) * primitive.radius;
              p1[0] = origin[0] + std::sin(t1) * primitive.radius; p1[1] = origin[1];
              p1[2] = origin[2] + std::cos(t1) * primitive.radius;
            } else {
              p0[0] = origin[0] + (rx * std::cos(t0) + ux * std::sin(t0)) * primitive.radius;
              p0[1] = origin[1] + (ry * std::cos(t0) + uy * std::sin(t0)) * primitive.radius;
              p0[2] = origin[2] + (rz * std::cos(t0) + uz * std::sin(t0)) * primitive.radius;
              p1[0] = origin[0] + (rx * std::cos(t1) + ux * std::sin(t1)) * primitive.radius;
              p1[1] = origin[1] + (ry * std::cos(t1) + uy * std::sin(t1)) * primitive.radius;
              p1[2] = origin[2] + (rz * std::cos(t1) + uz * std::sin(t1)) * primitive.radius;
            }
            push(out, origin, centre);
            push(out, p0, rim);
            push(out, p1, rim);
            emitTriangles += 1;
          }
        } else if (primitive.kind == emit::kRing) {
          const int segments = primitive.segments ? int(primitive.segments) : 32;
          const float inner = std::max(0.f, primitive.radius - primitive.width);
          const float outer = primitive.radius + primitive.width;
          for (int i = 0; i < segments; ++i) {
            const float t0 = float(i) / segments * 2.f * float(M_PI);
            const float t1 = float(i + 1) / segments * 2.f * float(M_PI);
            float i0[3], o0[3], i1[3], o1[3];
            if (primitive.shape == emit::kShapeFlat) {
              i0[0] = primitive.a[0] + std::sin(t0) * inner; i0[1] = primitive.a[1];
              i0[2] = primitive.a[2] + std::cos(t0) * inner;
              o0[0] = primitive.a[0] + std::sin(t0) * outer; o0[1] = primitive.a[1];
              o0[2] = primitive.a[2] + std::cos(t0) * outer;
              i1[0] = primitive.a[0] + std::sin(t1) * inner; i1[1] = primitive.a[1];
              i1[2] = primitive.a[2] + std::cos(t1) * inner;
              o1[0] = primitive.a[0] + std::sin(t1) * outer; o1[1] = primitive.a[1];
              o1[2] = primitive.a[2] + std::cos(t1) * outer;
            } else {
              const float c0 = std::cos(t0), s0 = std::sin(t0);
              const float c1 = std::cos(t1), s1 = std::sin(t1);
              i0[0] = primitive.a[0] + (rx * c0 + ux * s0) * inner;
              i0[1] = primitive.a[1] + (ry * c0 + uy * s0) * inner;
              i0[2] = primitive.a[2] + (rz * c0 + uz * s0) * inner;
              o0[0] = primitive.a[0] + (rx * c0 + ux * s0) * outer;
              o0[1] = primitive.a[1] + (ry * c0 + uy * s0) * outer;
              o0[2] = primitive.a[2] + (rz * c0 + uz * s0) * outer;
              i1[0] = primitive.a[0] + (rx * c1 + ux * s1) * inner;
              i1[1] = primitive.a[1] + (ry * c1 + uy * s1) * inner;
              i1[2] = primitive.a[2] + (rz * c1 + uz * s1) * inner;
              o1[0] = primitive.a[0] + (rx * c1 + ux * s1) * outer;
              o1[1] = primitive.a[1] + (ry * c1 + uy * s1) * outer;
              o1[2] = primitive.a[2] + (rz * c1 + uz * s1) * outer;
            }
            quad(out, i0, o0, o1, i1, colour);
          }
        } else if (primitive.kind == emit::kBolt) {
          // Bolts carry pixel extents: they are converted at this camera's depth, so a volley
          // keeps its size whatever the player's zoom is.
          const float scale = eyeDepth(primitive.a.data()) / focal;
          const float halfLength = std::max(0.005f, primitive.radius * scale);
          const float halfWidth = std::max(0.005f, primitive.width * scale);
          float dx = 1.f, dy = 0.f;
          if (primitive.shape != emit::kShapeSquare) {
            dx = primitive.b[0] * rx + primitive.b[1] * ry + primitive.b[2] * rz;
            dy = primitive.b[0] * ux + primitive.b[1] * uy + primitive.b[2] * uz;
            const float len = std::sqrt(dx * dx + dy * dy);
            if (len < 1e-4f) { dx = 1.f; dy = 0.f; } else { dx /= len; dy /= len; }
          }
          const float along[3] = {(rx * dx + ux * dy) * halfLength,
                                  (ry * dx + uy * dy) * halfLength,
                                  (rz * dx + uz * dy) * halfLength};
          const float across[3] = {(rx * -dy + ux * dx) * halfWidth,
                                   (ry * -dy + uy * dx) * halfWidth,
                                   (rz * -dy + uz * dx) * halfWidth};
          float corners[4][3];
          for (int corner = 0; corner < 4; ++corner) {
            const float sAlong = (corner == 1 || corner == 2) ? 1.f : -1.f;
            const float sAcross = (corner >= 2) ? 1.f : -1.f;
            corners[corner][0] = primitive.a[0] + along[0] * sAlong + across[0] * sAcross;
            corners[corner][1] = primitive.a[1] + along[1] * sAlong + across[1] * sAcross;
            corners[corner][2] = primitive.a[2] + along[2] * sAlong + across[2] * sAcross;
          }
          quad(out, corners[0], corners[1], corners[2], corners[3], colour);
        } else if (primitive.kind == emit::kShield) {
          // Instanced: the mesh is built once per detail level in view space, and this record
          // only says where this shell sits, how big it is, and what colour and fade it carries.
          // A standing shield shell. The tint and the fade are Python's (the strength ramp that
          // tells the player how much field is left); the rim falloff and the detail level come
          // from this camera, like every other apparent-size decision in this window.
          const double tint[3] = {primitive.colour[0] / 255.0, primitive.colour[1] / 255.0,
                                  primitive.colour[2] / 255.0};
          const double fade = primitive.colour[3] / 255.0;
          // A bubble must stay readable when it is small; the renderer grows it until it is at
          // least SHIELD_MIN_PX across, so the same floor is applied here at this camera.
          const float depth = eyeDepth(primitive.a.data());
          float radius = primitive.radius;
          if (focal > 0.f && depth > 0.f) {
            const float pxPerWorld = focal / depth;
            const float floorRadius = 0.5f * kShieldMinPx / std::max(pxPerWorld, 1e-6f);
            radius = std::max(radius, floorRadius);
          }
          const float apparent = focal > 0.f && depth > 0.f
                                     ? (focal / depth) * radius * 2.f
                                     : 0.f;
          const int detail = fx::shieldDetail(apparent);
          const double centre[3] = {primitive.a[0], primitive.a[1], primitive.a[2]};
          const fx::ShellInstance shell =
              fx::shellInstance(centre, double(radius), tint, fade, view);
          // Eight floats per shell: the whole per-frame CPU cost of a bubble.
          std::vector<float>& out = shieldInstances[detail];
          out.insert(out.end(), {shell.centre[0], shell.centre[1], shell.centre[2], shell.radius,
                                 shell.tint[0], shell.tint[1], shell.tint[2], shell.fade});
          ++shieldShells;
          ++shieldByDetail[detail];
          shieldFade += fade;
        } else if (primitive.kind == emit::kShieldHit || primitive.kind == emit::kHullHit) {
          // A contact is rebuilt here from its parameters, the way a blast is: position, normal,
          // size, age and seed cross, ~90 triangles of curved shell do not. The two camera-dependent
          // numbers - the shield contact's SHIELD_MIN_PX floor and the hull contact's 7 px floor -
          // are applied at this camera, exactly as Python applies them at its own.
          const bool shieldContact = primitive.kind == emit::kShieldHit;
          const float depth = eyeDepth(primitive.a.data());
          const double pxPerWorld =
              (focal > 0.f && depth > 0.f) ? double(focal) / double(depth) : 0.0;
          const double centre[3] = {primitive.a[0], primitive.a[1], primitive.a[2]};
          const double normal[3] = {primitive.b[0], primitive.b[1], primitive.b[2]};
          const double right3[3] = {rightVec[0], rightVec[1], rightVec[2]};
          const double up3[3] = {upVec[0], upVec[1], upVec[2]};
          // The contact size is the effect's own, carried in the shape byte in tenths for a shell
          // contact (its cap aperture is a function of it); a hull contact carries it in `radius`.
          const double size = shieldContact ? double(primitive.shape) / 10.0
                                            : double(primitive.radius);
          std::vector<fx::HitVertex> rebuilt, rebuiltSmoke;
          fx::HitCounters counters;
          fx::appendHit(shieldContact, centre, normal, double(primitive.radius), size,
                        double(primitive.width), uint32_t(primitive.segments),
                        (primitive.flags & emit::kFlagVisualContact) != 0, pxPerWorld, right3, up3,
                        rebuilt, rebuiltSmoke, &counters);
          for (const auto& v : rebuilt)
            hitTriangles.push_back({float(v.x), float(v.y), float(v.z), float(v.r), float(v.g),
                                    float(v.b), float(v.a)});
          for (const auto& v : rebuiltSmoke)
            hitSmokeVerts.push_back({float(v.x), float(v.y), float(v.z), float(v.r),
                                     float(v.g), float(v.b), float(v.a)});
          ++hitContacts;
          if (shieldContact)
            ++hitShieldContacts;
          else
            ++hitHullContacts;
          hitSparks += counters.sparkTriangles;
          hitTrianglesCount += counters.capTriangles + counters.rippleTriangles;
          hitSmokeTris += counters.smokeTriangles;
        } else if (primitive.kind == emit::kExplosion) {
          // A blast is rebuilt from its parameters with the renderer's own formulas. Smoke blends
          // normally (it is a dark mass), everything else adds light, so the two are separated and
          // the normal-blend pass is drawn first.
          std::vector<fx::Vertex> blastAdditive, blastNormal;
          std::vector<double> fxCounters;
          fx::appendExplosion(blastAdditive, blastNormal, primitive.a.data(), primitive.radius,
                              primitive.width, uint32_t(primitive.segments), rightVec, upVec,
                              eyeVec, &fxCounters);
          fxLayers = size_t(fxCounters.empty() ? 0 : fxCounters[0]);
          fxAlphaSum = fxCounters.size() > 1 ? fxCounters[1] : 0.0;
          fxVertexCount = blastAdditive.size() + blastNormal.size();
          for (const auto& v : blastNormal)
            smokeTriangles.push_back({v.x, v.y, v.z, v.r, v.g, v.b, v.a});
          for (const auto& v : blastAdditive)
            nearTriangles.push_back({v.x, v.y, v.z, v.r, v.g, v.b, v.a});
          emitTriangles += (blastAdditive.size() + blastNormal.size()) / 3;
        }
      }
      auto submitEmissive = [&](const std::vector<CueVertex> &verts, bool depthTest,
                                bool additive) {
        if (verts.empty())
          return;
        // A transient vertex buffer is finite (a few hundred thousand vertices), so a large list is
        // submitted in chunks. The count asked for must be the number of vertices still wanted:
        // `getAvailTransientVertexBuffer` returns min(available, requested), so asking for one
        // vertex returns exactly one and the loop degenerates into a draw call per vertex. A frame
        // with a few hundred damage contacts holds ~75k vertices; that burned bgfx's 65535
        // draw-call ceiling and every later draw - the standing shield shells included - was
        // silently discarded, with no failed call and no dropped-vertex count to show for it.
        size_t cursor = 0;
        while (cursor < verts.size()) {
        const uint32_t wanted = uint32_t(std::min<size_t>(verts.size() - cursor, 0xFFFFFFFFu));
        const uint32_t avail = bgfx::getAvailTransientVertexBuffer(wanted, cueLayout);
        const size_t want = std::min<size_t>(verts.size() - cursor, avail);
        if (want == 0) {
          emitDropped += uint32_t(verts.size() - cursor);   // counted, never silently squeezed
          break;
        }
        const uint32_t count = uint32_t(want);
        bgfx::TransientVertexBuffer tvb;
        bgfx::allocTransientVertexBuffer(&tvb, count, cueLayout);
        std::memcpy(tvb.data, verts.data() + cursor, count * sizeof(CueVertex));
        cursor += want;
        bgfx::setVertexBuffer(0, &tvb);
        // BGFX_STATE_BLEND_ADD is (ONE, ONE): alpha is ignored and every faint shell lands at
        // full brightness, which turns a soft fireball into a solid white disc. Additive blending
        // that honours the vertex alpha is (SRC_ALPHA, ONE).
        uint64_t state = BGFX_STATE_WRITE_RGB | BGFX_STATE_MSAA |
                         (additive ? BGFX_STATE_BLEND_FUNC(BGFX_STATE_BLEND_SRC_ALPHA,
                                                          BGFX_STATE_BLEND_ONE)
                                   : BGFX_STATE_BLEND_ALPHA);
        if (depthTest)
          state |= BGFX_STATE_DEPTH_TEST_LESS;
        bgfx::setState(state);
        bgfx::submit(1, cueProgram);
        }
      };
      // Shield instance memory is claimed NOW, before any large triangle batch: transient vertex and
      // instance memory come out of one per-frame pool in allocation order, and a frame with a few
      // hundred damage contacts allocates ~75k vertices of triangles, which is enough to leave the
      // instanced shell draws with nothing. The symptom is silent - the shells simply do not appear,
      // and `dropped_vertices` stays 0 because the instance path counts its own shortfall. Claiming
      // the instances first and submitting them last keeps both the memory and Python's layering
      // (`_draw_effects` at renderer.py:502 runs before `_draw_shields` at :510).
      struct ShieldDraw {
        bgfx::InstanceDataBuffer buffer;
        uint32_t count = 0;
        int detail = 0;
      };
      std::vector<ShieldDraw> shieldDraws;
      for (int detail = 0; detail < 3; ++detail) {
        const std::vector<float>& bucket = shieldInstances[detail];
        size_t cursor = 0;
        while (cursor < bucket.size()) {
          const uint32_t count = uint32_t((bucket.size() - cursor) / 8);
          const uint32_t avail = bgfx::getAvailInstanceDataBuffer(count, 32);
          const uint32_t take = std::min(count, avail);
          if (take == 0) {
            emitDropped += uint32_t((bucket.size() - cursor) / 8 * shieldMeshVertices[detail]);
            break;
          }
          ShieldDraw draw;
          draw.count = take;
          draw.detail = detail;
          bgfx::allocInstanceDataBuffer(&draw.buffer, take, 32);
          std::memcpy(draw.buffer.data, bucket.data() + cursor, size_t(take) * 8 * sizeof(float));
          cursor += size_t(take) * 8;
          shieldDraws.push_back(draw);
        }
      }
      submitEmissive(farTriangles, true, true);
      submitEmissive(smokeTriangles, false, false);
      submitEmissive(nearTriangles, false, true);
      // Contacts after the light and before the shells, which is where Python draws them: a marking
      // on armour is a surface fact, alpha-blended, above opaque armour and under a standing field.
      submitEmissive(hitSmokeVerts, false, false);
      submitEmissive(hitTriangles, false, false);
      // Shield shells are additive, depth-tested and never write depth - the ship inside must read
      // through its own field, and two translucent shells must not fight over the depth buffer.
      for (const ShieldDraw& draw : shieldDraws) {
        bgfx::setVertexBuffer(0, shieldMesh[draw.detail]);
        bgfx::setInstanceDataBuffer(&draw.buffer);
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_MSAA | BGFX_STATE_DEPTH_TEST_LESS |
                       BGFX_STATE_BLEND_FUNC(BGFX_STATE_BLEND_SRC_ALPHA, BGFX_STATE_BLEND_ONE));
        bgfx::submit(1, shieldProgram);
        shieldVertices += size_t(draw.count) * shieldMeshVertices[draw.detail];
      }
    }
    if (topRing) {
      const auto available = topRing->published();
      if (available > topSequence && topRing->read_at_sequence(available - 1, available, topPayload)) {
        topSequence = available;
        try {
          // Whole immutable snapshots: no dependency on missed patch/keyframe history.
          if (topPayload != topPrevious) {
            auto candidate = armada::top_hud::decode(topPayload);
            topModel = std::move(candidate);
            topPrevious = topPayload;
            topDirty = true;
          }
          topFrames++;
        } catch (const std::exception &e) {
          topDecodeFailures++;
          std::cerr << "native top HUD decode failed: " << e.what() << std::endl;
        }
      }
      if (topModel) ensureHudAtlas(height);
      if (topModel && (topDirty || width != topWidth || height != topHeight)) {
        topMesh = armada::top_hud::layout(*topModel, width, height, *topFont);
        topWidth = width; topHeight = height; topDirty = false;
      }
      if (!topMesh.vertices.empty()) {
        const auto nv = uint32_t(topMesh.vertices.size()), ni = uint32_t(topMesh.indices.size());
        if (bgfx::getAvailTransientVertexBuffer(nv, topLayout) < nv ||
            bgfx::getAvailTransientIndexBuffer(ni) < ni)
          throw DeviceError("Native HUD transient buffer exhausted");
        bgfx::TransientVertexBuffer vb;
        bgfx::TransientIndexBuffer ib;
        bgfx::allocTransientVertexBuffer(&vb, nv, topLayout);
        bgfx::allocTransientIndexBuffer(&ib, ni);
        std::memcpy(vb.data, topMesh.vertices.data(), nv * sizeof(armada::top_hud::Vertex));
        std::memcpy(ib.data, topMesh.indices.data(), ni * sizeof(uint16_t));
        bgfx::setViewRect(2, 0, 0, uint16_t(width), uint16_t(height));
        bgfx::setViewMode(2, bgfx::ViewMode::Sequential);
        bgfx::setVertexBuffer(0, &vb);
        bgfx::setIndexBuffer(&ib);
        bgfx::setTexture(0, topSampler, *topTexture);
        bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A | BGFX_STATE_BLEND_ALPHA);
        bgfx::submit(2, topProgram);
        topDrawn++;
      }
    }
    if (vectorRing) {
      // A complete candidate (geometry and fog together) replaces the last-good
      // presentation only after decoding and bounded CPU layout both succeed.
      auto installVectorMesh = [&](armada::vector_hud::DrawList candidate) {
        const bool changedFog = candidate.fogWidth != vectorMesh.fogWidth ||
            candidate.fogHeight != vectorMesh.fogHeight || candidate.fogPixels != vectorMesh.fogPixels;
        bgfx::TextureHandle replacement = BGFX_INVALID_HANDLE;
        if (changedFog && !candidate.fogPixels.empty()) {
          replacement = bgfx::createTexture2D(uint16_t(candidate.fogWidth), uint16_t(candidate.fogHeight),
              false, 1, bgfx::TextureFormat::RGBA8,
              BGFX_SAMPLER_MIN_POINT | BGFX_SAMPLER_MAG_POINT |
                  BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP,
              bgfx::copy(candidate.fogPixels.data(), uint32_t(candidate.fogPixels.size())));
          if (!bgfx::isValid(replacement)) throw DeviceError("Native minimap fog upload failed");
        }
        if (changedFog) {
          if (bgfx::isValid(*vectorFogTexture)) bgfx::destroy(*vectorFogTexture);
          *vectorFogTexture = replacement;
          if (bgfx::isValid(replacement)) ++vectorFogUploads;
        }
        vectorMesh = std::move(candidate);
        vectorWidth = width; vectorHeight = height;
      };
      const auto available = vectorRing->published();
      if (available > vectorSequence &&
          vectorRing->read_at_sequence(available - 1, available, vectorPayload)) {
        vectorSequence = available;
        std::optional<armada::vector_hud::Model> candidate;
        try {
          if (vectorPayload != vectorPrevious) candidate = armada::vector_hud::decode(vectorPayload);
        } catch (const std::exception &e) {
          ++vectorDecodeFailures;
          std::cerr << "native vector HUD decode failed: " << e.what() << std::endl;
        }
        if (candidate) {
          ensureHudAtlas(height); // trusted asset/resource failure is not a bad wire record
          std::optional<armada::vector_hud::DrawList> mesh;
          try {
            mesh = armada::vector_hud::layout(*candidate, width, height, *topFont);
          } catch (const std::exception &e) {
            ++vectorDecodeFailures;
            std::cerr << "native vector HUD layout rejected: " << e.what() << std::endl;
          }
          if (mesh) {
            installVectorMesh(std::move(*mesh));
            vectorModel = std::move(candidate);
            vectorPrevious.swap(vectorPayload);
            ++vectorFrames;
          }
        } else if (vectorPayload == vectorPrevious) {
          ++vectorFrames;
        }
      }
      if (vectorModel && (width != vectorWidth || height != vectorHeight)) {
        ensureHudAtlas(height);
        installVectorMesh(armada::vector_hud::layout(*vectorModel, width, height, *topFont));
      }
      if (!vectorMesh.vertices.empty()) {
        const auto nv = uint32_t(vectorMesh.vertices.size()), ni = uint32_t(vectorMesh.indices.size());
        if (bgfx::getAvailTransientVertexBuffer(nv, topLayout) < nv ||
            bgfx::getAvailTransientIndexBuffer(ni) < ni) {
          ++vectorTransientDrops; // skip the complete slice, never submit half its controls
        } else {
          bgfx::TransientVertexBuffer vb;
          bgfx::TransientIndexBuffer ib;
          bgfx::allocTransientVertexBuffer(&vb, nv, topLayout);
          bgfx::allocTransientIndexBuffer(&ib, ni);
          std::memcpy(vb.data, vectorMesh.vertices.data(), nv * sizeof(armada::top_hud::Vertex));
          std::memcpy(ib.data, vectorMesh.indices.data(), ni * sizeof(uint16_t));
          bgfx::setViewRect(2, 0, 0, uint16_t(width), uint16_t(height));
          bgfx::setViewMode(2, bgfx::ViewMode::Sequential);
          for (const auto &batch : vectorMesh.batches) {
            bgfx::setVertexBuffer(0, &vb);
            bgfx::setIndexBuffer(&ib, batch.firstIndex, batch.indexCount);
            bgfx::setTexture(0, topSampler, batch.textureKind == 1 ? *vectorFogTexture : *topTexture);
            bgfx::setState(BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A | BGFX_STATE_BLEND_ALPHA);
            bgfx::submit(2, topProgram);
          }
          ++vectorDrawn;
        }
      }
    }
    // W03: the unmigrated HUD/application overlays composite above native UI.
    if (uiRing) {
      const uint64_t available = uiRing->published();
      if (available > uiSequence && uiRing->read_at_sequence(available - 1, available, uiPayload)) {
        uiSequence = available;
        try {
          const auto frame = hud::decode(uiPayload);
          if (!bgfx::isValid(uiTexture) || frame.width != uiWidth || frame.height != uiHeight) {
            if (bgfx::isValid(uiTexture))
              bgfx::destroy(uiTexture);
            uiWidth = frame.width;
            uiHeight = frame.height;
            // Point sampling with the UV clamp: the HUD is presented one texel per pixel, so
            // linear filtering can only smear a texel into its neighbour.
            uiTexture = bgfx::createTexture2D(uiWidth, uiHeight, false, 1,
                                              bgfx::TextureFormat::RGBA8,
                                              BGFX_TEXTURE_NONE | BGFX_SAMPLER_MIN_POINT |
                                                  BGFX_SAMPLER_MAG_POINT | BGFX_SAMPLER_U_CLAMP |
                                                  BGFX_SAMPLER_V_CLAMP);
            if (!bgfx::isValid(uiTexture))
              throw DeviceError("HUD texture creation failed");
          }
          // A late-attaching window has no base surface: patches before the first full frame
          // would land on an uninitialised texture, so they are dropped (and counted).
          if (!frame.full && uiFullFrames == 0) {
            uiSkippedPatches += frame.patches.size();
            continue;
          }
          for (const auto &patch : frame.patches) {
            const bgfx::Memory *mem =
                bgfx::copy(patch.rgba.data(), uint32_t(patch.rgba.size()));
            bgfx::updateTexture2D(uiTexture, 0, 0, patch.rect.x, patch.rect.y, patch.rect.w,
                                  patch.rect.h, mem, uint32_t(patch.rect.w) * 4);
            uiPatches++;
            uiBytes += patch.rgba.size();
          }
          frame.full ? uiFullFrames++ : 0;
          uiFrames++;
        } catch (const std::exception &e) {
          // A malformed HUD payload is dropped, counted, and never half-applied: the texture keeps
          // the last good frame and the console says why.
          uiDecodeFailures++;
          std::cerr << "overlay decode failed: " << e.what() << std::endl;
        }
      }
      float identity[16] = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
      if (bgfx::isValid(uiTexture) && uiFullFrames > 0) {
        bgfx::setViewRect(3, 0, 0, uint16_t(width), uint16_t(height));
        bgfx::setViewTransform(3, identity, identity);
        bgfx::setVertexBuffer(0, uiVbo);
        bgfx::setIndexBuffer(uiIbo);
        bgfx::setTexture(0, uiSampler, uiTexture);
        bgfx::setState(o.hudOnly && !topRing && !vectorRing ? (BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A)
                                 : (BGFX_STATE_WRITE_RGB | BGFX_STATE_WRITE_A |
                                    BGFX_STATE_BLEND_ALPHA));
        bgfx::submit(3, uiProgram);
        bgfx::touch(3);
      }
    }
    bgfx::setDebug(overlay && !o.hudOnly ? BGFX_DEBUG_TEXT : BGFX_DEBUG_NONE);
    bgfx::dbgTextClear();
    if (overlay && !o.hudOnly) {
      bgfx::dbgTextPrintf(1, 1, 0x0f, "STAR ARMADA / %s / %s",
                          live ? "W02 LIVE RING" : "W01 OFFLINE",
                          bgfx::getRendererName(bgfx::getRendererType()));
      size_t drawnInstances = 0;
      for (const auto &group : groups)
        drawnInstances += group.instances.size() / 20;
      bgfx::dbgTextPrintf(
          1, 3, 0x07,
          "%zu mesh instances | %zu unique meshes | %zu triangles/pass",
          drawnInstances, groups.size(), drawnTriangles);
      bgfx::dbgTextPrintf(
          1, 5, 0x07,
          "Drag orbit | wheel zoom | WASD pan | 1 fleet 2 capital 3 station");
      bgfx::dbgTextPrintf(1, 6, 0x07,
                          "Shift+S PNG | H shadows (%s) | Esc quit",
                          shadows ? "ON" : "OFF");
      const auto *st = bgfx::getStats();
      if (live)
        bgfx::dbgTextPrintf(1, 8, 0x0b,
                            "GPU %.2f ms | submits %u | live: %llu frames adopted, "
                            "%llu dropped, decode %.2f ms, %llu behind",
                            st->gpuTimerFreq
                                ? 1000.0 *
                                      double(st->gpuTimeEnd - st->gpuTimeBegin) /
                                      st->gpuTimerFreq
                                : 0,
                            st->numDraw,
                            (unsigned long long)live->adopted,
                            (unsigned long long)live->dropped,
                            live->decode_ms.empty() ? 0.0 : live->decode_ms.back(),
                            (unsigned long long)(live->age_frames.empty()
                                                     ? 0
                                                     : live->age_frames.back()));
      else
        bgfx::dbgTextPrintf(1, 8, 0x0b,
                            "GPU %.2f ms | submits %u | fixed scene: NO "
                            "simulation, fog, HUD or VFX",
                            st->gpuTimerFreq
                                ? 1000.0 *
                                      double(st->gpuTimeEnd - st->gpuTimeBegin) /
                                      st->gpuTimerFreq
                                : 0,
                            st->numDraw);
    }
    // A frame-counted capture cannot fire in a duration-bounded live session, so the
    // live path arms it on elapsed time instead, late enough to leave frames for delivery.
    const bool shot_due =
        !o.shot.empty() && !shot_taken && frame > o.warmup &&
        ((o.frames > 0 && frame == std::max(0, o.frames + o.warmup - 5)) ||
         (o.frames == 0 && live && o.seconds > 0.0 &&
          std::chrono::duration<double>(Clock::now() - live_start).count() >=
              o.seconds * 0.85));
    if (shot_due) {
      bgfx::requestScreenShot(BGFX_INVALID_HANDLE, o.shot.string().c_str());
      screenshotExpected++;
      shot_taken = true;
      // The capture is of *this* frame; the loop keeps applying HUD frames afterwards, so the
      // sequence that belongs to the screenshot has to be recorded here.
      uiSequenceAtShot = uiSequence;
    }
    bgfx::Stats drawStats{};
    if (host) {
      bgfx::TextureRegion source{}, destination{};
      source.init(outputColor); destination.init(outputRead);
      bgfx::blit(4, destination, source);
      const uint32_t ready = bgfx::read(destination, host->pixels.data());
      uint32_t completed = bgfx::frame();
      drawStats = *bgfx::getStats();
      // Readback completion is bounded; never expose partially written pixels to Python.
      for (int wait = 0; completed < ready && wait < 8; ++wait) completed = bgfx::frame();
      if (completed < ready) throw DeviceError("Embedded readback failed to complete");
      host->finishFrame();
    } else {
      bgfx::frame();
    }
    if (live)
      live->after_frame();
    const auto end = Clock::now();
    const auto *st = host ? &drawStats : bgfx::getStats();
    if (frame >= o.warmup) {
      wall.push_back(
          std::chrono::duration<double, std::milli>(end - start).count());
      if (st->cpuTimerFreq)
        cpu.push_back(1000.0 * double(st->cpuTimeEnd - st->cpuTimeBegin) /
                      st->cpuTimerFreq);
      if (st->gpuTimerFreq && st->gpuTimeEnd >= st->gpuTimeBegin)
        gpu.push_back(1000.0 * double(st->gpuTimeEnd - st->gpuTimeBegin) /
                      st->gpuTimerFreq);
      draws.push_back(st->numDraw);
    }
    frame++;
  }
  // Counted after the loop: the report object is built before the first frame, when the
  // groups still hold the snapshot, so an in-place lambda would report 752 forever.
  {
    size_t drawn = 0;
    for (const auto &group : groups)
      drawn += group.instances.size() / 20;
    report["instances"] = drawn;
  }
  if (live) {
    report["live"] = {
        {"ring", o.ring.string()},
        {"frames_drawn", frame},
        {"producer_frames_adopted", live->adopted},
        {"producer_frames_dropped", live->dropped},
        {"decode_failures", live->decode_failures},
        {"producer_period_ms", live->period * 1000.0},
        {"decode_ms", stats(live->decode_ms)},
        {"frames_behind", stats(live->age_frames)},
        {"interpolation_alpha", stats(live->alphas)},
        {"gate", {{"unit", "frames behind at draw"}, {"limit", 2}, {"met", true}}},
        {"note", "Producer-only frames: no simulation or HUD is drawn by this window. "
                 "frames_behind counts producer frames published while this frame was "
                 "being drawn; it is not wall-clock latency and not a frame rate."}};
    const auto behind = stats(live->age_frames);
    report["live"]["gate"]["met"] =
        behind.contains("p95_ms") && behind["p95_ms"].get<double>() <= 2.0;
  }
  report["timing_scope"] =
      "Unsynchronized offline mesh-only frame loop; excludes simulation, HUD, "
      "fog, effects, LAN; capture can affect timing";
  report["wall_frame"] = stats(wall);
  report["bgfx_cpu"] = stats(cpu);
  report["gpu_frame"] = stats(gpu);
  report["wall_samples_ms"] = wall;
  report["gpu_samples_ms"] = gpu;
  report["draw_calls_samples"] = draws;
  if (cameraRing)
    // The pose crosses verbatim: `distance_scale` is 1.0 because nothing is compensated here. W05
    // scaled the distance by 0.62 to paper over a projection defect; the defect was `mtxProj`
    // being fed radians (it applies `toRad` itself), so the window framed 1.6x closer than the
    // game and its clicks resolved against a different picture. The projection block below is the
    // guard that keeps that from coming back.
    report["camera_ring"] = {{"ring", o.cameraRing.string()}, {"poses", cameraPoses},
                            {"decode_failures", cameraDecodeFailures}, {"torn", cameraTorn},
                            {"distance_scale", 1.0}};
  // The projection, in numbers rather than in a picture: proj[5] is 1/tan(vfov/2), so a 55 deg
  // vertical field of view at 800 px tall puts it at 1.9203. Anything else is a projection bug.
  report["projection"] = {{"fov_deg", camera.fov},
                          {"fov_input_rad", bx::toRad(camera.fov)},
                          {"proj_scale", projScale},
                          {"expected_scale", 1.0 / std::tan(bx::toRad(camera.fov) * 0.5)},
                          {"focal_px", 0.5 * double(height) /
                               std::tan(bx::toRad(camera.fov) * 0.5)}};
  report["camera"] = {{"target", camera.target},
                      {"distance", camera.distance},
                      {"yaw", camera.yaw},
                      {"pitch", camera.pitch},
                      {"fov", camera.fov}};
  report["inspection_binding"] = inspectionBinding;
  report["control_exercise"] = controlStates;
  report["quality"]["shadows_final"] = shadows;
  // Snapshot what the planet pass held before cleanup destroys the GPU handles, so the report
  // describes the run rather than the teardown.
  const size_t planetTexturesHeld = planetTextures.byName.size();
  const bool planetProgramValid = bgfx::isValid(planetProgram);
  const bool planetVboValid = bgfx::isValid(sphereVbo);
  const bool planetIboValid = bgfx::isValid(sphereIbo);
  std::vector<std::string> planetTextureNames, planetRequestedNames;
  for (const auto &entry : planetTextures.byName)
    planetTextureNames.push_back(entry.first);
  if (live)
    for (const auto &body : live->planets)
      if (planetRequestedNames.size() < 16)
        planetRequestedNames.push_back(body.texture);
  cleanup.run();
  report["screenshots_written"] = callback.shots.load();
    report["hardware"] = {
        {"ring", o.meshRing.empty() ? std::string() : o.meshRing.string()},
        {"meshes", hardwareMeshes.size()},
        {"blobs", hardwareBlobs},
        {"decode_failures", hardwareDecodeFailures},
        {"instances_drawn", hardwareInstances},
        {"dropped_instances", hardwareDropped},
        {"unmeshed", live ? live->surface_unmeshed : 0},
        {"note",
         "surface hardware crosses as a full basis (FLAG_SURFACE_FRAME) that the window copies "
         "verbatim, because a building stands on the foundation the site generator chose; its mesh "
         "arrives on the mesh ring because the offline catalogue cannot name a building that is "
         "constructed during a match; role colours are the shared palette, not on the wire"}};
    report["placement_preview"] = {
        {"instances_drawn", previewInstances},
        {"dropped_instances", previewDropped},
        {"note",
         "translucent rows (tint alpha < 1) submitted blended in the world view after every "
         "depth-tested but not depth-writing, alpha read from the instance row"}};
  if (uiRing) {
    report["hud"] = {{"ring", o.overlayRing.string()},
                     {"texture", {uiWidth, uiHeight}},
                     {"frames_applied", uiFrames},
                     {"applied_sequence", uiSequence},
                     {"screenshot_sequence", uiSequenceAtShot},
                     {"full_frames", uiFullFrames},
                     {"patches_applied", uiPatches},
                     {"bytes_applied", uiBytes},
                     {"decode_failures", uiDecodeFailures},
                     {"skipped_patches_before_keyframe", uiSkippedPatches},
                     {"hud_only", o.hudOnly},
                     {"mode", o.hudOnly ? "presented-unblended (diagnostic)"
                                        : "composited over the scene"}};
  }
  if (emitRing) {
    report["shields"] = {
        {"shells", shieldShells},
        {"vertices", shieldVertices},
        {"instances_by_detail",
         {{"low", shieldByDetail[0]}, {"medium", shieldByDetail[1]}, {"high", shieldByDetail[2]}}},
        {"fade_sum", shieldFade},
        {"min_px", 74.0},
        {"blend", "additive, depth-tested, no depth write"},
        {"note", "one instanced camera-facing hemisphere per shielded unit, alpha baked from "
                 "latitude like renderer.py::_shield_shell_list; tint and fade are Python's "
                 "strength ramp, the detail level and the readability floor come from this "
                 "camera"}};
    report["hits"] = {
        {"contacts", hitContacts},
        {"by_kind", {{"shield", hitShieldContacts}, {"hull", hitHullContacts}}},
        {"triangles", hitTrianglesCount},
        {"smoke_triangles", hitSmokeTris},
        {"spark_triangles", hitSparks},
        {"blend", "alpha, no depth test, no depth write"},
        {"note", "rebuilt from position, normal, size, age and seed like a blast; the seeded spark "
                 "fragments come from this window's port of Python's random.Random, so a seed "
                 "produces the same flecks on both sides"}};
    report["emissive"] = {
        {"ring", o.emitRing.string()},
        {"fx_demo", o.fxDemo},
        {"batches", emitBatches},
        {"decode_failures", emitDecodeFailures},
        {"primitives", emitPrimitives},
        {"triangles", emitTriangles},
        {"dropped_vertices", emitDropped},
        {"blend", "additive, no depth write; bolts sized in pixels at this camera"},
    };
  }
  if (!o.fxDemo.empty() && !emitRing) {
    report["fx_demo"] = {{"spec", o.fxDemo},
                        {"triangles", emitTriangles},
                        {"note", "diagnostic single blast; not a simulation effect"}};
  }
  if (markerRing) {
    report["cues"] = {
        {"ring", o.markerRing.string()},
        {"batches", cueBatches},
        {"decode_failures", cueDecodeFailures},
        {"circles", cueCircles},
        {"markers", cueMarkers},
        {"vertices", cueVertices},
        {"dropped_vertices", cueDropped},
        {"note", "selection rings, planet owner rings and ownership markers decided by the game; "
                 "marker pixel size is derived from this window's camera so the icon stays 9-15 px "
                 "at any zoom; lines are one pixel wide because bgfx has no line width"}};
  }
  if (planetRing) {
    report["planets"] = {
        {"ring", o.planetRing.string()},
        {"textures", planetTexturesHeld},
        {"valid", {{"program", planetProgramValid},
                   {"vbo", planetVboValid},
                   {"ibo", planetIboValid}}},
        {"texture_names", planetTextureNames},
        {"requested_names", planetRequestedNames},
        {"textures_uploaded", planetTextures.uploaded},
        {"textures_reused", planetTextures.reused},
        {"texture_bytes", planetTextures.bytes},
        {"texture_failures", planetTextures.failures},
        {"blobs_applied", planetBlobs},
        {"decode_failures", planetDecodeFailures},
        {"bodies_drawn", planetBodiesDrawn},
        {"frames_with_bodies", planetFramesWithBodies},
        {"untextured_bodies", planetUntextured},
        {"pose_failures", live ? live->planet_pose_failures : 0},
        {"sphere", {{"vertices", sphere.vertices.size() / 8},
                    {"triangles", sphere.indices.size() / 3},
                    {"sample", {sphere.vertices[0], sphere.vertices[1], sphere.vertices[2],
                                sphere.vertices[3], sphere.vertices[4], sphere.vertices[5],
                                sphere.vertices[6], sphere.vertices[7]}}}},
        {"note", "one blob per distinct planet, published once; the body is a unit sphere scaled "
                 "by the frame instance's radius, spun at 1.2 rad/s like the Python renderer"}};
  }
  if (fogRing) {
    report["fog"] = {
        {"ring", o.fogRing.string()},
        {"masks", fogMasks},
        {"generation", fogGeneration},
        {"cells", fogTextureCells},
        {"bounds", fogBounds},
        {"frames_drawn", fogFramesDrawn},
        {"decode_failures", fogDecodeFailures},
        {"blend", "alpha, depth test off (the mask covers unexplored space, not geometry)"},
        {"note", "the mask is Python's classification, one texel per visibility cell; the window "
                 "samples it and decides nothing about visibility"}};
  }
  if (inputOut) {
    report["input"] = {{"ring", o.inputRing.string()},
                       {"batches", inputBatches},
                       {"events", inputEvents},
                       {"published", inputOut->published()},
                       {"unmapped_keys", inputUnmappedKeys},
                       {"coordinates", "window pixels"},
                       {"window", {width, height}},
                       {"authority", "the window records events; the simulation validates "
                                     "and executes every command"},
                       {"exercise", o.inputExercise ? "scripted-synthetic" : "off"}};
  }
  if (topRing) {
    report["native_top_hud"] = {{"ring", o.topHudRing.string()}, {"frames_applied", topFrames},
        {"frames_drawn", topDrawn}, {"decode_failures", topDecodeFailures},
        {"atlas_uploads", topAtlasUploads}, {"drawable", {topWidth, topHeight}},
        {"vertices", topMesh.vertices.size()},
        {"authority", "Python display values/translation; C++ native font/layout/GPU drawing"}};
  }
  if (vectorRing) {
    report["native_vector_hud"] = {{"ring", o.vectorHudRing.string()}, {"frames_applied", vectorFrames},
        {"frames_drawn", vectorDrawn}, {"decode_failures", vectorDecodeFailures},
        {"fog_uploads", vectorFogUploads}, {"transient_drops", vectorTransientDrops},
        {"drawable", {vectorWidth, vectorHeight}}, {"vertices", vectorMesh.vertices.size()},
        {"authority", "Python display/visibility/commands; C++ native vectors/text/minimap"}};
  }
  if (callback.errors || callback.shots < screenshotExpected ||
      (!o.shot.empty() && o.frames > 0 && callback.shots == 0))
    throw std::runtime_error("Screenshot not delivered");
  if (!o.report.empty()) {
    if (!o.report.parent_path().empty())
      fs::create_directories(o.report.parent_path());
    std::ofstream f(o.report);
    f << report.dump(2) << '\n';
    if (!f)
      throw std::runtime_error("Cannot write report");
  }
  if (o.stdoutReport) std::cout << "VIEWER_OK " << report.dump() << std::endl;
  return 0;
}

#ifndef ARMADA_EMBEDDED_BUILD
int main(int argc, char **argv) {
  try {
    return run(options(argc, argv));
  } catch (const DeviceError &e) {
    std::cerr << "E_RENDERER_DEVICE " << e.what() << std::endl;
    return 4;
  } catch (const armada::ProtocolError &e) {
    std::cerr << "E_RENDERER_PROTOCOL " << e.what() << std::endl;
    return 3;
  } catch (const std::exception &e) {
    std::cerr << "VIEWER_ERROR " << e.what() << std::endl;
    return 1;
  }
}

#else
#ifdef _WIN32
#define ARMADA_API extern "C" __declspec(dllexport)
#else
#define ARMADA_API extern "C" __attribute__((visibility("default")))
#endif
ARMADA_API unsigned armada_abi_version() noexcept { return 1; }
ARMADA_API EmbeddedState *armada_open(int argc, char **argv) noexcept {
  try {
    auto parsed = options(argc, argv);
    parsed.inputRing.clear(); // pygame owns physical input in the existing window.
    parsed.frames = 0; parsed.seconds = 0.; parsed.warmup = 0;
    auto *host = new EmbeddedState;
    try {
      host->worker = std::thread([host, parsed] {
        try { run(parsed, host); }
        catch (const std::exception &e) {
          std::lock_guard lock(host->mutex); host->error = e.what();
        }
        catch (...) {
          std::lock_guard lock(host->mutex); host->error = "Unknown native renderer failure";
        }
        std::lock_guard lock(host->mutex);
        host->exited = true; host->cv.notify_all();
      });
    } catch (...) { delete host; throw; }
    return host;
  } catch (...) { return nullptr; }
}
ARMADA_API int armada_frame(EmbeddedState *host, void *out, size_t capacity) noexcept {
  if (!host || !out) return -1;
  try {
    std::unique_lock lock(host->mutex);
    if (host->stop || host->exited) return -2;
    host->completed = false; host->requested = true; host->cv.notify_all();
    if (!host->cv.wait_for(lock, std::chrono::seconds(15), [&] {
          return host->completed || host->exited;
        })) return -3;
    if (!host->error.empty() || !host->completed) return -4;
    if (capacity < host->pixels.size()) return -5;
    std::memcpy(out, host->pixels.data(), host->pixels.size());
    return int(host->pixels.size());
  } catch (...) { return -6; }
}
ARMADA_API int armada_poll(EmbeddedState *host) noexcept {
  if (!host) return 1;
  std::lock_guard lock(host->mutex);
  return host->exited ? (host->error.empty() ? 1 : 2) : 0;
}
ARMADA_API const char *armada_error(EmbeddedState *host) noexcept {
  thread_local std::string message;
  if (!host) return "Native session unavailable";
  std::lock_guard lock(host->mutex);
  message = host->error;
  return message.c_str();
}
ARMADA_API void armada_close(EmbeddedState *host) noexcept {
  if (!host) return;
  { std::lock_guard lock(host->mutex); host->stop = true; host->cv.notify_all(); }
  if (host->worker.joinable()) host->worker.join();
  delete host;
}
#endif
