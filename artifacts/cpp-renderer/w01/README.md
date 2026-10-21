# W01 offline viewer evidence

Code/captures: `7bf11d2204b3aca6c82e58943ab71f26613ea5d2`, draft PR #146.

- Start with `review-sheet.png` and `acceptance.json`.
- `fleet-timing.json` is the **capture-free** 240-sample Metal timing run. Other run timings include PNG readback and must not replace it.
- `fleet.snap` / `catalogue.snap` are exact exported W00 frames; every source mesh hash is in `acceptance.json`.
- `python-reference.png/json` is a frozen current production-world reference with normal passes/readability scaling. It is not equivalent to the native mesh-only workload; do not compute a speedup ratio.
- `source-build.log` preserves the initial direct-bx-header failure, repaired in `source-build-fixed.log`. Shader/API build failures and three review-regression RED/GREEN receipts are retained.
- `historical-3ae5bf7/` preserves the first results shown in chat; final acceptance uses the later code pin and reports.
- PNGs are losslessly compressed versions of callback output; source-file and stored-file digests plus unchanged RGBA pixels are recorded separately.
- Raw compiler logs intentionally retain their original trailing whitespace; a directory-scoped `.gitattributes` exemption preserves those receipt bytes without weakening source checks.
- Raw local reproduction scripts retain the machine paths actually used. Portable build/launch commands are in `render_cpp/README.md`; this is not a packaged application or fresh-machine/Windows acceptance.
- `SHA256SUMS.json` pins the complete evidence directory except itself. Verify it with Python hashlib, then verify `acceptance.json` source and mesh pins against the repository.

No owner appearance/camera acceptance, full-game FPS, same-quality speedup, live transport, native Windows, release or default activation is implied. The handoff is `art/manifests/handoffs/rW01-offline-native-viewer.md`.
