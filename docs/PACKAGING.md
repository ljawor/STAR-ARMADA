# STAR ARMADA — packaging / release

## What ships
| Platform | Artifact | Built by |
|---|---|---|
| macOS | `STAR-ARMADA-<ver>-mac.dmg` (signed ad-hoc, contains `STAR ARMADA.app`) | `scripts/build_mac.sh` or GitHub Actions |
| Windows | `STAR-ARMADA-<ver>-win.zip` (one-dir, `STAR ARMADA.exe`) | GitHub Actions |

## Local macOS build
```bash
./scripts/build_mac.sh                 # -> dist/STAR-ARMADA-0.2.0-mac.dmg
```
The script uses `.venv` if present, installs `pyinstaller` into it if missing,
runs `star_armada.spec`, ad-hoc codesigns the .app, and wraps it in a DMG.

## Releases
Tag a version and GitHub Actions builds both artifacts automatically:
```bash
git tag v0.2.0 && git push origin v0.2.0
```
Workflow: `.github/workflows/release.yml` — attaches the DMG and ZIP to the
GitHub release for the tag.

## Notes
- Assets are bundled via `datas=[("assets", "assets")]`; `DataStore` resolves
  them relative to `sys._MEIPASS` when frozen (see `main.py::_resource_root`).
- SDL/pygame on macOS needs a real window server — smoke mode in a frozen app
  still opens a window; CI builds are artifact-only (no run test).
- The DMG is ad-hoc signed (runs locally; for distribution outside your machine
  users right-click → Open the first time, or you add real Developer ID signing).