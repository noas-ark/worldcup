"""Structured prediction pipeline — evidence synthesis, stress-test, calibrated pick."""

import json
import re
from datetime import datetime, timedelta, timezone

import gemini
import requests


def dedupe_results(results: list) -> list:
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


def build_learning_context(results: list, limit: int = 8) -> str:
    """Summarize reflected matches — outcomes, mistakes, data lessons."""
    reflected = sorted(
        [r for r in dedupe_results(results) if r.get("reflected")],
        key=lambda r: r.get("reflected_at") or "",
        reverse=True,
    )[:limit]
    if not reflected:
        return "(no reflected matches yet)"

    lines = []
    for r in reflected:
        pred = r.get("prediction", {})
        res = r.get("result") or {}
        pick = pred.get("pick", "?")
        correct = r.get("correct")
        tag = "CORRECT" if correct else "WRONG"
        score = f"{res.get('home_score', '?')}-{res.get('away_score', '?')}"
        eval_snip = (r.get("evaluation") or "").replace("\n", " ")[:200]
        lines.append(
            f"- {r['home']} vs {r['away']}: picked {pick} ({pred.get('confidence', '?')}/10) "
            f"→ {score} [{tag}]. Learning: {eval_snip}"
        )
    return "\n".join(lines)


def build_fixture_context(
    home: str,
    away: str,
    home_name: str,
    away_name: str,
    schedule: list,
    results: list,
    kickoff: str,
) -> str:
    """Group-stage neighbors and results already played in this tournament."""
    try:
        kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    except ValueError:
        kickoff_dt = None

    group_teams = {home, away}
    for f in schedule:
        if f.get("stage") != "Group Stage":
            continue
        h, a = f.get("home"), f.get("away")
        if h in (home, away) or a in (home, away):
            group_teams.add(h)
            group_teams.add(a)

    played = []
    for r in dedupe_results(results):
        if not r.get("result"):
            continue
        h, a = r.get("home"), r.get("away")
        if h not in group_teams and a not in group_teams:
            continue
        res = r["result"]
        played.append(
            f"{h} {res['home_score']}-{res['away_score']} {a} (winner: {res['winner']})"
        )

    upcoming = []
    for f in schedule:
        if f.get("stage") != "Group Stage":
            continue
        h, a = f.get("home"), f.get("away")
        if h not in group_teams and a not in group_teams:
            continue
        k = f.get("kickoff_utc", "")
        if kickoff_dt and k:
            try:
                fdt = datetime.fromisoformat(k.replace("Z", "+00:00"))
                if fdt <= kickoff_dt and (h, a) != (home, away):
                    continue
            except ValueError:
                pass
        if (h, a) == (home, away):
            label = "THIS MATCH"
        else:
            label = k[:16].replace("T", " ")
        upcoming.append(f"{h} vs {a} ({label})")

    parts = [
        f"Group-stage cluster around {home_name} / {away_name}: {', '.join(sorted(group_teams))}",
    ]
    if played:
        parts.append("Tournament results so far:\n" + "\n".join(f"  • {p}" for p in played))
    if upcoming:
        parts.append("Related fixtures:\n" + "\n".join(f"  • {u}" for u in upcoming[:6]))
    return "\n".join(parts)


def fetch_espn_tournament_form(home: str, away: str, kickoff: str) -> str:
    """Free ESPN scoreboard — recent World Cup results for both teams."""
    try:
        kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    except ValueError:
        kickoff_dt = datetime.now(timezone.utc)

    teams = {home, away}
    lines = []
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

    for delta in range(14):
        day = (kickoff_dt - timedelta(days=delta)).strftime("%Y%m%d")
        try:
            resp = requests.get(url, params={"dates": day}, timeout=12)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue

        for event in data.get("events", []):
            comps = event.get("competitions", [{}])
            if not comps:
                continue
            comp = comps[0]
            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue
            abbrevs = {
                c["homeAway"]: c["team"].get("abbreviation", "").upper() for c in competitors
            }
            if abbrevs.get("home") not in teams and abbrevs.get("away") not in teams:
                continue
            status = comp.get("status", {}).get("type", {})
            if not status.get("completed", False):
                continue
            scores = {c["homeAway"]: c.get("score", "?") for c in competitors}
            date = event.get("date", day)[:10]
            lines.append(
                f"{date}: {abbrevs.get('home')} {scores.get('home')}-{scores.get('away')} "
                f"{abbrevs.get('away')}"
            )

    if not lines:
        return "(no completed ESPN World Cup results found for these teams yet)"
    return "ESPN tournament results:\n" + "\n".join(f"  • {ln}" for ln in lines[:12])


def _parse_json_response(text: str) -> dict:
    raw = text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


def synthesize_evidence(
    match: str,
    home_name: str,
    away_name: str,
    kickoff: str,
    strategy: str,
    context_text: str,
    learning_context: str,
    fixture_context: str,
    espn_form: str,
    useful_count: int,
    total_sources: int,
    retroactive: bool,
) -> dict:
    retro = (
        "RETROACTIVE: simulate pre-match analysis only — ignore any post-match scores in sources."
        if retroactive
        else ""
    )
    prompt = f"""You are a football data analyst. Extract structured evidence from research for {match}.
Kickoff: {kickoff}
{retro}

Strategy rules to apply:
{strategy or "(none yet)"}

Agent track record (learn from past mistakes):
{learning_context}

Fixture / group context:
{fixture_context}

ESPN results:
{espn_form}

Purchased research ({useful_count}/{total_sources} useful sources):
{context_text}

Return ONLY valid JSON:
{{
  "data_quality": "high|medium|low",
  "home_form": "one sentence",
  "away_form": "one sentence",
  "key_injuries": ["bullet"],
  "tactical_matchup": "one sentence — who has structural edge",
  "group_stakes": "one sentence — what each team needs",
  "home_win_signals": ["specific evidence bullets"],
  "away_win_signals": ["specific evidence bullets"],
  "draw_signals": ["specific evidence bullets"],
  "contradictions": ["conflicting signals if any"],
  "strategy_applied": ["which strategy rules matter here"]
}}"""

    text = gemini.generate(prompt, temperature=0.3, json_mode=True)
    return _parse_json_response(text)


