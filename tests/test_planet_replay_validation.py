"""Strict planetary work/attachment validation does not migrate untrusted input."""
import copy
import json
import unittest
from helpers import make_game
from game.net.replay_validation import validate_state, reconstruct
from game.systems.colonies import eligible_planet
from game.systems.planet_buildings import start_building


class PlanetReplayValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.planet = next(e for e in self.gm.state.entities.values() if eligible_planet(e))
        self.planet.colonized_by = 0
        p = self.gm.state.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000
        self.assertTrue(start_building(self.gm.construction, self.planet.id, 'planet_extractor', 0))
        self.saved = json.loads(json.dumps(self.gm.state.to_dict(precise=True)))

    def test_malformed_surface_work_rejected_before_completion(self):
        for field, value in [('source_owner', None), ('slot', None), ('slot', 6),
                ('slot', -1), ('slot', True), ('item', 'command_station'), ('source_owner', 1)]:
            with self.subTest(field=field, value=value):
                saved = copy.deepcopy(self.saved)
                work = saved['entities'][str(self.planet.id)]['build_queue'][0]
                if value is None:
                    del work[field]
                else:
                    work[field] = value
                with self.assertRaises(ValueError):
                    validate_state(saved)
        saved = copy.deepcopy(self.saved)
        source = saved['entities'][str(self.planet.id)]
        source['is_planet'] = False
        with self.assertRaises(ValueError):
            validate_state(saved)

    def test_malformed_attachment_discriminators_and_ranges_rejected(self):
        self.gm.construction.update(1000)
        saved = json.loads(json.dumps(self.gm.state.to_dict(precise=True)))
        building = next(e for e in self.gm.state.entities.values() if e.planet_building_slot is not None)
        for changes in ({'planet_building_slot': 6}, {'planet_building_slot': -1},
                {'planet_building_slot': True}, {'planet_id': None}, {'planet_id': 999999},
                {'satellite_slot': 0}, {'data_id': 'command_station'}, {'is_station': False}):
            with self.subTest(changes=changes):
                bad = copy.deepcopy(saved)
                bad['entities'][str(building.id)].update(changes)
                with self.assertRaises(ValueError):
                    validate_state(bad)

    def test_duplicate_live_attachment_rejected_in_each_domain(self):
        self.gm.construction.update(1000)
        saved = json.loads(json.dumps(self.gm.state.to_dict(precise=True)))
        building = next(e for e in saved['entities'].values() if e.get('planet_building_slot') is not None)
        for surface in (True, False):
            with self.subTest(surface=surface):
                bad = copy.deepcopy(saved)
                first = bad['entities'][str(building['id'])]
                if not surface:
                    first.update(planet_building_slot=None, satellite_slot=0, data_id='defense_satellite')
                duplicate = copy.deepcopy(first)
                duplicate['id'] = 999999
                bad['entities']['999999'] = duplicate
                with self.assertRaisesRegex(ValueError, 'attachment.*occupied'):
                    validate_state(bad)

    def test_queue_reservations_reject_duplicates_and_live_collisions(self):
        for surface in (True, False):
            for completed in (False, True):
                for reverse in (False, True):
                    with self.subTest(surface=surface, completed=completed, reverse=reverse):
                        saved = copy.deepcopy(self.saved)
                        planet = saved['entities'][str(self.planet.id)]
                        work = planet['build_queue'][0]
                        if not surface:
                            work.update(kind='satellite', item='defense_satellite', pos=[0, 0, 0])
                        if completed:
                            self.gm.construction.update(1000)
                            attachment = next(e for e in self.gm.state.entities.values()
                                              if e.planet_building_slot is not None)
                            record = json.loads(json.dumps(self.gm.state._entity_dict(attachment, precise=True)))
                            if not surface:
                                record.update(planet_building_slot=None, satellite_slot=0, data_id='defense_satellite')
                            saved['entities'][str(attachment.id)] = record
                        else:
                            planet['build_queue'].append(copy.deepcopy(work))
                        if reverse:
                            saved['entities'] = dict(reversed(list(saved['entities'].items())))
                        with self.assertRaisesRegex(ValueError, 'slot occupied'):
                            validate_state(saved)

    def test_configured_surface_capacity_applies_to_work_and_attachments(self):
        from game.data.store import DataStore
        rules = DataStore.get().rules['planet_buildings']
        original = rules['slot_cap']
        rules['slot_cap'] = 1
        try:
            bad = copy.deepcopy(self.saved)
            bad['entities'][str(self.planet.id)]['build_queue'][0]['slot'] = 1
            with self.assertRaises(ValueError):
                validate_state(bad)
            self.gm.construction.update(1000)
            bad = json.loads(json.dumps(self.gm.state.to_dict(precise=True)))
            attachment = next(e for e in bad['entities'].values() if e.get('planet_building_slot') is not None)
            attachment['planet_building_slot'] = 1
            with self.assertRaises(ValueError):
                validate_state(bad)
        finally:
            rules['slot_cap'] = original

    def test_independent_domains_planets_and_dead_freed_slots_accepted(self):
        self.gm.construction.update(1000)
        saved = json.loads(json.dumps(self.gm.state.to_dict(precise=True)))
        building = next(e for e in saved['entities'].values() if e.get('planet_building_slot') is not None)
        for variant in ('other_domain', 'other_planet', 'dead_live', 'dead_queue'):
            with self.subTest(variant=variant):
                valid = copy.deepcopy(saved)
                first = valid['entities'][str(building['id'])]
                second = copy.deepcopy(first)
                second['id'] = 999999
                if variant == 'other_domain':
                    second.update(planet_building_slot=None, satellite_slot=0, data_id='defense_satellite')
                elif variant == 'other_planet':
                    second['planet_id'] = next(e['id'] for e in valid['entities'].values()
                        if e.get('is_planet') and e['id'] != self.planet.id
                        and e.get('data_id') in ('temperate', 'industrial', 'agricultural', 'military', 'research', 'barren', 'trade'))
                else:
                    first['alive'] = False
                if variant == 'dead_queue':
                    valid['entities'][str(self.planet.id)]['build_queue'] = copy.deepcopy(
                        self.saved['entities'][str(self.planet.id)]['build_queue'])
                else:
                    valid['entities']['999999'] = second
                validate_state(valid)
                if variant.startswith('dead'):
                    first['planet_building_slot'] = -1
                    with self.assertRaises(ValueError):
                        validate_state(valid)
        queued = copy.deepcopy(self.saved)
        planet = queued['entities'][str(self.planet.id)]
        work = copy.deepcopy(planet['build_queue'][0])
        work.update(kind='satellite', item='defense_satellite', pos=[0, 0, 0])
        planet['build_queue'].append(work)
        other = copy.deepcopy(planet)
        other['id'] = 999998
        queued['entities']['999998'] = other
        validate_state(queued)

    def test_valid_exact_surface_work_and_completed_attachment_roundtrip(self):
        restored = reconstruct(self.saved)
        self.assertEqual(self.saved, json.loads(json.dumps(restored.state.to_dict(precise=True))))
        self.gm.construction.update(1000)
        saved = json.loads(json.dumps(self.gm.state.to_dict(precise=True)))
        restored = reconstruct(saved)
        self.assertEqual(saved, json.loads(json.dumps(restored.state.to_dict(precise=True))))
