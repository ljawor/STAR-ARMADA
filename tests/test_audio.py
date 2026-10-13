"""Audio tests — run headless with SDL_AUDIODRIVER=dummy.

The mixer opens fine under the dummy driver, so the real synthesis path is
testable: these tests read the actual buffers pygame would play.

What is covered here is what actually broke and what would silently regress:
the sample-rate agreement (a mismatch plays every sound fast and high), the
per-weapon voice mapping, blast sizing, click-free envelopes, filtered (not
hiss) noise, spatial gain, the per-category throttle, and an end-to-end run
that proves the event subscriptions really fire the right voices.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                            # noqa: E402
import pygame                                                 # noqa: E402

from game.core.vectors import Vec3                            # noqa: E402
from render.audio import (Audio, RATE, explosion_voice,       # noqa: E402
                          voice_for_weapon)


class _Events:
    def __init__(self):
        self.handlers = {}

    def subscribe(self, name, fn):
        self.handlers[name] = fn


class _State:
    """Minimal stand-in: the audio layer only needs time, events, entities."""

    def __init__(self):
        self.time = 0.0
        self.events = _Events()
        self.entities = {}
        self.winner = 0


class _Ev:
    def __init__(self, **data):
        self.data = data


def _audio(**settings):
    st = _State()
    a = Audio(st, settings=settings or {"sfx_volume": 0.8})
    return a, st


def _mono(snd):
    arr = pygame.sndarray.array(snd).astype(np.float64) / 32768.0
    return arr.mean(axis=1) if arr.ndim > 1 else arr


def _centroid(snd, rate):
    x = _mono(snd)
    n = min(2048, len(x))
    if n < 64:
        return 0.0
    win = np.hanning(n)
    sp = np.abs(np.fft.rfft(x[:n] * win)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / rate)
    return float((f * sp).sum() / (sp.sum() + 1e-12))


def _flatness(snd):
    x = _mono(snd)
    n = min(2048, len(x))
    if n < 64:
        return 0.0
    sp = np.abs(np.fft.rfft(x[:n] * np.hanning(n))) ** 2
    p = sp / (sp.sum() + 1e-12)
    return float(np.exp(np.mean(np.log(p + 1e-12))) / (np.mean(p) + 1e-12))


class TestRateAgreement(unittest.TestCase):
    """The headline bug: pygame.init() opens the mixer at 44100 first, so an
    init(frequency=22050) afterwards is a silent no-op and every buffer plays
    2x fast and 2x high."""

    def setUp(self):
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()

    def test_synth_rate_matches_mixer_rate(self):
        a, _ = _audio()
        self.assertTrue(a.available)
        if not a.available:
            return
        mixer_rate = pygame.mixer.get_init()[0]
        self.assertEqual(a.rate, mixer_rate,
                         "synthesis rate must match the mixer's real rate")
        # and the rate we asked for must be the rate we got — if the device
        # refused it, RATE and reality have silently diverged again
        self.assertEqual(a.rate, RATE,
                         f"asked the mixer for {RATE}Hz, got {mixer_rate}Hz")

    def test_duration_is_what_the_voice_intended(self):
        a, _ = _audio()
        if not a.available:
            return
        # the point is rate agreement: a 0.30 s laser must not come back as
        # ~0.15 s because the buffer was synthesised at half the mixer's rate.
        # Durations are the ones the #91 recipes ask for in render/audio.py.
        for name, intended in (("laser", 0.30), ("turbolaser", 0.50)):
            with self.subTest(voice=name):
                self.assertAlmostEqual(a.sounds[name].get_length(), intended, delta=0.005)

    def test_all_voices_are_audible_and_click_free(self):
        a, _ = _audio()
        if not a.available:
            return
        for name, snd in a.sounds.items():
            x = _mono(snd)
            peak = float(np.max(np.abs(x)))
            self.assertGreater(peak, 0.05, f"{name} is near-inaudible")
            # an envelope that starts at a large fraction of peak is a tick
            self.assertLess(abs(x[0]) / (peak + 1e-12), 0.35,
                            f"{name} has an onset click")


class TestVoiceMapping(unittest.TestCase):
    def test_weapon_types_map_to_distinct_voices(self):
        self.assertEqual(voice_for_weapon("laser", 14), "laser")
        self.assertEqual(voice_for_weapon("point_defense", 7), "laser_pd")
        self.assertEqual(voice_for_weapon("turbolaser", 90), "turbolaser")
        self.assertEqual(voice_for_weapon("turbolaser", 210), "turbolaser_heavy")
        self.assertEqual(voice_for_weapon("ion", 70), "ion")
        self.assertEqual(voice_for_weapon("missile", 55), "missile")
        self.assertEqual(voice_for_weapon("torpedo", 260), "torpedo")
        self.assertEqual(voice_for_weapon("plasma", 130), "plasma")
        self.assertEqual(voice_for_weapon("kinetic", 240), "kinetic")

    def test_beam_flag_wins_over_type(self):
        self.assertEqual(voice_for_weapon("beam", 55, is_beam=True), "beam")

    def test_unknown_and_missing_types_fall_back(self):
        self.assertEqual(voice_for_weapon(None), "laser")
        self.assertEqual(voice_for_weapon(""), "laser")
        self.assertEqual(voice_for_weapon("hyperdeath_ray"), "laser")

    def test_every_mapped_voice_exists(self):
        a, _ = _audio()
        if not a.available:
            return
        for wtype in ("laser", "point_defense", "turbolaser", "ion", "missile",
                      "torpedo", "plasma", "kinetic", "beam"):
            for dmg in (5.0, 90.0, 300.0):
                v = voice_for_weapon(wtype, dmg)
                self.assertIn(v, a.sounds, f"{wtype}/{dmg} -> missing {v}")

    def test_explosion_sizing(self):
        self.assertEqual(explosion_voice(20.0), "explosion")
        self.assertEqual(explosion_voice(90.0), "explosion")
        self.assertEqual(explosion_voice(150.0), "big_explosion")
        self.assertEqual(explosion_voice(20.0, is_station=True), "big_explosion")

    def test_capital_ships_get_the_big_blast(self):
        """Real radii from the shipped data: capitals/stations roar, fighters pop."""
        a, _ = _audio()
        self.assertEqual(explosion_voice(260.0), "big_explosion")   # supercapital
        self.assertEqual(explosion_voice(150.0), "big_explosion")   # battleship
        self.assertEqual(explosion_voice(90.0), "explosion")        # cruiser
        self.assertEqual(explosion_voice(22.0), "explosion")        # squadron
        self.assertEqual(explosion_voice(130.0, True), "big_explosion")
        if a.available:
            self.assertTrue(a.sounds[explosion_voice(260.0)].get_length()
                            > a.sounds[explosion_voice(22.0)].get_length())


class TestSynthesisQuality(unittest.TestCase):
    """A raw noise burst reads as static; these pin the timbre differences."""

    def test_no_voice_is_unfiltered_hiss(self):
        a, _ = _audio()
        if not a.available:
            return
        for name in ("explosion", "big_explosion", "impact_hull",
                     "impact_shield", "plasma", "missile"):
            self.assertLess(_flatness(a.sounds[name]), 0.55,
                            f"{name} is broadband hiss")

    def test_explosions_have_sub_bass_body(self):
        a, _ = _audio()
        if not a.available:
            return
        for name in ("explosion", "big_explosion"):
            x = _mono(a.sounds[name])
            n = min(4096, len(x))
            sp = np.abs(np.fft.rfft(x[:n] * np.hanning(n))) ** 2
            f = np.fft.rfftfreq(n, 1.0 / a.rate)
            low = float(sp[f < 150.0].sum() / (sp.sum() + 1e-12))
            self.assertGreater(low, 0.05, f"{name} has no body below 150Hz")

    def test_laser_is_brighter_than_explosion(self):
        a, _ = _audio()
        if not a.available:
            return
        laser = _centroid(a.sounds["laser"], a.rate)
        boom = _centroid(a.sounds["explosion"], a.rate)
        self.assertGreater(laser, boom * 1.5,
                           f"laser {laser:.0f}Hz vs boom {boom:.0f}Hz")

    def test_shield_hit_is_brighter_than_hull_hit(self):
        a, _ = _audio()
        if not a.available:
            return
        shield = _centroid(a.sounds["impact_shield"], a.rate)
        hull = _centroid(a.sounds["impact_hull"], a.rate)
        self.assertGreater(shield, hull * 1.4,
                           f"shield {shield:.0f}Hz vs hull {hull:.0f}Hz")

    def test_envelope_truly_starts_and_ends_at_zero(self):
        a, _ = _audio()
        if not a.available:
            return
        for name in ("laser", "explosion", "impact_hull", "jump"):
            x = _mono(a.sounds[name])
            peak = float(np.max(np.abs(x)))
            self.assertLess(abs(x[0]), 1e-6, f"{name} starts non-zero")
            self.assertLess(abs(x[-1]), 0.02 * peak, f"{name} ends non-zero")

    def test_voices_are_not_clipped(self):
        a, _ = _audio()
        if not a.available:
            return
        for name, snd in a.sounds.items():
            x = _mono(snd)
            # a solid run of full-scale samples means additive clipping
            flat_top = int(np.sum(np.abs(x) > 0.999))
            self.assertLess(flat_top, 8, f"{name} is clipped")


class TestSpatial(unittest.TestCase):
    def test_distance_attenuates_and_silences_far_battles(self):
        from render.camera import Camera
        camera = Camera(960, 640)
        camera.yaw = 0.
        a, _ = _audio()
        a.set_camera(camera)
        near, _ = a._spatial(camera.eye_position())
        mid, _ = a._spatial([3000.0, 0.0, 0.0])
        far, _ = a._spatial([20000.0, 0.0, 0.0])
        self.assertAlmostEqual(near, 1.0, places=5)
        self.assertLess(mid, near)
        self.assertEqual(far, 0.0, "an off-screen blast must be silent")

    def test_pan_follows_the_camera_right_vector(self):
        from render.camera import Camera
        camera = Camera(960, 640)
        camera.yaw = 0.
        a, _ = _audio()
        a.set_camera(camera)
        _, left = a._spatial([-2000.0, 0.0, 0.0])
        _, right = a._spatial([2000.0, 0.0, 0.0])
        self.assertLess(left, 0.0)
        self.assertGreater(right, 0.0)

    def test_no_camera_is_safe(self):
        a, _ = _audio()
        self.assertEqual(a._spatial([10.0, 0.0, 10.0]), (1.0, 0.0))
        self.assertEqual(a._spatial(None), (1.0, 0.0))


class TestThrottle(unittest.TestCase):
    def test_fire_is_throttled_but_never_blocks_forever(self):
        a, st = _audio()
        a._allowed("fire")
        st.time += 0.01
        self.assertFalse(a._allowed("fire"), "must throttle a burst")
        st.time += 1.0
        self.assertTrue(a._allowed("fire"), "must recover after the window")

    def test_categories_are_independent(self):
        a, st = _audio()
        self.assertTrue(a._allowed("fire"))
        self.assertTrue(a._allowed("hit"), "hit has its own window")
        self.assertTrue(a._allowed("explosion"))


class TestEventHandlers(unittest.TestCase):
    def _subscribe_check(self, a, st):
        for name in ("unit_destroyed", "weapon_fired", "projectile_hit",
                     "unit_critical", "jump_complete", "ship_built",
                     "station_built", "research_complete", "unit_leveled",
                     "game_over", "mission_complete", "mission_failed",
                     "convoy_arrived", "convoy_raided", "ability_used"):
            self.assertIn(name, st.events.handlers,
                          f"{name} is not subscribed — that sound can never play")

    def test_all_events_are_subscribed(self):
        a, st = _audio()
        self._subscribe_check(a, st)

    def test_handlers_survive_datales_entities_and_junk_payloads(self):
        """A convoy has no data row; a missing payload must not raise."""
        a, st = _audio()
        played = []
        a.play = lambda name, volume=0.5, pos=None: played.append(name)
        for name, handler in st.events.handlers.items():
            for payload in ({}, {"entity_id": 999}, {"data_id": None},
                            {"weapon": None}, {"weapon": "nonexistent"},
                            {"target_id": None}, {"winner": -1}):
                try:
                    handler(_Ev(**payload))
                except Exception as exc:          # pragma: no cover
                    self.fail(f"{name} raised on {payload}: {exc!r}")

    def test_fire_uses_the_weapon_type(self):
        a, st = _audio()
        seen = []
        a.play = lambda name, volume=0.5, pos=None: seen.append(name)
        a._ev_fire(_Ev(weapon="beam_lance", attacker_id=1))
        a._last.clear()
        a._ev_fire(_Ev(weapon="turbolaser", attacker_id=1))
        a._last.clear()
        a._ev_fire(_Ev(weapon="point_defense", attacker_id=1))
        self.assertEqual(seen, ["beam", "turbolaser", "laser_pd"])

    def test_hit_distinguishes_shield_from_hull(self):
        class E:
            def __init__(self, quad_charge):
                self.max_shield_quad = 100.0
                self.shields = {"front": quad_charge, "rear": 100.0,
                                "left": 100.0, "right": 100.0}
                self.pos = type("P", (), {"x": 0.0, "z": 0.0})()
                self.yaw = 0.0

        a, st = _audio()
        seen = []
        a.play = lambda name, volume=0.5, pos=None: seen.append(name)
        # impact from +z = the FRONT arc
        front_impact = type("P", (), {"x": 0.0, "z": 10.0})()
        st.entities[1] = E(quad_charge=50.0)      # facing arc has charge
        st.entities[2] = E(quad_charge=0.0)       # facing arc flat -> hull
        a._ev_hit(_Ev(target_id=1, impact_pos=front_impact))
        a._last.clear()
        a._ev_hit(_Ev(target_id=2, impact_pos=front_impact))
        self.assertTrue(seen[0].startswith("impact_shield"), seen)
        self.assertTrue(seen[1].startswith("impact_hull"), seen)

    def test_a_flat_facing_arc_reports_hull_even_with_other_arcs_charged(self):
        """The bug this was written for: summoning every quadrant reported
        'shield' long after the arc facing the shooter had collapsed."""
        class E:
            max_shield_quad = 100.0
            shields = {"front": 0.0, "rear": 100.0, "left": 100.0, "right": 100.0}
            pos = type("P", (), {"x": 0.0, "z": 0.0})()
            yaw = 0.0

        a, _ = _audio()
        seen = []
        a.play = lambda name, volume=0.5, pos=None: seen.append(name)
        impact = type("P", (), {"x": 0.0, "z": 10.0})()
        a._ev_hit(_Ev(target_id=1, impact_pos=impact))
        self.assertTrue(seen[0].startswith("impact_hull"), seen)

    def test_a_shieldless_hull_reports_hull(self):
        """Squadrons have shield_quad 0 — they must never clink like shields."""
        class E:
            max_shield_quad = 0.0
            shields = {"front": 0.0, "rear": 0.0, "left": 0.0, "right": 0.0}
            pos = type("P", (), {"x": 0.0, "z": 0.0})()
            yaw = 0.0

        a, st = _audio()
        seen = []
        a.play = lambda name, volume=0.5, pos=None: seen.append(name)
        st.entities[1] = E()
        a._ev_hit(_Ev(target_id=1, impact_pos=E.pos))
        self.assertTrue(seen[0].startswith("impact_hull"), seen)

    def test_explosion_voice_scales_with_real_ship_data(self):
        a, st = _audio()
        seen = []
        a.play = lambda name, volume=0.5, pos=None: seen.append(name)
        a._ev_explosion(_Ev(data_id="imperial_supercapital"))
        a._last.clear()
        a._ev_explosion(_Ev(data_id="imperial_tie_squadron"))
        a._last.clear()
        a._ev_explosion(_Ev(data_id="command_station", is_station=True))
        self.assertEqual(seen, ["big_explosion", "explosion", "big_explosion"])

    def test_game_over_respects_the_winner(self):
        a, st = _audio()
        seen = []
        a.play = lambda name, volume=0.5, pos=None: seen.append(name)
        a._ev_game_over(_Ev(winner=1))
        a._last.clear()
        a._ev_game_over(_Ev(winner=0))
        self.assertEqual(seen, ["mission_failed", "mission_complete"])

    def test_mute_is_respected(self):
        a, st = _audio()
        if not a.available:
            return
        a.muted = True
        self.assertIsNone(a.play("laser", 0.5))       # no exception, no output


class TestEndToEnd(unittest.TestCase):
    """Drive the REAL sim and prove the event wiring fires the right voices.

    Everything above tests the audio layer in isolation; unit-tested handlers
    say nothing about whether the sim ever publishes the events they listen
    for. This runs an actual skirmish with live fire and records what plays.
    """

    @classmethod
    def setUpClass(cls):
        try:
            from helpers import make_game, run_for        # tests/ on sys.path
        except ImportError:                               # pragma: no cover
            raise unittest.SkipTest("tests/helpers.py not importable")
        cls.make_game = staticmethod(make_game)
        cls.run_for = staticmethod(run_for)

    def test_a_real_battle_plays_weapon_and_impact_voices(self):
        gm = self.make_game(ai=False)
        st = gm.state
        a = Audio(st, settings={"sfx_volume": 0.8})
        if not a.available:
            self.skipTest("mixer unavailable headless")
        played = []
        a.play = lambda name, volume=0.5, pos=None: played.append(name)
        # place two hostile ships in knife range: the shipped skirmish starts
        # the players 22,000 u apart, so nothing engages on its own in 6 s.
        gm.factory.spawn_ship("imperial_frigate", 0, Vec3(-4000.0, 0.0, 0.0))
        gm.factory.spawn_ship("imperial_corvette", 1, Vec3(-3700.0, 0.0, 0.0))
        self.run_for(gm, 10.0)
        self.assertTrue(played, "a 10 s engagement produced no audio at all")
        self.assertTrue(any(n.startswith(("laser", "turbolaser", "ion", "beam"))
                            for n in played),
                        f"no firing voice in {sorted(set(played))}")
        self.assertTrue(any(n.startswith("impact") for n in played),
                        f"no impact voice in {sorted(set(played))}")

    def test_shield_hits_play_shield_voices_in_a_real_fight(self):
        """End-to-end counterpart of the quadrant bug: a shielded ship under
        fire must clink on its shields, not thud on its hull."""
        gm = self.make_game(ai=False)
        st = gm.state
        a = Audio(st, settings={"sfx_volume": 0.8})
        if not a.available:
            self.skipTest("mixer unavailable headless")
        played = []
        a.play = lambda name, volume=0.5, pos=None: played.append(name)
        gm.factory.spawn_ship("imperial_frigate", 0, Vec3(-4000.0, 0.0, 0.0))
        gm.factory.spawn_ship("imperial_corvette", 1, Vec3(-3700.0, 0.0, 0.0))
        self.run_for(gm, 8.0)
        self.assertTrue(any(n.startswith("impact_shield") for n in played),
                        f"no shield voice in {sorted(set(played))}")

    def test_a_kill_plays_an_explosion_voice(self):
        gm = self.make_game(ai=False)
        st = gm.state
        a = Audio(st, settings={"sfx_volume": 0.8})
        if not a.available:
            self.skipTest("mixer unavailable headless")
        seen = []
        a.play = lambda name, volume=0.5, pos=None: seen.append(name)
        # kill a ship outright and step one tick to resolve it
        victim = next(e for e in st.entities.values()
                      if e.alive and e.is_ship and e.owner == 1)
        st.damage_queue.append({
            "target": victim, "damage": 1e6, "shield_mult": 1.0,
            "armor_mult": 1.0, "system_mult": 1.0, "attacker_id": 0,
            "weapon": None, "impact_pos": victim.pos.copy(),
        })
        gm.step(1 / 30)
        self.assertTrue(any(n.endswith("explosion") for n in seen),
                        f"a kill produced no blast voice: {seen}")


class TestShutdown(unittest.TestCase):
    """main.py's teardown must survive being reached with no game started.

    Reported crash: the traceback ended at module level with
    `AttributeError: 'NoneType' object has no attribute 'cleanup'`, because
    `audio` is None until start_game() runs and the final teardown called
    audio.cleanup() unconditionally.
    """

    def test_teardown_is_guarded_for_a_menu_only_exit(self):
        main_py = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "main.py")
        src = open(main_py).read()
        self.assertIn("if audio is not None:", src,
                      "main.py must guard the teardown: quitting from a menu "
                      "never builds an Audio, so audio is still None")
        self.assertNotIn("\naudio.cleanup()", src,
                         "an unguarded audio.cleanup() crashes on a menu exit")

    def test_the_exit_probe_reproduces_and_clears_the_crash(self):
        """Drive the real main.py through a menu quit with audio unset."""
        probe = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "tools", "probe_main_exit.py")
        if not os.path.exists(probe):
            self.skipTest("probe_main_exit.py missing")
        r = subprocess.run(
            [sys.executable, probe],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=300,
            env=dict(os.environ, PYTHONPATH="."),
        )
        self.assertIn("MAIN_EXIT_OK", r.stdout,
                      f"menu-exit shutdown not clean:\n{r.stdout[-800:]}")


if __name__ == "__main__":
    unittest.main()
