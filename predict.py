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
import prediction_intel
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


def _git_env() -> dict:
    """Git subprocess env — drop stale GITHUB_TOKEN so gh auth credentials are used."""
    env = os.environ.copy()
    env.pop("GITHUB_TOKEN", None)
    return env


BUDGET = float(os.getenv("MATCH_RESEARCH_BUDGET", "0.50"))
MIN_SEARCH_CALLS = int(os.getenv("MIN_SEARCH_CALLS", "4"))  # Tavily + Brave baseline

TAVILY_URL = "https://api.signalfuse.co/v1/gateway/search/tavily"
BRAVE_URL = "https://api.signalfuse.co/v1/gateway/search/brave"
SWERVER_SEARCH_URL = "https://websearch--gw.swerver.net/search"

# ── Team source lookup (empirically verified working URLs on skim402) ─────────
#
# Skim402 WORKING sites: Transfermarkt, national-football-teams.com,
#   Soccerway, Guardian, BBC Sport, Flashscores, AP Sports
# Skim402 BLOCKED (403/404/500/JS-only): Wikipedia, FBref, WhoScored,
#   Sofascore, 11v11, ESPN, FIFA.com, Reuters, OddsPortal, Goal.com
# GDELT: use param 'topic' (NOT 'query') — 'query' returns 400
#         /news/sentiment and /news/entity-graph often 500 — prefer /news/recent
#
# Tuple: (tm_slug, tm_id, nft_id, guardian_slug)
#   tm_slug/tm_id → transfermarkt.com squad/results pages
#   nft_id        → national-football-teams.com country page
#   guardian_slug → theguardian.com/football/{slug}
TEAM_DATA = {
    "ALG": ("algerien",            3474,   12,    "algeria"),
    "ARG": ("argentinien",         3437,   4,     "argentina"),
    "AUS": ("australien",          3349,   16,    "australia"),
    "AUT": ("osterreich",          3347,   17,    "austria"),
    "BEL": ("belgien",             3382,   21,    "belgium"),
    "BIH": ("bosnien-herzegowina", 3348,   23,    "bosnia-herzegovina"),
    "BRA": ("brasilien",           3439,   30,    "brazil"),
    "CAN": ("kanada",              3409,   40,    "canada"),
    "CIV": ("elfenbeinküste",      3464,   107,   "ivory-coast"),
    "COD": ("dr-kongo",            3460,   50,    "dr-congo"),
    "COL": ("kolumbien",           3442,   51,    "colombia"),
    "CPV": ("kap-verde",           8225,   39,    "cape-verde"),
    "CRO": ("kroatien",            3358,   54,    "croatia"),
    "CUW": ("curacao",             12506,  192,   "curacao"),
    "CZE": ("tschechien",          3341,   57,    "czech-republic"),
    "ECU": ("ecuador",             3441,   63,    "ecuador"),
    "EGY": ("agypten",             3473,   64,    "egypt"),
    "ENG": ("england",             3317,   66,    "england"),
    "ESP": ("spanien",             3375,   68,    "spain"),
    "FRA": ("frankreich",          3377,   75,    "france"),
    "GER": ("deutschland",         3262,   43,    "germany"),
    "GHA": ("ghana",               3472,   81,    "ghana"),
    "HAI": ("haiti",               3412,   85,    "haiti"),
    "IRN": ("iran",                3434,   96,    "iran"),
    "IRQ": ("irak",                3431,   97,    "iraq"),
    "JOR": ("jordanien",           14718,  102,   "jordan"),
    "JPN": ("japan",               3433,   101,   "japan"),
    "KOR": ("sudkorea",            3430,   113,   "south-korea"),
    "KSA": ("saudi-arabien",       3436,   173,   "saudi-arabia"),
    "MAR": ("marokko",             3476,   133,   "morocco"),
    "MEX": ("mexiko",              3411,   136,   "mexico"),
    "NED": ("niederlande",         3299,   147,   "netherlands"),
    "NOR": ("norwegen",            3294,   153,   "norway"),
    "NZL": ("neuseeland",          3354,   150,   "new-zealand"),
    "PAN": ("panama",              3413,   159,   "panama"),
    "PAR": ("paraguay",            3445,   160,   "paraguay"),
    "POR": ("portugal",            3361,   165,   "portugal"),
    "QAT": ("katar",               14919,  168,   "qatar"),
    "RSA": ("sudafrika",           3481,   197,   "south-africa"),
    "SCO": ("schottland",          3318,   174,   "scotland"),
    "SEN": ("senegal",             3480,   175,   "senegal"),
    "SUI": ("schweiz",             3350,   187,   "switzerland"),
    "SWE": ("schweden",            3293,   188,   "sweden"),
    "TUN": ("tunesien",            3486,   199,   "tunisia"),
    "TUR": ("turkei",              3376,   200,   "turkey"),
    "URU": ("uruguay",             3444,   208,   "uruguay"),
    "USA": ("vereinigte-staaten",  3410,   211,   "usa"),
    "UZB": ("usbekistan",          14941,  209,   "uzbekistan"),
}

