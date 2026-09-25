#!/usr/bin/env python3
"""
update_dashboard.py — Patch live compliance data into dashboard.json
                      and auto-log post-ride notes to training-log/current-plan.md.

Reads training.db, computes:
  - week_summary:        rides, Z4 min, status vs plan target
  - week_summary.progression_flag: stay / increase / reduce (for next week)
  - week_summary.next_session:     terrain-aware suggestion for the next planned session
  - last_4_saturdays:   last 4 Saturday NP values + trend direction

Also appends an objective post-ride note to training-log/current-plan.md
for the most recent activity (if it hasn't been logged yet).

Run after each new activity ingested by fit_to_db.py.

Usage:
  python3 scripts/update_dashboard.py
  python3 scripts/update_dashboard.py --no-log    # skip appending to current-plan.md
"""

import json
import sqlite3
import os
import sys
from datetime import date, timedelta

REPO      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH   = os.path.join(REPO, "data", "training.db")
DASH_PATH = os.path.join(REPO, "data", "dashboard.json")
LOG_PATH  = os.path.join(REPO, "training-log", "current-plan.md")

NO_LOG = "--no-log" in sys.argv

# ── Plan targets (update each time the plan changes) ─────────────────────────
# Keyed by ISO week-start (Monday).
# z4_target_min = 0  → W1/W4, any Z4 is a bonus, no hard target
# sessions: ordered list of planned sessions remaining in the week
PLAN_TARGETS = {
    "2026-09-21": {
        "week": 1, "label": "W1 Re-anchor Z3",
        "z4_target_min": 0,
        "sat_np_min": 182, "sat_np_max": 190,
        "sessions": [
            {"day": "Thu", "type": "Z3",  "desc": "3×10min Z3 · 176–211W · end HR 158–165bpm"},
            {"day": "Sat", "type": "climb","desc": "3–3.5h · 800–1000m climbing · NP 182–190W"},
            {"day": "Sun", "type": "Z2",  "desc": "Z2 recovery · ≤145bpm"},
        ],
    },
    "2026-09-28": {
        "week": 2, "label": "W2 First Z4",
        "z4_target_min": 25,
        "sat_np_min": 185, "sat_np_max": 192,
        "sessions": [
            {"day": "Tue", "type": "Z4",   "desc": "2×15min progressive Z3→Z4 · end HR ≥166bpm"},
            {"day": "Thu", "type": "Z4",   "desc": "4×8min Z4 · 211–246W · end HR 166–174bpm"},
            {"day": "Sat", "type": "climb","desc": "3.5–4h · 1000–1300m climbing · NP 185–192W"},
            {"day": "Sun", "type": "Z2",   "desc": "Z2 · ≤145bpm"},
        ],
    },
    "2026-10-05": {
        "week": 3, "label": "W3 Crack Threshold",
        "z4_target_min": 40,
        "sat_np_min": 192, "sat_np_max": 200,
        "sessions": [
            {"day": "Tue", "type": "Z4",   "desc": "3×15min Z4 · 211–246W · end HR 166–174bpm"},
            {"day": "Thu", "type": "Z5",   "desc": "5×6min Z5 · 246–282W · end HR 172–179bpm"},
            {"day": "Sat", "type": "climb","desc": "4–4.5h · 1400–1700m climbing · NP 192–200W (target: LT label)"},
            {"day": "Sun", "type": "Z2",   "desc": "recovery · ≤140bpm"},
        ],
    },
    "2026-10-12": {
        "week": 4, "label": "W4 Recovery",
        "z4_target_min": 0,
        "sat_np_min": 165, "sat_np_max": 175,
        "sessions": [
            {"day": "Thu", "type": "Z3",   "desc": "2×10min Z3 · 176–211W · easy pace"},
            {"day": "Sat", "type": "climb","desc": "easy · ~400–600m climbing · NP 165–175W"},
        ],
    },
}

DOW_NAME = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def get_week_start(d=None):
    d = d or date.today()
    return d - timedelta(days=d.weekday())


# ── 1. Week summary with Z4 status ───────────────────────────────────────────

def compute_week_summary(conn):
    today  = date.today()
    ws     = get_week_start(today)
    we     = today
    ws_iso = ws.isoformat()
    target = PLAN_TARGETS.get(ws_iso, {})

    rows = conn.execute("""
        SELECT a.date, a.sub_sport, a.has_power,
               ROUND(a.distance_km, 0)                       AS km,
               a.np_w_computed                               AS np,
               a.pdc_20min_w                                 AS pdc20,
               ROUND((zs.hr_z4_s + zs.hr_z5_s) / 60.0, 1)  AS z4_min,
               a.pw_hr_drift_pct                             AS drift,
               a.max_hr_bpm                                  AS max_hr
        FROM activities a
        JOIN zone_summaries zs USING (activity_id)
        WHERE a.date >= ? AND a.date <= ?
        ORDER BY a.date
    """, (ws_iso, we.isoformat())).fetchall()

    z4_total = sum(r[6] or 0 for r in rows)
    rides = [
        {
            "date":      r[0],
            "sport":     r[1],
            "has_power": bool(r[2]),
            "km":        r[3],
            "np_w":      r[4],
            "pdc20_w":   r[5],
            "z4_min":    round(r[6] or 0, 1),
            "drift_pct": r[7],
            "max_hr":    r[8],
        }
        for r in rows
    ]

    z4_target = target.get("z4_target_min", 0)
    if z4_target == 0:
        z4_status = "bonus"
    elif z4_total >= z4_target:
        z4_status = "on_track"
    elif z4_total >= z4_target * 0.6:
        z4_status = "partial"
    else:
        z4_status = "behind"

    return {
        "week_start":    ws_iso,
        "week_end":      we.isoformat(),
        "week_label":    target.get("label", f"Week of {ws_iso}"),
        "plan_week_num": target.get("week"),
        "rides_count":   len(rides),
        "rides":         rides,
        "z4_min_total":  round(z4_total, 1),
        "z4_target_min": z4_target,
        "z4_status":     z4_status,
        "sat_np_target": [target.get("sat_np_min"), target.get("sat_np_max")] if target else None,
    }


