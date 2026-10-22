"""Does the window actually draw the half-built station, translucent, the way the legacy one did?

Publishes a real paid site (the game's own ConstructionSystem, a legal site its own validator accepted),
stops it at several progress points, renders each through the shipped viewer, and measures against a
control where the same scene has no site at all:

  * how much of the site the hull covers,
  * how much of the background still shows through it (a translucent hull must not be opaque),
  * whether that alpha rises as the work completes, finishing at the solid station's own image.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VIEWER = ROOT / 'render_cpp/build-w02/armada_viewer'
SNAPSHOT = ROOT / 'assets/cpp/catalogue.snap'
STATION_KIND = 'sensor_station'
PROGRESS = (0.03, 0.55, 0.97)


def find_legal_site(cs, builder, kind, spacing=90.0, rings=14):
    """A site the game itself accepts — not coordinates chosen to make the test pass."""
    last = ''
    for ring in range(1, rings + 1):
        for dx in range(-ring, ring + 1):
            for dz in range(-ring, ring + 1):
                if max(abs(dx), abs(dz)) != ring:
                    continue
                pos = type(builder.pos)(builder.pos.x + dx * spacing, 0.0,
                                        builder.pos.z + dz * spacing)
                far, _, _ = cs.too_far_to_build(pos, builder)
                if far:
                    continue
                ok, reason = cs.check_site(kind, pos, builder)
                if ok:
                    return pos
                last = reason
    raise SystemExit(f'no legal {kind} site near the fixture fleet: {last}')


def publish(scene, name, out, station_kind, mode='progress', progress=0.5, hull=True):
    """One session: no site, a paid site held at `progress`, or the finished station.

    ``hull=False`` is the isolation control: the same paid site with the station's own row suppressed, so
    whatever the scaffold draws can be subtracted and the hull measured on its own.
    """
    from render import asset_selection
    from render_bridge.live import LiveSession
    from tools.render.dump_snapshot import _default_selection
    from game.systems.construction import ConstructionSystem

    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    asset_selection.configure(_default_selection(), asset_root=ROOT, pack_root=ROOT / 'visual_packs')
    state, ds = scene.manager.state, scene.manager.ds
    cs = ConstructionSystem(state)
    cs.factory = scene.manager.factory
    state._construction_system = cs
    builder = next((e for e in state.entities.values()
                    if e.alive and e.owner == 0 and e.is_construction), None)
    if builder is None:
        # The fixture is a fleet, not a starting base: give the player the hull a station order needs.
        faction = getattr(state.players[0], 'faction', 'imperial')
        anchor = next(e for e in state.entities.values() if e.alive and e.owner == 0)
        builder = scene.manager.factory.spawn_ship(
            f'{faction}_constructor', 0,
            type(anchor.pos)(anchor.pos.x + 400.0, 0.0, anchor.pos.z))
    pos = find_legal_site(cs, builder, station_kind)
    if mode != 'none':
        # A graphics fixture is a fleet, not an economy: give the order the resources and the command
        # room a real player would have, so the site exists at all. Only the visuals are under test.
        player = state.players[0]
        player.credits = player.materials = player.energy = player.crew = max(
            1e6, getattr(player, 'credits', 0))
        player.command_capacity = max(10_000, getattr(player, 'command_capacity', 0))
        if not cs.start_station(builder.id, station_kind, pos, 0):
            raise SystemExit(
                f'the game rejected the site its own validator accepted '
                f'(command room: {cs.command_available(0, 1)}, '
                f'short of: {cs.missing_resources(0, cs.factory.station_build_cost(station_kind))})')
        if mode == 'done':
            cs.update(builder.build_queue[0]['total'] + 1.0)
        else:
            item = builder.build_queue[0]
            item['time_left'] = item['total'] * (1.0 - progress)
            builder.build_queue[0] = item

    from render_bridge import stations as _stations
    original = _stations._hull_binding
    if not hull:
        _stations._hull_binding = lambda *a, **k: None
    try:
        session = LiveSession(state, ds, directory=folder, local_player=0, size=(960, 600))
    except Exception:
        _stations._hull_binding = original
        raise
    try:
        visible = {e.id for e in state.entities.values() if e.alive}
        for _ in range(8):
            session.publish(state, visible_ids=visible)
    finally:
        session.close()
        _stations._hull_binding = original
    return folder, pos


def render(folder, site):
    report = folder / 'viewer.json'
    command = [str(VIEWER), '--snapshot', str(SNAPSHOT), '--assets', str(ROOT),
               '--ring', str(folder / 'frame.ring'), '--tables', str(folder / 'frame.ring.tables'),
               '--mesh-ring', str(folder / 'hardware.ring'),
               '--overlay-ring', str(folder / 'hud.ring'),
               '--frames', '24', '--warmup', '0',
               '--focus', '%g,%g,%g' % tuple(site), '--distance', '300', '--pitch', '34', '--yaw', '25',
               '--screenshot', str(folder / 'capture.png'), '--report', str(report)]
    done = subprocess.run(command, cwd=folder, capture_output=True, text=True,
                          env={**os.environ, 'SDL_VIDEODRIVER': 'cocoa'})
    if done.returncode != 0:
        raise SystemExit(f'viewer failed for {folder.name}:\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}')
    return json.loads(report.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--station', default=STATION_KIND)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    from PIL import Image
    from game.graphics_benchmark import make_fixture

    folders, site = {}, None
    folders['control'], site = publish(make_fixture('four-player-close-v1'), 'control', out,
                                       args.station, mode='none')
    for progress in PROGRESS:
        name = 'build_%02d' % round(progress * 100)
        folders[name], _ = publish(make_fixture('four-player-close-v1'), name, out,
                                   args.station, mode='progress', progress=progress)
    folders['built'], _ = publish(make_fixture('four-player-close-v1'), 'built', out,
                                  args.station, mode='done')
    # Isolation controls: the same sites without the hull row, to subtract the scaffold's own drawing.
    for progress, name in ((0.55, 'scaffold_55'), (0.97, 'scaffold_97')):
        folders[name], _ = publish(make_fixture('four-player-close-v1'), name, out, args.station,
                                   mode='progress', progress=progress, hull=False)
    site = (site.x, 0.0, site.z)

    reports, images = {}, {}
    for name, folder in folders.items():
        reports[name] = render(folder, site)
        images[name] = np.asarray(Image.open(folder / 'capture.png').convert('RGB'), dtype=float)

    base, built = images['control'], images['built']
    covered = np.max(np.abs(built - base), axis=2) > 30
    interior = covered.copy()
    interior[1:-1, 1:-1] &= (covered[:-2, 1:-1] & covered[2:, 1:-1] &
                             covered[1:-1, :-2] & covered[1:-1, 2:])
    interior[0, :] = interior[-1, :] = interior[:, 0] = interior[:, -1] = False
    span = (built - base)[interior]
    usable = np.abs(span) > 12
    reference = float(np.median(span[usable] / span[usable]))   # 1.0: the finished station

    isolated = {}
    for scaffold_name, full_name in (('scaffold_55', 'build_55'), ('scaffold_97', 'build_97')):
        alone = np.max(np.abs(images[full_name] - images[scaffold_name]), axis=2)
        scaffold_px = np.max(np.abs(images[scaffold_name] - base), axis=2) > 6
        visible = (alone > 10) & ~scaffold_px
        alpha = 0.0
        if visible.sum():
            alpha = float(np.median((images[full_name] - base)[visible][:, :3].mean(axis=1) /
                                    np.maximum(1e-6, (built - base)[visible][:, :3].mean(axis=1))))
        isolated[full_name] = {
            'pixels_where_only_the_hull_is_visible': int(visible.sum()),
            'measured_alpha': round(alpha, 4)}

    results = {'hull_isolated': isolated,
               'station_kind': args.station, 'site': [round(v, 1) for v in site],
               'covering_pixels': int(covered.sum()), 'interior_pixels': int(interior.sum()),
               'reference_pixels': int(usable.sum()), 'progress': {}}
    for name in folders:
        if name in ('control', 'built'):
            continue
        delta = (images[name] - base)[interior]
        ratio = float(np.median(delta[usable] / span[usable]))
        results['progress'][name] = {'fraction_requested': int(name[-2:]) / 100.0,
                                     'measured_alpha_vs_finished_station': round(ratio, 4),
                                     'background_through': round(max(0.0, 1.0 - ratio), 4)}
    # No HUD is published in this fixture (the ring is drawn by the game's own HUD; see
    # tests/test_construction_progress.py), so the window's hud counters stay zero here by design.
    early = results['progress']['build_03']['measured_alpha_vs_finished_station']
    mid = results['progress']['build_55']['measured_alpha_vs_finished_station']
    late = results['progress']['build_97']['measured_alpha_vs_finished_station']
    results['passed'] = bool(
        results['covering_pixels'] > 500 and results['interior_pixels'] > 300 and
        usable.sum() > 100 and
        0.02 < early < mid < late < 1.02 and              # fills in as the work completes
        results['progress']['build_55']['background_through'] > 0.10 and
        # The hull is the station mesh, transported and drawn on its own: measured where the scaffold is
        # not covering it, against the finished station's own image.
        results['hull_isolated'].get('build_97', {}).get('pixels_where_only_the_hull_is_visible', 0) > 200 and
        abs(results['hull_isolated']['build_97']['measured_alpha'] -
            (0.22 + 0.63 * 0.97)) < 0.12)
    (out / 'verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0 if results['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
