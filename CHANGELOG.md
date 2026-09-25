# Changelog

---

## 2026-09-25

### Fixed
- Service worker cache bug: `CACHE_NAME` bumped to `v3` + `updatefound` handler added so new SW activates immediately instead of waiting for tab close. This was causing stale `index.html` to be served after pushes.

### Added
- Best Rides tab: VAM leaderboard (top 10 laps by vertical speed m/h) + Longest Rides by distance/duration. All rows link to Garmin Connect.
- Season Overview tab: Numbers & Milestones section — W/kg PDC progression, monthly elevation chart, aerobic efficiency top 5, top calorie burn days.
- Footer: git-sweaty tracker link alongside Strava.

### Changed
- `update_dashboard.py`: now computes `best_vam_laps`, `longest_rides`, `milestones` and patches them into `dashboard.json`.
- `docs/coaching-context.md`: fixed stale FTP=256 zone block — now shows FTP=245W throughout.
- `.gitignore`: added `data/ingest.log`.
- `README.md`: structure updated to include `training-log/`, all new scripts.
- `dashboard.json` version bumped to 6.1.

---

## 2026-09-24

### Added
- `data/training.db` — SQLite database built from raw FIT files. Tables: `activities`, `laps`, `zone_summaries`. Single source of truth for all analysis.
- `scripts/fit_to_db.py` — ETL pipeline: parses all 184 raw FIT files per-second into SQLite. Computes NP, PDC (5s–60min), HR/power zones at both FTP=256 and FTP=235, aerobic coupling (HR drift), aerobic efficiency.
- `scripts/query_db.py` — Full season analysis report from training.db. Pure SQL, runs in <1s.
- `data/training_db_README.md` — DB schema, table descriptions, usage docs.

### Changed
- FTP updated to **245W** (manual entry Sep 24 2026). All interval targets and zone boundaries recomputed.
- `dashboard.json` v6.0 — full refresh: zone distribution, PDC progression (78 rides, was 37), monthly stats, best climbing laps all rebuilt from training.db.
- Training plan power targets corrected for FTP=245W across all 4 weeks.
- `README.md` — full rewrite reflecting current pipeline and accurate athlete data.
- `.gitignore` — removed `data/fit-analysis/` and `data/seconds/` from tracking (regenerable from training.db). Added `data/series/`, `data/deep/`, retired scripts.

### Removed from tracking
- `data/fit-analysis/` (184 JSONs) — superseded by training.db
- `data/seconds/` (184 JSONs) — superseded by training.db zone_summaries
- `scripts/build_db.py` — superseded by fit_to_db.py
- `scripts/full_analysis.py` — development intermediate, superseded by query_db.py
- `scripts/raw_analysis.py` — development intermediate, superseded by query_db.py

### Analysis findings (per-second from raw FIT)
- HR Z4+Z5 all-time: **857 min (3.7%)** — gap to 15% target: 11.3pp
- Power Z4+ at FTP=256W: 6.2% · at FTP=235W: 12.1% · at FTP=245W: ~9–10%
- Season PDC peaks (all Sep 19 Tre Valli): 5s=934W · 5min=279W · 10min=267W · 20min=239W · 60min=216W
- Aug 2026 genuine Z4 dip (28.5 min) · Sep 2026 recovering (73 min)
- Best aerobic efficiency: 1.421 W/bpm (Jun 30 Baita Resch)

---

## 2026-09-24 (earlier)

### Changed
- `dashboard.json` — FTP reassessment: Garmin 256W never tested. Sep 19 15-min climb → evidence-based estimate 235W.
- Power zone FTP=235 targets added to training plan.
- `z4_drought` claim retracted: Z4 present in every month when measured per-second (lap-averaging was masking it).

---

## 2026-09-23

### Added
- Full 12-month analysis: 184 activities, per-second FIT parsing, NP + PDC across all rides.
- `scripts/fit_seconds.py` — raw FIT download + per-second zone totals.
- `scripts/fit_series.py` — 1Hz numpy series cache (.npz).
- `scripts/fit_deep.py` — PDC, effort detection, climb detection, decoupling.
- `scripts/setup.sh` — one-command new-machine setup.
- `agent/` — portable Kiro agent config + prompt.
- `docs/ZONES.md` — zone reference.
- `docs/coaching-context.md` — full analytical context.
- GitHub Actions Lighthouse CI workflow.

### Changed
- Dashboard rebuilt: FTP 256W, 37 outdoor power rides verified, PDC progression charted.
- 4-week plan anchored to real NP targets and HR targets.
- Garmin tools expanded from 21 to 37.

---

## 2026-09-23 (initial)

### Added
- Initial dashboard (`index.html`).
- `goals.md`, `schedule.md`.
- GitHub Pages at `ettore.trevisiol.net/wattsupai`.