# ── 2. Progression flag ───────────────────────────────────────────────────────
# Compares this week's Z4 actual to the *next* week's target and recommends
# whether to increase, stay, or reduce intensity.

def compute_progression_flag(week_summary):
    today      = date.today()
    ws         = get_week_start(today)
    next_ws    = ws + timedelta(weeks=1)
    next_iso   = next_ws.isoformat()
    next_target = PLAN_TARGETS.get(next_iso, {})

    this_z4    = week_summary["z4_min_total"]
    this_z4_tgt = week_summary["z4_target_min"]
    next_z4_tgt = next_target.get("z4_target_min", 0)
    week_num    = week_summary.get("plan_week_num")

    # Rule: can we progress to next week?
    #   increase   → this week was on_track AND next week asks for more
    #   stay       → partial / borderline
    #   reduce     → behind, or this week's status is behind
    #   recovery   → next week is W4 (z4_target=0)

    if next_z4_tgt == 0:
        flag = "recovery"
        reason = "Next week is W4 recovery — volume drops, intensity eases."
    elif week_summary["z4_status"] == "on_track":
        flag = "increase"
        reason = (f"This week: {this_z4:.0f}min Z4 ≥ {this_z4_tgt}min target. "
                  f"Green light for W{(week_num or 0)+1} ({next_z4_tgt}min target).")
    elif week_summary["z4_status"] == "partial":
        flag = "stay"
        reason = (f"This week: {this_z4:.0f}min Z4 (partial vs {this_z4_tgt}min target). "
                  f"Repeat same intensity next week before adding load.")
    elif week_summary["z4_status"] in ("behind", "bonus") and this_z4_tgt > 0:
        flag = "reduce"
        reason = (f"This week: only {this_z4:.0f}min Z4 vs {this_z4_tgt}min target. "
                  f"Reduce next week's targets — don't jump to W{(week_num or 0)+1} load.")
    else:
        # W1 bonus week — no hard target, just confirm base before stepping up
        flag = "increase" if this_z4 >= 10 else "stay"
        reason = (f"W1 base week: {this_z4:.0f}min Z4 accumulated. "
                  + ("Good base — proceed to W2 Z4 target." if this_z4 >= 10
                     else "Light Z4 week — ease into W2, don't rush targets."))

    return {
        "flag":        flag,     # "increase" | "stay" | "reduce" | "recovery"
        "reason":      reason,
        "next_week":   next_iso,
        "next_z4_tgt": next_z4_tgt,
    }


# ── 3. Terrain-aware next session suggestion ──────────────────────────────────

