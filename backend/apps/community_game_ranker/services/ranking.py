"""DB side of the importance score: gather each game's inputs, call the pure functions in
`scoring.py`, and save the result. Also the ranked query the API serves."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce

from apps.community_game_ranker.models import GameLog, Player, Rivalry, TeamStanding
from apps.community_game_ranker.services import scoring

# Providers list games by US calendar date, so a "day" runs midnight to midnight Eastern.
SCHEDULE_TZ = ZoneInfo("America/New_York")


def day_bounds(day):
    start = datetime.combine(day, time.min, tzinfo=SCHEDULE_TZ)
    return start, start + timedelta(days=1)


def games_on(day, sport=None):
    """GameLog rows scheduled on `day` (US Eastern), optionally for one sport code."""
    start, end = day_bounds(day)
    qs = GameLog.objects.filter(scheduled_at__gte=start, scheduled_at__lt=end)
    return qs.filter(sport__code=sport) if sport else qs


def _standing(standings, team_id):
    s = standings.get(team_id)
    if s is None:
        return None
    return {"wins": s.wins, "losses": s.losses, "ties": s.ties, "conference_rank": s.conference_rank}


def _recent_results(team_id, before):
    """The team's last finished games before `before`, most recent first: 1 win, 0 loss, 0.5 tie."""
    games = (
        GameLog.objects.filter(Q(home_team_id=team_id) | Q(away_team_id=team_id))
        .filter(
            status=GameLog.Status.FINAL,
            scheduled_at__lt=before,
            home_score__isnull=False,
            away_score__isnull=False,
        )
        .order_by("-scheduled_at")[: scoring.MOMENTUM_GAMES]
    )
    results = []
    for g in games:
        ours, theirs = (
            (g.home_score, g.away_score) if g.home_team_id == team_id else (g.away_score, g.home_score)
        )
        results.append(1.0 if ours > theirs else 0.0 if ours < theirs else 0.5)
    return results


def game_factors(game):
    """Every factor value for one game. The only place scoring inputs come from the DB."""
    sport = game.sport.code
    team_ids = (game.home_team_id, game.away_team_id)
    standings = {
        s.team_id: s for s in TeamStanding.objects.filter(team_id__in=team_ids, season=game.season)
    }
    injured_star_statuses = list(
        game.injuries.filter(player__is_star=True, player__team_id__in=team_ids).values_list(
            "status", flat=True
        )
    )
    weather = getattr(game, "weather", None)
    rivalry = Rivalry.between(game.home_team, game.away_team)
    net_votes = game.votes.aggregate(net=Coalesce(Sum("value"), 0))["net"]

    return {
        "playoff": scoring.playoff_factor(
            sport, _standing(standings, game.home_team_id), _standing(standings, game.away_team_id)
        ),
        "star_injury": scoring.star_injury_factor(
            Player.objects.filter(team_id__in=team_ids, is_star=True).count(), injured_star_statuses
        ),
        "weather": scoring.weather_factor(
            sport,
            game.stadium.is_indoor if game.stadium else True,
            {
                "precip_mm": weather.precip_mm,
                "wind_kph": weather.wind_kph,
                "condition_text": weather.condition_text,
            }
            if weather
            else None,
        ),
        "momentum": scoring.momentum_factor(
            _recent_results(game.home_team_id, game.scheduled_at),
            _recent_results(game.away_team_id, game.scheduled_at),
        ),
        "rivalry": scoring.rivalry_factor(rivalry.intensity if rivalry else None),
        "status": scoring.status_factor(game.status),
        "community": scoring.community_factor(net_votes),
    }


def score_game(game):
    """Compute and save one game's importance score. Returns the score."""
    score, breakdown = scoring.importance(game.sport.code, game_factors(game))
    game.importance_score = score
    # Keep extra keys other steps store here (e.g. the AI playoff note).
    game.score_breakdown = {**game.score_breakdown, **breakdown}
    game.save(update_fields=["importance_score", "score_breakdown"])
    return score


def score_day(day, sport=None):
    """Score every game on `day` (US Eastern). Returns the number scored."""
    games = games_on(day, sport).select_related("sport", "home_team", "away_team", "stadium", "weather")
    count = 0
    for game in games:
        score_game(game)
        count += 1
    return count


def ranked_games(qs=None):
    """Annotate `net_votes` and order by importance, with net votes breaking ties."""
    qs = GameLog.objects.all() if qs is None else qs
    return qs.annotate(net_votes=Coalesce(Sum("votes__value"), 0)).order_by(
        F("importance_score").desc(nulls_last=True), "-net_votes", "scheduled_at"
    )
