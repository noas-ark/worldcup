"""Helper: write predict + reflect cron entries for a single match.

Imported by setup_schedule.py. Can also be run directly:
  python schedule_match.py NED JPN 2026-06-14T20:00:00Z
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone


def make_cron_lines(home: str, away: str, kickoff_utc: str) -> tuple[str, str]:
    """Return (predict_cron_line, reflect_cron_line) for the match."""
    dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00")).astimezone(timezone.utc)

    predict_dt = dt - timedelta(minutes=30)
    reflect_dt = dt + timedelta(minutes=150)  # 2.5 hours after kickoff

    def cron_time(d: datetime) -> str:
        return f"{d.minute} {d.hour} {d.day} {d.month} *"

    log_file = f"logs/{home}_{away}.log"
    base_cmd = f"cd /home/ubuntu/worldcup && source .env && /home/ubuntu/worldcup/venv/bin/python"

    predict_line = (
        f"# {home} vs {away} — predict (30 min before kickoff {dt.strftime('%Y-%m-%d %H:%M')} UTC)\n"
        f"{cron_time(predict_dt)} {base_cmd} predict.py {home} {away} >> {log_file} 2>&1"
    )
    reflect_line = (
        f"# {home} vs {away} — reflect (2.5h after kickoff)\n"
        f"{cron_time(reflect_dt)} {base_cmd} reflect.py {home} {away} >> {log_file} 2>&1"
    )
    return predict_line, reflect_line


def add_cron_entries(home: str, away: str, kickoff_utc: str) -> tuple[str, str]:
    """Add cron entries if not already present. Returns the two lines added."""
    predict_line, reflect_line = make_cron_lines(home, away, kickoff_utc)

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    skip_marker = f"predict.py {home} {away}"
    if skip_marker in existing:
        return predict_line, reflect_line  # already scheduled, skip

    new_crontab = existing.rstrip() + "\n\n" + predict_line + "\n" + reflect_line + "\n"
    subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
    return predict_line, reflect_line


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python schedule_match.py HOME AWAY KICKOFF_UTC")
        print("Example: python schedule_match.py NED JPN 2026-06-14T20:00:00Z")
        sys.exit(1)
    home, away, kickoff = sys.argv[1].upper(), sys.argv[2].upper(), sys.argv[3]
    p, r = add_cron_entries(home, away, kickoff)
    print("Added cron entries:")
    print(p)
    print(r)
