# S06 B3c — the remaining seventeen faction station rows (appearance approved, not landed)

Review-only evidence for batch `s06-b3c-stations` (appearance approved by the owner on 2026-10-17
under decision `s06-b3c-stations-2026-10-17`; not landed, nothing registered): the research station, defense platform, trade
station, fighter platform and repair dock across Alliance, Legion and Syndicate, plus the Legion and
Syndicate shipyards. **Nothing here is an approval record, a registry entry or a runtime manifest**,
and no production binding was replaced. The durable record is
`art/manifests/handoffs/S06-B3C-STATIONS.md`; this file only says what each artefact is and how to
produce it again.

## Regenerate everything

```bash
cd /Users/lukaszjawor/.hermes/cache/scratch/star-armada-s06
B=/Applications/Blender.app/Contents/MacOS/Blender

# 1. masters (refuses an existing master without --replace-seed)
for a in rebel:research_station confederacy:research_station syndicate:research_station \
         rebel:defense_platform confederacy:defense_platform syndicate:defense_platform \
         rebel:trade_station confederacy:trade_station syndicate:trade_station \
         rebel:fighter_platform confederacy:fighter_platform syndicate:fighter_platform \
         rebel:repair_dock confederacy:repair_dock syndicate:repair_dock \
         confederacy:shipyard syndicate:shipyard; do
  env -u SDL_VIDEODRIVER $B --background --factory-startup --python-exit-code 1 \
      --python tools/art/build_b3c_stations.py -- --asset $a --replace-seed
done

# 2. exports (export-only: each wrapper opens its own master and never saves it)
.venv/bin/python tools/art/gen_export_wrappers.py --check
for i in alliance_research_station legion_research_station syndicate_research_station \
         alliance_defense_platform legion_defense_platform syndicate_defense_platform \
         alliance_trade_station legion_trade_station syndicate_trade_station \
         alliance_fighter_platform legion_fighter_platform syndicate_fighter_platform \
         alliance_repair_dock legion_repair_dock syndicate_repair_dock \
         legion_shipyard syndicate_shipyard; do
  env -u SDL_VIDEODRIVER $B --background --factory-startup --python-exit-code 1 \
      --python tools/art/export_$i.py
done

# 3. sidecars and guards
.venv/bin/python tools/art/write_pending_sidecars.py --batch s06-b3c-stations
PYTHONPATH=tests .venv/bin/python -m unittest test_alliance_blender_b3c_stations

# 4. captures (the harness refuses an existing --out directory)
rm -rf artifacts/s06_alliance_batch_review/b3c-stations
env -u SDL_VIDEODRIVER .venv/bin/python tools/diag_alliance_batch_review.py \
    --spec art/manifests/pending/S06-BATCH-B3C-STATIONS.json \
    --out artifacts/s06_alliance_batch_review/b3c-stations \
    --motion rebel:research_station,confederacy:shipyard,syndicate:defense_platform
```

## What is in here

| file | what it is |
| --- | --- |
| `metrics.json` | the run's full record: per-row mesh hashes/bounds/footprints, every camera, per-view changed pixels, ablation counts, motion timelines, preservation flags |
| `contact-sheet.png` | every row, before/after, four views, labelled `UNAPPROVED REVIEW ONLY` |
| `overview.png`, `overview-{before,after}.png` | all seventeen rows at one scale (`yaw 90, pitch 40, distance 2800`) |
| `<label>-{before,after}-{close,rear,tactical,common-scale}.png` | the per-row frames |
| `<label>-ablated-{accent,dark,cool}.png` | one material role removed, from the camera that can see it |
| `<label>-close-restored.png` | the close view after the simulation was restored: `restored_changed_pixels: 0` |
| `<label>-{before,after}-motion.mp4` | the three paired 150-frame clips, `paired_samples_equal: true` |
| `<label>-{before,after}-ffmpeg.txt` | the encoder logs for those clips |

Batch totals from this run: close 5,853,167 changed pixels over 3 px, rear
4,706,715, tactical 345,405, overview 20,607; every row non-zero in all four
views and in all three role ablations; 221 files in total.
