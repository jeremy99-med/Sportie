"""Ingest: the only module that touches both the API clients and the ORM.

Every provider call goes through `cached_call`, which reads and writes `ExternalAPIMetadata`
so repeated runs do not burn quota. Clients return JSON-safe normalized dicts, so they can be
cached as-is.
"""

import logging
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.community_game_ranker.integrations import balldontlie, sportsdata, weatherapi
from apps.community_game_ranker.integrations.balldontlie import BalldontlieError
from apps.community_game_ranker.integrations.sportsdata import SportsDataError
from apps.community_game_ranker.integrations.weatherapi import WeatherAPIError
from apps.community_game_ranker.models import (
    ExternalAPIMetadata,
    GameLog,
    Injury,
    Player,
    Sport,
    Team,
    TeamStanding,
    WeatherCondition,
)
from apps.community_game_ranker.services import stars as stars_service
from apps.community_game_ranker.services.ranking import SCHEDULE_TZ

logger = logging.getLogger(__name__)

SUPPORTED_SPORTS = ("NBA", "NFL")
PROVIDER_ERRORS = (BalldontlieError, SportsDataError, WeatherAPIError)

# Cache lifetimes. SportsData recommends 5 min for injuries/standings, 15 min for player stats.
LIVE_TTL = timedelta(minutes=5)
FINAL_TTL = timedelta(hours=12)
STANDINGS_TTL = timedelta(minutes=30)
ROSTER_TTL = timedelta(hours=24)
WEATHER_TTL = timedelta(hours=3)

WEATHER_WINDOW = timedelta(days=3)  # WeatherAPI free plan forecasts 3 days
GAME_MATCH_WINDOW = timedelta(hours=12)  # same teams within this window = same game
BACKFILL_DAYS = 14

# Provider abbreviation -> our abbreviation (matches seed/teams_*.json). Providers disagree,
# e.g. PHO/PHX, GS/GSW, NO/NOP, WSH/WAS, JAC/JAX, LA/LAR. Unlisted abbreviations pass through.
TEAM_ALIASES = {
    "NBA": {
        "PHO": "PHX",
        "GS": "GSW",
        "NO": "NOP",
        "NOR": "NOP",
        "NY": "NYK",
        "SA": "SAS",
        "BRK": "BKN",
        "BK": "BKN",
        "CHO": "CHA",
        "UTAH": "UTA",
        "WSH": "WAS",
    },
    "NFL": {
        "JAC": "JAX",
        "LA": "LAR",
        "STL": "LAR",
        "WSH": "WAS",
        "ARZ": "ARI",
        "BLT": "BAL",
        "CLV": "CLE",
        "HST": "HOU",
        "SD": "LAC",
        "OAK": "LV",
        "KAN": "KC",
        "GNB": "GB",
        "NWE": "NE",
        "NOR": "NO",
        "SFO": "SF",
        "TAM": "TB",
    },
}


def normalize_abbreviation(sport, abbreviation):
    abbreviation = (abbreviation or "").strip().upper()
    return TEAM_ALIASES.get(sport, {}).get(abbreviation, abbreviation)


def current_season(day):
    """Season start year for a date. Both leagues start in the fall; Mar-Aug show last season."""
    return day.year if day.month >= 9 else day.year - 1


def _player_key(sport):
    return f"sportsdata_{sport.lower()}"


# ---------------------------------------------------------------- cache


def cached_call(provider, endpoint, params, fn, max_age):
    """Return a cached response when a fresh one exists, else call `fn()` and cache the result.

    The cache key is (provider, endpoint, hash of params). Only successful (200) responses are
    reused. If `fn` raises, nothing is cached and the error propagates.
    """
    params_hash = ExternalAPIMetadata.hash_params(params)
    now = timezone.now()
    row = ExternalAPIMetadata.objects.filter(
        provider=provider, endpoint=endpoint, params_hash=params_hash
    ).first()
    if row and row.status_code == 200 and row.response is not None and now - row.fetched_at < max_age:
        return row.response
    data = fn()
    ExternalAPIMetadata.objects.update_or_create(
        provider=provider,
        endpoint=endpoint,
        params_hash=params_hash,
        defaults={"response": data, "status_code": 200, "fetched_at": now},
    )
    return data