# Always-available tournament-level URLs (no team ID needed)
STATIC_URLS = {
    "CONTEXT": [
        "https://int.soccerway.com/international/world/world-cup/2026/group-stage/r77543/",
        "https://www.flashscore.com/football/world/world-cup-2026/",
    ],
    "NEWS": [
        "https://www.bbc.com/sport/football/world-cup",
        "https://www.theguardian.com/football/world-cup-2026",
        "https://apnews.com/hub/soccer",
    ],
}

def _team_urls(code: str, full_name: str) -> dict[str, list[str]]:
    """Return verified-working skim402 URLs for a team, keyed by research category."""
    d = TEAM_DATA.get(code)
    # safe name for national-football-teams.com (spaces → hyphens)
    nft_name = full_name.replace(" ", "-")
    urls: dict[str, list[str]] = {cat: list(v) for cat, v in STATIC_URLS.items()}
    for cat in ("FORM", "PLAYERS", "TACTICS", "H2H", "MARKET", "VENUE"):
        urls.setdefault(cat, [])
    if d:
        slug, tm_id, nft_id, guardian = d
        urls["FORM"] += [
            f"https://www.transfermarkt.com/{slug}/spielplandatum/verein/{tm_id}/plus/0/saison_id/2025",
            f"https://www.national-football-teams.com/country/{nft_id}/{nft_name}.html",
        ]
        urls["PLAYERS"] += [
            f"https://www.transfermarkt.com/{slug}/kader/verein/{tm_id}/saison_id/2025",
            f"https://www.national-football-teams.com/country/{nft_id}/{nft_name}.html",
        ]
        urls["TACTICS"] += [
            f"https://www.transfermarkt.com/{slug}/leistungsdaten/verein/{tm_id}/reldata/WM26/saison/2025",
            f"https://int.soccerway.com/teams/{code.lower()}/{slug}/{tm_id}/matches/",
        ]
        urls["H2H"] += [
            f"https://www.national-football-teams.com/country/{nft_id}/{nft_name}.html",
        ]
        urls["NEWS"] = urls.get("NEWS", []) + [
            f"https://www.theguardian.com/football/{guardian}",
        ]
    return urls

# ── Supplemental services not in x402-list.com directory ─────────────────────
# Verified live via 402 payment headers — prices confirmed from `amount` field.
# Use method="post" + body={} for POST endpoints; method="get" + params={} for GET.
SUPPLEMENTAL_SERVICES = [
    {
        "name": "SignalFuse — Tavily AI Search",
        "base_url": "https://api.signalfuse.co",
        "description": "AI-powered web search via Tavily — returns top results with full text snippets, optimised for agent research. Use for: match previews, squad news, injury reports.",
        "category": "Search",
        "min_price_usd": 0.012,
        "endpoints": [
            {
                "url": "https://api.signalfuse.co/v1/gateway/search/tavily",
                "method": "post",
                "summary": "Tavily AI web search — returns title, url, content snippets",
                "price_usd": 0.012,
                "body_fields": {"query": "string (required)", "search_depth": "basic|advanced", "max_results": "int (default 5)", "topic": "general|news"},
                "example_body": {"query": "Germany World Cup 2026 squad injuries", "search_depth": "basic", "max_results": 5, "topic": "news"},
            }
        ],
    },
    {
        "name": "SignalFuse — Brave Search",
        "base_url": "https://api.signalfuse.co",
        "description": "Premium web search via Brave Search API — structured results with title, url, description. Good for finding specific team pages and news articles.",
        "category": "Search",
        "min_price_usd": 0.008,
        "endpoints": [
            {
                "url": "https://api.signalfuse.co/v1/gateway/search/brave",
                "method": "get",
                "summary": "Brave web search — returns web results with title, url, description",
                "price_usd": 0.008,
                "params": ["q", "count"],
                "example_params": {"q": "Germany World Cup 2026 squad", "count": 5},
            }
        ],
    },
    {
        "name": "Swerver — Headless Browser Search",
        "base_url": "https://websearch--gw.swerver.net",
        "description": "Fast headless browser web search (~100ms). Returns structured results with title, url, snippet. Good fallback when other search fails.",
        "category": "Search",
        "min_price_usd": 0.01,
        "endpoints": [
            {
                "url": "https://websearch--gw.swerver.net/search",
                "method": "post",
                "summary": "Web search via headless browser — returns structured results",
                "price_usd": 0.01,
                "body_fields": {"query": "string (required)", "count": "int (default 5)"},
                "example_body": {"query": "Germany World Cup 2026 squad injuries Musiala", "count": 5},
            },
            {
                "url": "https://websearch--gw.swerver.net/scrape",
                "method": "post",
                "summary": "Scrape any URL via headless browser — returns markdown/text content",
                "price_usd": 0.01,
                "body_fields": {"url": "string (required)", "format": "markdown|html|text", "max_length": "int"},
                "example_body": {"url": "https://www.transfermarkt.com/...", "format": "markdown"},
            },
        ],
    },
]

