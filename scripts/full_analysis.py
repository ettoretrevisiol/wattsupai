#!/usr/bin/env python3
"""
Full season analysis — uses only local data (no Garmin API calls).

Sources:
  data/activities.json        → pre-processed metadata per ride
  data/seconds/*.json         → per-second HR + power zone totals (GROUND TRUTH)
  data/fit-analysis/*.json    → NP, PDC, laps, HR drift, shifting

HR zones:  Z1 100-129 | Z2 130-154 | Z3 155-165 | Z4 166-179 | Z5 180+
Power FTP 256W: P1<141 | P2 141-192 | P3 193-230 | P4 231-268 | P5 269-307 | P6 308-384 | P7 384+
"""

import json, os, glob
from collections import defaultdict
from datetime import datetime

BASE = "/Users/ettoretr/Documents/wattsupai/data"

# ── Load all three data sources ───────────────────────────────────────────────
with open(f"{BASE}/activities.json") as f:
    raw = json.load(f)
acts_meta = {str(a["id"]): a for a in raw.get("activities", [])}

seconds_data = {}
for fp in glob.glob(f"{BASE}/seconds/*.json"):
    aid = os.path.basename(fp).replace(".json", "")
    with open(fp) as fh:
        seconds_data[aid] = json.load(fh)

fit_analysis = {}
for fp in glob.glob(f"{BASE}/fit-analysis/*.json"):
    if "README" in fp:
        continue
    aid = os.path.basename(fp).replace(".json", "")
    with open(fp) as fh:
        try:
            fit_analysis[aid] = json.load(fh)
        except:
            pass

# ── Build unified ride list ───────────────────────────────────────────────────
all_ids = set(acts_meta) | set(seconds_data) | set(fit_analysis)

rides = []
for aid in all_ids:
    meta = acts_meta.get(aid, {})
    sec  = seconds_data.get(aid, {})
    fit  = fit_analysis.get(aid, {})

    date_str = fit.get("date") or meta.get("date", "")
    if not date_str:
        continue
    try:
        date = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except:
        continue

    # HR zone seconds from per-second data (ground truth)
    hr_z = sec.get("hr_time_in_zone_s", {})
    hr_total_s = sum(hr_z.values()) if hr_z else 0

    # Power zone seconds from per-second data
    pw_z = sec.get("power_time_in_zone_s", {})
    pw_total_s = sum(pw_z.values()) if pw_z else 0

    # session-level from fit-analysis
    session = fit.get("session", {})
    np_w = session.get("np_w")
    avg_power = session.get("avg_power_w") or sec.get("power_mean")
    max_power = session.get("max_power_w") or sec.get("power_max")
    avg_hr = session.get("avg_hr_bpm") or sec.get("hr_mean") or meta.get("avg_hr")
    max_hr = session.get("max_hr_bpm") or sec.get("hr_max") or meta.get("max_hr")
    elevation = session.get("total_ascent_m") or meta.get("elevation_m", 0)
    distance_km = (session.get("total_distance_m") or 0) / 1000 or meta.get("distance_km", 0)
    calories = session.get("total_calories") or meta.get("calories")

    has_power = pw_total_s > 0 or (meta.get("has_power_meter") is True) or (avg_power and avg_power > 5)

    route_name = fit.get("route_name") or meta.get("name", "")
    activity_type = fit.get("sub_sport") or meta.get("type", "")
    te_label = meta.get("training_effect_label") or ""
    training_load = meta.get("training_load")

    pdc = fit.get("pdc", {})
    hr_drift = fit.get("hr_drift", {})
    shift = fit.get("shift_summary", {})
    laps_raw = fit.get("laps_hr_raw", [])

    rides.append({
        "aid": aid,
        "date": date,
        "date_str": date_str[:10],
        "month": date_str[:7],
        "route_name": route_name,
        "activity_type": activity_type,
        "distance_km": distance_km,
        "elevation_m": elevation or 0,
        "calories": calories,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        # Per-second HR zones (ground truth)
        "hr_z1_s": hr_z.get("z1", 0),
        "hr_z2_s": hr_z.get("z2", 0),
        "hr_z3_s": hr_z.get("z3", 0),
        "hr_z4_s": hr_z.get("z4", 0),
        "hr_z5_s": hr_z.get("z5", 0),
        "hr_total_s": hr_total_s,
        # Per-second power zones (ground truth)
        "has_power": has_power,
        "pw_z1_s": pw_z.get("p1", 0),
        "pw_z2_s": pw_z.get("p2", 0),
        "pw_z3_s": pw_z.get("p3", 0),
        "pw_z4_s": pw_z.get("p4", 0),
        "pw_z5_s": pw_z.get("p5", 0),
        "pw_z6_s": pw_z.get("p6", 0),
        "pw_z7_s": pw_z.get("p7", 0),
        "pw_total_s": pw_total_s,
        # Session metrics
        "np_w": np_w,
        "avg_power": avg_power,
        "max_power": max_power,
        # PDC
        "pdc_5s": pdc.get("5s"),
        "pdc_5min": pdc.get("5min"),
        "pdc_10min": pdc.get("10min"),
        "pdc_20min": pdc.get("20min"),
        "pdc_60min": pdc.get("60min"),
        # Aerobic coupling
        "hr_drift_pct": hr_drift.get("hr_drift_pct"),
        "hr_drift_interp": hr_drift.get("interpretation"),
        # Labels
        "te_label": te_label,
        "training_load": training_load,
        # Shifting
        "proactive_pct": shift.get("proactive_pct"),
        # Laps
        "laps_raw": laps_raw,
        "best_climbing_laps": fit.get("best_climbing_laps", []),
    })

