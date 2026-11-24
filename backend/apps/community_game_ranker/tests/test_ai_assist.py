"""Hourly AI ranking (services/ai_assist.py). Claude itself is always mocked."""

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import anthropic
import pytest
from django.core.management import call_command

from apps.community_game_ranker.integrations import claude
from apps.community_game_ranker.integrations.claude import ClaudeError
from apps.community_game_ranker.models import (
    AIRanking,
    ExternalAPIMetadata,
    GameLog,
    Injury,
    Player,
    Sport,
    Team,
)
from apps.community_game_ranker.services import ai_assist

pytestmark = pytest.mark.django_db

DAY = date(2026, 11, 1)
EVENING = datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc)  # 7 pm Eastern
NOW = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)


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


class FakeClaude:
    """Stands in for claude.rank_games: records what Claude was sent and ranks by a fixed order."""

    def __init__(self, order=None, error=None):
        self.order = order  # game ids, best first; default: input order
        self.error = error
        self.calls = []

    def __call__(self, games):
        self.calls.append(games)
        if self.error:
            raise self.error
        ids = self.order or [g["id"] for g in games]
        return [{"game_id": gid, "rank": i, "reason": f"reason {gid}"} for i, gid in enumerate(ids, 1)]


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    stub = FakeClaude()
    monkeypatch.setattr(claude, "rank_games", stub)
    return stub


@pytest.fixture
def day_games():
    return {
        "bos": make_game("NBA", "BOS", "LAL"),
        "okc": make_game("NBA", "OKC", "WAS"),
        "gb": make_game("NFL", "GB", "CHI"),
    }


def test_disabled_without_api_key(day_games):
    assert ai_assist.rank_day(DAY, now=NOW)["status"] == "disabled"
    assert not AIRanking.objects.exists()


def test_no_games(fake):
    assert ai_assist.rank_day(DAY, now=NOW)["status"] == "no_games"
    assert fake.calls == []


def test_ranks_stores_reasons_and_rescores(fake, day_games):
    fake.order = [day_games["okc"].pk, day_games["gb"].pk, day_games["bos"].pk]
    result = ai_assist.rank_day(DAY, now=NOW)
    assert result == {"status": "ranked", "games": 3, "error": None}

    okc = AIRanking.objects.get(game=day_games["okc"])
    assert (okc.rank, okc.ranked_count, okc.reason, okc.model) == (1, 3, f"reason {okc.game_id}", claude.MODEL)
    for g in day_games.values():
        g.refresh_from_db()
    assert day_games["okc"].score_breakdown["ai"] == 1.0
    assert day_games["gb"].score_breakdown["ai"] == 0.5
    assert day_games["bos"].score_breakdown["ai"] == 0.0


def test_ai_rank_moves_the_importance_score(fake, day_games):
    from apps.community_game_ranker.services import ranking

    ranking.score_day(DAY)
    before = GameLog.objects.get(pk=day_games["okc"].pk).importance_score
    fake.order = [day_games["okc"].pk, day_games["gb"].pk, day_games["bos"].pk]
    ai_assist.rank_day(DAY, now=NOW)
    assert GameLog.objects.get(pk=day_games["okc"].pk).importance_score > before


def test_summary_has_the_facts_but_never_the_previous_ai_rating(fake, day_games):
    bos = day_games["bos"]
    star = Player.objects.create(team=team("NBA", "LAL"), name="LeBron James", is_star=True)
    Injury.objects.create(player=star, game=bos, status="out", description="Ankle", reported_at=NOW)
    ai_assist.rank_day(DAY, now=NOW)

    sent = {g["id"]: g for g in fake.calls[0]}[bos.pk]
    assert sent["injuries"][0]["player"] == "LeBron James"
    assert sent["injuries"][0]["status"] == "out"
    assert sent["rivalry"]["intensity_1_to_5"] == 5
    assert set(sent["subscores"]) == {
        "playoff", "star_injury", "weather", "momentum", "rivalry", "status", "community"
    }
    json.dumps(sent)  # JSON-safe

    # Second run, after the first rating exists: Claude must get the exact same summary,
    # so its own earlier rank and reason can't leak into the next one.
    first = fake.calls[0]
    fake.calls.clear()
    Injury.objects.filter(game=bos).update(status="questionable")
    ai_assist.rank_day(DAY, now=NOW + timedelta(hours=1))
    second = {g["id"]: g for g in fake.calls[0]}
    assert "ai" not in second[bos.pk]["subscores"]
    blob = json.dumps(fake.calls[0])
    assert "reason " not in blob  # FakeClaude's reasons from the first run
    # Apart from the injury, nothing differs from the first run's summary.
    second[bos.pk]["injuries"][0]["status"] = "out"
    second[bos.pk]["subscores"]["star_injury"] = {g["id"]: g for g in first}[bos.pk]["subscores"]["star_injury"]
    second[bos.pk]["formula_score"] = {g["id"]: g for g in first}[bos.pk]["formula_score"]
    assert list(second.values()) == first


