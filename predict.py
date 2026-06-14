"""Predict match outcome. Run 30 min before kickoff.

Usage: python predict.py HOME AWAY
Example: python predict.py NED JPN
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import gemini
import requests
from dotenv import load_dotenv

import discord_notify
import wallet

# ── Setup ──────────────────────────────────────────────────────────────────

load_dotenv()

if len(sys.argv) != 3:
    print("Usage: python predict.py HOME AWAY")
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



BUDGET = float(os.getenv("MATCH_RESEARCH_BUDGET", "0.50"))

# ── Step 1: Load state ─────────────────────────────────────────────────────

log("=== predict.py %s ===", MATCH)

strategy_path = WORK_DIR / "strategy.md"
results_path = WORK_DIR / "results.json"
schedule_path = WORK_DIR / "schedule.json"

strategy = strategy_path.read_text() if strategy_path.exists() else ""
results = json.loads(results_path.read_text()) if results_path.exists() else []
schedule = json.loads(schedule_path.read_text()) if schedule_path.exists() else []

balance = wallet.get_balance()
log("Wallet balance: $%.4f USDC", balance)

if balance < 0.10:
    err("Balance $%.4f too low (min $0.10). Top up and retry.", balance)
    sys.exit(1)

# Resolve kickoff from schedule
kickoff = datetime.now(timezone.utc).isoformat()
for fixture in schedule:
    if fixture.get("home") == HOME and fixture.get("away") == AWAY:
        kickoff = fixture.get("kickoff_utc", kickoff)
        break

# ── Step 2: Fetch service directory ────────────────────────────────────────

network = os.getenv("NETWORK", "base-mainnet")
services = []
try:
    resp = requests.get("https://x402-list.com/api/v1/services", timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    all_services = payload if isinstance(payload, list) else payload.get("data", [])
    services = [s for s in all_services if network in s.get("networks", [])]
    log("Service directory: %d services available for %s", len(services), network)
except Exception as e:
    err("Service directory fetch failed: %s — proceeding without paid data", e)

# ── Step 3: Agent plans research ───────────────────────────────────────────

recent_results = results[-3:] if results else []

plan_prompt = f"""You are a World Cup betting research agent planning data purchases.

Match: {MATCH}
Kickoff: {kickoff}
Wallet balance: ${balance:.4f} USDC
Research budget cap: ${BUDGET:.2f} USDC

Current strategy:
{strategy if strategy else "(no strategy yet — first match)"}

Recent match history:
{json.dumps(recent_results, indent=2) if recent_results else "(no history yet)"}

Available x402 data services:
{json.dumps(services, indent=2) if services else "(no services available)"}

Decide which data endpoints to purchase. Return ONLY a valid JSON array (no markdown, no explanation).
Each item must have: url (string), params (object), cost (number in USDC), reason (one sentence).
Only include endpoints from the service list above.
Total cost must not exceed ${BUDGET:.2f} USDC.
If no services are available or none are useful, return an empty array: []

Example format:
[
  {{"url": "https://api.example.com/stats", "params": {{"team": "{HOME}"}}, "cost": 0.05, "reason": "Recent form data for {HOME}"}}
]"""

research_plan = []
if services:
    try:
        log("Asking Gemini to plan research purchases...")
        research_plan_text = gemini.generate(plan_prompt)
        raw = research_plan_text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        research_plan = json.loads(raw)
        log("Gemini planned %d service calls", len(research_plan))
    except Exception as e:
        err("Failed to parse Gemini research plan: %s — skipping paid data", e)
        research_plan = []

# Validate: remove URLs not in service directory, enforce budget
valid_urls = {
    endpoint["url"]
    for svc in services
    for endpoint in svc.get("endpoints", [])
}
research_plan = [p for p in research_plan if p.get("url") in valid_urls]

# Trim to budget (remove most expensive first)
research_plan.sort(key=lambda x: x.get("cost", 0))
total_cost = 0.0
trimmed_plan = []
for item in research_plan:
    if total_cost + item.get("cost", 0) <= BUDGET:
        trimmed_plan.append(item)
        total_cost += item.get("cost", 0)
    else:
        log("Skipping %s ($%.4f) — would exceed budget", item.get("url"), item.get("cost", 0))
research_plan = trimmed_plan

log("Research plan: %d endpoints, estimated cost $%.4f", len(research_plan), total_cost)

# ── Step 4: Execute research (payments fire here) ──────────────────────────

context = []
total_spent = 0.0
services_used = []

if research_plan:
    try:
        session = wallet.get_x402_client()
        for svc in research_plan:
            url = svc["url"]
            params = svc.get("params", {})
            cost = svc.get("cost", 0)
            try:
                time.sleep(1)
                r = session.get(url, params=params, timeout=15)
                r.raise_for_status()
                log("paid $%.4f → %s", cost, url)
                data_text = r.text[:2000]  # cap at 2000 chars
                context.append({"source": url, "cost": cost, "data": data_text})
                services_used.append({"source": url, "cost": cost, "reason": svc.get("reason", ""), "data": data_text})
                total_spent += cost
            except Exception as e:
                err("Failed %s: %s", url, e)
    except Exception as e:
        err("x402 session setup failed: %s", e)

balance_after = balance - total_spent
log("Research complete. Spent $%.4f. Estimated balance: $%.4f", total_spent, balance_after)

# ── Step 5: Make prediction ────────────────────────────────────────────────

context_text = ""
if context:
    for c in context:
        context_text += f"\n--- {c['source']} (${c['cost']:.4f}) ---\n{c['data']}\n"
else:
    context_text = "(no paid research data purchased)"

predict_prompt = f"""You are a World Cup match predictor. Analyze the following and make a prediction.

