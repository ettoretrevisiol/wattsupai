#!/usr/bin/env python3
"""
fit_to_db.py — ETL pipeline: raw FIT files → SQLite database

Reads every .fit file in data/fit-raw/ and writes to data/training.db

Tables:
  activities      — one row per activity (session-level summary)
  laps            — one row per lap (FIT lap messages)
  records         — one row per second (FIT record messages) — optional, large
  zone_summaries  — pre-computed HR + power time-in-zone per activity (from records)

Usage:
  python3 fit_to_db.py                   # populate/update all activities
  python3 fit_to_db.py --records         # also write raw records table (large ~100MB)
  python3 fit_to_db.py --activity ID     # reprocess single activity

HR zones (Ettore):  Z1 100–129 | Z2 130–154 | Z3 155–165 | Z4 166–179 | Z5 180+
Power zones FTP=256W: P1<141 | P2 141–192 | P3 193–230 | P4 231–268 | P5 269–307 | P6 308–384 | P7 384+
Power zones FTP=235W: same bands recalculated
"""

import fitparse, sqlite3, glob, os, sys, argparse, time
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
FIT_DIR = "/Users/ettoretr/Documents/wattsupai/data/fit-raw"
DB_PATH = "/Users/ettoretr/Documents/wattsupai/data/training.db"
FTP_256  = 256   # Garmin manual entry
FTP_235  = 235   # evidence-based estimate from Sep 19 climb
FTP_245  = 245   # current working FTP (manual entry Sep 24 2026)

# ── Zone helpers ──────────────────────────────────────────────────────────────
def hr_zone(bpm):
    if bpm is None or bpm < 60: return None
    if bpm < 130: return 1
    if bpm < 155: return 2
    if bpm < 166: return 3
    if bpm < 180: return 4
    return 5

def power_zone(w, ftp):
    if w is None or w < 0: return None
    cutoffs = [0.55*ftp, 0.75*ftp, 0.90*ftp, 1.05*ftp, 1.20*ftp, 1.50*ftp]
    for i, c in enumerate(cutoffs):
        if w < c: return i + 1
    return 7

# ── Normalized Power ──────────────────────────────────────────────────────────
def calc_np(power_1s):
    """Standard NP: 30s rolling avg → 4th power mean → 4th root."""
    p = [x if (x is not None and x >= 0) else 0 for x in power_1s]
    if len(p) < 30:
        return None
    rolling4 = []
    window_sum = sum(p[:30])
    rolling4.append((window_sum / 30) ** 4)
    for i in range(30, len(p)):
        window_sum += p[i] - p[i - 30]
        rolling4.append((window_sum / 30) ** 4)
    return round((sum(rolling4) / len(rolling4)) ** 0.25)

# ── Best Mean Maximal Power (PDC) ─────────────────────────────────────────────
def best_mmp(power_1s, duration_s):
    p = [x if (x is not None and x >= 0) else 0 for x in power_1s]
    n = len(p)
    if n < duration_s:
        return None
    window = sum(p[:duration_s])
    best = window
    for i in range(duration_s, n):
        window += p[i] - p[i - duration_s]
        if window > best:
            best = window
    return round(best / duration_s)

# ── HR/Power drift (aerobic decoupling) ───────────────────────────────────────
def calc_pw_hr_drift(hr_1s, pw_1s):
    """
    Aerobic decoupling: compare (power/HR) in first half vs second half.
    Negative = HR lower in 2nd half (well coupled / improving aerobic).
    Positive = HR rising vs power (cardiac drift / fatigue).
    Returns pct change.
    """
    pairs = [(h, p) for h, p in zip(hr_1s, pw_1s)
             if h and p and h > 100 and p > 50]
    if len(pairs) < 120:
        return None
    mid = len(pairs) // 2
    r1 = sum(p / h for h, p in pairs[:mid]) / mid
    r2 = sum(p / h for h, p in pairs[mid:]) / (len(pairs) - mid)
    if r1 == 0:
        return None
    return round(100 * (r2 - r1) / r1, 2)