def compute_next_session_suggestion(conn, week_summary):
    """
    Look at what sessions remain this week (based on today's day-of-week),
    find the next planned session type, then suggest terrain from DB history.
    """
    today      = date.today()
    ws_iso     = week_summary["week_start"]
    target     = PLAN_TARGETS.get(ws_iso, {})
    sessions   = target.get("sessions", [])
    today_dow  = DOW_NAME[today.weekday()]   # "Mon".."Sun"

    # Days already ridden this week
    ridden_dates = {r["date"] for r in week_summary["rides"]}

    # Find the next unridden planned session
    dow_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_idx  = dow_order.index(today_dow)

    next_sess = None
    for sess in sessions:
        sess_idx = dow_order.index(sess["day"])
        # Include today and future days that haven't been done yet
        if sess_idx >= today_idx:
            # Check if this day already has a ride logged
            # (approximate: check if any ride in week falls on this weekday)
            day_date = (date.fromisoformat(ws_iso)
                        + timedelta(days=sess_idx))
            if day_date.isoformat() not in ridden_dates:
                next_sess = sess
                break

    if not next_sess:
        return {"message": "All planned sessions this week are done. Rest or Z2 only."}

    stype = next_sess["type"]
    day   = next_sess["day"]
    desc  = next_sess["desc"]

    # Build terrain context from DB
    terrain_hint = ""

    if stype in ("Z3", "Z4", "Z5"):
        # Weekday interval suggestion — flat or small hill
        # Look at recent well-coupled flat rides for route context
        flat_rides = conn.execute("""
            SELECT date, ROUND(distance_km,0) km,
                   avg_hr_bpm, max_hr_bpm,
                   pw_hr_drift_pct drift
            FROM activities
            WHERE is_indoor=0 AND has_power=0
              AND elevation_gain_m < 100
              AND elapsed_time_s BETWEEN 3600 AND 7200
            ORDER BY date DESC LIMIT 3
        """).fetchall()

        # Best Z4 lap on a flat weekday ride
        best_z4_flat = conn.execute("""
            SELECT a.date, MAX(l.avg_hr_bpm) peak_hr,
                   ROUND((zs.hr_z4_s+zs.hr_z5_s)/60.0,1) z4_min
            FROM activities a
            JOIN zone_summaries zs USING(activity_id)
            LEFT JOIN laps l USING(activity_id)
            WHERE a.is_indoor=0 AND a.has_power=0
              AND a.elevation_gain_m < 100
              AND (zs.hr_z4_s+zs.hr_z5_s) > 60
            GROUP BY a.activity_id
            ORDER BY z4_min DESC LIMIT 1
        """).fetchone()

        if stype == "Z3":
            terrain_hint = (
                "Flat or gently rolling route (any weekday flat). "
                "Pick a section with no traffic lights for 10min blocks. "
                "Judge quality by HR at END of each rep — cardiac lag is normal."
            )
        elif stype == "Z4":
            if best_z4_flat:
                terrain_hint = (
                    f"Best Z4 flat day on record: {best_z4_flat[0]} "
                    f"(peak HR {best_z4_flat[1]}bpm, {best_z4_flat[2]}min Z4). "
                    "Repeat a similar flat route with a long straight or small false flat. "
                    "Target HR 166–174bpm at END of rep. Cardiac lag: first 2–3 min will feel ok, then it builds."
                )
            else:
                terrain_hint = (
                    "Flat route, long straight sections. "
                    "Target HR 166–174bpm at end of each interval."
                )
        elif stype == "Z5":
            terrain_hint = (
                "Small climb (5–8min, any gradient) or flat false flat at high power. "
                "VO2max efforts: start at the bottom fresh, go all-in for 6min. "
                "HR will lag — target 172–179bpm at the end, not the start."
            )

    elif stype == "climb":
        # Saturday climbing suggestion from actual lap history
        # What elevation range is the target?
        np_min  = target.get("sat_np_min", 180)
        np_max  = target.get("sat_np_max", 195)
        elev_min = {"W1": 800, "W2": 1000, "W3": 1400, "W4": 400}.get(
            target.get("label", "")[:2], 800)
        elev_max = {"W1": 1000, "W2": 1300, "W3": 1700, "W4": 600}.get(
            target.get("label", "")[:2], 1200)

        # Find best lap with NP in target range and climb 10–25min
        ref_laps = conn.execute("""
            SELECT a.date,
                   l.np_w, l.avg_hr_bpm,
                   ROUND(l.elevation_gain_m,0) elev,
                   ROUND(l.elapsed_time_s/60.0,1) min
            FROM laps l JOIN activities a USING(activity_id)
            WHERE a.has_power=1 AND a.is_indoor=0
              AND l.np_w BETWEEN ? AND ?
              AND l.elevation_gain_m BETWEEN 80 AND 400
              AND l.elapsed_time_s BETWEEN 600 AND 1800
            ORDER BY l.np_w DESC
            LIMIT 3
        """, (np_min - 10, np_max + 10)).fetchall()

        # Recent Sat climbs near the target elevation
        ref_rides = conn.execute("""
            SELECT date, ROUND(elevation_gain_m,0) elev,
                   np_w_computed np, ROUND(elapsed_time_s/3600.0,1) h
            FROM activities
            WHERE strftime('%w',date)='6' AND has_power=1 AND is_indoor=0
              AND elevation_gain_m BETWEEN ? AND ?
            ORDER BY date DESC LIMIT 3
        """, (elev_min * 0.7, elev_max * 1.3)).fetchall()

        lap_ref = ""
        if ref_laps:
            best = ref_laps[0]
            lap_ref = (f" Reference: {best[0]} lap {best[4]}min / {best[3]}m / "
                       f"NP {best[1]}W at {best[2]}bpm — this is the target feel.")

        ride_ref = ""
        if ref_rides:
            r = ref_rides[0]
            ride_ref = (f" Closest historical Saturday: {r[0]} "
                        f"({r[1]:.0f}m elev, NP {r[2]}W, {r[3]}h).")

        terrain_hint = (
            f"Target {elev_min}–{elev_max}m climbing in 3–4.5h. "
            f"NP target {np_min}–{np_max}W — build to this across the ride, "
            f"not just the first climb."
            f"{lap_ref}{ride_ref}"
        )

    elif stype == "Z2":
        terrain_hint = (
            "Flat or gently rolling. Strict HR cap ≤145bpm — if a climb "
            "pushes you to 150+, ease off or walk. This ride is recovery, "
            "not fitness building."
        )

    return {
        "day":          day,
        "type":         stype,
        "desc":         desc,
        "terrain_hint": terrain_hint,
    }


# ── WattsUpAI custom status ───────────────────────────────────────────────────

