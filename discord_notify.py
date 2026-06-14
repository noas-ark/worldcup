"""Discord notification helper. Requires DISCORD_BOT_TOKEN in env."""

import logging
import os

import requests

CHANNEL_ID = "1515805396575715409"


def _send(message: str) -> None:
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not token:
        logging.warning("DISCORD_BOT_TOKEN not set — skipping Discord notification")
        return
    try:
        resp = requests.post(
            f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"content": message},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        logging.error("Discord notify failed: %s", e)


def notify_prediction(match: str, pick: str, confidence: int,
                      reasoning: str, research_cost: float, services_used: list,
                      kickoff: str) -> None:
    pick_label = {"home": match.split(" vs ")[0], "away": match.split(" vs ")[1], "draw": "DRAW"}.get(pick, pick)
    lines = [
        f"⚽ **{match}** — Prediction",
        f"• Pick: **{pick_label.upper()}** (confidence {confidence}/10)",
        f"• Reasoning: {reasoning}",
        f"• Research: ${research_cost:.4f} spent on {len(services_used)} endpoint(s)",
        f"• Kickoff: {kickoff[:16].replace('T', ' ')} UTC",
    ]
    _send("\n".join(lines))


def notify_outcome(match: str, home: str, away: str, home_score: int, away_score: int,
                   pick: str, correct: bool, research_cost: float,
                   evaluation: str, new_strategy_snippet: str) -> None:
    result_icon = "✅" if correct else "❌"
    outcome_label = "CORRECT" if correct else "INCORRECT"
    actual = "home" if home_score > away_score else ("away" if away_score > home_score else "draw")
    actual_label = {"home": home, "away": away, "draw": "DRAW"}.get(actual, actual)
    pick_label = {"home": home, "away": away, "draw": "DRAW"}.get(pick, pick)

    # Grab first substantive line from evaluation as key learning
    learning = ""
    for line in evaluation.splitlines():
        line = line.strip().lstrip("0123456789.-) ").strip()
        if not line or line.endswith(":") or line.upper() in ("MISTAKE", "DATA"):
            continue
        if len(line) > 15:
            learning = line[:140]
            break

    strategy_snippet = new_strategy_snippet.strip()[:160].replace("\n", " ")

    lines = [
        f"{result_icon} **{match}** — Result {outcome_label}",
        f"• Score: {home} {home_score}–{away_score} {away}",
        f"• Predicted: {pick_label.upper()} → actual: {actual_label.upper()}",
        f"• Research cost: ${research_cost:.4f}",
    ]
    if learning:
        lines.append(f"• Key takeaway: {learning}")
    if strategy_snippet:
        lines.append(f"• Strategy update: {strategy_snippet}{'…' if len(new_strategy_snippet.strip()) > 160 else ''}")
    _send("\n".join(lines))
