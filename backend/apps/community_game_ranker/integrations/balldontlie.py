"""balldontlie.io client (NBA). See .claude/docs/external-apis.md.

Free tier: 5 requests/min, and only teams, players and games. Standings and season averages
need the GOAT tier; on a lower tier those calls raise BalldontlieError (401/403).
"""

import os
from datetime import date as date_cls

import requests

BASE_URL = "https://api.balldontlie.io/v1"
TIMEOUT = 10
PER_PAGE = 100
MAX_PAGES = 20  # safety stop for cursor loops


class BalldontlieError(Exception):
    """Any failure talking to balldontlie (HTTP error, network error, missing key)."""


def _get(path, params=None):
    key = os.environ.get("BALLDONTLIE_API_KEY")
    if not key:
        raise BalldontlieError(0, "BALLDONTLIE_API_KEY is not set")
    try:
        resp = requests.get(
            f"{BASE_URL}{path}",
            params=params,
            headers={"Authorization": key},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise BalldontlieError(0, f"request failed: {type(exc).__name__}") from exc
    if resp.status_code != 200:
        raise BalldontlieError(resp.status_code, resp.text[:200])
    try:
        return resp.json()
    except ValueError as exc:
        raise BalldontlieError(resp.status_code, "response was not JSON") from exc


def _get_all(path, params=None):
    """Follow `meta.next_cursor` and return every item in `data`."""
    params = dict(params or {})
    params.setdefault("per_page", PER_PAGE)
    items = []
    for _ in range(MAX_PAGES):
        body = _get(path, params)
        items.extend(body.get("data") or [])
        cursor = (body.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
        params["cursor"] = cursor
    return items


def _team_ref(team):
    team = team or {}
    return {"id": team.get("id"), "abbreviation": team.get("abbreviation") or ""}


def _game_status(raw):
    if raw.get("postponed"):
        return "postponed"
    text = (raw.get("status") or "").strip().lower()
    if text.startswith("final"):
        return "final"
    if (raw.get("period") or 0) > 0:
        return "in_progress"
    return "scheduled"


def _normalize_game(raw):
    return {
        "provider": "balldontlie",
        "external_id": raw["id"],
        "sport": "NBA",
        "scheduled_at": raw.get("datetime") or raw.get("date"),
        "status": _game_status(raw),
        "season": raw.get("season"),
        "week": None,
        "season_code": None,
        "postseason": bool(raw.get("postseason")),
        "home_team": _team_ref(raw.get("home_team")),
        "away_team": _team_ref(raw.get("visitor_team")),
        "home_score": raw.get("home_team_score"),
        "away_score": raw.get("visitor_team_score"),
    }


def get_games(day):
    """Games on one calendar day (date or YYYY-MM-DD string)."""
    day = day.isoformat() if isinstance(day, date_cls) else day
    return [_normalize_game(g) for g in _get_all("/games", {"dates[]": day})]


def get_games_between(start, end):
    """Games between two dates, inclusive. One paginated call; good for backfills."""
    start = start.isoformat() if isinstance(start, date_cls) else start
    end = end.isoformat() if isinstance(end, date_cls) else end
    params = {"start_date": start, "end_date": end}
    return [_normalize_game(g) for g in _get_all("/games", params)]


def get_teams():
    body = _get("/teams")
    return [
        {
            "id": t["id"],
            "abbreviation": t.get("abbreviation") or "",
            "name": t.get("full_name") or t.get("name") or "",
        }
        for t in body.get("data") or []
    ]


def get_players(team_id):
    """Players on one team. Mind the 5 req/min free limit: do not loop over all teams."""
    raw = _get_all("/players", {"team_ids[]": team_id})
    return [
        {
            "id": p["id"],
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
            "position": p.get("position") or "",
            "team": _team_ref(p["team"]) if p.get("team") else None,
        }
        for p in raw
    ]


def get_standings(season):
    """NBA standings for a season start year. GOAT tier only."""
    body = _get("/standings", {"season": season})
    return [
        {
            "team": _team_ref(s.get("team")),
            "season": s.get("season", season),
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "conference_rank": s.get("conference_rank"),
        }
        for s in body.get("data") or []
    ]


def get_season_averages(season, player_ids, category="general", stat_type="base"):
    """Per-player season averages. GOAT tier only; response keys are UNCONFIRMED."""
    params = {
        "season": season,
        "season_type": "regular",
        "type": stat_type,
        "player_ids[]": list(player_ids),
    }
    raw = _get_all(f"/season_averages/{category}", params)
    out = []
    for row in raw:
        stats = row.get("stats") or {}
        out.append(
            {
                "player_id": (row.get("player") or {}).get("id"),
                "games": stats.get("gp"),
                "pts": stats.get("pts"),
                "reb": stats.get("reb"),
                "ast": stats.get("ast"),
            }
        )
    return out
