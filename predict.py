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

if len(sys.argv) < 3:
    print("Usage: python predict.py HOME AWAY [KICKOFF_UTC]")
    print("Example: python predict.py NED JPN 2026-06-14T20:00Z")
    sys.exit(1)

HOME = sys.argv[1].upper()
AWAY = sys.argv[2].upper()
MATCH = f"{HOME} vs {AWAY}"

# Optional kickoff override — used for retroactive predictions
KICKOFF_OVERRIDE = sys.argv[3] if len(sys.argv) > 3 else None
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

# Resolve kickoff from schedule or override
kickoff = datetime.now(timezone.utc).isoformat()
for fixture in schedule:
    if fixture.get("home") == HOME and fixture.get("away") == AWAY:
        kickoff = fixture.get("kickoff_utc", kickoff)
        break
if KICKOFF_OVERRIDE:
    kickoff = KICKOFF_OVERRIDE

# Detect retroactive run — if kickoff is in the past, research must be blinded
kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
RETROACTIVE = kickoff_dt < datetime.now(timezone.utc)
if RETROACTIVE:
    log("RETROACTIVE MODE — kickoff was %s, constraining research to pre-match sources only", kickoff)

# ── Step 2: Fetch service directory ────────────────────────────────────────

network = os.getenv("NETWORK", "base-mainnet")
services = []
try:
    resp = requests.get("https://x402-list.com/api/v1/services", timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    all_services = payload if isinstance(payload, list) else payload.get("data", [])
    network_code = "BSE" if network == "base-mainnet" else "BSE-SEPOLIA"
    services = [s for s in all_services if network_code in s.get("networks", []) and s.get("status") == "online"]
    log("Service directory: %d services available for %s", len(services), network)
except Exception as e:
    err("Service directory fetch failed: %s — proceeding without paid data", e)

# ── Step 3: Agent plans research ───────────────────────────────────────────

recent_results = results[-3:] if results else []

# Enrich services with actual endpoint paths from their OpenAPI specs
def _get_endpoints(base_url):
    try:
        spec = requests.get(f"{base_url}/openapi.json", timeout=5).json()
        out = []
        for path, methods in spec.get("paths", {}).items():
            for method, detail in methods.items():
                if method.upper() == "GET":
                    price = detail.get("x-price-usd") or detail.get("x-x402-price")
                    out.append({
                        "url": base_url.rstrip("/") + path,
                        "summary": detail.get("summary", ""),
                        "price_usd": float(price) if price else None,
                        "params": [p["name"] for p in detail.get("parameters", []) if p.get("in") == "query"],
                    })
        return out
    except Exception:
        return []

service_summary = []
for s in services:
    endpoints = _get_endpoints(s["base_url"])
    service_summary.append({
        "name": s["name"],
        "base_url": s["base_url"],
        "description": s["description"][:200],
        "category": s.get("category", ""),
        "min_price_usd": s.get("min_price_usd", "unknown"),
        "endpoints": endpoints,
    })

home_name = next((f.get("home_name", HOME) for f in schedule if f.get("home") == HOME and f.get("away") == AWAY), HOME)
away_name = next((f.get("away_name", AWAY) for f in schedule if f.get("home") == HOME and f.get("away") == AWAY), AWAY)

REQUIRED_CATEGORIES = ["FORM", "PLAYERS", "TACTICS", "H2H", "CONTEXT", "MARKET", "NEWS", "VENUE"]

# ── Stage 1: Analyst — what do we need to know? (no services shown yet) ───

retroactive_note = f"""
IMPORTANT — RETROACTIVE PREDICTION: This match kicked off at {kickoff} and has already finished.
You are simulating the analysis as if it were BEFORE the match. Focus on pre-match factors only:
squad form, historical H2H, tactical tendencies, group context, known injury news from before kickoff.
Do NOT ask questions about the actual result or post-match events.
""" if RETROACTIVE else ""

stage1_prompt = f"""You are a professional football analyst preparing to predict {home_name} vs {away_name}.
Kickoff: {kickoff}
{retroactive_note}
Before looking at any data sources, list every specific question you need answered
to make a high-quality prediction. Be granular and specific, not generic.

Good examples:
- Is {home_name}'s first-choice striker fit after the qualifying campaign?
- How does {away_name} defend against high-pressing European-style teams?
- What does each team need from this match given group standings?
- What are the current betting odds and what do they imply about expected outcome?
- What is the weather in the host city and does it favor a particular style?

List 8-12 specific questions grouped by these exact categories:
FORM, PLAYERS, TACTICS, H2H, CONTEXT, MARKET, NEWS, VENUE

Format your response as:
FORM
- question
- question

PLAYERS
- question
...etc"""

information_needs = ""
try:
    log("Stage 1: Analyst identifying information needs...")
    information_needs = gemini.generate(stage1_prompt)
    log("Stage 1 complete — information needs identified")

    # Ensure all required categories are covered
    missing = [c for c in REQUIRED_CATEGORIES if c not in information_needs.upper()]
    if missing:
        information_needs += f"\n\nAlso ensure coverage of these categories: {', '.join(missing)}"
        log("Added missing categories: %s", missing)
except Exception as e:
    err("Stage 1 failed: %s", e)
    information_needs = "\n".join(f"{c}\n- General {c.lower()} information" for c in REQUIRED_CATEGORIES)

log("Information needs:\n%s", information_needs)

# ── Stage 2: Shopper — map needs to available services ────────────────────

research_plan = []
research_gaps = []  # needs with no matching service

if services:
    retroactive_research_note = f"""
CRITICAL — RETROACTIVE BLINDING: This match kicked off at {kickoff}.
You must ONLY fetch sources that contain PRE-MATCH information:
  ✓ ALLOWED: Historical stats pages (FBref, Transfermarkt), Wikipedia team pages,
              pre-tournament squad lists, H2H history pages, pre-match previews
              published BEFORE {kickoff[:10]}, GDELT queries about team form/history
  ✗ FORBIDDEN: Anything that might show the score or result — avoid live scoreboards,
               match reports, post-match analysis, or news searches likely to return results.
               Do NOT use queries containing words like "result", "score", "winner", "final".
               For GDELT: add "preview OR form OR squad" to queries to bias toward pre-match content.
""" if RETROACTIVE else ""

    stage2_prompt = f"""You identified these information needs for {home_name} vs {away_name}:

{information_needs}

Here is the complete x402 service directory with real endpoints:
{json.dumps(service_summary, indent=2)}

Your research budget: ${BUDGET:.2f} USDC
Your strategy so far: {strategy if strategy else "(none yet)"}
{retroactive_research_note}
Map each information need to the best available service.

KEY RULES:
1. ONLY use endpoint URLs that appear in the "endpoints" lists above — exact URLs only
2. For Skim (/api/v2/read or /api/v2/read/js): params must be {{"url": "https://real-page.com"}}
   - Good Skim targets: FBref team stats, Transfermarkt squad pages, Wikipedia, pre-match previews
   - Use /api/v2/read/js for pages that require JavaScript rendering
3. For GDELT (/news/recent, /news/sentiment): params must be {{"query": "search terms"}}
4. Prioritize: PLAYERS/injuries > FORM > TACTICS > H2H > MARKET/odds > CONTEXT > NEWS > VENUE
5. Total cost must not exceed ${BUDGET:.2f} USDC
6. For each need with NO matching service, include it in a "gaps" field

Return ONLY valid JSON with this exact structure, no markdown:
{{
  "purchases": [
    {{
      "need": "the specific question this answers",
      "category": "FORM|PLAYERS|TACTICS|H2H|CONTEXT|MARKET|NEWS|VENUE",
      "url": "exact_endpoint_url",
      "params": {{}},
      "cost": 0.01,
      "why": "what intelligence this gives us"
    }}
  ],
  "gaps": [
    {{
      "need": "question that no available service can answer",
      "category": "FORM",
      "ideal_service": "description of what x402 service would be needed"
    }}
  ]
}}"""

    try:
        log("Stage 2: Mapping needs to services...")
        stage2_text = gemini.generate(stage2_prompt)
        raw = stage2_text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        stage2_result = json.loads(raw)
        research_plan = stage2_result.get("purchases", [])
        research_gaps = stage2_result.get("gaps", [])
        log("Stage 2 complete: %d purchases planned, %d gaps identified", len(research_plan), len(research_gaps))
        for gap in research_gaps:
            log("GAP [%s]: %s → needs: %s", gap.get("category"), gap.get("need"), gap.get("ideal_service"))
    except Exception as e:
        err("Stage 2 failed: %s — skipping paid data", e)
        research_plan = []

    # Remap field names from stage 2 format to internal format
    normalized_plan = []
    for item in research_plan:
        normalized_plan.append({
            "url": item.get("url", ""),
            "params": item.get("params", {}),
            "cost": item.get("cost", 0),
            "reason": item.get("why", item.get("need", "")),
            "need": item.get("need", ""),
            "category": item.get("category", ""),
        })
    research_plan = normalized_plan

# Validate: URL must start with a known service base_url
valid_base_urls = {s["base_url"].rstrip("/") for s in services}
def _url_is_valid(url):
    return any(url.startswith(base) for base in valid_base_urls)

before = len(research_plan)
research_plan = [p for p in research_plan if _url_is_valid(p.get("url", ""))]
if len(research_plan) < before:
    log("Removed %d hallucinated URLs not matching any known service", before - len(research_plan))

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
try:
reasoning = _parse(r"REASONING:\s*(.+)", full_reasoning, "Insufficient data for strong prediction")

log("Prediction: PICK=%s CONFIDENCE=%d", pick, confidence)
log("Reasoning: %s", reasoning)

# ── Step 6: Save state and push to GitHub ─────────────────────────────────

entry = {
    "match": MATCH,
    "home": HOME,
    "away": AWAY,
    "kickoff": kickoff,
    "strategy_snapshot": strategy,
    "information_needs": information_needs,
    "research_gaps": research_gaps,
    "services_planned": research_plan,
    "services_used": services_used,
    "research_cost": round(total_spent, 6),
    "wallet_before": round(balance, 4),
    "wallet_after": round(balance_after, 4),
    "prediction": {
        "pick": pick,
        "confidence": confidence,
        "reasoning": reasoning,
    },
    "full_reasoning": full_reasoning,
    "retroactive": RETROACTIVE,
    "result": None,
    "correct": None,
    "evaluation": None,
    "reflected": False,
}

import fcntl
lock_path = WORK_DIR / "results.lock"
with open(lock_path, "w") as lock_file:
    fcntl.flock(lock_file, fcntl.LOCK_EX)
    # Re-read inside lock to pick up any concurrent writes
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    results.append(entry)
    tmp = results_path.with_suffix(f".tmp.{HOME}_{AWAY}")
    tmp.write_text(json.dumps(results, indent=2))
    tmp.replace(results_path)
    fcntl.flock(lock_file, fcntl.LOCK_UN)
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
