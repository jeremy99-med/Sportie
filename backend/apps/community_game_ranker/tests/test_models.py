from datetime import datetime, timezone as dt_timezone

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.community_game_ranker.models import (
    CommunityVote,
    ExternalAPIMetadata,
    GameLog,
    Injury,
    Player,
    Rivalry,
    Sport,
    Stadium,
    Team,
    TeamStanding,
    WeatherCondition,
)

pytestmark = pytest.mark.django_db

KICKOFF = datetime(2026, 11, 1, 18, 0, tzinfo=dt_timezone.utc)


# Sports, NBA/NFL teams, stadiums, and rivalries are seeded by migration 0003, so fixtures
# fetch those rows instead of creating them.
@pytest.fixture
def nba():
    return Sport.objects.get(code=Sport.Code.NBA)


@pytest.fixture
def nfl():
    return Sport.objects.get(code=Sport.Code.NFL)


@pytest.fixture
def lakers(nba):
    return Team.objects.get(sport=nba, abbreviation="LAL")


@pytest.fixture
def celtics(nba):
    return Team.objects.get(sport=nba, abbreviation="BOS")


@pytest.fixture
def no_rivalries():
    """Clear the seeded rivalries so tests can create pairs from scratch."""
    Rivalry.objects.all().delete()


@pytest.fixture
def game(nba, lakers, celtics):
    return GameLog.objects.create(
        sport=nba, home_team=lakers, away_team=celtics, scheduled_at=KICKOFF, season=2026
    )


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="fan", password="pw-unused")


def assert_integrity_error(fn):
    with pytest.raises(IntegrityError), transaction.atomic():
        fn()


# Sport / Team


def test_sport_code_unique(nba):
    assert_integrity_error(lambda: Sport.objects.create(code=Sport.Code.NBA, name="Dup"))


def test_team_abbreviation_unique_per_sport(nba, nfl, lakers):
    assert_integrity_error(lambda: Team.objects.create(sport=nba, name="X", abbreviation="LAL"))
    # The same abbreviation in a different sport is fine.
    Team.objects.create(sport=nfl, name="Other", abbreviation="LAL")


def test_sport_protected_while_teams_exist(nba, lakers):
    with pytest.raises(ProtectedError):
        nba.delete()


def test_sport_and_team_str(nba, lakers):
    assert str(nba) == "NBA"
    assert str(lakers) == "LAL (NBA)"


# Stadium / Player


def test_stadium_latitude_range_enforced(lakers):
    assert_integrity_error(
        lambda: Stadium.objects.create(name="Bad", latitude=95, longitude=0, home_team=lakers)
    )


def test_stadium_survives_team_delete(nba):
    team = Team.objects.create(sport=nba, name="Temp", abbreviation="TMP")
    stadium = Stadium.objects.create(name="Arena", latitude=34.04, longitude=-118.27, home_team=team)
    team.delete()
    stadium.refresh_from_db()
    assert stadium.home_team is None
    assert str(stadium) == "Arena"


def test_player_str_with_and_without_team(lakers):
    assert str(Player.objects.create(name="LeBron James", team=lakers)) == "LeBron James (LAL)"
    assert str(Player.objects.create(name="Free Agent")) == "Free Agent (FA)"


# GameLog


def test_game_defaults_and_str(game):
    assert game.status == GameLog.Status.SCHEDULED
    assert game.home_score is None and game.importance_score is None
    assert game.score_breakdown == {}
    assert str(game) == "BOS @ LAL (NBA, 2026-11-01)"


def test_game_home_and_away_must_differ(nba, lakers):
    assert_integrity_error(
        lambda: GameLog.objects.create(
            sport=nba, home_team=lakers, away_team=lakers, scheduled_at=KICKOFF, season=2026
        )
    )


def test_game_clean_rejects_team_from_other_sport(nfl, lakers, celtics):
    game = GameLog(sport=nfl, home_team=lakers, away_team=celtics, scheduled_at=KICKOFF, season=2026)
    with pytest.raises(ValidationError) as exc:
        game.full_clean()
    assert {"home_team", "away_team"} <= exc.value.message_dict.keys()


def test_team_protected_while_games_exist(game, lakers):
    with pytest.raises(ProtectedError):
        lakers.delete()


# TeamStanding


def test_standing_unique_per_team_season(lakers):
    TeamStanding.objects.create(team=lakers, season=2026, wins=5, losses=2)
    assert_integrity_error(lambda: TeamStanding.objects.create(team=lakers, season=2026))
    # A new season is a new row.
    TeamStanding.objects.create(team=lakers, season=2027)