def compute_wattsupai_status(conn, hrv_weekly_avg, hrv_last_night, ctl, atl, tsb):
    """
    Compute a context-aware training status that accounts for:
    - Two-bike setup: power meter on weekend bike only
    - Weekday rides: HR-only, structured intervals possible
    - Primary signal: power Z4+ minutes (last 28d) where available
    - Secondary signal: HR Z4+ minutes (fallback for no-power days)
    - Recovery: HRV trend, TSB, RHR

    Returns a dict with label, color, code, explanation, and key metrics.
    """
    from datetime import date as dtdate

    today = dtdate.today().isoformat()

    # ── Collect signals ────────────────────────────────────────────────────────
    r = conn.execute("""
        SELECT
            -- Dual-signal Z4: power where available, HR as fallback
            ROUND(SUM(
                CASE WHEN a.has_power=1
                     THEN zs.pw245_z4_s+zs.pw245_z5_s+zs.pw245_z6_s+zs.pw245_z7_s
                     ELSE zs.hr_z4_s+zs.hr_z5_s END
            )/60.0, 1)                                                          AS dual_z4_min,
            ROUND(100.0*SUM(
                CASE WHEN a.has_power=1
                     THEN zs.pw245_z4_s+zs.pw245_z5_s+zs.pw245_z6_s+zs.pw245_z7_s
                     ELSE zs.hr_z4_s+zs.hr_z5_s END
            )/NULLIF(SUM(
                CASE WHEN a.has_power=1 THEN zs.pw245_total_s ELSE zs.hr_total_s END
            ),0), 1)                                                            AS dual_z4_pct,
            -- Power-only Z4 (quality climbing rides)
            ROUND(SUM(CASE WHEN a.has_power=1
                           THEN zs.pw245_z4_s+zs.pw245_z5_s+zs.pw245_z6_s+zs.pw245_z7_s
                           ELSE 0 END)/60.0, 1)                                AS pw_z4_min,
            -- Recent NP trend (last 4 Saturdays with power)
            COUNT(DISTINCT a.activity_id)                                       AS rides_28d,
            SUM(CASE WHEN a.has_power=1 THEN 1 ELSE 0 END)                     AS power_rides_28d,
            -- Weekday Z4 (HR signal, no-power rides)
            ROUND(SUM(CASE WHEN a.has_power=0
                           THEN zs.hr_z4_s+zs.hr_z5_s ELSE 0 END)/60.0, 1)   AS weekday_z4_min
        FROM activities a
        JOIN zone_summaries zs USING(activity_id)
        WHERE a.date >= date(?, '-28 days')
    """, (today,)).fetchone()

    dual_z4_min     = r[0] or 0
    dual_z4_pct     = r[1] or 0
    pw_z4_min       = r[2] or 0
    rides_28d       = r[3] or 0
    power_rides_28d = r[4] or 0
    weekday_z4_min  = r[5] or 0

    # Last 4 Sat NP trend
    sats = conn.execute("""
        SELECT np_w_computed FROM activities
        WHERE strftime('%w',date)='6' AND has_power=1 AND is_indoor=0
          AND date >= date(?, '-28 days')
        ORDER BY date DESC LIMIT 4
    """, (today,)).fetchall()
    sat_nps = [s[0] for s in sats if s[0]]
    np_trend = "rising" if len(sat_nps) >= 2 and sat_nps[0] > sat_nps[-1] + 3 else \
               "falling" if len(sat_nps) >= 2 and sat_nps[0] < sat_nps[-1] - 3 else "flat"
    latest_sat_np = sat_nps[0] if sat_nps else None

    # This week Z4
    week_start = (dtdate.today() - __import__('datetime').timedelta(days=dtdate.today().weekday())).isoformat()
    this_week_z4 = conn.execute("""
        SELECT ROUND(SUM(
            CASE WHEN a.has_power=1
                 THEN zs.pw245_z4_s+zs.pw245_z5_s+zs.pw245_z6_s+zs.pw245_z7_s
                 ELSE zs.hr_z4_s+zs.hr_z5_s END
        )/60.0, 1)
        FROM activities a JOIN zone_summaries zs USING(activity_id)
        WHERE a.date >= ?
    """, (week_start,)).fetchone()[0] or 0

    # ── Classify status ────────────────────────────────────────────────────────
    # Recovery check (overrides everything)
    hrv_drop = (hrv_weekly_avg or 50) - (hrv_last_night or 50)
    if tsb < -120 or hrv_drop > 12:
        code = "OVERREACHING"
        label = "Overreaching — reduce load"
        color = "red"
        explanation = (
            f"HRV dropped {hrv_drop:.0f}ms below weekly avg, or TSB {tsb} is critically low. "
            "Body is not absorbing training. Replace all quality with Z2 today."
        )
    # Detraining
    elif rides_28d < 8 or (ctl < 600 and tsb > 50):
        code = "DETRAINING"
        label = "Detraining — volume too low"
        color = "red"
        explanation = (
            f"Only {rides_28d} rides in 28 days. CTL {ctl} dropping with TSB {tsb}. "
            "Fitness eroding. Increase frequency before adding intensity."
        )
    # Building — quality work is present and producing
    elif dual_z4_pct >= 12 and np_trend in ("rising", "flat") and (hrv_weekly_avg or 0) >= 48:
        code = "BUILDING"
        label = "Building — quality stimulus present"
        color = "green"
        explanation = (
            f"Dual-signal Z4+: {dual_z4_min:.0f}min ({dual_z4_pct:.1f}%) over 28 days. "
            f"NP trend {np_trend} (last Sat: {latest_sat_np}W). "
            f"HRV {hrv_weekly_avg}ms — recovery holding. Plan is working."
        )
    # Productive — intensity there but not peak
    elif dual_z4_pct >= 7 and (hrv_weekly_avg or 0) >= 45:
        code = "PRODUCTIVE"
        label = "Productive — base solid, intensity adequate"
        color = "blue"
        explanation = (
            f"Z4+ at {dual_z4_pct:.1f}% (dual-signal, 28d). "
            f"NP {np_trend} at {latest_sat_np}W. "
            "Above minimum threshold stimulus. Continue current structure."
        )
    # Base phase — volume there, intensity missing
    elif rides_28d >= 8 and dual_z4_pct < 7:
        code = "BASE_PHASE"
        label = "Base Phase — intensity needed"
        color = "orange"
        # Diagnose which part is missing
        if pw_z4_min >= 40 and weekday_z4_min < 20:
            gap = "Saturday climbing contributes quality, but weekday intervals are missing. Add 2 structured sessions/week."
        elif pw_z4_min < 40 and weekday_z4_min >= 20:
            gap = "Weekday HR Z4 present, but Saturday NP needs pushing harder on climbs."
        else:
            gap = "Both weekday intervals and Saturday NP targets need stepping up."
        explanation = (
            f"Dual-signal Z4+: only {dual_z4_min:.0f}min ({dual_z4_pct:.1f}%) over 28 days. "
            f"Volume solid ({rides_28d} rides), aerobic base good. {gap}"
        )
    else:
        code = "MAINTAINING"
        label = "Maintaining — consistent but low stimulus"
        color = "yellow"
        explanation = (
            f"Z4+: {dual_z4_min:.0f}min over 28 days. "
            f"Ride frequency {rides_28d}/28d is adequate. "
            "FTP holding but not improving. Add one quality session to progress."
        )

    return {
        "code":              code,
        "label":             label,
        "color":             color,
        "explanation":       explanation,
        "dual_z4_min_28d":   round(dual_z4_min, 1),
        "dual_z4_pct_28d":   round(dual_z4_pct, 1),
        "pw_z4_min_28d":     round(pw_z4_min, 1),
        "weekday_z4_min_28d": round(weekday_z4_min, 1),
        "this_week_z4_min":  round(this_week_z4, 1),
        "np_trend":          np_trend,
        "latest_sat_np":     latest_sat_np,
        "rides_28d":         rides_28d,
        "power_rides_28d":   power_rides_28d,
        "signal_note":       (
            f"Power Z4 (Sat/weekend bike, FTP=235W): {pw_z4_min:.0f}min | "
            f"HR Z4 (weekday bike, fallback): {weekday_z4_min:.0f}min"
        ),
    }