# ── Baseline search plan (always run — not optional) ─────────────────────────

def _plan_key(item: dict) -> str:
    """Unique key for deduplicating research plan entries."""
    url = item.get("url", "")
    params = json.dumps(item.get("params") or {}, sort_keys=True)
    body = json.dumps(item.get("body") or {}, sort_keys=True)
    return f"{url}|{params}|{body}"


def _baseline_search_plan(home_name: str, away_name: str) -> list[dict]:
    """Mandatory Tavily/Brave searches covering every signal category."""
    match_label = f"{home_name} vs {away_name}"
    queries = [
        {
            "url": TAVILY_URL,
            "method": "post",
            "params": {},
            "body": {
                "query": f"{match_label} World Cup 2026 match preview tactics formation",
                "search_depth": "advanced",
                "max_results": 5,
                "topic": "news",
            },
            "cost": 0.012,
            "reason": "Baseline: match preview, tactics, predicted lineups",
            "need": "Comprehensive pre-match preview and tactical outlook",
            "category": "TACTICS",
        },
        {
            "url": TAVILY_URL,
            "method": "post",
            "params": {},
            "body": {
                "query": f"{match_label} World Cup 2026 squad injuries fitness team news",
                "search_depth": "advanced",
                "max_results": 5,
                "topic": "news",
            },
            "cost": 0.012,
            "reason": "Baseline: squad news, injuries, fitness updates",
            "need": "Player availability and camp news for both teams",
            "category": "PLAYERS",
        },
        {
            "url": BRAVE_URL,
            "method": "get",
            "params": {"q": f"{home_name} World Cup 2026 recent form results", "count": 5},
            "body": {},
            "cost": 0.008,
            "reason": f"Baseline: {home_name} recent form and results",
            "need": f"How has {home_name} performed in recent internationals?",
            "category": "FORM",
        },
        {
            "url": BRAVE_URL,
            "method": "get",
            "params": {"q": f"{away_name} World Cup 2026 recent form results", "count": 5},
            "body": {},
            "cost": 0.008,
            "reason": f"Baseline: {away_name} recent form and results",
            "need": f"How has {away_name} performed in recent internationals?",
            "category": "FORM",
        },
        {
            "url": BRAVE_URL,
            "method": "get",
            "params": {"q": f"{match_label} head to head history World Cup", "count": 5},
            "body": {},
            "cost": 0.008,
            "reason": "Baseline: head-to-head history and prior meetings",
            "need": "Historical H2H record and patterns between the teams",
            "category": "H2H",
        },
        {
            "url": BRAVE_URL,
            "method": "get",
            "params": {"q": f"{match_label} World Cup 2026 group standings context", "count": 5},
            "body": {},
            "cost": 0.008,
            "reason": "Baseline: group context and tournament stakes",
            "need": "Group standings and what each team needs from this match",
            "category": "CONTEXT",
        },
    ]
    return queries


def _merge_research_plans(baseline: list[dict], agent_plan: list[dict], budget: float) -> list[dict]:
    """Reserve budget for baseline searches, then fill with agent-chosen calls."""
    seen = {_plan_key(b) for b in baseline}
    merged = list(baseline)
    for item in agent_plan:
        key = _plan_key(item)
        if key not in seen:
            merged.append(item)
            seen.add(key)

    baseline_cost = sum(b.get("cost", 0) for b in baseline)
    if baseline_cost > budget:
        log("Baseline search cost $%.4f exceeds budget $%.2f — trimming baseline", baseline_cost, budget)
        trimmed = []
        running = 0.0
        for item in baseline:
            if running + item.get("cost", 0) <= budget:
                trimmed.append(item)
                running += item.get("cost", 0)
        baseline = trimmed
        baseline_cost = running

    remaining = budget - baseline_cost
    agent_only = [p for p in merged if _plan_key(p) not in {_plan_key(b) for b in baseline}]
    agent_only.sort(key=lambda x: x.get("cost", 0))

    final = list(baseline)
    agent_spent = 0.0
    for item in agent_only:
        cost = item.get("cost", 0)
        if agent_spent + cost <= remaining:
            final.append(item)
            agent_spent += cost
        else:
            log("Skipping %s ($%.4f) — would exceed budget after baseline", item.get("url"), cost)

    return final

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

recent_results = results[-3:] if results else []  # unused — kept for log compatibility

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

# Append supplemental services (not in directory but verified working)
service_summary.extend(SUPPLEMENTAL_SERVICES)

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

