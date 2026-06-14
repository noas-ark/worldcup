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

import google.generativeai as genai
import requests
from dotenv import load_dotenv

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

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

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

eval_prompt = f"""You are an independent evaluator assessing a World Cup match prediction.

Match: {MATCH}
Result: {HOME} {result_data['home_score']}-{result_data['away_score']} {AWAY}
Actual winner: {actual_winner}

Prediction that was made:
- Pick: {pick}
- Confidence: {prediction.get('confidence')}/10
- Reasoning: {prediction.get('reasoning')}

Research purchased (${entry.get('research_cost', 0):.4f} total):{research_summary if research_summary else " (none purchased)"}

Outcome: prediction was {'CORRECT' if correct else 'INCORRECT'}
Research cost: ${entry.get('research_cost', 0):.4f} USDC

Evaluate honestly:
1. Was the prediction correct? Why or why not?
2. Which purchased research was valuable (if any)?
3. What was the key factor that determined the outcome?
4. What should the agent learn from this match?

Be specific and critical. This evaluation will update the agent's strategy."""

log("Asking Gemini for evaluation...")
try:
    eval_resp = model.generate_content(eval_prompt)
    evaluation = eval_resp.text
except Exception as e:
    err("Gemini evaluation call failed: %s", e)
    evaluation = f"Evaluation unavailable: {e}"

# ── Step 4: Reflector call (updates strategy) ─────────────────────────────

recent_results = results[-5:]

reflect_prompt = f"""You are updating a World Cup prediction strategy document.

Current strategy (may be empty if this is the first match):
{strategy if strategy else "(empty — this is the first match)"}

Evaluator's assessment of the latest match ({MATCH}):
{evaluation}

Recent match history for context:
{json.dumps([{
    "match": r.get("match"),
    "pick": r.get("prediction", {}).get("pick"),
    "correct": r.get("correct"),
    "reasoning": r.get("prediction", {}).get("reasoning"),
} for r in recent_results], indent=2)}

Rewrite the strategy document with EXACTLY ONE change based on this match:
- Add a new rule, modify an existing rule, or remove an outdated rule
- Keep all still-valid rules from the current strategy
- Note which x402 data endpoints have been useful vs not useful
- Include the match that informed each rule (e.g., "NED vs JPN: ...")
- Stay under 500 words total

Return ONLY the updated strategy document text. No preamble, no explanation."""

log("Asking Gemini to update strategy...")
try:
    strat_resp = model.generate_content(reflect_prompt)
    new_strategy = strat_resp.text.strip()
except Exception as e:
    err("Gemini strategy update failed: %s", e)
    new_strategy = strategy  # keep current if update fails

strategy_path.write_text(new_strategy)
log("Updated strategy.md")

# ── Step 5: Update results.json and push to GitHub ─────────────────────────

results[entry_idx].update({
    "result": result_data,
    "correct": correct,
    "evaluation": evaluation,
    "reflected": True,
    "reflected_at": datetime.now(timezone.utc).isoformat(),
})

tmp = results_path.with_suffix(".tmp")
tmp.write_text(json.dumps(results, indent=2))
tmp.replace(results_path)
log("Updated results.json")

try:
    subprocess.run(
        ["git", "add", "results.json", "strategy.md"],
        cwd=WORK_DIR, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"reflect: {MATCH}"],
        cwd=WORK_DIR, check=True, capture_output=True,
    )
    subprocess.run(["git", "push", "origin", "master"], cwd=WORK_DIR, check=True, capture_output=True)
    log("Pushed to GitHub")
    subprocess.run(["git", "push", "hf", "master"], cwd=WORK_DIR, check=True, capture_output=True)
    log("Pushed to HF Space — dashboard updating")
except Exception as e:
    err("Git push failed (files saved locally): %s", e)

outcome_str = "✓ CORRECT" if correct else "✗ INCORRECT"
print(f"\n{'='*50}")
print(f"REFLECTION: {MATCH}")
print(f"  Result:     {HOME} {result_data['home_score']}-{result_data['away_score']} {AWAY}")
print(f"  Predicted:  {pick.upper()} → {outcome_str}")
print(f"  Research:   ${entry.get('research_cost', 0):.4f} spent")
print(f"\nStrategy update (first 200 chars):")
print(f"  {new_strategy[:200]}...")
print(f"{'='*50}\n")
