"""Exhaustive native pixel census from late-created real data entities.

Visual audit only: normal ships/stations use UnitFactory, autonomous convoys use
TradingSystem.update. A separate paid-build audit must prove queue completion.
Each entry is the ONLY published instance, with no HUD, markers, fog or effects;
non-background pixels therefore cannot be mistaken for an ownership marker.
"""
from pathlib import Path
import argparse
import ctypes
import json
import re
import sys
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--only', help='One exact data ID for a narrow reproduction')
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    import numpy as np
    from PIL import Image
    import test_native_station_lifecycle as fixtures
    from game.core.state import PlayerState
    from game.core.vectors import Vec3
    from game.systems.trading import TradingSystem
    from render import asset_selection
    from render.ship_sizes import ship_size
    from render_bridge import collect, packed, ring, hardware, camera, protocol
    from tools.render.dump_snapshot import _default_selection
    asset_selection.configure(_default_selection(), asset_root=ROOT, pack_root=ROOT / 'visual_packs')
    fixture = fixtures.StationLifecycleTests('test_paid_station_created_after_tables_is_present_in_live_frame')
    fixture.setUp()
    handle = None
    lib = None
    try:
        state, ds, factory = fixture.st, fixture.ds, fixture.factory
        state.entities.clear()
        factions = sorted({d.faction for d in ds.ships.values()})
        owner = {f: i for i, f in enumerate(factions)}
        state.players = {i: PlayerState(i, faction=f, credits=1e7, materials=1e7,
            energy=1e7, crew=1e7, command_capacity=10000) for f, i in owner.items()}
        # Immutable table is created BEFORE every audited entity, as in an actual match.
        names, weapons = collect.required_names(state, ds, ship_size=ship_size,
            ship_binding=asset_selection.ship_binding, all_visible=True)
        tables = collect.build_tables(names, weapons)
        collector = collect.FrameCollector(ds, tables, asset_selection=asset_selection,
            ship_size=ship_size, ship_binding=asset_selection.ship_binding, all_visible=True)
        rows = [dict(kind='ship', id=k, faction=d.faction) for k, d in sorted(ds.ships.items())]
        rows += [dict(kind='station', id=k, faction=f) for f in factions for k in sorted(ds.stations)]
        rows += [dict(kind='auto_ship', id='trade_convoy', faction=f) for f in factions]
        expected = len(ds.ships) + len(ds.stations) * len(factions) + len(factions)
        assert len(rows) == expected == len({(r['kind'],r['faction'],r['id']) for r in rows})
        if args.only: rows = [r for r in rows if r['id'] == args.only]
        assert rows, 'No requested data ID'
        (out / 'manifest.json').write_text(json.dumps(dict(full_inventory_count=expected,
            selected_count=len(rows), only=args.only, rows=rows), indent=2))
        native_bindings = {a['binding'] for a in protocol.decode((ROOT / 'assets/cpp/catalogue.snap').read_bytes()).payload['assets']}
        (out / 'tables.bin').write_bytes(tables.encode())
        frames = ring.Ring.create(out / 'frame.ring', slots=4, slot_bytes=1<<20)
        fixture.addCleanup(frames.close)
        meshes = ring.Ring.create(out / 'mesh.ring', slots=8, slot_bytes=4<<20)
        fixture.addCleanup(meshes.close)
        cameras = ring.Ring.create(out / 'camera.ring', slots=4, slot_bytes=1024)
        fixture.addCleanup(cameras.close)
        publisher = hardware.MeshPublisher()
        library = ROOT / 'render_cpp/build-w02' / ('armada_embedded.dll' if sys.platform == 'win32' else 'libarmada_embedded.dylib')
        lib = ctypes.CDLL(str(library))
        lib.armada_open.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_char_p)]
        lib.armada_open.restype = ctypes.c_void_p
        lib.armada_frame.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        lib.armada_frame.restype = ctypes.c_int
        lib.armada_close.argtypes = [ctypes.c_void_p]; lib.armada_close.restype = None
        argv = [str(ROOT / 'render_cpp/build-w02/armada_viewer'), '--snapshot',
            str(ROOT / 'assets/cpp/catalogue.snap'), '--assets', str(ROOT), '--ring',
            str(out / 'frame.ring'), '--tables', str(out / 'tables.bin'), '--mesh-ring',
            str(out / 'mesh.ring'), '--camera-ring', str(out / 'camera.ring'),
            '--width', '640', '--height', '400']
        encoded = (ctypes.c_char_p * len(argv))(*(str(p).encode() for p in argv))
        handle = lib.armada_open(len(argv), encoded)
        assert handle, 'Cannot initialize embedded native renderer'
        pixels = (ctypes.c_ubyte * (640 * 400 * 4))()
        def capture():
            for _ in range(3):
                assert lib.armada_frame(handle, pixels, len(pixels)) == len(pixels), 'Native readback failed'
            return Image.frombytes('RGBA', (640,400), bytes(pixels), 'raw','BGRA').convert('RGB')
        results = []
        # One append per entry keeps a killed run's completed evidence intact.
        with (out / 'results.jsonl').open('w') as progress:
            for index, row in enumerate(rows):
                result: dict[str, Any] = dict(row)
                try:
                    state.entities.clear()
                    who = owner[row['faction']]
                    if row['kind'] == 'ship':
                        entity = factory.spawn_ship(row['id'], who, Vec3())
                    elif row['kind'] == 'station':
                        entity = factory.spawn_station(row['id'], who, Vec3())
                    else:
                        factory.spawn_station('trade_station', who, Vec3())
                        factory.spawn_station('trade_station', who, Vec3(4000,0,0))
                        trade = TradingSystem(state)
                        trade.update(float(trade.cfg.get('spawn_interval',45)))
                        entity = next(e for e in state.entities.values() if e.data_id == 'trade_convoy')
                        state.entities = {entity.id:entity}
                    buffer = bytearray(packed.frame_size(8,8))
                    payload, stats = collector.collect_into(state, buffer, tick=0, frame_index=index)
                    decoded = packed.unpack_frame(payload, tables)
                    assert not stats['unknown_bindings'], stats
                    record, = decoded['instances']
                    assert record['entity_id'] == entity.id
                    binding = record['binding']
                    mesh = asset_selection.mesh_for(binding)
                    assert mesh, ('No selected mesh',binding)
                    vertices = np.array([p for triangles in mesh.values() for _,tri in triangles for p in tri])
                    m = np.array(record['matrix'])
                    world = vertices @ m[:9].reshape(3,3) + m[9:12]
                    low, high = world.min(axis=0), world.max(axis=0)
                    centre = (low+high)*.5
                    radius = float(np.linalg.norm(high-low)*.5)
                    assert radius > 0
                    pose = SimpleNamespace(target=centre, distance=max(100., radius*3.5), yaw=25., pitch=35.)
                    cameras.publish(camera.encode(pose))
                    empty = packed.pack_frame(bytearray(packed.frame_size(0,0)), tick=0,
                        frame_index=index, tables=tables, instances=[], effects=[])
                    frames.publish(bytes(empty)); baseline = np.asarray(capture(),dtype=int)
                    before = state.to_dict(precise=True)
                    publisher.publish_frame(payload,tables,meshes)
                    frames.publish(bytes(payload)); image = capture()
                    assert state.to_dict(precise=True) == before, 'Visual extraction changed simulation state'
                    difference = np.max(np.abs(np.asarray(image,dtype=int)-baseline),axis=2)
                    count = int((difference > 12).sum())
                    label = re.sub(r'[^A-Za-z0-9_-]', '_', row['kind']+'-'+row['faction']+'-'+row['id'])
                    image.save(out / (label+'.png'),optimize=True)
                    result.update(entity_id=entity.id,binding=binding,in_native_catalogue=binding in native_bindings,
                        instance_count=len(decoded['instances']), flags=record['flags'],
                        changed_hull_pixels=count, camera_distance=pose.distance, radius=radius,
                        capture=label+'.png', passed=count>40,
                        creation='TradingSystem.update' if row['kind']=='auto_ship' else 'UnitFactory (visual-only)')
                except Exception as exc:
                    result.update(passed=False,error=repr(exc))
                results.append(result)
                progress.write(json.dumps(result)+'\n');progress.flush()
        result = dict(expected=len(rows), full_inventory_count=expected, tested=len(results),
            unique_tested=len({(r['kind'],r['faction'],r['id']) for r in results}),
            passed=sum(r['passed'] for r in results), failures=[r for r in results if not r['passed']],
            only=args.only, rows=results)
        (out / 'verification.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
        assert result['tested']==result['unique_tested']==result['expected']==result['passed'], 'Native unit census incomplete or invisible hulls'
    finally:
        if handle and lib is not None: lib.armada_close(handle)
        fixture.doCleanups()


if __name__ == '__main__':
    main()
