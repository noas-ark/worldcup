---
title: World Cup Predictions
emoji: ⚽
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# World Cup Prediction Agent

https://huggingface.co/spaces/Noaleetz/worldcup-predictor-hack

A self-improving match prediction agent for the 2026 FIFA World Cup. Before each match it autonomously purchases real-time sports data via [x402](https://x402.org) micropayments, reasons over that data with Gemini, records the result afterward, and updates its own strategy document so future predictions get better.

Live dashboard: deployed on Hugging Face Spaces (Docker).

---

## How it works

Each match goes through two automated phases:

### 1. Predict (`predict.py`) — runs 30 minutes before kickoff

```bash
python predict.py HOME AWAY [KICKOFF_UTC]
# e.g. python predict.py NED JPN
# optional kickoff override: python predict.py NED JPN 2026-06-14T20:00Z
```

Kickoff is read from `schedule.json` by default; pass `KICKOFF_UTC` only for retroactive re-runs.

**Stage 1 — Analyst:** Gemini lists 8–12 specific questions grouped by category (FORM, PLAYERS, TACTICS, H2H, CONTEXT, MARKET, NEWS, VENUE). No data services are shown yet — this is pure information-needs planning.

**Stage 2 — Shopper:** A second Gemini call receives those needs, the current strategy, and the full x402 service directory. It maps each need to concrete endpoints and prices, and flags any *research gaps* (needs with no available service).

**Baseline searches (always run):** Six mandatory Tavily/Brave search calls cover match preview, squad news, both teams' form, head-to-head, and group context. They cost **$0.056** (2× Tavily @ $0.012 + 4× Brave @ $0.008) and are always included in the plan first; the shopper stages additional calls against whatever remains of the per-match budget.

**Data fetch:** The agent calls each planned endpoint through an x402-aware `requests` session. When a server responds with HTTP 402, the client automatically signs and submits an on-chain USDC micropayment on Base, then retries. Responses are cleaned before being passed to the predictor — skim402 nav junk is stripped, and Tavily/Brave/Swerver JSON is condensed to readable snippets.

**Fallback research:** If most calls fail, return low-quality data, or no search results were obtained, a third Gemini call plans up to five alternative endpoints (preferring Tavily/Brave) within the remaining budget.

**Stage 3 — Synthesizer:** Gemini extracts structured evidence from purchased data plus free context — past learnings, group-stage neighbors, and ESPN tournament results — and flags data quality, contradictions, and key factors.

**Stage 4 — Stress-test:** A separate Gemini call challenges the synthesis: blind spots, underweighted factors, draw risk, and a `confidence_cap` (1–10) based on evidence gaps.

**Stage 5 — Predictor:** A final Gemini call produces calibrated win probabilities and a pick:
- `HOME_PCT` / `DRAW_PCT` / `AWAY_PCT`: integers summing to 100
- `PICK`: home / away / draw
- `CONFIDENCE`: 1–10 (respects the stress-test cap — not defaulted to 5)
- `CONFIDENCE_REASON`: one sentence explaining the confidence level
- `REASONING`: one-sentence justification for the pick

There is **no bet sizing** — the agent predicts outcomes only, not stake amounts. The dashboard shows pick, win probabilities, confidence (with hover tooltip for the reason), and research cost. Older entries in `results.json` may still have a legacy `bet` field from earlier runs.

Results are saved to `results.json`, a Discord notification is sent, and the commit is pushed to GitHub and the HF Space.

---

### 2. Reflect (`reflect.py`) — runs 2.5 hours after kickoff

```bash
python reflect.py HOME AWAY
# e.g. python reflect.py NED JPN
```

**Result fetch:** Polls the ESPN public scoreboard API to get the final score. Retries over the last 3 days to handle timezone offsets.

**Evaluator:** An independent Gemini call receives the prediction, actual result, and purchased endpoints. It writes a terse post-match note (≤120 words): what went wrong (if applicable), which data sources were useful vs useless, and no filler or markdown formatting.

**Reflector:** A second Gemini call rewrites `strategy.md` with exactly one new rule, keeping still-valid existing rules. The document has two sections — **Rules** (one sentence per match-informed rule) and **Data sources** (`use:` / `skip:` entries tagged with the match). Max 250 words.

**Commit:** Updates `results.json` and `strategy.md`, pushes to GitHub, pushes to the HF Space (so the live dashboard updates), and sends a Discord outcome notification.

---

## Research pipeline detail

### x402 data sources

The agent pulls from two layers:

1. **Service directory** — fetched live from [x402-list.com](https://x402-list.com/api/v1/services), filtered to online services on the configured network (Base mainnet or Sepolia). OpenAPI specs are fetched per service to discover real endpoint paths and prices.

2. **Supplemental services** — verified working endpoints not yet in the directory:

| Service | Endpoint | Cost | Use |
|---------|----------|------|-----|
| SignalFuse Tavily | `POST /v1/gateway/search/tavily` | $0.012 | AI-ranked news/previews, injury reports |
| SignalFuse Brave | `GET /v1/gateway/search/brave` | $0.008 | Structured web search |
| Swerver Search | `POST /search` | $0.010 | Fast headless browser search |
| Swerver Scrape | `POST /scrape` | $0.010 | Scrape any URL when skim402 fails |
| Skim402 | `GET /api/v2/read?url=...` | ~$0.002 | Read verified team/tournament pages |
| GDELT | `GET /news/recent?topic=...` | varies | Recent news by topic |

### Verified team URLs

For skim402 page reads, `predict.py` maintains a lookup table (`TEAM_DATA`) of empirically verified URLs per team — Transfermarkt squad/results pages, national-football-teams.com, Soccerway, and Guardian team pages. Sites known to fail (Wikipedia, FBref, ESPN, etc.) are excluded.

### Budget allocation

`MATCH_RESEARCH_BUDGET` defaults to **$0.50** per match (set in `.env`). All spending — baseline, agent-planned, and fallback — must stay within that cap.

```
MATCH_RESEARCH_BUDGET ($0.50 default)
├── Baseline searches ($0.056 — always merged first)
├── Agent-chosen calls (Skim402, GDELT, extra Tavily/Brave, etc.)
│   └── Shopper plans against ~$0.44 remaining after baseline
└── Fallback calls (if data quality is poor)
    └── Uses whatever is left: BUDGET − total_spent so far
```

**Wallet checks:** `predict.py` aborts if on-chain USDC balance is below **$0.10**. Recommended starting balance is **$2.00** (~4 matches at default budget). Actual spend per match varies — baseline alone is $0.056; with agent and fallback calls, recent matches typically land around **$0.08–$0.12**.

---

## Self-improving strategy

`strategy.md` is the agent's accumulated knowledge — a terse document (≤250 words) with **Rules** and **Data sources** sections. It grows one rule at a time, each tagged with the match that informed it. The predictor reads the full strategy before every match; the reflector updates it after every result.

The **Data sources** section tracks which x402 endpoints have proven useful vs not across past matches, so the agent learns to allocate its budget more efficiently over time.

To regenerate terse evaluations and rebuild strategy from scratch for all past reflections:

```bash
python backfill_learnings.py
```

---

## x402 payment system

The agent pays for data using USDC on Base (mainnet or testnet). Key pieces:

| File | Role |
|------|------|
| `setup_wallet.py` | One-time keypair generation; prints `.env` values to add |
| `wallet.py` | Balance check via Web3 + USDC contract; x402 session factory |

**Balance check:** At startup, `predict.py` reads the on-chain USDC balance by calling `balanceOf` on the USDC contract. If it's below $0.10, the run aborts.

**x402 session:** `wallet.get_x402_client()` returns a `requests.Session` wired with `ExactEvmScheme` for the configured chain. Any request that returns `402 Payment Required` is handled automatically: the client signs a payment transaction with the wallet's private key, submits it on-chain, and retries — all transparent to the calling code. Both GET and POST endpoints are supported.

**Cost tracking:** `research_cost`, `wallet_before`, and `wallet_after` are saved per match in `results.json`. `wallet_after` is an estimate (`balance − total_spent`); the on-chain balance is not re-fetched mid-run.

---

## Web dashboard (`app.py`)

FastAPI app deployed on HF Spaces. Renders HTML directly (inline templates, no Jinja2). Routes:

| Route | Content |
|-------|---------|
| `/` | Pipeline dashboard: awaiting prediction → predicted → awaiting reflection → reflected, with win/loss record, pick + win probabilities + confidence, x402 spend, strategy snippet |
| `/match/HOME_AWAY` | Full detail: analyst needs, purchased endpoints with raw data, research gaps, win model, full Gemini reasoning, evaluation, strategy at prediction time |
| `/strategy` | Current strategy (rendered markdown) + snapshot history across all matches |
| `/learnings` | Strategy evolution per reflection — line diffs and terse post-match evaluations |
| `/api/results` | Raw `results.json` as JSON |
| `/api/schedule` | Raw `schedule.json` as JSON |

Research gaps (intelligence needs with no matching x402 service) are surfaced as a demand signal for the x402 ecosystem.

---

## Setup

### 1. Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file:

```env
# AI
GEMINI_API_KEY=...

# Wallet (generate with setup_wallet.py)
WALLET_ADDRESS=0x...
WALLET_PRIVATE_KEY=0x...

# Network: base-mainnet (real USDC) or base-sepolia (testnet)
NETWORK=base-mainnet

# Budget per match in USD (default 0.50)
MATCH_RESEARCH_BUDGET=0.50

# Optional: Discord bot for notifications
DISCORD_BOT_TOKEN=...
```

### 3. Wallet setup

```bash
# Generate a new keypair and print .env values
python setup_wallet.py

# For testnet: set NETWORK=base-sepolia, then fund from faucets:
#   ETH (gas): coinbase.com/faucets/base-ethereum-goerli-faucet
#   USDC:       faucet.circle.com  (select Base Sepolia)

# For mainnet: transfer USDC to the printed address on Base
# Recommended minimum: $2.00
```

---

## Scheduling

Matches are scheduled automatically with cron.

```bash
# Fetch all WC 2026 fixtures from ESPN and schedule upcoming matches
python setup_schedule.py

# Preview without writing cron entries
python setup_schedule.py --dry-run

# Schedule a single match manually
python schedule_match.py NED JPN 2026-06-14T20:00:00Z
```

`setup_schedule.py` fetches fixtures from the ESPN public API, writes `schedule.json`, adds cron entries for all upcoming matches, and pushes the schedule to GitHub. Predict runs 30 minutes before kickoff; reflect runs 2 hours 30 minutes after kickoff. Logs go to `logs/HOME_AWAY.log`.

---

## Manual run

```bash
# Predict (kickoff read from schedule.json; pass timestamp for retroactive mode)
python predict.py NED JPN
python predict.py NED JPN 2026-06-14T20:00Z   # retroactive override

# Reflect (after the match is complete)
python reflect.py NED JPN

# Run the dashboard locally
uvicorn app:app --reload --port 7860
```

Retroactive mode is automatically detected when the kickoff timestamp is in the past, and constrains research to pre-match sources only (no live scoreboards or post-match reports).

---

## File structure

```
predict.py          # Pre-match: analyst → shopper → fetch → fallback → synthesize → stress-test → predict
prediction_intel.py # Stages 3–5: evidence synthesis, stress-test, calibrated prediction + parsing
reflect.py          # Post-match: result + terse evaluation + strategy update
backfill_learnings.py # Regenerate evaluations and rebuild strategy for past reflections
app.py              # FastAPI web dashboard (inline HTML)
wallet.py           # USDC balance check + x402 payment session
gemini.py           # Gemini REST API wrapper
discord_notify.py   # Discord bot notifications
setup_wallet.py     # One-time wallet keypair generation
schedule_match.py   # Add cron entries for a single match
setup_schedule.py   # Fetch ESPN fixtures + bulk-load cron + push schedule.json
make_thumbnail.py   # Generate HF Space thumbnail (1280×720)
results.json        # All predictions and outcomes (includes probabilities, synthesis, stress_test)
strategy.md         # Agent's accumulated strategy (Rules + Data sources, rewritten each match)
schedule.json       # Fixture list with kickoff times (from ESPN)
logs/               # Per-match cron output
```

---

## Dependencies

- **Gemini Flash** — multi-stage reasoning (analyst → shopper → synthesizer → stress-test → predictor; separate evaluator + reflector)
- **x402** — HTTP 402 micropayment protocol for real-time sports data and search APIs
- **Web3 / eth-account** — Base chain interaction for balance checks and payment signing
- **FastAPI / uvicorn** — web dashboard
- **markdown** — server-side strategy rendering
- **ESPN public API** — free fixture list, tournament form, and post-match result fetching
- **Pillow** — HF Space thumbnail generation
