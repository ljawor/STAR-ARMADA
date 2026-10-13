"""Colony-only 5x default balance, exercised through real manager ticks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from helpers import make_game
from game.core.commands import PlayerCommand
from game.core.manager import GameManager
from game.core.state import GameState
from game.core.vectors import Vec3
from game.data.store import DataStore


# Pre-increase effective rates: crew includes the additive planet_crew_bonus.
OLD_RATES = {
    'temperate': {'credits': 1.2, 'crew': 0.4},
    'industrial': {'credits': 0.4, 'materials': 1.0, 'crew': 0.1},
    'agricultural': {'credits': 0.5, 'crew': 0.8},
    'military': {'credits': 0.3, 'crew': 0.3},
    'research': {'credits': 0.6, 'crew': 0.1},
    'barren': {'credits': 0.2, 'crew': 0.05},
    'trade': {'credits': 1.8, 'crew': 0.1},
}
RESOURCES = ('credits', 'materials', 'energy', 'crew')


class ColonyIncomeBalanceTests(unittest.TestCase):
    def baseline(self, gm):
        gm.step(0.125)
        return {pid: dict(p.income_frame) for pid, p in gm.state.players.items()}

    def assert_rates(self, gm, baseline, extras):
        for pid, p in gm.state.players.items():
            for resource in RESOURCES:
                self.assertAlmostEqual(p.income_frame[resource],
                    baseline[pid][resource] + extras.get(pid, {}).get(resource, 0))

    def test_nonplanet_income_remains_unscaled_with_an_active_colony(self):
        gm = make_game(ai=False)
        for index, kind in enumerate(('mining_station', 'trade_station', 'energy_relay')):
            gm.factory.spawn_station(kind, 0, Vec3(-10000 + index * 2000, 0, -10000))
        baseline = self.baseline(gm)
        expected = dict.fromkeys(RESOURCES, 0)
        for entity in gm.state.entities.values():
            if entity.is_station and entity.owner == 0 and entity.operational:
                for resource, rate in gm.ds.stations[entity.data_id].income.items():
                    expected[resource] += rate
        self.assertEqual(baseline[0], expected)
        planet = next(e for e in gm.state.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        gm.step(0.125)
        self.assert_rates(gm, baseline, {0: {'credits': 6, 'crew': 2}})

    def test_neutral_invalid_and_dead_colonies_pay_nothing(self):
        gm = make_game(ai=False)
        baseline = self.baseline(gm)
        planet = next(e for e in gm.state.entities.values() if e.data_id == 'temperate')
        # Terrain owner is never the income authority, even in malformed saves.
        planet.owner = 0
        for colonizer in (None, -1, 999):
            with self.subTest(colonizer=colonizer):
                planet.colonized_by = colonizer
                gm.step(0.125)
                self.assert_rates(gm, baseline, {})
        planet.colonized_by = 0
        planet.alive = False
        gm.step(0.125)
        self.assert_rates(gm, baseline, {})

    def test_legacy_gas_colony_pays_nothing_even_with_modded_rates(self):
        gm = make_game(ai=False)
        baseline = self.baseline(gm)
        gas = next(e for e in gm.state.entities.values() if e.data_id == 'gas_giant')
        gas.colonized_by = 0
        gm.ds.rules['economy']['planet_income']['gas_giant'] = dict.fromkeys(RESOURCES, 99)
        gm.ds.rules['economy']['planet_crew_bonus']['gas_giant'] = 99
        gm.step(0.125)
        self.assert_rates(gm, baseline, {})

    def test_same_faction_owners_receive_only_their_own_colonies(self):
        gm = make_game(ai=False)
        baseline = self.baseline(gm)
        self.assertEqual(gm.state.players[0].faction, gm.state.players[1].faction)
        for kind, pid in (('temperate', 0), ('industrial', 1)):
            planet = next(e for e in gm.state.entities.values() if e.data_id == kind)
            planet.colonized_by = pid
        gm.step(0.125)
        self.assert_rates(gm, baseline, {0: {'credits': 6, 'crew': 2},
                                      1: {'credits': 2, 'materials': 5, 'crew': 0.5}})

    def test_capture_moves_income_without_changing_previous_bank_or_charging_fee(self):
        gm = make_game(ai=False)
        baseline = self.baseline(gm)
        planet = next(e for e in gm.state.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 1
        gm.ds.rules['colonies']['control_seconds'] = 0.25
        ship = gm.factory.spawn_ship('imperial_colonizer', 0,
            planet.pos + Vec3(0, 0, planet.radius + 300))
        gm.state.queue_command(PlayerCommand('colonize', 0, unit_ids=(ship.id,), target_id=planet.id))
        for _ in range(10):
            before = {pid: {r: getattr(p, r) for r in RESOURCES}
                      for pid, p in gm.state.players.items()}
            gm.step(0.125)
            for pid, p in gm.state.players.items():
                for r in RESOURCES:
                    self.assertAlmostEqual(getattr(p, r) - before[pid][r], p.income_frame[r] * 0.125)
            if planet.colonized_by == 0:
                break
        self.assertEqual(planet.colonized_by, 0)
        self.assertFalse(ship.alive)
        gm.step(0.125)
        self.assert_rates(gm, baseline, {0: {'credits': 6, 'crew': 2}})

    def test_fractional_restore_continues_exactly_through_owner_transfers(self):
        gm = make_game(ai=False)
        baseline = self.baseline(gm)
        planet = next(e for e in gm.state.entities.values() if e.data_id == 'agricultural')
        planet.colonized_by = 0
        for _ in range(3):
            gm.step(0.137)
        snapshot = lambda manager: json.loads(json.dumps(manager.state.to_dict(precise=True)))
        saved = snapshot(gm)
        restored = GameManager(GameState.from_dict(saved))
        self.assertEqual(saved, snapshot(restored))
        for tick in range(20):
            if tick in (5, 12):
                owner = 1 if tick == 5 else None
                gm.state.entity(planet.id).colonized_by = owner
                restored.state.entity(planet.id).colonized_by = owner
            old_tick = gm.state.tick
            gm.step(0.137)
            restored.step(0.137)
            self.assertEqual(gm.state.tick, old_tick + 1)
            self.assertEqual(snapshot(gm), snapshot(restored))
            owner = planet.colonized_by
            extra = {} if owner is None else {owner: {'credits': 2.5, 'crew': 4}}
            self.assert_rates(gm, baseline, extra)

    def test_mod_rates_and_missing_tables_are_literal_not_implicitly_scaled(self):
        gm = make_game(ai=False)
        baseline = self.baseline(gm)
        planet = next(e for e in gm.state.entities.values() if e.data_id == 'temperate')
        planet.colonized_by = 0
        rules = copy.deepcopy(gm.ds.rules)
        scenarios = (
            ({'temperate': {'credits': 0.375, 'materials': 0.125, 'energy': 0.25, 'crew': 0.625}},
             {'temperate': 0.125}, {'credits': 0.375, 'materials': 0.125, 'energy': 0.25, 'crew': 0.75}),
            ({'temperate': {'credits': 0.375}}, None, {'credits': 0.375}),
            (None, {'temperate': 0.125}, {'crew': 0.125}),
            (None, None, {}),
        )
        with tempfile.TemporaryDirectory(prefix='colony-mod-') as tmp:
            data_dir = Path(tmp, 'mods', 'income', 'data')
            data_dir.mkdir(parents=True)
            for income, bonus, expected in scenarios:
                with self.subTest(income=income, bonus=bonus):
                    mod_rules = copy.deepcopy(rules)
                    for key, value in (('planet_income', income), ('planet_crew_bonus', bonus)):
                        if value is None:
                            mod_rules['economy'].pop(key, None)
                        else:
                            mod_rules['economy'][key] = value
                    (data_dir / 'game_rules.json').write_text(json.dumps(mod_rules))
                    with patch('game.data.store.ROOT', tmp):
                        ds = DataStore(assets_dir=gm.ds.assets_dir, mods=['income'])
                    gm.ds.rules = ds.rules
                    gm.step(0.125)
                    self.assert_rates(gm, baseline, {0: expected})
                    import pygame
                    from render.hud import HUD
                    pygame.font.init()
                    hud = HUD(1280, 800, gm.state)
                    labels = []
                    hud._label = lambda x, y, text, *args, **kwargs: labels.append(str(text))
                    try:
                        hud._left_panel({planet.id}, 0)
                        for resource in RESOURCES:
                            self.assertIn(f'{resource}: {expected.get(resource, 0):g}', labels)
                    finally:
                        hud.close()

    def test_every_default_colony_pays_exactly_five_times_previous_output(self):
        gm = make_game(ai=False)
        st = gm.state
        planet = next(e for e in st.entities.values() if e.data_id == 'temperate')
        gm.step(0.125)
        baseline = {pid: dict(p.income_frame) for pid, p in st.players.items()}
        for kind, old in OLD_RATES.items():
            with self.subTest(kind=kind):
                planet.data_id = kind
                planet.colonized_by = 0
                before = {r: getattr(st.players[0], r) for r in RESOURCES}
                previous_tick = st.tick
                gm.step(0.125)
                self.assertEqual(st.tick, previous_tick + 1)
                self.assertEqual(planet.owner, -1)
                for r in RESOURCES:
                    expected = baseline[0][r] + old.get(r, 0) * 5
                    self.assertAlmostEqual(st.players[0].income_frame[r], expected)
                    self.assertAlmostEqual(getattr(st.players[0], r) - before[r], expected * 0.125)
                    self.assertEqual(st.players[1].income_frame[r], baseline[1][r])
