"""Bounded headless AI self-play evidence, not a full-match acceptance claim.

Example: .venv/bin/python tools/diag_gameplay_acceptance.py --out <scratch-dir>
Default: all 4 factions x 4 maps x 3 difficulties, 600s at 30 Hz.
Every slot is AI, same faction/difficulty, original map loadouts/teams retained.
Use --seconds 120 for a shorter broad sweep and filtered 600-900s probes.
Child scenarios are foreground, serial, bounded; completed evidence survives errors.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game.core.manager import GameManager
from game.data.store import DataStore

FACTIONS = ('imperial', 'rebel', 'confederacy', 'syndicate')
MAPS = ('skirmish01', 'skirmish02', 'skirmish03', 'skirmish04')
DIFFICULTIES = ('easy', 'normal', 'hard')
RESOURCES = ('credits', 'materials', 'energy', 'crew')


def precise_hash(state):
    return hashlib.sha256(json.dumps(state.to_dict(precise=True), sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def snapshot(gm):
    st, ds = gm.state, gm.ds
    players = {}
    for pid, p in sorted(st.players.items()):
        units = [e for e in st.entities.values() if e.alive and e.owner == pid and not e.is_planet]
        colonies = [e for e in st.entities.values() if e.alive and e.is_planet and e.colonized_by == pid]
        output = Counter()
        for e in colonies:
            from game.systems.colonies import eligible_planet
            if eligible_planet(e):
                output.update(ds.rules.get('economy', {}).get('planet_income', {}).get(e.data_id, {}))
                output['crew'] += ds.rules.get('economy', {}).get('planet_crew_bonus', {}).get(e.data_id, 0)
        brain = gm.ai.ais.get(pid)
        players[str(pid)] = {
            'faction': p.faction, 'difficulty': p.ai_difficulty,
            'resources': {key: getattr(p, key) for key in RESOURCES},
            'income_per_second_including_difficulty': dict(p.income_frame),
            'colony_output_base_per_second': dict(output),
            'colonies': [{'id': e.id, 'type': e.data_id} for e in colonies],
            'infrastructure_alive': dict(Counter(e.data_id for e in units if e.is_station)),
            'infrastructure_operational': dict(Counter(e.data_id for e in units if e.is_station and e.operational)),
            'forces_alive': dict(Counter(e.data_id for e in units if e.is_ship or e.is_squadron)),
            'operational_units': sum(e.operational for e in units),
            'abandoned_units': [e.id for e in units if not e.operational],
            'crew_onboard': sum(e.crew for e in units),
            'crew_missing': sum(max(0, e.max_crew - e.crew) for e in units),
            'crew_passengers': sum(e.crew_cargo for e in units),
            'transports': [{'id': e.id, 'type': e.data_id, 'crew': e.crew,
                            'max_crew': e.max_crew, 'cargo': e.crew_cargo,
                            'mission': e.crew_mission} for e in units
                           if getattr(ds.ships.get(e.data_id), 'crew_capacity', 0)],
            'research_completed': sorted(p.researched), 'research_in_progress': copy.deepcopy(p.researching),
            'build_queues': {str(e.id): copy.deepcopy(e.build_queue) for e in units if e.build_queue},
            'pending_sites': {str(eid): {'kind': site[0], 'pos': [site[1].x, site[1].y, site[1].z]}
                              for eid, site in (brain._pending_site.items() if brain else [])},
        }
    return {'tick': st.tick, 'time': st.time, 'players': players,
            'queued_commands': [c.to_dict() for c in st.command_queue]}


def run_simulation(gm, seconds, wall_limit=90):
    if seconds <= 0 or wall_limit <= 0 or not math.isfinite(seconds + wall_limit):
        raise ValueError('seconds and wall_limit must be finite and positive')
    st = gm.state
    start_tick, start_time = st.tick, st.time
    requested = round(seconds * 30)
    start = time.monotonic()
    counts, samples, amounts = Counter(), defaultdict(list), Counter()

    def observe(ev):
        counts[ev.type] += 1
        if ev.type not in ('weapon_fired', 'projectile_hit') and len(samples[ev.type]) < 12:
            samples[ev.type].append({'tick': st.tick, 'time': st.time, 'data': dict(ev.data)})
        if ev.type in ('crew_replenished', 'crew_delivered'):
            amounts[ev.type] += ev.data.get('crew', 0)
    st.events.subscribe_any(observe)
    checkpoints = [snapshot(gm)]
    stop_reason = 'horizon_reached'
    for _ in range(requested):
        if st.game_over:
            stop_reason = 'game_over'
            break
        if time.monotonic() - start >= wall_limit:
            stop_reason = 'wall_limit'
            break
        previous = st.tick
        gm.step(1 / 30)
        if st.tick != previous + 1:
            stop_reason = 'no_tick_progress'
            break
        if (st.tick - start_tick) % 1800 == 0:
            checkpoints.append(snapshot(gm))
    if st.game_over:
        stop_reason = 'game_over'
    if checkpoints[-1]['tick'] != st.tick:
        checkpoints.append(snapshot(gm))
    elapsed = time.monotonic() - start
    actual = st.tick - start_tick
    return {'requested_seconds': seconds, 'requested_ticks': requested,
            'actual_ticks': actual, 'simulated_seconds': st.time - start_time,
            'wall_seconds': elapsed, 'ticks_per_wall_second': actual / max(elapsed, 1e-9),
            'stop_reason': stop_reason, 'game_over': st.game_over,
            'winner': st.winner, 'game_over_reason': st.game_over_reason,
            'acceptance_status': 'terminal_match_observed' if st.game_over else 'bounded_partial_observation',
            'event_counts': dict(counts), 'crew_transferred': dict(amounts),
            'event_samples': dict(samples), 'checkpoints': checkpoints,
            'final_precise_state_sha256': precise_hash(st)}


def scenario(faction, map_id, difficulty, seed, seconds, wall_limit):
    ds = DataStore()
    m = copy.deepcopy(ds.maps[map_id])
    for p in m['players']:
        p.update(faction=faction, is_ai=True, ai_difficulty=difficulty)
    gm = GameManager.start_skirmish(m)
    # AI construction/tactics begin on first tick; set seed before any simulation.
    gm.state.seed = seed
    result = run_simulation(gm, seconds, wall_limit)
    result['scenario'] = {'faction': faction, 'map': map_id, 'difficulty': difficulty,
                          'seed': seed, 'players': len(m['players']),
                          'policy': 'same-faction all-AI free-for-all, original map loadout'}
    result['catalogue_rules_sha256'] = hashlib.sha256(json.dumps(gm.ds.rules, sort_keys=True).encode()).hexdigest()
    result['planet_income_rules'] = copy.deepcopy(gm.ds.rules.get('economy', {}).get('planet_income'))
    return result


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True))
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=600)
    parser.add_argument('--wall-limit', type=float, default=90)
    parser.add_argument('--factions', nargs='+', choices=FACTIONS, default=list(FACTIONS))
    parser.add_argument('--maps', nargs='+', choices=MAPS, default=list(MAPS))
    parser.add_argument('--difficulties', nargs='+', choices=DIFFICULTIES, default=list(DIFFICULTIES))
    parser.add_argument('--seed-base', type=int, default=390000)
    parser.add_argument('--one', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--seed', type=int, default=390000, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.one:
        result = scenario(args.factions[0], args.maps[0], args.difficulties[0], args.seed,
                          args.seconds, args.wall_limit)
        save(args.out, result)
        print(json.dumps({k: result[k] for k in ('scenario', 'actual_ticks', 'wall_seconds', 'stop_reason')}), flush=True)
        return
    configs = list(itertools.product(args.factions, args.maps, args.difficulties))
    evidence = {'requested_scenarios': len(configs), 'results': [], 'errors': [],
                'limitations': ['No SDL/GL, human UI, native Windows or mixed-platform LAN.',
                                'Bounded self-play is not full-match acceptance or statistical balance.',
                                'Absence of boarding/recovery events is not proof those mechanics passed.']}
    for faction, map_id, difficulty in configs:
        index = (FACTIONS.index(faction) * 4 + MAPS.index(map_id)) * 3 + DIFFICULTIES.index(difficulty)
        seed = args.seed_base + index
        path = args.out / f'{faction}_{map_id}_{difficulty}_seed{seed}.json'
        command = [sys.executable, str(Path(__file__).resolve()), '--one', '--out', str(path),
                   '--seconds', str(args.seconds), '--wall-limit', str(args.wall_limit),
                   '--factions', faction, '--maps', map_id, '--difficulties', difficulty, '--seed', str(seed)]
        try:
            child = subprocess.run(command, capture_output=True, text=True, timeout=args.wall_limit + 30,
                                   cwd=ROOT)
            if child.returncode:
                raise RuntimeError(child.stderr or child.stdout)
            result = json.loads(path.read_text())
            evidence['results'].append(result)
            print(child.stdout.strip(), flush=True)
        except (subprocess.TimeoutExpired, RuntimeError) as exc:
            evidence['errors'].append({'faction': faction, 'map': map_id, 'difficulty': difficulty,
                                       'seed': seed, 'error': str(exc)})
        evidence['completed_scenarios'] = len(evidence['results'])
        evidence['total_actual_ticks'] = sum(r['actual_ticks'] for r in evidence['results'])
        save(args.out / 'matrix.json', evidence)
    print(json.dumps({'completed': evidence['completed_scenarios'], 'requested': len(configs),
                      'actual_ticks': evidence['total_actual_ticks'], 'errors': len(evidence['errors'])}))
    if evidence['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