rides.sort(key=lambda r: r["date"])

# ── Helper functions ──────────────────────────────────────────────────────────
def pct(n, total): return f"{100*n/total:.1f}%" if total > 0 else "N/A"
def hm(s):
    s = int(s)
    return f"{s//3600}h {(s%3600)//60:02d}m"

sep = "═" * 72

# ═══════════════════════════════════════════════════════════════════════════════
print(sep)
print("SECTION 1 — SEASON OVERVIEW")
print(sep)

total_rides = len(rides)
total_dist = sum(r["distance_km"] for r in rides)
total_elev = sum(r["elevation_m"] for r in rides)
total_cal  = sum(r["calories"] or 0 for r in rides)
hr_grand_s = sum(r["hr_total_s"] for r in rides)
pw_grand_s = sum(r["pw_total_s"] for r in rides)

indoor_rides    = [r for r in rides if "indoor" in r["activity_type"].lower()]
outdoor_rides   = [r for r in rides if "indoor" not in r["activity_type"].lower()]
power_rides     = [r for r in rides if r["has_power"]]
no_power_rides  = [r for r in rides if not r["has_power"]]

date_range = f"{rides[0]['date_str']} → {rides[-1]['date_str']}"

print(f"Date range:          {date_range}")
print(f"Total rides:         {total_rides}")
print(f"  Indoor (trainer):  {len(indoor_rides)}")
print(f"  Outdoor:           {len(outdoor_rides)}")
print(f"    With power:      {len([r for r in outdoor_rides if r['has_power']])}")
print(f"    Without power:   {len([r for r in outdoor_rides if not r['has_power']])}")
print(f"Total distance:      {total_dist:.0f} km")
print(f"Total elevation:     {total_elev:.0f} m")
print(f"Total calories:      {total_cal:.0f} kcal")
print(f"HR-tracked time:     {hm(hr_grand_s)}")
print(f"Power-tracked time:  {hm(pw_grand_s)}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 2 — HR ZONE DISTRIBUTION (per-second, ALL rides combined)")
print(sep)