def compute_status_history(conn):
    """
    Run the WattsUpAI status model for every calendar week in the DB.
    Returns a list of weekly snapshots ordered oldest-first — used to draw
    the season status timeline on the dashboard.
    """
    import datetime

    # Find season start and end
    bounds = conn.execute(
        "SELECT MIN(date), MAX(date) FROM activities WHERE is_indoor=0"
    ).fetchone()
    if not bounds or not bounds[0]:
        return []

    season_start = datetime.date.fromisoformat(bounds[0])
    season_end   = datetime.date.fromisoformat(bounds[1])

    # Walk week by week (Monday-based)
    # Start at the Monday of the first week with outdoor rides
    cursor = season_start - datetime.timedelta(days=season_start.weekday())
    today  = datetime.date.today()

    history = []

    while cursor <= min(season_end, today):
        week_end_s   = cursor.isoformat()
        window_start = (cursor - datetime.timedelta(days=28)).isoformat()

        # Dual-signal Z4 in trailing 28 days ending this week
        r = conn.execute("""
            SELECT
                ROUND(SUM(
                    CASE WHEN a.has_power=1
                         THEN zs.pw245_z4_s+zs.pw245_z5_s+zs.pw245_z6_s+zs.pw245_z7_s
                         ELSE zs.hr_z4_s+zs.hr_z5_s END
                )/60.0, 1)                                              AS dual_z4_min,
                ROUND(100.0*SUM(
                    CASE WHEN a.has_power=1
                         THEN zs.pw245_z4_s+zs.pw245_z5_s+zs.pw245_z6_s+zs.pw245_z7_s
                         ELSE zs.hr_z4_s+zs.hr_z5_s END
                )/NULLIF(SUM(
                    CASE WHEN a.has_power=1 THEN zs.pw245_total_s ELSE zs.hr_total_s END
                ),0), 1)                                                AS dual_z4_pct,
                ROUND(SUM(CASE WHEN a.has_power=1
                               THEN zs.pw245_z4_s+zs.pw245_z5_s+zs.pw245_z6_s+zs.pw245_z7_s
                               ELSE 0 END)/60.0, 1)                    AS pw_z4_min,
                ROUND(SUM(CASE WHEN a.has_power=0
                               THEN zs.hr_z4_s+zs.hr_z5_s ELSE 0 END)/60.0,1) AS wd_z4_min,
                COUNT(DISTINCT a.activity_id)                           AS rides,
                SUM(CASE WHEN a.has_power=1 THEN 1 ELSE 0 END)         AS power_rides
            FROM activities a
            JOIN zone_summaries zs USING(activity_id)
            WHERE a.date > ? AND a.date <= ?
        """, (window_start, week_end_s)).fetchone()

        dual_z4_min  = r[0] or 0
        dual_z4_pct  = r[1] or 0
        pw_z4_min    = r[2] or 0
        wd_z4_min    = r[3] or 0
        rides_28d    = r[4] or 0
        power_rides  = r[5] or 0

        # Latest Sat NP up to this week
        sat = conn.execute("""
            SELECT np_w_computed FROM activities
            WHERE strftime('%w',date)='6' AND has_power=1 AND is_indoor=0
              AND date <= ?
            ORDER BY date DESC LIMIT 1
        """, (week_end_s,)).fetchone()
        latest_np = sat[0] if sat else None

        # Classify (simplified — no live HRV for historical weeks)
        if rides_28d < 8:
            code  = "DETRAINING"
            color = "red"
        elif dual_z4_pct >= 12:
            code  = "BUILDING"
            color = "green"
        elif dual_z4_pct >= 7:
            code  = "PRODUCTIVE"
            color = "blue"
        elif rides_28d >= 8:
            code  = "BASE_PHASE"
            color = "orange"
        else:
            code  = "MAINTAINING"
            color = "yellow"

        history.append({
            "week":           week_end_s,
            "code":           code,
            "color":          color,
            "dual_z4_min":    round(dual_z4_min, 1),
            "dual_z4_pct":    round(dual_z4_pct, 1),
            "pw_z4_min":      round(pw_z4_min, 1),
            "wd_z4_min":      round(wd_z4_min, 1),
            "rides_28d":      rides_28d,
            "power_rides":    power_rides,
            "latest_sat_np":  latest_np,
        })

        cursor += datetime.timedelta(weeks=1)

    return history


