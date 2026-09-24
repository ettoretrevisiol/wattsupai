#!/usr/bin/env python3
"""
log_session.py — 3-question post-ride subjective prompt.

Asks 3 quick questions, then appends a structured note to
training-log/current-plan.md alongside the auto-generated objective note.

Run this immediately after a ride:
  python3 scripts/log_session.py

Takes ~30 seconds. Adds the context the objective data can't capture:
how you felt, whether you hit targets, what to remember.
"""

import os
import sqlite3
from datetime import date, datetime

REPO     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(REPO, "data", "training.db")
LOG_PATH = os.path.join(REPO, "training-log", "current-plan.md")

FEEL_OPTIONS = {
    "1": ("strong",  "Felt strong — hit all targets, could have gone harder."),
    "2": ("good",    "Felt good — solid session, executed the plan."),
    "3": ("ok",      "Felt ok — got through it, some struggles."),
    "4": ("tired",   "Felt tired — legs/body not there, had to back off."),
    "5": ("terrible","Felt terrible — clearly not recovered, off day."),
}

TARGET_OPTIONS = {
    "y": "✅ Yes — hit targets",
    "n": "❌ No — missed targets",
    "p": "~  Partial — hit some, missed some",
}


def get_latest_activity():
    """Return basic info about the most recent activity."""
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""
        SELECT date, sub_sport, has_power,
               ROUND(distance_km,0) km,
               ROUND(elevation_gain_m,0) elev,
               avg_hr_bpm, max_hr_bpm,
               np_w_computed np,
               ROUND((SELECT hr_z4_s+hr_z5_s FROM zone_summaries z
                      WHERE z.activity_id=a.activity_id)/60.0, 1) z4_min
        FROM activities a
        ORDER BY date DESC, start_time_utc DESC
        LIMIT 1
    """).fetchone()
    conn.close()
    return row


def prompt(question, options_dict=None, allow_free=False):
    """
    Print a question and return the user's answer.
    If options_dict is given, show choices and validate.
    If allow_free, accept any text.
    """
    print(f"\n  {question}")
    if options_dict:
        for key, val in options_dict.items():
            label = val if isinstance(val, str) else val[1]
            print(f"    [{key}] {label}")
        while True:
            ans = input("  → ").strip().lower()
            if ans in options_dict:
                return ans
            print(f"  Please enter one of: {', '.join(options_dict.keys())}")
    elif allow_free:
        ans = input("  → ").strip()
        return ans if ans else "(no notes)"
    return input("  → ").strip()


def check_already_logged(date_s):
    """Return True if a subjective log entry already exists for this date."""
    if not os.path.exists(LOG_PATH):
        return False
    with open(LOG_PATH) as f:
        content = f.read()
    return f"### {date_s} (subjective)" in content


def build_note(date_s, activity_row, feel_key, targets_key, end_hr_str, free_notes):
    feel_label = FEEL_OPTIONS[feel_key][1]
    targets_label = TARGET_OPTIONS[targets_key]

    lines = [
        f"### {date_s} (subjective)",
    ]

    if activity_row:
        _, sport, has_power, km, elev, avg_hr, max_hr, np_w, z4_min = activity_row
        pw_s = f" · NP {np_w}W" if has_power and np_w else ""
        lines.append(f"_{km:.0f}km · {elev:.0f}m{pw_s} · Z4={z4_min or 0:.0f}min_")

    lines += [
        "",
        f"- **Feel:** {feel_label}",
        f"- **Targets:** {targets_label}",
    ]

    if end_hr_str and end_hr_str != "(no notes)":
        lines.append(f"- **End-of-rep HR:** {end_hr_str}bpm")

    if free_notes and free_notes != "(no notes)":
        lines.append(f"- **Notes:** {free_notes}")

    lines.append("")
    return "\n".join(lines)


def append_to_log(note_text):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, "w") as f:
            f.write(f"# Current Plan\n\n## Session Log\n\n{note_text}")
        return

    with open(LOG_PATH) as f:
        content = f.read()

    if not content.endswith("\n"):
        content += "\n"
    content += "\n" + note_text

    with open(LOG_PATH, "w") as f:
        f.write(content)


def main():
    print()
    print("┌─────────────────────────────────────────┐")
    print("│  WattsUpAI — Post-Ride Log (30 seconds) │")
    print("└─────────────────────────────────────────┘")

    # Show latest activity context
    row = get_latest_activity()
    today_s = date.today().isoformat()

    if row:
        date_s, sport, has_power, km, elev, avg_hr, max_hr, np_w, z4_min = row
        pw_s = f" · NP {np_w}W" if has_power and np_w else " · no power"
        print(f"\n  Last activity: {date_s} · {km:.0f}km · {elev:.0f}m{pw_s}")
        print(f"  HR avg/max: {avg_hr}/{max_hr}bpm · Z4+Z5: {z4_min or 0:.0f}min")

        # Use latest activity date (may differ from today if logging after midnight)
        log_date = date_s
    else:
        print("\n  (no activity found in DB)")
        log_date = today_s

    # Check already logged
    if check_already_logged(log_date):
        print(f"\n  ✓ Subjective note for {log_date} already exists.")
        overwrite = input("  Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            print("  Skipped.")
            return

    print()

    # ── Question 1: How did it feel? ──────────────────────────────────────────
    feel_key = prompt("1. How did the session feel?", FEEL_OPTIONS)

    # ── Question 2: Did you hit the targets? ──────────────────────────────────
    targets_key = prompt(
        "2. Did you hit the session targets? (HR, power, or RPE)",
        TARGET_OPTIONS,
    )

    # ── Question 3: End-of-rep HR (only if interval session) ──────────────────
    end_hr_str = ""
    is_interval = feel_key in ("1", "2", "3", "4") and targets_key in ("y", "p", "n")
    print(f"\n  3. End-of-last-rep HR (bpm) — or press Enter to skip")
    end_hr_str = input("  → ").strip()
    if not end_hr_str:
        end_hr_str = ""

    # ── Optional free notes ───────────────────────────────────────────────────
    print(f"\n  Any other notes? (legs, weather, unusual HR, etc.) — or press Enter to skip")
    free_notes = input("  → ").strip()

    # Build and append
    note = build_note(log_date, row, feel_key, targets_key, end_hr_str, free_notes)
    append_to_log(note)

    print()
    print(f"  ✓ Logged to training-log/current-plan.md")
    print(f"  The coach will read this at the start of the next session.")
    print()


if __name__ == "__main__":
    main()
