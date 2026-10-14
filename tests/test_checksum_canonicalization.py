"""Byte-exact checksum oracle frozen from 84f81f2; unittest only."""
from dataclasses import dataclass, fields, is_dataclass
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from game.benchmark import make_scene, TICK_DT
from game.net import lan
from game.net.lan import CampaignScript, _json


def legacy_canonical(value):
    if isinstance(value, CampaignScript):
        return legacy_canonical(dict(triggers=value.triggers, progress=value.progress))
    if is_dataclass(value):
        return {f.name: legacy_canonical(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k): legacy_canonical(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [legacy_canonical(v) for v in value]
    if isinstance(value, set):
        return sorted((legacy_canonical(v) for v in value), key=lambda v: _json(v))
    if value is None or type(value) in (int, float, str, bool):
        return value
    raise TypeError(f'Unserializable simulation value: {type(value)}')


def legacy_state(manager):
    st = manager.state
    omitted = {'grid', 'events', 'dmg_system', 'effects', 'floating_texts'}
    state = {f.name: legacy_canonical(getattr(st, f.name)) for f in fields(st)
             if not f.name.startswith('_') and f.name not in omitted}
    brains = {pid: {k: legacy_canonical(v) for k, v in vars(ai).items()
                    if k not in ('state', 'ds')}
              for pid, ai in manager.ai.ais.items()}
    systems = {name: {k: legacy_canonical(v) for k, v in vars(getattr(manager, name)).items()
                      if k not in ('state', 'ds')}
               for name in ('trading', 'squadrons', 'victory', 'mission')}
    return legacy_canonical(dict(state=state, ai=brains, systems=systems,
                                capacity_timer=manager._capacity_timer))


class ChecksumCanonicalizationTests(unittest.TestCase):
    def test_exact_primitives_do_not_need_dataclass_introspection(self):
        with patch.object(lan, 'is_dataclass', wraps=is_dataclass) as inspect:
            for value in (None, True, False, 1, -0.0, 'text'):
                self.assertIs(lan._canonical(value), value)
        self.assertEqual(inspect.call_count, 0)

    def test_checksum_visits_each_primitive_once(self):
        gm = make_scene(2)
        # Count actual recursive visits, not wall-clock time/noisy speed assertions.
        original = lan._canonical
        # A state leaf was formerly visited once in its subtree and again at root.
        gm.state.seed = 987654321
        with patch.object(lan, '_canonical', wraps=original) as calls:
            lan.precise_checksum(gm)
        visits = sum(type(c.args[0]) is int and c.args[0] == 987654321
                     for c in calls.call_args_list)
        self.assertEqual(visits, 1, 'state leaves must not be recanonicalized')

    def assert_legacy_bytes(self, gm):
        expected = _json(legacy_state(gm))
        actual = _json(lan.canonical_state(gm))
        self.assertEqual(actual, expected)
        self.assertEqual(lan.precise_checksum(gm), hashlib.sha256(expected).hexdigest())

    def test_evolving_combat_exact_bytes_hash_and_all_entity_fields(self):
        gm = make_scene(24)
        for tick in range(41):
            with self.subTest(tick=tick):
                self.assert_legacy_bytes(gm)
                entity = next(iter(gm.state.entities.values()))
                value = lan.canonical_state(gm)['state']['entities'][str(entity.id)]
                self.assertEqual(set(value), {f.name for f in fields(entity)})
            gm.step(TICK_DT)

    def test_evolving_real_ai_matches_frozen_oracle(self):
        gm = make_scene(10)
        gm.state.players[1].is_ai = True
        gm.ai.ensure()
        self.assertTrue(gm.ai.ais)
        for tick in range(61):
            with self.subTest(tick=tick):
                self.assert_legacy_bytes(gm)
            gm.step(TICK_DT)

    def test_live_ai_system_fields_key_collisions_and_capacity_are_not_cached(self):
        gm = make_scene(2)
        gm.ai.ais = {3: SimpleNamespace(state=object(), ds=object(),
                        orders={1: [(-0.0, 1e-200)], '1': {3, 2, 1}}, timer=0.125)}
        for tick in range(5):
            gm.ai.ais[3].timer += 0.0000000000001
            gm.trading.checksum_probe = {tick: (tick, -0.0, 1.2345678901234567)}
            gm.squadrons.checksum_probe = [tick, {False, 'a', 4}]
            gm.victory.checksum_probe = {'tick': tick}
            gm.mission.checksum_probe = (tick, None)
            gm._capacity_timer += 0.125
            self.assert_legacy_bytes(gm)

    def test_edge_types_order_floats_campaign_dataclasses_and_rejections(self):
        @dataclass
        class Nested:
            value: object
            _private: object

        class IntSubclass(int):
            pass

        script = CampaignScript.__new__(CampaignScript)
        script.triggers = [{'z': (1, -0.0), 'a': {2, 1}}]
        script.progress = {'done': False}
        values = [None, True, False, 0, -7, 10**100, -0.0, 1e-300,
                  1.2345678901234567, 'é☃', (1, [2]), {3, 'x', False},
                  {1: 'first', '1': 'last', None: (3, 2)},
                  Nested(script, {'private': True}), script]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(_json(lan._canonical(value)),
                                 _json(legacy_canonical(value)))
        for value in [object(), b'bytes', frozenset({1}), IntSubclass(3), complex(1, 2)]:
            with self.subTest(value=type(value)):
                with self.assertRaises(TypeError) as old:
                    legacy_canonical(value)
                with self.assertRaises(TypeError) as new:
                    lan._canonical(value)
                self.assertEqual(str(new.exception), str(old.exception))
        for value in [float('nan'), float('inf'), -float('inf')]:
            with self.subTest(value=value):
                for canonical in (legacy_canonical, lan._canonical):
                    with self.assertRaises(ValueError):
                        _json(canonical(value))


if __name__ == '__main__':
    unittest.main()
