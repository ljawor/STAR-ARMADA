"""Procedural spatial-ish audio via pygame mixer + numpy (no audio assets).

All SFX are synthesized at startup: engine hum (ambient), laser fire, impact,
explosion, hyperspace charge, UI clicks. Event-bus driven: subscribes to
GameState.events so the sim never imports audio.
"""
from __future__ import annotations

import math

import numpy as np
import pygame

RATE = 22050


class Audio:
    def __init__(self, state, muted: bool = False):
        self.state = state
        self.muted = muted
        self.sounds: dict = {}
        self.available = False
        self.ambient_channel = None
        self._last_laser_t = -1.0
        self._last_hit_t = -1.0
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            self.available = True
        except pygame.error:
            return
        self._build()
        st = state
        st.events.subscribe("unit_destroyed", self._ev_explosion)
        st.events.subscribe("unit_critical", self._ev_impact)
        st.events.subscribe("weapon_fired", self._ev_fire)
        st.events.subscribe("projectile_hit", self._ev_hit)
        st.events.subscribe("jump_complete", self._ev_jump)
        st.events.subscribe("ship_built", self._ev_build)
        st.events.subscribe("station_built", self._ev_build)
        st.events.subscribe("research_complete", self._ev_build)
        st.events.subscribe("unit_leveled", self._ev_level)
        st.events.subscribe("game_over", self._ev_game_over)

    # ---------------------------------------------------------------- synthesis
    def _build(self) -> None:
        self.sounds["laser"] = self._pluck(0.07, 880.0, decay=26.0, vol=0.30)
        self.sounds["laser_heavy"] = self._pluck(0.13, 240.0, decay=14.0, vol=0.42)
        self.sounds["impact"] = self._noise_burst(0.09, 700.0, 200.0, 9.0, 0.30)
        self.sounds["explosion"] = self._noise_burst(0.65, 320.0, 45.0, 3.2, 0.65)
        self.sounds["big_explosion"] = self._noise_burst(1.3, 180.0, 26.0, 1.9, 0.85)
        self.sounds["jump"] = self._sweep(1.4, 90.0, 1400.0, vol=0.4)
        self.sounds["build"] = self._pluck(0.16, 520.0, decay=10.0, vol=0.32)
        self.sounds["ui"] = self._pluck(0.045, 700.0, decay=16.0, vol=0.22)
        self.sounds["alert"] = self._pluck(0.30, 392.0, decay=4.5, vol=0.34)

    def _pluck(self, dur, freq, decay, vol=0.4) -> pygame.mixer.Sound:
        t = np.linspace(0.0, dur, int(RATE * dur), endpoint=False)
        wave = (np.sin(2 * math.pi * freq * t) * 0.7
                + np.sin(2 * math.pi * freq * 2.02 * t) * 0.2
                + np.sin(2 * math.pi * freq * 2.99 * t) * 0.1)
        env = np.exp(-decay * t)
        mono = (wave * env * vol)
        st = (mono * 32767).astype(np.int16)
        return pygame.mixer.Sound(buffer=np.column_stack([st, st]).tobytes())

    def _noise_burst(self, dur, f_hi, f_lo, decay, vol=0.5) -> pygame.mixer.Sound:
        n = int(RATE * dur)
        rng = np.random.RandomState(11)
        noise = rng.uniform(-1.0, 1.0, n)
        # cheap low-pass via cumulative smoothing toward low-freq rumble
        t = np.linspace(0.0, dur, n, endpoint=False)
        sweep = f_hi + (f_lo - f_hi) * (t / max(dur, 1e-6))
        carrier = np.sin(2 * math.pi * np.cumsum(sweep) / RATE)
        mix = 0.65 * noise + 0.35 * carrier
        env = np.exp(-decay * t)
        mono = mix * env * vol
        st = (mono * 32767).astype(np.int16)
        return pygame.mixer.Sound(buffer=np.column_stack([st, st]).tobytes())

    def _sweep(self, dur, f0, f1, vol=0.4) -> pygame.mixer.Sound:
        n = int(RATE * dur)
        t = np.linspace(0.0, dur, n, endpoint=False)
        f = f0 + (f1 - f0) * (t / dur) ** 2
        wave = np.sin(2 * math.pi * np.cumsum(f) / RATE)
        env = np.sin(math.pi * t / dur) ** 0.5      # fade in/out
        mono = wave * env * vol
        st = (mono * 32767).astype(np.int16)
        return pygame.mixer.Sound(buffer=np.column_stack([st, st]).tobytes())

    # ---------------------------------------------------------------- playback
    def play(self, name: str, volume: float = 0.5) -> None:
        if self.muted or not self.available:
            return
        snd = self.sounds.get(name)
        if snd is not None:
            snd.set_volume(volume)
            snd.play()

    def start_ambient(self) -> None:
        """Low engine-room hum loop."""
        if self.muted or not self.available or self.ambient_channel:
            return
        dur = 4.0
        t = np.linspace(0.0, dur, int(RATE * dur), endpoint=False)
        hum = (np.sin(2 * math.pi * 42.0 * t) * 0.5
               + np.sin(2 * math.pi * 63.5 * t) * 0.3
               + np.sin(2 * math.pi * 89.0 * t) * 0.2)
        wobble = 0.85 + 0.15 * np.sin(2 * math.pi * 0.25 * t)
        mono = hum * wobble * 0.12
        st = (mono * 32767).astype(np.int16)
        snd = pygame.mixer.Sound(buffer=np.column_stack([st, st]).tobytes())
        ch = pygame.mixer.find_channel(True)
        if ch:
            ch.set_volume(0.5)
            ch.play(snd, loops=-1)
            self.ambient_channel = ch

    def toggle_mute(self) -> None:
        self.muted = not self.muted
        if self.available:
            pygame.mixer.set_num_channels(8 if not self.muted else 0)
            if not self.muted:
                self.ambient_channel = None
                self.start_ambient()

    # ---------------------------------------------------------------- events
    def _ev_fire(self, ev) -> None:
        # rate-limit: fleets fire dozens of shots/sec — cap at ~6 lasers/sec
        now = self.state.time
        if now - self._last_laser_t < 0.16:
            return
        self._last_laser_t = now
        heavy = bool(ev.data.get("heavy"))
        self.play("laser_heavy" if heavy else "laser",
                  0.42 if heavy else 0.30)

    def _ev_hit(self, ev) -> None:
        now = self.state.time
        if now - self._last_hit_t < 0.12:
            return
        self._last_hit_t = now
        self.play("impact", 0.30)

    def _ev_impact(self, ev) -> None:
        self.play("impact", 0.35)

    def _ev_explosion(self, ev) -> None:
        big = bool(ev.data.get("supercapital") or ev.data.get("is_station"))
        self.play("big_explosion" if big else "explosion",
                  0.8 if big else 0.55)

    def _ev_jump(self, ev) -> None:
        self.play("jump", 0.6)

    def _ev_level(self, ev) -> None:
        self.play("ui", 0.4)

    def _ev_game_over(self, ev) -> None:
        self.play("big_explosion", 0.9)
        self.play("alert", 0.6)

    def _ev_build(self, ev) -> None:
        self.play("build", 0.5)

    def cleanup(self) -> None:
        if self.ambient_channel:
            self.ambient_channel.stop()
        if self.available:
            pygame.mixer.quit()