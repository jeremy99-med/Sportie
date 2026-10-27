import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.community_game_ranker.models import Player, Team
from apps.community_game_ranker.services.stars import StarListError, pick_stars, sync_stars

pytestmark = pytest.mark.django_db


@pytest.fixture
def lakers():
    return Team.objects.get(sport__code="NBA", abbreviation="LAL")


def test_sync_stars_creates_and_marks_players(lakers):
    assert sync_stars({"NBA": {"LAL": ["Luka Doncic", "Austin Reaves"]}}) == (2, 0)
    assert set(lakers.players.filter(is_star=True).values_list("name", flat=True)) == {
        "Luka Doncic",
        "Austin Reaves",
    }


def test_sync_stars_is_idempotent(lakers):
    stars = {"NBA": {"LAL": ["Luka Doncic"]}}
    sync_stars(stars)
    sync_stars(stars)
    assert lakers.players.count() == 1


def test_sync_stars_clears_players_dropped_from_list(lakers):
    sync_stars({"NBA": {"LAL": ["Luka Doncic", "Austin Reaves"]}})
    assert sync_stars({"NBA": {"LAL": ["Luka Doncic"]}}) == (1, 1)
    # The player row stays (injury history may point at it); only the flag changes.
    assert Player.objects.get(name="Austin Reaves").is_star is False


def test_sync_stars_rejects_more_than_five_per_team():
    with pytest.raises(StarListError):
        sync_stars({"NBA": {"LAL": [f"Player {i}" for i in range(6)]}})
    assert not Player.objects.exists()


def test_sync_stars_rejects_unknown_team():
    with pytest.raises(StarListError):
        sync_stars({"NBA": {"XXX": ["Nobody"]}})


def test_seed_stars_command_applies_bundled_overrides():
    call_command("seed_stars")
    stars = Player.objects.filter(is_star=True)
    assert stars.filter(team__sport__code="NBA", name="Nikola Jokić", team__abbreviation="DEN").exists()
    assert stars.filter(team__sport__code="NFL", name="Patrick Mahomes", team__abbreviation="KC").exists()


def test_seed_stars_command_reports_bad_file(tmp_path):
    bad = tmp_path / "stars.json"
    bad.write_text(json.dumps({"NBA": {"always": [{"name": "Nobody", "team": "XXX"}]}}))
    with pytest.raises(CommandError):
        call_command("seed_stars", file=bad)


def test_seed_stars_command_rejects_old_format(tmp_path):
    old = tmp_path / "stars.json"
    old.write_text(json.dumps({"NBA": {"LAL": ["Luka Doncic"]}}))
    with pytest.raises(CommandError):
        call_command("seed_stars", file=old)


def test_seed_stars_overrides_only_run_keeps_other_stars(lakers):
    sync_stars({"NBA": {"LAL": ["Luka Doncic", "Austin Reaves"]}})
    sync_stars(None, {"NBA": {"always": [{"name": "LeBron James", "team": "LAL"}]}})
    assert set(lakers.players.filter(is_star=True).values_list("name", flat=True)) == {
        "LeBron James",
        "Luka Doncic",
        "Austin Reaves",
    }


# ---------------------------------------------------------------- pick_stars


def stat(name, team, metric, games=10):
    return {"name": name, "team_abbreviation": team, "metric": metric, "games": games}


def test_pick_stars_ranks_by_metric_per_team():
    stats = [
        stat("B", "LAL", 30.0),
        stat("A", "LAL", 45.5),
        stat("C", "LAL", 12.0),
        stat("X", "DEN", 50.0),
    ]
    assert pick_stars(stats, per_team=2) == {"LAL": ["A", "B"], "DEN": ["X"]}


def test_pick_stars_caps_at_per_team_and_never_above_five():
    stats = [stat(f"P{i}", "LAL", float(i)) for i in range(10)]
    assert pick_stars(stats, per_team=3)["LAL"] == ["P9", "P8", "P7"]
    assert len(pick_stars(stats, per_team=8)["LAL"]) == 5


def test_pick_stars_applies_minimum_games():
    stats = [stat("Hot Start", "LAL", 99.0, games=2), stat("Steady", "LAL", 20.0, games=12)]
    assert pick_stars(stats, min_games=5) == {"LAL": ["Steady"]}
    assert pick_stars(stats, min_games=1)["LAL"] == ["Hot Start", "Steady"]


def test_pick_stars_ignores_teamless_rows_and_breaks_ties_by_name():
    stats = [stat("Zed", "LAL", 10.0), stat("Amy", "LAL", 10.0), stat("Ghost", "", 80.0)]
    assert pick_stars(stats) == {"LAL": ["Amy", "Zed"]}


def test_pick_stars_does_not_mutate_input():
    stats = [stat("B", "LAL", 1.0), stat("A", "LAL", 2.0)]
    pick_stars(stats)
    assert [s["name"] for s in stats] == ["B", "A"]


# ---------------------------------------------------------------- overrides


def test_overrides_are_applied_after_computed_stars(lakers):
    computed = {"NBA": {"LAL": ["Austin Reaves", "Rui Hachimura", "Gabe Vincent"]}}
    overrides = {"NBA": {"always": [{"name": "Luka Doncic", "team": "LAL"}], "never": ["Gabe Vincent"]}}
    sync_stars(computed, overrides)
    assert set(lakers.players.filter(is_star=True).values_list("name", flat=True)) == {
        "Luka Doncic",
        "Austin Reaves",
        "Rui Hachimura",
    }


def test_overrides_cap_at_five_and_always_wins_over_computed(lakers):
    computed = {"NBA": {"LAL": [f"Computed {i}" for i in range(5)]}}
    overrides = {"NBA": {"always": [{"name": "Luka Doncic", "team": "LAL"}]}}
    sync_stars(computed, overrides)
    names = set(lakers.players.filter(is_star=True).values_list("name", flat=True))
    assert len(names) == 5
    assert "Luka Doncic" in names and "Computed 4" not in names


def test_never_clears_a_star_even_on_untouched_teams(lakers):
    sync_stars({"NBA": {"LAL": ["Luka Doncic"]}})
    sync_stars(None, {"NBA": {"never": ["Luka Doncic"]}})
    assert not lakers.players.filter(is_star=True).exists()


def test_bare_name_override_must_match_one_player(lakers):
    with pytest.raises(StarListError):
        sync_stars(None, {"NBA": {"always": ["Nobody Here"]}})
    Player.objects.create(team=lakers, name="Luka Doncic")
    sync_stars(None, {"NBA": {"always": ["Luka Doncic"]}})
    assert Player.objects.get(name="Luka Doncic").is_star


def test_five_always_names_max():
    always = [{"name": f"P{i}", "team": "LAL"} for i in range(6)]
    with pytest.raises(StarListError):
        sync_stars(None, {"NBA": {"always": always}})
