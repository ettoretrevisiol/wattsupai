# WattsUpAI 🚴

> Personal cycling training coach powered by live Garmin data, power analysis, and AI.  
> Built for daily use. Data-driven. No fluff.

**Live dashboard → [ettore.trevisiol.net/wattsupai](https://ettore.trevisiol.net/wattsupai)**

---

## Setup (New Machine)

```bash
# 1. Clone the repo
git clone https://github.com/ettoretrevisiol/wattsupai
cd wattsupai

# 2. Run setup — installs the Kiro agent, configures paths, handles Garmin auth
bash scripts/setup.sh
```

That's it. The setup script:
- Checks for `kiro-cli` and `uvx` (install these first if missing — see below)
- Installs the agent config into `~/.kiro/agents/wattsupai.json` with the correct absolute path
- Copies the agent prompt to `~/.kiro/agents/prompts/wattsupai.md`
- Runs Garmin authentication if no tokens are found in `~/.garminconnect`

Then start the coach:
```bash
kiro-cli chat --agent wattsupai
```

### Prerequisites

| Tool | Install |
|------|---------|
| [Kiro CLI](https://kiro.ai) | Download from kiro.ai |
| [uv / uvx](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | `brew install git` |

### Garmin Auth

Tokens are stored in `~/.garminconnect` (not in the repo — never committed). They last ~6 months. To re-authenticate at any time:
```bash
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
```

### Rebuild Activity Database

The local database (`data/activities.json`) is seeded with historical data. To refresh with latest activities:
```bash
python3 scripts/build_db.py
```

---



WattsUpAI is a personal training system that:

- Reads live Garmin Connect data (activities, HRV, sleep, training load, power zones)
- Analyses 12 months of cycling history with correct power zones (FTP-based)
- Maintains a local activity database for instant offline analysis
- Generates a data-driven 4-week training plan anchored to actual performance metrics
- Publishes a web dashboard to a personal domain for mobile access

This is not a generic fitness app. It is built around one athlete's data, goals, and constraints.

---

## Repo Structure

```
wattsupai/
├── index.html              # Dashboard (published to ettore.trevisiol.net/wattsupai)
├── goals.md                # Current training goals — edit anytime
├── schedule.md             # Weekly availability — edit anytime
│
├── data/
│   └── activities.json     # Local activity database (186 activities, 12 months)
│                           # Fields: NP, training effect, HR zones, power zones per ride
│
├── scripts/
│   └── build_db.py         # Database builder — fetches all activity details from Garmin
│
├── docs/
│   └── coaching-context.md # Full coaching context: zones, FTP, findings, rules
│
└── training-log/           # Free-text session notes (optional, read by the coach agent)
    └── YYYY-MM-DD.md
```

---

## Athlete Profile

| Parameter | Value |
|-----------|-------|
| FTP | **256W** (manual entry, confirmed Sep 12 2026) |
| Lactate Threshold HR | **171 bpm** |
| Max HR | **194 bpm** (Garmin HRmax used) |
| VO2max | **61** (peak this season: 62, Aug 2026) |
| CTL | **803** |

### Power Zones (FTP 256W)

| Zone | Name | Watts | % FTP |
|------|------|-------|-------|
| Z1 | Recovery | 0–140W | <55% |
| Z2 | Endurance | 141–192W | 55–75% |
| Z3 | Tempo | 193–230W | 75–90% |
| Z4 | Threshold | 231–268W | 90–105% |
| Z5 | VO2max | 269–307W | 105–120% |
| Z6 | Anaerobic | 308–384W | 120–150% |
| Z7 | Neuromuscular | 384W+ | >150% |

### Heart Rate Zones

| Zone | Name | BPM |
|------|------|-----|
| Z1 | Recovery | 100–129 |
| Z2 | Endurance | 130–154 |
| Z3 | Tempo | 155–165 |
| Z4 | Threshold | 166–179 |
| Z5 | VO2max | 180–194 |

### Bike Setup

| Bike | Power Meter | Used For |
|------|------------|---------|
| Weekend / climbing bike | ✅ Yes | Saturday rides — use watts as primary metric |
| Weekday bike | ❌ No | Tue/Thu intervals — use RPE + end-of-interval HR |

> **Key rule:** On the weekday bike, cardiac lag on short efforts is normal. Judge interval quality by HR at the **end** of each rep, not during it.

---

## Key Findings (from 12-month analysis)

### Training Load
- **186 rides** · **10,387 km** · **Sep 2025 – Sep 2026**
- Winter Oct–Mar: structured indoor block (Z2+Z3+Z4 intervals, 3–4×/week)
- Summer Jun–Sep: holiday blocks Cortina + Friuli, high volume outdoor
- Post-holiday drift into plateau (Sep 2026)

### Zone Distribution (outdoor power meter rides, last 4 months)
- All climbing rides: NP range **149–189W** = **58–74% of FTP** = Z2 range
- Z3 time (193–230W) accumulates during steep climbing sections
- Z4 (231W+) visible in power zone counters on hard rides (e.g. Culmine Sep 12: 50 min Z4; Tre Valli Sep 19: 34 min Z4)
- **No structured Z4 anywhere in the week** — the training gap

### Current WattsUpAI Status: **Plateau**
Aerobic low load: 3.7× above target. Aerobic high: **below target** (AEROBIC_HIGH_SHORTAGE confirmed by Garmin load balance). Recovery signals excellent. Fix: add 2× structured Z4 sessions/week (Tue/Thu).

---

## 4-Week Plan (Sep 25 – Oct 19, 2026)

Goal: **hold/increase FTP before winter**. Target NP progression on Saturday climbs.

| Week | Tue | Thu | Sat target | Sat NP target |
|------|-----|-----|-----------|---------------|
| W1 Sep 25–28 | 3×10 min Z3 | — | 800–1,000m | 185–195W |
| W2 Sep 30–Oct 5 | 2×15 min Z3→Z4 | 4×8 min Z4 | 1,000–1,300m | 193–205W |
| W3 Oct 7–12 | 3×15 min Z4 | 5×6 min Z5 | 1,400–1,700m | **205–220W** |
| W4 Oct 13–19 | Easy Z2 | 2×10 min Z3 | 400–600m | 170–185W |

**Success metric:** W3 Saturday NP ≥205W with Lactate Threshold training effect label.

---

## Monitoring Rules

| Signal | Action |
|--------|--------|
| HRV weekly avg ≥50ms | Train as planned ✅ |
| HRV 45–50ms | Soften Thursday to Z3 only |
| HRV <45ms | Replace all quality with Z2 |
| HRV drops >10ms in 2 days | Full rest day immediately |
| Sleep respiration >16 br/min | Check for illness before intensity |
| Sat NP not improving W1→W2→W3 | Check Thu session quality |

---

## Local Activity Database

`data/activities.json` contains structured records for all 186 activities:

```json
{
  "id": 24419641071,
  "date": "2026-09-19",
  "name": "Tre Valli Varesine",
  "category": "climbing_pm",
  "duration_min": 314.4,
  "distance_km": 126.8,
  "elevation_m": 2086,
  "np": 182,
  "np_pct_ftp": 71.1,
  "np_zone": "Z2 Endurance",
  "training_effect_label": "AEROBIC_BASE",
  "training_load": 371.1,
  "power_zones": {
    "3": 54.7,
    "4": 34.1,
    "5": 12.0
  }
}
```

To rebuild or update the database:

```bash
cd scripts
python3 build_db.py
```

Requires Garmin authentication tokens in `~/.garminconnect`. To re-authenticate:

```bash
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
```

---

## Dashboard

The dashboard (`index.html`) is a self-contained single-file HTML/JS app. No build step, no dependencies beyond two CDN loads (Chart.js + Google Fonts).

Published via GitHub Pages to a custom domain. To update:

```bash
# After editing index.html:
git add index.html
git commit --no-verify -m "describe change"
git push --no-verify origin main
# GitHub Pages redeploys in ~30 seconds
```

**Tabs:**
- Season Overview — 12-month stats, WattsUpAI status, NP trend chart, milestones
- Training Load — PMC (CTL/ATL/TSB), VO2max trend, load snapshot
- Recovery & HRV — 30-day HRV chart, respiration, monitoring rules
- Best Rides — top climbs and longest rides
- 4-Week Plan — session-by-session with NP targets, HR targets, coaching notes

---

## AI Coach (WattsUpAI Agent)

The Kiro AI agent `wattsupai` reads this repo + live Garmin data to answer questions and suggest daily sessions.

```bash
kiro-cli chat --agent wattsupai
```

**Resources auto-loaded:** `goals.md`, `schedule.md`, `docs/coaching-context.md`, `training-log/`

**37 Garmin tools enabled**, including:
- `get_activity_hr_in_timezones` — exact HR zone time per activity
- `get_activity_power_in_timezones` — exact power zone time per activity  
- `get_cycling_ftp` — FTP from Garmin
- `get_heart_rate_zones` — saved HR zones from device
- `get_power_duration_curve` — season-best power curve
- `get_training_load_balance` — aerobic low/high/anaerobic distribution
- `get_lactate_threshold` — Garmin's LT estimate

**Analysis rules (important):**
- Never use 5km auto-lap averages for zone analysis — descents drag the average down
- Use `get_activity()` for NP + training_effect_label (correct intensity metric for hilly rides)
- Use `get_activity_power_in_timezones()` for actual time-in-zone data
- FTP is **256W** — always use this, never estimate from lap data

---

## Garmin Auth

Tokens live in `~/.garminconnect`. They last ~6 months. To re-authenticate:

```bash
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
```

---

## Goals

See [`goals.md`](goals.md) for current training goals and priorities.  
See [`schedule.md`](schedule.md) for weekly availability.  
See [`docs/coaching-context.md`](docs/coaching-context.md) for full analytical context.

---

*Last updated: 23 Sep 2026 · FTP 256W · CTL 803 · VO2max 61*
