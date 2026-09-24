# data/fit-analysis/

FIT file analysis cache — one JSON per activity.

Updated by WattsUpAI (Kiro) after each ride session. To trigger an update, open a chat session and say "check my training".

## Coverage (as of Sep 24 2026)

- **118 files total**
- 37 outdoor power meter rides (road_biking, has_power: true) — full PDC, NP, HR drift, shifting quality
- ~65 indoor cycling sessions (indoor_cycling) — structured trainer sessions
- ~16 flat/no-power rides — HR-only data

## Schema

```json
{
  "activity_id": 12345678,
  "date": "YYYY-MM-DD",
  "route_name": "Route name",
  "sport": "cycling",
  "sub_sport": "road | indoor_cycling",
  "has_power": true,

  "session": {
    "np_w": 182,
    "avg_power_w": 148,
    "max_power_w": 809,
    "total_ascent_m": 2086,
    "avg_hr_bpm": 149,
    "max_hr_bpm": 175,
    "avg_cadence_rpm": 74,
    "total_distance_m": 106000,
    "total_elapsed_time_s": 25000,
    "total_timer_time_s": 23000,
    "variability_index": 1.23,
    "total_calories": 2500
  },

  "hr_drift": {
    "hr_drift_pct": -2.0,
    "interpretation": "well_coupled | moderate_decoupling | significant_decoupling | indoor_structured | no_power_meter"
  },

  "temperature": {
    "avg_temp_c": 22.0,
    "min_temp_c": 16,
    "max_temp_c": 30
  },

  "pdc": {
    "5s": 494,
    "30s": null,
    "1min": null,
    "5min": null,
    "10min": null,
    "20min": 239,
    "60min": 163
  },

  "best_climbing_laps": [
    {
      "lap": 4,
      "np_w": 237,
      "avg_power_w": 197,
      "avg_hr_bpm": 163,
      "ascent_m": 250,
      "notes": "best climb"
    }
  ],

  "shift_summary": {
    "total_shifts": 548,
    "proactive_pct": 63.5,
    "reactive_pct": 26.6,
    "avg_cadence_at_shift_rpm": 64.4
  },

  "notes": "Free text coaching notes"
}
```

## Key rules

- **Power detection**: `has_power = session.avg_power_w > 0`. Never assume power by bike type.
- **FTP**: 256W (Garmin manual entry Sep 12 2026)
- **HR zones**: Z1 100–129 | Z2 130–154 | Z3 155–165 | Z4 166–179 | Z5 180+
- **Power zones**: Z1 <141W | Z2 141–192W | Z3 193–230W | Z4 231–268W | Z5 269–307W | Z6 308–384W
- **NP for zone analysis**: Use per-climb lap NP, NOT 5km auto-lap averages (descents corrupt them)
- **HR drift interpretation**: `well_coupled` = <10% | `moderate` = 10–20% | `significant` = >20%

## Season PDC peak

Sep 19 2026 — Tre Valli Varesine — **239W** (20min)

## Source

Fetched via Garmin Connect MCP tool (`get_activity_fit_data`). Raw FIT files are not stored — only the extracted metrics above.
