"""World Cup Prediction Agent — Web UI.

FastAPI app deployed on HF Spaces. Renders HTML directly (no Jinja2).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

BASE = Path(__file__).parent
app = FastAPI(title="World Cup Prediction Agent")

# FIFA 3-letter → ISO 2-letter → flag emoji
_FIFA_TO_ISO2 = {
    "NED": "NL", "JPN": "JP", "CIV": "CI", "ECU": "EC", "SWE": "SE",
    "TUN": "TN", "ESP": "ES", "CPV": "CV", "BEL": "BE", "EGY": "EG",
    "KSA": "SA", "URU": "UY", "IRN": "IR", "NZL": "NZ", "FRA": "FR",
    "SEN": "SN", "IRQ": "IQ", "NOR": "NO", "ARG": "AR", "ALG": "DZ",
    "AUT": "AT", "JOR": "JO", "POR": "PT", "COD": "CD", "ENG": "GB",
    "GHA": "GH", "PAN": "PA", "UZB": "UZ", "COL": "CO", "CZE": "CZ",
    "RSA": "ZA", "SUI": "CH", "BIH": "BA", "CAN": "CA", "QAT": "QA",
    "MEX": "MX", "KOR": "KR", "USA": "US", "AUS": "AU", "SCO": "GB",
    "MAR": "MA", "BRA": "BR", "HAI": "HT", "TUR": "TR", "PAR": "PY",
    "GER": "DE", "CUW": "CW", "CRO": "HR", "CRC": "CR", "IRE": "IE",
    "WLS": "GB", "DEN": "DK", "SRB": "RS", "POL": "PL", "SLO": "SI",
    "ROM": "RO", "HUN": "HU", "SVK": "SK", "GRE": "GR", "BUL": "BG",
    "CHL": "CL", "PER": "PE", "BOL": "BO", "VEN": "VE", "HON": "HN",
    "CUB": "CU", "JAM": "JM", "TRI": "TT", "CMR": "CM", "NGA": "NG",
    "MLI": "ML", "BFA": "BF", "GUI": "GN", "COG": "CG", "BEN": "BJ",
    "ZIM": "ZW", "ZAM": "ZM", "MOZ": "MZ", "ANG": "AO", "ETH": "ET",
    "TAN": "TZ", "UGA": "UG", "RWA": "RW", "CTA": "CF", "GAB": "GA",
    "IRQ": "IQ", "UAE": "AE", "KUW": "KW", "BHR": "BH", "OMA": "OM",
    "YEM": "YE", "SYR": "SY", "LIB": "LB", "PAL": "PS", "AFG": "AF",
    "IND": "IN", "BAN": "BD", "PAK": "PK", "SRI": "LK", "NEP": "NP",
    "THA": "TH", "VIE": "VN", "IDN": "ID", "MAS": "MY", "PHI": "PH",
    "CHN": "CN", "TPE": "TW", "HKG": "HK", "MAC": "MO", "MGL": "MN",
    "RUS": "RU", "UKR": "UA", "BLR": "BY", "KAZ": "KZ", "GEO": "GE",
    "ARM": "AM", "AZE": "AZ", "MDA": "MD", "LTU": "LT", "LAT": "LV",
    "EST": "EE", "FIN": "FI", "ISL": "IS", "IRL": "IE", "NIG": "NE",
}

def _flag(code: str) -> str:
    """Return flag emoji for a FIFA team code, or empty string."""
    iso2 = _FIFA_TO_ISO2.get(code.upper(), "")
    if not iso2 or len(iso2) != 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())

def _pick_display(pick: str, home: str, away: str) -> str:
    """Translate home/away/draw to team code."""
    if pick == "home":
        return home
    if pick == "away":
        return away
    return "DRAW"

def _team(code: str) -> str:
    """Team code with flag emoji."""
    flag = _flag(code)
    return f"{flag} {code}" if flag else code

CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d0d0d; color: #e0e0e0; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 14px; line-height: 1.6; }
a { color: #4dabf7; text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
header { border-bottom: 1px solid #333; padding-bottom: 16px; margin-bottom: 24px; }
header h1 { font-size: 20px; color: #fff; }
.meta { display: flex; gap: 24px; margin-top: 8px; color: #888; font-size: 12px; }
.meta span { color: #e0e0e0; }
h2 { font-size: 13px; color: #aaa; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; border-bottom: 1px solid #222; padding-bottom: 6px; }
.section { margin-bottom: 32px; }
.match-card { background: #111; border: 1px solid #2a2a2a; border-radius: 6px; margin-bottom: 16px; overflow: hidden; }
.match-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; background: #161616; border-bottom: 1px solid #222; }
.match-title { font-size: 15px; font-weight: bold; color: #fff; }
.match-time { font-size: 11px; color: #555; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold; }
.badge.correct { background: #1a3a1a; color: #4caf50; border: 1px solid #4caf50; }
.badge.incorrect { background: #3a1a1a; color: #f44336; border: 1px solid #f44336; }
.badge.pending { background: #1a1a3a; color: #888; border: 1px solid #444; }
.match-body { padding: 12px 16px; }
.pred-row { display: flex; gap: 24px; margin-bottom: 10px; flex-wrap: wrap; }
.pred-item .label { font-size: 10px; color: #555; text-transform: uppercase; }
.pred-item .value { font-size: 14px; color: #e0e0e0; }
.pred-item .value.pick { font-size: 16px; font-weight: bold; color: #fff; }
.reasoning { font-size: 12px; color: #888; font-style: italic; margin-bottom: 10px; }
.x402-label { font-size: 10px; color: #555; text-transform: uppercase; margin: 8px 0 4px; }
table.x402 { width: 100%; border-collapse: collapse; font-size: 12px; }
table.x402 th { text-align: left; color: #555; font-weight: normal; padding: 3px 6px; border-bottom: 1px solid #222; }
table.x402 td { padding: 4px 6px; color: #aaa; border-bottom: 1px solid #1a1a1a; vertical-align: top; }
table.x402 td.url { color: #4dabf7; font-size: 11px; word-break: break-all; max-width: 300px; }
table.x402 td.cost { color: #f9a825; white-space: nowrap; }
.no-data { font-size: 12px; color: #444; font-style: italic; }
.result-bar { margin-top: 10px; padding: 8px 12px; border-radius: 4px; font-size: 13px; }
.result-bar.correct { background: #0d1f0d; border-left: 3px solid #4caf50; }
.result-bar.incorrect { background: #1f0d0d; border-left: 3px solid #f44336; }
.result-score { font-weight: bold; color: #fff; }
.eval-text { font-size: 12px; color: #666; margin-top: 6px; }
.detail-link { font-size: 11px; color: #555; margin-top: 8px; display: block; }
.upcoming-item { background: #161616; border: 1px solid #2a2a2a; border-radius: 4px; padding: 8px 12px; display: flex; justify-content: space-between; margin-bottom: 6px; }
.strategy-box { background: #111; border: 1px solid #2a2a2a; border-radius: 6px; padding: 16px; }
pre { white-space: pre-wrap; word-wrap: break-word; color: #bbb; font-size: 13px; }
.full-text { font-size: 12px; color: #aaa; white-space: pre-wrap; background: #0a0a0a; border: 1px solid #1e1e1e; border-radius: 4px; padding: 12px; max-height: 400px; overflow-y: auto; }
.nav { margin-bottom: 20px; font-size: 13px; }
</style>
"""