Match: {MATCH}
Home team: {HOME}
Away team: {AWAY}
Kickoff: {kickoff}
Remaining wallet balance after research: ${balance_after:.4f} USDC

Current strategy (your accumulated learnings):
{strategy if strategy else "(no strategy yet — first match)"}

Research data purchased:
{context_text}

Recent match history and outcomes:
{json.dumps(recent_results, indent=2) if recent_results else "(no history yet)"}

Analyze the match thoroughly, then end your response with EXACTLY these 4 lines:
PICK: [home|away|draw]
CONFIDENCE: [1-10]
BET: $[amount]
REASONING: [one sentence max]"""

log("Asking Gemini for prediction...")
try:
    pred_resp_text = gemini.generate(predict_prompt)
    full_reasoning = pred_resp_text
except Exception as e:
    err("Gemini prediction call failed: %s", e)
    full_reasoning = ""

# Parse structured fields
def _parse(pattern, text, default):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default

pick_raw = _parse(r"PICK:\s*(\w+)", full_reasoning, "home").lower()
pick = pick_raw if pick_raw in ("home", "away", "draw") else "home"
confidence_raw = _parse(r"CONFIDENCE:\s*(\d+)", full_reasoning, "5")
confidence = max(1, min(10, int(confidence_raw)))
bet_raw = _parse(r"BET:\s*\$?([\d.]+)", full_reasoning, "0.10")
try:
    bet = round(float(bet_raw), 2)
except ValueError:
    bet = 0.10
reasoning = _parse(r"REASONING:\s*(.+)", full_reasoning, "Insufficient data for strong prediction")

log("Prediction: PICK=%s CONFIDENCE=%d BET=$%.2f", pick, confidence, bet)
log("Reasoning: %s", reasoning)

# ── Step 6: Save state and push to GitHub ─────────────────────────────────

entry = {
    "match": MATCH,
    "home": HOME,
    "away": AWAY,
    "kickoff": kickoff,
    "strategy_snapshot": strategy,
    "services_planned": research_plan,
    "services_used": services_used,
    "research_cost": round(total_spent, 6),
    "wallet_before": round(balance, 4),
    "wallet_after": round(balance_after, 4),
    "prediction": {
        "pick": pick,
        "confidence": confidence,
        "bet": bet,
        "reasoning": reasoning,
    },
    "full_reasoning": full_reasoning,
    "result": None,
    "correct": None,
    "evaluation": None,
    "reflected": False,
}

results.append(entry)
tmp = results_path.with_suffix(".tmp")
tmp.write_text(json.dumps(results, indent=2))
tmp.replace(results_path)
log("Saved prediction to results.json")

try:
    subprocess.run(["git", "add", "results.json"], cwd=WORK_DIR, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"predict: {MATCH}"],
        cwd=WORK_DIR, check=True, capture_output=True,
    )
    subprocess.run(["git", "push", "origin", "master"], cwd=WORK_DIR, check=True, capture_output=True)
    log("Pushed to GitHub")
    subprocess.run(["git", "push", "hf", "master:main"], cwd=WORK_DIR, check=True, capture_output=True)
    log("Pushed to HF Space — dashboard updating")
except Exception as e:
    err("Git push failed (prediction saved locally): %s", e)

discord_notify.notify_prediction(
    match=MATCH, pick=pick, confidence=confidence, bet=bet,
    reasoning=reasoning, research_cost=total_spent,
    services_used=services_used, kickoff=kickoff,
)

print(f"\n{'='*50}")
print(f"PREDICTION: {MATCH}")
print(f"  Pick:       {pick.upper()} (confidence {confidence}/10)")
print(f"  Reasoning:  {reasoning}")
print(f"  Research:   ${total_spent:.4f} spent on {len(services_used)} endpoint(s)")
print(f"  Balance:    ${balance:.4f} → ~${balance_after:.4f}")
print(f"{'='*50}\n")
