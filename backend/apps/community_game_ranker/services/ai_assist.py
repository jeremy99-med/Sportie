"""Hourly Claude pass: rank today's games, explain each rank, and feed the rank into the score.

`rank_day` runs from `refresh_ranker` on every 5-minute pass but acts at most once per
AI_INTERVAL. When it acts it:

1. Builds a JSON summary of each game: the formula subscores and the facts behind them. The AI
   factor, Claude's earlier rank, and its earlier reason are left out on purpose, so each hourly
   rank depends only on the other factors, never on the previous one.
2. Hashes that summary. If it matches the last successful run's inputs, nothing the rank depends
   on has changed, so Claude is not called and the current ranks stay.
3. Otherwise calls Claude, replaces the day's AIRanking rows, and re-scores the day.

The last run per day is kept in ExternalAPIMetadata (provider `anthropic`, endpoint `rank_day`):
`fetched_at` is the last check, `response` holds the inputs hash and the rankings, and
`status_code` is 200 after a good run or 502 after a failed one.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.community_game_ranker.integrations import claude
from apps.community_game_ranker.integrations.claude import ClaudeError
from apps.community_game_ranker.models import (
    AIRanking,
    ExternalAPIMetadata,
    GameLog,
    Rivalry,
    TeamStanding,
)
from apps.community_game_ranker.services import ranking, scoring

logger = logging.getLogger(__name__)

# "Every hour". Slightly under 60 minutes: refresh passes are 5 minutes apart plus their own run
# time, so a strict hour would often slip to the 13th pass.
AI_INTERVAL = timedelta(minutes=58)
PROVIDER = ExternalAPIMetadata.Provider.ANTHROPIC
ENDPOINT = "rank_day"
FAILED_STATUS = 502


def _recent_games(team_id, before):
    """The team's last finished games before `before`, most recent first, spelled out.

    One dict per game (date, opponent, result, score) rather than a "LWWWW" string: Claude
    misread that string's order and called a team that had just lost "winners of four straight".
    """
    games = (
        GameLog.objects.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))
        .filter(
            status=GameLog.Status.FINAL,
            scheduled_at__lt=before,
            home_score__isnull=False,
            away_score__isnull=False,
        )
        .select_related("home_team", "away_team")
        .order_by("-scheduled_at")[: scoring.MOMENTUM_GAMES]
    )
    out = []
    for g in games:
        at_home = g.home_team_id == team_id
        ours, theirs = (g.home_score, g.away_score) if at_home else (g.away_score, g.home_score)
        opponent = g.away_team if at_home else g.home_team
        out.append({
            "date": g.scheduled_at.astimezone(ranking.SCHEDULE_TZ).date().isoformat(),
            "opponent": opponent.abbreviation,
            "at_home": at_home,
            "result": "W" if ours > theirs else "L" if ours < theirs else "T",
            "score": f"{ours}-{theirs}",
        })
    return out


def _streak(recent):
    """Current streak from most-recent-first results, e.g. "L1" or "W4"; None with no games."""
    if not recent:
        return None
    first = recent[0]["result"]
    count = next((i for i, g in enumerate(recent) if g["result"] != first), len(recent))
    return f"{first}{count}"


def _standing(standing):
    if standing is None:
        return None
    return {
        "wins": standing.wins,
        "losses": standing.losses,
        "ties": standing.ties,
        "conference_rank": standing.conference_rank,
        "games_back": standing.games_back,
    }


def game_summary(game):
    """Everything Claude sees about one game. JSON-safe and deterministic, so it hashes stably.

    Never include the `ai` factor or the game's AIRanking here (see the module docstring).
    """
    factors = ranking.game_factors(game)
    subscores = {name: round(value, 3) for name, value in factors.items() if name != "ai"}
    team_ids = (game.home_team_id, game.away_team_id)
    standings = {
        s.team_id: s for s in TeamStanding.objects.filter(team_id__in=team_ids, season=game.season)
    }
    # Every reported injury, not just stars: the star-only list made Claude call a team with
    # a non-star out "fully healthy". The formula's star_injury factor is still stars only.
    injuries = (
        game.injuries.filter(player__team_id__in=team_ids)
        .select_related("player__team")
        .order_by("-player__is_star", "player__name")
    )
    weather = getattr(game, "weather", None)
    rivalry = Rivalry.between(game.home_team, game.away_team)
    live = game.status != "scheduled" and game.home_score is not None and game.away_score is not None

    def side(team):
        recent = _recent_games(team.pk, game.scheduled_at)
        return {
            "team": f"{team.city} {team.name}".strip(),
            "abbreviation": team.abbreviation,
            "standing": _standing(standings.get(team.pk)),
            "streak": _streak(recent),
            "recent_games_newest_first": recent,
        }

    return {
        "id": game.pk,
        "sport": game.sport.code,
        "week": game.week,
        "start_eastern": game.scheduled_at.astimezone(ranking.SCHEDULE_TZ).strftime("%H:%M"),
        "status": game.status,
        "score": {"home": game.home_score, "away": game.away_score} if live else None,
        "home": side(game.home_team),
        "away": side(game.away_team),
        "injuries": [
            {
                "player": i.player.name,
                "team": i.player.team.abbreviation if i.player.team else None,
                "is_star": i.player.is_star,
                "status": i.status,
                "status_is_estimate": i.status_estimated,
                "note": i.description,
            }
            for i in injuries
        ],
        "indoor": game.stadium.is_indoor if game.stadium else True,
        "weather": {
            "temp_c": weather.temp_c,
            "precip_mm": weather.precip_mm,
            "snow_cm": weather.snow_cm,
            "wind_kph": weather.wind_kph,
            "condition": weather.condition_text,
        }
        if weather
        else None,
        "rivalry": {"name": rivalry.name, "intensity_1_to_5": rivalry.intensity} if rivalry else None,
        "net_votes": game.votes.aggregate(net=Coalesce(Sum("value"), 0))["net"],
        "subscores": subscores,
        "formula_score": scoring.base_importance(game.sport.code, factors),
    }


def rank_day(day, now=None, force=False):
    """Run the AI pass for `day` (US Eastern) if it's due. Returns {"status", "games", "error"}.

    Status is one of: disabled (no API key), no_games, fresh (ran under AI_INTERVAL ago),
    unchanged (inputs match the last good run), ranked, error. `force` skips the interval check
    but still skips Claude when nothing changed.
    """
    now = now or timezone.now()
    if not claude.is_configured():
        return {"status": "disabled", "games": 0, "error": None}

    params = {"day": day.isoformat()}
    params_hash = ExternalAPIMetadata.hash_params(params)
    last = ExternalAPIMetadata.objects.filter(
        provider=PROVIDER, endpoint=ENDPOINT, params_hash=params_hash
    ).first()
    if last and not force and now - last.fetched_at < AI_INTERVAL:
        return {"status": "fresh", "games": 0, "error": None}

    games = list(
        ranking.games_on(day)
        .select_related("sport", "home_team", "away_team", "stadium", "weather")
        .order_by("scheduled_at", "pk")
    )
    if not games:
        return {"status": "no_games", "games": 0, "error": None}

    summaries = [game_summary(g) for g in games]
    inputs_hash = ExternalAPIMetadata.hash_params({"games": summaries, "model": claude.MODEL})
    last_good = last.response if last and last.status_code == 200 and last.response else None
    if last_good and last_good.get("inputs_hash") == inputs_hash:
        last.fetched_at = now
        last.save(update_fields=["fetched_at"])
        return {"status": "unchanged", "games": len(games), "error": None}

    try:
        rankings = claude.rank_games(summaries)
    except ClaudeError as exc:
        logger.warning("AI ranking for %s failed: %s", day, exc)
        # Keep the last good rankings (and their hash) and try again next interval.
        ExternalAPIMetadata.objects.update_or_create(
            provider=PROVIDER,
            endpoint=ENDPOINT,
            params_hash=params_hash,
            defaults={"status_code": FAILED_STATUS, "fetched_at": now,
                      "response": last.response if last else None},
        )
        return {"status": "error", "games": len(games), "error": str(exc)}

    with transaction.atomic():
        AIRanking.objects.filter(game__in=games).delete()
        AIRanking.objects.bulk_create(
            AIRanking(
                game_id=r["game_id"],
                rank=r["rank"],
                ranked_count=len(rankings),
                reason=r["reason"],
                model=claude.MODEL,
                rated_at=now,
            )
            for r in rankings
        )
        ExternalAPIMetadata.objects.update_or_create(
            provider=PROVIDER,
            endpoint=ENDPOINT,
            params_hash=params_hash,
            defaults={
                "status_code": 200,
                "fetched_at": now,
                "response": {"inputs_hash": inputs_hash, "model": claude.MODEL, "rankings": rankings},
            },
        )
    ranking.score_day(day)
    return {"status": "ranked", "games": len(games), "error": None}