z1 = sum(r["hr_z1_s"] for r in rides)
z2 = sum(r["hr_z2_s"] for r in rides)
z3 = sum(r["hr_z3_s"] for r in rides)
z4 = sum(r["hr_z4_s"] for r in rides)
z5 = sum(r["hr_z5_s"] for r in rides)
tot = z1+z2+z3+z4+z5

print(f"  Z1 100-129 bpm:  {hm(z1):>10}  {pct(z1,tot):>6}  [{z1/60:.0f} min]")
print(f"  Z2 130-154 bpm:  {hm(z2):>10}  {pct(z2,tot):>6}  [{z2/60:.0f} min]")
print(f"  Z3 155-165 bpm:  {hm(z3):>10}  {pct(z3,tot):>6}  [{z3/60:.0f} min]")
print(f"  Z4 166-179 bpm:  {hm(z4):>10}  {pct(z4,tot):>6}  [{z4/60:.0f} min]")
print(f"  Z5 180+ bpm:     {hm(z5):>10}  {pct(z5,tot):>6}  [{z5/60:.0f} min]")
print(f"  TOTAL:           {hm(tot):>10}")
print(f"\n  Z3+:  {hm(z3+z4+z5):>10}  {pct(z3+z4+z5,tot):>6}")
print(f"  Z4+:  {hm(z4+z5):>10}  {pct(z4+z5,tot):>6}  (target: ≥15%)")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 3 — HR ZONE BREAKDOWN BY CATEGORY")
print(sep)

def zone_stats_hr(ride_list, label):
    z1 = sum(r["hr_z1_s"] for r in ride_list)
    z2 = sum(r["hr_z2_s"] for r in ride_list)
    z3 = sum(r["hr_z3_s"] for r in ride_list)
    z4 = sum(r["hr_z4_s"] for r in ride_list)
    z5 = sum(r["hr_z5_s"] for r in ride_list)
    tot = z1+z2+z3+z4+z5
    if tot == 0:
        return
    print(f"\n  {label} ({len(ride_list)} rides, {hm(tot)} HR):")
    print(f"    Z1:{pct(z1,tot):>6}  Z2:{pct(z2,tot):>6}  Z3:{pct(z3,tot):>6}  "
          f"Z4:{pct(z4,tot):>6}  Z5:{pct(z5,tot):>6}")
    print(f"    Z4+: {pct(z4+z5,tot):>6}  =  {(z4+z5)/60:.0f} min  "
          f"Z3+: {pct(z3+z4+z5,tot):>6}  =  {(z3+z4+z5)/60:.0f} min")

zone_stats_hr(rides, "ALL RIDES")
zone_stats_hr(indoor_rides, "Indoor only")
zone_stats_hr(outdoor_rides, "Outdoor only")
zone_stats_hr(power_rides, "All with power")
zone_stats_hr(no_power_rides, "All without power")
zone_stats_hr([r for r in outdoor_rides if r["has_power"]], "Outdoor + power meter")
zone_stats_hr([r for r in outdoor_rides if not r["has_power"]], "Outdoor, no power meter")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 4 — POWER ZONE DISTRIBUTION (per-second, all power rides)")
print("  FTP=256W: P1<141 | P2 141-192 | P3 193-230 | P4 231-268 | P5 269-307 | P6 308-384 | P7 384+")
print(sep)

p1 = sum(r["pw_z1_s"] for r in rides)
p2 = sum(r["pw_z2_s"] for r in rides)
p3 = sum(r["pw_z3_s"] for r in rides)
p4 = sum(r["pw_z4_s"] for r in rides)
p5 = sum(r["pw_z5_s"] for r in rides)
p6 = sum(r["pw_z6_s"] for r in rides)
p7 = sum(r["pw_z7_s"] for r in rides)
ptot = p1+p2+p3+p4+p5+p6+p7

