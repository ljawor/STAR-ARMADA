"""#57: losing a satellite leaves its orbit slot uninhabitable for 3 minutes.

Reported: *"Satellite penalty time — 3-min slot lock"*. Destroy a satellite and
the site it occupied had to cost the attacker something: for three minutes the
slot cannot be rebuilt in, the deadline is part of the saved world (so it
survives a reload, a replay and a capture), the orbit panel counts it down, and
the AI does not waste a strategic decision queueing into it.
"""
import json
import unittest
from types import SimpleNamespace
import pygame
from helpers import make_game, run_for
from game.core.commands import PlayerCommand
from game.core.state import GameState
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.net.replay_validation import validate_state
from game.systems import colonies
from render.camera import Camera
from render.hud import HUD
from render.input import InputController


class SatellitePenaltyTests(unittest.TestCase):
    def setUp(self):
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.planet.colonized_by = 0
        p = self.st.players[0]
        p.credits = p.materials = p.energy = p.crew = 100000

    # ---------------------------------------------------------------- helpers
    def satellite(self, owner=0, slot=0, pos=None):
        """A satellite as the build path leaves it: attached to a real slot."""
        pos = self.planet.pos + Vec3(0, 0, self.planet.radius + 900) if pos is None else pos
        sat = self.gm.factory.spawn_station('defense_satellite', owner, pos)
        sat.planet_id = self.planet.id
        sat.satellite_slot = slot
        return sat

    def occupied(self):
        return set(self.gm.construction.satellite_slots(self.planet))

    def queue_satellite(self, kind='defense_satellite'):
        self.st.queue_command(PlayerCommand('build_satellite', 0,
            target_id=self.planet.id, station_kind=kind))
        self.gm.step(1 / 30)

    def destroy(self, sat, attacker_player=1):
        """Authoritative death path: `DamageSystem._kill` is the only writer of
        deaths (combat reaches it through `_apply_damage`)."""
        killer = self.gm.factory.spawn_ship('imperial_frigate', attacker_player,
                                            sat.pos + Vec3(400, 0, 0))
        self.gm.damage._kill(sat, killer, killer.id)
        self.gm.step(1 / 30)
        return killer

    def snapshot(self):
        return json.loads(json.dumps(self.gm.state.to_dict(precise=True)))

    # ------------------------------------------------------------------ tests
    def test_a_combat_kill_locks_the_slot_for_three_minutes_and_then_frees_it(self):
        from game.data.store import DataStore
        self.assertEqual(DataStore.get().rules['colonies']['satellite_penalty_seconds'], 180.0)
        sat = self.satellite(slot=0)
        slot = sat.satellite_slot
        self.assertIn(slot, self.occupied())
        # Real guns, not a test shortcut: the frigate's orders put the satellite
        # in combat and the satellite dies to fire. A `defense_satellite` cannot
        # engage a frigate, so the attacker is never interrupted.
        gunner = self.gm.factory.spawn_ship('imperial_frigate', 1, sat.pos + Vec3(600, 0, 0))
        gunner.order_type = 'attack'
        gunner.order_target_id = sat.id
        gunner.current_target = sat.id
        for _ in range(240 * 30):
            if not sat.alive:
                break
            self.gm.step(1 / 30)
        self.assertFalse(sat.alive, 'frigate failed to kill the satellite in 240s')
        self.assertEqual(colonies.satellite_lock_remaining(self.st, self.planet, slot), 180.0)
        # The site is unavailable: the next paid satellite is reserved elsewhere.
        self.assertIn(slot, self.occupied())
        self.queue_satellite()
        self.assertNotEqual(self.planet.build_queue[-1]['slot'], slot)
        # ...and exactly 3 minutes later it is usable again.
        run_for(self.gm, 179)
        self.assertGreater(colonies.satellite_lock_remaining(self.st, self.planet, slot), 0.0)
        run_for(self.gm, 2)
        self.assertEqual(colonies.locked_satellite_slots(self.st, self.planet), set())
        self.assertEqual(colonies.satellite_lock_remaining(self.st, self.planet, slot), 0.0)

    def test_the_penalty_is_world_state_so_it_survives_save_restore_and_replay(self):
        sat = self.satellite(slot=2)
        self.destroy(sat)
        raw = self.snapshot()
        self.assertEqual(raw['entities'][str(self.planet.id)]['satellite_locks'], {'2': 180.0})
        validate_state(raw)                       # schema accepts the new field
        restored = GameManager(GameState.from_dict(raw))
        self.assertEqual(colonies.satellite_lock_remaining(restored.state, restored.state.entity(self.planet.id), 2),
                         180.0)
        # Lockstep/replay: both worlds must stay bit-identical while the clock runs.
        for _ in range(30):
            self.gm.step(1 / 30)
            restored.step(1 / 30)
            self.assertEqual(self.snapshot(), json.loads(json.dumps(restored.state.to_dict(precise=True))))
        for bad, path in (({'9': 1.0}, 'satellite_locks.slot'),
                          ({'2': -1.0}, 'satellite_locks.until'),
                          ({'2': float('nan')}, 'satellite_locks.until')):
            payload = self.snapshot()
            payload['entities'][str(self.planet.id)]['satellite_locks'] = bad
            with self.assertRaisesRegex(ValueError, path):
                validate_state(payload)
        payload = self.snapshot()
        payload['entities'][str(self.planet.id)]['satellite_locks'] = {'2': 180.0}
        del payload['entities'][str(self.planet.id)]['is_planet']
        with self.assertRaises(ValueError):
            validate_state(payload)              # not a planet: no slot to lock

    def test_repeated_destruction_can_only_extend_the_deadline(self):
        self.destroy(self.satellite(slot=1))
        self.gm.damage._kill(self.satellite(slot=1, pos=self.planet.pos + Vec3(0, 0, 1200)), None, 1)
        self.assertEqual(colonies.satellite_lock_remaining(self.st, self.planet, 1), 180.0)
        until = self.planet.satellite_locks[1]
        self.gm.state.time += 100.0
        self.destroy(self.satellite(slot=1, pos=self.planet.pos + Vec3(0, 0, 1500)))
        self.assertGreater(self.planet.satellite_locks[1], until)   # pushed out, never pulled in

    def test_capture_keeps_the_wreck_penalty_on_the_contested_site(self):
        sat = self.satellite(slot=0)
        self.destroy(sat)
        captor = self.gm.factory.spawn_ship('imperial_colonizer', 1,
            self.planet.pos + Vec3(0, 0, self.planet.radius + 300))
        self.st.queue_command(PlayerCommand('colonize', 1, unit_ids=(captor.id,), target_id=self.planet.id))
        run_for(self.gm, 14)
        self.assertEqual(self.planet.colonized_by, 1)
        self.assertGreater(colonies.satellite_lock_remaining(self.st, self.planet, 0), 0.0)

    def test_ai_does_not_queue_a_satellite_into_a_fully_locked_orbit(self):
        from game.ai.ai import AIPlayer
        ai = AIPlayer(self.st, 0)
        self.gm.factory.spawn_station('mining_station', 0, Vec3(-9000, 0, 3000))
        self.gm.ds.rules['colonies']['satellite_cap'] = 1
        self.destroy(self.satellite(slot=0, owner=1))
        self.gm.visibility.update()
        before = [c for c in self.st.command_queue if c.type == 'build_satellite']
        ai._maybe_expand(ai.home_station())
        self.assertEqual([c for c in self.st.command_queue if c.type == 'build_satellite'], before)
        # Non-vacuity: the same decision *does* fire once the site is free again.
        self.planet.satellite_locks.clear()
        ai._maybe_expand(ai.home_station())
        self.assertEqual({c.station_kind for c in self.st.command_queue if c.type == 'build_satellite'},
                         {'defense_satellite', 'attack_satellite'})


