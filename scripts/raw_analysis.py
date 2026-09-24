#!/usr/bin/env python3
"""
Full season analysis from RAW FIT files only.
No Garmin API, no pre-processed JSON — every sample read directly.

184 .fit files → per-second HR + power classification → all stats computed here.

HR zones (Ettore):
  Z1: 100-129 bpm
  Z2: 130-154 bpm
  Z3: 155-165 bpm
  Z4: 166-179 bpm
  Z5: 180+    bpm

Power zones FTP=256W:
  P1: <141W        (Z1 Recovery)
  P2: 141-192W     (Z2 Endurance)
  P3: 193-230W     (Z3 Tempo)
  P4: 231-268W     (Z4 Threshold)
  P5: 269-307W     (Z5 VO2max)
  P6: 308-384W     (Z6 Anaerobic)
  P7: 384+W        (Z7 NM)

Corrected FTP estimate: 235W (Sep 19 15-min climb evidence).
Both FTPs used for comparison in power zone sections.
"""

import fitparse, glob, os, sys
from datetime import datetime, timezone
from collections import defaultdict

FIT_DIR = "/Users/ettoretr/Documents/wattsupai/data/fit-raw"

# ── Zone boundary helpers ──────────────────────────────────────────────────────
def hr_zone(bpm):
    if bpm is None or bpm < 60: return None
    if bpm < 130: return 1
    if bpm < 155: return 2
    if bpm < 166: return 3
    if bpm < 180: return 4
    return 5

def power_zone(w, ftp=256):
    if w is None or w < 0: return None
    thresholds = [0.55*ftp, 0.75*ftp, 0.90*ftp, 1.05*ftp, 1.20*ftp, 1.50*ftp]
    for i, t in enumerate(thresholds):
        if w < t: return i+1
    return 7

# ── Rolling NP helper (30s rolling average, 4th power mean) ──────────────────
def calc_np(power_series):
    """Compute Normalized Power from 1-second power series."""
    if len(power_series) < 30:
        return None
    # Fill None with 0
    p = [x if x is not None else 0 for x in power_series]
    rolling = []
    for i in range(29, len(p)):
        avg = sum(p[i-29:i+1]) / 30
        rolling.append(avg ** 4)
    if not rolling:
        return None
    return round((sum(rolling) / len(rolling)) ** 0.25)

# ── Best mean maximal power (PDC) ─────────────────────────────────────────────
def best_mmp(power_series, duration_s):
    """Find best mean power over `duration_s` seconds."""
    p = [x if x is not None else 0 for x in power_series]
    if len(p) < duration_s:
        return None
    best = 0
    for i in range(len(p) - duration_s + 1):
        avg = sum(p[i:i+duration_s]) / duration_s
        if avg > best:
            best = avg
    return round(best)

# ── HR drift (aerobic decoupling) ─────────────────────────────────────────────
def calc_hr_drift(hr_series, power_series):
    """
    Compare power:HR ratio in first half vs second half.
    Negative = HR lower in 2nd half relative to power (well coupled or improving).
    Positive = HR higher in 2nd half (decoupling / fatigue).
    Returns pct drift.
    """
    paired = [(h,p) for h,p in zip(hr_series, power_series)
              if h is not None and p is not None and h > 100 and p > 50]
    if len(paired) < 120:
        return None
    mid = len(paired) // 2
    first = paired[:mid]
    second = paired[mid:]
    ratio1 = sum(p/h for h,p in first) / len(first)
    ratio2 = sum(p/h for h,p in second) / len(second)
    if ratio1 == 0:
        return None
    drift = 100 * (ratio2 - ratio1) / ratio1   # positive = decoupling
    return round(drift, 1)

# ── Parse all FIT files ───────────────────────────────────────────────────────
print("Parsing all FIT files... (this may take 30-60s)")

rides = []
fit_files = sorted(glob.glob(f"{FIT_DIR}/*.fit"))
print(f"Found {len(fit_files)} FIT files\n")