# ── 4d. Numbers & Milestones ──────────────────────────────────────────────────

def compute_milestones(conn):
    """W/kg PDC, monthly elevation, top calorie days, aerobic efficiency top 5."""

    # W/kg best 20min (weight 65kg)
    WEIGHT_KG = 65.0
    wpkg_rows = conn.execute("""
        SELECT date, pdc_20min_w,
               ROUND(pdc_20min_w / ?, 2) wpkg
        FROM activities
        WHERE pdc_20min_w IS NOT NULL
        ORDER BY pdc_20min_w DESC
        LIMIT 5
    """, (WEIGHT_KG,)).fetchall()
    wpkg = [{"date": r[0], "pdc20_w": r[1], "wpkg": r[2]} for r in wpkg_rows]

    # Monthly elevation (outdoor only)
    elev_rows = conn.execute("""
        SELECT month,
               ROUND(SUM(elevation_gain_m), 0) elev_m,
               ROUND(SUM(distance_km), 0)      km,
               COUNT(*)                         rides
        FROM activities
        WHERE is_indoor = 0
        GROUP BY month
        ORDER BY month
    """).fetchall()
    monthly_elev = [
        {"month": r[0], "elev_m": r[1], "km": r[2], "rides": r[3]}
        for r in elev_rows
    ]

    # Top calorie days
    cal_rows = conn.execute("""
        SELECT date, calories,
               ROUND(distance_km, 0)           km,
               ROUND(elapsed_time_s / 3600.0, 1) hours,
               ROUND(elevation_gain_m, 0)       elev_m,
               activity_id
        FROM activities
        WHERE is_indoor = 0 AND calories IS NOT NULL
        ORDER BY calories DESC
        LIMIT 6
    """).fetchall()
    top_calories = [
        {"date": r[0], "calories": r[1], "km": r[2],
         "hours": r[3], "elev_m": r[4], "activity_id": r[5]}
        for r in cal_rows
    ]

    # Aerobic efficiency top 5 (W/bpm, outdoor power rides)
    eff_rows = conn.execute("""
        SELECT date,
               ROUND(aerobic_eff_np_hr, 3)     eff,
               np_w_computed                   np,
               avg_hr_bpm                      hr,
               ROUND(elevation_gain_m, 0)       elev_m,
               activity_id
        FROM activities
        WHERE aerobic_eff_np_hr IS NOT NULL
          AND is_indoor = 0 AND has_power = 1
        ORDER BY aerobic_eff_np_hr DESC
        LIMIT 5
    """).fetchall()
    top_efficiency = [
        {"date": r[0], "eff": r[1], "np_w": r[2],
         "hr_bpm": r[3], "elev_m": r[4], "activity_id": r[5]}
        for r in eff_rows
    ]

    # Cadence monthly average
    cad_rows = conn.execute("""
        SELECT month, ROUND(AVG(avg_cadence_rpm), 1) avg_cad, COUNT(*) n
        FROM activities
        WHERE is_indoor = 0 AND avg_cadence_rpm > 50
        GROUP BY month ORDER BY month
    """).fetchall()
    monthly_cadence = [{"month": r[0], "avg_rpm": r[1], "rides": r[2]}
                       for r in cad_rows]

    return {
        "weight_kg":        WEIGHT_KG,
        "wpkg_pdc20":       wpkg,
        "monthly_elevation": monthly_elev,
        "top_calorie_days": top_calories,
        "top_efficiency":   top_efficiency,
        "monthly_cadence":  monthly_cadence,
    }


# ── 4b. Best VAM laps ────────────────────────────────────────────────────────

def compute_best_vam_laps(conn, limit=10):
    """Top climbing laps by VAM (m/h), computed from elevation_gain / elapsed_time."""
    rows = conn.execute("""
        SELECT a.date,
               l.lap_index,
               ROUND(l.elevation_gain_m / (l.elapsed_time_s / 3600.0), 0) AS vam,
               ROUND(l.elevation_gain_m, 0)                                AS elev_m,
               ROUND(l.elapsed_time_s / 60.0, 1)                          AS min,
               COALESCE(l.np_w, l.avg_power_w)                            AS pw,
               l.avg_hr_bpm                                                AS hr,
               a.activity_id
        FROM laps l
        JOIN activities a USING (activity_id)
        WHERE a.is_indoor = 0
          AND l.elevation_gain_m > 80
          AND l.elapsed_time_s BETWEEN 300 AND 5400
        ORDER BY (l.elevation_gain_m / l.elapsed_time_s) DESC
        LIMIT ?
    """, (limit,)).fetchall()

    return [
        {
            "date":       r[0],
            "lap_index":  r[1],
            "vam":        int(r[2]),
            "elev_m":     r[3],
            "min":        r[4],
            "power_w":    r[5],
            "hr_bpm":     r[6],
            "activity_id": r[7],
        }
        for r in rows
    ]


# ── 4c. Longest rides ─────────────────────────────────────────────────────────

