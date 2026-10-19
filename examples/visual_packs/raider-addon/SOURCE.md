# S08 derived fixture provenance

Original design: Lukasz Jawor; licence declaration: original (as in source manifest).
Derived using `tools/art/build_s08_examples.py` v1; no Blender was run.
The input is the evaluated Blender 5.0.1 bevel export recorded in `art/manifests/provenance/rebel-frigate.json`, not reconstructed geometry.
Only identity/contract metadata and the trim/accent material-role bijection change; vertices, normals, indices, bounds and triangle count remain unchanged.
The original approval applies only to the original revision. This derived fixture has no owner appearance approval and does not claim one.
The original .blend and export remain in the repository, not in this pack.

## Read-only repository inputs (SHA-256)

- `art/blender/alliance_frigate.blend`: `721693dce2de5919e941dd778129c409864e5b78499604b65e1f2e59bc17dd49`
- `assets/models/alliance_frigate.mesh.json`: `8562c3c85424d87839b580a495f8f5744cf96e9b06d189eaa78fd867a4e6aa32`
- `assets/models/manifests/alliance_frigate.json`: `2a4394117ce2770850639ab6559a386996010478c10f13dd5de9fe7374363e3a`
- `art/manifests/provenance/rebel-frigate.json`: `5952841e6a84c9076fad76bcd078e3dd70aec181de18119962ec6ada3dc1d7ce`
- `tools/art/build_alliance_frigate.py`: `8a3822c0d39dca356a605f185a1feceaeaa8c2c97b827cee1d0a5265f84b0a28`

Derived asset: `example:raiders/scout`; revision: `d70f0cc01b5e39ba56409781e41ccf212dda52b13048b3296c4f575926ff6ca6`.
Geometry: 4424 vertices, 7708 triangles, six roles, one LOD, no textures.
