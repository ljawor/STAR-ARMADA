# macOS Bundle Launch Fix

## 1. Cause and repair

The installed v1.0.0 app rendered its menus but returned to the main menu immediately after Launch Skirmish. A disposable diagnostic copy executing the original release main bytecode recorded native poll status 2 and `armada_error == "mesh outside asset root"`.

PyInstaller uses `Contents/Frameworks` for `_MEIPASS`; its `assets` and `visual_packs` entries resolve through symlinks into `Contents/Resources`. Native `scene.hpp::load_mesh` correctly rejected those resolved meshes as outside Frameworks. Frozen macOS `cpp_window.spawn` now derives its native root from the real `assets` directory's parent. Source and Windows launches are unchanged. The C++ containment, parent-traversal and SHA-256 guards are unchanged.

`EmbeddedWindow` intentionally receives the same Resources root, so its worker cwd also becomes Resources. All session paths and the library path are absolute; frozen library discovery uses `_MEIPASS/cpp`. This does not introduce cwd-relative dependencies. Shader discovery remains binary-adjacent. Regression cases cover both mesh namespaces, preserved shader argv, flat frozen macOS layouts, source launches and frozen Windows argv (the latter is not native Windows execution).

## 2. Verification and review

- The new bundle-layout regression failed before the repair and passed after it.
- Independent read-only review confirmed the root cause, repair and unchanged security guard. It found the new test missing from release CI; the follow-up adds an explicit macOS release step plus a packaging-contract test requiring that step before packaging. Both were run locally, including the contract's failing-before/passing-after sequence.
- Final focused Python invocation: 115 passed, 19 subtests passed, 20 existing pygame image deprecation warnings. Modules: `test_macos_bundle_assets`, `test_resolution_runtime`, `test_native_vector_integration`, `test_native_top_hud`, `test_host_window`, `test_release_packaging`, `test_native_worker`.
- Native CTest: 16/16 passed, including the scene loader's symlink-escape negative control.
- An actual newly packaged app was driven through its visible menu controls into a running 2560x1440 fullscreen skirmish. Later capture showed game time 00:39 and the world/HUD still drawing. Its live worker config named Contents/Resources as `--assets`. Captures and full diagnostic logs are local under `~/.hermes/cache/scratch/`.
- Frozen payload validation passed: 3 binaries and 18 shader files. Strict deep code-sign verification passed (local ad-hoc signing, not notarization).
- Local DMG passed `hdiutil verify`; a read-only mount matched all 546 regular non-symlink files against the exercised build, with zero mismatches.

No full application suite or GitHub CI run is claimed. The feature branch has no workflow run; the new macOS step belongs to the tag-triggered release workflow. Owner acceptance, merge and publication remain pending.

## 3. Owner test artifact

Runtime code: `892f8efcaa6230c24edffb471bacf00e75a13ce2`. Subsequent changes only extend tests, CI and this receipt; they do not alter the test app's runtime.

- Local DMG: `~/Downloads/STAR-ARMADA-mac-launch-fix-892f8ef.dmg`
- SHA-256: `03e965edd4d6f9a6c6ee9d21413c08bb2ffa6914b4d68d69792a1a41f2e8c1a2`
- Extracted app: `~/Downloads/STAR-ARMADA-launch-fix-892f8ef/STAR ARMADA.app`

This is an unmerged local test build, still carrying the existing 1.0.0 version label. It also includes the already-landed main changes through `8db12a4`; it is not a byte-identical reissue of the public v1.0.0 tag. Neither `/Applications/STAR ARMADA.app` nor the published release was replaced.