# ── Database schema ───────────────────────────────────────────────────────────
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS activities (
    -- Identity
    activity_id         TEXT PRIMARY KEY,
    date                TEXT NOT NULL,          -- YYYY-MM-DD
    start_time_utc      TEXT,
    month               TEXT,                   -- YYYY-MM
    year                INTEGER,

    -- Sport
    sport               TEXT,
    sub_sport           TEXT,
    is_indoor           INTEGER,                -- 0/1

    -- Totals
    distance_km         REAL,
    elevation_gain_m    REAL,
    elevation_loss_m    REAL,
    timer_time_s        REAL,
    elapsed_time_s      REAL,
    calories            INTEGER,

    -- HR summary (from session message)
    avg_hr_bpm          INTEGER,
    max_hr_bpm          INTEGER,

    -- Power summary (from session message, NULL if no power meter)
    has_power           INTEGER,                -- 0/1
    avg_power_w         INTEGER,
    max_power_w         INTEGER,
    np_w_session        INTEGER,               -- NP from session message (Garmin)
    np_w_computed       INTEGER,               -- NP computed from raw records
    threshold_power_w   INTEGER,               -- FTP stored in device at time of ride
    training_stress_score REAL,
    intensity_factor    REAL,

    -- Temperature
    avg_temp_c          REAL,
    max_temp_c          REAL,

    -- Training effect (Garmin labels)
    te_aerobic          REAL,
    te_anaerobic        REAL,

    -- Cadence
    avg_cadence_rpm     INTEGER,
    max_cadence_rpm     INTEGER,

    -- Computed: PDC (best mean maximal power, from raw records)
    pdc_5s_w            INTEGER,
    pdc_30s_w           INTEGER,
    pdc_1min_w          INTEGER,
    pdc_5min_w          INTEGER,
    pdc_10min_w         INTEGER,
    pdc_20min_w         INTEGER,
    pdc_60min_w         INTEGER,

    -- Computed: aerobic decoupling
    pw_hr_drift_pct     REAL,

    -- Computed: aerobic efficiency
    aerobic_eff_np_hr   REAL,                  -- NP / avg_HR

    -- Record count
    n_records           INTEGER,

    -- ETL metadata
    fit_file_size_bytes INTEGER,
    etl_timestamp       TEXT
);

CREATE TABLE IF NOT EXISTS laps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id         TEXT NOT NULL REFERENCES activities(activity_id),
    lap_index           INTEGER,
    start_time_utc      TEXT,
    elapsed_time_s      REAL,
    timer_time_s        REAL,
    distance_km         REAL,
    elevation_gain_m    REAL,
    elevation_loss_m    REAL,
    avg_hr_bpm          INTEGER,
    max_hr_bpm          INTEGER,
    avg_power_w         INTEGER,
    max_power_w         INTEGER,
    np_w                INTEGER,               -- from FIT lap message
    avg_cadence_rpm     INTEGER,
    avg_speed_ms        REAL,
    avg_temp_c          REAL,
    avg_vam             REAL,                  -- vertical ascent m/h
    lap_trigger         TEXT,                  -- 'manual', 'distance', 'time', etc.
    -- HR zones (seconds in zone for this lap, from records)
    hr_z1_s             REAL,
    hr_z2_s             REAL,
    hr_z3_s             REAL,
    hr_z4_s             REAL,
    hr_z5_s             REAL,
    -- Power zones (seconds, FTP=256)
    pw_z1_s             REAL,
    pw_z2_s             REAL,
    pw_z3_s             REAL,
    pw_z4_s             REAL,
    pw_z5_s             REAL,
    pw_z6_s             REAL,
    pw_z7_s             REAL
);

