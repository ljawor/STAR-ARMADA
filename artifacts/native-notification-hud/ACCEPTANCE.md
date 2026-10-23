# Native INCOMING / lower-centre message — acceptance receipt

Head: the commit this file is published with on `feat/native-notification-hud`.
Capture tool: `tools/render/capture_native_notification_hud_game.py`
(real `main.py --skirmish`, unchanged production while-body executed one frame at a
time, hidden Cocoa window, framebuffer read before the normal flip).

Production checks run for this head:

| Check | Result |
|---|---|
| `pytest tests/test_native_notification_hud.py tests/test_native_notification_capture.py` | 69 passed |
| `cmake --build render_cpp/build-w02` (all native targets, incl. `armada_vector_hud`) | built |
| `ctest --test-dir render_cpp/build-w02` | 15/15 passed |
| HUD regressions (`test_collapsible_hud`, `test_fleet_panel`, `test_hud_compact`, `test_hybrid_hud`, `test_mission_hud_layout`, `test_multiselect_hud`, `test_native_top_hud`, `test_native_vector_hud`, `test_native_vector_integration`, `test_native_vector_probe`, `test_overlay_upload`, `test_render_overlay`, `test_ship_rank_hud`) | 78 tests, OK |
| actual-main capture, 2560x1440 | `passed: true`, protected files unchanged |
| actual-main capture, 1280x720 | `passed: true`, protected files unchanged |

Measured geometry (logical, from `notification-metrics.json`, `construction-en`):

| Case | legacy INCOMING | native INCOMING | legacy flash (measured) | native flash |
|---|---|---|---|---|
| 2560x1440 | 10, 590, 420x196 | 10, 639, 240x147 | 466, 723, 348x35 | 510, 727, 260x27 |
| 1280x720 | 10, 590, 420x196 | 10, 639, 240x147 | 466, 723, 348x35 | 510, 727, 260x27 |

Native INCOMING shares x=10 and width=240 with the approved compact left panel and keeps
its bottom at H-14; the flash keeps its centre anchor and is 0.75 of the legacy measured
card. Pixel deltas are non-zero in every case (`mean_absolute_rgb` 14.08 / 29.45 at
2560x1440, 13.91 / 27.21 at 1280x720), and `state_sha256` is identical before and after
for every case.

Glyphs `△ ✦ ◉` now have native outlines (destruction `✕` already did); EN/PL/DE/RU
strings render without tofu in the inspected captures.

Not proven here: interactive play-through feel, and the owner's visual approval. The
captures are evidence for the bytes at this head only.
