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
    WeatherCondition,
)

pytestmark = pytest.mark.django_db

KICKOFF = datetime(2026, 11, 1, 18, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def nba():
    return Sport.objects.create(code=Sport.Code.NBA, name="Basketball")


@pytest.fixture
def nfl():
    return Sport.objects.create(code=Sport.Code.NFL, name="Football", is_outdoor_default=True)


@pytest.fixture
def lakers(nba):
    return Team.objects.create(sport=nba, name="Lakers", abbreviation="LAL", city="Los Angeles")


@pytest.fixture
def celtics(nba):
    return Team.objects.create(sport=nba, name="Celtics", abbreviation="BOS", city="Boston")


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


def test_rivalry_normalizes_team_order(lakers, celtics):
    rivalry = Rivalry.objects.create(team_a=celtics, team_b=lakers, intensity=5, name="Classic")
    rivalry.refresh_from_db()
    assert rivalry.team_a_id < rivalry.team_b_id
    assert str(rivalry) == "Classic (LAL vs BOS)"


def test_rivalry_pair_unique_in_either_order(lakers, celtics):
    Rivalry.objects.create(team_a=lakers, team_b=celtics, intensity=4)
    assert_integrity_error(lambda: Rivalry.objects.create(team_a=celtics, team_b=lakers, intensity=3))


def test_rivalry_between_is_order_independent(lakers, celtics, nba):
    rivalry = Rivalry.objects.create(team_a=lakers, team_b=celtics, intensity=4)
    assert Rivalry.between(celtics, lakers) == rivalry
    assert Rivalry.between(lakers, celtics) == rivalry
    other = Team.objects.create(sport=nba, name="Knicks", abbreviation="NYK")
    assert Rivalry.between(lakers, other) is None


@pytest.mark.parametrize("intensity", [0, 6])
def test_rivalry_intensity_range(lakers, celtics, intensity):
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


def test_vote_unique_per_user_game_category(user, game):
    CommunityVote.objects.create(
        user=user, game=game, value=CommunityVote.Value.UP, category=CommunityVote.Category.ENJOYMENT
    )
    # A different category on the same game is allowed.
    CommunityVote.objects.create(
        user=user,
        game=game,
        value=CommunityVote.Value.DOWN,
        category=CommunityVote.Category.OFFICIATING,
    )
    assert_integrity_error(
        lambda: CommunityVote.objects.create(
            user=user,
            game=game,
            value=CommunityVote.Value.DOWN,
            category=CommunityVote.Category.ENJOYMENT,
        )
    )


def test_vote_value_must_be_plus_or_minus_one(user, game):
    assert_integrity_error(
        lambda: CommunityVote.objects.create(
            user=user, game=game, value=2, category=CommunityVote.Category.ENJOYMENT
        )
    )


def test_vote_str_and_cascade(user, game):
    vote = CommunityVote.objects.create(
        user=user, game=game, value=CommunityVote.Value.UP, category=CommunityVote.Category.ENJOYMENT
    )
    assert str(vote) == f"fan +1 enjoyment on game {game.pk}"
    user.delete()
    assert not CommunityVote.objects.exists()
