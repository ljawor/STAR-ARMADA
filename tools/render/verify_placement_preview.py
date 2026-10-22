"""Measure the station placement preview (#171) in the native window.

The preview crosses as one ordinary fleet instance whose tint alpha is below 1, and the window
submits any such instance in its own view after the opaque world. That is a claim about pixels, so
this tool renders the same scene three ways and checks the compositing arithmetic:

* ``base``   - no ghost at all: the background the player is judging the site against
* ``faint``  - the same ghost at alpha 0.25
* ``ghost``  - the production preview (alpha from ``collect.GHOST_VALID``)
* ``solid``  - the same instance forced to alpha 1.0, i.e. the "no transparency" control

The station mesh overlaps itself, so a translucent copy does not composite once: the far side, the
near side and every plate between them each contribute. That rules out checking a single-layer
``alpha * solid + (1 - alpha) * base`` - the measurement is the *progressive* one instead. Inside
the pixels the solid control covers, each variant's coverage is
``(image - base) / (solid - base)``, and the medians must order faint < ghost < solid: alpha
respected, preview visible, and no variant identical to the background (dropped) or to the solid
control (ignored).

Usage: ``python tools/render/verify_placement_preview.py --out artifacts/placement-preview``
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

VIEWER = ROOT / 'render_cpp/build-w02/armada_viewer'
SNAPSHOT = ROOT / 'assets/cpp/catalogue.snap'
FOCUS = (600.0, 0.0, -400.0)
GHOST = {'station_kind': 'shipyard', 'faction': 'imperial', 'world': FOCUS,
         'radius': 120.0, 'valid': True}


def publish(name: str, out: Path, ghost=None, alpha_override=None) -> Path:
    """Publish a short session into ``out/name`` and return its frame ring."""
    from game.graphics_benchmark import make_fixture
    from render import asset_selection
    from render_bridge.live import LiveSession
    from tools.render.dump_snapshot import _default_selection
    from render_bridge import collect

    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    scene = make_fixture('four-player-close-v1')
    asset_selection.configure(_default_selection(), asset_root=ROOT, pack_root=ROOT / 'visual_packs')
    previous = (collect.GHOST_VALID, collect.GHOST_INVALID)
    if alpha_override is not None:
        collect.GHOST_VALID = (*collect.GHOST_VALID[:3], alpha_override)
    session = LiveSession(scene.manager.state, scene.manager.ds, directory=folder,
                          local_player=0, size=(960, 600))
    try:
        state = session.state
        visible = {e.id for e in state.entities.values() if e.alive}
        for _ in range(8):
            session.publish(state, visible_ids=visible, ghost=ghost)
    finally:
        session.close()
        collect.GHOST_VALID, collect.GHOST_INVALID = previous
    return folder


def render(folder: Path, out: Path) -> dict:
    report = folder / 'viewer.json'
    command = [str(VIEWER), '--snapshot', str(SNAPSHOT), '--assets', str(ROOT),
               '--ring', str(folder / 'frame.ring'), '--tables', str(folder / 'frame.ring.tables'),
               '--mesh-ring', str(folder / 'hardware.ring'),
               '--overlay-ring', str(folder / 'hud.ring'),
               '--frames', '24', '--warmup', '0',
               '--focus', '%g,%g,%g' % FOCUS, '--distance', '330', '--pitch', '32', '--yaw', '25',
               '--screenshot', str(folder / 'capture.png'), '--report', str(report)]
    done = subprocess.run(command, cwd=folder, capture_output=True, text=True,
                          env={**os.environ, 'SDL_VIDEODRIVER': 'cocoa'})
    if done.returncode != 0:
        raise SystemExit(f'viewer failed for {folder.name}:\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}')
    return json.loads(report.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    from PIL import Image

    alpha = None
    folders = {
        'base': publish('base', out, ghost=None),
        'faint': publish('faint', out, ghost=GHOST, alpha_override=0.25),
        'ghost': publish('ghost', out, ghost=GHOST),
        # 0.95, not 1.0: a full-alpha row takes the opaque path, which also drops the preview's
        # legality tint, and then the control differs from the ghost in colour as well as alpha.
        'strong': publish('strong', out, ghost=GHOST, alpha_override=0.95),
    }
    from render_bridge import collect
    alpha = collect.GHOST_VALID[3]

    reports, images = {}, {}
    for name, folder in folders.items():
        reports[name] = render(folder, out)
        images[name] = np.asarray(Image.open(folder / 'capture.png').convert('RGB'), dtype=float)

    base, strong = images['base'], images['strong']
    covered = np.max(np.abs(strong - base), axis=2) > 30
    # Erode by one pixel: MSAA resolves edges as partial coverage, which is neither variant.
    interior = covered.copy()
    interior[1:-1, 1:-1] &= (covered[:-2, 1:-1] & covered[2:, 1:-1] &
                             covered[1:-1, :-2] & covered[1:-1, 2:])
    interior[0, :] = interior[-1, :] = interior[:, 0] = interior[:, -1] = False
    span = (strong - base)[interior]
    usable = np.abs(span) > 12                      # pixels that actually differ, per channel
    results = {'alpha': alpha,
               'ghost_pixels_covering_the_site': int(covered.sum()),
               'interior_pixels_measured': int(interior.sum()),
               'control_alpha': 0.95}
    ratios = {}
    for name in ('faint', 'ghost', 'strong'):
        delta = (images[name] - base)[interior]
        ratio = float(np.median(delta[usable] / span[usable]))
        ratios[name] = ratio
        results[name] = {'median_abs_vs_base': float(np.mean(np.abs(images[name] - base)[interior])),
                         'median_abs_vs_control': float(np.mean(np.abs(images[name] - strong)[interior])),
                         'green_over_red': float(np.mean((images[name][interior][:, 1] -
                                                          images[name][interior][:, 0]))),
                         'preview_instances_drawn':
                             reports[name].get('placement_preview', {}).get('instances_drawn')}
    # The control is 0.95 of the way to a solid station, so alpha = 0.95 * ratio / ratio(strong).
    measured = 0.95 * ratios['ghost'] / ratios['strong'] if ratios['strong'] else 0.0
    results['measured_alpha'] = measured
    results['measured_alpha_with_faint'] = 0.95 * ratios['faint'] / ratios['strong'] if ratios['strong'] else 0.0
    results['background_through_preview'] = float(1.0 - ratios['ghost'])
    results['preview_instances_without_ghost'] = reports['base'].get('placement_preview', {}).get('instances_drawn')
    results['passed'] = bool(
        covered.sum() > 500 and interior.sum() > 300 and
        abs(measured - alpha) < 0.10 and
        results['measured_alpha_with_faint'] < measured < 1.0 and
        results['background_through_preview'] > 0.15 and
        # The legality tint must actually reach the window, and must scale with opacity: a
        # preview with the tint dropped renders neutral grey, which is what a broken shader
        # path looks like.
        results['ghost']['green_over_red'] > 5.0 and
        results['strong']['green_over_red'] > results['ghost']['green_over_red'] >
        results['faint']['green_over_red'] and
        results['ghost']['preview_instances_drawn'] > 0 and
        results['faint']['preview_instances_drawn'] > 0 and
        results['strong']['preview_instances_drawn'] > 0)
    (out / 'verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0 if results['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
