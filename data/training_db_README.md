# training.db — Local SQLite Training Database

Raw FIT → SQLite pipeline. All numbers computed from per-second samples.
**No Garmin API. No summaries. Ground truth only.**

## Files

| File | Purpose |
|---|---|
| `data/training.db` | SQLite database (0.57 MB) |
| `scripts/fit_to_db.py` | ETL: parses all FIT files, populates DB |
| `scripts/query_db.py` | Full season analysis report |
| `data/fit-raw/*.fit` | 184 raw FIT files (45 MB) — source of truth |

## Tables

### `activities` — one row per ride
Session-level summary computed from raw records + FIT session message.

Key columns:
- `activity_id` — Garmin activity ID (TEXT, primary key)
- `date`, `month`, `year` — date fields
- `sport`, `sub_sport`, `is_indoor` — activity type
- `distance_km`, `elevation_gain_m`, `timer_time_s`, `calories`
- `avg_hr_bpm`, `max_hr_bpm`
- `has_power`, `avg_power_w`, `max_power_w`
- `np_w_session` — NP from Garmin's own session message
- `np_w_computed` — NP recomputed here from raw 1s records (more reliable)
- `threshold_power_w` — FTP stored in device at time of ride
- `pdc_5s_w` ... `pdc_60min_w` — Power Duration Curve (all computed from raw)
- `pw_hr_drift_pct` — aerobic coupling metric (NP/HR ratio first vs second half)
- `aerobic_eff_np_hr` — NP / avg_HR (W/bpm)
- `te_aerobic`, `te_anaerobic` — Garmin training effect labels
- `avg_temp_c`, `max_temp_c`

### `laps` — one row per FIT lap
From FIT lap messages + per-record zone assignment within each lap's time window.

Key columns:
- `activity_id`, `lap_index`, `start_time_utc`
- `elapsed_time_s`, `distance_km`, `elevation_gain_m`
- `avg_hr_bpm`, `max_hr_bpm`, `avg_power_w`, `max_power_w`, `np_w`
- `avg_vam` — vertical ascent rate (m/h)
- `lap_trigger` — 'manual', 'distance', 'time', etc.
- `hr_z1_s` ... `hr_z5_s` — seconds in each HR zone within this lap
- `pw_z1_s` ... `pw_z7_s` — seconds in each power zone (FTP=256W)

### `zone_summaries` — one row per ride, pre-aggregated zones
Pre-computed from per-second records. Fastest for season-level aggregations.

Key columns:
- `hr_z1_s` ... `hr_z5_s`, `hr_total_s` — HR zones (seconds)
- `pw256_z1_s` ... `pw256_z7_s`, `pw256_total_s` — Power zones at FTP=256W
- `pw235_z1_s` ... `pw235_z7_s`, `pw235_total_s` — Power zones at FTP=235W (corrected)

### `records` — one row per second (optional, not populated by default)
Written only when `fit_to_db.py --records` is used. ~100 MB.

## Zone definitions

### HR zones
| Zone | Range |
|---|---|
| Z1 | 100–129 bpm |
| Z2 | 130–154 bpm |
| Z3 | 155–165 bpm |
| Z4 | 166–179 bpm |
| Z5 | 180+ bpm |

### Power zones (FTP=256W — Garmin manual, untested)
| Zone | Range | Label |
|---|---|---|
| P1 | <141W | Recovery |
| P2 | 141–192W | Endurance |
| P3 | 193–230W | Tempo |
| P4 | 231–268W | Threshold |
| P5 | 269–307W | VO2max |
| P6 | 308–384W | Anaerobic |
| P7 | 384+W | NM |

### Power zones (FTP=235W — evidence-based, from Sep 19 15-min climb)
Same percentages, different watt values. Both stored in `zone_summaries`.

## Usage

```bash
# Rebuild entire database from FIT files
python3 scripts/fit_to_db.py --force

# Add new activities only (incremental)
python3 scripts/fit_to_db.py

# Reprocess one activity
python3 scripts/fit_to_db.py --activity 24419641071

# Full season analysis report
python3 scripts/query_db.py

# Ad-hoc SQL
sqlite3 data/training.db "
  SELECT date, np_w_computed, pdc_20min_w, pw_hr_drift_pct
  FROM activities
  WHERE has_power=1 AND is_indoor=0
  ORDER BY pdc_20min_w DESC LIMIT 10
"
```

## Key numbers (as of Sep 24 2026)

| Metric | Value |
|---|---|
| Total rides | 184 |
| Date range | 2025-09-28 → 2026-09-24 |
| Total distance | 10,313 km |
| Total elevation | 78,612 m |
| HR Z4+Z5 (all-time) | 857 min (3.7%) |
| HR Z4+ target | ≥15% → gap: 11.3pp |
| Season best 20-min PDC | 239W (Sep 19 Tre Valli) |
| Season best 5-min PDC | 279W (Sep 19 Tre Valli) |
| Season best 60-min | 216W (Jul 25 Ghisallino) |
| Aerobic efficiency avg | 1.202 W/bpm |

## Python environment

```
/Users/ettoretr/.cache/uv/archive-v0/kKQyyZw9eWA6xSrfjm0LO/bin/python3
```

Packages needed: `fitparse` (ETL), `sqlite3` (stdlib, always available).
