#!/usr/bin/env python3
"""
query_db.py — Full season analysis from local SQLite training database.

All numbers computed from raw FIT data (via fit_to_db.py ETL).
No Garmin API calls. No pre-processed summaries.

Run:
  python3 query_db.py               # full report to stdout
  python3 query_db.py > report.txt  # save to file
"""

import sqlite3, os
from datetime import datetime

DB_PATH = "/Users/ettoretr/Documents/wattsupai/data/training.db"
SEP     = "═" * 74

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row  # access columns by name

def q(sql, params=()):
    return conn.execute(sql, params).fetchall()

def q1(sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return r[0] if r else None

def hm(s):
    if s is None: return "  -"
    s = int(s)
    return f"{s//3600}h{(s%3600)//60:02d}m"

def pct(n, d, dec=1):
    if not d or d == 0: return "  N/A"
    return f"{100*n/d:.{dec}f}%"

def bar(val, scale=3, char="▓"):
    if val is None: return ""
    return char * max(0, int(val / scale))


# ══════════════════════════════════════════════════════════════════════════════
print(SEP)
print("SEASON ANALYSIS — computed from raw FIT files via training.db")
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(SEP)

# ── Overview ──────────────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("1. SEASON OVERVIEW")
print(f"{'─'*74}")

row = q("""
    SELECT
        COUNT(*)                            AS total_rides,
        SUM(CASE WHEN is_indoor=1 THEN 1 ELSE 0 END) AS indoor,
        SUM(CASE WHEN is_indoor=0 THEN 1 ELSE 0 END) AS outdoor,
        SUM(CASE WHEN has_power=1 AND is_indoor=0 THEN 1 ELSE 0 END) AS out_power,
        SUM(CASE WHEN has_power=0 AND is_indoor=0 THEN 1 ELSE 0 END) AS out_nopow,
        MIN(date) AS first, MAX(date) AS last,
        ROUND(SUM(distance_km),0)           AS total_km,
        ROUND(SUM(elevation_gain_m),0)      AS total_m,
        SUM(calories)                       AS total_cal
    FROM activities
""")[0]

print(f"  Date range:              {row['first']} → {row['last']}")
print(f"  Total rides:             {row['total_rides']}")
print(f"    Indoor (trainer):      {row['indoor']}")
print(f"    Outdoor total:         {row['outdoor']}")
print(f"      with power meter:    {row['out_power']}")
print(f"      without power:       {row['out_nopow']}")
print(f"  Total distance:          {row['total_km']:.0f} km")
print(f"  Total elevation:         {row['total_m']:.0f} m")
print(f"  Total calories:          {row['total_cal'] or 0:.0f} kcal")

hr_time = q1("SELECT SUM(hr_total_s) FROM zone_summaries")
pw_time = q1("SELECT SUM(pw256_total_s) FROM zone_summaries")
print(f"  HR-tracked time:         {hm(hr_time)}")
print(f"  Power-tracked time:      {hm(pw_time)}")


# ── HR Zone Distribution — all rides ─────────────────────────────────────────
print(f"\n{'─'*74}")
print("2. HR ZONE DISTRIBUTION — per-second, computed from raw records")
print(f"   Zones: Z1 100-129 | Z2 130-154 | Z3 155-165 | Z4 166-179 | Z5 180+")
print(f"{'─'*74}")

def hr_zone_block(label, where="1=1", params=()):
    r = q(f"""
        SELECT
            SUM(zs.hr_z1_s) z1, SUM(zs.hr_z2_s) z2,
            SUM(zs.hr_z3_s) z3, SUM(zs.hr_z4_s) z4,
            SUM(zs.hr_z5_s) z5, SUM(zs.hr_total_s) tot,
            COUNT(*) n
        FROM zone_summaries zs
        JOIN activities a USING (activity_id)
        WHERE {where}
    """, params)[0]
    if not r['tot'] or r['tot'] == 0: return
    z1,z2,z3,z4,z5,tot,n = r['z1'],r['z2'],r['z3'],r['z4'],r['z5'],r['tot'],r['n']
    print(f"\n  {label} ({n} rides, {hm(tot)} HR time):")
    print(f"    Z1:  {hm(z1):>9}  {pct(z1,tot):>7}")
    print(f"    Z2:  {hm(z2):>9}  {pct(z2,tot):>7}")
    print(f"    Z3:  {hm(z3):>9}  {pct(z3,tot):>7}  [{z3/60:.0f} min]")
    print(f"    Z4:  {hm(z4):>9}  {pct(z4,tot):>7}  [{z4/60:.0f} min]")
    print(f"    Z5:  {hm(z5):>9}  {pct(z5,tot):>7}  [{z5/60:.0f} min]")
    print(f"    ─────────────────────────────────")
    print(f"    Z3+: {hm(z3+z4+z5):>9}  {pct(z3+z4+z5,tot):>7}")
    print(f"    Z4+: {hm(z4+z5):>9}  {pct(z4+z5,tot):>7}  ← target ≥15%  gap: {max(0,15-100*(z4+z5)/tot):.1f}pp")

hr_zone_block("ALL RIDES COMBINED")
hr_zone_block("Indoor only",               "a.is_indoor=1")
hr_zone_block("Outdoor + power meter",     "a.is_indoor=0 AND a.has_power=1")
hr_zone_block("Outdoor, no power meter",   "a.is_indoor=0 AND a.has_power=0")


# ── Power Zone Distribution ───────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("3. POWER ZONE DISTRIBUTION — per-second, all rides with power")
print(f"{'─'*74}")

def pw_zone_block(label, ftp, col_prefix, where="1=1", params=()):
    r = q(f"""
        SELECT
            SUM(zs.{col_prefix}_z1_s) p1, SUM(zs.{col_prefix}_z2_s) p2,
            SUM(zs.{col_prefix}_z3_s) p3, SUM(zs.{col_prefix}_z4_s) p4,
            SUM(zs.{col_prefix}_z5_s) p5, SUM(zs.{col_prefix}_z6_s) p6,
            SUM(zs.{col_prefix}_z7_s) p7, SUM(zs.{col_prefix}_total_s) tot,
            COUNT(*) n
        FROM zone_summaries zs
        JOIN activities a USING (activity_id)
        WHERE {where}
    """, params)[0]
    if not r['tot'] or r['tot'] == 0: return
    p1,p2,p3,p4,p5,p6,p7,tot = r['p1'],r['p2'],r['p3'],r['p4'],r['p5'],r['p6'],r['p7'],r['tot']
    print(f"\n  {label} FTP={ftp}W ({r['n']} power rides):")
    print(f"    P1 <{int(0.55*ftp)}W  Recovery:  {hm(p1):>9}  {pct(p1,tot):>7}")
    print(f"    P2  Endurance:         {hm(p2):>9}  {pct(p2,tot):>7}")
    print(f"    P3  Tempo:             {hm(p3):>9}  {pct(p3,tot):>7}")
    print(f"    P4  Threshold:         {hm(p4):>9}  {pct(p4,tot):>7}  [{p4/60:.0f} min]")
    print(f"    P5  VO2max:            {hm(p5):>9}  {pct(p5,tot):>7}  [{p5/60:.0f} min]")
    print(f"    P6  Anaerobic:         {hm(p6):>9}  {pct(p6,tot):>7}")
    print(f"    P7  NM:                {hm(p7):>9}  {pct(p7,tot):>7}")
    p4plus = p4+p5+p6+p7
    print(f"    P4+ threshold+:        {hm(p4plus):>9}  {pct(p4plus,tot):>7}  [{p4plus/60:.0f} min]")

pw_zone_block("All power rides", 256, "pw256", "a.has_power=1")
pw_zone_block("All power rides", 235, "pw235", "a.has_power=1")

# Side-by-side comparison
r256 = q1("SELECT SUM(pw256_z4_s+pw256_z5_s+pw256_z6_s+pw256_z7_s) FROM zone_summaries z JOIN activities a USING(activity_id) WHERE a.has_power=1")
r235 = q1("SELECT SUM(pw235_z4_s+pw235_z5_s+pw235_z6_s+pw235_z7_s) FROM zone_summaries z JOIN activities a USING(activity_id) WHERE a.has_power=1")
ptot = q1("SELECT SUM(pw256_total_s) FROM zone_summaries z JOIN activities a USING(activity_id) WHERE a.has_power=1")
if r256 and r235 and ptot:
    print(f"\n  FTP impact on P4+ classification:")
    print(f"    FTP=256W → P4+: {r256/60:.0f} min  ({100*r256/ptot:.1f}% of power time)")
    print(f"    FTP=235W → P4+: {r235/60:.0f} min  ({100*r235/ptot:.1f}% of power time)")
    print(f"    Δ = {(r235-r256)/60:.0f} min mis-classified as Tempo at FTP=256W")


# ── Monthly breakdown ─────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("4. MONTHLY BREAKDOWN — HR Z4 minutes + power Z4 minutes")
print(f"{'─'*74}")

monthly = q("""
    SELECT
        a.month,
        COUNT(*)                                        AS rides,
        ROUND(SUM(zs.hr_z4_s + zs.hr_z5_s)/60, 1)     AS hr_z4_min,
        ROUND(SUM(zs.hr_z3_s + zs.hr_z4_s + zs.hr_z5_s)/60, 1) AS hr_z3plus_min,
        ROUND(100.0*(SUM(zs.hr_z4_s+zs.hr_z5_s))/NULLIF(SUM(zs.hr_total_s),0), 1) AS hr_z4_pct,
        ROUND(SUM(zs.pw256_z4_s+zs.pw256_z5_s+zs.pw256_z6_s+zs.pw256_z7_s)/60, 1) AS pw_z4_min,
        ROUND(100.0*(SUM(zs.pw256_z4_s+zs.pw256_z5_s+zs.pw256_z6_s+zs.pw256_z7_s))
              /NULLIF(SUM(zs.pw256_total_s),0), 1)      AS pw_z4_pct,
        ROUND(SUM(zs.hr_total_s)/3600.0, 1)             AS hr_hours,
        ROUND(SUM(a.distance_km), 0)                    AS km
    FROM activities a
    JOIN zone_summaries zs USING (activity_id)
    GROUP BY a.month
    ORDER BY a.month
""")

print(f"\n  {'Month':<9} {'Rides':>5} {'kmD':>6} {'HRh':>5} {'Z4+Z5m':>8} {'Z3+m':>7} {'Z4%':>6}  {'PwZ4m':>7} {'PwZ4%':>7}")
print("  " + "─"*65)
for r in monthly:
    pw_str = f"{r['pw_z4_min']:7.1f}  {r['pw_z4_pct'] or 0:6.1f}%" if r['pw_z4_min'] else "      -        -"
    note = ""
    if r['month'] == "2026-04": note = " ← PEAK"
    if r['month'] == "2026-08": note = " ← DIP"
    if r['month'] == "2026-09": note = " ← recovering"
    print(f"  {r['month']}  {r['rides']:5}  {r['km'] or 0:6.0f}  {r['hr_hours']:5.1f}  "
          f"{r['hr_z4_min'] or 0:7.1f}  {r['hr_z3plus_min'] or 0:6.1f}  "
          f"{r['hr_z4_pct'] or 0:5.1f}%  {pw_str}{note}")


# ── Per-ride table ────────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("5. PER-RIDE BREAKDOWN — all rides, chronological")
print(f"   Columns: date | sub_sport | km | m↑ | avHR | mxHR | Z3m | Z4m | Z5m | NP | PDC20 | drift%")
print(f"{'─'*74}")

all_rides = q("""
    SELECT
        a.date, a.sub_sport, a.is_indoor, a.has_power,
        ROUND(a.distance_km,0)          AS km,
        ROUND(a.elevation_gain_m,0)     AS elev,
        a.avg_hr_bpm                    AS avhr,
        a.max_hr_bpm                    AS mxhr,
        ROUND(zs.hr_z3_s/60.0,1)       AS z3m,
        ROUND(zs.hr_z4_s/60.0,1)       AS z4m,
        ROUND(zs.hr_z5_s/60.0,1)       AS z5m,
        a.np_w_computed                 AS np,
        a.pdc_20min_w                   AS pdc20,
        a.pw_hr_drift_pct               AS drift,
        a.te_aerobic                    AS te,
        a.avg_temp_c
    FROM activities a
    JOIN zone_summaries zs USING (activity_id)
    WHERE zs.hr_total_s > 120
    ORDER BY a.date
""")

print(f"\n  {'Date':<12} {'Sport':<14} {'km':>5} {'m↑':>5} "
      f"{'avHR':>5} {'mxHR':>5} {'Z3m':>5} {'Z4m':>5} {'Z5m':>5} "
      f"{'NP':>5} {'PDC20':>6} {'drift':>7}")
print("  " + "─"*100)

for r in all_rides:
    np_s    = str(r['np']) if r['np'] else "-"
    pdc_s   = str(r['pdc20']) if r['pdc20'] else "-"
    drift_s = f"{r['drift']:+.1f}%" if r['drift'] is not None else "-"
    flag    = ""
    if (r['z4m'] or 0) >= 15: flag = " ◀◀Z4"
    elif (r['z4m'] or 0) >= 5: flag = " ◀Z4"
    elif r['mxhr'] and r['mxhr'] >= 180: flag = " ↑Z5"
    print(f"  {r['date']:<12} {r['sub_sport']:<14} "
          f"{r['km'] or 0:>5.0f} {r['elev'] or 0:>5.0f} "
          f"{r['avhr'] or '-':>5} {r['mxhr'] or '-':>5} "
          f"{r['z3m'] or 0:>5.1f} {r['z4m'] or 0:>5.1f} {r['z5m'] or 0:>5.1f} "
          f"{np_s:>5} {pdc_s:>6} {drift_s:>7}{flag}")


# ── Top 20 Z4 rides ───────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("6. TOP 20 RIDES BY HR Z4+Z5 MINUTES")
print(f"{'─'*74}")

top_z4 = q("""
    SELECT
        a.date, a.sub_sport,
        ROUND((zs.hr_z3_s)/60,1) z3m,
        ROUND((zs.hr_z4_s)/60,1) z4m,
        ROUND((zs.hr_z5_s)/60,1) z5m,
        a.max_hr_bpm, a.np_w_computed np,
        a.te_aerobic te
    FROM activities a
    JOIN zone_summaries zs USING (activity_id)
    ORDER BY (zs.hr_z4_s + zs.hr_z5_s) DESC
    LIMIT 20
""")

for i, r in enumerate(top_z4, 1):
    np_s = f"NP={r['np']}W" if r['np'] else ""
    te_s = f"TE={r['te']:.1f}" if r['te'] else ""
    print(f"  {i:2}. {r['date']}  {r['sub_sport']:<18}  "
          f"Z3:{r['z3m']:5.1f}m  Z4:{r['z4m']:5.1f}m  Z5:{r['z5m']:4.1f}m  "
          f"maxHR={r['max_hr_bpm'] or '-'}  {np_s}  {te_s}")


# ── 20-min PDC progression ────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("7. 20-MIN PDC PROGRESSION — outdoor power rides, chronological")
print(f"{'─'*74}")

pdc_prog = q("""
    SELECT date, pdc_20min_w, pdc_5min_w, pdc_10min_w, np_w_computed, sub_sport
    FROM activities
    WHERE has_power=1 AND is_indoor=0 AND pdc_20min_w IS NOT NULL
    ORDER BY date
""")

prev = None
for r in pdc_prog:
    w = r['pdc_20min_w']
    delta = f"{w-prev:+d}" if prev else "   "
    bar_s = "▓" * max(0, int((w - 150) / 3))
    print(f"  {r['date']}  {w:>3}W ({delta})  {bar_s}  "
          f"[5m={r['pdc_5min_w'] or '-':>4} 10m={r['pdc_10min_w'] or '-':>4}]")
    prev = w


# ── Best PDC all-time ──────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("8. SEASON BEST PDC (all durations)")
print(f"{'─'*74}")

for dur, col in [("5s","pdc_5s_w"),("30s","pdc_30s_w"),("1min","pdc_1min_w"),
                  ("5min","pdc_5min_w"),("10min","pdc_10min_w"),
                  ("20min","pdc_20min_w"),("60min","pdc_60min_w")]:
    r = q(f"""
        SELECT {col}, date, sub_sport FROM activities
        WHERE {col} IS NOT NULL
        ORDER BY {col} DESC LIMIT 1
    """)
    if r:
        print(f"  {dur:>6}:  {r[0][col]:>4}W   {r[0]['date']}  {r[0]['sub_sport']}")


# ── Aerobic coupling ──────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("9. AEROBIC COUPLING — HR drift % (power rides >60min)")
print(f"   Negative drift = well coupled (NP/HR stable or improving)")
print(f"   Positive drift = cardiac drift / fatigue / heat")
print(f"{'─'*74}")

drift_rides = q("""
    SELECT date, sub_sport, pw_hr_drift_pct drift,
           np_w_computed np, avg_hr_bpm avhr, avg_temp_c temp,
           elevation_gain_m elev
    FROM activities
    WHERE pw_hr_drift_pct IS NOT NULL
    ORDER BY date
""")

for r in drift_rides:
    d = r['drift']
    interp = "well-coupled ✓" if abs(d) < 5 else ("moderate" if abs(d) < 15 else "decoupled ⚠")
    np_s = f"NP={r['np']}W" if r['np'] else ""
    t_s  = f"{r['temp']}°C" if r['temp'] else ""
    print(f"  {r['date']}  {r['sub_sport']:<16}  drift={d:+6.1f}%  {interp:<18}  {np_s}  {t_s}")


# ── Aerobic efficiency ────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("10. AEROBIC EFFICIENCY — NP / avg_HR (W/bpm), hilly outdoor power rides")
print(f"{'─'*74}")

eff_rides = q("""
    SELECT date, aerobic_eff_np_hr eff, np_w_computed np,
           avg_hr_bpm avhr, elevation_gain_m elev, sub_sport
    FROM activities
    WHERE aerobic_eff_np_hr IS NOT NULL AND is_indoor=0 AND elevation_gain_m > 100
    ORDER BY aerobic_eff_np_hr DESC
    LIMIT 20
""")

for r in eff_rides:
    b = "▓" * int((r['eff'] or 0) * 5)
    print(f"  {r['date']}  {r['eff']:.3f} W/bpm  NP={r['np']}W  avgHR={r['avhr']}  "
          f"{r['elev']:.0f}m  {b}")

avg_eff = q1("""
    SELECT AVG(aerobic_eff_np_hr) FROM activities
    WHERE aerobic_eff_np_hr IS NOT NULL AND is_indoor=0 AND elevation_gain_m > 100
""")
if avg_eff:
    print(f"\n  Season avg aerobic efficiency: {avg_eff:.3f} W/bpm")


# ── Best laps ─────────────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("11. BEST CLIMBING LAPS — by lap NP, outdoor power rides")
print(f"{'─'*74}")

best_laps = q("""
    SELECT
        a.date, a.sub_sport,
        l.lap_index, l.np_w, l.avg_power_w, l.avg_hr_bpm,
        ROUND(l.elevation_gain_m,0) elev,
        ROUND(l.elapsed_time_s/60.0,1) min,
        ROUND(l.hr_z4_s/60.0,1) z4m
    FROM laps l
    JOIN activities a USING (activity_id)
    WHERE a.has_power=1 AND a.is_indoor=0
      AND l.np_w IS NOT NULL AND l.elevation_gain_m > 80
    ORDER BY l.np_w DESC
    LIMIT 25
""")

print(f"  {'Date':<12} {'Sport':<14} {'Lap':>4} {'NP':>5} {'AvgW':>5} "
      f"{'HR':>5} {'Asc':>5} {'min':>6} {'Z4m':>5}")
print("  " + "─"*72)
for r in best_laps:
    print(f"  {r['date']:<12} {r['sub_sport']:<14} L{r['lap_index']:<3} "
          f"{r['np_w'] or '-':>5} {r['avg_power_w'] or '-':>5} "
          f"{r['avg_hr_bpm'] or '-':>5} {r['elev'] or '-':>5}m "
          f"{r['min']:>5.1f}m {r['z4m'] or 0:>5.1f}")


# ── No-power lap HR intensity ─────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("12. NO-POWER RIDES — lap-level HR intensity (peak lap HR per ride)")
print(f"{'─'*74}")

nopow = q("""
    SELECT
        a.date,
        a.sub_sport,
        MAX(l.avg_hr_bpm)                                            AS peak_lap_hr,
        SUM(CASE WHEN l.avg_hr_bpm >= 155 THEN 1 ELSE 0 END)        AS z3_laps,
        SUM(CASE WHEN l.avg_hr_bpm >= 166 THEN 1 ELSE 0 END)        AS z4_laps,
        a.max_hr_bpm                                                  AS session_max_hr
    FROM laps l
    JOIN activities a USING (activity_id)
    WHERE a.has_power=0 AND a.is_indoor=0
      AND l.avg_hr_bpm IS NOT NULL
    GROUP BY a.activity_id
    HAVING peak_lap_hr >= 150
    ORDER BY a.date
""")

z3_count = sum(1 for r in nopow if r['peak_lap_hr'] >= 155)
z4_count = sum(1 for r in nopow if r['peak_lap_hr'] >= 166)

for r in nopow:
    if r['peak_lap_hr'] < 155: continue
    flag = " ◀◀" if r['z4_laps'] >= 3 else (" ◀" if r['z4_laps'] >= 1 else "")
    print(f"  {r['date']}  peak={r['peak_lap_hr']:>3}bpm  "
          f"Z3-laps={r['z3_laps']}  Z4-laps={r['z4_laps']}  "
          f"sessMax={r['session_max_hr'] or '-'}{flag}")

total_nopow = q1("SELECT COUNT(DISTINCT activity_id) FROM laps l JOIN activities a USING(activity_id) WHERE a.has_power=0 AND a.is_indoor=0")
print(f"\n  No-power outdoor rides total:        {total_nopow}")
print(f"  Rides with peak lap ≥Z3 (155+bpm):  {z3_count}  ({100*z3_count//max(total_nopow,1)}%)")
print(f"  Rides with peak lap ≥Z4 (166+bpm):  {z4_count}  ({100*z4_count//max(total_nopow,1)}%)")


# ── Recent 30 days ────────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("13. RECENT 30 DAYS — Aug 25 → Sep 24 2026")
print(f"{'─'*74}")

recent = q("""
    SELECT
        a.date, a.sub_sport, a.has_power,
        ROUND(a.distance_km,0) km,
        ROUND(a.elevation_gain_m,0) elev,
        a.avg_hr_bpm avhr, a.max_hr_bpm mxhr,
        ROUND(zs.hr_z3_s/60,1) z3m,
        ROUND(zs.hr_z4_s/60,1) z4m,
        ROUND(zs.hr_z5_s/60,1) z5m,
        a.np_w_computed np,
        a.pdc_20min_w pdc20,
        a.pw_hr_drift_pct drift,
        a.te_aerobic te,
        a.avg_temp_c temp,
        MAX(l.avg_hr_bpm) peak_lap
    FROM activities a
    JOIN zone_summaries zs USING (activity_id)
    LEFT JOIN laps l USING (activity_id)
    WHERE a.date >= '2026-08-25'
    GROUP BY a.activity_id
    ORDER BY a.date
""")

for r in recent:
    pw_s    = f"NP={r['np']}W  PDC20={r['pdc20']}W" if r['has_power'] and r['np'] else "no-power"
    drift_s = f"drift={r['drift']:+.1f}%" if r['drift'] is not None else ""
    te_s    = f"TE={r['te']:.1f}" if r['te'] else ""
    t_s     = f"{r['temp']}°C" if r['temp'] else ""
    print(f"\n  {r['date']}  {r['sub_sport']}  {r['km']:.0f}km · {r['elev']:.0f}m · "
          f"{t_s}")
    print(f"    avgHR={r['avhr'] or '-'}  maxHR={r['mxhr'] or '-'}  "
          f"peakLap={r['peak_lap'] or '-'}bpm")
    print(f"    Z3:{r['z3m'] or 0:.1f}m  Z4:{r['z4m'] or 0:.1f}m  Z5:{r['z5m'] or 0:.1f}m  "
          f"{pw_s}  {drift_s}  {te_s}")


# ── Diagnosis ─────────────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("14. DIAGNOSIS SUMMARY")
print(f"{'─'*74}")

tot_hr_s  = q1("SELECT SUM(hr_total_s) FROM zone_summaries")
z4_all_s  = q1("SELECT SUM(hr_z4_s+hr_z5_s) FROM zone_summaries")
z3_all_s  = q1("SELECT SUM(hr_z3_s) FROM zone_summaries")

last_z4 = q("""
    SELECT a.date, a.sub_sport, ROUND((zs.hr_z4_s+zs.hr_z5_s)/60,1) z4min, a.np_w_computed np
    FROM activities a JOIN zone_summaries zs USING(activity_id)
    WHERE zs.hr_z4_s+zs.hr_z5_s > 60
    ORDER BY a.date DESC LIMIT 1
""")

best20 = q("SELECT pdc_20min_w, date FROM activities WHERE pdc_20min_w IS NOT NULL ORDER BY pdc_20min_w DESC LIMIT 1")
best5  = q1("SELECT MAX(pdc_5min_w) FROM activities")
best10 = q1("SELECT MAX(pdc_10min_w) FROM activities")

sep_z4  = q1("SELECT SUM(hr_z4_s+hr_z5_s)/60.0 FROM zone_summaries z JOIN activities a USING(activity_id) WHERE a.month='2026-09'")
week_z4 = q1("SELECT SUM(hr_z4_s+hr_z5_s)/60.0 FROM zone_summaries z JOIN activities a USING(activity_id) WHERE a.date>='2026-09-18'")

print(f"\n  ── HR Zone Reality ──────────────────────────────")
print(f"  Total HR time:         {hm(tot_hr_s)}")
print(f"  Z4+Z5 all-time:        {z4_all_s/60:.0f} min   ({100*z4_all_s/tot_hr_s:.1f}%)")
print(f"  Z3 all-time:           {z3_all_s/60:.0f} min   ({100*z3_all_s/tot_hr_s:.1f}%)")
print(f"  Z3+ combined:          {(z3_all_s+z4_all_s)/60:.0f} min   ({100*(z3_all_s+z4_all_s)/tot_hr_s:.1f}%)")
print(f"  Z4+ gap to 15% target: {max(0, 15 - 100*z4_all_s/tot_hr_s):.1f} percentage points")

if last_z4:
    r = last_z4[0]
    from datetime import date as dtdate
    days = (dtdate(2026,9,24) - dtdate.fromisoformat(r['date'])).days
    print(f"\n  ── Z4 Recency ───────────────────────────────────")
    print(f"  Last ride with >1min Z4:  {r['date']} ({days} days ago)")
    print(f"    {r['sub_sport']}  Z4={r['z4min']}min  NP={r['np'] or '-'}W")

print(f"  Sep 2026 Z4+Z5:           {sep_z4:.0f} min")
print(f"  Current week (Sep18-24):  {week_z4:.0f} min Z4+Z5")

print(f"\n  ── Power Duration Curve ─────────────────────────")
print(f"  Season best 5-min:   {best5}W")
print(f"  Season best 10-min:  {best10}W")
if best20:
    print(f"  Season best 20-min:  {best20[0][0]}W  on {best20[0]['date']}")
    print(f"    FTP estimate ×0.95:        {round(best20[0][0]*0.95)}W")
    print(f"    FTP from 15-min climb:     ~235W  (Sep 19: 261W × 0.90)")
    print(f"    Garmin manual entry:       256W   (never formally tested)")

print(f"\n  ── Interval Targets (use FTP=235W) ──────────────")
print(f"  Z3 Tempo:     176–212W  (end HR 158–165bpm)")
print(f"  Z4 Threshold: 212–247W  (end HR 166–174bpm)")
print(f"  Z5 VO2max:    247–282W  (end HR 172–179bpm)")


# ── Weekly compliance ─────────────────────────────────────────────────────────
print(f"\n{'─'*74}")
print("15. WEEKLY COMPLIANCE — current week + last 4 Saturdays")
print(f"{'─'*74}")

from datetime import date as dtdate
today = dtdate.today()
# Start of current ISO week (Monday)
week_start = (today - __import__('datetime').timedelta(days=today.weekday())).isoformat()
week_end   = today.isoformat()

week_rides = q("""
    SELECT a.date, a.sub_sport, a.has_power,
           ROUND(a.distance_km,0) km,
           a.np_w_computed np,
           a.pdc_20min_w pdc20,
           ROUND(zs.hr_z4_s/60.0 + zs.hr_z5_s/60.0, 1) z4min
    FROM activities a
    JOIN zone_summaries zs USING(activity_id)
    WHERE a.date >= ? AND a.date <= ?
    ORDER BY a.date
""", (week_start, week_end))

week_z4_total = sum((r['z4min'] or 0) for r in week_rides)
week_np_rides = [r for r in week_rides if r['np']]

print(f"\n  Week {week_start} → {week_end}:")
if week_rides:
    for r in week_rides:
        pw_s  = f"NP={r['np']}W" if r['np'] else "no-power"
        z4_s  = f"Z4={r['z4min']:.1f}min" if r['z4min'] else "Z4=0"
        print(f"    {r['date']}  {r['sub_sport']:<16}  {pw_s:<12}  {z4_s}")
else:
    print("    (no rides yet this week)")

print(f"\n  Week totals: {len(week_rides)} ride(s)  ·  Z4+Z5: {week_z4_total:.1f} min")

# Plan targets for this week
print(f"\n  Plan targets (W1 Sep 25–28):")
print(f"    Thu: 3×10min Z3 (184–220W / end HR 158–165bpm)")
print(f"    Sat: NP 182–190W, 800–1,000m climbing")
print(f"    Z4 target this week: any Z4 is a bonus in W1 (re-anchor Z3)")

# Last 4 Saturdays
print(f"\n  Last 4 Saturdays (power meter rides):")
sats = q("""
    SELECT date, np_w_computed np, pdc_20min_w pdc20,
           ROUND(elevation_gain_m,0) elev,
           ROUND(distance_km,0) km,
           ROUND(duration_s/3600.0, 1) hours
    FROM activities
    WHERE strftime('%w', date) = '6'
      AND is_indoor = 0
    ORDER BY date DESC
    LIMIT 4
""")

prev_np = None
for r in sats:
    np_s = f"NP={r['np']}W" if r['np'] else "NP=-"
    delta = ""
    if prev_np and r['np']:
        delta = f" ({r['np']-prev_np:+d}W MoM)"
    pdc_s = f"PDC20={r['pdc20']}W" if r['pdc20'] else ""
    print(f"    {r['date']}  {np_s}{delta}  {pdc_s}  {r['elev']:.0f}m  {r['km']:.0f}km  {r['hours']}h")
    prev_np = r['np']

print(f"\n{'═'*74}")
print("✓ Analysis complete. Source: data/training.db (raw FIT → SQLite ETL)")

conn.close()
