# W11: the window is the default

Nine steps of bridge work mean nothing if the game still draws with the old renderer unless the
player passes a flag. This is the switch, and what it takes to keep the rollback control usable.

## The setting

`DEFAULT_SETTINGS["renderer"]` is `"cpp"`. A launch with no argument uses the native window;
`--renderer legacy` draws with the process's own GL renderer for one session, and the settings screen
has a **Renderer (next session)** row on the first page that flips the stored choice.

Presentation only: the simulation never reads the key, so a LAN match plays identically either way
and a replay does not care which one drew it. A hand-edited `settings.json` naming a renderer that
does not exist reads as the shipped default rather than as a game with no picture - the same
tolerance the volume keys get.

## Three ways to end up with no picture, and what happens now

| situation | behaviour |
|---|---|
| `--renderer legacy` | the GL renderer draws, no window is spawned |
| the viewer binary is missing | `spawn` logs why, returns None, and the loop falls back to legacy with a message |
| the window dies mid-match | the loop notices, says so once, and draws the match here |

A display fault never blanks a match or ends it. That was the rule from W05 and it survives the
default flip.

## Packaging

`star_armada.spec` now ships the viewer (`render_cpp/build-w02/armada_viewer` -> `cpp/armada_viewer`)
and the bgfx shader tree (`render_cpp/shaders` -> `render_cpp/shaders`), and `cpp_window.find_binary`
searches `sys._MEIPASS/cpp/` before the source tree, so a frozen app finds its own window. The mesh
catalogue already ships inside `assets/`.

### The bundle was built and the packaged viewer was run

`pyinstaller star_armada.spec` completes, and the app ships `Contents/Frameworks/cpp/armada_viewer`
with `cpp/shaders/*.bin` beside it, plus `assets/` (including `assets/cpp/catalogue.snap`) and
`visual_packs/`. Running **the packaged binary against only packaged data** -

    "STAR ARMADA.app/Contents/Frameworks/cpp/armada_viewer" \
      --snapshot .../Resources/assets/cpp/catalogue.snap \
      --shaders  .../Frameworks/cpp/shaders --assets .../Resources ...

- drew **5,828 non-background pixels**, the same figure the checkout gives for the starfield, and
  reported no shader or protocol error (`E_FRAME` is the empty ring the probe passed on purpose).

Two packaging faults were found and fixed by doing this, and neither would have been visible from
reading the spec:

1. **Shaders were not shipped at all.** The viewer resolves them from a directory baked in at build
   time (the build tree), so a bundle would have had no shaders; `cpp_window.spawn` now passes
   `--shaders <binary dir>/shaders` when that directory exists.
2. **The first frozen run refused to build its catalogue**: the shipped catalogue names meshes under
   `visual_packs/`, which was not bundled, and `visual_packs` is the shipped *default* model
   selection. It is now shipped, because a bundle without it cannot draw at all.

The launch path inside the app was not exercised end to end (that needs a player to start a match in
a packaged build); what is verified is that the packaged viewer, its shaders and its catalogue work
from inside the bundle.

## Windows

Unchanged and unverified: the ring writer uses POSIX `flock`, the window has only been run on macOS
with Metal, and no D3D12 run exists. `Windows signal` stays disabled by the owner's instruction
("I have canceled the CI checks in Github. We shoudl for now disable them. We will enable them
later"), so nothing on Windows is claimed here.

## What was run

- `main.py --skirmish` with **no renderer argument**: the window spawned (`armada_viewer pid ...`),
  no fallback line, `CPP_EVENT`/`CPP_INPUT`/`CPP_STATE`/`CPP_VIEW` traces present.
- `main.py --skirmish --smoke` (default = cpp): `SMOKE_CPP_OK t=30s winner=None entities={0: 7, 1: 12}`.
- `main.py --skirmish --smoke --renderer legacy`: `SMOKE_DONE t=30s winner=None entities={0: 7, 1: 12}`.
- `tests/test_render_default.py`: 6 tests (default, hand-edited file, settings row, bundle lookup,
  build directory, no viewer).
- Render suites: **217 tests OK**. `ctest`: **12/12 passed**.
