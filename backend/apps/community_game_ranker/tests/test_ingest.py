from datetime import date, datetime, timedelta, timezone

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.community_game_ranker.models import (
    ExternalAPIMetadata,
    GameLog,
    Injury,
    Player,
    Team,
    TeamStanding,
    WeatherCondition,
)
from apps.community_game_ranker.services import ingest

from .conftest import load_fixture

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
NFL_DAY = date(2026, 11, 1)
NBA_DAY = date(2026, 10, 29)


def team(sport, abbreviation):
    return Team.objects.get(sport__code=sport, abbreviation=abbreviation)


def nfl_routes(http, weather=True):
    http.add("/nfl/scores/json/ScoresByDate/", load_fixture("sportsdata", "nfl_scores"))
    http.add("/nfl/scores/json/Standings/2026", load_fixture("sportsdata", "nfl_standings"))
    http.add("/nfl/stats/json/Injuries/2026REG/8", load_fixture("sportsdata", "nfl_injuries"))
    if weather:
        http.add("weatherapi.com", load_fixture("weatherapi", "forecast"))


def nba_routes(http):
    http.add("/v1/games", load_fixture("balldontlie", "games"))
    http.add("/nba/scores/json/Standings/2027", load_fixture("sportsdata", "nba_standings"))
    http.add("/nba/projections/json/InjuredPlayers", load_fixture("sportsdata", "nba_injuries"))


@pytest.fixture
def nfl_players():
    Player.objects.create(
        team=team("NFL", "KC"), name="Patrick Mahomes", external_ids={"sportsdata_nfl": 9001}
    )
    Player.objects.create(
        team=team("NFL", "DET"), name="Aidan Hutchinson", external_ids={"sportsdata_nfl": 9003}
    )


# ---------------------------------------------------------------- cached_call


def test_cached_call_hits_cache_and_skips_the_function():
    calls = []

    def fn():
        calls.append(1)
        return {"value": len(calls)}

    args = ("balldontlie", "games", {"date": "2026-10-29"}, fn, timedelta(minutes=5))
    assert ingest.cached_call(*args) == {"value": 1}
    assert ingest.cached_call(*args) == {"value": 1}
    assert len(calls) == 1
    row = ExternalAPIMetadata.objects.get()
    assert row.status_code == 200 and row.response == {"value": 1}


def test_cached_call_refetches_when_stale_and_keys_on_params():
    calls = []

    def fn():
        calls.append(1)
        return {"n": len(calls)}

    ingest.cached_call("sportsdata", "x", {"a": 1}, fn, timedelta(0))
    ingest.cached_call("sportsdata", "x", {"a": 1}, fn, timedelta(0))
    ingest.cached_call("sportsdata", "x", {"a": 2}, fn, timedelta(hours=1))
    assert len(calls) == 3
    assert ExternalAPIMetadata.objects.count() == 2  # one row per distinct params


def test_cached_call_does_not_cache_failures():
    def boom():
        raise ingest.SportsDataError(500, "down")

    with pytest.raises(ingest.SportsDataError):
        ingest.cached_call("sportsdata", "x", {}, boom, timedelta(hours=1))
    assert not ExternalAPIMetadata.objects.exists()


# ---------------------------------------------------------------- ingest_day (NFL)


def test_ingest_nfl_day_upserts_games_with_aliases_and_stadiums(http, nfl_players):
    nfl_routes(http)
    result = ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)["NFL"]

    assert result["created"] == 3 and result["errors"] == []
    kc = GameLog.objects.get(home_team__abbreviation="KC")
    assert kc.away_team.abbreviation == "BUF"
    assert kc.stadium == team("NFL", "KC").stadiums.first()
    assert (kc.season, kc.week, kc.status) == (2026, 8, "scheduled")
    # Provider abbreviations LA, JAC, WSH map to LAR, JAX, WAS.
    assert GameLog.objects.filter(home_team__abbreviation="DET", away_team__abbreviation="LAR").exists()
    final = GameLog.objects.get(home_team__abbreviation="JAX")
    assert (final.away_team.abbreviation, final.status) == ("WAS", "final")
    assert (final.home_score, final.away_score) == (20, 17)


def test_ingest_nfl_day_standings_and_injuries(http, nfl_players):
    nfl_routes(http)
    ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)

    assert TeamStanding.objects.filter(season=2026).count() == 6
    kc = TeamStanding.objects.get(team__abbreviation="KC", team__sport__code="NFL")
    assert (kc.wins, kc.losses, kc.conference_rank) == (6, 1, 1)
    assert TeamStanding.objects.filter(team__abbreviation="LAR").exists()
    injuries = {i.player.name: i.status for i in Injury.objects.select_related("player")}
    # Probable is dropped; Josh Allen is not rostered so he is skipped.
    assert injuries == {"Patrick Mahomes": "questionable", "Aidan Hutchinson": "out"}