if service_summary:
    retroactive_research_note = f"""
CRITICAL — RETROACTIVE BLINDING: This match kicked off at {kickoff}.
You must ONLY fetch sources that contain PRE-MATCH information:
  ✓ ALLOWED: Transfermarkt squad/results pages, national-football-teams.com, Soccerway,
              Guardian team pages, BBC Sport, GDELT news (use broad topic terms + "preview OR squad OR form")
  ✗ FORBIDDEN: Anything that might show the actual score or result — avoid live scoreboards,
               match reports, post-match analysis. Do NOT use topics containing "result", "score", "winner".
""" if RETROACTIVE else ""

    # Pre-resolve verified working URLs for both teams
    home_urls = _team_urls(HOME, home_name)
    away_urls = _team_urls(AWAY, away_name)
    baseline_cost_est = sum(b.get("cost", 0) for b in _baseline_search_plan(home_name, away_name))
    agent_budget = max(0.0, BUDGET - baseline_cost_est)

    stage2_prompt = f"""You identified these information needs for {home_name} vs {away_name}:

{information_needs}

Here is the complete x402 service directory with real endpoints:
{json.dumps(service_summary, indent=2)}

Your research budget for ADDITIONAL calls: ${agent_budget:.2f} USDC
(${baseline_cost_est:.2f} is already reserved for mandatory Tavily/Brave baseline searches)
Your strategy so far: {strategy if strategy else "(none yet)"}
{retroactive_research_note}

══════════════════════════════════════════════
VERIFIED WORKING URLS — USE THESE FOR SKIM
(empirically tested; sources below are confirmed to return content)

Skim endpoint: https://skim402.com/api/v2/read
  params: {{"url": "<one of the URLs below>"}}

{home_name} ({HOME}) sources:
  FORM/RESULTS : {chr(10).join('  • ' + u for u in home_urls.get('FORM', []))}
  SQUAD/PLAYERS: {chr(10).join('  • ' + u for u in home_urls.get('PLAYERS', []))}
  TACTICS/STATS: {chr(10).join('  • ' + u for u in home_urls.get('TACTICS', []))}
  H2H HISTORY  : {chr(10).join('  • ' + u for u in home_urls.get('H2H', []))}
  NEWS         : {chr(10).join('  • ' + u for u in home_urls.get('NEWS', []))}

{away_name} ({AWAY}) sources:
  FORM/RESULTS : {chr(10).join('  • ' + u for u in away_urls.get('FORM', []))}
  SQUAD/PLAYERS: {chr(10).join('  • ' + u for u in away_urls.get('PLAYERS', []))}
  TACTICS/STATS: {chr(10).join('  • ' + u for u in away_urls.get('TACTICS', []))}
  H2H HISTORY  : {chr(10).join('  • ' + u for u in away_urls.get('H2H', []))}
  NEWS         : {chr(10).join('  • ' + u for u in away_urls.get('NEWS', []))}

Tournament/context (always works):
  • https://int.soccerway.com/international/world/world-cup/2026/group-stage/r77543/
  • https://www.flashscore.com/football/world/world-cup-2026/
  • https://www.bbc.com/sport/football/world-cup
  • https://www.theguardian.com/football/world-cup-2026
  • https://apnews.com/hub/soccer

GDELT endpoint: https://news-x402.com/news/recent
  method: GET  params: {{"topic": "search phrase", "hours": 48}}
  ⚠ Use param name "topic" (NOT "query") — "query" returns 400 errors
  ⚠ Prefer /news/recent only — /news/sentiment and /news/entity-graph are unreliable (500s)
  Example topics: "{home_name} World Cup 2026 squad" | "2026 World Cup injury news"

SEARCH ENDPOINTS (NEW — for NEWS, PLAYERS, FORM queries):
  SignalFuse Tavily — best for injury/squad news, AI-ranked results:
    url: https://api.signalfuse.co/v1/gateway/search/tavily
    method: POST  body: {{"query": "...", "search_depth": "basic", "max_results": 5, "topic": "news"}}
    cost: $0.012

  SignalFuse Brave — premium web search, structured results:
    url: https://api.signalfuse.co/v1/gateway/search/brave
    method: GET  params: {{"q": "...", "count": 5}}
    cost: $0.008

  Swerver Search — fast headless browser search:
    url: https://websearch--gw.swerver.net/search
    method: POST  body: {{"query": "...", "count": 5}}
    cost: $0.010

  Swerver Scrape — scrape any URL via headless browser (use when skim402 fails):
    url: https://websearch--gw.swerver.net/scrape
    method: POST  body: {{"url": "https://...", "format": "markdown"}}
    cost: $0.010

SITES TO AVOID for Skim (all return 403/404/500 or require JavaScript):
  ✗ Wikipedia — 500 server errors  ✗ FBref — 403  ✗ WhoScored/Sofascore/11v11 — 403
  ✗ ESPN/FIFA.com — JavaScript-only  ✗ Reuters/OddsPortal/Goal.com — 401/404
══════════════════════════════════════════════

Map each information need to the best service.

RULES:
1. For Skim (GET): only use URLs from the verified team lists above — no invented URLs
2. For search endpoints (Tavily/Brave/Swerver): write a specific query string for the match
3. For GDELT: use "topic" param (NOT "query"), prefer /news/recent only
4. For POST endpoints: put the request body in the "body" field (not "params")
5. Prioritize: PLAYERS/injuries > FORM > TACTICS > H2H > CONTEXT > NEWS > VENUE
6. MANDATORY: Include at least 2 Tavily POST searches AND 2 Brave GET searches in your plan.
   Search endpoints find real current articles — use them heavily for NEWS, PLAYERS, FORM, TACTICS.
   Skim/Transfermarkt pages often return wrong clubs or nav junk; search is more reliable.
7. Cover ALL 8 categories (FORM, PLAYERS, TACTICS, H2H, CONTEXT, MARKET, NEWS, VENUE) if budget allows
8. Total cost must not exceed ${agent_budget:.2f} USDC (baseline searches are added separately — plan agent calls only)
9. Aim for 4-6 additional purchases beyond the mandatory baseline searches
10. Write targeted queries — include team names, "World Cup 2026", and the specific signal (injuries, tactics, form)

Return ONLY valid JSON, no markdown:
{{
  "purchases": [
    {{
      "need": "the specific question this answers",
      "category": "FORM|PLAYERS|TACTICS|H2H|CONTEXT|MARKET|NEWS|VENUE",
      "url": "exact_endpoint_url",
      "method": "get",
      "params": {{}},
      "body": {{}},
      "cost": 0.002,
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
            "method": item.get("method", "get").lower(),
            "params": item.get("params", {}),
            "body": item.get("body", {}),
            "cost": item.get("cost", 0),
            "reason": item.get("why", item.get("need", "")),
            "need": item.get("need", ""),
            "category": item.get("category", ""),
        })
    research_plan = normalized_plan

# Validate: URL must start with a known service base_url (directory + supplemental)
valid_base_urls = {s["base_url"].rstrip("/") for s in services}
valid_base_urls |= {s["base_url"].rstrip("/") for s in SUPPLEMENTAL_SERVICES}
def _url_is_valid(url):
    return any(url.startswith(base) for base in valid_base_urls)

before = len(research_plan)
research_plan = [p for p in research_plan if _url_is_valid(p.get("url", ""))]
if len(research_plan) < before:
    log("Removed %d hallucinated URLs not matching any known service", before - len(research_plan))

# Always merge mandatory baseline Tavily/Brave searches (reserved budget)
baseline = _baseline_search_plan(home_name, away_name)
baseline_cost = sum(b.get("cost", 0) for b in baseline)
log("Baseline search plan: %d calls, $%.4f reserved", len(baseline), baseline_cost)
research_plan = _merge_research_plans(baseline, research_plan, BUDGET)

total_cost = sum(p.get("cost", 0) for p in research_plan)
log("Research plan: %d endpoints, estimated cost $%.4f", len(research_plan), total_cost)

# ── Skim402 response cleanup ─────────────────────────────────────────────────

_SKIM_NAV_MARKERS = (
    "/navigation/",
    "[DISCOVER]",
    "[![Transfermarkt]",
    "[TRANSFERS & RUMOURS]",
    "[MARKET VALUES]",
    "deadline-day banner",
    "banner-desktop",
    "banner-mobile",
    "cloudfront.net/",
    "tmsi.akamaized.net/head/",
)


def _is_skim_nav_junk(line: str) -> bool:
    """True for Transfermarkt header/nav/ad lines that precede page content."""
    s = line.strip()
    if not s:
        return True
    return any(m in s for m in _SKIM_NAV_MARKERS)


def _strip_skim_junk(markdown: str) -> str:
    """Drop everything before the first real content line in skim markdown."""
    lines = markdown.split("\n")
    for i, line in enumerate(lines):
        if not _is_skim_nav_junk(line):
            return "\n".join(lines[i:]).strip()
    return markdown.strip()


def _clean_skim_response(raw_text: str, source_url: str) -> str:
    """Parse skim402 JSON and return compact, nav-stripped text for Gemini."""
    if "skim402.com" not in source_url:
        return raw_text[:3000]
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text[:3000]

    markdown = payload.get("markdown") or payload.get("text") or ""
    if not isinstance(markdown, str) or not markdown.strip():
        return raw_text[:3000]

    cleaned_md = _strip_skim_junk(markdown)
    page_url = payload.get("finalUrl") or payload.get("url") or ""
    title = (payload.get("metadata") or {}).get("title") or ""
    parts = []
    if page_url:
        parts.append(f"URL: {page_url}")
    if title:
        parts.append(f"Title: {title}")
    parts.append(cleaned_md)
    return "\n".join(parts)[:3000]


_JUNK_DATA_MARKERS = (
    "SV Lieth", "Arthurlie FC", "Woodvale FC", "1.FC Quickborn",
    "Stay on Top of Football", "Soccerway is your go-to",
    "Les jeux d'argent", "deadline-day banner",
    "Not in squad during this season",
)


def _clean_search_response(raw_text: str, source_url: str) -> str:
    """Extract readable snippets from Tavily/Brave/Swerver search JSON."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text[:4000]

    parts = []
    if "tavily" in source_url:
        for r in data.get("results") or []:
            title = r.get("title", "")
            url = r.get("url", "")
            content = (r.get("content") or "")[:600]
            if title or content:
                parts.append(f"• {title}\n  {url}\n  {content}")
    elif "brave" in source_url:
        web = data.get("web") or {}
        for r in web.get("results") or []:
            title = r.get("title", "")
            url = r.get("url", "")
            desc = r.get("description") or ""
            if title or desc:
                parts.append(f"• {title}\n  {url}\n  {desc}")
        for r in (data.get("discussions") or {}).get("results") or []:
            title = r.get("title", "")
            url = r.get("url", "")
            desc = r.get("description") or ""
            if title or desc:
                parts.append(f"• [Discussion] {title}\n  {url}\n  {desc}")
    elif "swerver.net/search" in source_url:
        for r in data.get("results") or data.get("organic") or []:
            title = r.get("title", "")
            url = r.get("url", r.get("link", ""))
            snippet = r.get("snippet") or r.get("description") or ""
            if title or snippet:
                parts.append(f"• {title}\n  {url}\n  {snippet}")

    if parts:
        return "\n\n".join(parts)[:4000]
    return raw_text[:4000]


