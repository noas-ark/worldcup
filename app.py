"""World Cup Prediction Agent — Web UI.

FastAPI app deployed on Render. Reads flat files from disk.
Start with: uvicorn app:app --host 0.0.0.0 --port $PORT
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="World Cup Prediction Agent")


def _load_results() -> list[dict]:
    p = BASE / "results.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _load_strategy() -> str:
    p = BASE / "strategy.md"
    return p.read_text() if p.exists() else ""


def _load_schedule() -> list[dict]:
    p = BASE / "schedule.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _record_stats(results: list[dict]) -> dict:
    completed = [r for r in results if r.get("correct") is not None]
    wins = sum(1 for r in completed if r.get("correct"))
    total = len(completed)
    return {
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "pct": f"{wins/total*100:.0f}%" if total else "—",
    }


def _upcoming(schedule: list[dict], results: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    predicted = {(r["home"], r["away"]) for r in results}
    upcoming = []
    for f in schedule:
        k = f.get("kickoff_utc", "")
        if not k:
            continue
        try:
            dt = datetime.fromisoformat(k.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt > now and (f["home"], f["away"]) not in predicted:
            upcoming.append({**f, "kickoff_dt": dt})
    return sorted(upcoming, key=lambda x: x["kickoff_dt"])[:10]


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    results = list(reversed(_load_results()))
    strategy = _load_strategy()
    schedule = _load_schedule()
    stats = _record_stats(results)
    upcoming = _upcoming(schedule, _load_results())
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "results": results,
            "strategy": strategy,
            "stats": stats,
            "upcoming": upcoming,
        },
    )


@app.get("/match/{match_key}", response_class=HTMLResponse)
async def match_detail(request: Request, match_key: str):
    home, _, away = match_key.partition("_")
    home, away = home.upper(), away.upper()
    results = _load_results()
    entry = next(
        (r for r in reversed(results) if r.get("home") == home and r.get("away") == away),
        None,
    )
    if not entry:
        raise HTTPException(status_code=404, detail=f"No prediction found for {home} vs {away}")
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "detail": entry, "results": [], "strategy": "", "stats": {}, "upcoming": []},
    )


@app.get("/strategy", response_class=HTMLResponse)
async def strategy_page(request: Request):
    strategy = _load_strategy()
    results = _load_results()
    history = [
        {"match": r.get("match"), "kickoff": r.get("kickoff"), "snapshot": r.get("strategy_snapshot", "")}
        for r in results
        if r.get("strategy_snapshot") is not None
    ]
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "strategy_page": True, "strategy": strategy, "strategy_history": history,
         "results": [], "stats": {}, "upcoming": []},
    )


@app.get("/api/results")
async def api_results():
    return _load_results()


@app.get("/api/schedule")
async def api_schedule():
    return _load_schedule()
