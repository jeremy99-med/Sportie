from datetime import date, datetime, timezone

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.community_game_ranker import views
from apps.community_game_ranker.models import (
    CommunityVote,
    GameLog,
    Injury,
    Player,
    Rivalry,
    Sport,
    Team,
    WeatherCondition,
)
from apps.community_game_ranker.services import ranking

pytestmark = pytest.mark.django_db

DAY = date(2026, 11, 1)
EVENING = datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc)
URL = "/api/ranker/games/"


@pytest.fixture(autouse=True)
def clear_throttles():
    cache.clear()


def team(sport, abbreviation):
    return Team.objects.get(sport__code=sport, abbreviation=abbreviation)


def make_game(sport, home, away, when=EVENING, **fields):
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


def user(name):
    return get_user_model().objects.create_user(username=name)


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def fan():
    return user("fan")


@pytest.fixture
def client(fan):
    c = APIClient()
    c.force_authenticate(fan)
    return c


@pytest.fixture
def games():
    """A ranked NBA day plus one NFL game the same day and one NBA game the next day."""
    low = make_game("NBA", "OKC", "WAS", importance_score=30.0)
    high = make_game("NBA", "BOS", "LAL", importance_score=80.0)  # seeded Celtics-Lakers rivalry
    nfl = make_game("NFL", "GB", "CHI", importance_score=60.0)
    make_game("NBA", "NYK", "MIA", when=datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc))
    return {"high": high, "low": low, "nfl": nfl}


# List


def test_list_is_public_and_ranked(anon, games):
    response = anon.get(URL, {"date": DAY.isoformat()})
    assert response.status_code == 200
    assert [g["id"] for g in response.json()] == [games["high"].id, games["nfl"].id, games["low"].id]
    first = response.json()[0]
    assert first["home_team"]["abbreviation"] == "BOS"
    assert first["rivalry"] == {"name": "Celtics-Lakers", "intensity": 5}
    assert first["my_vote"] is None and first["net_votes"] == 0


def test_list_filters_by_sport(anon, games):
    response = anon.get(URL, {"date": DAY.isoformat(), "sport": "NFL"})
    assert [g["id"] for g in response.json()] == [games["nfl"].id]


def test_list_defaults_to_today_eastern(anon, games, monkeypatch):
    monkeypatch.setattr(views, "_today_eastern", lambda: DAY)
    assert len(anon.get(URL).json()) == 3


@pytest.mark.parametrize("params", [{"date": "11/01/2026"}, {"sport": "NBA2"}])
def test_list_rejects_bad_params(anon, params):
    assert anon.get(URL, params).status_code == 400


def test_list_shows_only_star_injuries_and_weather(anon, games):
    high = games["high"]
    star = Player.objects.create(team=team("NBA", "BOS"), name="Star", is_star=True)
    bench = Player.objects.create(team=team("NBA", "BOS"), name="Bench")
    for p in (star, bench):
        Injury.objects.create(player=p, game=high, status="out", reported_at=EVENING)
    WeatherCondition.objects.create(game=games["nfl"], temp_c=-2, condition_text="Snow")

    by_id = {g["id"]: g for g in anon.get(URL, {"date": DAY.isoformat()}).json()}
    assert by_id[high.id]["star_injuries"] == [
        {"player": "Star", "team": "BOS", "status": "out", "status_estimated": False, "description": ""}
    ]
    assert by_id[high.id]["weather"] is None
    assert by_id[games["nfl"].id]["weather"]["condition_text"] == "Snow"


def test_list_query_count_does_not_grow_with_games(anon, games, django_assert_max_num_queries):
    for i, (home, away) in enumerate([("DEN", "PHX"), ("MIL", "CHI"), ("DAL", "HOU")]):
        make_game("NBA", home, away, importance_score=10.0 + i)
    with django_assert_max_num_queries(4):
        assert len(anon.get(URL, {"date": DAY.isoformat()}).json()) == 6


# Detail


def test_detail(anon, games):
    response = anon.get(f"{URL}{games['high'].id}/")
    assert response.status_code == 200 and response.json()["id"] == games["high"].id
    assert anon.get(f"{URL}999999/").status_code == 404


# Voting


def test_vote_requires_sign_in(anon, games):
    assert anon.post(f"{URL}{games['high'].id}/vote/", {"value": 1}).status_code == 403
    assert not CommunityVote.objects.exists()


def test_upvote_then_remove_then_downvote(client, games):
    url = f"{URL}{games['high'].id}/vote/"
    up = client.post(url, {"value": 1}).json()
    assert up["my_vote"] == 1 and up["net_votes"] == 1
    removed = client.post(url, {"value": 1}).json()
    assert removed["my_vote"] is None and removed["net_votes"] == 0
    assert removed["importance_score"] == GameLog.objects.get(pk=games["high"].pk).importance_score
    response = client.post(url, {"value": -1})
    assert response.status_code == 200
    assert response.json()["my_vote"] == -1 and response.json()["net_votes"] == -1


def test_vote_rejects_bad_value_and_missing_game(client, games):
    assert client.post(f"{URL}{games['high'].id}/vote/", {"value": 2}).status_code == 400
    assert client.post(f"{URL}999999/vote/", {"value": 1}).status_code == 404


def test_my_vote_is_per_user(client, games):
    other = user("other")
    CommunityVote.objects.create(user=other, game=games["high"], value=-1)
    CommunityVote.objects.create(user=other, game=games["low"], value=1)
    client.post(f"{URL}{games['low'].id}/vote/", {"value": -1})

    by_id = {g["id"]: g for g in client.get(URL, {"date": DAY.isoformat()}).json()}
    assert by_id[games["high"].id]["my_vote"] is None  # only the other user voted
    assert by_id[games["high"].id]["net_votes"] == -1
    assert by_id[games["low"].id]["my_vote"] == -1
    assert by_id[games["low"].id]["net_votes"] == 0


def test_votes_reorder_the_ranking(client, games):
    a = make_game("NBA", "DEN", "PHX")
    b = make_game("NBA", "MIL", "CHI")
    ranking.score_game(a)
    ranking.score_game(b)
    client.post(f"{URL}{b.id}/vote/", {"value": 1})
    ids = [g["id"] for g in client.get(URL, {"date": DAY.isoformat()}).json()]
    assert ids.index(b.id) < ids.index(a.id)


def test_votes_are_rate_limited(client, games, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"votes": "2/min"})
    url = f"{URL}{games['high'].id}/vote/"
    assert client.post(url, {"value": 1}).status_code == 200
    assert client.post(url, {"value": 1}).status_code == 200
    assert client.post(url, {"value": 1}).status_code == 429


def test_rivalry_lookup_is_order_independent(anon):
    Rivalry.objects.all().delete()
    Rivalry.objects.create(team_a=team("NBA", "LAL"), team_b=team("NBA", "BOS"), intensity=3, name="X")
    g = make_game("NBA", "LAL", "BOS")
    assert anon.get(f"{URL}{g.id}/").json()["rivalry"] == {"name": "X", "intensity": 3}
