"""SportsData.io client for NFL and NBA. See .claude/docs/external-apis.md.

One API key per league (SPORTSDATA_NFL_API_KEY / SPORTSDATA_NBA_API_KEY). Trial keys return
scrambled values in some fields (injury status, scores), so use a paid key for real data.
Field names marked UNCONFIRMED in the docs are read defensively with .get().
"""

import os
from datetime import date as date_cls
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://api.sportsdata.io/v3"
TIMEOUT = 10
LEAGUES = ("NFL", "NBA")
EASTERN = ZoneInfo("America/New_York")

# Game.Status values from the NBA data dictionary (confirmed 2026-10-28). The NFL dictionary links
# to a separate guide instead of listing them; we assume the same set.
_STATUS_MAP = {
    "scheduled": "scheduled",
    "inprogress": "in_progress",
    "final": "final",
    "f/ot": "final",
    "forfeit": "final",
    "suspended": "delayed",
    "delayed": "delayed",
    "postponed": "postponed",
    "canceled": "postponed",
    "cancelled": "postponed",
}
# UNCONFIRMED numeric codes for Score.SeasonType.
_NFL_SEASON_SUFFIX = {1: "REG", 2: "PRE", 3: "POST"}

# Injury statuses we keep, mapped to our Injury.Status. "Probable" and the like are dropped.
_INJURY_STATUS = {
    "out": "out",
    "doubtful": "doubtful",
    "questionable": "questionable",
    "day-to-day": "questionable",
    "day to day": "questionable",
}
# Trial keys replace injury status, body part and notes with the word "Scrambled" but keep the
# player, team and start date. We still record those players, at this assumed severity.
SCRAMBLED = "scrambled"
SCRAMBLED_INJURY_STATUS = "questionable"


class SportsDataError(Exception):
    """Any failure talking to SportsData.io (HTTP error, network error, missing key)."""


def _api_season(league, season):
    """Our start-year season -> SportsData's label. NBA uses the ending year (confirmed live 2026-10-27)."""
    return season + 1 if league == "NBA" else season


def _our_season(league, api_season):
    if api_season is None:
        return None
    return api_season - 1 if league == "NBA" else api_season


def _check_league(league):
    if league not in LEAGUES:
        raise SportsDataError(0, f"unsupported league {league!r}")