for fpath in fit_files:
    aid = os.path.basename(fpath).replace(".fit", "")
    try:
        fit = fitparse.FitFile(fpath)
    except Exception as e:
        print(f"  SKIP {aid}: {e}")
        continue

    # Session-level metadata from session message
    session_info = {}
    for msg in fit.get_messages("session"):
        for f in msg:
            session_info[f.name] = f.value

    start_time = session_info.get("start_time")
    if start_time is None:
        continue
    if hasattr(start_time, "replace"):
        # naive datetime — treat as UTC
        date_str = start_time.strftime("%Y-%m-%d")
        month_str = start_time.strftime("%Y-%m")
    else:
        continue

    sport = str(session_info.get("sport", "")).lower()
    sub_sport = str(session_info.get("sub_sport", "")).lower()
    is_indoor = "indoor" in sub_sport or sub_sport == "virtual_activity"

    total_distance_km = (session_info.get("total_distance") or 0) / 1000
    total_ascent_m    = session_info.get("total_ascent") or 0
    total_calories    = session_info.get("total_calories") or 0
    timer_time_s      = session_info.get("total_timer_time") or 0
    avg_temp_c        = session_info.get("avg_temperature")
    max_temp_c        = session_info.get("max_temperature")
    te_aerobic        = session_info.get("total_training_effect")
    te_anaerobic      = session_info.get("total_anaerobic_training_effect")

    # Per-record samples
    hr_series    = []
    power_series = []
    speed_series = []
    alt_series   = []
    cadence_series = []
    timestamps   = []

    for rec in fit.get_messages("record"):
        d = {f.name: f.value for f in rec}
        hr    = d.get("heart_rate")
        power = d.get("power")
        speed = d.get("speed")           # m/s
        alt   = d.get("enhanced_altitude") or d.get("altitude")
        cad   = d.get("cadence")
        ts    = d.get("timestamp")

        hr_series.append(hr)
        power_series.append(power)
        speed_series.append(speed)
        alt_series.append(alt)
        cadence_series.append(cad)
        timestamps.append(ts)

    n_records = len(hr_series)
    if n_records < 30:
        continue

    has_power = sum(1 for p in power_series if p is not None and p > 5) > 60

    # ── HR zone seconds (each record ≈ 1s unless gaps) ────────────────────────
    # Compute actual sample intervals from timestamps
    intervals = []
    for i in range(1, len(timestamps)):
        if timestamps[i] and timestamps[i-1]:
            try:
                delta = (timestamps[i] - timestamps[i-1]).total_seconds()
                intervals.append(max(0.5, min(delta, 10.0)))  # clamp 0.5–10s
            except:
                intervals.append(1.0)
        else:
            intervals.append(1.0)
    intervals = [intervals[0]] + intervals  # first sample gets same as second

    hr_zone_s  = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
    pw_zone_s  = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0}
    pw_zone_s235 = {1:0.0, 2:0.0, 3:0.0, 4:0.0, 5:0.0, 6:0.0, 7:0.0}
    hr_total_s = 0.0
    pw_total_s = 0.0

    for i, (hr, pw, dt) in enumerate(zip(hr_series, power_series, intervals)):
        z = hr_zone(hr)
        if z:
            hr_zone_s[z] += dt
            hr_total_s   += dt
        if has_power and pw is not None and pw >= 0:
            z256 = power_zone(pw, ftp=256)
            z235 = power_zone(pw, ftp=235)
            if z256:
                pw_zone_s[z256]    += dt
                pw_total_s         += dt
            if z235:
                pw_zone_s235[z235] += dt

    # ── Summary HR stats ──────────────────────────────────────────────────────
    hr_vals = [h for h in hr_series if h is not None and h > 60]
    avg_hr  = round(sum(hr_vals)/len(hr_vals)) if hr_vals else None
    max_hr  = max(hr_vals) if hr_vals else None

    # ── NP and PDC (power rides only) ────────────────────────────────────────
    np_w = None
    pdc  = {}
    if has_power:
        clean_power = [p for p in power_series if p is not None]
        np_w = calc_np(power_series)
        for dur, key in [(5,"5s"),(300,"5min"),(600,"10min"),(1200,"20min"),(3600,"60min")]:
            pdc[key] = best_mmp(power_series, dur)

    # ── Avg power ──────────────────────────────────────────────────────────────
    pw_vals = [p for p in power_series if p is not None and p > 0]
    avg_power = round(sum(pw_vals)/len(pw_vals)) if pw_vals else None
    max_power = max(pw_vals) if pw_vals else None

    # ── HR drift ──────────────────────────────────────────────────────────────
    hr_drift_pct = None
    if has_power and timer_time_s > 3600:
        hr_drift_pct = calc_hr_drift(hr_series, power_series)

    # ── Aerobic efficiency (NP / avg_HR) ─────────────────────────────────────
    aerobic_efficiency = None
    if np_w and avg_hr and avg_hr > 100:
        aerobic_efficiency = round(np_w / avg_hr, 3)

    rides.append({
        "aid": aid,
        "date_str": date_str,
        "month": month_str,
        "date": datetime.strptime(date_str, "%Y-%m-%d"),
        "sport": sport,
        "sub_sport": sub_sport,
        "is_indoor": is_indoor,
        "distance_km": round(total_distance_km, 1),
        "elevation_m": total_ascent_m,
        "timer_s": timer_time_s,
        "calories": total_calories,
        "avg_temp_c": avg_temp_c,
        "max_temp_c": max_temp_c,
        "te_aerobic": te_aerobic,
        "te_anaerobic": te_anaerobic,
        # HR
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "hr_z1_s": hr_zone_s[1],
        "hr_z2_s": hr_zone_s[2],
        "hr_z3_s": hr_zone_s[3],
        "hr_z4_s": hr_zone_s[4],
        "hr_z5_s": hr_zone_s[5],
        "hr_total_s": hr_total_s,
        # Power (FTP=256)
        "has_power": has_power,
        "np_w": np_w,
        "avg_power": avg_power,
        "max_power": max_power,
        "pw_z1_s": pw_zone_s[1],
        "pw_z2_s": pw_zone_s[2],
        "pw_z3_s": pw_zone_s[3],
        "pw_z4_s": pw_zone_s[4],
        "pw_z5_s": pw_zone_s[5],
        "pw_z6_s": pw_zone_s[6],
        "pw_z7_s": pw_zone_s[7],
        "pw_total_s": pw_total_s,
        # Power (FTP=235 corrected)
        "pw235_z4_s": pw_zone_s235[4]+pw_zone_s235[5]+pw_zone_s235[6]+pw_zone_s235[7],
        # PDC
        "pdc_5s":    pdc.get("5s"),
        "pdc_5min":  pdc.get("5min"),
        "pdc_10min": pdc.get("10min"),
        "pdc_20min": pdc.get("20min"),
        "pdc_60min": pdc.get("60min"),
        # Coupling
        "hr_drift_pct": hr_drift_pct,
        "aerobic_efficiency": aerobic_efficiency,
        "n_records": n_records,
    })