def test_standing_str_shows_ties_only_when_present(lakers, nfl):
    assert str(TeamStanding.objects.create(team=lakers, season=2026, wins=5, losses=2)) == (
        "LAL 2026: 5-2"
    )
    bears = Team.objects.get(sport=nfl, abbreviation="CHI")
    assert str(TeamStanding.objects.create(team=bears, season=2026, wins=4, losses=3, ties=1)) == (
        "CHI 2026: 4-3-1"
    )


# Injury / Weather


def test_injury_unique_per_player_game(game, lakers):
    player = Player.objects.create(name="LeBron James", team=lakers, is_star=True)
    Injury.objects.create(player=player, game=game, status=Injury.Status.OUT, reported_at=KICKOFF)
    assert_integrity_error(
        lambda: Injury.objects.create(
            player=player, game=game, status=Injury.Status.DOUBTFUL, reported_at=KICKOFF
        )
    )
    assert str(player.injuries.get()) == "LeBron James: Out"


def test_weather_one_per_game_and_nonnegative(game):
    weather = WeatherCondition.objects.create(game=game, temp_c=12.4, condition_text="Cloudy")
    assert game.weather == weather
    assert str(weather) == "12°C, Cloudy"
    assert_integrity_error(lambda: WeatherCondition.objects.create(game=game, temp_c=5))
    weather.delete()
    assert_integrity_error(lambda: WeatherCondition.objects.create(game=game, temp_c=5, wind_kph=-1))


# Rivalry


def test_rivalry_normalizes_team_order(no_rivalries, lakers, celtics):
    rivalry = Rivalry.objects.create(team_a=celtics, team_b=lakers, intensity=5, name="Classic")
    rivalry.refresh_from_db()
    assert rivalry.team_a_id < rivalry.team_b_id
    # BOS is seeded before LAL, so it has the lower pk and becomes team_a.
    assert str(rivalry) == "Classic (BOS vs LAL)"


def test_rivalry_pair_unique_in_either_order(no_rivalries, lakers, celtics):
    Rivalry.objects.create(team_a=lakers, team_b=celtics, intensity=4)
    assert_integrity_error(lambda: Rivalry.objects.create(team_a=celtics, team_b=lakers, intensity=3))


def test_rivalry_between_is_order_independent(no_rivalries, lakers, celtics, nba):
    rivalry = Rivalry.objects.create(team_a=lakers, team_b=celtics, intensity=4)
    assert Rivalry.between(celtics, lakers) == rivalry
    assert Rivalry.between(lakers, celtics) == rivalry
    other = Team.objects.get(sport=nba, abbreviation="NYK")
    assert Rivalry.between(lakers, other) is None


@pytest.mark.parametrize("intensity", [0, 6])
def test_rivalry_intensity_range(no_rivalries, lakers, celtics, intensity):
    assert_integrity_error(
        lambda: Rivalry.objects.create(team_a=lakers, team_b=celtics, intensity=intensity)
    )


# ExternalAPIMetadata


def test_hash_params_is_key_order_independent():
    assert ExternalAPIMetadata.hash_params({"a": 1, "b": 2}) == ExternalAPIMetadata.hash_params(
        {"b": 2, "a": 1}
    )
    assert ExternalAPIMetadata.hash_params({"a": 1}) != ExternalAPIMetadata.hash_params({"a": 2})
    assert len(ExternalAPIMetadata.hash_params(None)) == 64


def test_api_cache_key_unique():
    key = dict(
        provider=ExternalAPIMetadata.Provider.BALLDONTLIE,
        endpoint="/games",
        params_hash=ExternalAPIMetadata.hash_params({"date": "2026-11-01"}),
    )
    entry = ExternalAPIMetadata.objects.create(**key, status_code=200, response={"data": []})
    assert str(entry) == "balldontlie /games [200]"
    assert_integrity_error(lambda: ExternalAPIMetadata.objects.create(**key, status_code=500))


# CommunityVote


def test_vote_unique_per_user_game(user, game):
    CommunityVote.objects.create(user=user, game=game, value=CommunityVote.Value.UP)
    assert_integrity_error(
        lambda: CommunityVote.objects.create(user=user, game=game, value=CommunityVote.Value.DOWN)
    )


def test_vote_value_must_be_plus_or_minus_one(user, game):
    assert_integrity_error(lambda: CommunityVote.objects.create(user=user, game=game, value=2))


def test_vote_str_and_cascade(user, game):
    vote = CommunityVote.objects.create(user=user, game=game, value=CommunityVote.Value.UP)
    assert str(vote) == f"fan +1 on game {game.pk}"
    user.delete()
    assert not CommunityVote.objects.exists()