def _get(league, feed, endpoint):
    _check_league(league)
    key = os.environ.get(f"SPORTSDATA_{league}_API_KEY")
    if not key:
        raise SportsDataError(0, f"SPORTSDATA_{league}_API_KEY is not set")
    url = f"{BASE_URL}/{league.lower()}/{feed}/json/{endpoint}"
    try:
        resp = requests.get(url, headers={"Ocp-Apim-Subscription-Key": key}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SportsDataError(0, f"request failed: {type(exc).__name__}") from exc
    if resp.status_code != 200:
        raise SportsDataError(resp.status_code, resp.text[:200])
    try:
        body = resp.json()
    except ValueError as exc:
        raise SportsDataError(resp.status_code, "response was not JSON") from exc
    # Every endpoint we call returns a JSON array of objects.
    if not isinstance(body, list) or not all(isinstance(row, dict) for row in body):
        raise SportsDataError(resp.status_code, "unexpected response shape (expected a list of objects)")
    return body


def format_date(day):
    """SportsData path date format: 2026-OCT-27."""
    if isinstance(day, str):
        day = date_cls.fromisoformat(day)
    return f"{day.year}-{day.strftime('%b').upper()}-{day.day:02d}"


def _utc_iso(raw):
    """Prefer the UTC timestamp; otherwise treat the naive `DateTime` as US Eastern."""
    utc = raw.get("DateTimeUTC")
    if utc:
        return datetime.fromisoformat(utc).replace(tzinfo=timezone.utc).isoformat()
    local = raw.get("DateTime") or raw.get("Date")
    if not local:
        return None
    return datetime.fromisoformat(local).replace(tzinfo=EASTERN).astimezone(timezone.utc).isoformat()


def _normalize_game(league, raw):
    api_season = raw.get("Season")
    season = _our_season(league, api_season)
    if league == "NFL":
        suffix = _NFL_SEASON_SUFFIX.get(raw.get("SeasonType"), "REG")
        external_id = raw.get("GameKey")
        home_id, away_id = raw.get("GlobalHomeTeamID"), raw.get("GlobalAwayTeamID")
        home_score, away_score = raw.get("HomeScore"), raw.get("AwayScore")
        week = raw.get("Week")
        season_code = f"{api_season}{suffix}" if api_season else None
    else:
        external_id = raw.get("GameID")
        home_id, away_id = raw.get("HomeTeamID"), raw.get("AwayTeamID")
        home_score, away_score = raw.get("HomeTeamScore"), raw.get("AwayTeamScore")
        week = None
        season_code = None
    status = _STATUS_MAP.get((raw.get("Status") or "").strip().lower(), "scheduled")
    return {
        "provider": "sportsdata",
        "external_id": external_id,
        "sport": league,
        "scheduled_at": _utc_iso(raw),
        "status": status,
        "season": season,
        "week": week,
        "season_code": season_code,
        "postseason": raw.get("SeasonType") == 3,
        "home_team": {"id": home_id, "abbreviation": raw.get("HomeTeam") or ""},
        "away_team": {"id": away_id, "abbreviation": raw.get("AwayTeam") or ""},
        "home_score": home_score,
        "away_score": away_score,
    }


def _games(league, body):
    return [_normalize_game(league, g) for g in body or [] if g.get("HomeTeam") and g.get("AwayTeam")]


def get_scores(league, day, final_only=False):
    """Games (with scores/status) on one day."""
    _check_league(league)
    suffix = "Final" if final_only else ""
    if league == "NFL":
        endpoint = f"ScoresByDate{suffix}/{format_date(day)}"
    else:
        endpoint = f"GamesByDate{suffix}/{format_date(day)}"
    return _games(league, _get(league, "scores", endpoint))


def get_schedule(league, season):
    """Full-season schedule. `season` is our start year."""
    _check_league(league)
    api = _api_season(league, season)
    endpoint = f"Schedules/{api}" if league == "NFL" else f"Games/{api}"
    return _games(league, _get(league, "scores", endpoint))


def get_injuries(league, season_code=None, week=None):
    """Current injuries. NFL needs `season_code` (e.g. '2026REG') and `week`; NBA is one feed."""
    _check_league(league)
    if league == "NFL":
        if not season_code or week is None:
            raise SportsDataError(0, "NFL injuries need season_code and week")
        raw = _get(league, "stats", f"Injuries/{season_code}/{week}")
    else:
        raw = _get(league, "projections", "InjuredPlayers")
    out = []
    for row in raw or []:
        label = (row.get("InjuryStatus") if league == "NBA" else row.get("Status")) or ""
        estimated = label.strip().lower() == SCRAMBLED
        status = SCRAMBLED_INJURY_STATUS if estimated else _INJURY_STATUS.get(label.strip().lower())
        if status is None or row.get("PlayerID") is None:
            continue
        if league == "NFL":
            parts = [row.get("BodyPart"), row.get("PracticeDescription")]
        else:
            parts = [row.get("InjuryBodyPart"), row.get("InjuryNotes")]
        # Trial keys scramble the body part and notes along with the status, possibly as garbage
        # text rather than the literal "Scrambled", so drop them whenever the status is estimated.
        parts = [] if estimated else [p for p in parts if p and p.strip().lower() != SCRAMBLED]
        out.append(
            {
                "player_id": row["PlayerID"],
                "name": _player_name(row),
                "team_abbreviation": row.get("Team") or "",
                "position": row.get("Position") or "",
                "status": status,
                "status_estimated": estimated,
                "description": " - ".join(parts),
            }
        )
    return out


def get_standings(league, season):
    """Standings for our start-year `season`."""
    _check_league(league)
    raw = _get(league, "scores", f"Standings/{_api_season(league, season)}")
    out = []
    for row in raw or []:
        abbreviation = row.get("Team") or row.get("Key") or ""
        if not abbreviation:
            continue
        out.append(
            {
                "team": {"id": row.get("TeamID"), "abbreviation": abbreviation},
                "season": season,
                "wins": row.get("Wins") or 0,
                "losses": row.get("Losses") or 0,
                "ties": row.get("Ties") or 0,
                "conference_rank": row.get("ConferenceRank"),
                "games_back": row.get("GamesBack"),
            }
        )
    return out


def _player_name(row):
    return row.get("Name") or f"{row.get('FirstName', '')} {row.get('LastName', '')}".strip()


def get_players(league):
    """Active players with their current team abbreviation (empty string = no team)."""
    _check_league(league)
    endpoint = "PlayersByAvailable" if league == "NFL" else "PlayersActiveBasic"
    raw = _get(league, "scores", endpoint)
    return [
        {
            "id": p["PlayerID"],
            "name": _player_name(p),
            "position": p.get("Position") or "",
            "team_abbreviation": p.get("Team") or "",
        }
        for p in raw or []
        if p.get("PlayerID") is not None
    ]


def get_player_season_stats(league, season):
    """Per-player season metric used to pick stars.

    `metric` is points+rebounds+assists per game for the NBA and season fantasy points for the
    NFL. `games` is games played.
    """
    _check_league(league)
    raw = _get(league, "stats", f"PlayerSeasonStats/{_api_season(league, season)}")
    out = []
    for row in raw or []:
        if row.get("PlayerID") is None:
            continue
        if league == "NFL":
            games = row.get("Played") or 0
            metric = row.get("FantasyPoints") or 0.0
        else:
            games = row.get("Games") or 0
            total = sum(row.get(k) or 0 for k in ("Points", "Rebounds", "Assists"))
            metric = total / games if games else 0.0
        out.append(
            {
                "player_id": row["PlayerID"],
                "name": _player_name(row),
                "team_abbreviation": row.get("Team") or "",
                "position": row.get("Position") or "",
                "games": games,
                "metric": round(float(metric), 3),
            }
        )
    return out


def get_teams(league):
    """Active teams with SportsData ids (NFL `Teams`, NBA `teams`; `AllTeams` adds inactive ones)."""
    _check_league(league)
    raw = _get(league, "scores", "Teams" if league == "NFL" else "teams")
    return [
        {
            "id": t.get("TeamID"),
            "abbreviation": t.get("Key") or "",
            "name": t.get("FullName") or f"{t.get('City', '')} {t.get('Name', '')}".strip(),
        }
        for t in raw or []
        if t.get("Key")
    ]