def _clean_response(raw_text: str, source_url: str) -> str:
    """Route response cleanup to the appropriate parser."""
    if "skim402.com" in source_url:
        return _clean_skim_response(raw_text, source_url)
    if any(x in source_url for x in ("signalfuse.co", "swerver.net")):
        return _clean_search_response(raw_text, source_url)
    return raw_text[:3000]


def _is_low_quality_data(data_text: str) -> bool:
    """Detect skim/nav junk or empty payloads that won't help prediction."""
    if not data_text or len(data_text.strip()) < 80:
        return True
    hits = sum(1 for m in _JUNK_DATA_MARKERS if m in data_text)
    return hits >= 2


# ── Step 4: Execute research (payments fire here) ──────────────────────────

context = []
total_spent = 0.0
services_used = []
failed_needs = []  # track for fallback

def _execute_svc(session, svc):
    """Fire one research call — GET or POST — and return response text."""
    url = svc["url"]
    method = svc.get("method", "get").lower()
    params = dict(svc.get("params") or {})
    body = svc.get("body") or {}

    # GDELT fix: enforce 'topic' param — Gemini sometimes outputs 'query' which returns 400
    if "news-x402.com/news/recent" in url and "query" in params:
        params["topic"] = params.pop("query")
        log("GDELT param fix: renamed 'query' → 'topic'")

    if method == "post":
        return session.post(url, json=body, timeout=20)
    else:
        return session.get(url, params=params, timeout=20)