rides.sort(key=lambda r: r["date"])
print(f"Parsed {len(rides)} rides  ({rides[0]['date_str']} → {rides[-1]['date_str']})\n")

# ══════════════════════════════════════════════════════════════════════════════
SEP = "═" * 74

def hm(s):
    s = int(s)
    return f"{s//3600}h{(s%3600)//60:02d}m"

def pct(n, d):
    return f"{100*n/d:.1f}%" if d > 0 else "N/A"

# ══════════════════════════════════════════════════════════════════════════════
print(SEP)
print("SECTION 1 — SEASON OVERVIEW (from raw FIT files)")
print(SEP)

indoor   = [r for r in rides if r["is_indoor"]]
outdoor  = [r for r in rides if not r["is_indoor"]]
pw_rides = [r for r in rides if r["has_power"]]
nopw     = [r for r in rides if not r["has_power"]]
out_pw   = [r for r in outdoor if r["has_power"]]
out_nopw = [r for r in outdoor if not r["has_power"]]

total_dist  = sum(r["distance_km"] for r in rides)
total_elev  = sum(r["elevation_m"] for r in rides)
total_hr_s  = sum(r["hr_total_s"] for r in rides)
total_pw_s  = sum(r["pw_total_s"] for r in rides)
total_cal   = sum(r["calories"] or 0 for r in rides)