def test_summary_lists_non_star_injuries_and_spells_out_recent_form(fake, day_games):
    # Regression: Claude called a team "fully healthy" and "winners of four straight" when a
    # non-star was questionable and the team had lost its latest game (sent as "LWWWW").
    bos = day_games["bos"]
    bench = Player.objects.create(team=team("NBA", "BOS"), name="Bench Guy", is_star=False)
    Injury.objects.create(player=bench, game=bos, status="questionable", reported_at=NOW)
    for days_ago, (home, away, hs, as_) in enumerate(
        [("BOS", "OKC", 93, 105), ("WAS", "BOS", 102, 110), ("BOS", "WAS", 123, 85)], start=1
    ):
        make_game("NBA", home, away, when=EVENING - timedelta(days=days_ago),
                  status=GameLog.Status.FINAL, home_score=hs, away_score=as_)
    ai_assist.rank_day(DAY, now=NOW)

    sent = {g["id"]: g for g in fake.calls[0]}[bos.pk]
    assert sent["injuries"] == [{
        "player": "Bench Guy", "team": "BOS", "is_star": False, "status": "questionable",
        "status_is_estimate": False, "note": "",
    }]
    home = sent["home"]
    assert home["streak"] == "L1"
    assert [g["result"] for g in home["recent_games_newest_first"]] == ["L", "W", "W"]
    assert home["recent_games_newest_first"][0] == {
        "date": "2026-10-31", "opponent": "OKC", "at_home": True, "result": "L", "score": "93-105",
    }


def test_streak():
    games = lambda s: [{"result": r} for r in s]  # noqa: E731
    assert ai_assist._streak([]) is None
    assert ai_assist._streak(games("LWWWW")) == "L1"
    assert ai_assist._streak(games("WWWWL")) == "W4"
    assert ai_assist._streak(games("TT")) == "T2"


def test_waits_an_hour_between_runs(fake, day_games):
    ai_assist.rank_day(DAY, now=NOW)
    Injury.objects.create(
        player=Player.objects.create(team=team("NBA", "BOS"), name="Star", is_star=True),
        game=day_games["bos"], status="out", reported_at=NOW,
    )
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(minutes=30))["status"] == "fresh"
    assert len(fake.calls) == 1
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(hours=1))["status"] == "ranked"
    assert len(fake.calls) == 2


def test_skips_claude_when_nothing_changed(fake, day_games):
    ai_assist.rank_day(DAY, now=NOW)
    first = list(AIRanking.objects.values_list("game_id", "rank", "rated_at"))
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(hours=1))["status"] == "unchanged"
    assert len(fake.calls) == 1
    assert list(AIRanking.objects.values_list("game_id", "rank", "rated_at")) == first
    # The check counts as this hour's run.
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(hours=1, minutes=30))["status"] == "fresh"


def test_reranks_when_a_factor_changes(fake, day_games):
    ai_assist.rank_day(DAY, now=NOW)
    assert AIRanking.objects.get(game=day_games["bos"]).rank == 1
    star = Player.objects.create(team=team("NBA", "LAL"), name="LeBron James", is_star=True)
    Injury.objects.create(player=star, game=day_games["bos"], status="out", reported_at=NOW)
    fake.order = [day_games["gb"].pk, day_games["okc"].pk, day_games["bos"].pk]

    assert ai_assist.rank_day(DAY, now=NOW + timedelta(hours=1))["status"] == "ranked"
    assert AIRanking.objects.get(game=day_games["bos"]).rank == 3
    assert AIRanking.objects.count() == 3


def test_failure_keeps_last_rankings_and_retries_next_hour(fake, day_games):
    ai_assist.rank_day(DAY, now=NOW)
    GameLog.objects.filter(pk=day_games["gb"].pk).update(status="in_progress")
    fake.error = ClaudeError("boom")

    result = ai_assist.rank_day(DAY, now=NOW + timedelta(hours=1))
    assert result["status"] == "error" and result["error"] == "boom"
    assert AIRanking.objects.count() == 3  # last good rankings stay
    row = ExternalAPIMetadata.objects.get(provider="anthropic")
    assert row.status_code == ai_assist.FAILED_STATUS
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(hours=1, minutes=5))["status"] == "fresh"

    fake.error = None
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(hours=2))["status"] == "ranked"


