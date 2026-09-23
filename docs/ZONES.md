# Training Zones

_Last updated: 23 Sep 2026_

## FTP

**256W** — Garmin Connect, manual entry Sep 12 2026.

To update: change in Garmin Connect → My Performance → Cycling FTP, then re-run `scripts/build_db.py` to reanalyse zone percentages.

---

## Heart Rate Zones

Configured in Garmin Connect device settings.

| Zone | Name | BPM |
|------|------|-----|
| Z1 | Recovery | 100–129 |
| Z2 | Endurance | 130–154 |
| Z3 | Tempo | 155–165 |
| Z4 | Threshold | 166–179 |
| Z5 | VO2max | 180–194 |

**Max HR used by Garmin:** 194 bpm  
**Lactate threshold HR:** 171 bpm (Garmin estimate)

---

## Power Zones

Calculated from FTP 256W using standard Garmin percentages.

| Zone | Name | Watts | % FTP |
|------|------|-------|-------|
| Z1 | Recovery | 0–140W | <55% |
| Z2 | Endurance | 141–192W | 55–75% |
| Z3 | Tempo | 193–230W | 75–90% |
| Z4 | Threshold | 231–268W | 90–105% |
| Z5 | VO2max | 269–307W | 105–120% |
| Z6 | Anaerobic | 308–384W | 120–150% |
| Z7 | Neuromuscular | 384W+ | >150% |

---

## Two-Bike Setup

| Bike | Power Meter | Primary metric |
|------|------------|----------------|
| Weekend / climbing bike | ✅ Yes | Watts (power meter) |
| Weekday flat bike | ❌ No | RPE + end-of-interval HR |

**Cardiac lag rule:** On the weekday bike, short intervals (6–10 min) won't show Z4 HR until the last 2–3 minutes. Judge quality by HR at the **end** of the rep, not during it.

---

## Key NP Reference Points (historical)

| NP | % FTP | Label | Notes |
|----|-------|-------|-------|
| 198W | 77% | AEROBIC_BASE | Aug 27 2026 — season peak NP |
| 196W | 77% | VO2MAX | Apr 23 2026 — season best label |
| 187W | 73% | LACTATE_THRESHOLD | Nov 3 2025 |
| 183W | 72% | LACTATE_THRESHOLD | Jul 25 2026 Ghisallino |
| 179W | 70% | AEROBIC_BASE | Sep 2026 plateau average |

To get a **Lactate Threshold label**: NP needs to reach ~183W+ with corresponding HR response. Target for W3 Oct 11: NP 198–215W.