print(f"  Date range:              {rides[0]['date_str']} → {rides[-1]['date_str']}")
print(f"  Total rides:             {len(rides)}")
print(f"    Indoor (trainer):      {len(indoor)}")
print(f"    Outdoor total:         {len(outdoor)}")
print(f"      Outdoor + power:     {len(out_pw)}")
print(f"      Outdoor, no power:   {len(out_nopw)}")
print(f"  Total distance:          {total_dist:.0f} km")
print(f"  Total elevation:         {total_elev:.0f} m")
print(f"  Total calories:          {total_cal:.0f} kcal")
print(f"  HR-tracked time:         {hm(total_hr_s)}")
print(f"  Power-tracked time:      {hm(total_pw_s)}")
print(f"  Total records parsed:    {sum(r['n_records'] for r in rides):,}")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 2 — HR ZONE DISTRIBUTION (per-second, ALL rides)")
print(SEP)

def hr_zone_report(ride_list, label):
    z1 = sum(r["hr_z1_s"] for r in ride_list)
    z2 = sum(r["hr_z2_s"] for r in ride_list)
    z3 = sum(r["hr_z3_s"] for r in ride_list)
    z4 = sum(r["hr_z4_s"] for r in ride_list)
    z5 = sum(r["hr_z5_s"] for r in ride_list)
    tot = z1+z2+z3+z4+z5
    if tot == 0:
        print(f"  {label}: no HR data")
        return
    print(f"\n  {label} ({len(ride_list)} rides, {hm(tot)} HR time):")
    print(f"    Z1 100-129:  {hm(z1):>9}  {pct(z1,tot):>6}")
    print(f"    Z2 130-154:  {hm(z2):>9}  {pct(z2,tot):>6}")
    print(f"    Z3 155-165:  {hm(z3):>9}  {pct(z3,tot):>6}  [{z3/60:.0f} min]")
    print(f"    Z4 166-179:  {hm(z4):>9}  {pct(z4,tot):>6}  [{z4/60:.0f} min]")
    print(f"    Z5 180+:     {hm(z5):>9}  {pct(z5,tot):>6}  [{z5/60:.0f} min]")
    print(f"    ─────────────────────────────────────")
    print(f"    Z3+:         {hm(z3+z4+z5):>9}  {pct(z3+z4+z5,tot):>6}")
    print(f"    Z4+:         {hm(z4+z5):>9}  {pct(z4+z5,tot):>6}  (target ≥15%)")

hr_zone_report(rides,   "ALL RIDES COMBINED")
hr_zone_report(indoor,  "Indoor only")
hr_zone_report(out_pw,  "Outdoor + power meter")
hr_zone_report(out_nopw,"Outdoor, no power meter")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 3 — POWER ZONE DISTRIBUTION (per-second)")
print("  Both FTP=256W (Garmin manual) and FTP=235W (evidence-based estimate)")
print(SEP)

def pw_zone_report(ride_list, label, ftp_key="pw"):
    p1 = sum(r[f"{ftp_key}_z1_s"] for r in ride_list)
    p2 = sum(r[f"{ftp_key}_z2_s"] for r in ride_list)
    p3 = sum(r[f"{ftp_key}_z3_s"] for r in ride_list)
    p4 = sum(r[f"{ftp_key}_z4_s"] for r in ride_list)
    p5 = sum(r[f"{ftp_key}_z5_s"] for r in ride_list)
    p6 = sum(r[f"{ftp_key}_z6_s"] for r in ride_list)
    p7 = sum(r[f"{ftp_key}_z7_s"] for r in ride_list)
    tot = p1+p2+p3+p4+p5+p6+p7
    if tot == 0:
        return
    print(f"\n  {label} ({len([r for r in ride_list if r['has_power']])} power rides):")
    print(f"    P1 <141W   Recovery:   {hm(p1):>9}  {pct(p1,tot):>6}")
    print(f"    P2 141-192 Endurance:  {hm(p2):>9}  {pct(p2,tot):>6}")
    print(f"    P3 193-230 Tempo:      {hm(p3):>9}  {pct(p3,tot):>6}")
    print(f"    P4 231-268 Threshold:  {hm(p4):>9}  {pct(p4,tot):>6}  [{p4/60:.0f} min]")
    print(f"    P5 269-307 VO2max:     {hm(p5):>9}  {pct(p5,tot):>6}  [{p5/60:.0f} min]")
    print(f"    P6 308-384 Anaerobic:  {hm(p6):>9}  {pct(p6,tot):>6}")
    print(f"    P7 384+W   NM:         {hm(p7):>9}  {pct(p7,tot):>6}")
    p4plus = p4+p5+p6+p7
    print(f"    P4+:                   {hm(p4plus):>9}  {pct(p4plus,tot):>6}  [{p4plus/60:.0f} min total]")

