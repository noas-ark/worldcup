"""Post-match reflection. Run ~2.5 hours after kickoff.

Usage: python reflect.py HOME AWAY
Example: python reflect.py NED JPN
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import gemini
import requests
from dotenv import load_dotenv

import discord_notify

# ── Setup ──────────────────────────────────────────────────────────────────

load_dotenv()

if len(sys.argv) != 3:
    print("Usage: python reflect.py HOME AWAY")
    sys.exit(1)

HOME = sys.argv[1].upper()
AWAY = sys.argv[2].upper()
MATCH = f"{HOME} vs {AWAY}"
WORK_DIR = Path(__file__).parent

os.makedirs(WORK_DIR / "logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(WORK_DIR / "logs" / f"{HOME}_{AWAY}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.info
err = logging.error


def _git_env() -> dict:
    """Git subprocess env — drop stale GITHUB_TOKEN so gh auth credentials are used."""
    env = os.environ.copy()
    env.pop("GITHUB_TOKEN", None)
    return env


# ── Step 1: Get match result ───────────────────────────────────────────────

log("=== reflect.py %s ===", MATCH)

result_data = None

def _get_result_from_espn() -> dict | None:
    """Try ESPN public API to find completed match score."""
    try:
        # Try last 2 days to account for timezone offsets
        from datetime import timedelta
        for delta in range(3):
            day = (datetime.now(timezone.utc) - timedelta(days=delta)).strftime("%Y%m%d")
            url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
            resp = requests.get(url, params={"dates": day}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            for event in data.get("events", []):
                comps = event.get("competitions", [{}])
                if not comps:
                    continue
                comp = comps[0]
                competitors = comp.get("competitors", [])
                if len(competitors) != 2:
                    continue
                abbrevs = {c["homeAway"]: c["team"].get("abbreviation", "").upper() for c in competitors}
                if abbrevs.get("home") != HOME or abbrevs.get("away") != AWAY:
                    continue
                status = comp.get("status", {}).get("type", {})
                if not status.get("completed", False):
                    log("Match found but not yet completed (state: %s)", status.get("state"))
                    return None
                scores = {c["homeAway"]: int(c.get("score", 0)) for c in competitors}
                home_score = scores.get("home", 0)
                away_score = scores.get("away", 0)
                if home_score > away_score:
                    winner = "home"
                elif away_score > home_score:
                    winner = "away"
                else:
                    winner = "draw"
                log("ESPN result: %s %d-%d %s → winner: %s", HOME, home_score, away_score, AWAY, winner)
                return {"home_score": home_score, "away_score": away_score, "winner": winner}
    except Exception as e:
        err("ESPN API failed: %s", e)
    return None

result_data = _get_result_from_espn()

if result_data is None:
    err("Could not fetch match result from ESPN. Try again in a few minutes.")
    err("Or set the result manually in results.json and re-run.")
    sys.exit(1)

# ── Step 2: Find prediction in results.json ────────────────────────────────

results_path = WORK_DIR / "results.json"
strategy_path = WORK_DIR / "strategy.md"

results = json.loads(results_path.read_text()) if results_path.exists() else []
strategy = strategy_path.read_text() if strategy_path.exists() else ""

# Find the most recent unprocessed entry for this match
entry_idx = None
for i in range(len(results) - 1, -1, -1):
    e = results[i]
    if e.get("home") == HOME and e.get("away") == AWAY and not e.get("reflected", False):
        entry_idx = i
        break

if entry_idx is None:
    err("No unprocessed prediction found for %s in results.json", MATCH)
    sys.exit(1)

entry = results[entry_idx]
prediction = entry.get("prediction", {})
log("Found prediction: pick=%s confidence=%d", prediction.get("pick"), prediction.get("confidence"))

# ── Step 3: Evaluator call (separate from predictor) ──────────────────────

pick = prediction.get("pick", "home")
actual_winner = result_data["winner"]
correct = (pick == actual_winner)
wallet_delta = -entry.get("research_cost", 0)

research_summary = ""
for svc in entry.get("services_used", []):
    research_summary += f"\n- {svc['source']} (${svc['cost']:.4f}): {svc.get('reason', '')}"

mistake_section = "" if correct else """MISTAKE:
- One sentence: what the pick got wrong.
- One sentence: the specific reasoning error.
"""

eval_prompt = f"""Write a terse post-match learning note for a prediction agent.

Match: {MATCH}
Result: {HOME} {result_data['home_score']}-{result_data['away_score']} {AWAY} (winner: {actual_winner})
Predicted: {pick} (confidence {prediction.get('confidence')}/10) — {'CORRECT' if correct else 'WRONG'}
Reasoning given: {prediction.get('reasoning')}
Research purchased (${entry.get('research_cost', 0):.4f}):{research_summary if research_summary else " none"}

