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

```
python predict.py HOME AWAY [KICKOFF_UTC]
# e.g. python predict.py NED JPN 2026-06-14T20:00Z
```

**Stage 1 — Analyst:** Gemini reads the current strategy document and the service directory of available x402 data endpoints, then produces a structured list of *information needs* (what it wants to know about the match) and a *research plan* (which endpoints to call and why, given the $0.50 per-match budget).

**Stage 2 — Shopper:** A second Gemini call takes the research plan and the actual OpenAPI specs of the available services, maps needs to real endpoints with their prices, and produces the final purchase list.

**Data fetch:** The agent calls each planned endpoint through an x402-aware `requests` session. When a server responds with HTTP 402, the client automatically signs and submits an on-chain USDC micropayment on Base, then retries — no manual payment step. Each response (up to 2,000 chars) is collected as context.

**Prediction:** A final Gemini call reasons over the purchased data, the strategy, and recent match history, then outputs:
- `PICK`: home / away / draw
- `CONFIDENCE`: 1–10
- `BET`: suggested stake in USD
- `REASONING`: one-sentence justification

Results are saved to `results.json`, a Discord notification is sent, and the commit is pushed to GitHub and the HF Space.

---

### 2. Reflect (`reflect.py`) — runs 2.5 hours after kickoff

```
python reflect.py HOME AWAY
# e.g. python reflect.py NED JPN
```

**Result fetch:** Polls the ESPN public scoreboard API to get the final score. Retries over the last 3 days to handle timezone offsets.

**Evaluator:** An independent Gemini call receives the prediction, the actual result, and the purchased data, and produces a critical evaluation: was the pick correct, which data was valuable, what was the decisive factor, and what should the agent learn.

**Reflector:** A second Gemini call rewrites the strategy document with exactly one change based on the evaluator's assessment, keeping all still-valid rules and noting which x402 endpoints have proven useful vs not.

**Commit:** Updates `results.json` and `strategy.md`, pushes to GitHub, pushes to the HF Space (so the live dashboard updates), and sends a Discord outcome notification.

---

## Self-improving strategy

`strategy.md` is the agent's accumulated knowledge — a short document (≤500 words) of rules and learnings. It grows one rule at a time, each tagged with the match that informed it. The predictor reads the full strategy before every match; the reflector updates it after every result.

The strategy also tracks which x402 data services have been useful across past matches, so the agent learns to allocate its $0.50 budget more efficiently over time.

---

## x402 payment system

The agent pays for data using USDC on Base (mainnet or testnet). Key pieces:

| File | Role |
|------|------|
| `setup_wallet.py` | One-time keypair generation; prints `.env` values to add |
| `wallet.py` | Balance check via Web3 + USDC contract; x402 session factory |

**Balance check:** At startup, `predict.py` reads the on-chain USDC balance by calling `balanceOf` on the USDC contract. If it's below $0.10, the run aborts.

**x402 session:** `wallet.get_x402_client()` returns a `requests.Session` wired with `ExactEvmScheme` for the configured chain. Any `GET` that returns `402 Payment Required` is handled automatically: the client signs a payment transaction with the wallet's private key, submits it on-chain, and retries the request — all transparent to the calling code.

**Cost tracking:** `total_spent` accumulates per-match. `balance_after = balance - total_spent` is an estimate (the on-chain balance is not re-fetched mid-run). Both figures are saved to `results.json` for analysis.

---

## Web dashboard (`app.py`)

FastAPI app deployed on HF Spaces. Three routes:

| Route | Content |
|-------|---------|
| `/` | Live dashboard: upcoming fixtures, all predictions with badges, x402 spend table, strategy snippet |
| `/match/HOME_AWAY` | Full detail: analyst needs, purchased endpoints with raw data, research gaps, Gemini reasoning, evaluation, strategy at prediction time |
| `/strategy` | Current strategy + full evolution history across all matches |
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

Matches are scheduled automatically with cron via `schedule_match.py`:

```bash
# Schedule a single match (adds two cron entries: predict + reflect)
python schedule_match.py NED JPN 2026-06-14T20:00:00Z

# Or use setup_schedule.py to load from schedule.json in bulk
python setup_schedule.py
```

Predict runs 30 minutes before kickoff; reflect runs 2 hours 30 minutes after kickoff. Logs go to `logs/HOME_AWAY.log`.

---

## Manual run

```bash
# Predict (can be run after kickoff with a past timestamp for retroactive mode)
python predict.py NED JPN 2026-06-14T20:00Z

# Reflect (after the match is complete)
python reflect.py NED JPN

# Run the dashboard locally
uvicorn app:app --reload --port 7860
```

Retroactive mode is automatically detected when the kickoff timestamp is in the past, and constrains research to pre-match sources only.

---

## File structure

```
predict.py          # Pre-match: research + prediction
reflect.py          # Post-match: result + evaluation + strategy update
app.py              # FastAPI web dashboard
wallet.py           # USDC balance check + x402 payment session
gemini.py           # Gemini REST API wrapper
discord_notify.py   # Discord bot notifications
setup_wallet.py     # One-time wallet keypair generation
schedule_match.py   # Add cron entries for a single match
setup_schedule.py   # Bulk-load schedule.json into cron
results.json        # All predictions and outcomes (append-only)
strategy.md         # Agent's accumulated strategy (rewritten each match)
schedule.json       # Fixture list with kickoff times
```

---

## Dependencies

- **Gemini Flash** — two-stage reasoning (analyst → shopper → predictor; separate evaluator + reflector)
- **x402** — HTTP 402 micropayment protocol for real-time sports data
- **Web3 / eth-account** — Base chain interaction for balance checks and payment signing
- **FastAPI / uvicorn** — web dashboard
- **ESPN public API** — free post-match result fetching