if research_plan:
    try:
        session = wallet.get_x402_client()
        for svc in research_plan:
            url = svc["url"]
            cost = svc.get("cost", 0)
            try:
                time.sleep(1)
                r = _execute_svc(session, svc)
                r.raise_for_status()
                method_label = svc.get("method", "get").upper()
                log("paid $%.4f → %s %s", cost, method_label, url)
                data_text = _clean_response(r.text, url)
                if _is_low_quality_data(data_text):
                    log("Low-quality response from %s — will consider fallback search", url)
                    failed_needs.append(svc)
                context.append({"source": url, "cost": cost, "data": data_text})
                services_used.append({"source": url, "cost": cost, "reason": svc.get("reason", ""), "data": data_text})
                total_spent += cost
            except Exception as e:
                err("Failed %s: %s", url, e)
                failed_needs.append(svc)
    except Exception as e:
        err("x402 session setup failed: %s", e)

# ── Step 4b: Fallback research if majority of calls failed or data is junk ───
useful_count = sum(1 for s in services_used if not _is_low_quality_data(s.get("data", "")))
has_search = any("signalfuse.co" in s["source"] or "swerver.net/search" in s["source"] for s in services_used)
needs_fallback = (
    (failed_needs and len(failed_needs) > len(services_used))
    or useful_count < 2
    or not has_search
)