def test_weather_only_for_outdoor_open_games(http, nfl_players):
    nfl_routes(http)
    result = ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)["NFL"]

    assert result["weather"] == 1
    weather = WeatherCondition.objects.get()
    assert weather.game.home_team.abbreviation == "KC"  # DET is indoor, JAX game is final
    assert (weather.temp_c, weather.precip_mm, weather.wind_kph) == (6.5, 1.2, 22.5)
    assert len(http.urls("weatherapi.com")) == 1


def test_weather_error_is_recorded_without_stopping_ingest(http, nfl_players):
    nfl_routes(http, weather=False)
    http.add("weatherapi.com", load_fixture("weatherapi", "error_no_location"), status=400)
    result = ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)["NFL"]

    assert result["created"] == 3 and result["weather"] == 0
    assert len(result["errors"]) == 1 and "weather" in result["errors"][0]
    assert not WeatherCondition.objects.exists()


def test_game_upsert_is_idempotent_and_second_run_hits_cache(http, nfl_players):
    nfl_routes(http)
    ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)
    calls_after_first = len(http.calls)
    second = ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)["NFL"]

    assert len(http.calls) == calls_after_first  # everything served from ExternalAPIMetadata
    assert (second["created"], second["updated"]) == (0, 3)
    assert GameLog.objects.count() == 3
    assert Injury.objects.count() == 2
    assert TeamStanding.objects.count() == 6
    assert WeatherCondition.objects.count() == 1


def test_game_update_changes_status_and_score_in_place(http, nfl_players):
    nfl_routes(http)
    ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)
    scores = load_fixture("sportsdata", "nfl_scores")
    scores[0].update(Status="Final", HomeScore=31, AwayScore=27)
    ExternalAPIMetadata.objects.all().delete()
    http.routes.insert(0, ("/nfl/scores/json/ScoresByDate/", scores, 200))
    ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)

    assert GameLog.objects.count() == 3
    kc = GameLog.objects.get(home_team__abbreviation="KC")
    assert (kc.status, kc.home_score, kc.away_score) == ("final", 31, 27)


def test_recovered_players_lose_their_injury_row(http, nfl_players):
    nfl_routes(http)
    ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)
    ExternalAPIMetadata.objects.all().delete()
    http.routes.insert(0, ("/nfl/stats/json/Injuries/", [], 200))
    ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)
    assert not Injury.objects.exists()


def test_provider_failure_is_reported_not_raised(http):
    http.add("/nfl/", load_fixture("sportsdata", "error_unauthorized"), status=401)
    result = ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)["NFL"]
    assert result["created"] == 0 and "games" in result["errors"][0]
    assert not GameLog.objects.exists()


def test_unknown_teams_are_skipped(http):
    scores = load_fixture("sportsdata", "nfl_scores")
    scores[0]["HomeTeam"] = "ZZZ"
    http.add("/nfl/scores/json/ScoresByDate/", scores)
    http.add("/nfl/scores/json/Standings/2026", [])
    http.add("/nfl/stats/json/Injuries/", [])
    http.add("weatherapi.com", load_fixture("weatherapi", "forecast"))
    result = ingest.ingest_day(NFL_DAY, sports=("NFL",), now=NOW)["NFL"]
    assert (result["created"], result["skipped"]) == (2, 1)


def test_rejects_unsupported_sport():
    with pytest.raises(ValueError):
        ingest.ingest_day(NFL_DAY, sports=("NHL",))


# ---------------------------------------------------------------- ingest_day (NBA)


def test_ingest_nba_day(http):
    nba_routes(http)
    Player.objects.create(
        team=team("NBA", "DEN"), name="Nikola Jokic", external_ids={"sportsdata_nba": 20000571}
    )
    result = ingest.ingest_day(NBA_DAY, sports=("NBA",), now=NOW)["NBA"]

    assert result["created"] == 3 and result["errors"] == []
    # balldontlie "GS" maps to our GSW.
    assert GameLog.objects.filter(home_team__abbreviation="LAL", away_team__abbreviation="GSW").exists()
    assert set(GameLog.objects.values_list("status", flat=True)) == {"final", "scheduled", "in_progress"}
    den_games = GameLog.objects.filter(home_team__abbreviation="DEN")
    assert den_games.get().stadium.is_indoor is True
    assert not WeatherCondition.objects.exists()  # NBA arenas are indoor
    assert not http.urls("weatherapi.com")
    # SportsData labels the 2026-27 season 2027 (assumed); our row stores the start year.
    assert TeamStanding.objects.filter(season=2026, team__abbreviation="PHX").exists()
    assert TeamStanding.objects.filter(season=2026, team__abbreviation="GSW").exists()
    # Jokic is out for both open games he plays in (DEN home, and GSW vs DEN).
    assert Injury.objects.filter(player__name="Nikola Jokic", status="out").count() == 2