pw_zone_report(pw_rides, "FTP=256W — All power rides")

# FTP=235 comparison
p4_256 = sum(r["pw_z4_s"]+r["pw_z5_s"]+r["pw_z6_s"]+r["pw_z7_s"] for r in pw_rides)
p4_235 = sum(r["pw235_z4_s"] for r in pw_rides)
ptot   = sum(r["pw_total_s"] for r in pw_rides)
print(f"\n  FTP comparison for P4+ (threshold+):")
print(f"    FTP=256W:  {p4_256/60:.0f} min  {pct(p4_256, ptot)} of total power time")
print(f"    FTP=235W:  {p4_235/60:.0f} min  {pct(p4_235, ptot)} of total power time")
print(f"    → The 256W FTP causes ~{(p4_235-p4_256)/60:.0f} min of threshold work to be")
print(f"      mis-classified as Tempo. At 235W, true P4+ is {pct(p4_235,ptot)}.")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 4 — MONTHLY HR Z4+Z5 MINUTES")
print(f"  {'Month':<9}  {'Z4+Z5 min':>10}  {'Z3+Z4+Z5 min':>13}  {'Z4%':>6}  {'rides':>6}")
print("  " + "─"*52)
print(SEP)

monthly = defaultdict(lambda: {"z3":0,"z4":0,"z5":0,"tot":0,"rides":0})
for r in rides:
    m = r["month"]
    monthly[m]["z3"]  += r["hr_z3_s"]
    monthly[m]["z4"]  += r["hr_z4_s"]
    monthly[m]["z5"]  += r["hr_z5_s"]
    monthly[m]["tot"] += r["hr_total_s"]
    monthly[m]["rides"] += 1

for m in sorted(monthly.keys()):
    d = monthly[m]
    z4m  = (d["z4"]+d["z5"]) / 60
    z3m  = (d["z3"]+d["z4"]+d["z5"]) / 60
    z4p  = 100*(d["z4"]+d["z5"]) / d["tot"] if d["tot"] else 0
    note = ""
    if m == "2026-04": note = " ← season peak"
    if m == "2026-08": note = " ← DIP"
    if m == "2026-09": note = " ← recovering"
    print(f"  {m}   {z4m:9.1f}   {z3m:12.1f}   {z4p:5.1f}%   {d['rides']:5}{note}")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 5 — PER-RIDE BREAKDOWN (all rides)")
print(f"  {'Date':<12} {'Name':<32} {'km':>5} {'m↑':>5} {'AvHR':>5} {'MxHR':>5} "
      f"{'Z3m':>5} {'Z4m':>5} {'Z5m':>5} {'NP':>5} {'20m':>5}")
print("  " + "─"*105)
print(SEP)

for r in rides:
    if r["hr_total_s"] < 120:
        continue
    z3m  = r["hr_z3_s"]/60
    z4m  = r["hr_z4_s"]/60
    z5m  = r["hr_z5_s"]/60
    np_s = str(r["np_w"]) if r["np_w"] else "-"
    p20  = str(r["pdc_20min"]) if r["pdc_20min"] else "-"
    ah   = f"{r['avg_hr']}" if r["avg_hr"] else "-"
    mh   = f"{r['max_hr']}" if r["max_hr"] else "-"
    nm   = (r.get("route_name") or f"{r['sub_sport']} {r['date_str']}")[:32]

    # Pull name from fit-analysis if available
    flag = ""
    if z4m >= 15: flag = " ◀◀Z4"
    elif z4m >= 5: flag = " ◀Z4"
    elif r["max_hr"] and r["max_hr"] >= 180: flag = " ↑Z5"

    print(f"  {r['date_str']:<12} {nm:<32} {r['distance_km']:>5.0f} {r['elevation_m']:>5.0f} "
          f"{ah:>5} {mh:>5} {z3m:>5.1f} {z4m:>5.1f} {z5m:>5.1f} "
          f"{np_s:>5} {p20:>5}{flag}")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 6 — TOP 20 RIDES BY HR Z4+Z5 MINUTES")
print(SEP)

