"""Fetch World Cup 2026 fixture list and write all cron entries at once.

Run once at the start of the tournament:
  python setup_schedule.py           # fetch + schedule + push schedule.json
  python setup_schedule.py --dry-run # print only, no cron writes
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

import schedule_match

WORK_DIR = Path(__file__).parent

# World Cup 2026 date range
WC_START = "20260611"
WC_END   = "20260719"

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


def fetch_fixtures() -> list[dict]:
    """Fetch all WC 2026 fixtures from ESPN public API."""
    print(f"Fetching fixtures from ESPN ({WC_START}–{WC_END})...")
    resp = requests.get(ESPN_URL, params={"dates": f"{WC_START}-{WC_END}"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    fixtures = []
    for event in data.get("events", []):
        comps = event.get("competitions", [{}])
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors", [])
        if len(competitors) != 2:
            continue

        home_team = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away_team = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home_team or not away_team:
            continue

        kickoff_utc = event.get("date", "")  # ISO format from ESPN
        stage = (
            event.get("season", {}).get("slug", "")
            or "group-stage"
        ).replace("-", " ").title()

        fixtures.append({
            "home": home_team["team"].get("abbreviation", "").upper(),
            "away": away_team["team"].get("abbreviation", "").upper(),
            "home_name": home_team["team"].get("displayName", ""),
            "away_name": away_team["team"].get("displayName", ""),
            "kickoff_utc": kickoff_utc,
            "stage": stage,
        })

    print(f"Found {len(fixtures)} fixtures")
    return fixtures


def main():
    dry_run = "--dry-run" in sys.argv

    try:
        fixtures = fetch_fixtures()
    except Exception as e:
        print(f"ERROR: ESPN API failed: {e}")
        sys.exit(1)

    if not fixtures:
        print("No fixtures found. Check ESPN API or date range.")
        sys.exit(1)

    # Save schedule.json regardless of dry-run
    schedule_path = WORK_DIR / "schedule.json"
    schedule_path.write_text(json.dumps(fixtures, indent=2))
    print(f"Saved {len(fixtures)} fixtures to schedule.json")

    now = datetime.now(timezone.utc)
    upcoming = [
        f for f in fixtures
        if f.get("kickoff_utc") and datetime.fromisoformat(
            f["kickoff_utc"].replace("Z", "+00:00")
        ) > now
    ]
    past = len(fixtures) - len(upcoming)
    print(f"  {len(upcoming)} upcoming, {past} already past")

    added = 0
    skipped = 0

    for fixture in upcoming:
        home = fixture["home"]
        away = fixture["away"]
        kickoff = fixture["kickoff_utc"]

        if not home or not away or not kickoff:
            continue

        p_line, r_line = schedule_match.make_cron_lines(home, away, kickoff)
        print(f"\n  {home} vs {away} — {kickoff}")
        print(f"    {p_line.splitlines()[-1]}")
        print(f"    {r_line.splitlines()[-1]}")

        if not dry_run:
            try:
                schedule_match.add_cron_entries(home, away, kickoff)
                added += 1
            except Exception as e:
                print(f"    WARNING: cron write failed: {e}")
                skipped += 1
        else:
            added += 1

    if dry_run:
        print(f"\nDRY RUN: would schedule {added} matches. Run without --dry-run to apply.")
    else:
        print(f"\nScheduled {added} matches ({skipped} failed).")
        # Push schedule.json to GitHub
        try:
            subprocess.run(
                ["git", "add", "schedule.json"],
                cwd=WORK_DIR, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "setup: add WC 2026 fixture schedule"],
                cwd=WORK_DIR, check=True, capture_output=True,
            )
            subprocess.run(["git", "push"], cwd=WORK_DIR, check=True, capture_output=True)
            print("Pushed schedule.json to GitHub")
        except Exception as e:
            print(f"Git push failed (schedule.json saved locally): {e}")

    print("\nDone. Verify with: crontab -l")


if __name__ == "__main__":
    main()