# ---------------------------------------------------------------- backfill


def test_backfill_loads_only_finished_nfl_games(http):
    http.add("/nfl/scores/json/ScoresByDateFinal/", load_fixture("sportsdata", "nfl_scores"))
    result = ingest.backfill_finished(NFL_DAY, sports=("NFL",), now=NOW)["NFL"]

    assert len(http.calls) == ingest.BACKFILL_DAYS
    assert GameLog.objects.count() == 1
    assert GameLog.objects.get().status == "final"
    assert result["created"] == 1


def test_backfill_nba_uses_one_ranged_call(http):
    http.add("/v1/games", load_fixture("balldontlie", "games"))
    ingest.backfill_finished(NBA_DAY, sports=("NBA",), now=NOW)

    assert len(http.calls) == 1
    assert http.calls[0]["params"]["start_date"] == "2026-10-15"
    assert http.calls[0]["params"]["end_date"] == "2026-10-28"
    assert list(GameLog.objects.values_list("status", flat=True)) == ["final"]


# ---------------------------------------------------------------- rosters


def nfl_roster_routes(http):
    http.add("/nfl/scores/json/PlayersByAvailable", load_fixture("sportsdata", "nfl_players"))
    http.add("/nfl/scores/json/Teams", load_fixture("sportsdata", "nfl_teams"))


def test_sync_rosters_upserts_players_and_links_team_ids(http):
    nfl_roster_routes(http)
    # A star placeholder from seed_stars (no ids yet) must be adopted, not duplicated.
    seeded = Player.objects.create(team=team("NFL", "KC"), name="Patrick Mahomes", is_star=True)
    summary = ingest.sync_rosters("NFL")

    assert summary["created"] == 3  # Allen, Hutchinson, Nacua; the free agent has no team
    assert Player.objects.filter(team__sport__code="NFL").count() == 4
    seeded.refresh_from_db()
    assert seeded.is_star and seeded.external_ids == {"sportsdata_nfl": 9001} and seeded.position == "QB"
    assert Player.objects.get(name="Puka Nacua").team.abbreviation == "LAR"  # LA -> LAR
    assert not Player.objects.filter(name="Free Agent").exists()
    # Team ids are matched through the alias map (JAX, LA -> LAR).
    assert summary["teams_linked"] == 3
    assert team("NFL", "KC").external_ids == {"sportsdata": 17}
    assert team("NFL", "JAX").external_ids == {"sportsdata": 26}
    assert team("NFL", "LAR").external_ids == {"sportsdata": 32}


def test_sync_rosters_is_idempotent(http):
    nfl_roster_routes(http)
    ingest.sync_rosters("NFL")
    again = ingest.sync_rosters("NFL")
    assert (again["created"], again["updated"], again["moved"]) == (0, 0, 0)
    assert Player.objects.count() == 4


def test_traded_player_changes_team_and_keeps_star_flag(http):
    nfl_roster_routes(http)
    allen = Player.objects.create(
        team=team("NFL", "KC"), name="Josh Allen", is_star=True, external_ids={"sportsdata_nfl": 9002}
    )
    summary = ingest.sync_rosters("NFL")

    allen.refresh_from_db()
    assert allen.team.abbreviation == "BUF"  # feed says BUF
    assert allen.is_star is True
    assert summary["moved"] == 1
    assert Player.objects.filter(name="Josh Allen").count() == 1


def test_player_listed_without_a_team_is_released(http):
    nfl_roster_routes(http)
    cut = Player.objects.create(
        team=team("NFL", "BUF"), name="Free Agent", external_ids={"sportsdata_nfl": 9005}
    )
    summary = ingest.sync_rosters("NFL")
    cut.refresh_from_db()
    assert cut.team is None and summary["released"] == 1


def test_sync_rosters_nba_links_both_providers(http):
    http.add("/nba/scores/json/PlayersActiveBasic", load_fixture("sportsdata", "nba_players"))
    http.add("/nba/scores/json/teams", load_fixture("sportsdata", "nba_teams"))
    http.add("/v1/teams", load_fixture("balldontlie", "teams"))
    ingest.sync_rosters("NBA")

    assert team("NBA", "DEN").external_ids == {"sportsdata": 4, "balldontlie": 8}
    assert team("NBA", "PHX").external_ids == {"sportsdata": 5, "balldontlie": 24}  # PHO alias
    assert team("NBA", "GSW").external_ids == {"balldontlie": 10}  # GS alias
    assert Player.objects.get(name="Role Player").team.abbreviation == "PHX"


