#!/usr/bin/env python3
"""
update_dashboard.py — Patch live compliance data into dashboard.json.

Reads training.db, computes:
  - week_summary:     this week's rides, Z4 minutes, status vs plan target
  - last_4_saturdays: last 4 Saturday NP values + trend direction

Writes result back to data/dashboard.json in-place.

Run after each new activity ingested by fit_to_db.py.
Also run by the launchd auto-ingest job (installed by setup.sh).

Usage:
  python3 scripts/update_dashboard.py
"""

import json
import sqlite3
import os
from datetime import date, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH   = os.path.join(REPO, "data", "training.db")
DASH_PATH = os.path.join(REPO, "data", "dashboard.json")

# ── Plan targets (update each time the plan changes) ─────────────────────────
# Keyed by ISO week start (Monday). z4_target_min = 0 means "any Z4 is bonus"
PLAN_TARGETS = {
    "2026-09-21": {"week": 1, "label": "W1 Re-anchor Z3",  "z4_target_min": 0,  "sat_np_min": 182, "sat_np_max": 190},
    "2026-09-28": {"week": 2, "label": "W2 First Z4",       "z4_target_min": 25, "sat_np_min": 185, "sat_np_max": 192},
    "2026-10-05": {"week": 3, "label": "W3 Crack Threshold","z4_target_min": 40, "sat_np_min": 192, "sat_np_max": 200},
    "2026-10-12": {"week": 4, "label": "W4 Recovery",        "z4_target_min": 0,  "sat_np_min": 165, "sat_np_max": 175},
}


def get_week_start(d=None):
    """Return Monday of the current (or given) week."""
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def compute_week_summary(conn):
    today = date.today()
    ws    = get_week_start(today)
    we    = today

    # Plan target for this week
    ws_iso = ws.isoformat()
    target = PLAN_TARGETS.get(ws_iso, {})

    rows = conn.execute("""
        SELECT a.date, a.sub_sport, a.has_power,
               ROUND(a.distance_km, 0)            AS km,
               a.np_w_computed                     AS np,
               a.pdc_20min_w                       AS pdc20,
               ROUND((zs.hr_z4_s + zs.hr_z5_s) / 60.0, 1) AS z4_min
        FROM activities a
        JOIN zone_summaries zs USING (activity_id)
        WHERE a.date >= ? AND a.date <= ?
        ORDER BY a.date
    """, (ws_iso, we.isoformat())).fetchall()

    z4_total = sum(r[6] or 0 for r in rows)
    rides    = [
        {
            "date":      r[0],
            "sport":     r[1],
            "has_power": bool(r[2]),
            "km":        r[3],
            "np_w":      r[4],
            "pdc20_w":   r[5],
            "z4_min":    round(r[6] or 0, 1),
        }
        for r in rows
    ]

    # Status vs target
    z4_target = target.get("z4_target_min", 0)
    if z4_target == 0:
        z4_status = "bonus"          # W1: any Z4 counts as bonus
    elif z4_total >= z4_target:
        z4_status = "on_track"
    elif z4_total >= z4_target * 0.6:
        z4_status = "partial"
    else:
        z4_status = "behind"

    return {
        "week_start":     ws_iso,
        "week_end":       we.isoformat(),
        "week_label":     target.get("label", f"Week of {ws_iso}"),
        "plan_week_num":  target.get("week"),
        "rides_count":    len(rides),
        "rides":          rides,
        "z4_min_total":   round(z4_total, 1),
        "z4_target_min":  z4_target,
        "z4_status":      z4_status,      # "on_track" | "partial" | "behind" | "bonus"
        "sat_np_target":  [target.get("sat_np_min"), target.get("sat_np_max")] if target else None,
    }


def compute_last_4_saturdays(conn):
    rows = conn.execute("""
        SELECT date,
               np_w_computed                        AS np,
               pdc_20min_w                          AS pdc20,
               ROUND(elevation_gain_m, 0)           AS elev_m,
               ROUND(distance_km, 0)                AS km,
               ROUND(elapsed_time_s / 3600.0, 1)    AS hours
        FROM activities
        WHERE strftime('%w', date) = '6'    -- Saturday
          AND is_indoor = 0
        ORDER BY date DESC
        LIMIT 4
    """).fetchall()

    results = []
    for i, r in enumerate(rows):
        prev_np = rows[i + 1][1] if i + 1 < len(rows) else None
        trend   = None
        if r[1] and prev_np:
            diff  = r[1] - prev_np
            trend = "up" if diff > 3 else ("down" if diff < -3 else "flat")
        results.append({
            "date":    r[0],
            "np_w":    r[1],
            "pdc20_w": r[2],
            "elev_m":  r[3],
            "km":      r[4],
            "hours":   r[5],
            "np_trend_vs_prev": trend,   # "up" | "down" | "flat" | null
        })

    return results


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        print("Run: python3 scripts/fit_to_db.py")
        raise SystemExit(1)

    if not os.path.exists(DASH_PATH):
        print(f"ERROR: dashboard.json not found at {DASH_PATH}")
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)

    week_summary    = compute_week_summary(conn)
    last_4_sats     = compute_last_4_saturdays(conn)

    conn.close()

    # Patch into dashboard.json
    with open(DASH_PATH) as f:
        d = json.load(f)

    d["week_summary"]    = week_summary
    d["last_4_saturdays"] = last_4_sats

    with open(DASH_PATH, "w") as f:
        json.dump(d, f, indent=2)

    print(f"✓ dashboard.json updated")
    print(f"  Week {week_summary['week_start']}: {week_summary['rides_count']} ride(s), "
          f"Z4={week_summary['z4_min_total']}min ({week_summary['z4_status']})")
    if last_4_sats:
        sat_str = "  Last 4 Sat NP: " + " → ".join(
            f"{s['np_w'] or '-'}W" for s in reversed(last_4_sats)
        )
        print(sat_str)


if __name__ == "__main__":
    main()
