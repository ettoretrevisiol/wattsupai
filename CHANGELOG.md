# Changelog

All notable changes to the dashboard and training plan are recorded here.

---

## [Unreleased]

## 2026-09-23

### Added
- Full 12-month activity database (`data/activities.json`) — 186 activities with NP, training effect labels, HR zones, power zones
- `scripts/build_db.py` — database builder that fetches all activity details from Garmin Connect
- `scripts/setup.sh` — one-command setup script for new machines
- `agent/` — portable Kiro agent config and prompt, deploys with `setup.sh`
- `docs/ZONES.md` — FTP, HR zones, power zones reference
- `docs/coaching-context.md` — full analytical context for the AI coach
- GitHub Actions Lighthouse CI workflow

### Changed
- Dashboard rebuilt from database: FTP 256W (Garmin, Sep 12 2026), 68 NP data points, verified 3 LT/VO2MAX sessions in 12 months
- 4-week plan anchored to real NP targets (W1: 185–195W → W3: 198–215W)
- Saturday targets bumped to 1,500–2,200m climbing (realistic for the athlete)
- Plan sessions stripped to bare essentials — no commentary
- WattsUpAI status engine replaces Garmin's training status label
- Garmin tools expanded from 21 to 37 (added zone breakdowns, FTP, lactate threshold, power duration curve)
- Repo restructured: `data/`, `scripts/`, `docs/`, `agent/` folders

### Analysis findings
- **3 high-quality sessions in 12 months:** Nov 3 2025 (LT, NP 187W), Apr 23 2026 (VO2MAX, NP 196W — season best), Jul 25 2026 (LT, NP 183W)
- Peak NP: 198W (Aug 27 2026, Friuli — 77% FTP)
- Sep 2026 plateau: avg NP 179W, no LT label in 59 days
- FTP confirmed: 256W (Garmin manual entry Sep 12 2026)

---

## 2026-09-23 (initial)

### Added
- Initial dashboard (`index.html`) with 6-month cycling analysis
- `goals.md`, `schedule.md`
- GitHub Pages deployment at `ettore.trevisiol.net/wattsupai`