def test_refresh_stars_picks_from_stats_then_applies_overrides(http):
    http.add("/nba/stats/json/PlayerSeasonStats/2027", load_fixture("sportsdata", "nba_player_season_stats"))
    # Rostered by sync_rosters under the roster feed's spelling, which differs from the stats feed's.
    for pid, name in [(1, "Nikola Jokić"), (2, "Bench Guy")]:
        Player.objects.create(team=team("NBA", "DEN"), name=name, external_ids={"sportsdata_nba": pid})
    overrides = {"NBA": {"always": [{"name": "Luka Dončić", "team": "LAL"}], "never": []}}
    ingest.refresh_stars("NBA", NBA_DAY, overrides)

    starred = set(Player.objects.filter(is_star=True).values_list("name", flat=True))
    assert starred == {"Nikola Jokić", "Luka Dončić"}  # Bench Guy has too few games
    # Matched by provider id, so no duplicate row under the stats feed's spelling.
    assert not Player.objects.filter(name="Nikola Jokic").exists()


def test_refresh_stars_lowers_minimum_games_early_in_season(http):
    early = [
        {"PlayerID": 1, "Name": "N.Jokic", "Team": "DEN", "Games": 4, "Points": 120, "Rebounds": 50, "Assists": 40},
        {"PlayerID": 2, "Name": "B.Guy", "Team": "DEN", "Games": 1, "Points": 30, "Rebounds": 5, "Assists": 5},
    ]
    http.add("/nba/stats/json/PlayerSeasonStats/2027", early)
    for pid, name in [(1, "Nikola Jokić"), (2, "Bench Guy")]:
        Player.objects.create(team=team("NBA", "DEN"), name=name, external_ids={"sportsdata_nba": pid})
    ingest.refresh_stars("NBA", NBA_DAY)
    # 4 games played so far -> minimum is 2, so Jokic qualifies and the 1-game player doesn't.
    assert set(Player.objects.filter(is_star=True).values_list("name", flat=True)) == {"Nikola Jokić"}


def test_refresh_stars_never_picks_nfl_kickers(http):
    stats = [
        {"PlayerID": 1, "Name": "P.Mahomes", "Team": "KC", "Position": "QB", "Played": 7, "FantasyPoints": 140},
        {"PlayerID": 2, "Name": "H.Butker", "Team": "KC", "Position": "K", "Played": 7, "FantasyPoints": 150},
    ]
    http.add("/nfl/stats/json/PlayerSeasonStats/2026", stats)
    for pid, name in [(1, "Patrick Mahomes"), (2, "Harrison Butker")]:
        Player.objects.create(team=team("NFL", "KC"), name=name, external_ids={"sportsdata_nfl": pid})
    ingest.refresh_stars("NFL", date(2026, 11, 1))
    assert set(Player.objects.filter(is_star=True).values_list("name", flat=True)) == {"Patrick Mahomes"}


def test_refresh_stars_skips_stat_rows_without_a_rostered_player(http):
    http.add("/nba/stats/json/PlayerSeasonStats/2027", load_fixture("sportsdata", "nba_player_season_stats"))
    ingest.refresh_stars("NBA", NBA_DAY)
    assert not Player.objects.exists()


# ---------------------------------------------------------------- commands


def test_ingest_ranker_command(http, capsys):
    nba_routes(http)
    call_command("ingest_ranker", date="2026-10-29", sport="NBA")
    assert GameLog.objects.count() == 3
    assert "ingest NBA: 3 new" in capsys.readouterr().out


def test_ingest_ranker_rejects_bad_date():
    with pytest.raises(CommandError):
        call_command("ingest_ranker", date="10/29/2026")


def test_sync_rosters_command(http):
    nfl_roster_routes(http)
    call_command("sync_rosters", sport="NFL", skip_stars=True)
    assert Player.objects.count() == 4


def test_live_ttl_uses_eastern_day_not_utc():
    # 02:00 UTC on Oct 29 is 22:00 ET on Oct 28, so Oct 27 is still "yesterday" and live.
    now = datetime(2026, 10, 29, 2, 0, tzinfo=timezone.utc)
    assert ingest._ttl_for_day(date(2026, 10, 27), now) == ingest.LIVE_TTL
    assert ingest._ttl_for_day(date(2026, 10, 26), now) == ingest.FINAL_TTL
