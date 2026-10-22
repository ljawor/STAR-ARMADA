# Transparent planned station restoration — local evidence

## Cause and restoration

The C++ producer sent only the construction scaffold, omitting the planned station
silhouette previously drawn by the Python renderer. The native fleet fragment
shader also always output alpha 1, so merely setting a transparent instance tint
would not restore it.

The paid queue now publishes the exact full-sized station mesh as a separate
render-only preview: 20% opacity initially, gradually rising to 55%; completion
removes preview/scaffold and leaves the real opaque entity. Scaffold height still
tracks progress. No costs, timing, collision, selection or simulation state changes.
Completed mesh geometry is reused from the preview's cached mesh publication.

Opaque hardware remains in the opaque/shadow path. Translucent previews are
back-to-front, depth-tested but do not write depth or cast a premature solid
shadow. Explicit view order is shadow → opaque → preview/fog → HUD → readback;
the original window receives that same composited output. Fog must cover previews
in unknown areas rather than exposing construction through unexplored cells.

## Actual results

- New CPU red reproduced the missing full station at a paid site.
- Native red: opacity 0.2, 0.55 and 1 rendered identical images. This is a real
  GPU negative control, not an inferred diagnosis from packed records.
- Native green opacity controls and paid early/half/completed captures passed for
  Imperial authored and Rebel station meshes. Hardware decode failures, dropped
  instances and missing meshes were zero in the paid render sequence.
- A naive initial probe demanded late transparent brightness stay below opaque
  brightness. Intersecting authored layers can show bright interiors through the
  preview; that is not guaranteed. Final probe checks convergence to the opaque
  image, nonzero visible preview and distinct early/late states instead. The
  original constant-alpha GPU captures also fail the corrected criterion.
- New view initially collided with embedded readback's existing view ID: standalone
  pictures passed but live fog pixels did not. That failure is retained. Readback
  now has a separate last view, and the same live native fog probe passes.
- 375 targeted Python/integration tests passed, including actual host/join LAN
  reconnect, natural paid UI commands and replay checks. First union failed on
  the recovery harness's assumption that `screen` was a bare assignment target;
  it now also recognizes tuple assignment after the resolution helper change.
  No production recovery behavior was changed for that harness repair.
- 13 native CTest checks passed. Actual main.py match → menu → second match,
  original native host identity, local orbit and natural F5 save passed.

`station-build-sequence.png` is a labelled, unscaled crop of the native Imperial
paid-queue captures. Raw captures were losslessly re-encoded to avoid unnecessarily
large PNG files. These are controlled render fixtures, not a claim of all-station
parity or a recording of a live player match. Receipts, original failures, reports
and source SHA256 pins accompany them. Independent station-only review is pending.

The existing WIP renderer lifecycle/fatal/concurrency/packaging blockers remain;
this restoration is not overall merge/release approval or cross-platform acceptance.