# ---------------------------------------------------------------- helpers


def _parse_when(value):
    if not value:
        return None
    when = parse_datetime(value)
    if when is None:
        day = parse_date(value)
        if day is None:
            return None
        when = datetime(day.year, day.month, day.day)
    if timezone.is_naive(when):
        when = when.replace(tzinfo=dt_timezone.utc)
    return when


def _team_map(sport):
    return {t.abbreviation: t for t in Team.objects.filter(sport__code=sport)}


def _resolve_team(sport, teams, ref):
    return teams.get(normalize_abbreviation(sport, ref.get("abbreviation")))


def _ttl_for_day(day, now):
    """`day` is a US Eastern calendar day, so compare it against today's Eastern date, not UTC's."""
    today = now.astimezone(SCHEDULE_TZ).date()
    return LIVE_TTL if day >= today - timedelta(days=1) else FINAL_TTL


def _fetch_games(sport, day, now):
    ttl = _ttl_for_day(day, now)
    if sport == "NBA":
        return cached_call(
            "balldontlie", "games", {"date": day.isoformat()}, lambda: balldontlie.get_games(day), ttl
        )
    return cached_call(
        "sportsdata",
        "ScoresByDate",
        {"league": sport, "date": day.isoformat()},
        lambda: sportsdata.get_scores(sport, day),
        ttl,
    )


def _upsert_games(sport, games, summary):
    """Upsert normalized games. Returns the GameLog rows."""
    sport_obj = Sport.objects.get(code=sport)
    teams = _team_map(sport)
    rows = []
    for g in games:
        home = _resolve_team(sport, teams, g["home_team"])
        away = _resolve_team(sport, teams, g["away_team"])
        when = _parse_when(g.get("scheduled_at"))
        if home is None or away is None or home == away or when is None or g.get("season") is None:
            summary["skipped"] += 1
            logger.warning("Skipping %s game %s: unmapped teams or missing time", sport, g.get("external_id"))
            continue
        game, created = GameLog.objects.update_or_create(
            sport=sport_obj,
            home_team=home,
            away_team=away,
            scheduled_at__range=(when - GAME_MATCH_WINDOW, when + GAME_MATCH_WINDOW),
            defaults={
                "scheduled_at": when,
                "status": g["status"],
                "home_score": g.get("home_score"),
                "away_score": g.get("away_score"),
                "season": g["season"],
                "week": g.get("week"),
                "stadium": home.stadiums.first(),
            },
        )
        summary["created" if created else "updated"] += 1
        # Kept for later steps (injury lookup by NFL week, season code).
        game._ingest = {"season_code": g.get("season_code")}
        rows.append(game)
    return rows


def _new_summary():
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "standings": 0,
        "injuries": 0,
        "weather": 0,
        "errors": [],
    }