Rules:
- Plain text only. No preamble, praise, or filler ("Here is...", "honest evaluation", etc.).
- No markdown headers, bold, or horizontal rules.
- Max 120 words.
- Be blunt and specific. Name the exact mistake, not abstract narratives.

Format exactly:

{mistake_section}DATA:
- useful: [source] — one line on what it told us that mattered
- useless: [source] — one line on why it didn't help

List only endpoints that were actually purchased. 2-5 bullets total across useful/useless."""

log("Asking Gemini for evaluation...")
try:
    eval_resp_text = gemini.generate(eval_prompt)
    evaluation = eval_resp_text
except Exception as e:
    err("Gemini evaluation call failed: %s", e)
    evaluation = f"Evaluation unavailable: {e}"

# ── Step 4: Reflector call (updates strategy) ─────────────────────────────

reflect_prompt = f"""Update the agent's strategy document. Write like engineering notes — terse, direct, no marketing language or dramatic rule names.

Current strategy:
{strategy if strategy else "(empty — first match)"}

Latest match note ({MATCH}):
{evaluation}

Rewrite with EXACTLY ONE rule change from this match. Keep still-valid existing rules.

Format:

# Strategy

## Rules
- MATCH: one sentence rule

## Data sources
- use: source type — why (MATCH)
- skip: source type — why (MATCH)

Max 250 words. Return ONLY the document."""

log("Asking Gemini to update strategy...")
try:
    strat_resp_text = gemini.generate(reflect_prompt)
    new_strategy = strat_resp_text.strip()
except Exception as e:
    err("Gemini strategy update failed: %s", e)
    new_strategy = strategy  # keep current if update fails

strategy_path.write_text(new_strategy)
log("Updated strategy.md")

# ── Step 5: Update results.json and push to GitHub ─────────────────────────

import fcntl
lock_path = WORK_DIR / "results.lock"
with open(lock_path, "w") as lock_file:
    fcntl.flock(lock_file, fcntl.LOCK_EX)
    # Re-read inside lock to pick up concurrent writes
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    # Re-find our entry after re-read
    for i in range(len(results) - 1, -1, -1):
        if results[i].get("home") == HOME and results[i].get("away") == AWAY and not results[i].get("reflected"):
            entry_idx = i
            break
    results[entry_idx].update({
        "result": result_data,
        "correct": correct,
        "evaluation": evaluation,
        "reflected": True,
        "reflected_at": datetime.now(timezone.utc).isoformat(),
        "strategy_after": new_strategy,
    })
    tmp = results_path.with_suffix(f".tmp.{HOME}_{AWAY}")
    tmp.write_text(json.dumps(results, indent=2))
    tmp.replace(results_path)
    fcntl.flock(lock_file, fcntl.LOCK_UN)
log("Updated results.json")

try:
    git_env = _git_env()
    subprocess.run(
        ["git", "add", "results.json", "strategy.md"],
        cwd=WORK_DIR, check=True, capture_output=True, env=git_env,
    )
    subprocess.run(
        ["git", "commit", "-m", f"reflect: {MATCH}"],
        cwd=WORK_DIR, check=True, capture_output=True, env=git_env,
    )
    subprocess.run(["git", "push", "origin", "master"], cwd=WORK_DIR, check=True, capture_output=True, env=git_env)
    log("Pushed to GitHub")
    subprocess.run(["git", "push", "hf", "master:main"], cwd=WORK_DIR, check=True, capture_output=True, env=git_env)
    log("Pushed to HF Space — dashboard updating")
except Exception as e:
    err("Git push failed (files saved locally): %s", e)

discord_notify.notify_outcome(
    match=MATCH, home=HOME, away=AWAY,
    home_score=result_data["home_score"], away_score=result_data["away_score"],
    pick=pick, correct=correct,
    research_cost=entry.get("research_cost", 0),
    evaluation=evaluation, new_strategy_snippet=new_strategy,
)

outcome_str = "✓ CORRECT" if correct else "✗ INCORRECT"
print(f"\n{'='*50}")
print(f"REFLECTION: {MATCH}")
print(f"  Result:     {HOME} {result_data['home_score']}-{result_data['away_score']} {AWAY}")
print(f"  Predicted:  {pick.upper()} → {outcome_str}")
print(f"  Research:   ${entry.get('research_cost', 0):.4f} spent")
print(f"\nStrategy update (first 200 chars):")
print(f"  {new_strategy[:200]}...")
print(f"{'='*50}\n")
