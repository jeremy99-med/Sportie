import pytest
import requests

from apps.community_game_ranker.integrations import balldontlie, sportsdata, weatherapi
from apps.community_game_ranker.integrations.balldontlie import BalldontlieError
from apps.community_game_ranker.integrations.sportsdata import SportsDataError
from apps.community_game_ranker.integrations.weatherapi import WeatherAPIError

from .conftest import load_fixture

# ---------------------------------------------------------------- balldontlie


def test_balldontlie_get_games_normalizes(http):
    http.add("/v1/games", load_fixture("balldontlie", "games"))
    games = balldontlie.get_games("2026-10-29")

    assert [g["external_id"] for g in games] == [1001, 1002, 1003]
    final, scheduled, live = games
    assert final["status"] == "final" and final["home_score"] == 118 and final["away_score"] == 110
    assert scheduled["status"] == "scheduled"
    assert live["status"] == "in_progress"
    assert final["home_team"] == {"id": 14, "abbreviation": "LAL"}
    assert final["away_team"] == {"id": 10, "abbreviation": "GS"}  # raw provider abbreviation
    assert final["sport"] == "NBA" and final["season"] == 2026
    call = http.calls[0]
    assert call["headers"] == {"Authorization": "test-key"}
    assert call["params"]["dates[]"] == "2026-10-29"
    assert call["timeout"] == balldontlie.TIMEOUT


def test_balldontlie_teams_and_players(http):
    http.add("/v1/teams", load_fixture("balldontlie", "teams"))
    http.add("/v1/players", load_fixture("balldontlie", "players"))
    assert balldontlie.get_teams()[0] == {"id": 14, "abbreviation": "LAL", "name": "Los Angeles Lakers"}
    player = balldontlie.get_players(14)[0]
    assert player == {
        "id": 237,
        "name": "LeBron James",
        "position": "F",
        "team": {"id": 14, "abbreviation": "LAL"},
    }


def test_balldontlie_follows_cursor(http, monkeypatch):
    pages = [
        {"data": [{"id": 1}], "meta": {"next_cursor": 7}},
        {"data": [{"id": 2}], "meta": {}},
    ]
    seen = []

    def fake_get(url, params=None, **kwargs):
        seen.append(dict(params))
        from .conftest import FakeResponse

        return FakeResponse(200, pages[len(seen) - 1])

    monkeypatch.setattr(requests, "get", fake_get)
    assert [g["external_id"] for g in balldontlie.get_games("2026-10-29")] == [1, 2]
    assert "cursor" not in seen[0] and seen[1]["cursor"] == 7


def test_balldontlie_invalid_request_raises(http):
    http.add("/v1/standings", load_fixture("balldontlie", "error_unauthorized"), status=401)
    with pytest.raises(BalldontlieError) as exc:
        balldontlie.get_standings(2026)  # GOAT-only endpoint on a lower tier
    assert exc.value.args[0] == 401


def test_balldontlie_missing_key_raises(monkeypatch):
    monkeypatch.delenv("BALLDONTLIE_API_KEY", raising=False)
    with pytest.raises(BalldontlieError):
        balldontlie.get_teams()


def test_balldontlie_network_error_raises(monkeypatch):
    monkeypatch.setenv("BALLDONTLIE_API_KEY", "k")

    def boom(*args, **kwargs):
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(BalldontlieError):
        balldontlie.get_teams()


def test_balldontlie_status_state_final_wins(http):
    game = {"id": 1, "status": "4th Qtr", "status_state": "final", "period": 4}
    http.add("/v1/games", {"data": [game], "meta": {}})
    assert balldontlie.get_games("2026-10-29")[0]["status"] == "final"


def _sequence(monkeypatch, responses):
    """Patch requests.get to return `responses` in order."""
    from .conftest import FakeResponse

    queue = [FakeResponse(status, payload) for status, payload in responses]
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: queue.pop(0))
    return queue