CREATE TABLE IF NOT EXISTS zone_summaries (
    activity_id         TEXT PRIMARY KEY REFERENCES activities(activity_id),
    -- HR zones (seconds), FTP-independent
    hr_z1_s             REAL,
    hr_z2_s             REAL,
    hr_z3_s             REAL,
    hr_z4_s             REAL,
    hr_z5_s             REAL,
    hr_total_s          REAL,
    -- Power zones (seconds) at FTP=256W
    pw256_z1_s          REAL,
    pw256_z2_s          REAL,
    pw256_z3_s          REAL,
    pw256_z4_s          REAL,
    pw256_z5_s          REAL,
    pw256_z6_s          REAL,
    pw256_z7_s          REAL,
    pw256_total_s       REAL,
    -- Power zones (seconds) at FTP=235W
    pw235_z1_s          REAL,
    pw235_z2_s          REAL,
    pw235_z3_s          REAL,
    pw235_z4_s          REAL,
    pw235_z5_s          REAL,
    pw235_z6_s          REAL,
    pw235_z7_s          REAL,
    pw235_total_s       REAL,
    -- Power zones (seconds) at FTP=245W (current working FTP Sep 2026)
    pw245_z1_s          REAL,
    pw245_z2_s          REAL,
    pw245_z3_s          REAL,
    pw245_z4_s          REAL,
    pw245_z5_s          REAL,
    pw245_z6_s          REAL,
    pw245_z7_s          REAL,
    pw245_total_s       REAL
);