def stress_test_evidence(
    match: str,
    home_name: str,
    away_name: str,
    synthesis: dict,
    strategy: str,
) -> dict:
    prompt = f"""You are a skeptical betting analyst reviewing a colleague's match brief for {match}.

Strategy:
{strategy or "(none)"}

Colleague's synthesis:
{json.dumps(synthesis, indent=2)}

Challenge weak reasoning. Find overlooked risks. Do NOT invent facts not implied by the synthesis.

Return ONLY valid JSON:
{{
  "blind_spots": ["what the synthesis may be overweighting"],
  "underweighted_factors": ["factors that could flip the result"],
  "draw_risk": "low|medium|high — with one sentence why",
  "favorite": "home|away|none",
  "confidence_cap": 1-10 integer — max justified confidence given gaps,
  "verdict": "one sentence overall assessment"
}}"""

    text = gemini.generate(prompt, temperature=0.4, json_mode=True)
    return _parse_json_response(text)


def make_final_prediction(
    match: str,
    home: str,
    away: str,
    home_name: str,
    away_name: str,
    kickoff: str,
    strategy: str,
    synthesis: dict,
    stress_test: dict,
    useful_count: int,
    total_sources: int,
) -> str:
    prompt = f"""You are a World Cup match predictor. Make a calibrated prediction for {match}.
Home: {home_name} ({home})
Away: {away_name} ({away})
Kickoff: {kickoff}

Strategy:
{strategy or "(none)"}

Evidence synthesis:
{json.dumps(synthesis, indent=2)}

Stress-test review:
{json.dumps(stress_test, indent=2)}

Research quality: {useful_count}/{total_sources} useful sources.

PROCESS (think through this, then output the format lines):
1. Estimate win probabilities (integers 0-100, must sum to 100).
2. PICK = outcome with highest probability (if within 5% of second-best, prefer draw only when draw_signals dominate).
3. CONFIDENCE must respect stress_test.confidence_cap and data_quality:
   - high quality + cap 8+ → use 7-10 when probability spread ≥ 15%
   - medium → 5-7
   - low → 3-5
   - Never use 5 as a default — justify the number.
4. Do NOT pick draw at 5/10 unless draw probability is clearly highest OR home/away within 5% and draw_signals are strongest.

End with EXACTLY these lines:
HOME_PCT: [0-100]
DRAW_PCT: [0-100]
AWAY_PCT: [0-100]
PICK: [home|away|draw]
CONFIDENCE: [1-10]
CONFIDENCE_REASON: [one sentence]
REASONING: [one sentence on key factor]"""

    return gemini.generate(prompt, temperature=0.35)


def confidence_from_probs(probs: dict[str, int], pick: str, cap: int | None = None) -> int:
    """Map probability distribution to 1-10 confidence."""
    p = probs.get(pick, 0)
    ordered = sorted(probs.values(), reverse=True)
    spread = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]

    if p >= 62:
        base = 8
    elif p >= 52:
        base = 7
    elif p >= 42:
        base = 6
    elif p >= 36:
        base = 5
    else:
        base = 4

    if spread >= 28:
        base += 2
    elif spread >= 18:
        base += 1
    elif spread < 8:
        base -= 1

    conf = max(1, min(10, base))
    if cap is not None:
        conf = min(conf, max(1, min(10, int(cap))))
    return conf


def parse_prediction_response(text: str, stress_cap: int | None = None) -> dict:
    def _parse(pattern: str, default: str = "") -> str:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    home_pct = int(_parse(r"HOME_PCT:\s*(\d+)", "34") or 34)
    draw_pct = int(_parse(r"DRAW_PCT:\s*(\d+)", "33") or 33)
    away_pct = int(_parse(r"AWAY_PCT:\s*(\d+)", "33") or 33)
    total = home_pct + draw_pct + away_pct
    if total != 100 and total > 0:
        home_pct = round(100 * home_pct / total)
        draw_pct = round(100 * draw_pct / total)
        away_pct = 100 - home_pct - draw_pct

    probs = {"home": home_pct, "draw": draw_pct, "away": away_pct}
    pick_raw = _parse(r"PICK:\s*(\w+)", "home").lower()
    pick = pick_raw if pick_raw in ("home", "away", "draw") else max(probs, key=probs.get)

    model_conf = _parse(r"CONFIDENCE:\s*(\d+)", "")
    if model_conf.isdigit():
        confidence = max(1, min(10, int(model_conf)))
        if stress_cap is not None:
            confidence = min(confidence, stress_cap)
    else:
        confidence = confidence_from_probs(probs, pick, stress_cap)

    return {
        "pick": pick,
        "confidence": confidence,
        "confidence_reason": _parse(r"CONFIDENCE_REASON:\s*(.+)", ""),
        "reasoning": _parse(r"REASONING:\s*(.+)", "Insufficient data for strong prediction"),
        "probabilities": probs,
        "full_reasoning": text,
    }