def test_balldontlie_retries_once_after_429(http, monkeypatch):
    waits = []
    monkeypatch.setattr(balldontlie.time, "sleep", waits.append)
    _sequence(monkeypatch, [(429, {}), (200, {"data": [], "meta": {}})])
    assert balldontlie.get_teams() == []
    assert waits == [balldontlie.RATE_LIMIT_WAIT]


def test_balldontlie_persistent_429_raises_rate_limit_error(http, monkeypatch):
    monkeypatch.setattr(balldontlie.time, "sleep", lambda seconds: None)
    _sequence(monkeypatch, [(429, {}), (429, {})])
    with pytest.raises(balldontlie.BalldontlieRateLimitError) as exc:
        balldontlie.get_teams()
    assert exc.value.args[0] == 429
    assert isinstance(exc.value, BalldontlieError)


def test_balldontlie_unexpected_shape_raises(http):
    http.add("/v1/teams", ["not", "a", "dict"])
    with pytest.raises(BalldontlieError):
        balldontlie.get_teams()


# ---------------------------------------------------------------- sportsdata


def test_sportsdata_nfl_scores_normalize(http):
    http.add("/v3/nfl/scores/json/ScoresByDate/2026-NOV-01", load_fixture("sportsdata", "nfl_scores"))
    games = sportsdata.get_scores("NFL", "2026-11-01")

    assert len(games) == 3
    kc = games[0]
    assert kc["home_team"] == {"id": None, "abbreviation": "KC"}
    assert kc["status"] == "scheduled"
    assert kc["scheduled_at"] == "2026-11-01T18:00:00+00:00"
    assert (kc["season"], kc["week"], kc["season_code"]) == (2026, 8, "2026REG")
    assert games[2]["status"] == "final" and games[2]["home_score"] == 20
    call = http.calls[0]
    assert call["headers"] == {"Ocp-Apim-Subscription-Key": "test-key"}
    assert "key=" not in call["url"]


def test_sportsdata_injuries_drop_probable(http):
    http.add("/v3/nfl/stats/json/Injuries/2026REG/8", load_fixture("sportsdata", "nfl_injuries"))
    injuries = sportsdata.get_injuries("NFL", "2026REG", 8)
    assert [(i["name"], i["status"]) for i in injuries] == [
        ("Patrick Mahomes", "questionable"),
        ("Aidan Hutchinson", "out"),
    ]
    assert injuries[0]["description"] == "Ankle - Limited"


def test_sportsdata_scrambled_injuries_kept_as_estimated_questionable(http):
    http.add("/v3/nba/projections/json/InjuredPlayers", load_fixture("sportsdata", "nba_injuries_trial"))
    injuries = sportsdata.get_injuries("NBA")
    assert [(i["name"], i["status"], i["status_estimated"], i["description"]) for i in injuries] == [
        ("Derrick White", "questionable", True, ""),
        # A real status is used as-is; only the scrambled notes are dropped.
        ("Nikola Jokic", "out", False, "Knee"),
    ]


def test_sportsdata_nba_uses_season_offset_and_stats(http):
    http.add("/v3/nba/scores/json/Standings/2027", load_fixture("sportsdata", "nba_standings"))
    http.add("/v3/nba/stats/json/PlayerSeasonStats/2027", load_fixture("sportsdata", "nba_player_season_stats"))
    standings = sportsdata.get_standings("NBA", 2026)
    assert standings[0]["team"]["abbreviation"] == "DEN" and standings[0]["season"] == 2026
    jokic = sportsdata.get_player_season_stats("NBA", 2026)[0]
    assert jokic["metric"] == 50.0 and jokic["games"] == 10  # (270+130+100)/10


def test_sportsdata_nfl_stats_use_fantasy_points(http):
    http.add("/v3/nfl/stats/json/PlayerSeasonStats/2026", load_fixture("sportsdata", "nfl_player_season_stats"))
    assert sportsdata.get_player_season_stats("NFL", 2026)[0]["metric"] == 160.4