if needs_fallback and service_summary:
    log("Research quality low (%d useful / %d total, search=%s) — running fallback",
        useful_count, len(services_used), has_search)

    if failed_needs:
        failed_categories = list({f.get("category", "NEWS") for f in failed_needs})
    else:
        failed_categories = REQUIRED_CATEGORIES
    budget_remaining = BUDGET - total_spent

    # Build fallback URL pool from verified sources not yet tried
    tried_urls = {f["url"] for f in failed_needs} | {s["source"] for s in services_used}
    home_urls_fb = _team_urls(HOME, home_name)
    away_urls_fb = _team_urls(AWAY, away_name)
    all_verified = []
    for cat_urls in home_urls_fb.values():
        all_verified += cat_urls
    for cat_urls in away_urls_fb.values():
        all_verified += cat_urls
    untried_verified = [u for u in dict.fromkeys(all_verified) if u not in tried_urls]

    fallback_prompt = f"""Primary research for {home_name} vs {away_name} failed or returned low-quality data. Pick alternatives.

Failed or low-quality requests:
{json.dumps([{{"category": f["category"], "need": f["need"], "failed_url": f["url"]}} for f in failed_needs], indent=2)}

Categories still needed: {', '.join(failed_categories)}
Remaining budget: ${budget_remaining:.2f} USDC

PRIORITY: Use Tavily and Brave search endpoints first — they return real articles and are most reliable.

SEARCH ENDPOINTS (preferred):
  Tavily POST: {TAVILY_URL}
    body: {{"query": "...", "search_depth": "advanced", "max_results": 5, "topic": "news"}}
    cost: $0.012
  Brave GET: {BRAVE_URL}
    params: {{"q": "...", "count": 5}}
    cost: $0.008
  Swerver POST: {SWERVER_SEARCH_URL}
    body: {{"query": "...", "count": 5}}
    cost: $0.010

VERIFIED UNTRIED URLS (skim402 fallback only if search unavailable):
{chr(10).join('  • ' + u for u in untried_verified[:15])}

Tournament context (always available):
  • https://int.soccerway.com/international/world/world-cup/2026/group-stage/r77543/
  • https://www.bbc.com/sport/football/world-cup
  • https://www.theguardian.com/football/world-cup-2026

GDELT (if needed): https://news-x402.com/news/recent
  params: {{"topic": "search phrase", "hours": 48}}  ← use "topic", NOT "query"

Select up to 5 calls. Prefer at least 2 search endpoints (Tavily or Brave).

Return ONLY valid JSON (no markdown):
{{
  "purchases": [
    {{
      "need": "what question this answers",
      "category": "FORM|PLAYERS|TACTICS|H2H|CONTEXT|MARKET|NEWS|VENUE",
      "url": "exact_endpoint_url",
      "method": "get",
      "params": {{}},
      "body": {{}},
      "cost": 0.012,
      "why": "why this covers the failed category"
    }}
  ]
}}"""

    try:
        fallback_text = gemini.generate(fallback_prompt)
        raw = fallback_text.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        fallback_result = json.loads(raw)
        fallback_plan_raw = fallback_result.get("purchases", [])

        fallback_plan = [
            {
                "url": item.get("url", ""),
                "method": item.get("method", "get").lower(),
                "params": item.get("params", {}),
                "body": item.get("body", {}),
                "cost": item.get("cost", 0),
                "reason": item.get("why", item.get("need", "")),
                "need": item.get("need", ""),
                "category": item.get("category", ""),
            }
            for item in fallback_plan_raw
            if _url_is_valid(item.get("url", ""))
        ]
        log("Fallback plan: %d alternative endpoints", len(fallback_plan))

        fallback_session = wallet.get_x402_client()
        for svc in fallback_plan:
            url = svc["url"]
            cost = svc.get("cost", 0)
            if total_spent + cost > BUDGET:
                log("Skipping fallback %s — would exceed budget", url)
                continue
            try:
                time.sleep(1)
                r = _execute_svc(fallback_session, svc)
                r.raise_for_status()
                log("fallback paid $%.4f → %s %s", cost, svc.get("method","get").upper(), url)
                data_text = _clean_response(r.text, url)
                context.append({"source": url, "cost": cost, "data": data_text})
                services_used.append({"source": url, "cost": cost, "reason": svc.get("reason", ""), "data": data_text})
                total_spent += cost
            except Exception as e:
                err("Fallback also failed %s: %s", url, e)
    except Exception as e:
        err("Fallback research stage failed: %s", e)

balance_after = balance - total_spent
log("Research complete. Spent $%.4f. Estimated balance: $%.4f", total_spent, balance_after)

useful_count = sum(1 for s in services_used if not _is_low_quality_data(s.get("data", "")))

# ── Step 5: Intelligent prediction pipeline ────────────────────────────────

context_text = ""
if context:
    for c in context:
        context_text += f"\n--- {c['source']} (${c['cost']:.4f}) ---\n{c['data']}\n"
else:
    context_text = "(no paid research data purchased)"

