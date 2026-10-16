# Versioned asset schemas

The machine-checked half of `docs/ASSET_EXTENSION_CONTRACT.md`. Everything here is normative: if a
document does not validate, the build refuses it.

```
python3 tools/art/validate_contract.py          # human-readable, exit 0/1
python3 tools/art/validate_contract.py --json   # machine-readable
python3 -m unittest tests.test_asset_contract   # the same check, in the suite
```

## Layout

```
model-manifest.schema.json   one immutable description of a renderable model
binding-registry.schema.json canonical identity -> asset id
visual-pack.schema.json      render-only pack: replaces core bindings, adds namespaced models
examples/manifests/          the three approved assets, migrated from the specimen exports
examples/core-registry.json  registry excerpt: approved trio plus pending/legacy rows
examples/packs/              one replacement pack and one additive pack, with their payloads
examples/invalid/            24 negative controls: each must be rejected with the code in EXPECTED.json
```

## Version policy

- The document format is identified by `contract` (a string id) plus `contract_major` (an integer).
  Both are required, and an unknown combination fails loudly: a newer export is never reinterpreted
  as an older one.
- `contract_major` bumps when a document that validated before would mean something different
  now — a removed field, a changed meaning, a new required field. Adding an optional field is a
  minor change and does not bump it.
- The exporter's payload format is versioned separately (`export.contract`), because a model can
  legitimately be re-exported into a new payload format without the manifest's meaning changing.
- A new material role is a new major version with a declared fallback, not a new enum value.

## The validator's guarantees

`tools/art/validate_contract.py` implements a documented subset of JSON Schema (`type`,
`required`, `additionalProperties`, `properties`, `items`, `enum`, `const`, `pattern`, `minItems`,
`maxItems`, `uniqueItems`, `minProperties`, `minimum`, `maximum`, `exclusiveMinimum`, `minLength`,
`maxLength`, `$ref` to `#/$defs/...`). It refuses to skip a keyword it does not implement, so a
schema can never be half-enforced by accident. It adds no dependency: `jsonschema` is not in
`requirements.txt` and is not required here.

On top of structure it checks: recomputed revision, pinned file existence/size/hash, the payload as
geometry (finite positions, indices inside the vertex array, `triangle_count`), envelope
containment, the claimed material roles against the payload, path safety including symlink escape,
duplicate bindings and pack entries, additive/core collisions, additive packs without a gameplay
mod, unresolved core bindings, unknown contracts, and stale or evidence-less approvals.

And it refuses to pass on valid input alone: every rejection rule above has a negative control in
`examples/invalid/`, with the expected code in `EXPECTED.json`. A validator that only ever sees
valid documents proves nothing.
