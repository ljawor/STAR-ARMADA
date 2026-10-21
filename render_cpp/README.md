# W01 offline native renderer viewer

This is a **standalone diagnostic tool**, not the game's new renderer. Normal launch,
simulation, LAN, saves/replays, asset approval records and renderer defaults do not change.
The offline camera can orbit/pan/zoom a frozen snapshot; nothing advances the match.

## 1. Build and launch

See `docs/RENDER_PROTOCOL.md` for the W00 envelope. From the repository root:

```sh
cmake -S render_cpp -B render_cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build render_cpp/build --target armada_viewer test_scene test_camera --parallel 4
ctest --test-dir render_cpp/build --output-on-failure
.venv/bin/python tools/render/dump_snapshot.py --out render_cpp/build/fleet.snap
render_cpp/build/armada_viewer --snapshot render_cpp/build/fleet.snap --assets assets
```

The first configure/build fetches pinned upstream dependencies and builds bgfx and shaderc.
It requires a C++20 toolchain, CMake, Git and SDL3 development libraries (`brew install sdl3`
on macOS). No third-party sources or local dependency paths are committed. macOS requests
**Metal**, Windows requests **Direct3D 12**; a failed native backend is not silently replaced
with OpenGL. Windows build/graphics acceptance must be measured on a Windows machine.

## 2. Controls

- Left-drag: orbit. Mouse wheel: zoom. WASD: camera-relative pan.
- `1`: original fixture camera. `2`: close hull inspection. `3`: close station inspection.
- `Shift+S`: save `armada-viewer.png` in the current directory.
- `F`: toggle diagnostic text. `H`: toggle the directional shadow pass. Escape: quit.

The debug overlay is deliberately a diagnostic overlay, not migrated gameplay HUD.
The camera is local; there is no game command/picking or live camera mirror.

## 3. Bounded measurement

```sh
render_cpp/build/armada_viewer --snapshot render_cpp/build/fleet.snap --assets assets \
  --warmup 30 --frames 180 --no-overlay --report render_cpp/build/timing.json
render_cpp/build/armada_viewer --snapshot render_cpp/build/fleet.snap --assets assets \
  --warmup 30 --frames 30 --preset 2 --screenshot render_cpp/build/capital.png \
  --report render_cpp/build/capture.json
```

Keep timings and screenshots in separate runs. Reports include snapshot/state identity,
asset/instance/triangle counts, native backend, requested MSAA, per-frame samples and tails.
They are **unsynchronized offline mesh-only timings**, not full-game FPS, not comparable to
historical `glFinish`-per-stage full benchmarks, and not simulation/LAN throughput.
No VSync request is made; compositor/presentation pacing can still constrain wall time.

`--validate-only --report ...` validates the file and every referenced source mesh without
opening a window. `--exercise-controls` sends synthetic SDL events through the actual event
handler during a bounded run and records the resulting camera states.

## 4. Preserved geometry, explicitly incomplete world

The loader hashes the **existing runtime JSON bytes**, validates indices/counts/finite
numbers and uploads all material roles without triangle reduction or per-role suppression.
Instances sharing a mesh are submitted together. W01's metallic/roughness lighting and
single 2048-square directional shadow map are an experimental presentation, **not an
appearance approval** of any changed model or of the final renderer.

The Python exporter records its fixture, precise state digest, inventory and omissions.
Canonical hull scale is exported rather than camera-dependent gameplay readability scaling.
The native viewer does **not** implement planet surfaces, fog raster, projectiles, shields,
trails, selection/ownership overlays, gameplay HUD, menus, audio, input mapping or simulation.
It draws the mesh instances selected by the offline exporter. An all-visible diagnostic
snapshot must be labeled as such; it is not representative player visibility.

Those differences must not be used to claim a whole-game speedup. W02 live streaming and
W03–W05 parity remain separate gates. No shared-memory protocol or 1 ms serialization claim
is established by this JSON-based offline profile.