def compute_longest_rides(conn, limit=8):
    """Top outdoor rides by distance and by duration."""
    by_dist = conn.execute("""
        SELECT date,
               ROUND(distance_km, 0)            AS km,
               ROUND(elapsed_time_s / 3600.0, 1) AS hours,
               ROUND(elevation_gain_m, 0)        AS elev_m,
               np_w_computed                     AS np,
               avg_hr_bpm                        AS hr,
               activity_id
        FROM activities
        WHERE is_indoor = 0
        ORDER BY distance_km DESC
        LIMIT ?
    """, (limit,)).fetchall()

    by_time = conn.execute("""
        SELECT date,
               ROUND(elapsed_time_s / 3600.0, 2)  AS hours,
               ROUND(distance_km, 0)               AS km,
               ROUND(elevation_gain_m, 0)           AS elev_m,
               np_w_computed                       AS np,
               avg_hr_bpm                          AS hr,
               activity_id
        FROM activities
        WHERE is_indoor = 0
        ORDER BY elapsed_time_s DESC
        LIMIT ?
    """, (limit,)).fetchall()

    def fmt_dist(r):
        return {"date": r[0], "km": r[1], "hours": r[2],
                "elev_m": r[3], "np_w": r[4], "hr_bpm": r[5],
                "activity_id": r[6]}

    def fmt_time(r):
        return {"date": r[0], "hours": r[1], "km": r[2],
                "elev_m": r[3], "np_w": r[4], "hr_bpm": r[5],
                "activity_id": r[6]}

    return {
        "by_distance": [fmt_dist(r) for r in by_dist],
        "by_duration": [fmt_time(r) for r in by_time],
    }


# ── 4. Last 4 Saturdays ───────────────────────────────────────────────────────