top20 = sorted(rides, key=lambda r: r["hr_z4_s"]+r["hr_z5_s"], reverse=True)[:20]
for i, r in enumerate(top20, 1):
    z3m = r["hr_z3_s"]/60
    z4m = r["hr_z4_s"]/60
    z5m = r["hr_z5_s"]/60
    np_s = f"NP={r['np_w']}W" if r["np_w"] else "no power"
    nm = r.get("route_name") or r["sub_sport"]
    print(f"  {i:2}. {r['date_str']}  {nm[:38]:<38}  "
          f"Z3:{z3m:5.1f}m  Z4:{z4m:5.1f}m  Z5:{z5m:4.1f}m  "
          f"maxHR={r['max_hr'] or '-'}  {np_s}")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 7 — 20-MIN PDC PROGRESSION (outdoor power rides, chronological)")
print(SEP)

pdc_list = [(r["date_str"], r["pdc_20min"], r.get("route_name",""), r["np_w"])
            for r in rides if r["pdc_20min"] and r["has_power"] and not r["is_indoor"]]
pdc_list.sort()
prev = None
for d, w, nm, np in pdc_list:
    delta = f"(+{w-prev})" if prev else ""
    bar = "▓" * max(0, int((w-150)/3))
    print(f"  {d}  {w:>3}W {delta:>6}  {bar}  {nm[:35]}")
    prev = w

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 8 — AEROBIC COUPLING / HR DRIFT (power rides >60min)")
print("  Positive drift = decoupling (HR rising relative to power).")
print("  Negative or near-0 = well coupled.")
print(SEP)

drift_list = [(r["date_str"], r.get("route_name",""), r["hr_drift_pct"], r["np_w"], r["avg_hr"])
              for r in rides if r["hr_drift_pct"] is not None]
drift_list.sort()
for d, nm, drift, np, ah in drift_list:
    np_s = f"NP={np}W" if np else ""
    ah_s = f"avgHR={ah}" if ah else ""
    interp = "well-coupled ✓" if abs(drift) < 5 else ("moderate" if abs(drift) < 15 else "decoupled ⚠")
    print(f"  {d}  {nm[:32]:<32}  drift={drift:+6.1f}%  {interp:<18}  {np_s}  {ah_s}")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 9 — AEROBIC EFFICIENCY (NP/avg_HR W/bpm, outdoor hilly rides)")
print(SEP)

eff_list = [(r["aerobic_efficiency"], r["date_str"], r.get("route_name",""),
             r["np_w"], r["avg_hr"])
            for r in out_pw if r["aerobic_efficiency"] and r["elevation_m"] > 100]
eff_list.sort(reverse=True)

for eff, d, nm, np, ah in eff_list[:20]:
    bar = "▓" * int(eff * 5)
    print(f"  {d}  {nm[:32]:<32}  {eff:.3f} W/bpm  NP={np}W  avgHR={ah}  {bar}")

if eff_list:
    avg_eff = sum(e[0] for e in eff_list) / len(eff_list)
    print(f"\n  Season avg: {avg_eff:.3f} W/bpm  (n={len(eff_list)} hilly rides)")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 10 — RECENT 30 DAYS: FULL PER-RIDE DETAIL (Aug 25 → Sep 24)")
print(SEP)

cutoff = datetime(2026, 8, 25)
recent = sorted([r for r in rides if r["date"] >= cutoff], key=lambda r: r["date"])

for r in recent:
    z3m = r["hr_z3_s"]/60
    z4m = r["hr_z4_s"]/60
    z5m = r["hr_z5_s"]/60
    pw_s = f"NP={r['np_w']}W  PDC20={r['pdc_20min']}W" if r["has_power"] else "no power"
    drift_s = f"drift={r['hr_drift_pct']:+.1f}%" if r["hr_drift_pct"] is not None else ""
    nm = r.get("route_name") or r["sub_sport"]
    te_s = ""
    if r["te_aerobic"]:
        te_s = f"TE={r['te_aerobic']:.1f}a/{r['te_anaerobic']:.1f}an" if r["te_anaerobic"] else f"TE={r['te_aerobic']:.1f}"
    print(f"\n  {r['date_str']}  {nm}")
    print(f"    {r['distance_km']:.0f}km · {r['elevation_m']:.0f}m · "
          f"avgHR={r['avg_hr'] or '-'} · maxHR={r['max_hr'] or '-'} · "
          f"temp={r['avg_temp_c'] or '-'}°C")
    print(f"    Z3:{z3m:.1f}m · Z4:{z4m:.1f}m · Z5:{z5m:.1f}m · {pw_s} · {drift_s} {te_s}")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("SECTION 11 — DIAGNOSIS SUMMARY")