learning_context = prediction_intel.build_learning_context(results)
fixture_context = prediction_intel.build_fixture_context(
    HOME, AWAY, home_name, away_name, schedule, results, kickoff,
)
espn_form = prediction_intel.fetch_espn_tournament_form(HOME, AWAY, kickoff)
log("Fixture context loaded; ESPN form: %d chars", len(espn_form))

synthesis = {}
stress_test = {}
try:
    log("Stage 3: Synthesizing evidence...")
    synthesis = prediction_intel.synthesize_evidence(
        MATCH, home_name, away_name, kickoff, strategy, context_text,
        learning_context, fixture_context, espn_form,
        useful_count, len(services_used), RETROACTIVE,
    )
    log("Stage 3 complete — data_quality=%s", synthesis.get("data_quality"))
except Exception as e:
    err("Stage 3 synthesis failed: %s", e)
    synthesis = {"data_quality": "low", "contradictions": [str(e)]}

try:
    log("Stage 4: Stress-testing evidence...")
    stress_test = prediction_intel.stress_test_evidence(
        MATCH, home_name, away_name, synthesis, strategy,
    )
    log(
        "Stage 4 complete — favorite=%s cap=%s draw_risk=%s",
        stress_test.get("favorite"),
        stress_test.get("confidence_cap"),
        stress_test.get("draw_risk"),
    )
except Exception as e:
    err("Stage 4 stress test failed: %s", e)
    stress_test = {"confidence_cap": 6, "draw_risk": "medium"}

stress_cap = stress_test.get("confidence_cap")
if isinstance(stress_cap, str) and stress_cap.isdigit():
    stress_cap = int(stress_cap)
elif not isinstance(stress_cap, int):
    stress_cap = None

log("Stage 5: Final calibrated prediction...")
full_reasoning = ""
parsed = None
for attempt in range(3):
    try:
        suffix = ""
        if attempt > 0:
            suffix = (
                "\n\nCRITICAL: End with HOME_PCT, DRAW_PCT, AWAY_PCT (sum 100), "
                "then PICK, CONFIDENCE, CONFIDENCE_REASON, REASONING."
            )
        pred_resp_text = prediction_intel.make_final_prediction(
            MATCH, HOME, AWAY, home_name, away_name, kickoff,
            strategy, synthesis, stress_test, useful_count, len(services_used),
        ) + suffix
        if pred_resp_text.strip() and re.search(r"PICK:\s*(home|away|draw)", pred_resp_text, re.I):
            parsed = prediction_intel.parse_prediction_response(pred_resp_text, stress_cap)
            full_reasoning = pred_resp_text
            break
        err("Prediction attempt %d: missing PICK line", attempt + 1)
    except Exception as e:
        err("Prediction attempt %d failed: %s", attempt + 1, e)

if parsed is None:
    parsed = {
        "pick": "home",
        "confidence": 4,
        "confidence_reason": "Pipeline failed — low-confidence fallback",
        "reasoning": "Could not complete prediction pipeline",
        "probabilities": {"home": 40, "draw": 30, "away": 30},
        "full_reasoning": full_reasoning or "",
    }

pick = parsed["pick"]
confidence = parsed["confidence"]
confidence_reason = parsed["confidence_reason"]
reasoning = parsed["reasoning"]
probabilities = parsed["probabilities"]

log(
    "Prediction: PICK=%s CONFIDENCE=%d probs=%s",
    pick, confidence, probabilities,
)
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
        "confidence_reason": confidence_reason,
        "reasoning": reasoning,
        "probabilities": probabilities,
    },
    "evidence_synthesis": synthesis,
    "stress_test": stress_test,
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
    # Re-read inside lock; replace prior unreflected prediction (keep reflected entries)
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    results = [
        r for r in results
        if not (r.get("home") == HOME and r.get("away") == AWAY and not r.get("reflected", False))
    ]
    results.append(entry)
    tmp = results_path.with_suffix(f".tmp.{HOME}_{AWAY}")
    tmp.write_text(json.dumps(results, indent=2))
    tmp.replace(results_path)
    fcntl.flock(lock_file, fcntl.LOCK_UN)
log("Saved prediction to results.json")

try:
    git_env = _git_env()
    subprocess.run(["git", "add", "results.json"], cwd=WORK_DIR, check=True, capture_output=True, env=git_env)
    subprocess.run(
        ["git", "commit", "-m", f"predict: {MATCH}"],
        cwd=WORK_DIR, check=True, capture_output=True, env=git_env,
    )
    subprocess.run(["git", "push", "origin", "master"], cwd=WORK_DIR, check=True, capture_output=True, env=git_env)
    log("Pushed to GitHub")
    subprocess.run(["git", "push", "hf", "master:main"], cwd=WORK_DIR, check=True, capture_output=True, env=git_env)
    log("Pushed to HF Space — dashboard updating")
except Exception as e:
    err("Git push failed (prediction saved locally): %s", e)

discord_notify.notify_prediction(
    match=MATCH, pick=pick, confidence=confidence,
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