class SatellitePenaltyHUDTests(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        self.gm = make_game(ai=False)
        self.st = self.gm.state
        self.planet = next(e for e in self.st.entities.values() if e.data_id == 'temperate')
        self.planet.colonized_by = 0
        self.camera = Camera(1280, 800)
        self.camera.target = self.planet.pos.to_dict()
        self.camera.distance = 5000
        self.hud = HUD(1280, 800, self.st)
        self.ctrl = InputController(self.st, self.camera, self.hud, SimpleNamespace(flash=lambda text: None))

    def tearDown(self):
        self.hud.close()

    def panel_text(self):
        texts = []
        self.hud._label = lambda x, y, text, color=None, font=None: texts.append(str(text))
        self.hud.buttons.clear()
        self.hud.blocked_rects.clear()
        self.hud.planet_page = 'orbit'
        self.hud._right_panel({self.planet.id}, 0)
        return texts

    def test_orbit_panel_counts_the_rebuild_down_instead_of_offering_the_slot(self):
        from game.systems.colonies import lock_satellite_slot
        sat = self.gm.factory.spawn_station('defense_satellite', 0,
            self.planet.pos + Vec3(0, 0, self.planet.radius + 900))
        sat.planet_id = self.planet.id
        sat.satellite_slot = 0
        lock_satellite_slot(self.st, self.planet, 0)
        texts = self.panel_text()
        self.assertTrue(any(t.startswith('1: REBUILD') for t in texts), texts)
        self.assertFalse(any(t.startswith('1: FREE') for t in texts), texts)
        self.assertTrue(any(t.startswith('2: FREE') for t in texts), texts)
        # The wreck stops being offered as buildable space once the clock runs out.
        self.st.time += 180.0
        texts = self.panel_text()
        self.assertFalse(any(t.startswith('1: REBUILD') for t in texts), texts)
        self.assertTrue(any(t.startswith('1: FREE') for t in texts), texts)
