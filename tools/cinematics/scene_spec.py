"""Pinned read-only scene plan for the offline 1440p startup cinematic.

Run with the project Python, not Blender: resolves the same approved core meshes
as the game, captures their hashes and real class lengths, then writes a plan.
The Blender authoring tool consumes only this data; runtime imports neither tool.
"""
from pathlib import Path
import hashlib
import json
import math

LAYOUT = (
    ('imperial_supercapital', 'imperial', (-210, -110, 0), 76),
    ('imperial_battleship', 'imperial', (-235, 180, 30), 76),
    ('imperial_frigate', 'imperial', (-75, -35, -70), 76),
    ('imperial_frigate', 'imperial', (-300, 340, 75), 76),
    ('rebel_battleship', 'rebel', (205, 100, 25), -104),
    ('rebel_frigate', 'rebel', (90, 40, -60), -104),
    ('rebel_frigate', 'rebel', (300, 310, 80), -104),
)


def build_plan(root):
    import game.core  # Preserve the application's import order, no manager instance.
    from game.data.store import DataStore
    from render.asset_registry import AssetResolver
    from render.ship_sizes import ship_size
    root = Path(root).resolve()
    resolver = AssetResolver(root)
    ds = DataStore.get()
    ships = []
    for index, (data_id, faction, location, yaw) in enumerate(LAYOUT):
        binding = f'{faction}:{ds.ships[data_id].category}'
        resolved = resolver.resolve(binding)
        if resolved is None or resolved.source != 'core':
            raise ValueError('Cinematic requires approved core mesh: ' + binding)
        manifest = resolver._core_manifest(binding)
        entry = manifest['files'][resolved.lod]
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root / 'assets/models'):
            raise ValueError('Model escapes core assets')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise ValueError('Core model approval hash differs: ' + binding)
        payload = json.loads(path.read_text(encoding='utf-8'))
        span = payload['bounds'][1][2] - payload['bounds'][0][2]
        length = ship_size(ds, data_id, faction).length
        ships.append(dict(id=index, data_id=data_id, faction=faction, binding=binding,
                          asset=resolved.asset, revision=resolved.revision,
                          runtime_path=entry['path'], runtime_sha256=digest,
                          triangle_count=payload['triangle_count'], length=length,
                          scale=length/span, location=list(location), yaw=yaw))
    return dict(version=1, resolution=[2560, 1440], fps=24, source_seconds=16,
                overlap_seconds=1, scope='offline menu movie only; no gameplay or runtime renderer changes',
                renderer='Blender 5.0.1 EEVEE offline cinematic, not native gameplay renderer',
                authoring='script-authoritative; original approved core geometry, cinematic-only materials and lighting',
                repo_root=str(root), ships=ships)


def camera_pose(t):
    phase = math.tau * t / 16
    return dict(location=(385 + 22*math.sin(phase), -875 + 18*math.cos(phase),
                          420 + 8*math.sin(phase)), target=(0, 55, 32))


def ship_pose(row, t):
    phase = math.tau*t/16
    x,y,z = row['location']
    i = row['id']
    return dict(location=(x + 8*math.sin(phase+i), y + 6*math.cos(phase+i*.4),
                          z + 2.5*math.sin(phase+i*.7)),
                rotation=(0, 0, math.radians(row['yaw']) + .01*math.sin(phase+i)))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(build_plan(Path(__file__).resolve().parents[2]), indent=2), encoding='utf-8')
    print(args.out)
