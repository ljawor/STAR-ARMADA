"""Procedural combat audio — synthesized at the MIXER's real rate, no assets.

Event-bus driven, so the sim never imports audio. Every voice is built from
filtered noise, swept tones and sub-bass; nothing is a raw hiss burst.

Two rules learned the hard way here:

1. Synthesize at whatever rate the mixer ACTUALLY runs at. ``pygame.init()``
   already opens the mixer (44100 on macOS) before this class is constructed,
   so an ``init(frequency=22050)`` afterwards is a silent no-op — the buffers
   are then played 2x fast and 2x high. ``self.rate`` is always read back from
   ``pygame.mixer.get_init()``.
2. One voice per weapon family, and separate shield/hull impact voices. A
   single "laser" pluck plus one noise burst for everything is what a missing
   audio asset sounds like; the ear needs the weapon to be identifiable.
3. Voice character is measured, never guessed. The owner's reference recordings
   (a laser and a photon gun) are NOT shipped — every voice here is synthesised —
   so "matches the reference" means numbers: tools/sfx_character.py measures both
   with the same function (weight = spectral centroid, crack = 95 % rolloff, tail)
   and tools/diag_weapon_sfx.py fails when a voice leaves the band the references
   define. Note the rolloff is a percentile of the MAGNITUDE spectrum, so a brief
   click cannot raise it: only top end that lasts as long as the body can.

Playback is spatial-ish: distance attenuation and stereo pan from the camera,
plus per-category rate limiting (the sim publishes dozens of shots/second).
"""
from __future__ import annotations

import math

import numpy as np
import pygame

#: Rate we ASK the mixer for. The real rate is read back into ``Audio.rate``.
RATE = 44100

#: weapon type -> voice, used when the type has no damage-based variant.
VOICE_BY_TYPE = {
    "laser": "laser",
    "point_defense": "laser_pd",
    "turbolaser": "turbolaser",
    "ion": "ion",
    "missile": "missile",
    "torpedo": "torpedo",
    "plasma": "plasma",
    "kinetic": "kinetic",
    "beam": "beam",
}

#: seconds of quiet required between plays of a category (audio-side throttle;
#: the sim is never throttled for audio's sake).
RATE_LIMITS = {
    "fire": 0.085,
    "hit": 0.070,
    "explosion": 0.050,
    "crit": 0.900,
    "build": 0.220,
    "research": 0.220,
    "ui": 0.040,
    "alert": 0.600,
    "convoy": 0.400,
    "raid": 0.400,
    "mission": 1.000,
    "ability": 0.080,
    "jump": 0.300,
    "jump_depart": 0.400,
}

#: distance (world units) at which a sound has fallen to ~half gain.
_REF_DIST = 1500.0
#: beyond this, skip playback entirely — the battle is off-screen.
_MAX_DIST = 14000.0


# --------------------------------------------------------------------- helpers
def _rng(seed: int) -> np.random.RandomState:
    return np.random.RandomState(seed)


def _tone(n, rate, f0, f1, curve=1.0, harmonics=((1, 1.0),)) -> np.ndarray:
    """Swept additive tone. ``curve`` bends the sweep (1 = linear)."""
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / rate
    u = (t / max(t[-1], 1e-6)) ** curve
    f = f0 + (f1 - f0) * u
    ph = 2.0 * math.pi * np.cumsum(f) / rate
    w = np.zeros(n)
    for mult, amp in harmonics:
        w += amp * np.sin(ph * mult)
    return w


