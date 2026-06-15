"""World Cup Prediction Agent — Web UI.

FastAPI app deployed on HF Spaces. Renders HTML directly (no Jinja2).
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import markdown
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


def _team_names() -> dict[str, str]:
    """FIFA code → full country name from schedule.json."""
    names: dict[str, str] = {}
    for f in _load("schedule.json", []):
        if f.get("home") and f.get("home_name"):
            names[f["home"]] = f["home_name"]
        if f.get("away") and f.get("away_name"):
            names[f["away"]] = f["away_name"]
    return names


def _team_full(code: str, names: dict[str, str] | None = None) -> str:
    """Team with flag emoji and full country name."""
    flag = _flag(code)
    name = (names or {}).get(code.upper(), "")
    if name:
        return f"{flag} {name}" if flag else name
    return _team(code)


def _pick_display_full(pick: str, home: str, away: str, names: dict[str, str]) -> str:
    """Translate home/away/draw to full team label."""
    if pick == "home":
        return _team_full(home, names)
    if pick == "away":
        return _team_full(away, names)
    return "DRAW"


def _prob_summary(pred: dict, home: str, away: str) -> str:
    """Win probability line when model outputs HOME/DRAW/AWAY percentages."""
    probs = pred.get("probabilities") or {}
    if not probs:
        return ""
    h = probs.get("home", "?")
    d = probs.get("draw", "?")
    a = probs.get("away", "?")
    return f"model {h}%/{d}%/{a}% ({home}/{d}/{away})"

CSS = """
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d0d0d; color: #e0e0e0; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 14px; line-height: 1.6; }
a { color: #4dabf7; text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
header { border-bottom: 1px solid #333; padding-bottom: 16px; margin-bottom: 24px; }
header h1 { font-size: 20px; color: #fff; }
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
.badge.awaiting-prediction { background: #1a1a2a; color: #9e9e9e; border: 1px solid #444; }
.badge.predicted { background: #1a2a3a; color: #4dabf7; border: 1px solid #4dabf7; }
.badge.live { background: #1a2a1a; color: #66bb6a; border: 1px solid #66bb6a; }
.badge.awaiting-reflect { background: #2a2210; color: #f9a825; border: 1px solid #f9a825; }
.badge.reflected-correct { background: #1a3a1a; color: #4caf50; border: 1px solid #4caf50; }
.badge.reflected-incorrect { background: #3a1a1a; color: #f44336; border: 1px solid #f44336; }
.pipeline { display: flex; align-items: stretch; gap: 8px; margin-bottom: 28px; flex-wrap: wrap; }
.pipeline-step { flex: 1; min-width: 140px; background: #111; border: 1px solid #2a2a2a; border-radius: 6px; padding: 12px 14px; }
.pipeline-step .count { display: block; font-size: 22px; font-weight: bold; color: #fff; line-height: 1.2; }
.pipeline-step .label { font-size: 11px; color: #888; margin-top: 2px; }
.pipeline-step.active { border-color: #4dabf7; background: #0f1a24; }
.pipeline-arrow { color: #333; align-self: center; font-size: 18px; padding: 0 2px; }
.section-desc { font-size: 12px; color: #555; margin: -8px 0 14px; line-height: 1.5; }
.status-line { font-size: 11px; color: #666; margin-top: 3px; }
.empty-section { color: #444; font-style: italic; font-size: 12px; padding: 8px 0 16px; }
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
.strategy-md { color: #bbb; font-size: 13px; line-height: 1.7; }
.strategy-md p { margin: 6px 0; }
.strategy-md h1, .strategy-md h2, .strategy-md h3 { color: #e0e0e0; margin: 12px 0 6px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #2a2a2a; padding-bottom: 4px; }
.strategy-md strong { color: #fff; }
.strategy-md ul, .strategy-md ol { padding-left: 20px; margin: 4px 0; }
.strategy-md li { margin: 2px 0; }
.strategy-md a { color: #4dabf7; }
.full-text { font-size: 12px; color: #aaa; white-space: pre-wrap; background: #0a0a0a; border: 1px solid #1e1e1e; border-radius: 4px; padding: 12px; max-height: 400px; overflow-y: auto; }
.full-text.strategy-md { white-space: normal; }
.nav { margin-bottom: 20px; font-size: 13px; }
details summary::-webkit-details-marker { display: none; }
details summary { outline: none; }
details[open] .match-header { border-bottom: 1px solid #222; }
details[open] summary span.chevron { transform: rotate(180deg); display: inline-block; }
.tooltip-wrap { position: relative; display: inline-block; cursor: help; border-bottom: 1px dashed #555; }
.tooltip-wrap .tooltip-box { visibility: hidden; opacity: 0; background: #1e1e1e; color: #ccc; font-size: 11px; line-height: 1.5; border: 1px solid #333; border-radius: 4px; padding: 8px 10px; position: absolute; z-index: 10; bottom: 125%; left: 50%; transform: translateX(-50%); width: 260px; pointer-events: none; transition: opacity 0.15s; white-space: normal; font-weight: normal; font-style: normal; }
.tooltip-wrap:hover .tooltip-box { visibility: visible; opacity: 1; }
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

_STAGE_ORDER = ["Group Stage", "Round Of 32", "Round Of 16", "Quarterfinals", "Semifinals", "Final"]

def _stage_indicator(schedule: list, results: list) -> str:
    """Return HTML for a tournament stage progress indicator."""
    now = datetime.now(timezone.utc)
    predicted = {(r["home"], r["away"]) for r in results}

    # Count past/future per stage; find current stage (earliest with future unpredicted games)
    stage_stats: dict[str, dict] = {}
    for f in schedule:
        k = f.get("kickoff_utc", "")
        try:
            dt = datetime.fromisoformat(k.replace("Z", "+00:00"))
        except Exception:
            continue
        st = f.get("stage", "")
        if not st:
            continue
        s = stage_stats.setdefault(st, {"total": 0, "past": 0, "future_unpredicted": 0})
        s["total"] += 1
        if dt <= now:
            s["past"] += 1
        elif (f["home"], f["away"]) not in predicted:
            s["future_unpredicted"] += 1

    # Determine which stages exist in this schedule (in order)
    present_stages = [s for s in _STAGE_ORDER if s in stage_stats]
    if not present_stages:
        return ""

    # Current stage = first one that still has future unpredicted matches
    current_stage = next(
        (s for s in present_stages if stage_stats[s]["future_unpredicted"] > 0),
        present_stages[-1],
    )

    # Build pipeline HTML
    pills = ""
    for i, st in enumerate(present_stages):
        stats = stage_stats[st]
        is_current = st == current_stage
        is_done = present_stages.index(st) < present_stages.index(current_stage)

        if is_current:
            played = stats["past"]
            total = stats["total"]
            pct = int(played / total * 100) if total else 0
            bg = "#1a2a3a"
            border = "#4dabf7"
            color = "#4dabf7"
            label = f'<span style="font-weight:bold;color:#4dabf7;">{st}</span> <span style="color:#555;font-size:10px;">{played}/{total} played</span>'
            progress = f'<div style="height:2px;background:#0a1a2a;border-radius:1px;margin-top:4px;"><div style="width:{pct}%;height:2px;background:#4dabf7;border-radius:1px;"></div></div>'
        elif is_done:
            bg = "#0d1a0d"
            border = "#2a3a2a"
            color = "#4caf50"
            label = f'<span style="color:#4caf50;">✓ {st}</span>'
            progress = ""
        else:
            bg = "#111"
            border = "#222"
            color = "#444"
            label = f'<span style="color:#444;">{st}</span>'
            progress = ""

        connector = '<div style="color:#333;align-self:center;padding:0 4px;font-size:12px;">›</div>' if i < len(present_stages) - 1 else ""
        pills += f'<div style="background:{bg};border:1px solid {border};border-radius:4px;padding:6px 10px;min-width:100px;flex:1;"><div style="font-size:11px;">{label}</div>{progress}</div>{connector}'

    return f'<div style="display:flex;align-items:stretch;gap:0;margin-bottom:14px;flex-wrap:wrap;gap:4px;">{pills}</div>'


def _dedupe_results(results: list) -> list:
    """Keep the best entry per fixture — prefer reflected over unreflected."""
    latest: dict[tuple, dict] = {}
    for r in results:
        key = (r.get("home"), r.get("away"))
        prev = latest.get(key)
        if prev is None:
            latest[key] = r
        elif r.get("reflected") and not prev.get("reflected"):
            latest[key] = r
        elif prev.get("reflected") and not r.get("reflected"):
            continue
        else:
            latest[key] = r
    return list(latest.values())


def _kickoff_dt(r_or_fixture) -> datetime | None:
    k = r_or_fixture.get("kickoff") or r_or_fixture.get("kickoff_utc") or ""
    try:
        return datetime.fromisoformat(k.replace("Z", "+00:00"))
    except Exception:
        return None


def _upcoming(schedule, results):
    now = datetime.now(timezone.utc)
    predicted = {(r["home"], r["away"]) for r in results}
    out = []
    for f in schedule:
        dt = _kickoff_dt(f)
        if dt is None:
            continue
        if dt > now and (f["home"], f["away"]) not in predicted:
            out.append((dt, f))
    sorted_all = [f for _, f in sorted(out, key=lambda x: x[0])]
    return sorted_all[:8], len(sorted_all)


def _match_state(r: dict) -> dict:
    """Classify a predicted match: reflected, or awaiting reflection (with sub-status)."""
    if r.get("reflected"):
        if r.get("correct") is True:
            badge = '<span class="badge reflected-correct">✓ REFLECTED</span>'
        else:
            badge = '<span class="badge reflected-incorrect">✗ REFLECTED</span>'
        return {
            "bucket": "reflected",
            "sublabel": "Final result scored · strategy updated",
            "badge": badge,
        }

    kdt = _kickoff_dt(r)
    now = datetime.now(timezone.utc)
    if kdt is not None:
        secs_since = (now - kdt).total_seconds()
        if secs_since > 7200:
            return {
                "bucket": "awaiting_reflection",
                "sublabel": "Match finished · reflection pending (~2.5h after kickoff)",
                "badge": '<span class="badge awaiting-reflect">AWAITING REFLECTION</span>',
            }
        if secs_since > 0:
            return {
                "bucket": "awaiting_reflection",
                "sublabel": "Match in progress · reflection after final whistle",
                "badge": '<span class="badge live">● LIVE</span>',
            }
        rel, _ = _time_rel(r.get("kickoff", ""))
        return {
            "bucket": "awaiting_reflection",
            "sublabel": f"Pick locked in · kicks off in {rel}",
            "badge": '<span class="badge predicted">PREDICTED</span>',
        }

    return {
        "bucket": "awaiting_reflection",
        "sublabel": "Pick locked in · awaiting kickoff",
        "badge": '<span class="badge predicted">PREDICTED</span>',
    }


def _badge(r):
    return _match_state(r)["badge"]


def _kickoff_passed(r: dict) -> bool:
    kdt = _kickoff_dt(r)
    if kdt is None:
        return False
    return (datetime.now(timezone.utc) - kdt).total_seconds() > 0


def _awaiting_reflection(r: dict) -> bool:
    return not r.get("reflected") and _kickoff_passed(r)


def _upcoming_predicted(r: dict) -> bool:
    return not r.get("reflected") and not _kickoff_passed(r)


def _awaiting_reflect_sort_key(r: dict) -> tuple:
    kdt = _kickoff_dt(r)
    now = datetime.now(timezone.utc)
    if kdt is None:
        return (9, 0)
    secs_since = (now - kdt).total_seconds()
    if secs_since > 7200:
        priority = 0
    elif secs_since > 0:
        priority = 1
    else:
        priority = 2
    return (priority, -kdt.timestamp())


def _kickoff_sort_key(r: dict) -> float:
    kdt = _kickoff_dt(r)
    return kdt.timestamp() if kdt else 0.0


def _render_match_card(r: dict, names: dict[str, str] | None = None) -> str:
    pred = r.get("prediction", {})
    res = r.get("result")
    used = r.get("services_used", [])
    planned = r.get("services_planned", [])
    state = _match_state(r)
    if names is None:
        names = _team_names()

    x402_html = ""
    if used:
        rows = "".join(
            f'<tr><td class="url">{_esc(s["source"])}</td><td class="cost">${s["cost"]:.4f}</td>'
            f'<td>{_esc(s.get("reason", ""))}</td></tr>'
            for s in used
        )
        x402_html = f'<div class="x402-label">x402 data purchased</div><table class="x402"><tr><th>Endpoint</th><th>Cost</th><th>Reason</th></tr>{rows}</table>'
    elif planned:
        x402_html = f'<div class="no-data">{len(planned)} endpoint(s) considered, none purchased.</div>'
    else:
        x402_html = '<div class="no-data">No x402 data for this match.</div>'

    result_html = ""
    if res and r.get("reflected"):
        cls = "correct" if r.get("correct") else "incorrect"
        eval_snippet = _esc((r.get("evaluation") or "")[:180])
        result_html = f'''<div class="result-bar {cls}">
          Result: <span class="result-score">{_team_full(r['home'], names)} {res['home_score']}–{res['away_score']} {_team_full(r['away'], names)}</span>
          {f'<div class="eval-text">{eval_snippet}{"…" if len(r.get("evaluation", "")) > 180 else ""}</div>' if eval_snippet else ""}
        </div>'''
    elif res and not r.get("reflected"):
        result_html = f'''<div class="result-bar" style="background:#1a1810;border-left:3px solid #f9a825;">
          Provisional score: <span class="result-score">{_team_full(r['home'], names)} {res['home_score']}–{res['away_score']} {_team_full(r['away'], names)}</span>
          <div class="eval-text">Official reflection not run yet — win/loss not scored.</div>
        </div>'''

    rel, rel_color = _time_rel(r.get("kickoff", ""))
    kickoff_note = f'<span style="color:{rel_color}">{rel}</span>' if rel else ""

    prob_note = _prob_summary(pred, r["home"], r["away"])
    prob_html = f' &nbsp;·&nbsp; {prob_note}' if prob_note else ""

    return f"""<div class="match-card">
      <details>
      <summary style="list-style:none;cursor:pointer;">
      <div class="match-header">
        <div>
          <div class="match-title">{_team(r['home'])} vs {_team(r['away'])}</div>
          <div class="match-time">{kickoff_note}{' &nbsp;·&nbsp; ' if kickoff_note else ''}Pick: <b>{_team(_pick_display(pred.get('pick', '?'), r['home'], r['away']))}</b> &nbsp;·&nbsp; conf {pred.get("confidence", "?")}/10{prob_html}</div>
          <div class="status-line">{_esc(state['sublabel'])}</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">{state['badge']}<span style="color:#444;font-size:16px;">⌄</span></div>
      </div>
      </summary>
      <div class="match-body">
        <div class="pred-row">
          <div class="pred-item"><div class="label">Pick</div><div class="value pick">{_pick_display_full(pred.get('pick', '?'), r['home'], r['away'], names)}</div></div>
          <div class="pred-item"><div class="label">Confidence</div><div class="value"><span class="tooltip-wrap">{pred.get("confidence", "?")}/10<span class="tooltip-box">{_esc(pred.get("confidence_reason", "Hover reason not available for this prediction."))}</span></span></div></div>
          <div class="pred-item"><div class="label">Research cost</div><div class="value" style="color:#f9a825;">${r.get("research_cost", 0):.4f}</div></div>
        </div>
        <div class="reasoning">"{_esc(pred.get("reasoning", ""))}"</div>
        {x402_html}
        {result_html}
        <a href="/match/{_esc(r['home'])}_{_esc(r['away'])}" class="detail-link">Full reasoning & reflection →</a>
      </div>
      </details>
    </div>"""


def _pipeline_html(awaiting_pred: int, awaiting_reflect: int, reflected: int, wins: int, losses: int) -> str:
    record = f"{wins}W–{losses}L" if reflected else "—"
    return f"""<div class="pipeline">
  <div class="pipeline-step{' active' if awaiting_pred else ''}">
    <span class="count">{awaiting_pred}</span>
    <span class="label">Awaiting prediction</span>
  </div>
  <div class="pipeline-arrow">→</div>
  <div class="pipeline-step{' active' if awaiting_reflect else ''}">
    <span class="count">{awaiting_reflect}</span>
    <span class="label">Predicted · awaiting reflection</span>
  </div>
  <div class="pipeline-arrow">→</div>
  <div class="pipeline-step{' active' if reflected else ''}">
    <span class="count">{reflected}</span>
    <span class="label">Reflected ({record})</span>
  </div>
</div>"""

def _time_rel(kickoff_str: str) -> tuple[str, str]:
    """Return (label, color) for a kickoff time relative to now."""
    try:
        kdt = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = kdt - now
        secs = delta.total_seconds()
        abs_secs = abs(secs)
        if abs_secs < 3600:
            mins = int(abs_secs / 60)
            label = f"{mins}m {'away' if secs > 0 else 'ago'}"
        elif abs_secs < 86400:
            hrs = abs_secs / 3600
            label = f"{hrs:.1f}h {'away' if secs > 0 else 'ago'}"
        else:
            days = abs_secs / 86400
            label = f"{days:.1f}d {'away' if secs > 0 else 'ago'}"
        if secs > 0:
            color = "#4caf50" if secs > 86400 else ("#f9a825" if secs > 3600 else "#f44336")
        else:
            color = "#555"
        return label, color
    except Exception:
        return "", "#555"

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def _render_md(text: str) -> str:
    if not text or not text.strip():
        return ""
    return markdown.markdown(text, extensions=["sane_lists", "nl2br"])

def _md(text: str, extra_class: str = "") -> str:
    cls = f"strategy-md {extra_class}".strip()
    return f'<div class="{cls}">{_render_md(text)}</div>'

def _page(body, title="⚽ World Cup Prediction Agent"):
    nav = '<div class="nav"><a href="/">Dashboard</a> · <a href="/learnings">Learnings</a> · <a href="/strategy">Strategy</a></div>'
    header = """
<header>
  <h1>⚽ World Cup Prediction Agent</h1>
</header>"""
    return HTMLResponse(f"<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title>{CSS}</head><body><div class='container'>{header}{nav}{body}</div></body></html>")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    results_raw = _load("results.json", [])
    all_results = _dedupe_results(results_raw)
    schedule = _load("schedule.json", [])
    strategy = _load_text("strategy.md")
    upcoming, upcoming_total = _upcoming(schedule, results_raw)

    reflected = [r for r in all_results if r.get("reflected")]
    awaiting_reflect = sorted(
        [r for r in all_results if _awaiting_reflection(r)],
        key=_awaiting_reflect_sort_key,
    )
    upcoming_predicted = sorted(
        [r for r in all_results if _upcoming_predicted(r)],
        key=_kickoff_sort_key,
    )
    wins = sum(1 for r in reflected if r.get("correct"))
    losses = len(reflected) - wins

    html = _pipeline_html(upcoming_total, len(awaiting_reflect), len(reflected), wins, losses)
    team_names = _team_names()

    # ── 1. Awaiting prediction ──────────────────────────────────────────────
    stage_bar = _stage_indicator(schedule, results_raw) if schedule else ""
    if upcoming:
        items = ""
        for f in upcoming:
            rel, rel_color = _time_rel(f["kickoff_utc"])
            items += f"""<div class="upcoming-item">
              <div>
                <div><b>{_team(f['home'])} vs {_team(f['away'])}</b> <span style="color:#555;font-size:11px;margin-left:8px;">{_esc(f.get('stage', ''))}</span></div>
                <div class="status-line">Agent runs ~30 min before kickoff</div>
              </div>
              <div style="text-align:right;">
                <span class="badge awaiting-prediction">AWAITING PREDICTION</span>
                <div style="color:{rel_color};font-size:12px;margin-top:4px;">{rel} &nbsp;<span style="color:#444;">({f['kickoff_utc'][:16].replace('T', ' ')} UTC)</span></div>
              </div>
            </div>"""
        footer = ""
        if upcoming_total > len(upcoming):
            footer = f'<div style="font-size:11px;color:#444;margin-top:8px;text-align:right;">Showing next {len(upcoming)} of {upcoming_total} fixtures without a prediction</div>'
        html += f"""<div class="section">
  <h2>Awaiting Prediction</h2>
  <div class="section-desc">Fixtures on the schedule with no pick yet. <code>predict.py</code> runs automatically ~30 minutes before kickoff.</div>
  {stage_bar}{items}{footer}
</div>"""
    else:
        html += """<div class="section">
  <h2>Awaiting Prediction</h2>
  <div class="section-desc">Fixtures on the schedule with no pick yet. <code>predict.py</code> runs automatically ~30 minutes before kickoff.</div>
  <div class="empty-section">No unpredicted fixtures coming up — every scheduled match has a pick, or the group stage is complete.</div>
</div>"""

    # ── 2. Predicted — upcoming ───────────────────────────────────────────
    if upcoming_predicted:
        cards = "".join(_render_match_card(r, team_names) for r in upcoming_predicted)
        html += f"""<div class="section">
  <h2>Predicted — Upcoming</h2>
  <div class="section-desc">Pick is locked in before kickoff. Reflection runs automatically ~2.5h after the final whistle.</div>
  {cards}
</div>"""

    # ── 3. Predicted — awaiting reflection ────────────────────────────────
    html += '<div class="section"><h2>Predicted — Awaiting Reflection</h2>'
    html += '<div class="section-desc">Match has kicked off. <code>reflect.py</code> fetches the result, scores the prediction, and updates strategy (~2.5h after kickoff).</div>'
    if awaiting_reflect:
        cards = "".join(_render_match_card(r, team_names) for r in awaiting_reflect)
        html += cards + "</div>"
    else:
        html += '<div class="empty-section">Nothing here — no played matches waiting on reflection.</div></div>'

    # ── 4. Reflected ────────────────────────────────────────────────────────
    html += '<div class="section"><h2>Reflected</h2>'
    html += '<div class="section-desc">Match complete. Prediction scored against the final result and learnings applied to strategy.</div>'
    if reflected:
        reflected_sorted = sorted(
            reflected,
            key=lambda r: r.get("reflected_at") or "",
            reverse=True,
        )
        cards = "".join(_render_match_card(r, team_names) for r in reflected_sorted)
        html += cards + "</div>"
    else:
        html += '<div class="empty-section">No reflections yet — they appear here after the first match finishes and <code>reflect.py</code> runs.</div></div>'

    # Strategy snippet
    if strategy:
        snippet = _md(strategy[:500])
        more = '<div style="margin-top:8px;"><a href="/strategy">… read more</a></div>' if len(strategy) > 500 else ""
        html += f'<div class="section"><h2>Current Strategy <a href="/strategy" style="font-size:11px;color:#555;font-weight:normal;margin-left:8px;">full history →</a></h2><div class="strategy-box">{snippet}{more}</div></div>'

    return _page(html)


@app.get("/match/{match_key}", response_class=HTMLResponse)
async def match_detail(match_key: str):
    home, _, away = match_key.partition("_")
    home, away = home.upper(), away.upper()
    results = _load("results.json", [])
    entry = next(
        (r for r in reversed(_dedupe_results(results))
        if r.get("home") == home and r.get("away") == away),
        None,
    )
    if not entry:
        raise HTTPException(status_code=404, detail=f"No prediction found for {home} vs {away}")

    pred = entry.get("prediction", {})
    res = entry.get("result")
    used = entry.get("services_used", [])
    planned = entry.get("services_planned", [])

    state = _match_state(entry)
    result_html = ""
    if res and entry.get("reflected"):
        cls = "correct" if entry.get("correct") else "incorrect"
        result_html = f'<div class="result-bar {cls}" style="margin-bottom:16px;"><span class="result-score">{_team(home)} {res["home_score"]}–{res["away_score"]} {_team(away)}</span> &nbsp;{state["badge"]}</div>'
    elif res:
        result_html = f'''<div class="result-bar" style="margin-bottom:16px;background:#1a1810;border-left:3px solid #f9a825;">
          <span class="result-score">{_team(home)} {res["home_score"]}–{res["away_score"]} {_team(away)}</span> &nbsp;{state["badge"]}
          <div class="eval-text">Provisional score — win/loss not scored until reflection runs.</div>
        </div>'''
    else:
        result_html = f'<div style="margin-bottom:16px;">{state["badge"]}<div class="status-line" style="margin-top:6px;">{_esc(state["sublabel"])}</div></div>'

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
    snapshot_html = f'<div class="section"><h2>Strategy at Prediction Time</h2><div class="full-text strategy-md">{_render_md(entry.get("strategy_snapshot","")) or "(empty)"}</div></div>' if entry.get("strategy_snapshot") is not None else ""

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
    <div class="pred-item"><div class="label">Confidence</div><div class="value"><span class="tooltip-wrap">{pred.get("confidence","?")}/10<span class="tooltip-box">{_esc(pred.get("confidence_reason","Hover reason not available for this prediction."))}</span></span></div></div>
  </div>
  {f'<div style="font-size:12px;color:#666;margin-top:8px;">Win model: {_esc(_prob_summary(pred, home, away))}</div>' if _prob_summary(pred, home, away) else ""}
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

    current = f'<div class="strategy-box">{_md(strategy)}</div>' if strategy else '<div class="strategy-box"><div style="color:#444;font-style:italic;">No strategy yet — will be written after the first match reflection.</div></div>'

    hist_html = ""
    if history:
        items = ""
        for match, date, snap in reversed(history):
            snap_text = (snap or "")[:300]
            suffix = "…" if len(snap or "") > 300 else ""
            items += f'<div style="border-bottom:1px solid #1a1a1a;padding:10px 0;"><div style="font-size:12px;color:#888;margin-bottom:4px;">After {_esc(match)} ({date})</div>{_md(snap_text + suffix)}</div>'
        hist_html = f'<div class="section"><h2>Strategy Evolution</h2>{items}</div>'

    body = f'<div class="section"><h2>Current Strategy</h2>{current}</div>{hist_html}'
    return _page(body, "Strategy — World Cup Predictions")


def _strategy_history_from_results(results: list) -> list[dict]:
    """Build strategy evolution from reflected entries in results.json."""
    by_match: dict[str, dict] = {}
    for r in results:
        if not r.get("reflected"):
            continue
        match = r.get("match") or ""
        if not match:
            continue
        prev = by_match.get(match)
        if prev is None or (r.get("reflected_at") or "") >= (prev.get("reflected_at") or ""):
            by_match[match] = r

    entries = sorted(by_match.values(), key=lambda r: r.get("reflected_at") or "")
    if not entries:
        return []

    current = _load_text("strategy.md")
    history = []
    for i, r in enumerate(entries):
        match = r["match"]
        try:
            dt = datetime.fromisoformat((r.get("reflected_at") or "").replace("Z", "+00:00"))
        except Exception:
            dt = None

        prev_content = r.get("strategy_snapshot") or ""
        if not prev_content.strip() and i > 0:
            prev_content = history[i - 1]["content"]

        content = r.get("strategy_after") or ""
        if not content.strip():
            if i == len(entries) - 1:
                content = current
            else:
                nxt = entries[i + 1].get("strategy_snapshot") or entries[i + 1].get("strategy_after") or ""
                content = nxt

        history.append({
            "match": match,
            "date": dt,
            "subject": f"reflect: {match}",
            "content": content,
            "prev_content": prev_content,
        })
    return history


def _strategy_history_from_git() -> list[dict]:
    """Return strategy evolution from git log (local dev fallback)."""
    try:
        log = subprocess.run(
            ["git", "log", "--pretty=format:%H|%ai|%s", "--", "strategy.md"],
            cwd=BASE, capture_output=True, text=True, check=True,
        )
    except Exception:
        return []

    entries = []
    lines = [l for l in log.stdout.strip().splitlines() if l]
    for line in lines:
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, date_str, subject = parts
        match_name = subject.replace("reflect: ", "").replace("init: ", "").strip()
        try:
            dt = datetime.fromisoformat(date_str.strip())
        except Exception:
            dt = None
        try:
            content = subprocess.run(
                ["git", "show", f"{sha}:strategy.md"],
                cwd=BASE, capture_output=True, text=True, check=True,
            ).stdout
        except Exception:
            content = ""
        entries.append({"match": match_name, "date": dt, "sha": sha, "subject": subject, "content": content})

    entries.reverse()

    latest_reflect_idx: dict[str, int] = {}
    for i, e in enumerate(entries):
        if e["subject"].startswith("reflect:"):
            latest_reflect_idx[e["match"]] = i
    entries = [
        e for i, e in enumerate(entries)
        if not e["subject"].startswith("reflect:") or latest_reflect_idx.get(e["match"]) == i
    ]

    for i, e in enumerate(entries):
        e["prev_content"] = entries[i - 1]["content"] if i > 0 else ""
    return entries


def _strategy_history() -> list[dict]:
    """Strategy evolution for the Learnings page — results.json first, git as fallback."""
    results = _load("results.json", [])
    history = _strategy_history_from_results(results)
    if history:
        git_by_match = {
            e["match"]: e for e in _strategy_history_from_git()
            if e["subject"].startswith("reflect:")
        }
        for e in history:
            g = git_by_match.get(e["match"])
            if not g:
                continue
            if not (e.get("content") or "").strip():
                e["content"] = g["content"]
            if not (e.get("prev_content") or "").strip():
                e["prev_content"] = g["prev_content"]
        return history
    return _strategy_history_from_git()


def _text_diff_html(old: str, new: str) -> str:
    """Produce simple line-level added/removed/unchanged HTML."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    old_set = set(old_lines)
    new_set = set(new_lines)
    parts = []
    for line in new_lines:
        esc = _esc(line)
        if line not in old_set:
            parts.append(f'<div class="diff-add">+ {esc}</div>')
        else:
            parts.append(f'<div class="diff-same">  {esc}</div>')
    for line in old_lines:
        if line not in new_set:
            esc = _esc(line)
            parts.append(f'<div class="diff-remove">- {esc}</div>')
    return "\n".join(parts) if parts else '<div class="diff-same">(no change)</div>'


@app.get("/learnings", response_class=HTMLResponse)
async def learnings_page():
    history = _strategy_history()
    results = _load("results.json", [])
    # Index evaluations by match name for quick lookup
    evals = {r.get("match", ""): r for r in results if r.get("evaluation")}

    DIFF_CSS = """
<style>
.diff-add    { color: #4caf50; background: #0d1f0d; padding: 1px 6px; white-space: pre-wrap; word-break: break-word; }
.diff-remove { color: #f44336; background: #1f0d0d; padding: 1px 6px; white-space: pre-wrap; word-break: break-word; }
.diff-same   { color: #444;    padding: 1px 6px; white-space: pre-wrap; word-break: break-word; }
.learning-card { background: #111; border: 1px solid #2a2a2a; border-radius: 6px; margin-bottom: 24px; overflow: hidden; }
.learning-header { background: #161616; border-bottom: 1px solid #222; padding: 10px 16px; display: flex; justify-content: space-between; align-items: baseline; }
.learning-match { font-size: 15px; font-weight: bold; color: #fff; }
.learning-date  { font-size: 11px; color: #555; }
.learning-body  { padding: 14px 16px; }
.eval-box { background: #0a0a0a; border: 1px solid #1e1e1e; border-radius: 4px; padding: 10px 12px; font-size: 12px; color: #888; white-space: pre-wrap; max-height: 220px; overflow-y: auto; margin-bottom: 12px; }
.diff-box { background: #050505; border: 1px solid #1e1e1e; border-radius: 4px; padding: 8px 4px; font-size: 12px; font-family: monospace; max-height: 320px; overflow-y: auto; }
.section-label { font-size: 10px; color: #555; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; margin-top: 12px; }
</style>"""

    body = DIFF_CSS

    reflect_entries = [e for e in reversed(history) if e["subject"].startswith("reflect:")]

    if not reflect_entries:
        body += '<div style="color:#444;font-style:italic;padding:32px 0;">No reflections recorded yet — learnings appear after each match is reflected.</div>'
        return _page(body, "Learnings — World Cup Predictions")

    cards = ""
    for e in reflect_entries:
        match_name = e["match"]
        date_str = e["date"].strftime("%Y-%m-%d %H:%M UTC") if e["date"] else ""
        result_entry = evals.get(match_name, {})

        # Outcome badge
        if result_entry.get("correct") is True:
            badge = '<span class="badge correct">✓ CORRECT</span>'
        elif result_entry.get("correct") is False:
            badge = '<span class="badge incorrect">✗ INCORRECT</span>'
        else:
            badge = ""

        # Score
        res = result_entry.get("result")
        score_html = ""
        if res:
            score_html = f'<div style="font-size:12px;color:#666;margin-bottom:10px;">{_esc(result_entry.get("home",""))} {res["home_score"]}–{res["away_score"]} {_esc(result_entry.get("away",""))}</div>'

        # Evaluation
        eval_text = result_entry.get("evaluation", "")
        eval_html = ""
        if eval_text:
            eval_html = f'<div class="section-label">Evaluator assessment</div><div class="eval-box">{_esc(eval_text)}</div>'

        # Strategy diff
        diff_html = _text_diff_html(e["prev_content"], e["content"])
        is_first = not e["prev_content"].strip()
        diff_label = "Initial strategy written" if is_first else "Strategy change"

        cards += f"""<div class="learning-card">
  <div class="learning-header">
    <div>
      <div class="learning-match">{_esc(match_name)}</div>
      <div class="learning-date">{date_str}</div>
    </div>
    {badge}
  </div>
  <div class="learning-body">
    {score_html}
    {eval_html}
    <div class="section-label">{diff_label}</div>
    <div class="diff-box">{diff_html}</div>
  </div>
</div>"""

    body += f'<div class="section"><h2>Strategy Evolution — {len(reflect_entries)} reflection{"s" if len(reflect_entries) != 1 else ""}</h2>{cards}</div>'
    return _page(body, "Learnings — World Cup Predictions")


@app.get("/api/results")
async def api_results():
    return _load("results.json", [])

@app.get("/api/schedule")
async def api_schedule():
    return _load("schedule.json", [])
