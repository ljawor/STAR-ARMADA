# Saved Games

Main menu → **Saved Games** continues an existing match without starting a new
simulation. Selecting a row is passive. **Load selected** passes its filepath to
`main.load_saved_game` → the existing `start_game(load_path=...)` → `make_game` →
JSON → `GameState.from_dict` → `GameManager`. Canonical runtime, AI/system timers,
queued commands and campaign mission/progress are restored by the existing codec
and manager. Legacy saves use their existing migration/fallback behavior; the UI
does not invent missing future state. Loading does not replay a fresh mission intro.

## Managed-file contract (fail closed)

The saves directory also holds settings and campaign progression. The library
owns **only** direct regular files with these exact, case-sensitive ASCII names:

- `quicksave.json` — Quick (F5/F9)
- `autosave.json` — Autosave (legacy CLI save name)
- `autosave_<digits>.json` — Autosave (digits are ASCII `0`–`9`)

Malformed JSON in this namespace remains visible/selectable/deletable. Arbitrary
manual/custom filenames are **not** supported by the library: unknown JSON,
settings/campaign (including casing variants), replay JSON, screenshots, nested
files and symlinks are excluded. Existing CLI `--load` still accepts custom file
paths; no files are renamed, migrated or newly classified by decoding their JSON.
No saver format changes are introduced.

**Delete all** streams *all eligible managed files*, not just a visible page or
browser snapshot. It preserves settings, campaign progression, unknown JSON,
replays, screenshots, outside files and symlink/reparse-point children. Selected
filenames and root membership are revalidated on each operation. POSIX deletion
uses pinned no-follow directory descriptors; Windows uses the existing native
`Folder` handle-relative enumeration/deletion backend. Symlinked save/user
directories fail closed; Windows ancestor junctions/reparse points are rejected.
Unsupported unsafe operations fail closed rather than falling back to unlink.

Deletion requires an exclusive red confirmation screen; the seaglass default is
**Cancel**. Enter, keypad Enter and Escape cancel. No underlying row, Load or
navigation controls remain active during confirmation.

## Browsing and loading

- Timestamp-first rows, UTC labels, newest **file modification time** first,
  filename secondary and truncated to measured bounds. Save kind is explicit.
- Six rows per page, pinned Back/Refresh/Previous/Next; selected details and
  seaglass Load on the right, red Delete selected/Delete all.
- Browser scans at most 4096 directory entries, reads at most 64 KiB per eligible
  metadata file, sorts the scanned candidates, and retains the newest 1000.
  Scan/browser limits are visible. Delete all is independent and uncapped.
- No `GameState`/`GameManager` is constructed while browsing or selecting.
  Metadata is advisory: large/legacy/unverified saves are validated on Load.
- Explicit loads read at most 64 MiB plus one sentinel byte and reject excess
  before JSON decoding. Save formats 1–3 (or missing legacy format) are supported;
  future/invalid format values are rejected. Existing ordinary-save migration
  runs first, followed by existing typed validation of the reconstructed candidate.
  Decoding/reconstruction is completed before previous
  recording/network ownership or renderer/HUD/audio resources are torn down.
  Malformed, unsupported/incompatible canonical state, missing files and unsafe
  paths return an error to the usable library. File reads are pinned/no-follow
  for managed saves. Legacy CLI custom loads retain their CLI path semantics.

The screen uses the shared 1120×700 Clean Classic canvas and the existing battle
movie routing (only Replays remains static). Reduced Motion/settings behavior is
unchanged. Seven centered main-menu actions fit the 800×600 baseline.

## Verification

Focused regression command:

```sh
PYTHONPATH=. .venv/bin/python -m unittest tests.test_saved_games tests.test_clean_classic_menu tests.test_splash_movie_integration tests.test_replay_deletion_windows -v
```

Real SDL/OpenGL acceptance, using a **new** scratch output directory:

```sh
PYTHONPATH=. .venv/bin/python tools/diag_saved_games.py --out /path/to/new/scratch-output
```

The diagnostic patches all four persistence constants before any `MenuStack` or
main initialization, uses a disposable user root, the production F5 writer,
actual main-loop Load dispatch, full renderer/HUD/gameplay transition, production
`m00_recovery_drill` campaign restore after its initial trigger and 120 per-tick
full-precision continuation comparisons per resolution.
It captures main/empty/normal/selected/paged/corrupt/confirmation states at
800×600 windowed and 1440×900 actual fullscreen and asserts the actual SDL surface
dimensions, geometry bounds, non-overlapping glyphs, nonblank
framebuffers and zero GL errors. Protected fixture bytes are checked and the
isolated user root is removed even after failures.

`NativeWindowsDeletionTests.test_saved_games_namespace_uncapped_delete_and_safe_read_real_handles`
adds saved-file read/browse/deletion, 4101-file bulk deletion and junction/protected
file assertions to the existing required native Windows class. The Windows
signal workflow already runs the entire class and requires its exact discovered
count, so **no workflow gate change is needed**. macOS portable tests/skips do not
establish native Windows acceptance; that gate remains required before release.