print(f"  P1 <141W   (Recovery):    {hm(p1):>10}  {pct(p1,ptot):>6}")
print(f"  P2 141-192W (Endurance):  {hm(p2):>10}  {pct(p2,ptot):>6}")
print(f"  P3 193-230W (Tempo):      {hm(p3):>10}  {pct(p3,ptot):>6}")
print(f"  P4 231-268W (Threshold):  {hm(p4):>10}  {pct(p4,ptot):>6}")
print(f"  P5 269-307W (VO2max):     {hm(p5):>10}  {pct(p5,ptot):>6}")
print(f"  P6 308-384W (Anaerobic):  {hm(p6):>10}  {pct(p6,ptot):>6}")
print(f"  P7 384+W    (NM):         {hm(p7):>10}  {pct(p7,ptot):>6}")
print(f"  TOTAL:                    {hm(ptot):>10}")
print(f"\n  P4+ (threshold+): {hm(p4+p5+p6+p7):>10}  {pct(p4+p5+p6+p7,ptot):>6}  "
      f"({(p4+p5+p6+p7)/60:.0f} min total)")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 5 — MONTHLY HR Z4+Z5 MINUTES (per-second, all rides)")
print(sep)

monthly = defaultdict(lambda: {"z3_s":0,"z4_s":0,"z5_s":0,"tot_s":0,"rides":0,"pw_z4_s":0,"pw_tot_s":0})
for r in rides:
    m = r["month"]
    monthly[m]["z3_s"]    += r["hr_z3_s"]
    monthly[m]["z4_s"]    += r["hr_z4_s"]
    monthly[m]["z5_s"]    += r["hr_z5_s"]
    monthly[m]["tot_s"]   += r["hr_total_s"]
    monthly[m]["rides"]   += 1
    monthly[m]["pw_z4_s"] += r["pw_z4_s"] + r["pw_z5_s"] + r["pw_z6_s"] + r["pw_z7_s"]
    monthly[m]["pw_tot_s"]+= r["pw_total_s"]

print(f"  {'Month':<8}  {'Z4+Z5 min':>10}  {'Z3+Z4+Z5 min':>13}  "
      f"{'Z4% HR':>7}  {'PwrZ4 min':>10}  {'PwrZ4%':>7}  {'Rides':>6}")
print("  " + "-"*70)
for m in sorted(monthly.keys()):
    d = monthly[m]
    z4m = (d["z4_s"] + d["z5_s"]) / 60
    z3m = (d["z3_s"] + d["z4_s"] + d["z5_s"]) / 60
    z4pct = 100 * (d["z4_s"]+d["z5_s"]) / d["tot_s"] if d["tot_s"] > 0 else 0
    pw4m = d["pw_z4_s"] / 60
    pw4pct = 100 * d["pw_z4_s"] / d["pw_tot_s"] if d["pw_tot_s"] > 0 else 0
    pw_str = f"{pw4m:9.1f}" if d["pw_tot_s"] > 0 else "         -"
    pw_pct_str = f"{pw4pct:6.1f}%" if d["pw_tot_s"] > 0 else "      -"
    peak_flag = " ← peak" if m == "2026-04" else ""
    dip_flag = " ← DIP" if m in ("2026-08",) else ""
    print(f"  {m}  {z4m:9.1f}  {z3m:12.1f}  {z4pct:6.1f}%  {pw_str}  {pw_pct_str}  {d['rides']:6}{peak_flag}{dip_flag}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 6 — PER-RIDE BREAKDOWN (all rides, sorted by date)")
print(f"  {'Date':<12} {'Route':<32} {'km':>5} {'m↑':>5} {'AvHR':>5} {'MxHR':>5} "
      f"{'Z3m':>5} {'Z4m':>5} {'Z5m':>5} {'NP':>5} {'20m':>5} {'TE'}")
print("  " + "-"*115)
print(sep)