def _record_error(summary, step, exc):
    logger.warning("Ingest step %s failed: %r", step, exc)
    summary["errors"].append(f"{step}: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- standings


def _sync_standings(sport, season, summary):
    data = cached_call(
        "sportsdata",
        "Standings",
        {"league": sport, "season": season},
        lambda: sportsdata.get_standings(sport, season),
        STANDINGS_TTL,
    )
    teams = _team_map(sport)
    for row in data:
        team = _resolve_team(sport, teams, row["team"])
        if team is None:
            continue
        TeamStanding.objects.update_or_create(
            team=team,
            season=season,
            defaults={
                "wins": row.get("wins") or 0,
                "losses": row.get("losses") or 0,
                "ties": row.get("ties") or 0,
                "conference_rank": row.get("conference_rank"),
                "games_back": row.get("games_back"),
            },
        )
        summary["standings"] += 1


# ---------------------------------------------------------------- injuries


def _fetch_injuries(sport, games):
    """Return all current injuries for the sport (NFL: one call per season-code/week)."""
    if sport == "NBA":
        return cached_call(
            "sportsdata",
            "InjuredPlayers",
            {"league": sport},
            lambda: sportsdata.get_injuries(sport),
            LIVE_TTL,
        )
    out, seen = [], set()
    for game in games:
        code, week = game._ingest["season_code"], game.week
        if not code or week is None or (code, week) in seen:
            continue
        seen.add((code, week))
        out.extend(
            cached_call(
                "sportsdata",
                "Injuries",
                {"league": sport, "season": code, "week": week},
                lambda code=code, week=week: sportsdata.get_injuries(sport, code, week),
                LIVE_TTL,
            )
        )
    return out


def _sync_injuries(sport, games, now, summary):
    open_games = [g for g in games if g.status in (GameLog.Status.SCHEDULED, GameLog.Status.IN_PROGRESS, GameLog.Status.DELAYED)]
    if not open_games:
        return
    injuries = _fetch_injuries(sport, open_games)
    key = _player_key(sport)
    players = {
        p.external_ids[key]: p
        for p in Player.objects.filter(external_ids__has_key=key)
    }
    for game in open_games:
        game_abbrs = {game.home_team.abbreviation, game.away_team.abbreviation}
        seen_ids = set()
        for inj in injuries:
            if normalize_abbreviation(sport, inj["team_abbreviation"]) not in game_abbrs:
                continue
            player = players.get(inj["player_id"])
            if player is None:
                continue
            Injury.objects.update_or_create(
                player=player,
                game=game,
                defaults={
                    "status": inj["status"],
                    "status_estimated": inj.get("status_estimated", False),
                    "description": inj["description"],
                },
                create_defaults={
                    "status": inj["status"],
                    "status_estimated": inj.get("status_estimated", False),
                    "description": inj["description"],
                    "reported_at": now,
                },
            )
            seen_ids.add(player.id)
            summary["injuries"] += 1
        # Players who recovered since the last run no longer appear in the feed.
        game.injuries.exclude(player_id__in=seen_ids).delete()


# ---------------------------------------------------------------- weather


def _sync_weather(games, now, summary):
    for game in games:
        stadium = game.stadium
        if stadium is None or stadium.is_indoor:
            continue
        if game.status in (GameLog.Status.FINAL, GameLog.Status.POSTPONED):
            continue
        if not (now - timedelta(hours=6) <= game.scheduled_at <= now + WEATHER_WINDOW):
            continue
        lat, lon = float(stadium.latitude), float(stadium.longitude)
        when = game.scheduled_at.isoformat()
        try:
            data = cached_call(
                "weatherapi",
                "forecast",
                {"lat": lat, "lon": lon, "when": when},
                lambda lat=lat, lon=lon, when=game.scheduled_at: weatherapi.get_forecast(lat, lon, when),
                WEATHER_TTL,
            )
        except WeatherAPIError as exc:
            _record_error(summary, f"weather {game.id}", exc)
            continue
        if data.get("temp_c") is None:
            continue
        WeatherCondition.objects.update_or_create(
            game=game,
            defaults={
                "temp_c": data["temp_c"],
                "precip_mm": data.get("precip_mm") or 0,
                "snow_cm": data.get("snow_cm") or 0,
                "wind_kph": data.get("wind_kph") or 0,
                "condition_text": (data.get("condition_text") or "")[:100],
                "fetched_at": now,
            },
        )
        summary["weather"] += 1


# ---------------------------------------------------------------- public: games


def ingest_day(day, sports=SUPPORTED_SPORTS, now=None):
    """Ingest one day: games, standings, injuries, weather. Returns {sport: summary}.

    A failure in one step (for example a rate-limited provider) is recorded in that sport's
    `errors` list and does not stop the other steps.
    """
    if isinstance(day, str):
        day = date.fromisoformat(day)
    now = now or timezone.now()
    results = {}
    for sport in sports:
        if sport not in SUPPORTED_SPORTS:
            raise ValueError(f"Unsupported sport {sport!r}; use one of {SUPPORTED_SPORTS}")
        summary = results[sport] = _new_summary()
        try:
            raw_games = _fetch_games(sport, day, now)
        except PROVIDER_ERRORS as exc:
            _record_error(summary, "games", exc)
            continue
        with transaction.atomic():
            games = _upsert_games(sport, raw_games, summary)
        if not games:
            continue  # nothing scheduled: skip the rest to save quota
        steps = (
            ("standings", lambda: _sync_standings(sport, games[0].season, summary)),
            ("injuries", lambda: _sync_injuries(sport, games, now, summary)),
            ("weather", lambda: _sync_weather(games, now, summary)),
        )
        for name, step in steps:
            try:
                step()
            except PROVIDER_ERRORS as exc:
                _record_error(summary, name, exc)
    return results


def backfill_finished(end_day, days=BACKFILL_DAYS, sports=SUPPORTED_SPORTS, now=None):
    """Upsert finished games from the `days` days before `end_day` (for the momentum factor)."""
    if isinstance(end_day, str):
        end_day = date.fromisoformat(end_day)
    now = now or timezone.now()
    start, end = end_day - timedelta(days=days), end_day - timedelta(days=1)
    results = {}
    for sport in sports:
        if sport not in SUPPORTED_SPORTS:
            raise ValueError(f"Unsupported sport {sport!r}; use one of {SUPPORTED_SPORTS}")
        summary = results[sport] = _new_summary()
        try:
            if sport == "NBA":
                raw = cached_call(
                    "balldontlie",
                    "games_range",
                    {"start": start.isoformat(), "end": end.isoformat()},
                    lambda: balldontlie.get_games_between(start, end),
                    FINAL_TTL,
                )
            else:
                raw = []
                for offset in range(days):
                    day = start + timedelta(days=offset)
                    raw.extend(
                        cached_call(
                            "sportsdata",
                            "ScoresByDateFinal",
                            {"league": sport, "date": day.isoformat()},
                            lambda day=day: sportsdata.get_scores(sport, day, final_only=True),
                            FINAL_TTL,
                        )
                    )
        except PROVIDER_ERRORS as exc:
            _record_error(summary, "backfill", exc)
            continue
        with transaction.atomic():
            _upsert_games(sport, [g for g in raw if g["status"] == "final"], summary)
    return results


# ---------------------------------------------------------------- public: rosters


def _link_team_ids(sport, summary):
    """Fill Team.external_ids by (aliased) abbreviation. Returns how many teams changed."""
    sources = [
        ("sportsdata", lambda: sportsdata.get_teams(sport)),
    ]
    if sport == "NBA":
        sources.append(("balldontlie", balldontlie.get_teams))
    teams = _team_map(sport)
    changed = set()
    for provider, fn in sources:
        try:
            data = cached_call(provider, "teams", {"league": sport}, fn, ROSTER_TTL)
        except PROVIDER_ERRORS as exc:
            _record_error(summary, f"teams {provider}", exc)
            continue
        for row in data:
            team = teams.get(normalize_abbreviation(sport, row["abbreviation"]))
            if team is None or row.get("id") is None:
                continue
            if team.external_ids.get(provider) != row["id"]:
                team.external_ids = {**team.external_ids, provider: row["id"]}
                changed.add(team)
    for team in changed:
        team.save(update_fields=["external_ids"])
    return len(changed)


def sync_rosters(sport):
    """Sync Team.external_ids and Players for one sport from SportsData.io.

    Players are matched by external id, so a traded player just gets a new team and keeps
    `is_star`. Players first created by `seed_stars` (no id yet) are matched by team + name.
    Players who dropped off a roster (or moved to an unknown team) get `team=None`.
    """
    if sport not in SUPPORTED_SPORTS:
        raise ValueError(f"Unsupported sport {sport!r}; use one of {SUPPORTED_SPORTS}")
    summary = {"teams_linked": 0, "created": 0, "updated": 0, "moved": 0, "released": 0, "errors": []}
    summary["teams_linked"] = _link_team_ids(sport, summary)

    data = cached_call(
        "sportsdata", "players", {"league": sport}, lambda: sportsdata.get_players(sport), ROSTER_TTL
    )
    key = _player_key(sport)
    teams = _team_map(sport)
    by_id = {p.external_ids[key]: p for p in Player.objects.filter(external_ids__has_key=key)}
    unclaimed = {
        (p.team_id, p.name): p
        for p in Player.objects.filter(team__sport__code=sport).exclude(external_ids__has_key=key)
    }
    to_create, to_update = [], {}
    for row in data:
        team = teams.get(normalize_abbreviation(sport, row["team_abbreviation"]))
        player = by_id.get(row["id"])
        if player is None and team is not None:
            player = unclaimed.pop((team.id, row["name"]), None)
        if player is None:
            if team is not None:  # ignore players with no team we track
                to_create.append(
                    Player(
                        team=team,
                        name=row["name"],
                        position=row["position"],
                        external_ids={key: row["id"]},
                    )
                )
            continue
        before = (player.team_id, player.name, player.position, player.external_ids.get(key))
        if before[0] is not None and (team.id if team else None) != before[0]:
            summary["moved" if team else "released"] += 1
        player.team = team
        player.name = row["name"]
        player.position = row["position"]
        player.external_ids = {**player.external_ids, key: row["id"]}
        if before != (player.team_id, player.name, player.position, row["id"]):
            to_update[player.id] = player
    with transaction.atomic():
        Player.objects.bulk_create(to_create)
        Player.objects.bulk_update(list(to_update.values()), ["team", "name", "position", "external_ids"])
    summary["created"] = len(to_create)
    summary["updated"] = len(to_update)
    return summary


def refresh_stars(sport, day=None, overrides=None):
    """Compute stars from season stats (`pick_stars`) and apply the overrides. Returns (marked, cleared)."""
    day = day or timezone.now().date()
    season = current_season(day)
    stats = cached_call(
        "sportsdata",
        "PlayerSeasonStats",
        {"league": sport, "season": season},
        lambda: sportsdata.get_player_season_stats(sport, season),
        ROSTER_TTL,
    )
    # The stats feed abbreviates names ("J.Allen") while the roster feed has full names
    # ("Josh Allen"), so use the roster's name for each provider id. Run sync_rosters first.
    key = _player_key(sport)
    roster_names = {
        p.external_ids[key]: p.name for p in Player.objects.filter(external_ids__has_key=key)
    }
    excluded = stars_service.NON_STAR_POSITIONS.get(sport, set())
    stats = [
        {**row, "name": roster_names[row["player_id"]]}
        for row in stats
        if row.get("player_id") in roster_names and row.get("position") not in excluded
    ]
    # Early in the season nobody has MIN_GAMES yet, so require half the games played so far.
    most_games = max((row.get("games") or 0 for row in stats), default=0)
    min_games = min(stars_service.MIN_GAMES[sport], max(1, most_games // 2))
    picked = stars_service.pick_stars(stats, per_team=3, min_games=min_games)
    known = _team_map(sport)
    picked = {
        normalize_abbreviation(sport, team): names
        for team, names in picked.items()
        if normalize_abbreviation(sport, team) in known
    }
    return stars_service.sync_stars(
        {sport: picked}, {sport: overrides[sport]} if overrides and sport in overrides else None
    )