def _load(filename, default):
    p = BASE / filename
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:
        return default

def _load_text(filename):
    p = BASE / filename
    return p.read_text() if p.exists() else ""

def _stats(results):
    done = [r for r in results if r.get("correct") is not None]
    w = sum(1 for r in done if r.get("correct"))
    t = len(done)
    return w, t - w, f"{w/t*100:.0f}%" if t else "—"

def _upcoming(schedule, results):
    now = datetime.now(timezone.utc)
    predicted = {(r["home"], r["away"]) for r in results}
    out = []
    for f in schedule:
        k = f.get("kickoff_utc", "")
        try:
            dt = datetime.fromisoformat(k.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt > now and (f["home"], f["away"]) not in predicted:
            out.append((dt, f))
    return [f for _, f in sorted(out, key=lambda x: x[0])[:8]]

def _badge(r):
    if r.get("correct") is True:
        return '<span class="badge correct">✓ CORRECT</span>'
    if r.get("correct") is False:
        return '<span class="badge incorrect">✗ INCORRECT</span>'
    return '<span class="badge pending">PENDING</span>'

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def _page(body, title="⚽ World Cup Prediction Agent"):
    results = _load("results.json", [])
    w, l, pct = _stats(results)
    nav = '<div class="nav"><a href="/">Dashboard</a> · <a href="/strategy">Strategy</a></div>'
    header = f"""
<header>
  <h1>⚽ World Cup Prediction Agent</h1>
  <div class="meta">
    <div>Record: <span>{w}W–{l}L ({pct})</span></div>
    <div>Matches predicted: <span>{len(results)}</span></div>
  </div>
</header>"""
    return HTMLResponse(f"<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title>{CSS}</head><body><div class='container'>{header}{nav}{body}</div></body></html>")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    results = list(reversed(_load("results.json", [])))
    schedule = _load("schedule.json", [])
    strategy = _load_text("strategy.md")
    upcoming = _upcoming(schedule, _load("results.json", []))

    html = ""

    # Upcoming
    if upcoming:
        items = ""
        for f in upcoming:
            items += f"""<div class="upcoming-item">
              <div><b>{_team(f['home'])} vs {_team(f['away'])}</b> <span style="color:#555;font-size:11px;margin-left:8px;">{_esc(f.get('stage',''))}</span></div>
              <div style="color:#666;font-size:12px;">{f['kickoff_utc'][:16].replace('T',' ')} UTC</div>
            </div>"""
        html += f'<div class="section"><h2>Upcoming</h2>{items}</div>'

    # Past matches
    if results:
        cards = ""
        for r in results:
            pred = r.get("prediction", {})
            res = r.get("result")
            used = r.get("services_used", [])
            planned = r.get("services_planned", [])

            x402_html = ""
            if used:
                rows = "".join(f'<tr><td class="url">{_esc(s["source"])}</td><td class="cost">${s["cost"]:.4f}</td><td>{_esc(s.get("reason",""))}</td></tr>' for s in used)
                x402_html = f'<div class="x402-label">x402 data purchased</div><table class="x402"><tr><th>Endpoint</th><th>Cost</th><th>Reason</th></tr>{rows}</table>'
            elif planned:
                x402_html = f'<div class="no-data">{len(planned)} endpoint(s) considered, none purchased.</div>'
            else:
                x402_html = '<div class="no-data">No x402 data for this match.</div>'

            result_html = ""
            if res:
                cls = "correct" if r.get("correct") else "incorrect"
                eval_snippet = _esc((r.get("evaluation") or "")[:180])
                result_html = f'''<div class="result-bar {cls}">
                  Result: <span class="result-score">{_team(r['home'])} {res['home_score']}–{res['away_score']} {_team(r['away'])}</span>
                  {f'<div class="eval-text">{eval_snippet}{"…" if len(r.get("evaluation",""))>180 else ""}</div>' if eval_snippet else ""}
                </div>'''

            cards += f"""<div class="match-card">
              <div class="match-header">
                <div>
                  <div class="match-title">{_team(r['home'])} vs {_team(r['away'])}</div>
                  <div class="match-time">{r.get("kickoff","")[:16].replace("T"," ")} UTC</div>
                </div>
                {_badge(r)}
              </div>
              <div class="match-body">
                <div class="pred-row">
                  <div class="pred-item"><div class="label">Pick</div><div class="value pick">{_team(_pick_display(pred.get('pick','?'), r['home'], r['away']))}</div></div>
                  <div class="pred-item"><div class="label">Confidence</div><div class="value">{pred.get("confidence","?")}/10</div></div>
                  <div class="pred-item"><div class="label">Bet</div><div class="value">${pred.get("bet","?")}</div></div>
                  <div class="pred-item"><div class="label">Research cost</div><div class="value" style="color:#f9a825;">${r.get("research_cost",0):.4f}</div></div>
                </div>
                <div class="reasoning">"{_esc(pred.get("reasoning",""))}"</div>
                {x402_html}
                {result_html}
                <a href="/match/{_esc(r['home'])}_{_esc(r['away'])}" class="detail-link">Full reasoning & reflection →</a>
              </div>
            </div>"""
        html += f'<div class="section"><h2>Predictions</h2>{cards}</div>'
    else:
        html += '<div style="color:#444;font-style:italic;padding:32px 0;">No predictions yet.</div>'

    # Strategy snippet
    if strategy:
        snippet = _esc(strategy[:500])
        more = ' <a href="/strategy">… read more</a>' if len(strategy) > 500 else ""
        html += f'<div class="section"><h2>Current Strategy <a href="/strategy" style="font-size:11px;color:#555;font-weight:normal;margin-left:8px;">full history →</a></h2><div class="strategy-box"><pre>{snippet}{more}</pre></div></div>'

    return _page(html)


@app.get("/match/{match_key}", response_class=HTMLResponse)
async def match_detail(match_key: str):
    home, _, away = match_key.partition("_")
    home, away = home.upper(), away.upper()
    results = _load("results.json", [])
    entry = next((r for r in reversed(results) if r.get("home") == home and r.get("away") == away), None)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No prediction found for {home} vs {away}")

    pred = entry.get("prediction", {})
    res = entry.get("result")
    used = entry.get("services_used", [])
    planned = entry.get("services_planned", [])

    result_html = ""
    if res:
        cls = "correct" if entry.get("correct") else "incorrect"
        result_html = f'<div class="result-bar {cls}" style="margin-bottom:16px;"><span class="result-score">{_team(home)} {res['home_score']}–{res['away_score']} {_team(away)}</span> &nbsp;{_badge(entry)}</div>'

    used_urls = {s["source"] for s in used}

    # Build per-endpoint cards for purchased data
    endpoint_cards = ""
    for s in used:
        data_content = _esc(s.get("data", "(no data saved)"))
        endpoint_cards += f"""
<div style="background:#0a0a0a;border:1px solid #2a2a2a;border-radius:4px;margin-bottom:12px;overflow:hidden;">
  <div style="background:#161616;padding:8px 12px;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center;">
    <div style="color:#4dabf7;font-size:12px;word-break:break-all;">{_esc(s['source'])}</div>
    <div style="color:#f9a825;font-size:12px;white-space:nowrap;margin-left:12px;">${s['cost']:.4f} USDC</div>
  </div>
  <div style="padding:8px 12px;">
    <div style="font-size:11px;color:#666;margin-bottom:6px;">Why purchased: {_esc(s.get('reason',''))}</div>
    <div style="font-size:11px;color:#555;text-transform:uppercase;margin-bottom:4px;">Data received:</div>
    <div style="font-size:12px;color:#aaa;white-space:pre-wrap;max-height:200px;overflow-y:auto;background:#050505;padding:8px;border-radius:3px;border:1px solid #1a1a1a;">{data_content}</div>
  </div>
</div>"""

    # Summary table of all planned endpoints
    plan_rows = ""
    for s in planned:
        if s["url"] in used_urls:
            status = '<span style="color:#4caf50">✓ purchased</span>'
        else:
            status = '<span style="color:#555">skipped</span>'
        plan_rows += f'<tr><td class="url">{_esc(s["url"])}</td><td class="cost">${s.get("cost",0):.4f}</td><td>{status}</td><td>{_esc(s.get("reason",""))}</td></tr>'

    x402_section = ""
    if planned or used:
        total = entry.get("research_cost", 0)
        budget = 0.50
        cards_html = endpoint_cards if endpoint_cards else '<div class="no-data">No endpoints were purchased.</div>'
        table_html = f'<table class="x402"><tr><th>Endpoint</th><th>Cost</th><th>Status</th><th>Reason</th></tr>{plan_rows}</table>' if plan_rows else ""
        x402_section = f"""<div class="section">
  <h2>x402 Data Purchases — ${total:.4f} spent of ${budget:.2f} budget</h2>
  <div style="font-size:12px;color:#666;margin-bottom:12px;">{len(used)} of {len(planned)} planned endpoints purchased</div>
  {cards_html}
  {f'<details style="margin-top:8px;"><summary style="font-size:11px;color:#555;cursor:pointer;">All considered endpoints</summary><div style="margin-top:8px;">{table_html}</div></details>' if table_html else ""}
</div>"""

    eval_html = f'<div class="section"><h2>Reflection & Evaluation</h2><div class="full-text">{_esc(entry.get("evaluation","(not yet reflected)"))}</div></div>' if entry.get("evaluation") else ""
    snapshot_html = f'<div class="section"><h2>Strategy at Prediction Time</h2><div class="full-text">{_esc(entry.get("strategy_snapshot","(empty)"))}</div></div>' if entry.get("strategy_snapshot") is not None else ""

    # Information needs (Stage 1 analyst output)
    needs_html = ""
    if entry.get("information_needs"):
        needs_html = f'<div class="section"><h2>Analyst Information Needs (Stage 1)</h2><div class="full-text">{_esc(entry["information_needs"])}</div></div>'

    # Research gaps
    gaps_html = ""
    if entry.get("research_gaps"):
        gap_rows = "".join(
            f'<tr><td style="color:#f9a825">{_esc(g.get("category","?"))}</td><td>{_esc(g.get("need",""))}</td><td style="color:#555;font-size:11px;">{_esc(g.get("ideal_service",""))}</td></tr>'
            for g in entry["research_gaps"]
        )
        gaps_html = f'''<div class="section"><h2>Research Gaps — No x402 Service Available</h2>
<div style="font-size:12px;color:#666;margin-bottom:8px;">These intelligence needs had no matching service in the directory. This is a demand signal for the x402 ecosystem.</div>
<table class="x402"><tr><th>Category</th><th>Need</th><th>Ideal Service</th></tr>{gap_rows}</table>
</div>'''

    body = f"""
<div style="margin-bottom:12px;"><a href="/" style="color:#555;font-size:12px;">← Back</a></div>
<h2 style="font-size:18px;color:#fff;border:none;margin-bottom:8px;">{_esc(entry["match"])}</h2>
<div style="color:#555;font-size:12px;margin-bottom:16px;">{entry.get("kickoff","")[:16].replace("T"," ")} UTC</div>
{result_html}
<div class="section"><h2>Prediction</h2>
  <div class="pred-row">
    <div class="pred-item"><div class="label">Pick</div><div class="value pick">{_team(_pick_display(pred.get('pick','?'), home, away))}</div></div>
    <div class="pred-item"><div class="label">Confidence</div><div class="value">{pred.get("confidence","?")}/10</div></div>
    <div class="pred-item"><div class="label">Bet</div><div class="value">${pred.get("bet","?")}</div></div>
  </div>
  <div class="reasoning">"{_esc(pred.get("reasoning",""))}"</div>
</div>
{needs_html}
{x402_section}
{gaps_html}
<div class="section"><h2>Full Gemini Reasoning</h2><div class="full-text">{_esc(entry.get("full_reasoning","(none)"))}</div></div>
{eval_html}
{snapshot_html}"""

    return _page(body, f"{home} vs {away} — World Cup Predictions")


@app.get("/strategy", response_class=HTMLResponse)
async def strategy_page():
    strategy = _load_text("strategy.md")
    results = _load("results.json", [])
    history = [(r.get("match"), r.get("kickoff","")[:10], r.get("strategy_snapshot","")) for r in results if r.get("strategy_snapshot") is not None]

    current = f'<div class="strategy-box"><pre>{_esc(strategy) if strategy else "(no strategy yet)"}</pre></div>'

    hist_html = ""
    if history:
        items = ""
        for match, date, snap in reversed(history):
            snippet = _esc((snap or "")[:300])
            items += f'<div style="border-bottom:1px solid #1a1a1a;padding:10px 0;"><div style="font-size:12px;color:#888;margin-bottom:4px;">After {_esc(match)} ({date})</div><div style="font-size:11px;color:#555;">{snippet}{"…" if len(snap or "")>300 else ""}</div></div>'
        hist_html = f'<div class="section"><h2>Strategy Evolution</h2>{items}</div>'

    body = f'<div class="section"><h2>Current Strategy</h2>{current}</div>{hist_html}'
    return _page(body, "Strategy — World Cup Predictions")


@app.get("/api/results")
async def api_results():
    return _load("results.json", [])

@app.get("/api/schedule")
async def api_schedule():
    return _load("schedule.json", [])
