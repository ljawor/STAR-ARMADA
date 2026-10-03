"""Damage-resolved contacts; pure geometry tests require no GL context."""
import math
import unittest
from helpers import make_game
from game.core.vectors import Vec3


class HitDataTests(unittest.TestCase):
    def test_absorption_has_only_shield_contact(self):
        gm = make_game(ai=False)
        st = gm.state
        target = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
        target.shields['front'] = 100
        st.effects.clear()
        impact = target.pos + Vec3(0, 0, target.radius * .5)
        hull = target.hull
        gm.damage._apply_damage(target, 12, 2, 1, 1, impact_pos=impact)
        hits = [f for f in st.effects if f['kind'].endswith('_hit')]
        self.assertEqual([f['kind'] for f in hits], ['shield_hit'])
        fx = hits[0]
        self.assertEqual(fx['damage'], 24)
        self.assertEqual(fx['target_id'], target.id)
        self.assertEqual(fx['direction'], [0., 0., -1.])
        self.assertEqual(fx['normal'], [0., 0., 1.])
        self.assertEqual(fx['center'], target.pos.to_dict())
        self.assertAlmostEqual(fx['pos'][2], target.pos.z + target.radius * 1.35)
        self.assertGreater(fx['size'], 0)
        self.assertLess(fx['size'], target.radius * .5)
        self.assertIsInstance(fx['seed'], int)
        self.assertEqual(target.hull, hull)
        self.assertEqual(target.shields['front'], 76)
    def test_overflow_distinct_contacts_deterministic_without_rng(self):
        gm = make_game(ai=False)
        st = gm.state
        t = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
        t.shields['front'] = 10
        st.effects.clear()
        from unittest.mock import patch
        rng_guard = patch.object(type(st), 'rng', side_effect=AssertionError('VFX consumed RNG'))
        rng_guard.start()
        self.addCleanup(rng_guard.stop)
        hp = t.hull
        impact = t.pos + Vec3(0, 0, 1)
        gm.damage._apply_damage(t, 20, 2, .5, 1, impact_pos=impact)
        hits = [f for f in st.effects if f['kind'].endswith('_hit')]
        self.assertEqual([f['kind'] for f in hits], ['shield_hit', 'hull_hit'])
        self.assertEqual([f['damage'] for f in hits], [10, 7.5])
        self.assertEqual(t.hull, hp - 7.5)
        self.assertLess(hits[1]['radius'], hits[0]['radius'])
        first = hits[1]
        st.effects.clear()
        gm.damage._spawn_hit('hull_hit', t, impact, None, 7.5)
        self.assertEqual(st.effects[0], first)
        st.tick += 1
        gm.damage._spawn_hit('hull_hit', t, impact, None, 7.5)
        self.assertNotEqual(st.effects[-1]['seed'], first['seed'])

    def test_zero_hull_multiplier_and_empty_arc_do_not_fake_contacts(self):
        gm = make_game(ai=False)
        st = gm.state
        t = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
        t.shields['front'] = 0
        t.shields['rear'] = 100
        st.effects.clear()
        gm.damage._apply_damage(t, 20, 1, 0, 1, impact_pos=t.pos + Vec3(0, 0, 1))
        self.assertFalse(any(f['kind'].endswith('_hit') for f in st.effects))
    def test_projectile_hit_has_no_duplicate_generic_impact(self):
        from game.core.world import Projectile
        from unittest.mock import patch
        gm = make_game(ai=False)
        st = gm.state
        t = next(e for e in st.entities.values() if e.is_station and e.owner == 1)
        p = Projectile(id=99, owner=0, weapon_id='laser_cannon',
                       pos=t.pos + Vec3(0, 0, t.radius), vel=Vec3(0, 0, -10),
                       target_id=t.id, damage=12, shield_mult=1, armor_mult=1,
                       system_mult=1, life=2)
        st.projectiles = {p.id: p}
        st.effects.clear()
        with patch.object(gm.projectiles, '_find_hit', return_value=(t, t)):
            gm.projectiles.update(.01)
        self.assertFalse(any(f['kind'] == 'impact' for f in st.effects))
        hit = st.damage_queue[-1]
        self.assertEqual(hit['impact_direction'], Vec3(0, 0, -10))
        self.assertIsInstance(hit['effect_seed'], int)
        gm.damage.update(0)
        fx = next(f for f in st.effects if f['kind'] == 'shield_hit')
        self.assertEqual(fx['direction'], [0., 0., -1.])
        self.assertEqual(fx['seed'], hit['effect_seed'])


    def test_beam_visual_contact_keeps_original_front_arc_damage(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        gm = make_game(ai=False)
        st = gm.state
        e = next(e for e in st.entities.values() if e.owner == 0 and e.is_ship)
        target = next(e for e in st.entities.values() if e.owner == 1 and e.is_station)
        e.pos = target.pos + Vec3(400, 0, 0)
        e.current_target = target.id
        wd = next(w for w in gm.weapons.ds.weapons.values() if w.is_beam)
        unit = SimpleNamespace(weapons=[wd.id])
        st.effects.clear()
        with patch.object(gm.weapons, '_resolve_unit_data', return_value=unit):
            gm.weapons._ship_weapons(e, 0, is_static=True)
        hit = st.damage_queue[-1]
        self.assertEqual(hit['impact_direction'].normalized(), Vec3(-1, 0, 0))
        self.assertNotIn('impact_pos', hit)  # no gameplay quadrant change!
        beam = next(f for f in st.effects if f['kind'] == 'beam')
        self.assertTrue(beam['resolved_contact'])
        self.assertLess(beam['target_pos'][0], e.pos.x)
        self.assertGreater(beam['target_pos'][0], target.pos.x)
        before = dict(target.shields)
        gm.damage.update(0)
        self.assertLess(target.shields['front'], before['front'])
        self.assertEqual(target.shields['left'], before['left'])
        fx = next(f for f in st.effects if f['kind'] == 'shield_hit')
        self.assertEqual(fx['normal'], [1., 0., 0.])

    def test_depletion_does_not_spawn_whole_target_glow(self):
        gm = make_game(ai=False)
        st = gm.state
        t = next(e for e in st.entities.values() if e.is_station and e.owner == 0)
        t.shields['front'] = 1
        st.effects.clear()
        gm.damage._apply_damage(t, 2, 1, 1, 1, impact_pos=t.pos + Vec3(0, 0, 1))
        self.assertNotIn('shield_down', [fx['kind'] for fx in st.effects])


class GeometryTests(unittest.TestCase):
    def test_curved_localized_shell_geometry_is_deterministic_and_fades(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('render.hit_effects'),
                             'missing localized hit geometry module')
        from render.hit_effects import hit_geometry
        fx = dict(kind='shield_hit', pos=[0, 0, 135], center=[0, 0, 0],
                  normal=[0, 0, 1], direction=[0, 0, -1], radius=135,
                  size=12, seed=12, t=.08)
        mesh = hit_geometry(fx)
        self.assertEqual(mesh, hit_geometry(fx))
        self.assertGreater(len(mesh['triangles']), 0)
        shell = mesh['shell']
        self.assertGreater(len(shell), 0)
        for p in shell:
            self.assertAlmostEqual(math.sqrt(sum(x*x for x in p)), 135, places=5)
            self.assertGreater(p[2], 135 * .88)
        self.assertGreater(max(p[2] for p in shell) - min(p[2] for p in shell), 1)
        early = sum(c[3] for p, c in mesh['triangles'])
        late = hit_geometry(dict(fx, t=.49))
        self.assertLess(sum(c[3] for p, c in late['triangles']), early)
        expired = hit_geometry(dict(fx, t=.8))
        self.assertFalse(expired['triangles'] or expired['lines'])


if __name__ == '__main__':
    unittest.main()