def _shape(x, rate, fc, res=0.0, slope=2.0, hp=0.0, nfft=512) -> np.ndarray:
    """Zero-phase WOLA spectral shaping with a time-varying corner.

    ``fc`` may be a scalar or a per-sample array (Hz), which is how the
    downward-sweeping blasts get their body instead of a static hiss.
    ``res`` adds a resonant bump at the corner; ``hp`` adds a low cut.
    """
    n = len(x)
    if n <= 0:
        return x
    # keep the frame no longer than the signal, and a power of two
    nfft = max(64, min(nfft, 1 << int(math.log2(max(64, n)))))
    hop = max(1, nfft // 2)
    win = np.hanning(nfft)
    f = np.fft.rfftfreq(nfft, 1.0 / rate)
    pad = np.concatenate([x, np.zeros(nfft)])
    fc_arr = (np.full(n, float(fc)) if np.isscalar(fc)
              else np.asarray(fc, dtype=np.float64))
    acc = np.zeros(n + nfft)
    wsum = np.zeros(n + nfft)
    for pos in range(0, n, hop):
        blk = pad[pos:pos + nfft]
        if len(blk) < nfft:                     # tail frame: zero-pad
            blk = np.concatenate([blk, np.zeros(nfft - len(blk))])
        c = max(float(fc_arr[min(pos + nfft // 2, n - 1)]), 20.0)
        r = f / c
        h = 1.0 / np.sqrt(1.0 + r ** slope)
        if res:
            h = h * (1.0 + res * np.exp(-((r - 1.0) / 0.45) ** 2))
        if hp:
            rh = f / hp
            h = h * (rh / np.sqrt(1.0 + rh * rh))
        y = np.fft.irfft(np.fft.rfft(blk * win) * h, nfft)
        acc[pos:pos + nfft] += y * win
        wsum[pos:pos + nfft] += win * win
    return acc[:n] / np.maximum(wsum[:n], 1e-6)


def _env(n, rate, attack=0.004, decay=3.0, hold=0.0) -> np.ndarray:
    """Click-free envelope: smoothstep attack from exactly 0, exp decay."""
    t = np.arange(n) / rate
    a = np.clip(t / max(attack, 1e-4), 0.0, 1.0)
    a = a * a * (3.0 - 2.0 * a)
    return a * np.exp(-decay * np.maximum(t - hold, 0.0))


def _norm(x, peak=0.85) -> np.ndarray:
    m = float(np.max(np.abs(x)))
    return x if m < 1e-9 else x * (peak / m)


def _tail(x, rate, ms=6.0) -> np.ndarray:
    """Fade the last few ms to zero so a truncated tail never clicks."""
    n = len(x)
    k = min(n, int(rate * ms / 1000.0))
    if k > 1:
        x = x.copy()
        x[n - k:] *= np.linspace(1.0, 0.0, k)
    return x


def _to_sound(mono, rate, peak=0.85) -> pygame.mixer.Sound:
    mono = _tail(_norm(np.asarray(mono, dtype=np.float64), peak), rate)
    st = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)
    return pygame.mixer.Sound(buffer=np.ascontiguousarray(
        np.column_stack([st, st])).tobytes())


def voice_for_weapon(wtype, damage=0.0, is_beam=False) -> str:
    """Pick the firing voice for a weapon. Pure, so it is testable headless."""
    if is_beam:
        return "beam"
    if wtype == "turbolaser":
        return "turbolaser_heavy" if damage >= 150 else "turbolaser"
    if wtype == "laser":
        return "laser_heavy" if damage >= 25 else "laser"
    return VOICE_BY_TYPE.get(wtype or "", "laser")


def explosion_voice(radius: float, is_station: bool = False) -> str:
    """Blast size from the dying entity's radius — fighters pop, capitals roar."""
    return "big_explosion" if (is_station or radius >= 110.0) else "explosion"


def sane_settings(settings):
    """Copy presentation settings; invalid/nonfinite volumes use safe defaults."""
    result = dict(settings or {})
    for key, default in (("sfx_volume", 0.8), ("music_volume", 0.6)):
        try:
            value = float(result.get(key, default))
        except (TypeError, ValueError, OverflowError):
            value = default
        result[key] = max(0.0, min(1.0, value)) if math.isfinite(value) else default
    result["audio_dynamic_range"] = ("night" if result.get("audio_dynamic_range") == "night"
                                     else "standard")
    result["audio_mono"] = result.get("audio_mono") is True
    return result


# ---------------------------------------------------------------------- engine
class Audio:
    def __init__(self, state, muted: bool = False, settings: dict | None = None,
                 local_player: int = 0):
        self.state = state
        self.local_player = local_player
        self.muted = muted
        self.settings = sane_settings(settings)
        self.sounds: dict = {}
        self.available = False
        self.rate = RATE
        self.ambient_channel = None
        self.camera = None
        self._last: dict = {}
        self._variant = 0
        self._voice_cursor = 0
        self._active_voices = {}
        self._quiet_sounds = {}
        self._ds = None
        try:
            # pygame.init() has already opened the mixer at the device default
            # (44100). Re-open at OUR rate so synthesis and playback agree;
            # if that fails we still read the real rate back and stay in pitch.
            if pygame.mixer.get_init() is not None:
                pygame.mixer.quit()
            pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            init = pygame.mixer.get_init()
            if init is None:
                return
            self.rate = int(init[0])
            pygame.mixer.set_num_channels(32)
            # Do not use find_channel(force=True): its forced fallback can
            # return reserved channels. All production allocation is explicit.
            pygame.mixer.set_reserved(3)
            self.available = True
        except pygame.error:
            return
        self._build()
        # Peak-reducing companding lifts quiet tails relative to transients.
        # Separate cached buffers leave the established standard timbres intact.
        self.night_sounds = {}
        for name, sound in self.sounds.items():
            pcm = pygame.sndarray.array(sound).astype(np.float64) / 32768.0
            peak = float(np.max(np.abs(pcm)))
            shaped = np.sign(pcm) * np.sqrt(np.abs(pcm) / max(peak, 1e-9)) * min(peak, 0.60)
            self.night_sounds[name] = pygame.mixer.Sound(
                buffer=np.ascontiguousarray(shaped * 32767, dtype=np.int16).tobytes())
        self._subscribe(state)

    def _subscribe(self, state):
        if not self.available:
            return
        for event, method in self._EVENT_HANDLERS:
            state.events.subscribe(event, getattr(self, method))

    _EVENT_HANDLERS = (
        ('unit_destroyed', '_ev_explosion'),
        ('unit_critical', '_ev_critical'),
        ('weapon_fired', '_ev_fire'),
        ('projectile_hit', '_ev_hit'),
        ('jump_complete', '_ev_jump'),
        ('jump_depart', '_ev_jump_depart'),
        ('ship_built', '_ev_build'),
        ('station_built', '_ev_station'),
        ('research_complete', '_ev_research'),
        ('unit_leveled', '_ev_level'),
        ('game_over', '_ev_game_over'),
        ('mission_complete', '_ev_mission_complete'),
        ('mission_failed', '_ev_mission_failed'),
        ('convoy_arrived', '_ev_convoy'),
        ('convoy_raided', '_ev_raid'),
        ('ability_used', '_ev_ability'),
    )

    def _detach(self, state):
        # EventBus has no public unsubscribe; remove only this engine's handlers.
        for event, method in self._EVENT_HANDLERS:
            callbacks = getattr(state.events, '_subs', {}).get(event, [])
            handler = getattr(self, method)
            callbacks[:] = [fn for fn in callbacks if fn != handler]

    def rebind_state(self, state, ds=None):
        """Transfer event ownership without touching mixer, voices or ambience."""
        if state is self.state:
            self._ds = ds
            return
        try:
            self._subscribe(state)
        except Exception:
            self._detach(state)
            raise
        self._detach(self.state)
        self.state, self._ds = state, ds
        self._last.clear()


    # ------------------------------------------------------------- data access
    def _store(self):
        if self._ds is None:
            from game.data.store import DataStore      # local: avoid a cycle
            self._ds = DataStore.get()
        return self._ds

    # ---------------------------------------------------------------- synthesis
    def _build(self) -> None:
        rate = self.rate
        rng = _rng(7)

        def noise(dur, seed):
            return _rng(seed).uniform(-1.0, 1.0, max(1, int(rate * dur)))

        # --- energy weapons: a dark thump with a short bright edge (#91) -------
        # Tuned against the owner's reference recording of a laser shot, measured
        # with tools/sfx_character.py: weight around a 1.3 kHz centroid, a 137 ms
        # tail, a ~2.8 kHz ring-out rolloff. The old voice was an 85 ms chirp whose
        # centroid sat above 5 kHz — heard next to the reference it is a hiss with
        # no weight. Layers are unit-peaked before mixing because _shape()
        # attenuates each band by its own factor, so raw levels are not comparable.
        def laser(dur=0.30, f0=1500.0, f1=330.0, dec=15.0, fc=1050.0,
                  bed=0.0121, brite=1.99, bed_fc=4200.0, bed_hp=2200.0,
                  edge_fc=5600.0, edge_hp=3400.0):
            n = int(rate * dur)
            body = _shape(_tone(n, rate, f0, f1, curve=0.55,
                                harmonics=((1, 1.0), (2, 0.22), (3, 0.06))),
                          rate, fc, res=0.45, hp=70.0) * _env(n, rate, 0.002, dec)
            # sustained fizz: keeps top end alive exactly as long as the body rings
            fizz = _norm(_shape(noise(dur, 3), rate, bed_fc, res=0.3, slope=2.8,
                                hp=bed_hp) * _env(n, rate, 0.004, dec), 1.0)
            # 7 ms edge: marks the leading edge. It cannot carry the rolloff — a
            # burst that short has no magnitude to speak of inside a 300 ms window.
            edge = _norm(_shape(noise(dur, 9), rate, edge_fc, res=0.3, slope=2.8,
                                hp=edge_hp) * _env(n, rate, 0.0006, 150.0), 1.0)
            return body + fizz * bed + edge * brite

        self.sounds["laser"] = _to_sound(laser(0.30, 1500.0, 330.0, 15.0, 1050.0), rate)
        self.sounds["laser_b"] = _to_sound(laser(0.28, 1660.0, 372.0, 16.5, 1150.0), rate)
        self.sounds["laser_c"] = _to_sound(laser(0.32, 1360.0, 296.0, 13.5, 980.0), rate)
        # point-defense: the same gun, smaller — brighter, over sooner
        self.sounds["laser_pd"] = _to_sound(
            laser(0.19, 2350.0, 620.0, 24.0, 1900.0, bed=0.0100, brite=1.60), rate)
        # heavy laser (damage >= 25): deeper body, longer ring
        self.sounds["laser_heavy"] = _to_sound(
            laser(0.42, 1060.0, 232.0, 10.5, 900.0, bed=0.0130, brite=1.50), rate)

        # --- turbolaser / plasma: the photon-gun character (issue #91) --------
        # Measured against the owner's reference recording of a photon gun: weight
        # around a 1.0 kHz centroid yet BROADBAND (95 % rolloff ~7.3 kHz) and
        # ringing for ~350 ms. A laser keeps its top end to itself precisely because
        # it is short; the photon voice earns its crack from fizz that lasts as long
        # as the shot does — a brief click cannot carry it (see tools/sfx_character.py
        # on why the rolloff is a magnitude percentile, not an energy one).
        def turbolaser(dur, f0, f1, dec, fc, bed, vol=1.0):
            n = int(rate * dur)
            body = _shape(_tone(n, rate, f0, f1, curve=0.5,
                                harmonics=((1, 0.9), (2, 0.4), (3, 0.18), (4, 0.07))),
                          rate, fc, res=0.5, hp=60.0) * _env(n, rate, 0.0025, dec)
            fizz = _norm(_shape(noise(dur, 5), rate, 6500.0, res=0.2, slope=3.0,
                                hp=3000.0) * _env(n, rate, 0.006, dec), 1.0)
            return (body + fizz * bed) * vol

        self.sounds["turbolaser"] = _to_sound(
            turbolaser(0.50, 460.0, 120.0, 6.6, 1900.0, 0.0330), rate)
        self.sounds["turbolaser_heavy"] = _to_sound(
            turbolaser(0.68, 330.0, 86.0, 4.6, 1600.0, 0.0295), rate)

        # --- ion cannon: buzzing electric discharge (ring modulation) -------
        def ion(dur=0.34):
            n = int(rate * dur)
            carrier = _tone(n, rate, 700.0, 320.0, curve=0.7,
                            harmonics=((1, 0.6), (3, 0.35), (5, 0.2), (7, 0.12)))
            t = np.arange(n) / rate
            buzz = 0.55 + 0.45 * np.sign(np.sin(2 * math.pi * 62.0 * t))
            zap = _shape(noise(dur, 11), rate, 3400.0, res=1.6, hp=600.0)
            return (carrier * buzz * 0.8 + zap * 0.35) * _env(n, rate, 0.004, 9.0)

        self.sounds["ion"] = _to_sound(ion(), rate)

        # --- missiles/torpedoes: launch thump + whooshing motor ------------
        def whoosh(dur, seed, cut0, cut1, dec, thump_f=90.0, vol=1.0):
            n = int(rate * dur)
            t = np.arange(n) / rate
            cut = cut0 + (cut1 - cut0) * (t / max(dur, 1e-6)) ** 0.6
            air = _shape(noise(dur, seed), rate, cut, res=0.9, hp=180.0)
            thump = _tone(n, rate, thump_f * 1.6, thump_f * 0.6, curve=0.5)
            return (air * _env(n, rate, 0.012, dec)
                    + thump * _env(n, rate, 0.004, 16.0) * 0.5) * vol

        self.sounds["missile"] = _to_sound(whoosh(0.55, 21, 900.0, 2600.0, 4.2), rate)
        self.sounds["torpedo"] = _to_sound(
            whoosh(0.70, 23, 650.0, 2000.0, 3.2, thump_f=70.0, vol=1.05), rate)

        # --- mass driver: supersonic crack then a low thud -----------------
        def kinetic(dur=0.22):
            n = int(rate * dur)
            bang = _shape(noise(dur, 31), rate, 5200.0, res=1.0, hp=700.0)
            body = _tone(n, rate, 220.0, 70.0, curve=0.5,
                         harmonics=((1, 0.8), (2, 0.3)))
            return (bang * _env(n, rate, 0.0008, 34.0)
                    + body * _env(n, rate, 0.004, 13.0) * 0.8)

        self.sounds["kinetic"] = _to_sound(kinetic(), rate)

        # --- plasma: the photon character with the top end closing downward ----
        def plasma(dur=0.45, dec=6.6, bed=0.0330):
            n = int(rate * dur)
            t = np.arange(n) / rate
            cut = 8000.0 + (4200.0 - 8000.0) * (t / dur) ** 0.5
            flame = _norm(_shape(noise(dur, 41), rate, cut, res=0.2, slope=3.0,
                                 hp=2600.0) * _env(n, rate, 0.006, dec), 1.0)
            core = _shape(_tone(n, rate, 420.0, 140.0, curve=0.7,
                                harmonics=((1, 0.9), (2, 0.4), (3, 0.14))),
                          rate, 1700.0, res=0.45, hp=60.0) * _env(n, rate, 0.003, dec)
            return core + flame * bed

        self.sounds["plasma"] = _to_sound(plasma(), rate)

        # --- beam lance: sustained hum with vibrato, fade in AND out -------
        def beam(dur=0.40):
            n = int(rate * dur)
            t = np.arange(n) / rate
            vib = 1.0 + 0.012 * np.sin(2 * math.pi * 7.0 * t)
            hum = _tone(n, rate, 1180.0, 900.0, curve=0.4,
                        harmonics=((1, 0.55), (2, 0.25), (4, 0.12)))
            hiss = _shape(noise(dur, 51), rate, 4200.0, res=1.1, hp=1200.0)
            env = np.clip(t / 0.02, 0, 1) * np.clip((dur - t) / 0.06, 0, 1)
            return (hum * vib + hiss * 0.30) * env

        self.sounds["beam"] = _to_sound(beam(), rate)

        # --- impacts: shield = glassy zap, hull = metal clang ---------------
        def shield_hit(seed, dur=0.14, f=1750.0):
            n = int(rate * dur)
            ring = _tone(n, rate, f, f * 0.72, curve=0.3,
                         harmonics=((1, 0.6), (2.6, 0.25), (4.1, 0.12)))
            zap = _shape(noise(dur, seed), rate, 7000.0, res=1.5, hp=2500.0)
            return ring * _env(n, rate, 0.0015, 26.0) + \
                zap * _env(n, rate, 0.001, 45.0) * 0.40

        def hull_hit(seed, dur=0.20, f=520.0):
            n = int(rate * dur)
            # inharmonic partials = metal, not a musical note
            clang = _tone(n, rate, f, f * 0.85, curve=0.4,
                          harmonics=((1, 0.6), (2.41, 0.3), (3.77, 0.18), (5.3, 0.1)))
            thud = _shape(noise(dur, seed), rate, 1400.0, res=1.2, hp=120.0)
            return clang * _env(n, rate, 0.002, 17.0) + \
                thud * _env(n, rate, 0.001, 30.0) * 0.45

        self.sounds["impact_shield"] = _to_sound(shield_hit(61), rate)
        self.sounds["impact_shield_b"] = _to_sound(shield_hit(67, 0.13, 1960.0), rate)
        self.sounds["impact_hull"] = _to_sound(hull_hit(71), rate)
        self.sounds["impact_hull_b"] = _to_sound(hull_hit(73, 0.19, 580.0), rate)
        # generic fallback (no target resolvable)
        self.sounds["impact"] = self.sounds["impact_hull"]

        # --- explosions: sweeping resonant noise + sub-bass thump -----------
        def blast(dur, seed, cut0, cut1, dec, sub_f, sub_dec, res=1.5, vol=1.0):
            n = int(rate * dur)
            t = np.arange(n) / rate
            cut = cut0 + (cut1 - cut0) * (t / max(dur, 1e-6)) ** 0.45
            fire = _shape(noise(dur, seed), rate, cut, res=res, nfft=1024)
            crack = _shape(noise(dur, seed + 1), rate, 4200.0, hp=500.0,
                           nfft=512)
            sub = _tone(n, rate, sub_f * 1.7, sub_f * 0.75, curve=0.5)
            return (fire * _env(n, rate, 0.006, dec) * 1.0
                    + crack * _env(n, rate, 0.001, 42.0) * 0.35
                    + sub * _env(n, rate, 0.010, sub_dec) * 0.75) * vol

        self.sounds["explosion"] = _to_sound(
            blast(0.75, 101, 1500.0, 70.0, 5.2, 52.0, 5.0), rate)
        self.sounds["big_explosion"] = _to_sound(
            blast(1.50, 107, 1000.0, 38.0, 2.6, 34.0, 2.2, res=1.8, vol=1.05), rate)

        # --- utility voices -------------------------------------------------
        # hyperspace charge: rising sweep, faded in and out (no click)
        n = int(rate * 1.4)
        t = np.arange(n) / rate
        f = 90.0 + (1400.0 - 90.0) * (t / 1.4) ** 2
        w = np.sin(2 * math.pi * np.cumsum(f) / rate)
        shine = _shape(noise(1.4, 131), rate, 3000.0, res=0.8, hp=400.0)
        je = np.sin(math.pi * t / 1.4) ** 0.5
        self.sounds["jump"] = _to_sound((w + shine * 0.25) * je, rate, peak=0.7)
        # hyperspace departure (#92): the mirror voice — falling sweep, the
        # hull dropping into FTL at charge end. Same envelope family.
        f = 1400.0 + (90.0 - 1400.0) * (t / 1.4) ** 2
        w = np.sin(2 * math.pi * np.cumsum(f) / rate)
        shine = _shape(noise(1.4, 132), rate, 3000.0, res=0.8, hp=400.0)
        self.sounds["jump_depart"] = _to_sound(
            (w + shine * 0.22) * je, rate, peak=0.6)

        def chirp(freqs, dur_each=0.11, vol=0.75, seed=0):
            parts = []
            for i, fr in enumerate(freqs):
                nn = int(rate * dur_each)
                tone = _tone(nn, rate, fr, fr * 1.004,
                             harmonics=((1, 0.7), (2, 0.18), (3, 0.08)))
                parts.append(tone * _env(nn, rate, 0.006, 9.0))
            return np.concatenate(parts) * vol

        self.sounds["build"] = _to_sound(chirp([523.0, 784.0], 0.13, 0.7), rate)
        self.sounds["research"] = _to_sound(
            chirp([523.25, 659.25, 783.99, 1046.5], 0.14, 0.7), rate)
        # two-tone alarm, three pulses — used for battle warnings
        self.sounds["alert"] = _to_sound(
            chirp([392.0, 523.25, 392.0, 523.25, 392.0, 523.25], 0.15, 0.65), rate)
        self.sounds["warning"] = _to_sound(
            chirp([330.0, 247.0, 330.0, 247.0], 0.13, 0.7), rate)
        self.sounds["convoy"] = _to_sound(chirp([659.25, 880.0], 0.22, 0.55), rate)
        self.sounds["raid"] = _to_sound(
            _shape(noise(0.60, 151), rate, 700.0, res=1.7, hp=90.0)
            * _env(int(rate * 0.60), rate, 0.02, 5.0), rate)
        self.sounds["ability"] = _to_sound(
            chirp([440.0, 660.0, 880.0], 0.14, 0.6), rate)
        self.sounds["mission_complete"] = _to_sound(
            chirp([523.25, 659.25, 783.99, 1046.5, 1318.5], 0.19, 0.8), rate)
        self.sounds["mission_failed"] = _to_sound(
            chirp([392.0, 349.23, 293.66, 233.08], 0.26, 0.75), rate)

        # short soft UI blip (kept click-free with a 5 ms attack)
        nn = int(rate * 0.05)
        ui = _tone(nn, rate, 900.0, 760.0, harmonics=((1, 0.7), (2, 0.2)))
        self.sounds["ui"] = _to_sound(ui * _env(nn, rate, 0.005, 42.0), rate,
                                      peak=0.55)
        del rng  # noise draws are seeded per voice; the global rng is unused

    # ---------------------------------------------------------------- playback
    def set_camera(self, camera) -> None:
        """Camera used for distance attenuation and stereo pan (optional)."""
        self.camera = camera

    def _spatial(self, pos):
        """Return (gain, pan) for a world position; (1.0, 0.0) when unknown."""
        cam = self.camera
        if cam is None or pos is None:
            return 1.0, 0.0
        try:
            if hasattr(pos, "to_tuple"):
                pos = pos.to_tuple()
            eye = cam.eye_position()
            dx = float(pos[0]) - float(eye[0])
            dy = float(pos[1]) - float(eye[1])
            dz = float(pos[2]) - float(eye[2])
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            gain = 1.0 / (1.0 + (dist / _REF_DIST) ** 1.4)
            if dist > _MAX_DIST:
                return 0.0, 0.0
            # pan by the camera's right vector on the XZ plane
            right, _, _ = cam.basis()
            if dist < 1e-6:
                return gain, 0.0
            pan = max(-1.0, min(1.0, (dx * right[0] + dy * right[1] + dz * right[2]) / dist))
            return gain, pan
        except Exception:
            return 1.0, 0.0

    def _allowed(self, category: str) -> bool:
        """Per-category audio-side throttle (the sim is never throttled)."""
        limit = RATE_LIMITS.get(category)
        if not limit:
            return True
        now = float(getattr(self.state, "time", 0.0))
        if now - self._last.get(category, -999.0) < limit:
            return False
        self._last[category] = now
        return True

    def mix_gains(self, name: str, volume: float = 0.5, pos=None):
        """Production stereo gains, also consumed by the offline WAV probe."""
        gain, pan = self._spatial(pos)
        if self.settings["audio_mono"]:
            pan = 0.0
        try:
            volume = float(volume)
        except (TypeError, ValueError, OverflowError):
            volume = 0.0
        if not math.isfinite(volume) or self.muted:
            volume = 0.0
        # A bounded eight-voice battle pool plus two isolated alert voices.
        # Worst coherent SFX peak: .85 * (8*.07 + .18 + .22) = .816;
        # ambient peak <= .16 at gain <= .5 adds at most .08 (< .9 total).
        budget = .22 if name in ("mission_complete", "mission_failed") else (
            .18 if name in ("warning", "alert") else .07)
        vol = max(0.0, min(1.0, volume)) * self.settings["sfx_volume"] * gain * budget
        return (vol * (1.0 - max(0.0, pan) * 0.55),
                vol * (1.0 + min(0.0, pan) * 0.55))

    def play(self, name: str, volume: float = 0.5, pos=None) -> None:
        if self.muted or not self.available:
            return
        bank = self.night_sounds if self.settings["audio_dynamic_range"] == "night" else self.sounds
        snd = bank.get(name)
        left, right = self.mix_gains(name, volume, pos)
        if snd is None or max(left, right) < 0.0005:
            return
        try:
            if name in ("mission_complete", "mission_failed"):
                slot = 2
            elif name in ("warning", "alert"):
                slot = 1
            else:
                slot = next((i for i in range(3, 11)
                             if not pygame.mixer.Channel(i).get_busy()), None)
                if slot is None:
                    slot = 3 + self._voice_cursor
                    self._voice_cursor = (self._voice_cursor + 1) % 8
            ch = pygame.mixer.Channel(slot)
        except pygame.error:
            return
        if ch is None:
            return
        # pygame's stereo setter truncates gains to unsigned 8-bit panning.
        # Stage ALL battle voices from their first sample: live volume/mono
        # edits can make an initially louder transient quiet, and SDL cannot
        # swap its PCM without restarting the attack. Their maximum .07 gain
        # is below this exact 1/8 Sound gain, so compensation never clips or
        # increases the intended mix budget. Reserved warnings stay literal.
        if name not in ("warning", "alert", "mission_complete", "mission_failed"):
            if snd not in self._quiet_sounds:
                quiet = pygame.mixer.Sound(buffer=snd.get_raw())
                quiet.set_volume(0.125)
                self._quiet_sounds[snd] = quiet
            snd = self._quiet_sounds[snd]
        sound_gain = snd.get_volume()
        ch.set_volume(left / sound_gain, right / sound_gain)
        ch.play(snd)
        # Store a detached position: settings refresh never retains/mutates an
        # entity's vector. Ignore stale entries once SDL finishes/replaces it.
        if pos is None:
            point = None
        elif hasattr(pos, "to_tuple"):
            point = pos.to_tuple()
        elif isinstance(pos, (list, tuple)):
            point = tuple(pos)
        else:
            point = None
        self._active_voices[slot] = (name, volume, point, snd)

    def start_ambient(self) -> None:
        """Low engine-room hum + filtered rumble loop."""
        if self.muted or not self.available or self.ambient_channel:
            return
        rate = self.rate
        dur = 4.0
        n = int(rate * dur)
        t = np.linspace(0.0, dur, n, endpoint=False)
        hum = (np.sin(2 * math.pi * 42.0 * t) * 0.5
               + np.sin(2 * math.pi * 63.5 * t) * 0.3
               + np.sin(2 * math.pi * 89.0 * t) * 0.2)
        rumble = _shape(_rng(211).uniform(-1.0, 1.0, n), rate, 220.0, hp=40.0)
        wobble = 0.85 + 0.15 * np.sin(2 * math.pi * 0.25 * t)
        mono = np.clip(hum * wobble * 0.12 + rumble * 0.03, -0.16, 0.16)
        # WOLA edge normalization can amplify noise in the first few samples.
        # Ease both loop edges to zero instead of repeating that transient.
        edge = min(n // 2, int(rate * 0.02))
        ramp = np.linspace(0.0, 1.0, edge)
        ramp = ramp * ramp * (3.0 - 2.0 * ramp)
        mono[:edge] *= ramp
        mono[-edge:] *= ramp[::-1]
        st = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
        snd = pygame.mixer.Sound(buffer=np.ascontiguousarray(
            np.column_stack([st, st])).tobytes())
        ch = self._reserve_ambient()
        if ch is not None:
            ch.set_volume(0.5 * float(self.settings.get("music_volume", 0.6)))
            ch.play(snd, loops=-1)
            self.ambient_channel = ch

    def _reserve_ambient(self):
        """The channel set aside for the ambient loop (channel 0)."""
        try:
            ch = pygame.mixer.Channel(0)
            # mark it busy WITHOUT stealing: play a real Sound to guarantee it
            # is the channel the loop lands on, then hand it to the hum.
            ch.play(pygame.mixer.Sound(buffer=b"\x00" * 4))
            return ch
        except pygame.error:
            return None

    def apply_settings(self, settings: dict) -> None:
        """Live-apply volume changes from the settings menu."""
        previous_profile = self.settings["audio_dynamic_range"]
        self.settings = sane_settings(settings)
        if not self.available:
            return
        # SDL cannot seek a Sound when replacing its PCM bank. End old
        # transients rather than replaying their attacks in the new profile.
        if (self.settings["sfx_volume"] == 0.0 or self.muted
                or previous_profile != self.settings["audio_dynamic_range"]):
            for i in range(1, 11):
                pygame.mixer.Channel(i).stop()
            self._active_voices.clear()
        else:
            for slot, (name, volume, pos, sound) in list(self._active_voices.items()):
                channel = pygame.mixer.Channel(slot)
                if not channel.get_busy() or channel.get_sound() is not sound:
                    self._active_voices.pop(slot, None)
                else:
                    left, right = self.mix_gains(name, volume, pos)
                    sound_gain = sound.get_volume()
                    channel.set_volume(left / sound_gain, right / sound_gain)
        if self.ambient_channel:
            self.ambient_channel.set_volume(
                0.0 if self.muted else 0.5 * self.settings["music_volume"])

    def toggle_mute(self) -> None:
        self.muted = not self.muted
        if self.available:
            pygame.mixer.stop()
            if self.ambient_channel:
                self.ambient_channel.set_volume(0.0)
            if not self.muted:
                self.ambient_channel = None
                self.start_ambient()

    # ------------------------------------------------------------------ events
    def _event_owner(self, ev):
        for key in ("owner", "player", "target_owner"):
            if ev.data.get(key) is not None:
                return ev.data[key]
        for key in ("entity_id", "attacker_id", "target_id"):
            e = self.state.entities.get(ev.data.get(key))
            if e is not None:
                return getattr(e, "owner", None)
        return None

    def _own_event(self, ev):
        return self._event_owner(ev) == self.local_player

    def _audible_event(self, ev):
        """Use live detection, never explored memory; run BEFORE rate limiting.

        Data-only legacy synthesis fixtures have no visibility API. Production
        GameState always does, and unresolved/hidden foreign events fail closed.
        A local kill notification is already player knowledge even if a dead
        victim has ceased to be a live sensor contact.
        """
        if self._own_event(ev) or ev.data.get("killer_owner") == self.local_player:
            return True
        can_see = getattr(self.state, "can_see", None)
        if not callable(can_see):
            return True
        for key in ("entity_id", "attacker_id", "target_id"):
            eid = ev.data.get(key)
            if eid is not None and can_see(self.local_player, eid):
                return True
        # Destroyed entities cease being live contacts; check their position
        # against CURRENT sensors, not discovery or hidden entity metadata.
        pos = ev.data.get("pos") or ev.data.get("impact_pos")
        visible = getattr(self.state, "is_position_visible", None)
        if pos is not None and callable(visible):
            from game.core.vectors import Vec3
            try:
                point = pos if isinstance(pos, Vec3) else Vec3.from_dict(pos)
                return bool(visible(self.local_player, point))
            except (TypeError, ValueError, IndexError, KeyError):
                pass
        return False

    def _weapon(self, wid):
        """WeaponData for an id, or None (data-less weapons must not crash)."""
        if not wid:
            return None
        try:
            return self._store().weapons.get(wid)
        except Exception:
            return None

    def _ev_fire(self, ev) -> None:
        if not self._audible_event(ev):
            return
        # fleets fire dozens of shots/sec: throttle audio, never the sim
        if not self._allowed("fire"):
            return
        wd = self._weapon(ev.data.get("weapon"))
        wtype = getattr(wd, "type", None)
        dmg = float(getattr(wd, "damage", 0.0) or 0.0)
        is_beam = bool(getattr(wd, "is_beam", False))
        voice = voice_for_weapon(wtype, dmg, is_beam)
        # rotate laser variants so sustained fire does not sound mechanical
        if voice == "laser":
            self._variant = (self._variant + 1) % 3
            voice = ("laser", "laser_b", "laser_c")[self._variant]
        heavy = voice in ("turbolaser_heavy", "laser_heavy", "torpedo", "kinetic")
        self.play(voice, 0.42 if heavy else 0.30, pos=self._ev_pos(ev))

    def _ev_pos(self, ev):
        """World position of an event, when the payload or entity provides one."""
        p = ev.data.get("pos") or ev.data.get("impact_pos")
        if p:
            return p
        eid = ev.data.get("entity_id") or ev.data.get("attacker_id") \
            or ev.data.get("target_id")
        if eid is None:
            return None
        e = self.state.entities.get(eid)
        return getattr(e, "pos", None) if e is not None else None

    def _ev_hit(self, ev) -> None:
        if not self._audible_event(ev):
            return
        if not self._allowed("hit"):
            return
        target = self.state.entities.get(ev.data.get("target_id"))
        shielded = bool(target is not None and self._shield_absorbed(target, ev))
        self._variant = (self._variant + 1) % 2
        if shielded:
            voice = ("impact_shield", "impact_shield_b")[self._variant]
        else:
            voice = ("impact_hull", "impact_hull_b")[self._variant]
        self.play(voice, 0.30, pos=self._ev_pos(ev))

    @staticmethod
    def _shield_absorbed(target, ev) -> bool:
        """Did this hit land on a shield arc that still had charge?

        Only the quadrant FACING the impact depletes (see DamageSystem), so
        summing every quadrant would report "shield" even once the facing arc
        is flat and the hull is taking damage — which is exactly the sound cue
        the player needs.
        """
        if getattr(target, "max_shield_quad", 0.0) <= 0:
            return False
        shields = getattr(target, "shields", None) or {}
        if not shields:
            return False
        impact = ev.data.get("impact_pos")
        if impact is None:
            return False
        try:
            dx = float(impact[0] if not hasattr(impact, "x") else impact.x) - target.pos.x
            dz = float(impact[2] if not hasattr(impact, "z") else impact.z) - target.pos.z
            if abs(dx) > abs(dz):
                fx, fz = math.sin(target.yaw), math.cos(target.yaw)
                quad = "left" if (dx * fz - dz * fx) > 0 else "right"
            else:
                quad = "front" if dz > 0 else "rear"
        except Exception:
            return True                      # unknown geometry: assume shielded
        # the facing arc absorbs, and any overflow reaches the hull; if the
        # facing arc is already empty the hit is a hull hit.
        return float(shields.get(quad, 0.0)) > 0.0

    def _ev_critical(self, ev) -> None:
        if not self._own_event(ev):
            return
        if not self._allowed("crit"):
            return
        self.play("warning", 0.5)

    def _radius(self, ev) -> float:
        did = ev.data.get("data_id")
        if not did:
            return 0.0
        try:
            ds = self._store()
            for table in (ds.ships, ds.stations):
                d = table.get(did)
                if d is not None:
                    return float(getattr(d, "radius", 0.0) or 0.0)
        except Exception:
            return 0.0
        return 0.0

    def _ev_explosion(self, ev) -> None:
        if not self._audible_event(ev):
            return
        if not self._allowed("explosion"):
            return
        radius = self._radius(ev)
        is_station = bool(ev.data.get("is_station"))
        voice = explosion_voice(radius, is_station)
        big = voice == "big_explosion"
        self.play(voice, 0.85 if big else 0.55, pos=self._ev_pos(ev))

    def _ev_jump(self, ev) -> None:
        if not self._audible_event(ev):
            return
        self.play("jump", 0.6, pos=self._ev_pos(ev))

    def _ev_jump_depart(self, ev) -> None:
        if not self._audible_event(ev):
            return
        self.play("jump_depart", 0.55, pos=self._ev_pos(ev))

    def _ev_level(self, ev) -> None:
        if not self._own_event(ev):
            return
        self.play("ui", 0.4)

    def _ev_build(self, ev) -> None:
        if not self._own_event(ev):
            return
        if self._allowed("build"):
            self.play("build", 0.5)

    def _ev_station(self, ev) -> None:
        if not self._own_event(ev):
            return
        if self._allowed("build"):
            self.play("build", 0.7)

    def _ev_research(self, ev) -> None:
        if not self._own_event(ev):
            return
        if self._allowed("research"):
            self.play("research", 0.6)

    def _ev_convoy(self, ev) -> None:
        if self.local_player not in (ev.data.get("owner"), ev.data.get("convoy_owner")):
            return
        if self._allowed("convoy"):
            self.play("convoy", 0.5)

    def _ev_raid(self, ev) -> None:
        if self.local_player not in (ev.data.get("looter"), ev.data.get("convoy_owner")):
            return
        if self._allowed("raid"):
            self.play("raid", 0.6)

    def _ev_ability(self, ev) -> None:
        if not self._audible_event(ev):
            return
        if self._allowed("ability"):
            self.play("ability", 0.5, pos=self._ev_pos(ev))

    def _ev_mission_complete(self, ev) -> None:
        if self._allowed("mission"):
            self.play("mission_complete", 0.8)

    def _ev_mission_failed(self, ev) -> None:
        if self._allowed("mission"):
            self.play("mission_failed", 0.8)

    def _ev_game_over(self, ev) -> None:
        if not self._allowed("mission"):
            return
        winner = ev.data.get("winner", getattr(self.state, "winner", -1))
        allies = getattr(self.state, "allied_player_ids", lambda pid: [pid])(self.local_player)
        if winner in allies:
            self.play("mission_complete", 0.9)
        else:
            self.play("mission_failed", 0.9)

    def cleanup(self) -> None:
        self._detach(self.state)
        if self.ambient_channel:
            self.ambient_channel.stop()
        if self.available:
            pygame.mixer.quit()
        self._active_voices.clear()
        self._quiet_sounds.clear()
