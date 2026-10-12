"""Capture #76's fighter state from the user's matching-version command log.

Run in a source/content tree matching the recording. --baseline freezes ONLY
MovementSystem from that git revision (all other code/content must be unchanged).
Camera state is not recorded; no camera telemetry is inferred by this tracer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import types


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--baseline', default='f913802')
    parser.add_argument('--until', type=int)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    from game import __version__
    from game.net.replay import PlaybackSession, load_replay, content_digest
    data = load_replay(args.replay)
    session = PlaybackSession(data)  # strict version/content validation
    gm, st = session.gm, session.gm.state
    source = subprocess.check_output(['git', 'show', f'{args.baseline}:game/systems/movement.py'])
    module = types.ModuleType('game.systems._nebula_trace_baseline')
    module.__package__ = 'game.systems'
    exec(compile(source, 'immutable-baseline-movement.py', 'exec'), module.__dict__)
    gm.movement = module.MovementSystem(st)
    original = gm.separation.update
    gravity_changes = []
    def separation(dt):
        fighter = st.entity(28)
        before = [fighter.pos.x, fighter.pos.y, fighter.pos.z, fighter.vel.y] if fighter else None
        original(dt)
        if fighter and before and abs(fighter.vel.y - before[3]) > .01:
            planets = [p for p in st.entities.values() if p.is_planet and p.data_id != 'asteroid_field']
            planet = min(planets, key=lambda p: p.pos.dist_sq(fighter.pos))
            gravity_changes.append({'tick': st.tick, 'before_xyz_vy': before,
                                    'after_xyz_vy': [fighter.pos.x, fighter.pos.y, fighter.pos.z, fighter.vel.y],
                                    'nearest_planet': planet.id, 'planet_xyz': [planet.pos.x, planet.pos.y, planet.pos.z],
                                    'planet_radius': planet.radius})
    gm.separation.update = separation
    commands = {entry['tick']: entry['cmd'] for entry in data['commands'] if entry['cmd']['type'] == 'attack'}
    stop = min(session.end_tick, args.until if args.until is not None else session.end_tick)
    snapshots = {100000, 104623, 107518, 109825, 110000}
    sampled = 0
    with (args.out / 'trace.jsonl').open('w') as stream:
        while not session.ended and st.tick < stop:
            if st.tick % 3000 == 0 or st.tick in commands:
                fighter = st.entity(28)
                row = {'tick': st.tick, 'attack_command': commands.get(st.tick), 'fighter': None}
                if fighter:
                    row['fighter'] = {'id': 28, 'pos': [fighter.pos.x, fighter.pos.y, fighter.pos.z],
                                      'vel': [fighter.vel.x, fighter.vel.y, fighter.vel.z],
                                      'hull': fighter.hull, 'order': fighter.order_type,
                                      'destination': fighter.order_target_pos.to_dict() if fighter.order_target_pos else None,
                                      'detected': st.can_see(0, 28)}
                stream.write(json.dumps(row) + '\n')
                sampled += 1
            if st.tick in snapshots:
                (args.out / f'state-{st.tick}.json').write_text(json.dumps(st.to_dict(precise=True)))
            session.step()
            if st.tick % 15000 == 0:
                print('replayed', st.tick, flush=True)
    (args.out / 'state-final.json').write_text(json.dumps(st.to_dict(precise=True)))
    (args.out / 'gravity-velocity-changes.json').write_text(json.dumps(gravity_changes, indent=2))
    report = {'replay_sha256': hashlib.sha256(args.replay.read_bytes()).hexdigest(),
              'baseline_movement': args.baseline, 'game_version': __version__,
              'content_digest': content_digest(gm.ds), 'actual_end_tick': st.tick,
              'requested_end_tick': stop, 'recorded_end_tick': session.end_tick,
              'samples': sampled, 'gravity_velocity_changes': len(gravity_changes)}
    (args.out / 'trace-report.json').write_text(json.dumps(report, indent=2))
    assert st.tick == stop, report
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
