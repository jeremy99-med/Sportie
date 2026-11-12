from datetime import date, datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.community_game_ranker.models import (
    CommunityVote,
    GameLog,
    Injury,
    Player,
    Rivalry,
    Sport,
    Team,
    TeamStanding,
    WeatherCondition,
)
from apps.community_game_ranker.services import ranking

pytestmark = pytest.mark.django_db

DAY = date(2026, 11, 1)
EVENING = datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc)  # 7 pm Eastern


def team(sport, abbreviation):
    return Team.objects.get(sport__code=sport, abbreviation=abbreviation)


def game(sport, home, away, when=EVENING, **fields):
    home, away = team(sport, home), team(sport, away)
    return GameLog.objects.create(
        sport=Sport.objects.get(code=sport),
        home_team=home,
        away_team=away,
        stadium=home.stadiums.first(),
        scheduled_at=when,
        season=2026,
        **fields,
    )


def standing(sport, abbreviation, rank, played):
    TeamStanding.objects.create(
        team=team(sport, abbreviation),
        season=2026,
        wins=played // 2,
        losses=played - played // 2,
        conference_rank=rank,
    )


def vote(g, value, n):
    for i in range(n):
        user = get_user_model().objects.create_user(username=f"fan{g.pk}-{value}-{i}")
        CommunityVote.objects.create(user=user, game=g, value=value)


def ranked_ids(day=DAY):
    return list(ranking.ranked_games(ranking.games_on(day)).values_list("id", flat=True))


@pytest.fixture(autouse=True)
def no_rivalries():
    """Seeded rivalries would add stakes to some pairs; tests opt in explicitly."""
    Rivalry.objects.all().delete()


def test_high_stakes_game_first_and_low_stakes_game_last():
    # Late season: two bubble teams in a rivalry vs. a leader against a cellar team.
    for abbr, rank in [("BOS", 8), ("PHI", 9), ("MIA", 6), ("ATL", 7), ("OKC", 1), ("WAS", 15)]:
        standing("NBA", abbr, rank, played=70)
    Rivalry.objects.create(team_a=team("NBA", "BOS"), team_b=team("NBA", "PHI"), intensity=4)
    high = game("NBA", "BOS", "PHI")
    middle = game("NBA", "MIA", "ATL")
    low = game("NBA", "OKC", "WAS")

    assert ranking.score_day(DAY) == 3
    assert ranked_ids() == [high.id, middle.id, low.id]


def test_votes_break_ties_between_equal_games():
    plain = game("NBA", "BOS", "PHI")
    loved = game("NBA", "MIA", "ATL")
    vote(loved, CommunityVote.Value.UP, 3)
    ranking.score_day(DAY)
    assert ranked_ids() == [loved.id, plain.id]


def test_net_votes_order_games_with_identical_scores():
    a = game("NBA", "BOS", "PHI", importance_score=50.0)
    b = game("NBA", "MIA", "ATL", importance_score=50.0)
    vote(b, CommunityVote.Value.UP, 2)
    vote(a, CommunityVote.Value.DOWN, 1)
    rows = list(ranking.ranked_games(ranking.games_on(DAY)))
    assert [r.id for r in rows] == [b.id, a.id]
    assert [r.net_votes for r in rows] == [2, -1]


def test_injured_star_lowers_the_score():
    healthy = game("NBA", "BOS", "PHI")
    hurt = game("NBA", "MIA", "ATL")
    for abbr in ["BOS", "PHI", "MIA", "ATL"]:
        Player.objects.create(team=team("NBA", abbr), name=f"{abbr} Star", is_star=True)
    star = Player.objects.get(name="MIA Star")
    Injury.objects.create(player=star, game=hurt, status=Injury.Status.OUT, reported_at=EVENING)
    ranking.score_day(DAY)
    hurt.refresh_from_db()
    healthy.refresh_from_db()
    assert hurt.score_breakdown["star_injury"] == 0.5
    assert hurt.importance_score < healthy.importance_score


def test_snow_raises_an_outdoor_nfl_game_but_not_an_indoor_one():
    outdoor = game("NFL", "GB", "CHI")  # Lambeau Field
    indoor = game("NFL", "DET", "MIN")  # Ford Field
    for g in (outdoor, indoor):
        WeatherCondition.objects.create(game=g, temp_c=-3, precip_mm=2, wind_kph=20, condition_text="Heavy snow")
    ranking.score_day(DAY)
    outdoor.refresh_from_db()
    indoor.refresh_from_db()
    assert outdoor.score_breakdown["weather"] == 1.0
    assert indoor.score_breakdown["weather"] == 0.0


def test_momentum_comes_from_recent_final_games():
    for days_ago in range(1, 4):
        game("NBA", "BOS", "WAS", when=EVENING - timedelta(days=days_ago), status="final", home_score=110, away_score=90)
    hot = game("NBA", "BOS", "PHI")
    ranking.score_game(hot)
    # BOS won 3 of 3; PHI has no finished games (neutral 0.5).
    assert hot.score_breakdown["momentum"] == pytest.approx(0.75)


def test_score_day_uses_us_eastern_dates():
    late_tip = game("NBA", "LAL", "GSW", when=datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc))  # 10 pm ET Nov 1
    next_day = game("NBA", "BOS", "PHI", when=datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc))
    assert ranking.score_day(DAY) == 1
    late_tip.refresh_from_db()
    next_day.refresh_from_db()
    assert late_tip.importance_score is not None and next_day.importance_score is None


def test_score_game_keeps_other_breakdown_keys():
    g = game("NBA", "BOS", "PHI", score_breakdown={"playoff_ai": {"rationale": "x"}})
    ranking.score_game(g)
    g.refresh_from_db()
    assert g.score_breakdown["playoff_ai"] == {"rationale": "x"}
    assert "playoff" in g.score_breakdown


def test_ingest_ranker_scores_the_day(monkeypatch, capsys):
    monkeypatch.setattr(
        "apps.community_game_ranker.services.ingest.ingest_day", lambda day, sports: {}
    )
    g = game("NBA", "BOS", "PHI")
    call_command("ingest_ranker", date=DAY.isoformat(), sport="NBA")
    g.refresh_from_db()
    assert g.importance_score is not None
    assert "scored NBA: 1 games" in capsys.readouterr().out