def test_sportsdata_invalid_request_raises(http):
    http.add("/v3/nfl/", load_fixture("sportsdata", "error_unauthorized"), status=401)
    with pytest.raises(SportsDataError) as exc:
        sportsdata.get_scores("NFL", "2026-11-01")
    assert exc.value.args[0] == 401


def test_sportsdata_rejects_unknown_league_and_missing_key(monkeypatch):
    with pytest.raises(SportsDataError):
        sportsdata.get_scores("NHL", "2026-11-01")
    monkeypatch.delenv("SPORTSDATA_NFL_API_KEY", raising=False)
    with pytest.raises(SportsDataError):
        sportsdata.get_players("NFL")


def test_sportsdata_format_date():
    assert sportsdata.format_date("2026-11-01") == "2026-NOV-01"


# ---------------------------------------------------------------- weatherapi


def test_weatherapi_picks_hour_closest_to_kickoff(http):
    http.add("/v1/forecast.json", load_fixture("weatherapi", "forecast"))
    result = weatherapi.get_forecast(39.0489, -94.4839, "2026-11-01T18:00:00+00:00")
    assert result == {
        "temp_c": 6.5,
        "precip_mm": 1.2,
        "snow_cm": 0.0,
        "wind_kph": 22.5,
        "condition_text": "Light rain",
    }
    call = http.calls[0]
    assert call["params"]["key"] == "test-key"
    assert call["params"]["q"] == "39.0489,-94.4839"
    assert call["timeout"] == weatherapi.TIMEOUT


def test_weatherapi_kickoff_outside_window_raises(http):
    http.add("/v1/forecast.json", load_fixture("weatherapi", "forecast"))
    with pytest.raises(WeatherAPIError):
        weatherapi.get_forecast(39.0, -94.0, "2026-12-25T18:00:00+00:00")


def test_weatherapi_invalid_request_raises(http):
    http.add("/v1/forecast.json", load_fixture("weatherapi", "error_no_location"), status=400)
    with pytest.raises(WeatherAPIError) as exc:
        weatherapi.get_forecast(0, 0, "2026-11-01T18:00:00+00:00")
    assert exc.value.args[0] == 400


def test_sportsdata_estimated_injury_drops_any_text(http):
    row = {
        "PlayerID": 1,
        "Team": "BOS",
        "FirstName": "Derrick",
        "LastName": "White",
        "InjuryStatus": "Scrambled",
        "InjuryBodyPart": "Xqzv",  # garbage, not the literal word
        "InjuryNotes": "Lorem ipsum",
    }
    http.add("/v3/nba/projections/json/InjuredPlayers", [row])
    assert sportsdata.get_injuries("NBA")[0]["description"] == ""


@pytest.mark.parametrize("payload", [{"Message": "error with 200"}, [1, 2]])
def test_sportsdata_unexpected_shape_raises(http, payload):
    http.add("/v3/nba/scores/json/teams", payload)
    with pytest.raises(SportsDataError):
        sportsdata.get_teams("NBA")


def test_weatherapi_returns_snow_cm(http):
    forecast = load_fixture("weatherapi", "forecast")
    for day in forecast["forecast"]["forecastday"]:
        for hour in day["hour"]:
            hour["snow_cm"] = 2.5
    http.add("/v1/forecast.json", forecast)
    assert weatherapi.get_forecast(39.0489, -94.4839, "2026-11-01T18:00:00+00:00")["snow_cm"] == 2.5


@pytest.mark.parametrize(
    "payload",
    [
        ["not", "a", "dict"],
        {"forecast": {"forecastday": [{"hour": [{"temp_c": 5}]}]}},  # hour without time_epoch
    ],
)
def test_weatherapi_malformed_response_raises(http, payload):
    http.add("/v1/forecast.json", payload)
    with pytest.raises(WeatherAPIError):
        weatherapi.get_forecast(0, 0, "2026-11-01T18:00:00+00:00")