def compute_last_4_saturdays(conn):
    rows = conn.execute("""
        SELECT date,
               np_w_computed                        AS np,
               pdc_20min_w                          AS pdc20,
               ROUND(elevation_gain_m, 0)           AS elev_m,
               ROUND(distance_km, 0)                AS km,
               ROUND(elapsed_time_s / 3600.0, 1)    AS hours
        FROM activities
        WHERE strftime('%w', date) = '6'
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
            "date":               r[0],
            "np_w":               r[1],
            "pdc20_w":            r[2],
            "elev_m":             r[3],
            "km":                 r[4],
            "hours":              r[5],
            "np_trend_vs_prev":   trend,
        })

    return results


# ── 5. Auto post-ride note ────────────────────────────────────────────────────

def generate_post_ride_note(conn):
    """
    Builds an objective one-paragraph note for the most recent activity
    and appends it to training-log/current-plan.md if not already there.
    Returns the note text (or None if no new ride).
    """
    row = conn.execute("""
        SELECT a.date, a.sub_sport, a.has_power,
               ROUND(a.distance_km, 0)                       AS km,
               ROUND(a.elevation_gain_m, 0)                  AS elev,
               a.avg_hr_bpm, a.max_hr_bpm,
               a.np_w_computed                               AS np,
               a.pdc_20min_w                                 AS pdc20,
               ROUND((zs.hr_z4_s + zs.hr_z5_s) / 60.0, 1)  AS z4_min,
               ROUND(zs.hr_z3_s / 60.0, 1)                  AS z3_min,
               a.pw_hr_drift_pct                             AS drift,
               a.aerobic_eff_np_hr                           AS eff,
               a.avg_temp_c                                  AS temp,
               a.avg_cadence_rpm                             AS cad
        FROM activities a
        JOIN zone_summaries zs USING(activity_id)
        ORDER BY a.date DESC, a.start_time_utc DESC
        LIMIT 1
    """).fetchone()

    if not row:
        return None

    (date_s, sport, has_power, km, elev, avg_hr, max_hr, np_w,
     pdc20, z4_min, z3_min, drift, eff, temp, cad) = row

    # Check if this date is already in the log
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH) as f:
            existing = f.read()
        # Look for this exact date in any log entry heading
        marker = f"### {date_s}"
        if marker in existing:
            return None  # already logged

    # Build the note
    parts = []

    # Header
    temp_s = f" · {temp}°C" if temp else ""
    parts.append(f"### {date_s} (auto-logged by update_dashboard.py)")
    parts.append(f"**{km:.0f}km · {elev:.0f}m{temp_s}**")
    parts.append("")

    # Power summary
    if has_power and np_w:
        np_pct = round(np_w / 235 * 100)
        np_zone = ("Z2" if np_w < 184 else "Z3" if np_w < 221 else
                   "Z4" if np_w < 258 else "Z5")
        parts.append(f"- NP: **{np_w}W** ({np_pct}% FTP, {np_zone})"
                     + (f" · PDC 20min: {pdc20}W" if pdc20 else ""))
    else:
        parts.append(f"- No power data (weekday bike)")

    # HR summary
    parts.append(f"- avg HR: {avg_hr}bpm · max HR: {max_hr}bpm")

    # Zone time
    parts.append(f"- Z3: {z3_min:.0f}min · Z4+Z5: **{z4_min:.0f}min**")

    # Aerobic coupling
    if drift is not None:
        coupling = ("well-coupled ✓" if abs(drift) < 5 else
                    "moderate" if abs(drift) < 15 else "decoupled ⚠")
        parts.append(f"- Aerobic coupling: {drift:+.1f}% ({coupling})")

    # Efficiency
    if eff:
        parts.append(f"- Aerobic efficiency: {eff:.3f} W/bpm")

    # Cadence
    if cad:
        parts.append(f"- Avg cadence: {cad}rpm")

    # Auto-assessment
    parts.append("")
    assessment_lines = []

    # Z4 assessment
    if z4_min >= 20:
        assessment_lines.append(f"Strong Z4 session ({z4_min:.0f}min) — plan target hit.")
    elif z4_min >= 10:
        assessment_lines.append(f"Solid Z4 contribution ({z4_min:.0f}min).")
    elif z4_min >= 3:
        assessment_lines.append(f"Light Z4 ({z4_min:.0f}min) — Z3 dominant.")
    else:
        assessment_lines.append(f"Z2/Z3 base ride (Z4={z4_min:.0f}min).")

    # NP vs target for power rides
    if has_power and np_w:
        ws_iso = get_week_start(date.fromisoformat(date_s)).isoformat()
        plan   = PLAN_TARGETS.get(ws_iso, {})
        import calendar
        weekday = date.fromisoformat(date_s).weekday()
        if weekday == 5:  # Saturday
            np_lo = plan.get("sat_np_min")
            np_hi = plan.get("sat_np_max")
            if np_lo and np_hi:
                if np_w >= np_lo:
                    assessment_lines.append(f"Sat NP {np_w}W ✅ (target {np_lo}–{np_hi}W).")
                else:
                    assessment_lines.append(
                        f"Sat NP {np_w}W below target ({np_lo}–{np_hi}W) — "
                        f"check climbing meters and pacing.")

    # Coupling note
    if drift is not None and abs(drift) >= 15:
        assessment_lines.append(
            "High HR drift — heat, fatigue, or effort too hard. "
            "Monitor recovery before next quality session.")
    elif drift is not None and abs(drift) < 5 and has_power:
        assessment_lines.append("Well-coupled — aerobic system solid.")

    parts.append("**Auto-assessment:** " + " ".join(assessment_lines))
    parts.append("**Subjective:** _(add: felt strong/ok/tired · RPE · any notes)_")
    parts.append("")

    return "\n".join(parts)


def append_to_log(note_text):
    """Append note_text to training-log/current-plan.md under the Session Log section."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    if not os.path.exists(LOG_PATH):
        print(f"  ⚠  {LOG_PATH} not found — skipping log append")
        return

    with open(LOG_PATH) as f:
        content = f.read()

    # Find the session log section and append after the last entry
    section_marker = "## Session Log"
    if section_marker in content:
        # Append before the end of the file
        if not content.endswith("\n"):
            content += "\n"
        content += "\n" + note_text
    else:
        # No session log section — append at end with a header
        content += f"\n\n## Session Log\n\n{note_text}"

    with open(LOG_PATH, "w") as f:
        f.write(content)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        print("Run: python3 scripts/fit_to_db.py")
        raise SystemExit(1)

    if not os.path.exists(DASH_PATH):
        print(f"ERROR: dashboard.json not found at {DASH_PATH}")
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)

    # Load dashboard.json early — needed for current_status HRV/CTL inputs
    with open(DASH_PATH) as f:
        d = json.load(f)

    week_summary    = compute_week_summary(conn)
    progression     = compute_progression_flag(week_summary)
    next_session    = compute_next_session_suggestion(conn, week_summary)
    last_4_sats     = compute_last_4_saturdays(conn)
    best_vam_laps   = compute_best_vam_laps(conn)
    longest_rides   = compute_longest_rides(conn)
    milestones      = compute_milestones(conn)

    # WattsUpAI custom status (current)
    s = d.get("current_status", {})
    wattsupai_status = compute_wattsupai_status(
        conn,
        hrv_weekly_avg=s.get("hrv_weekly_avg_ms"),
        hrv_last_night=s.get("hrv_last_night_ms"),
        ctl=s.get("ctl", 800),
        atl=s.get("atl", 800),
        tsb=s.get("tsb", 0),
    )

    # Historical weekly status timeline (full season)
    wattsupai_status_history = compute_status_history(conn)

    # Embed progression flag and next session into week_summary
    week_summary["progression_flag"] = progression
    week_summary["next_session"]     = next_session

    # Auto post-ride note
    note = None
    if not NO_LOG:
        note = generate_post_ride_note(conn)
        if note:
            append_to_log(note)

    conn.close()

    # Patch dashboard.json
    d["week_summary"]              = week_summary
    d["last_4_saturdays"]          = last_4_sats
    d["best_vam_laps"]             = best_vam_laps
    d["longest_rides"]             = longest_rides
    d["milestones"]                = milestones
    d["wattsupai_status"]          = wattsupai_status
    d["wattsupai_status_history"]  = wattsupai_status_history

    with open(DASH_PATH, "w") as f:
        json.dump(d, f, indent=2)

    # ── Print summary ─────────────────────────────────────────────────────────
    print("✓ dashboard.json updated")
    print(f"  Week {week_summary['week_start']}: "
          f"{week_summary['rides_count']} ride(s) · "
          f"Z4={week_summary['z4_min_total']}min ({week_summary['z4_status']})")
    ws_status = wattsupai_status
    print(f"  WattsUpAI: {ws_status['code']} — {ws_status['label']}")
    print(f"    Z4 28d: {ws_status['dual_z4_min_28d']}min ({ws_status['dual_z4_pct_28d']}%) · "
          f"Sat NP: {ws_status['latest_sat_np']}W ({ws_status['np_trend']})")

    p = progression
    flag_icon = {"increase": "↑", "stay": "→", "reduce": "↓", "recovery": "🔄"}.get(p["flag"], "?")
    print(f"  Progression: {flag_icon} {p['flag'].upper()} — {p['reason']}")

    ns = next_session
    if "message" in ns:
        print(f"  Next session: {ns['message']}")
    else:
        print(f"  Next session ({ns['day']} {ns['type']}): {ns['desc']}")
        if ns.get("terrain_hint"):
            print(f"    Terrain: {ns['terrain_hint'][:120]}{'...' if len(ns['terrain_hint']) > 120 else ''}")

    if last_4_sats:
        sat_str = "  Last 4 Sat NP: " + " → ".join(
            f"{s['np_w'] or '-'}W" for s in reversed(last_4_sats))
        print(sat_str)

    if note:
        print(f"  ✓ Post-ride note appended to training-log/current-plan.md")
    elif not NO_LOG:
        print(f"  (most recent ride already logged — no new entry added)")


if __name__ == "__main__":
    main()
