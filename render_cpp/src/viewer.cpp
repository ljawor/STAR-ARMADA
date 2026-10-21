// Standalone W01 viewer: no authoritative game state and no Python runtime.
#include "camera.hpp"
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
#include <thread>
namespace fs = std::filesystem;
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
struct Callbacks final : bgfx::CallbackI {
  std::atomic<int> shots{0}, errors{0};
  void fatal(const char *, uint16_t, bgfx::Fatal::Enum,
             const char *msg) override {
    std::fprintf(stderr, "BGFX_FATAL %s\n", msg);
    std::abort();
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
  fs::path snapshot, assets, shaders = ARMADA_SHADER_DIR, shot, report;
  int width = 1280, height = 800, frames = 0, warmup = 30, preset = 1, msaa = 4;
  bool shadows = true, overlay = true, validate = false, exercise = false;
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
    else if (k == "--warmup")
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
    else if (k == "--no-overlay")
      o.overlay = false;
    else if (k == "--validate-only")
      o.validate = true;
    else if (k == "--exercise-controls")
      o.exercise = true;
    else if (k == "--help") {
      std::cout
          << "armada_viewer --snapshot scene.snap --assets assets [--frames "
             "180 --report timing.json --screenshot fleet.png]\nMouse drag "
             "orbit | wheel zoom | WASD pan | 1 fleet | 2 capital | 3 station "
             "| S screenshot | F overlay | H shadows | Esc quit\n";
      std::exit(0);
    } else
      throw std::runtime_error("Unknown option: " + k);
  }
  if (o.snapshot.empty() || o.assets.empty())
    throw std::runtime_error("--snapshot and --assets are required");
  if (o.width < 320 || o.height < 240 || o.width > 7680 || o.height > 4320 ||
      o.frames < 0 || o.warmup < 0 || o.preset < 1 || o.preset > 3 ||
      (o.msaa != 0 && o.msaa != 4))
    throw std::runtime_error("Invalid viewer limits");
  return o;
}
static bgfx::ShaderHandle shader(const fs::path &p) {
  std::ifstream f(p, std::ios::binary | std::ios::ate);
  if (!f)
    throw std::runtime_error("Missing shader: " + p.string());
  auto n = f.tellg();
  if (n <= 0 || n > 4 * 1024 * 1024)
    throw std::runtime_error("Invalid shader size");
  auto *m = bgfx::alloc(uint32_t(n));
  f.seekg(0);
  f.read(reinterpret_cast<char *>(m->data), n);
  auto h = bgfx::createShader(m);
  if (!bgfx::isValid(h))
    throw std::runtime_error("Shader rejected: " + p.string());
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
static int run(const Options &o) {
  Callbacks callback;
  Cleanup cleanup;
  auto scene = armada::read_snapshot(o.snapshot);
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
  Json report{{"profile", "W01-offline-mesh-only"},
              {"fixture", scene.at("fixture")},
              {"state_sha256", scene.at("state_sha256")},
              {"metadata", scene.value("metadata", Json::object())},
              {"snapshot_sha256",
               picosha2::hash256_hex_string(armada::read_bytes(o.snapshot))},
              {"unique_meshes", groups.size()},
              {"unique_triangles", triangles},
              {"instances", scene.at("instances").size()},
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
  if (!SDL_Init(SDL_INIT_VIDEO))
    throw std::runtime_error(SDL_GetError());
  cleanup.actions.push_back([] { SDL_Quit(); });
  SDL_Window *window = SDL_CreateWindow(
      "STAR ARMADA | W01 offline native viewer", o.width, o.height,
      SDL_WINDOW_RESIZABLE
#ifdef __APPLE__
          | SDL_WINDOW_METAL
#endif
  );
  if (!window)
    throw std::runtime_error(SDL_GetError());
  cleanup.actions.push_back([window] { SDL_DestroyWindow(window); });
  void *nativeWindow = nullptr;
#ifdef __APPLE__
  SDL_MetalView metal = SDL_Metal_CreateView(window);
  if (!metal)
    throw std::runtime_error(SDL_GetError());
  cleanup.actions.push_back([metal] { SDL_Metal_DestroyView(metal); });
  nativeWindow = SDL_Metal_GetLayer(metal);
#elif defined(_WIN32)
  nativeWindow =
      SDL_GetPointerProperty(SDL_GetWindowProperties(window),
                             SDL_PROP_WINDOW_WIN32_HWND_POINTER, nullptr);
#else
#error "W01 currently targets macOS and Windows"
#endif
  bgfx::renderFrame();
  bgfx::Init init;
  init.callback = &callback;
  init.fallback = false;
#ifdef __APPLE__
  init.type = bgfx::RendererType::Metal;
#else
  init.type = bgfx::RendererType::Direct3D12;
#endif
  int pixelWidth = 0, pixelHeight = 0;
  SDL_GetWindowSizeInPixels(window, &pixelWidth, &pixelHeight);
  init.swapChain.nwh = nativeWindow;
  init.swapChain.width = pixelWidth;
  init.swapChain.height = pixelHeight;
  init.swapChain.flags =
      o.msaa == 4 ? BGFX_SWAP_CHAIN_MSAA_X4 : BGFX_SWAP_CHAIN_NONE;
  if (!bgfx::init(init))
    throw std::runtime_error("bgfx initialization failed (requested native "
                             "backend, no silent fallback)");
  cleanup.actions.push_back([] { bgfx::shutdown(); });
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
      throw std::runtime_error("GPU mesh upload failed");
    const auto handle = g.vbo;
    cleanup.actions.push_back([handle] { bgfx::destroy(handle); });
  }
  auto program = bgfx::createProgram(shader(o.shaders / "vs_fleet.bin"),
                                     shader(o.shaders / "fs_fleet.bin"), true);
  if (!bgfx::isValid(program))
    throw std::runtime_error("Fleet program creation failed");
  cleanup.actions.push_back([program] { bgfx::destroy(program); });
  auto shadowProgram =
      bgfx::createProgram(shader(o.shaders / "vs_shadow.bin"),
                          shader(o.shaders / "fs_shadow.bin"), true);
  if (!bgfx::isValid(shadowProgram))
    throw std::runtime_error("Shadow program creation failed");
  cleanup.actions.push_back([shadowProgram] { bgfx::destroy(shadowProgram); });
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
      throw std::runtime_error("Uniform creation failed");
    cleanup.actions.push_back([handle] { bgfx::destroy(handle); });
  }
  auto depth =
      bgfx::createTexture2D(2048, 2048, false, 1, bgfx::TextureFormat::D16,
                            BGFX_TEXTURE_RT | BGFX_SAMPLER_COMPARE_LEQUAL |
                                BGFX_SAMPLER_U_CLAMP | BGFX_SAMPLER_V_CLAMP);
  if (!bgfx::isValid(depth))
    throw std::runtime_error("Shadow depth texture creation failed");
  cleanup.actions.push_back([depth] { bgfx::destroy(depth); });
  auto shadowFB = bgfx::createFrameBuffer(1, &depth, false);
  if (!bgfx::isValid(shadowFB))
    throw std::runtime_error("Shadow framebuffer creation failed");
  cleanup.actions.push_back([shadowFB] { bgfx::destroy(shadowFB); });
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
  auto previous = Clock::now();
  std::array<float, 3> lightTarget = original.target;
  int screenshotExpected = 0;
  std::vector<Json> controlStates;
  while (running && (o.frames == 0 || frame < o.frames + o.warmup)) {
    const auto start = Clock::now();
    const float dt = std::chrono::duration<float>(start - previous).count();
    previous = start;
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
    SDL_Event ev;
    while (SDL_PollEvent(&ev)) {
      if (ev.type == SDL_EVENT_QUIT)
        running = false;
      else if (ev.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) {
        width = std::max(1, ev.window.data1);
        height = std::max(1, ev.window.data2);
        init.swapChain.width = width;
        init.swapChain.height = height;
        bgfx::reset(BGFX_RESET_NONE, &init.swapChain);
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
        case SDLK_F:
          overlay = !overlay;
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
    const bool *keys = SDL_GetKeyboardState(nullptr);
    camera.pan(float(keys[SDL_SCANCODE_D]) - float(keys[SDL_SCANCODE_A]),
               float(keys[SDL_SCANCODE_W]) - float(keys[SDL_SCANCODE_S]), dt);
    if (o.exercise && (frame == 0 || frame == 5 || frame == 10 || frame == 15))
      controlStates.push_back(Json{{"frame", frame},
                                   {"target", camera.target},
                                   {"distance", camera.distance},
                                   {"yaw", camera.yaw},
                                   {"pitch", camera.pitch}});
    auto eye = camera.eye();
    float view[16], proj[16], lightView[16], lightProj[16], lightVP[16],
        lightMtx[16];
    bx::mtxLookAt(view, {eye[0], eye[1], eye[2]},
                  {camera.target[0], camera.target[1], camera.target[2]},
                  {0, 1, 0}, bx::Handedness::Right);
    bx::mtxProj(proj, camera.fov, float(width) / height, .5f, 150000.f,
                bgfx::getCaps()->homogeneousDepth, bx::Handedness::Right);
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
    bgfx::setViewClear(0, BGFX_CLEAR_DEPTH, 0, 1.f);
    bgfx::setViewFrameBuffer(0, shadowFB);
    bgfx::setViewRect(0, 0, 0, 2048, 2048);
    bgfx::setViewTransform(0, lightView, lightProj);
    bgfx::setViewClear(1, BGFX_CLEAR_COLOR | BGFX_CLEAR_DEPTH, 0x080e1bff, 1.f);
    bgfx::setViewRect(1, 0, 0, uint16_t(width), uint16_t(height));
    bgfx::setViewTransform(1, view, proj);
    bgfx::touch(1);
    const float eyeData[4] = {eye[0], eye[1], eye[2], 1},
                optionData[4] = {shadows ? 1.f : 0.f, 0, 0, 0};
    for (const auto &g : groups) {
      const uint32_t count = uint32_t(g.instances.size() / 20);
      if (!count)
        continue;
      if (bgfx::getAvailInstanceDataBuffer(count, 80) < count)
        throw std::runtime_error(
            "Instance buffer exhausted; refusing partial fleet");
      bgfx::InstanceDataBuffer buffer;
      bgfx::allocInstanceDataBuffer(&buffer, count, 80);
      std::memcpy(buffer.data, g.instances.data(),
                  g.instances.size() * sizeof(float));
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
    }
    bgfx::setDebug(overlay ? BGFX_DEBUG_TEXT : BGFX_DEBUG_NONE);
    bgfx::dbgTextClear();
    if (overlay) {
      bgfx::dbgTextPrintf(1, 1, 0x0f, "STAR ARMADA / W01 OFFLINE / %s",
                          bgfx::getRendererName(bgfx::getRendererType()));
      bgfx::dbgTextPrintf(
          1, 3, 0x07,
          "%zu mesh instances | %zu unique meshes | %zu triangles/pass",
          scene.at("instances").size(), groups.size(), drawnTriangles);
      bgfx::dbgTextPrintf(
          1, 5, 0x07,
          "Drag orbit | wheel zoom | WASD pan | 1 fleet 2 capital 3 station");
      bgfx::dbgTextPrintf(1, 6, 0x07,
                          "Shift+S PNG | F overlay | H shadows (%s) | Esc quit",
                          shadows ? "ON" : "OFF");
      const auto *st = bgfx::getStats();
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
    if (!o.shot.empty() && o.frames > 0 && frame == o.frames + o.warmup - 5) {
      bgfx::requestScreenShot(BGFX_INVALID_HANDLE, o.shot.string().c_str());
      screenshotExpected++;
    }
    bgfx::frame();
    const auto end = Clock::now();
    const auto *st = bgfx::getStats();
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
  report["timing_scope"] =
      "Unsynchronized offline mesh-only frame loop; excludes simulation, HUD, "
      "fog, effects, LAN; capture can affect timing";
  report["wall_frame"] = stats(wall);
  report["bgfx_cpu"] = stats(cpu);
  report["gpu_frame"] = stats(gpu);
  report["wall_samples_ms"] = wall;
  report["gpu_samples_ms"] = gpu;
  report["draw_calls_samples"] = draws;
  report["camera"] = {{"target", camera.target},
                      {"distance", camera.distance},
                      {"yaw", camera.yaw},
                      {"pitch", camera.pitch},
                      {"fov", camera.fov}};
  report["inspection_binding"] = inspectionBinding;
  report["control_exercise"] = controlStates;
  report["quality"]["shadows_final"] = shadows;
  cleanup.run();
  report["screenshots_written"] = callback.shots.load();
  if (callback.errors || callback.shots < screenshotExpected)
    throw std::runtime_error("Screenshot not delivered");
  if (!o.report.empty()) {
    if (!o.report.parent_path().empty())
      fs::create_directories(o.report.parent_path());
    std::ofstream f(o.report);
    f << report.dump(2) << '\n';
    if (!f)
      throw std::runtime_error("Cannot write report");
  }
  std::cout << "VIEWER_OK " << report.dump() << std::endl;
  return 0;
}
int main(int argc, char **argv) {
  try {
    return run(options(argc, argv));
  } catch (const armada::ProtocolError &e) {
    std::cerr << "E_RENDERER_PROTOCOL " << e.what() << std::endl;
    return 3;
  } catch (const std::exception &e) {
    std::cerr << "VIEWER_ERROR " << e.what() << std::endl;
    return 1;
  }
}
