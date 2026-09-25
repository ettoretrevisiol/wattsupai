# WattsUpAI 🚴

> Personal cycling training coach powered by live Garmin data, raw FIT analysis, and AI.

**Live dashboard → [ettore.trevisiol.net/wattsupai](https://ettore.trevisiol.net/wattsupai)**

---

## What it is

WattsUpAI is a personal training system built for one athlete. It:

- Reads live Garmin Connect data (activities, HRV, sleep, training load)
- Maintains a local SQLite database built from raw FIT files — no Garmin summaries, no lap averages
- Computes NP, PDC, per-second HR/power zones, aerobic coupling, and aerobic efficiency from the raw signal
- Publishes a web dashboard to a personal domain for mobile access
- Runs an AI coach (Kiro agent) that reads the DB + live Garmin data to suggest daily sessions

---

## Setup (new machine)

```bash
git clone https://github.com/ettoretrevisiol/wattsupai
cd wattsupai
bash scripts/setup.sh
```

The setup script installs the Kiro agent config and handles Garmin auth. Then:

```bash
kiro-cli chat --agent wattsupai
```

### Prerequisites

| Tool | Install |
|------|---------|
| [Kiro CLI](https://kiro.ai) | Download from kiro.ai |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | `brew install git` (macOS) |

### Garmin auth

Tokens are stored in `~/.garminconnect` (never committed). They last ~6 months.

```bash
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
```

---

## Repo structure

```
wattsupai/
├── index.html                  # Dashboard — published to ettore.trevisiol.net/wattsupai
├── manifest.json / sw.js       # PWA support
├── goals.md                    # Current training goals — edit anytime
├── schedule.md                 # Weekly availability — edit anytime
│
├── data/
│   ├── training.db             # SQLite database — source of truth for all analysis
│   │                           # Tables: activities, laps, zone_summaries
│   │                           # Rebuilt from raw FIT with: python3 scripts/fit_to_db.py
│   └── dashboard.json          # Dashboard data (updated after each session)
│
├── scripts/
│   ├── fit_to_db.py            # ETL: raw FIT files → training.db
│   ├── update_dashboard.py     # Patch week_summary, milestones, VAM etc → dashboard.json
│   │                           # Also auto-logs post-ride note to training-log/
│   ├── log_session.py          # 3-question post-ride subjective prompt
│   └── query_db.py             # Full season analysis report (stdout)
│
├── docs/
│   ├── coaching-context.md     # Permanent coaching context: zones, FTP, findings, rules
│   ├── ZONES.md                # HR + power zone reference
│   └── training_db_README.md  # DB schema + usage docs
│
├── training-log/
│   └── current-plan.md         # Active plan + session log (rewrite each plan cycle)
│
├── agent/
│   ├── agent.json.template     # Kiro agent config template (deployed by setup.sh)
│   └── prompt.md               # Coach system prompt
│
└── icons/                      # PWA icons
```

**Not in git (local only):**
- `data/fit-raw/` — 184 raw FIT files (~45 MB). Contains GPS coordinates — never committed.
- `data/fit-analysis/`, `data/seconds/`, `data/series/`, `data/deep/` — regenerable caches.

---

## Athlete profile

| Parameter | Value |
|-----------|-------|
| FTP | **235W** (manual entry Sep 25 2026) |
| VO2max | **61** (peak this season: 62, Aug–Sep 2026) |
| CTL | ~803 |
| W/kg | **3.77** at 65 kg |

### Power zones (FTP 235W)

| Zone | Name | Watts | % FTP |
|------|------|-------|-------|
| Z1 | Recovery | <134W | <55% |
| Z2 | Endurance | 134–183W | 55–75% |
| Z3 | Tempo | 184–220W | 75–90% |
| Z4 | Threshold | 221–257W | 90–105% |
| Z5 | VO2max | 258–294W | 105–120% |
| Z6 | Anaerobic | 295–367W | 120–150% |
| Z7 | Neuromuscular | 368W+ | >150% |

### Heart rate zones

| Zone | Name | BPM |
|------|------|-----|
| Z1 | Recovery | 100–129 |
| Z2 | Endurance | 130–154 |
| Z3 | Tempo | 155–165 |
| Z4 | Threshold | 166–179 |
| Z5 | VO2max | 180+ |

---

## Data pipeline

```
data/fit-raw/*.fit
      │
      ▼
scripts/fit_to_db.py  ──►  data/training.db
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              activities        laps      zone_summaries
          (NP, PDC, drift)  (per-lap HR   (HR+power zones
                             & power)     at FTP=245W)
                    │
                    ▼
            scripts/query_db.py  ──►  stdout (full season report)
                    │
                    ▼
            data/dashboard.json  ──►  index.html (live dashboard)
```

`fit_to_db.py` computes everything from raw 1-second samples — no Garmin lap summaries used anywhere:
- **NP** via 30s rolling average → 4th power mean
- **PDC** at 5s / 30s / 1min / 5min / 10min / 20min / 60min
- **HR/power zones** — every sample classified, weighted by actual interval
- **Aerobic coupling** (HR drift %) — power:HR ratio first vs second half of ride
- **Aerobic efficiency** — NP / avg_HR (W/bpm)

### Rebuild the database

```bash
# Add only new activities (incremental)
python3 scripts/fit_to_db.py

# Full rebuild from scratch
python3 scripts/fit_to_db.py --force

# Reprocess one activity
python3 scripts/fit_to_db.py --activity 24419641071
```

Requires `fitparse`:
```bash
pip install fitparse
# or with the uv env that already has it:
# /Users/ettoretr/.cache/uv/archive-v0/kKQyyZw9eWA6xSrfjm0LO/bin/python3
```

---

## Season summary (Sep 2025 – Sep 2026)

| Metric | Value |
|--------|-------|
| Total rides | 184 |
| Distance | 10,313 km |
| Elevation | 78,612 m |
| HR-tracked time | 384h |
| Season best 5-min power | **279W** (Sep 19, Tre Valli Varesine) |
| Season best 20-min power | **239W** (Sep 19, Tre Valli Varesine) |
| HR Z4+Z5 all-time | 857 min (3.7%) — gap to 15% target: 11.3pp |
| Best aerobic efficiency | 1.421 W/bpm (Jun 30, Baita Resch) |

---

## 4-week plan (Sep 25 – Oct 19 2026)

Goal: hold/increase FTP before winter. Full details in `data/dashboard.json` → `training_plan`.

| Week | Tue | Thu | Sat NP target |
|------|-----|-----|---------------|
| W1 Sep 25–28 | 3×10 min Z3 (184–220W) | — | 182–190W |
| W2 Sep 30–Oct 5 | 2×15 min Z3→Z4 | 4×8 min Z4 (221–250W) | 185–192W |
| W3 Oct 7–12 | 3×15 min Z4 (221–250W) | 5×6 min Z5 (258–294W) | 192–200W |
| W4 Oct 13–19 | Easy Z2 | 2×10 min Z3 | ~165–175W |

---

## Update the dashboard

After any coaching session:

```bash
# Edit data/dashboard.json and/or index.html, then:
git add data/dashboard.json index.html
git commit --no-verify -m "describe change"
git push --no-verify origin main
# GitHub Pages redeploys in ~30 seconds
```

---

## Monitoring rules

| Signal | Action |
|--------|--------|
| HRV weekly avg ≥50ms | Train as planned ✅ |
| HRV 45–50ms | Soften Thu to Z3 only |
| HRV <45ms | Replace quality work with Z2 |
| HRV drops >10ms in 2 days | Full rest day |
| Sleep respiration >16 br/min | Check for illness before intensity |

---

## Key files for the AI coach

The Kiro agent (`wattsupai`) auto-loads:

| File | Purpose |
|------|---------|
| `goals.md` | Training goals and priorities |
| `schedule.md` | Weekly availability |
| `docs/coaching-context.md` | Full analytical context, zones, plan, findings |

Live Garmin data is fetched at session start via the Garmin MCP integration.

---

*Last updated: Sep 25 2026 · FTP 235W · VO2max 61 · CTL ~803*