for r in rides:
    if r["hr_total_s"] < 120:
        continue
    z3m = r["hr_z3_s"] / 60
    z4m = r["hr_z4_s"] / 60
    z5m = r["hr_z5_s"] / 60
    np_s = str(r["np_w"]) if r["np_w"] else "-"
    p20_s = str(r["pdc_20min"]) if r["pdc_20min"] else "-"
    te_s = (r["te_label"] or "-")[:18]
    route = (r["route_name"] or r["activity_type"] or "-")[:32]
    ah = f"{r['avg_hr']:.0f}" if r["avg_hr"] else "-"
    mh = f"{r['max_hr']:.0f}" if r["max_hr"] else "-"
    flag = ""
    if z4m >= 15: flag = " ◀◀ Z4"
    elif z4m >= 5: flag = " ◀ Z4"
    elif z4m >= 1: flag = " · Z4"
    print(f"  {r['date_str']:<12} {route:<32} {r['distance_km']:>5.0f} {r['elevation_m']:>5.0f} "
          f"{ah:>5} {mh:>5} {z3m:>5.1f} {z4m:>5.1f} {z5m:>5.1f} "
          f"{np_s:>5} {p20_s:>5} {te_s}{flag}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 7 — TOP 20 RIDES BY HR Z4 MINUTES")
print(sep)

top_z4 = sorted(rides, key=lambda r: r["hr_z4_s"]+r["hr_z5_s"], reverse=True)[:20]
for r in top_z4:
    z3m = r["hr_z3_s"]/60
    z4m = r["hr_z4_s"]/60
    z5m = r["hr_z5_s"]/60
    np_s = f"NP={r['np_w']}W" if r["np_w"] else ""
    te_s = r["te_label"] or ""
    print(f"  {r['date_str']}  {r['route_name'][:35]:<35}  "
          f"Z3:{z3m:5.1f}  Z4:{z4m:5.1f}  Z5:{z5m:4.1f}  maxHR={r['max_hr'] or '-'}  "
          f"{np_s}  {te_s}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 8 — 20-MIN PDC PROGRESSION (outdoor power rides)")
print(sep)

pdc_rides = [(r["date_str"], r["pdc_20min"], r["route_name"])
             for r in rides if r["pdc_20min"] and r["has_power"]]
pdc_rides.sort()
for d, w, name in pdc_rides:
    bar = "▓" * int((w - 150) / 3) if w > 150 else ""
    print(f"  {d}  {w:>3}W  {bar}  {name[:35]}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 9 — HR COUPLING (drift %, outdoor power rides)")
print("  well_coupled <10% | moderate 10-20% | significant >20%")
print(sep)

drift_rides = [(r["date_str"], r["route_name"], r["hr_drift_pct"],
                r["hr_drift_interp"], r["np_w"])
               for r in rides if r["hr_drift_pct"] is not None and r["has_power"]]
drift_rides.sort()
for d, name, drift, interp, np in drift_rides:
    np_s = f"NP={np}W" if np else ""
    flag = " ✓" if interp == "well_coupled" else (" ⚠" if interp and "significant" in interp else "")
    print(f"  {d}  {name[:32]:<32}  drift={drift:+5.1f}%  {str(interp):<28}  {np_s}{flag}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 10 — AEROBIC EFFICIENCY (NP/avg_HR, W/bpm, outdoor power rides)")
print(sep)

eff_list = []
for r in rides:
    if r["np_w"] and r["avg_hr"] and r["avg_hr"] > 100 and r["has_power"] and r["elevation_m"] > 50:
        eff = r["np_w"] / r["avg_hr"]
        eff_list.append((eff, r["date_str"], r["route_name"], r["np_w"], r["avg_hr"]))

eff_list.sort(reverse=True)
for eff, d, name, np, ah in eff_list[:20]:
    bar = "▓" * int(eff * 5)
    print(f"  {d}  {name[:32]:<32}  {eff:.3f} W/bpm  NP={np}W  avgHR={ah:.0f}  {bar}")

