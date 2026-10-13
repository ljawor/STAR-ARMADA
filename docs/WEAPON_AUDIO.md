# Weapon audio — laser and photon voices (#91)

Every sound in STAR ARMADA is synthesised at load time by `render/audio.py`
(filtered noise, swept tones, sub-bass). **No audio file ships with the game** —
there is no asset to lose, nothing to license, and the buffers always match the
mixer's real rate. Issue #91 was opened as "improve sound effects" with no symptom
named; it became concrete when the owner supplied two reference recordings of how
a **laser** and a **photon gun** should sound.

Those reference MP3s are **not** in this repository and are not needed to build or
test anything: they were measured on the machine that had them, and the numbers
they produced live in `tools/sfx_character.py::REFERENCE_TARGETS`. They are a
target, not an asset.

## What the references measure

Measured with the same function that measures our voices (see below), median per
shot:

| metric | laser reference | photon reference | meaning |
|---|---|---|---|
| `all_centroid` | 1279 Hz | 1033 Hz | weight: where the shot's energy sits |
| `all_roll95` | 3589 Hz | 7280 Hz | crack: 95 % magnitude rolloff, whole shot |
| `body_centroid` | 1101 Hz | 859 Hz | weight during the ring-out |
| `body_roll95` | 2788 Hz | 6344 Hz | crack during the ring-out |
| `tail_ms` | 136.8 ms | 358.9 ms | how long it stays above −20 dB |
| `peak_dbfs` | −8.1 | −11.3 | level of the recording |

So the two weapons are **not** "bright versus dark". They are the same weight with
a different amount of top end and a different length: the laser is a tight 137 ms
thump, the photon gun is a 359 ms thump that stays broadband throughout.

## What changed

| voice | weapons | before | after |
|---|---|---|---|
| `laser`, `laser_b`, `laser_c` | laser, interceptor | 85 ms chirp, centroid >5 kHz, rolloff ~18 kHz | 300 ms dark thump, centroid ~1.4 kHz, rolloff ~2.8 kHz |
| `laser_pd` | point-defense | thinner/higher short chirp | same gun, smaller: brighter and over sooner (90 ms) |
| `laser_heavy` | laser ≥ 25 dmg | short-ish chirp | deeper body, longer ring (205 ms) |
| `turbolaser`, `turbolaser_heavy` | turbolaser | 280 ms band-limited crack | 500 ms / 680 ms broadband thump, rolloff ~7.3 kHz |
| `plasma` | plasma lance | short band-passed flame | same photon character with the top end closing downward |

Every voice is unchanged in *name* and *mapping* (`voice_for_weapon`), so the sim,
the event bus and the replays see exactly what they saw before.

## How a voice is built

Three layers, and the split matters:

* **body** — a swept additive tone with 3–4 harmonics, shaped at a corner
  frequency (`_shape(...)`, zero-phase WOLA), then enveloped. This is the weight.
* **fizz** — band-limited noise that decays with the body. This is what keeps the
  top end alive for as long as the shot rings, which is what the rolloff measures.
* **edge** — a ~7 ms band-limited burst that marks the leading edge.

Layers are peak-normalised **before** mixing (`_norm(layer, 1.0)`), because
`_shape()` attenuates each band by its own factor: a level that looks "loud" in
source units can be inaudible after band-limiting, and vice versa.

### The one thing worth knowing before re-tuning

`all_roll95` / `body_roll95` are percentiles of the **magnitude** spectrum, not of
energy. A brief, loud burst therefore contributes almost nothing to them: only top
end that lasts about as long as the body can move the number. Early attempts to
"add a click" to raise the rolloff failed for exactly this reason, and that is why
the photon voice earns its crack from sustained fizz instead.

## Tools

| tool | what it does |
|---|---|
| `tools/sfx_character.py` | measures a recording **or** a synthesised voice: attack, time-to-peak, tail, peak, and the centroid / 95 % rolloff of the onset, the ring-out and the whole shot. Splits a multi-shot recording into single shots and reports median/p10/p90. Also writes spectrogram PNGs (log frequency) with pygame — no matplotlib in this project. |
| `tools/diag_weapon_sfx.py` | acceptance probe: measures the reworked voices, exports each as a WAV to listen to, writes spectrograms, checks every voice against the band the references define plus the relationships that keep the voices tellable apart, and exits non-zero when one drifts out. |

```bash
python tools/sfx_character.py --voices laser,turbolaser --reference path/to/ref.wav
python tools/diag_weapon_sfx.py --out /tmp/sfx91 --reference path/to/ref.wav
```

## Deliberate deviations from the recordings

* **Attack.** Both recordings swell to their peak (laser 68 ms in, photon 147 ms
  in); a game voice is punched in ~3 ms. Fire feedback at RTS rates has to be
  immediate, so the transient is intentionally sharper, which is also why the
  ring-out window of a synthesised voice sits brighter than the recording's.
* **Normalisation.** Every voice is normalised to the same peak, as before; the
  recordings are not peak-normalised, so their `peak_dbfs` differ from ours. The
  relative loudness of the weapons is a mix decision and was not changed by #91.
* **Nothing under `game/` reads audio.** Voices are built from event-bus data, so a
  voice can never affect simulation state, a digest or a replay.

## Acceptance evidence

* `tools/diag_weapon_sfx.py` — every reworked voice inside its band, every
  relationship holding (exit 0), spectrograms and WAVs written.
* `tests/test_weapon_sfx.py` — 7 tests: bands, relationships, "matches the recorded
  laser / photon gun" within a stated tolerance, "the laser is no longer a bare
  chirp", "no voice is silent or clipped" (checked on the **sample** peak, because a
  4 ms envelope cannot see a 3 ms transient clipped past full scale), and "no two
  voices are the same shot relabelled".
* Sabotage matrix (11 rows, each de-fixing one thing: the old chirp, a missing fizz
  bed, a voice duplicated from another, a clipped voice, a no-op measurement, a
  wrong reference number) — 11/11 caught, tree restored byte-exact.

Out of scope for #91: music, per-weapon *variant* character beyond the two families
above, and any change to the volume/mix balance.
