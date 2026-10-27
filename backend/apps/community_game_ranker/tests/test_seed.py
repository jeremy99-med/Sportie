import importlib

import pytest
from django.apps import apps as django_apps

from apps.community_game_ranker.models import Rivalry, Sport, Stadium, Team

pytestmark = pytest.mark.django_db

seed_migration = importlib.import_module(
    "apps.community_game_ranker.migrations.0003_seed_reference_data"
)


def test_seed_creates_all_sports_and_teams():
    assert set(Sport.objects.values_list("code", flat=True)) == {"NFL", "NBA", "NHL", "MLB"}
    assert Team.objects.filter(sport__code="NBA").count() == 30
    assert Team.objects.filter(sport__code="NFL").count() == 32


def test_every_seeded_team_has_exactly_one_stadium():
    for team in Team.objects.filter(sport__code__in=["NBA", "NFL"]):
        assert team.stadiums.count() == 1, team


def test_nba_arenas_are_indoor_and_some_nfl_stadiums_are_outdoor():
    assert not Stadium.objects.filter(home_team__sport__code="NBA", is_indoor=False).exists()
    assert Stadium.objects.get(home_team__sport__code="NFL", home_team__abbreviation="GB").is_indoor is False
    assert Stadium.objects.get(home_team__sport__code="NFL", home_team__abbreviation="DET").is_indoor is True


def test_seeded_rivalries_are_normalized_and_same_sport():
    assert Rivalry.objects.exists()
    for rivalry in Rivalry.objects.select_related("team_a", "team_b"):
        assert rivalry.team_a_id < rivalry.team_b_id
        assert rivalry.team_a.sport_id == rivalry.team_b.sport_id


def test_seed_is_idempotent():
    counts = (Team.objects.count(), Stadium.objects.count(), Rivalry.objects.count())
    seed_migration.seed(django_apps, None)
    assert (Team.objects.count(), Stadium.objects.count(), Rivalry.objects.count()) == counts