print(SEP)

# Overall
tot_hr = sum(r["hr_total_s"] for r in rides)
z4_all = sum(r["hr_z4_s"]+r["hr_z5_s"] for r in rides)
z3_all = sum(r["hr_z3_s"] for r in rides)

# Last ride with >60s Z4
z4_rides = sorted(
    [r for r in rides if r["hr_z4_s"]+r["hr_z5_s"] > 60],
    key=lambda r: r["date"]
)
last_z4 = z4_rides[-1] if z4_rides else None

# Best PDC
best20 = max((r["pdc_20min"] for r in rides if r["pdc_20min"]), default=None)
best20_r = next((r for r in sorted(rides, key=lambda x: -(x["pdc_20min"] or 0)) if r["pdc_20min"]==best20), None)
best5  = max((r["pdc_5min"] for r in rides if r["pdc_5min"]), default=None)
best10 = max((r["pdc_10min"] for r in rides if r["pdc_10min"]), default=None)

# Sep stats
sep_rides = [r for r in rides if r["month"] == "2026-09"]
sep_z4m = sum(r["hr_z4_s"]+r["hr_z5_s"] for r in sep_rides) / 60

# Current week
cur_rides = [r for r in rides if r["date"] >= datetime(2026,9,18)]
cur_z4m = sum(r["hr_z4_s"]+r["hr_z5_s"] for r in cur_rides)/60

print(f"\n  ── HR Zone Truth ────────────────────────────────────")
print(f"  Total HR time analysed:     {hm(tot_hr)}")
print(f"  Z4+Z5 all-time:             {z4_all/60:.0f} min  ({100*z4_all/tot_hr:.1f}%)")
print(f"  Z3 all-time:                {z3_all/60:.0f} min  ({100*z3_all/tot_hr:.1f}%)")
print(f"  Z3+ combined:               {(z3_all+z4_all)/60:.0f} min  ({100*(z3_all+z4_all)/tot_hr:.1f}%)")
print(f"  Target Z4+ %:               ≥15%  ← current gap: {15 - 100*z4_all/tot_hr:.1f}pp")

print(f"\n  ── Z4 Recency ───────────────────────────────────────")
if last_z4:
    z4m_last = (last_z4["hr_z4_s"]+last_z4["hr_z5_s"])/60
    days_ago = (datetime(2026,9,24) - last_z4["date"]).days
    print(f"  Last ride with >1min Z4:    {last_z4['date_str']} ({days_ago} days ago)")
    print(f"    → {last_z4.get('route_name','')}  Z4:{z4m_last:.0f}min  maxHR={last_z4['max_hr']}")
print(f"  Sep 2026 Z4+Z5 total:       {sep_z4m:.0f} min")
print(f"  Current week (Sep18-24):    {cur_z4m:.0f} min Z4+Z5")

print(f"\n  ── Power Duration Curve (season bests) ──────────────")
print(f"  5-min best:   {best5}W")
print(f"  10-min best:  {best10}W")
print(f"  20-min best:  {best20}W  on {best20_r['date_str'] if best20_r else '?'}")
if best20:
    print(f"    → FTP estimate (×0.95): {round(best20*0.95)}W")
    print(f"    → FTP estimate (15-min climb method): ~235W")
    print(f"    → Garmin manual entry: 256W (never tested via ramp/20-min test)")

print(f"\n  ── Action Items ─────────────────────────────────────")
print(f"  1. Z4 is at {100*z4_all/tot_hr:.1f}% — need ~{15-100*z4_all/tot_hr:.0f}pp more to hit 15% target")
print(f"  2. Thu Week1 (today) already Z3 — on track")
print(f"  3. Correct interval targets use FTP~235W:")
print(f"     Z3 Tempo: 176-212W  |  Z4 Threshold: 212-247W  |  Z5 VO2max: 247-282W")
print(f"  4. Schedule a dedicated 20-min climb test when a 22+ min climb is available")

print(f"\n{'═'*74}")
print("✓ Raw FIT analysis complete.")
