#!/usr/bin/env python3
"""
WattsUpAI Activity Database Builder
Fetches full details for all 186 activities from Garmin Connect
and builds activities.json for instant offline analysis.

Usage: python3 build_db.py
Requires: garminconnect installed and authenticated (~/.garminconnect tokens)
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime

try:
    from garminconnect import Garmin
except ImportError:
    print("Installing garminconnect...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "garminconnect", "--quiet"])
    from garminconnect import Garmin

# ── CONFIG ──────────────────────────────────────────────────────────────────
OUT_FILE = Path(__file__).parent / "activities.json"
TOKEN_DIR = Path.home() / ".garminconnect"
FTP = 256  # W — confirmed from Garmin, updated Sep 12 2026

# Power zones based on FTP 256W (Garmin standard percentages)
POWER_ZONES = {
    1: (0,     int(0.55 * FTP)),   # Recovery
    2: (int(0.55 * FTP), int(0.75 * FTP)),  # Endurance
    3: (int(0.75 * FTP), int(0.90 * FTP)),  # Tempo
    4: (int(0.90 * FTP), int(1.05 * FTP)),  # Threshold
    5: (int(1.05 * FTP), int(1.20 * FTP)),  # VO2max
    6: (int(1.20 * FTP), int(1.50 * FTP)),  # Anaerobic
    7: (int(1.50 * FTP), 9999),             # Neuromuscular
}

# HR zones (confirmed from Garmin)
HR_ZONES = {1: 100, 2: 130, 3: 155, 4: 166, 5: 180}

# ── ACTIVITY LIST (all 186, Sep 2025 - Sep 2026) ────────────────────────────
ACTIVITIES = [
    # id, date, name, type (road/indoor/virtual), has_powermeter
    (24465495850,"2026-09-23","Milano - Abbiategrasso","road",False),
    (24439888804,"2026-09-21","Milano - Abbiategrasso","road",False),
    (24430453668,"2026-09-20","Milano - Tornavento","road",False),
    (24419641071,"2026-09-19","Tre Valli Varesine","road",True),
    (24398797496,"2026-09-17","Milano - Morimondo","road",False),
    (24366303080,"2026-09-15","Milano - Abbiategrasso","road",False),
    (24344106906,"2026-09-13","Milano - Tornavento","road",False),
    (24332535841,"2026-09-12","Lecco - Culmine - Taleggio","road",True),
    (24312869222,"2026-09-10","Milano - Mairano - Abbiategrasso","road",False),
    (24280099291,"2026-09-08","Milano - Abbiategrasso","road",False),
    (24258570508,"2026-09-06","Como - Nesso - Ghisallino Power","road",True),
    (24245491818,"2026-09-05","Lecco - Agueglio - Morterone","road",True),
    (24219542914,"2026-09-03","Milano - Abbiategrasso","road",False),
    (24192593959,"2026-09-01","Milano - Cassinetta","road",False),
    (24170541318,"2026-08-30","Ara - Forgaria - Versegnis - Cavazzo","road",True),
    (24157928844,"2026-08-29","Ara - San Daniele - Fagagna - Sedilis","road",True),
    (24132511348,"2026-08-27","Ara - Attimis - Povoletto","road",True),
    (24113456628,"2026-08-25","Ara - Fagagna - Tavagnacco","road",True),
    (24083392793,"2026-08-23","Ara - Monteaperta - Taipana - Prossenicco","road",True),
    (24071620702,"2026-08-22","Ara - Majano - Monteaperta - Remanzacco","road",True),
    (24034049473,"2026-08-19","Ara - Tanamea - Caporetto - Cividale","road",True),
    (24020523301,"2026-08-18","Ara - Tanamea - Buia - Pagnacco","road",True),
    (23996169972,"2026-08-16","Cortina - Giau - Valparola","road",True),
    (23961022502,"2026-08-13","Cortina - Falzarego - Campolongo - Valparola","road",True),
    (23933657597,"2026-08-11","Cortina - San Candido - Misurina","road",True),
    (23912303030,"2026-08-09","Cortina - Falzarego - Valparola - Gardena - Sella - Pordoi - Giau","road",True),
    (23872904989,"2026-08-06","Cortina - Cimabanche - Monte Croce Comelico","road",True),
    (23835130056,"2026-08-03","Cortina - Giau - Valparola - Tre Croci - Cimabanche","road",True),
    (23799499959,"2026-07-31","Cortina - Valparola - Gardena - Campolongo - Falzarego","road",True),
    (23758664119,"2026-07-28","Milano - Abbiategrasso","road",False),
    (23737517606,"2026-07-26","Milano - Bereguardo - Abbiategrasso","road",False),
    (23724892894,"2026-07-25","Como - Nesso - Ghisallino Power","road",True),
    (23699203621,"2026-07-23","Milano - Abbiategrasso","road",False),
    (23673393484,"2026-07-21","Milano - Cassinetta","road",False),
    (23652925081,"2026-07-19","Como - Balcone - Lugano","road",True),
    (23639549148,"2026-07-18","Milano - Bereguardo - Robecco","road",False),
    (23602986808,"2026-07-15","Milano - Abbiategrasso","road",False),
    (23570316392,"2026-07-12","Cortina - Giau - Falzarego - Tre Croci - Cimabanche","road",True),
    (23538538776,"2026-07-09","Cortina - Cimabanche","road",True),
    (23513921013,"2026-07-07","Cortina - Cimabanche","road",True),
    (23486060702,"2026-07-05","Cortina - Dobbiaco","road",True),
    (23476724958,"2026-07-04","Cortina - Giau - Campolongo - Valparola - Falzarego","road",True),
    (23456466892,"2026-07-02","Cortina - Misurina","road",True),
    (23432733741,"2026-06-30","Cortina - Baita Resch - Lago Scin","road",True),
    (23404120213,"2026-06-28","Cortina - Landro - Antorno - Misurina","road",True),
    (23396147027,"2026-06-27","Cortina - Falzarego - Valparola - Gardena - Sella - Pordoi - Falzarego","road",True),
    (23371726696,"2026-06-25","Milano - Abbiategrasso","road",False),
    (23347714104,"2026-06-23","Milano - Abbiategrasso","road",False),
    (23327889893,"2026-06-21","Lago Lugano via Val Mara","road",True),
    (23315235657,"2026-06-20","Como - Nesso - Ghisallino Power","road",True),
    (23291028404,"2026-06-18","Milano - Cassinetta","road",False),
    (23265435778,"2026-06-16","Milano - Cassinetta","road",False),
    (23247353161,"2026-06-14","Mottarone - Sovazza","road",True),
    (23232542257,"2026-06-13","Milano - Tornavento","road",False),
    (23214948269,"2026-06-11","Milano - Mairano - Abbiategrasso","road",False),
    (23183670484,"2026-06-09","Milano - Abbiategrasso - Robecco","road",False),
    (23164118181,"2026-06-07","Como - Balcone - Lugano","road",True),
    (23150708559,"2026-06-06","Oltre Po","road",True),
    (23123645988,"2026-06-04","Milano - Abbiategrasso","road",False),
    (23087344572,"2026-06-01","Milano - Abbiategrasso","road",False),
    (23077680781,"2026-05-31","Milano - Nosate - Abbiategrasso","road",False),
    (23064611546,"2026-05-30","Milano - Mairano - Abbiategrasso","road",False),
    (23055367709,"2026-05-29","Valcava","road",True),
    (23027803552,"2026-05-27","Milano - Rosate - Abbiategrasso","road",False),
    (23015232775,"2026-05-26","Milano - Robecco","road",False),
    (22992612035,"2026-05-24","Milano - Mairano - Abbiategrasso","road",False),
    (22984152670,"2026-05-23","Tre Laghi","road",True),
    (22963203500,"2026-05-21","Milano - Ozzero - Rosate","road",False),
    (22939807571,"2026-05-19","Milano - Robecco - Abbiategrasso","road",False),
    (22913695000,"2026-05-17","Milano - Sesto Calende","road",False),
    (22902492251,"2026-05-16","Milano - Mairano - Abbiategrasso","road",False),
    (22889111639,"2026-05-15","VO2 Max 4: 30/15 seconds at 120%FTP","indoor",True),
    (22870202987,"2026-05-13","Milano - Robecco","road",False),
    (22859195654,"2026-05-12","Base 1","indoor",True),
    (22835295733,"2026-05-10","Base 1","indoor",True),
    (22820987608,"2026-05-09","Ghisallo - Colma - Vicerè","road",True),
    (22800002982,"2026-05-07","Base 3","indoor",True),
    (22788105608,"2026-05-06","1h Z2+5xZ4","indoor",True),
    (22776261432,"2026-05-05","1h Z2+4xshortZ3","indoor",True),
    (22749247005,"2026-05-03","Onno - Ghisallino Power","road",True),
    (22736311320,"2026-05-02","Milano - Mairano - Morimondo","road",False),
    (22726220443,"2026-05-01","Milano - Tornavento","road",False),
    (22705162024,"2026-04-29","Milano - Abbiategrasso - Robecco","road",False),
    (22680621746,"2026-04-27","Milano - Mairano - Abbiategrasso","road",False),
    (22652819701,"2026-04-25","Milano - Pavia - Vigevano","road",False),
    (22633717234,"2026-04-23","Milano - Robecco - Abbiategrasso","road",False),
    (22602225296,"2026-04-21","1h Z2+4xshortZ3","indoor",True),
    (22584832753,"2026-04-19","Milano - Mairano - Morimondo","road",False),
    (22570119691,"2026-04-18","Albavilla - Nesso - Ghisallino - Onno","road",True),
    (22555546691,"2026-04-17","Base 4","indoor",True),
    (22531586882,"2026-04-15","1h Z2+5xZ4","indoor",True),
    (22507734713,"2026-04-13","1h Z2+4xshortZ3","indoor",True),
    (22488657053,"2026-04-11","Giro del Lago di Como","road",True),
    (22473669794,"2026-04-10","Base 1","indoor",True),
    (22449005064,"2026-04-08","1h Z2+4xshortZ3","indoor",True),
    (22426475907,"2026-04-06","Milano - Bereguardo - Robecco","road",False),
    (22405438246,"2026-04-04","Milano - Maddalena - Morimondo","road",False),
    (22390331550,"2026-04-03","1h Z2+4xshortZ3","indoor",True),
    (22356704707,"2026-03-31","1h Z2+4xshortZ3","indoor",True),
    (22337021912,"2026-03-29","Milano - Mairano - Morimondo","road",False),
    (22326812793,"2026-03-28","Milano - Bereguardo - Robecco","road",False),
    (22309008240,"2026-03-26","1h Z2+4xshortZ3","indoor",True),
    (22279687516,"2026-03-24","1h Z2+5xZ4","indoor",True),
    (22260143387,"2026-03-22","Milano - Mairano - Bereguardo - Robecco","road",False),
    (22230312799,"2026-03-19","1h Z2+4xshortZ3","indoor",True),
    (22218627978,"2026-03-18","1h Z2+5xZ4","indoor",True),
    (22195507694,"2026-03-16","1h Z2+4xshortZ3","indoor",True),
    (22180507561,"2026-03-15","Base 3","indoor",True),
    (22168683435,"2026-03-14","VO2 Max 3: 40/20 seconds at 120%FTP","indoor",True),
    (22146356534,"2026-03-12","1h Z2+5xZ4","indoor",True),
    (22122952437,"2026-03-10","1h Z2+4xshortZ3","indoor",True),
    (22102784113,"2026-03-08","Milano - Basiano - Abbiategrasso","road",False),
    (22091745600,"2026-03-07","Milano - Tornavento","road",False),
    (22069701857,"2026-03-05","1h Z2+5xZ4","indoor",True),
    (22043419091,"2026-03-03","1h Z2+4xshortZ3","indoor",True),
    (22024210468,"2026-03-01","2h15 Z2+Z3","indoor",True),
    (21996191786,"2026-02-26","1h Z2+5xZ4","indoor",True),
    (21966289882,"2026-02-24","Base 1","indoor",True),
    (21947707055,"2026-02-22","Milano - Castelletto","road",False),
    (21937301273,"2026-02-21","Milano - Mairano - Basiano","road",False),
    (21914371911,"2026-02-19","Base 1","indoor",True),
    (21906890513,"2026-02-18","1h Z2+5xZ4","indoor",True),
    (21893019441,"2026-02-17","VO2 Max 4: 30/15 seconds at 120%FTP","indoor",True),
    (21873983231,"2026-02-15","Base 2","indoor",True),
    (21864631574,"2026-02-14","1h30 Z2+7xZ3","indoor",True),
    (21842639614,"2026-02-12","1h Z2+5xZ4","indoor",True),
    (21827503468,"2026-02-10","1h Z2+4xshortZ3","indoor",True),
    (21765353727,"2026-02-04","45min Z2+3xZ4","indoor",True),
    (21747723965,"2026-02-03","45min Z2+3xZ4","indoor",True),
    (21737148717,"2026-02-02","Base 1","indoor",True),
    (21718887313,"2026-01-31","1h30 Z2+7xZ3","indoor",True),
    (21679129223,"2026-01-27","1h Z2+4xshortZ3","indoor",True),
    (21672916778,"2026-01-26","1h Z2+5xZ4","indoor",True),
    (21659757784,"2026-01-25","1h30 Z2+7xZ3","indoor",True),
    (21632729024,"2026-01-22","1h Z2+5xZ4","indoor",True),
    (21621670487,"2026-01-21","1h Z2+4xshortZ3","indoor",True),
    (21604710136,"2026-01-20","1h Z2+4xshortZ3","indoor",True),
    (21586771235,"2026-01-18","1h Z2+5xZ4","indoor",True),
    (21575716971,"2026-01-17","1h30 Z2+7xZ3","indoor",True),
    (21558104990,"2026-01-15","1h Z2+4xshortZ3","indoor",True),
    (21547112066,"2026-01-14","VO2 Max 4: 30/15 seconds at 120%FTP","indoor",True),
    (21525925791,"2026-01-12","1h Z2+5xZ4","indoor",True),
    (21510125444,"2026-01-11","1h30 Z2+7xZ3","indoor",True),
    (21500699583,"2026-01-10","1h30 Z2+7xZ3","indoor",True),
    (21491622811,"2026-01-09","Base 1","indoor",True),
    (21342324837,"2025-12-24","1h Z2+4xshortZ3","indoor",True),
    (21334373045,"2025-12-23","Base 4","indoor",True),
    (21332337555,"2025-12-20","1h30 Z2+7xZ3","indoor",True),
    (21292484515,"2025-12-18","VO2 Max 4: 30/15 seconds at 120%FTP","indoor",True),
    (21283126477,"2025-12-17","Base 1","indoor",True),
    (21274918394,"2025-12-16","1h Z2+4xshortZ3","indoor",True),
    (21254639097,"2025-12-14","Milano - Mairano - Motta - Abbiategrasso","road",False),
    (21245318573,"2025-12-13","Anaerobic 4: 8 x 1 minutes Zone 6","indoor",True),
    (21231856586,"2025-12-11","1h30 Z2+7xZ3","indoor",True),
    (21219900817,"2025-12-10","45min Z2+3xZ4","indoor",True),
    (21204717231,"2025-12-08","Tempo 2","indoor",True),
    (21195372026,"2025-12-07","Threshold 2","indoor",True),
    (21175797391,"2025-12-05","Pa Sak (Thailand)","virtual",True),
    (21130676444,"2025-11-30","Milano - Abbiategrasso","road",False),
    (21122004962,"2025-11-29","Milano - Mairano - Basiano - Robecco","road",False),
    (21096462561,"2025-11-26","Milano - Mairano - Gaggiano","road",False),
    (21061467226,"2025-11-22","Milano - Mairano - Basiano","road",False),
    (21024660655,"2025-11-18","Milano - Mairano - Gaggiano","road",False),
    (20986520209,"2025-11-14","Milano - Abbiategrasso","road",False),
    (20937268109,"2025-11-09","Milano - Mairano - Morimondo","road",False),
    (20929436812,"2025-11-08","Milano - Pavia - Ticino - Robecco","road",False),
    (20909593346,"2025-11-06","Milano - Mairano - Gaggiano","road",False),
    (20899381000,"2025-11-05","Milano - Abbiategrasso","road",False),
    (20879106410,"2025-11-03","Milano - Mairano - Gaggiano","road",False),
    (20858083765,"2025-11-01","Milano - Morimondo","road",False),
    (20801895211,"2025-10-26","Milano - Basiano - Mairano","road",False),
    (20791394339,"2025-10-25","Milano - Mairano - Morimondo","road",False),
    (20735574497,"2025-10-19","Milano - Abbiategrasso","road",False),
    (20726662669,"2025-10-18","Milano - Mairano - Gaggiano","road",False),
    (20703336608,"2025-10-16","Paris Indoor Cycling","indoor",True),
    (20665076079,"2025-10-12","Milano - Mairano - Basiano","road",False),
    (20658226016,"2025-10-11","Milano - Nosate","road",False),
    (20646214658,"2025-10-10","Milano - Mirano - Gaggiano","road",False),
    (20615906370,"2025-10-07","Milano - Robecco","road",False),
    (20596377932,"2025-10-05","Giro dei Tre Navigli","road",False),
    (20586837541,"2025-10-04","Milano - Mairano - Gaggiano","road",False),
    (20556526088,"2025-10-01","Milano - Abbiategrasso","road",False),
    (20536381557,"2025-09-29","Milano - Mairano - Gaggiano","road",False),
    (20526132907,"2025-09-28","Lecco - Passo Agueglio - Pasturo","road",True),
    (20495854804,"2025-09-25","Milano - Mairano - Gaggiano","road",False),
    (20485719301,"2025-09-24","Milano - Mairano - Gaggiano","road",False),
]


def classify_activity(act, detail):
    """Classify activity by type and terrain."""
    name = act[2].lower()
    atype = act[3]
    has_pm = act[4]
    elev = detail.get("elevation_gain_meters", 0) or 0
    duration = detail.get("duration_seconds", 0) or 0
    distance = detail.get("distance_meters", 0) or 0
    
    if atype == "indoor":
        return "indoor_structured"
    
    # Flat weekday (no PM, <100m gain, <80km)
    if not has_pm and elev < 100 and distance < 85000:
        return "flat_weekday"
    
    # Long flat (Sunday endurance)
    if not has_pm and elev < 400:
        return "long_flat"
    
    # Hilly with PM
    if has_pm and elev >= 600:
        return "climbing_pm"
    
    # Hilly without PM
    if not has_pm and elev >= 400:
        return "climbing_no_pm"
    
    return "other"


def get_zone_label(np_w, ftp=256):
    """Get power zone label from NP and FTP."""
    if np_w is None:
        return "N/A"
    pct = np_w / ftp * 100
    if pct < 55: return "Z1 Recovery"
    if pct < 75: return "Z2 Endurance"
    if pct < 90: return "Z3 Tempo"
    if pct < 105: return "Z4 Threshold"
    if pct < 120: return "Z5 VO2max"
    return "Z6+ Anaerobic"


def main():
    print("WattsUpAI Activity Database Builder")
    print("=" * 50)
    
    # Load tokens
    try:
        client = Garmin(session_dir=str(TOKEN_DIR))
        client.login()
        print("✓ Logged in to Garmin Connect")
    except Exception as e:
        print(f"✗ Login failed: {e}")
        print("Run: uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth")
        return

    db = {
        "metadata": {
            "built_at": datetime.now().isoformat(),
            "total_activities": len(ACTIVITIES),
            "ftp_w": FTP,
            "power_zones": {str(k): v for k, v in POWER_ZONES.items()},
            "hr_zones": HR_ZONES,
            "lactate_threshold_hr": 171,
        },
        "activities": []
    }
    
    # Load existing if present (resume on interrupt)
    existing_ids = set()
    if OUT_FILE.exists():
        with open(OUT_FILE) as f:
            existing = json.load(f)
        db["activities"] = existing.get("activities", [])
        existing_ids = {a["id"] for a in db["activities"]}
        print(f"Resuming: {len(existing_ids)} activities already fetched")
    
    total = len(ACTIVITIES)
    fetched = 0
    
    for i, act in enumerate(ACTIVITIES):
        act_id, date, name, atype, has_pm = act
        
        if act_id in existing_ids:
            continue
        
        print(f"[{i+1}/{total}] {date} {name[:40]}...", end=" ", flush=True)
        
        try:
            # Get activity detail
            detail = client.get_activity(act_id)
            time.sleep(0.3)  # rate limit
            
            record = {
                "id": act_id,
                "date": date,
                "name": name,
                "type": atype,
                "has_power_meter": has_pm,
                "category": classify_activity(act, detail),
                "duration_min": round((detail.get("duration_seconds") or 0) / 60, 1),
                "distance_km": round((detail.get("distance_meters") or 0) / 1000, 1),
                "elevation_m": detail.get("elevation_gain_meters") or 0,
                "avg_hr": detail.get("avg_hr_bpm"),
                "max_hr": detail.get("max_hr_bpm"),
                "avg_power": detail.get("avg_power_watts"),
                "max_power": detail.get("max_power_watts"),
                "np": detail.get("normalized_power_watts"),
                "np_pct_ftp": round((detail.get("normalized_power_watts") or 0) / FTP * 100, 1) if detail.get("normalized_power_watts") else None,
                "np_zone": get_zone_label(detail.get("normalized_power_watts")),
                "training_effect": detail.get("training_effect"),
                "anaerobic_effect": detail.get("anaerobic_training_effect"),
                "training_effect_label": detail.get("training_effect_label"),
                "training_load": round(detail.get("training_load") or 0, 1),
                "calories": detail.get("calories"),
                "hr_zones": None,
                "power_zones": None,
            }
            
            # Fetch zone data for power meter rides
            if has_pm and atype != "indoor":
                try:
                    hz = client.get_activity_hr_in_timezones(act_id)
                    time.sleep(0.2)
                    record["hr_zones"] = {
                        str(z["zoneNumber"]): round(z["secsInZone"] / 60, 1)
                        for z in hz
                    }
                except Exception as e:
                    print(f"(HR zones error: {e})", end=" ")
                
                try:
                    pz = client.get_activity_power_in_timezones(act_id)
                    time.sleep(0.2)
                    record["power_zones"] = {
                        str(z["zoneNumber"]): round(z["secsInZone"] / 60, 1)
                        for z in pz
                    }
                except Exception as e:
                    print(f"(power zones error: {e})", end=" ")
            
            # For indoor rides, get HR zones too
            elif atype == "indoor":
                try:
                    hz = client.get_activity_hr_in_timezones(act_id)
                    time.sleep(0.2)
                    record["hr_zones"] = {
                        str(z["zoneNumber"]): round(z["secsInZone"] / 60, 1)
                        for z in hz
                    }
                except:
                    pass
                try:
                    pz = client.get_activity_power_in_timezones(act_id)
                    time.sleep(0.2)
                    record["power_zones"] = {
                        str(z["zoneNumber"]): round(z["secsInZone"] / 60, 1)
                        for z in pz
                    }
                except:
                    pass
            
            db["activities"].append(record)
            fetched += 1
            print(f"✓ NP:{record['np']}W [{record['training_effect_label']}] load:{record['training_load']}")
            
            # Save every 10 activities
            if fetched % 10 == 0:
                with open(OUT_FILE, "w") as f:
                    json.dump(db, f, indent=2)
                print(f"  → Saved checkpoint ({len(db['activities'])} activities)")
        
        except Exception as e:
            print(f"✗ Error: {e}")
            time.sleep(1)
    
    # Final save
    # Sort by date descending
    db["activities"].sort(key=lambda x: x["date"], reverse=True)
    db["metadata"]["total_fetched"] = len(db["activities"])
    
    with open(OUT_FILE, "w") as f:
        json.dump(db, f, indent=2)
    
    print(f"\n✓ Database built: {OUT_FILE}")
    print(f"  {len(db['activities'])} activities")
    
    # Quick summary
    power_rides = [a for a in db["activities"] if a.get("np")]
    print(f"\nPower meter rides: {len(power_rides)}")
    labels = {}
    for a in power_rides:
        l = a.get("training_effect_label", "unknown")
        labels[l] = labels.get(l, 0) + 1
    print("Training effect distribution:")
    for l, n in sorted(labels.items(), key=lambda x: -x[1]):
        print(f"  {l}: {n}")


if __name__ == "__main__":
    main()