CREATE TABLE IF NOT EXISTS records (
    -- Only written when --records flag is set
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id         TEXT NOT NULL REFERENCES activities(activity_id),
    timestamp_utc       TEXT,
    seconds_from_start  REAL,
    heart_rate          INTEGER,
    power_w             INTEGER,
    cadence_rpm         INTEGER,
    speed_ms            REAL,
    altitude_m          REAL,
    temperature_c       INTEGER,
    distance_m          REAL,
    lat                 REAL,
    lon                 REAL,
    -- Derived
    hr_zone             INTEGER,
    power_zone_256      INTEGER,
    power_zone_235      INTEGER
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_activities_date   ON activities(date);
CREATE INDEX IF NOT EXISTS idx_activities_month  ON activities(month);
CREATE INDEX IF NOT EXISTS idx_laps_activity     ON laps(activity_id);
CREATE INDEX IF NOT EXISTS idx_laps_avg_hr       ON laps(avg_hr_bpm);
CREATE INDEX IF NOT EXISTS idx_laps_np           ON laps(np_w);
CREATE INDEX IF NOT EXISTS idx_records_activity  ON records(activity_id);
CREATE INDEX IF NOT EXISTS idx_zone_summaries    ON zone_summaries(activity_id);
"""

# ── Core ETL: parse one FIT file ──────────────────────────────────────────────
def parse_fit(fpath, write_records=False):
    """
    Parse a single FIT file.
    Returns (activity_dict, laps_list, zone_summary_dict, records_list).
    """
    aid = os.path.basename(fpath).replace(".fit", "")
    file_size = os.path.getsize(fpath)

    try:
        fit = fitparse.FitFile(fpath)
    except Exception as e:
        print(f"  ERROR reading {aid}: {e}")
        return None

    # ── Session message ────────────────────────────────────────────────────────
    sess = {}
    for msg in fit.get_messages("session"):
        for f in msg:
            sess[f.name] = f.value
        break  # only one session per file

    start_time = sess.get("start_time")
    if start_time is None:
        return None
    date_str  = start_time.strftime("%Y-%m-%d")
    month_str = start_time.strftime("%Y-%m")

    sport     = str(sess.get("sport", "")).lower()
    sub_sport = str(sess.get("sub_sport", "")).lower()
    is_indoor = int("indoor" in sub_sport or "virtual" in sub_sport)

    activity = {
        "activity_id":        aid,
        "date":               date_str,
        "start_time_utc":     start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "month":              month_str,
        "year":               int(date_str[:4]),
        "sport":              sport,
        "sub_sport":          sub_sport,
        "is_indoor":          is_indoor,
        "distance_km":        round((sess.get("total_distance") or 0) / 1000, 3),
        "elevation_gain_m":   sess.get("total_ascent") or 0,
        "elevation_loss_m":   sess.get("total_descent") or 0,
        "timer_time_s":       sess.get("total_timer_time"),
        "elapsed_time_s":     sess.get("total_elapsed_time"),
        "calories":           sess.get("total_calories"),
        "avg_hr_bpm":         sess.get("avg_heart_rate"),
        "max_hr_bpm":         sess.get("max_heart_rate"),
        "avg_power_w":        sess.get("avg_power"),
        "max_power_w":        sess.get("max_power"),
        "np_w_session":       sess.get("normalized_power"),
        "threshold_power_w":  sess.get("threshold_power"),
        "training_stress_score": sess.get("training_stress_score"),
        "intensity_factor":   sess.get("intensity_factor"),
        "avg_temp_c":         sess.get("avg_temperature"),
        "max_temp_c":         sess.get("max_temperature"),
        "te_aerobic":         sess.get("total_training_effect"),
        "te_anaerobic":       sess.get("total_anaerobic_training_effect"),
        "avg_cadence_rpm":    sess.get("avg_cadence"),
        "max_cadence_rpm":    sess.get("max_cadence"),
        "fit_file_size_bytes": file_size,
        "etl_timestamp":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # ── Records (per-second samples) ──────────────────────────────────────────
    hr_1s    = []
    pw_1s    = []
    ts_list  = []
    all_rec_rows = []

    t0 = None
    for msg in fit.get_messages("record"):
        d = {f.name: f.value for f in msg}
        ts = d.get("timestamp")
        hr = d.get("heart_rate")
        pw = d.get("power")

        if ts and t0 is None:
            t0 = ts

        secs = (ts - t0).total_seconds() if (ts and t0) else None

        hr_1s.append(hr)
        pw_1s.append(pw)
        ts_list.append(ts)

        if write_records:
            lat = d.get("position_lat")
            lon = d.get("position_long")
            # Convert semicircles to degrees
            if lat: lat = round(lat * 180 / 2**31, 6)
            if lon: lon = round(lon * 180 / 2**31, 6)
            all_rec_rows.append({
                "activity_id":      aid,
                "timestamp_utc":    ts.strftime("%Y-%m-%dT%H:%M:%S") if ts else None,
                "seconds_from_start": secs,
                "heart_rate":       hr,
                "power_w":          pw,
                "cadence_rpm":      d.get("cadence"),
                "speed_ms":         d.get("enhanced_speed") or d.get("speed"),
                "altitude_m":       d.get("enhanced_altitude") or d.get("altitude"),
                "temperature_c":    d.get("temperature"),
                "distance_m":       d.get("distance"),
                "lat":              lat,
                "lon":              lon,
                "hr_zone":          hr_zone(hr),
                "power_zone_256":   power_zone(pw, FTP_256),
                "power_zone_235":   power_zone(pw, FTP_235),
            })

    n_records = len(hr_1s)
    has_power = sum(1 for p in pw_1s if p is not None and p > 5) > 60

    # Compute sample intervals from timestamps
    intervals = []
    for i in range(len(ts_list)):
        if i == 0:
            intervals.append(1.0)
        elif ts_list[i] and ts_list[i-1]:
            try:
                delta = (ts_list[i] - ts_list[i-1]).total_seconds()
                intervals.append(max(0.5, min(delta, 10.0)))
            except:
                intervals.append(1.0)
        else:
            intervals.append(1.0)

    # ── Zone summaries from records ────────────────────────────────────────────
    hr_z  = {1:0.0, 2:0.0, 3:0.0, 4:0.0, 5:0.0}
    pw256 = {1:0.0, 2:0.0, 3:0.0, 4:0.0, 5:0.0, 6:0.0, 7:0.0}
    pw235 = {1:0.0, 2:0.0, 3:0.0, 4:0.0, 5:0.0, 6:0.0, 7:0.0}
    pw245 = {1:0.0, 2:0.0, 3:0.0, 4:0.0, 5:0.0, 6:0.0, 7:0.0}
    hr_total_s   = 0.0
    pw256_total  = 0.0
    pw235_total  = 0.0
    pw245_total  = 0.0

    for hr, pw, dt in zip(hr_1s, pw_1s, intervals):
        z = hr_zone(hr)
        if z:
            hr_z[z]    += dt
            hr_total_s += dt
        if has_power and pw is not None and pw >= 0:
            z256 = power_zone(pw, FTP_256)
            z235 = power_zone(pw, FTP_235)
            z245 = power_zone(pw, FTP_245)
            if z256:
                pw256[z256]  += dt
                pw256_total  += dt
            if z235:
                pw235[z235]  += dt
                pw235_total  += dt
            if z245:
                pw245[z245]  += dt
                pw245_total  += dt

    zone_summary = {
        "activity_id":   aid,
        "hr_z1_s": hr_z[1], "hr_z2_s": hr_z[2], "hr_z3_s": hr_z[3],
        "hr_z4_s": hr_z[4], "hr_z5_s": hr_z[5], "hr_total_s": hr_total_s,
        "pw256_z1_s": pw256[1], "pw256_z2_s": pw256[2], "pw256_z3_s": pw256[3],
        "pw256_z4_s": pw256[4], "pw256_z5_s": pw256[5], "pw256_z6_s": pw256[6],
        "pw256_z7_s": pw256[7], "pw256_total_s": pw256_total,
        "pw235_z1_s": pw235[1], "pw235_z2_s": pw235[2], "pw235_z3_s": pw235[3],
        "pw235_z4_s": pw235[4], "pw235_z5_s": pw235[5], "pw235_z6_s": pw235[6],
        "pw235_z7_s": pw235[7], "pw235_total_s": pw235_total,
        "pw245_z1_s": pw245[1], "pw245_z2_s": pw245[2], "pw245_z3_s": pw245[3],
        "pw245_z4_s": pw245[4], "pw245_z5_s": pw245[5], "pw245_z6_s": pw245[6],
        "pw245_z7_s": pw245[7], "pw245_total_s": pw245_total,
    }

    # ── Computed session metrics ───────────────────────────────────────────────
    activity["has_power"]      = int(has_power)
    activity["n_records"]      = n_records
    activity["np_w_computed"]  = calc_np(pw_1s) if has_power else None

    # PDC
    if has_power:
        activity["pdc_5s_w"]   = best_mmp(pw_1s, 5)
        activity["pdc_30s_w"]  = best_mmp(pw_1s, 30)
        activity["pdc_1min_w"] = best_mmp(pw_1s, 60)
        activity["pdc_5min_w"] = best_mmp(pw_1s, 300)
        activity["pdc_10min_w"]= best_mmp(pw_1s, 600)
        activity["pdc_20min_w"]= best_mmp(pw_1s, 1200)
        activity["pdc_60min_w"]= best_mmp(pw_1s, 3600)
    else:
        for k in ["pdc_5s_w","pdc_30s_w","pdc_1min_w","pdc_5min_w",
                  "pdc_10min_w","pdc_20min_w","pdc_60min_w"]:
            activity[k] = None

    # HR/power drift (only for rides > 60 min with power)
    if has_power and (activity.get("timer_time_s") or 0) > 3600:
        activity["pw_hr_drift_pct"] = calc_pw_hr_drift(hr_1s, pw_1s)
    else:
        activity["pw_hr_drift_pct"] = None

    # Aerobic efficiency
    np_comp = activity["np_w_computed"]
    avg_hr  = activity["avg_hr_bpm"]
    if np_comp and avg_hr and avg_hr > 100:
        activity["aerobic_eff_np_hr"] = round(np_comp / avg_hr, 4)
    else:
        activity["aerobic_eff_np_hr"] = None

    # ── Laps ──────────────────────────────────────────────────────────────────
    laps = []
    lap_idx = 0

    # Build a ts→(hr,pw) map for zone-per-lap assignment
    ts_to_hrpw = {}
    if ts_list:
        for ts, hr, pw in zip(ts_list, hr_1s, pw_1s):
            if ts:
                ts_to_hrpw[ts] = (hr, pw)

    for msg in fit.get_messages("lap"):
        d = {f.name: f.value for f in msg}
        lap_start = d.get("start_time")
        lap_end   = d.get("timestamp")

        lap_row = {
            "activity_id":    aid,
            "lap_index":      lap_idx,
            "start_time_utc": lap_start.strftime("%Y-%m-%dT%H:%M:%S") if lap_start else None,
            "elapsed_time_s": d.get("total_elapsed_time"),
            "timer_time_s":   d.get("total_timer_time"),
            "distance_km":    round((d.get("total_distance") or 0) / 1000, 3),
            "elevation_gain_m": d.get("total_ascent") or 0,
            "elevation_loss_m": d.get("total_descent") or 0,
            "avg_hr_bpm":     d.get("avg_heart_rate"),
            "max_hr_bpm":     d.get("max_heart_rate"),
            "avg_power_w":    d.get("avg_power"),
            "max_power_w":    d.get("max_power"),
            "np_w":           d.get("normalized_power"),
            "avg_cadence_rpm":d.get("avg_cadence"),
            "avg_speed_ms":   d.get("avg_speed"),
            "avg_temp_c":     d.get("avg_temperature"),
            "avg_vam":        d.get("avg_vam"),
            "lap_trigger":    str(d.get("lap_trigger", "")),
        }

        # Per-lap zone seconds from records
        lhr  = {1:0.0, 2:0.0, 3:0.0, 4:0.0, 5:0.0}
        lpw  = {1:0.0, 2:0.0, 3:0.0, 4:0.0, 5:0.0, 6:0.0, 7:0.0}

        if lap_start and lap_end and ts_list:
            for ts, hr, pw, dt in zip(ts_list, hr_1s, pw_1s, intervals):
                if ts and lap_start <= ts <= lap_end:
                    z = hr_zone(hr)
                    if z: lhr[z] += dt
                    if has_power and pw is not None and pw >= 0:
                        z256 = power_zone(pw, FTP_256)
                        if z256: lpw[z256] += dt

        lap_row.update({
            "hr_z1_s": lhr[1], "hr_z2_s": lhr[2], "hr_z3_s": lhr[3],
            "hr_z4_s": lhr[4], "hr_z5_s": lhr[5],
            "pw_z1_s": lpw[1], "pw_z2_s": lpw[2], "pw_z3_s": lpw[3],
            "pw_z4_s": lpw[4], "pw_z5_s": lpw[5], "pw_z6_s": lpw[6],
            "pw_z7_s": lpw[7],
        })

        laps.append(lap_row)
        lap_idx += 1

    return activity, laps, zone_summary, (all_rec_rows if write_records else [])


# ── DB writer ─────────────────────────────────────────────────────────────────
def upsert_activity(conn, activity, laps, zone_summary, records):
    aid = activity["activity_id"]

    # Activities
    cols = list(activity.keys())
    placeholders = ",".join("?" * len(cols))
    vals = [activity[c] for c in cols]
    conn.execute(
        f"INSERT OR REPLACE INTO activities ({','.join(cols)}) VALUES ({placeholders})",
        vals
    )

    # Remove existing laps/zone_summaries for this activity (re-insert)
    conn.execute("DELETE FROM laps WHERE activity_id=?", (aid,))
    conn.execute("DELETE FROM zone_summaries WHERE activity_id=?", (aid,))

    # Laps
    if laps:
        lap_cols = list(laps[0].keys())
        lap_ph   = ",".join("?" * len(lap_cols))
        conn.executemany(
            f"INSERT INTO laps ({','.join(lap_cols)}) VALUES ({lap_ph})",
            [[l[c] for c in lap_cols] for l in laps]
        )

    # Zone summary
    zs_cols = list(zone_summary.keys())
    zs_ph   = ",".join("?" * len(zs_cols))
    conn.execute(
        f"INSERT OR REPLACE INTO zone_summaries ({','.join(zs_cols)}) VALUES ({zs_ph})",
        [zone_summary[c] for c in zs_cols]
    )

    # Records (optional)
    if records:
        conn.execute("DELETE FROM records WHERE activity_id=?", (aid,))
        rec_cols = list(records[0].keys())
        rec_ph   = ",".join("?" * len(rec_cols))
        conn.executemany(
            f"INSERT INTO records ({','.join(rec_cols)}) VALUES ({rec_ph})",
            [[r[c] for c in rec_cols] for r in records]
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Build training SQLite DB from raw FIT files")
    parser.add_argument("--records", action="store_true",
                        help="Also write raw records table (adds ~100MB)")
    parser.add_argument("--activity", type=str, default=None,
                        help="Reprocess single activity ID only")
    parser.add_argument("--force", action="store_true",
                        help="Re-process all files even if already in DB")
    args = parser.parse_args()

    # Init DB
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    # Get already-processed IDs
    existing = set(row[0] for row in conn.execute("SELECT activity_id FROM activities"))
    print(f"DB: {len(existing)} activities already loaded")

    # Find FIT files
    if args.activity:
        files = [f"{FIT_DIR}/{args.activity}.fit"]
    else:
        files = sorted(glob.glob(f"{FIT_DIR}/*.fit"))

    to_process = []
    for fpath in files:
        aid = os.path.basename(fpath).replace(".fit", "")
        if args.force or aid not in existing:
            to_process.append(fpath)

    print(f"Files to process: {len(to_process)} / {len(files)}")
    if not to_process:
        print("Nothing to do. Use --force to reprocess all.")
        conn.close()
        return

    t_start = time.time()
    ok = 0
    errors = 0

    for i, fpath in enumerate(to_process, 1):
        aid = os.path.basename(fpath).replace(".fit", "")
        result = parse_fit(fpath, write_records=args.records)
        if result is None:
            errors += 1
            continue
        activity, laps, zone_summary, records = result
        try:
            upsert_activity(conn, activity, laps, zone_summary, records)
            ok += 1
        except Exception as e:
            print(f"  DB ERROR {aid}: {e}")
            errors += 1
            conn.rollback()
            continue

        # Progress
        if i % 20 == 0 or i == len(to_process):
            elapsed = time.time() - t_start
            rate = i / elapsed
            eta  = (len(to_process) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{len(to_process)}]  {ok} ok  {errors} errors  "
                  f"{elapsed:.0f}s elapsed  ETA {eta:.0f}s")
            conn.commit()

    conn.commit()

    # Final stats
    elapsed = time.time() - t_start
    total_acts = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    total_laps = conn.execute("SELECT COUNT(*) FROM laps").fetchone()[0]
    total_recs = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    db_size_mb = os.path.getsize(DB_PATH) / 1024 / 1024

    print(f"\n{'='*60}")
    print(f"ETL complete in {elapsed:.1f}s")
    print(f"  Activities:  {total_acts}")
    print(f"  Laps:        {total_laps}")
    print(f"  Records:     {total_recs}")
    print(f"  DB size:     {db_size_mb:.1f} MB")
    print(f"  DB path:     {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