if eff_list:
    avg_eff = sum(e[0] for e in eff_list) / len(eff_list)
    best = eff_list[0]
    print(f"\n  Season avg: {avg_eff:.3f} W/bpm  |  Best: {best[0]:.3f} on {best[1]}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 11 — BEST CLIMBING LAPS (NP-ranked)")
print(sep)

all_laps = []
for r in rides:
    for lap in r["best_climbing_laps"]:
        np_val = lap.get("np_w") or lap.get("avg_power_w") or 0
        all_laps.append({
            "date": r["date_str"],
            "route": r["route_name"],
            "lap": lap.get("lap"),
            "np_w": np_val,
            "avg_w": lap.get("avg_power_w"),
            "hr": lap.get("avg_hr_bpm"),
            "asc": lap.get("ascent_m"),
            "notes": lap.get("notes",""),
        })

all_laps.sort(key=lambda l: -(l["np_w"] or 0))
print(f"  {'Date':<12} {'Route':<30} {'Lap':>4} {'NP':>5} {'AvgW':>5} {'HR':>5} {'Asc':>5}  Notes")
print("  " + "-"*90)
for l in all_laps[:25]:
    np_s = str(l["np_w"]) if l["np_w"] else "-"
    aw_s = str(l["avg_w"]) if l["avg_w"] else "-"
    hr_s = str(l["hr"]) if l["hr"] else "-"
    asc_s = str(l["asc"]) if l["asc"] else "-"
    print(f"  {l['date']:<12} {l['route'][:28]:<28} L{str(l['lap']):<3} "
          f"{np_s:>5} {aw_s:>5} {hr_s:>5} {asc_s:>5}  {l['notes'][:30]}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 12 — NO-POWER RIDES: LAP-LEVEL HR INTENSITY")
print("  All rides where ≥1 lap avg HR ≥155bpm (Z3+)")
print(sep)

no_pw_rides = [r for r in rides if not r["has_power"] and r["laps_raw"]]
no_pw_rides.sort(key=lambda r: r["date"])

z3_count = 0
z4_count = 0
for r in no_pw_rides:
    laps = [l for l in r["laps_raw"] if isinstance(l, (list,tuple)) and len(l) >= 2]
    if not laps:
        continue
    peak = max(l[1] for l in laps)
    n_z3 = sum(1 for l in laps if l[1] >= 155)
    n_z4 = sum(1 for l in laps if l[1] >= 166)
    if peak >= 155:
        z3_count += 1
        if peak >= 166:
            z4_count += 1
        flag = " ◀◀" if n_z4 >= 3 else (" ◀" if n_z4 >= 1 else "")
        print(f"  {r['date_str']}  {r['route_name'][:32]:<32}  "
              f"peak={peak:>3}bpm  Z3laps={n_z3}  Z4laps={n_z4}{flag}")

print(f"\n  No-power rides total:         {len(no_pw_rides)}")
print(f"  Rides with ≥1 lap ≥Z3 (155+): {z3_count} ({100*z3_count/max(len(no_pw_rides),1):.0f}%)")
print(f"  Rides with ≥1 lap ≥Z4 (166+): {z4_count} ({100*z4_count/max(len(no_pw_rides),1):.0f}%)")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 13 — SHIFTING QUALITY PROGRESSION")
print(sep)

shift_list = [(r["date_str"], r["route_name"], r["proactive_pct"])
              for r in rides if r["proactive_pct"] is not None]
shift_list.sort()

monthly_shift = defaultdict(list)
for d, name, p in shift_list:
    monthly_shift[d[:7]].append(p)
    bar = "▓" * int(p/3)
    print(f"  {d}  {name[:32]:<32}  proactive={p:.1f}%  {bar}")

print("\n  Monthly averages:")
for m in sorted(monthly_shift.keys()):
    vals = monthly_shift[m]
    avg = sum(vals)/len(vals)
    print(f"    {m}  avg={avg:.1f}%  (n={len(vals)})")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 14 — RECENT 30 DAYS DETAIL (Aug 25 → Sep 24 2026)")
