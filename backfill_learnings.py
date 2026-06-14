"""Regenerate terse evaluations and rebuild strategy for past reflections."""

import json
from pathlib import Path

from dotenv import load_dotenv

import gemini

load_dotenv()

WORK_DIR = Path(__file__).parent
RESULTS_PATH = WORK_DIR / "results.json"
STRATEGY_PATH = WORK_DIR / "strategy.md"


def _eval_prompt(entry: dict) -> str:
    home, away = entry["home"], entry["away"]
    match = entry["match"]
    prediction = entry.get("prediction", {})
    result = entry["result"]
    pick = prediction.get("pick", "home")
    correct = pick == result["winner"]

    research_summary = ""
    for svc in entry.get("services_used", []):
        research_summary += f"\n- {svc['source']} (${svc['cost']:.4f}): {svc.get('reason', '')}"

    mistake_section = "" if correct else """MISTAKE:
- One sentence: what the pick got wrong.
- One sentence: the specific reasoning error.
"""

    return f"""Write a terse post-match learning note for a prediction agent.

Match: {match}
Result: {home} {result['home_score']}-{result['away_score']} {away} (winner: {result['winner']})
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


def _reflect_prompt(strategy: str, evaluation: str, match: str) -> str:
    return f"""Update the agent's strategy document. Write like engineering notes — terse, direct, no marketing language or dramatic rule names.

Current strategy:
{strategy if strategy else "(empty — first match)"}

Latest match note ({match}):
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


def main() -> None:
    results = json.loads(RESULTS_PATH.read_text())
    reflected = sorted(
        [r for r in results if r.get("reflected")],
        key=lambda r: r.get("reflected_at") or "",
    )
    if not reflected:
        print("No reflected entries to backfill.")
        return

    strategy = ""
    by_match = {r["match"]: r for r in results}

    for entry in reflected:
        match = entry["match"]
        print(f"Regenerating evaluation: {match}")
        evaluation = gemini.generate(_eval_prompt(entry)).strip()
        entry["evaluation"] = evaluation
        by_match[match]["evaluation"] = evaluation
        print(f"  → {len(evaluation)} chars")

        print(f"Rebuilding strategy after: {match}")
        strategy = gemini.generate(_reflect_prompt(strategy, evaluation, match)).strip()
        entry["strategy_after"] = strategy
        by_match[match]["strategy_after"] = strategy

    STRATEGY_PATH.write_text(strategy + "\n")
    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nDone. Updated {len(reflected)} reflections and strategy.md ({len(strategy)} chars).")


if __name__ == "__main__":
    main()