def test_force_skips_the_wait_but_not_the_unchanged_check(fake, day_games):
    ai_assist.rank_day(DAY, now=NOW)
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(minutes=5), force=True)["status"] == "unchanged"
    GameLog.objects.filter(pk=day_games["gb"].pk).update(status="in_progress")
    assert ai_assist.rank_day(DAY, now=NOW + timedelta(minutes=10), force=True)["status"] == "ranked"


def test_unranked_game_is_scored_without_the_ai_weight(fake, day_games):
    from apps.community_game_ranker.services import ranking

    ai_assist.rank_day(DAY, now=NOW)
    late = make_game("NBA", "DEN", "PHX")  # added after the AI run
    ranking.score_day(DAY)
    late.refresh_from_db()
    assert late.score_breakdown["ai"] is None and late.importance_score is not None


def test_rank_ai_command(fake, day_games, monkeypatch, capsys):
    monkeypatch.setattr("apps.community_game_ranker.services.ai_assist.timezone.now", lambda: NOW)
    call_command("rank_ai", date=DAY.isoformat())
    assert "ai 2026-11-01: ranked (3 games)" in capsys.readouterr().out
    assert AIRanking.objects.count() == 3


def test_refresh_ranker_runs_ai_after_ingest(fake, day_games, monkeypatch, capsys):
    monkeypatch.setattr(
        "apps.community_game_ranker.services.ingest.refresh_live", lambda: {}
    )
    monkeypatch.setattr("django.utils.timezone.now", lambda: NOW)
    call_command("refresh_ranker", once=True)
    assert "ai 2026-11-01: ranked (3 games)" in capsys.readouterr().out
    call_command("refresh_ranker", once=True, no_ai=True)
    assert len(fake.calls) == 1


# The Claude client (integrations/claude.py), with the SDK client faked.


def fake_response(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


@pytest.fixture
def sdk(monkeypatch):
    """Patch anthropic.Anthropic; set `sdk.response` or `sdk.error` before calling."""
    state = SimpleNamespace(response=None, error=None, requests=[])

    def create(**kwargs):
        state.requests.append(kwargs)
        if state.error:
            raise state.error
        return state.response

    monkeypatch.setattr(
        anthropic,
        "Anthropic",
        lambda **kw: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))),
    )
    return state


GAMES = [{"id": 7, "sport": "NBA"}, {"id": 9, "sport": "NFL"}]


def test_client_success_sorts_and_renumbers(sdk):
    sdk.response = fake_response(
        {"rankings": [
            {"game_id": 7, "rank": 4, "reason": " Close race. "},
            {"game_id": 9, "rank": 2, "reason": "Snow at Lambeau."},
        ]}
    )
    assert claude.rank_games(GAMES) == [
        {"game_id": 9, "rank": 1, "reason": "Snow at Lambeau."},
        {"game_id": 7, "rank": 2, "reason": "Close race."},
    ]
    request = sdk.requests[0]
    assert request["model"] == claude.MODEL
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert request["fallbacks"] == "default"
    assert '"id": 7' in request["messages"][0]["content"]


def test_client_empty_day_makes_no_call(sdk):
    assert claude.rank_games([]) == [] and sdk.requests == []


@pytest.mark.parametrize(
    "response",
    [
        fake_response({"rankings": [{"game_id": 7, "rank": 1, "reason": "x"}]}),  # missing a game
        fake_response({"rankings": [
            {"game_id": 7, "rank": 1, "reason": "x"}, {"game_id": 8, "rank": 2, "reason": "y"},
        ]}),  # unknown game
        fake_response({"rankings": [
            {"game_id": 7, "rank": 1, "reason": "x"}, {"game_id": 9, "rank": 2, "reason": " "},
        ]}),  # blank reason
        fake_response("not json"),
        fake_response({}, stop_reason="refusal"),
        fake_response({}, stop_reason="max_tokens"),
    ],
)
def test_client_bad_answers_raise(sdk, response):
    sdk.response = response
    with pytest.raises(ClaudeError):
        claude.rank_games(GAMES)


def test_client_invalid_request_raises(sdk):
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    sdk.error = anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx2.Response(401, request=request), body=None
    )
    with pytest.raises(ClaudeError, match="401"):
        claude.rank_games(GAMES)