print(sep)

cutoff = datetime(2026, 8, 25)
recent = [r for r in rides if r["date"] >= cutoff]
recent.sort(key=lambda r: r["date"])

for r in recent:
    z3m = r["hr_z3_s"]/60
    z4m = r["hr_z4_s"]/60
    z5m = r["hr_z5_s"]/60
    np_s = f"NP={r['np_w']}W" if r["np_w"] else "no-power"
    p20_s = f"PDC20={r['pdc_20min']}W" if r["pdc_20min"] else ""
    drift_s = f"drift={r['hr_drift_pct']:+.1f}%" if r["hr_drift_pct"] is not None else ""
    te_s = r["te_label"] or ""
    print(f"\n  {r['date_str']}  {r['route_name']}")
    print(f"    {r['distance_km']:.0f}km · {r['elevation_m']:.0f}m · "
          f"avgHR={r['avg_hr'] or '-'} · maxHR={r['max_hr'] or '-'}")
    print(f"    Z3:{z3m:.1f}m · Z4:{z4m:.1f}m · Z5:{z5m:.1f}m · {np_s} · {p20_s} · {drift_s}")
    if te_s:
        print(f"    TE: {te_s}")
    if r["laps_raw"]:
        laps = [l for l in r["laps_raw"] if isinstance(l,(list,tuple)) and len(l)>=2]
        if laps:
            peak = max(l[1] for l in laps)
            nz3 = sum(1 for l in laps if l[1]>=155)
            nz4 = sum(1 for l in laps if l[1]>=166)
            print(f"    lap peak={peak}bpm · Z3-laps={nz3} · Z4-laps={nz4}")

# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{sep}")
print("SECTION 15 — SUMMARY DIAGNOSIS")
print(sep)

# Compute key numbers
total_z4_min = (z4 + z5) / 60
total_z4_pct = 100*(z4+z5)/tot if tot else 0

# Last Z4 ride
z4_rides_list = sorted(
    [(r["date_str"], r["route_name"], (r["hr_z4_s"]+r["hr_z5_s"])/60)
     for r in rides if r["hr_z4_s"]+r["hr_z5_s"] > 60],
    key=lambda x: x[0]
)
last_z4_ride = z4_rides_list[-1] if z4_rides_list else None

# Best 20min PDC
best_pdc = max((r["pdc_20min"] for r in rides if r["pdc_20min"]), default=None)
best_pdc_date = next((r["date_str"] for r in sorted(rides,key=lambda r: -(r["pdc_20min"] or 0)) if r["pdc_20min"]==best_pdc), None)

# Sep 2026 Z4
sep_rides = [r for r in rides if r["month"] == "2026-09"]
sep_z4_min = sum(r["hr_z4_s"]+r["hr_z5_s"] for r in sep_rides) / 60

print(f"  Total HR-tracked time:         {hm(tot)}")
print(f"  Z4+Z5 all-time:                {total_z4_min:.0f} min  ({total_z4_pct:.1f}%)")
print(f"  Target Z4+ %:                  ≥15%  ← gap: {15-total_z4_pct:.1f}pp")
print(f"  Last ride with >1min Z4:       {last_z4_ride[0] if last_z4_ride else 'none'} ({last_z4_ride[1] if last_z4_ride else ''}, {last_z4_ride[2]:.0f}min Z4)")
print(f"  Sep 2026 Z4+Z5 so far:         {sep_z4_min:.0f} min")
print(f"  Season best 20-min PDC:        {best_pdc}W on {best_pdc_date}")
print(f"")
print(f"  FTP note: 256W (Garmin manual). Evidence from Sep 19 15-min climb")
print(f"  suggests true FTP ~235W (15-min best 261W × 0.90). Use 235W for intervals.")

print(f"\n{'═'*72}")
print("✓ Analysis complete.")
