import json
from decimal import Decimal
from pathlib import Path

from django.db import migrations

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
TEAM_FILES = {"NBA": "teams_nba.json", "NFL": "teams_nfl.json"}


def load(name):
    with open(SEED_DIR / name) as f:
        return json.load(f, parse_float=Decimal)


def seed(apps, schema_editor):
    Sport = apps.get_model("community_game_ranker", "Sport")
    Team = apps.get_model("community_game_ranker", "Team")
    Stadium = apps.get_model("community_game_ranker", "Stadium")
    Rivalry = apps.get_model("community_game_ranker", "Rivalry")

    sports = {}
    for row in load("sports.json"):
        code = row.pop("code")
        sports[code], _ = Sport.objects.update_or_create(code=code, defaults=row)

    teams = {}
    for code, filename in TEAM_FILES.items():
        for row in load(filename):
            abbreviation = row.pop("abbreviation")
            teams[code, abbreviation], _ = Team.objects.update_or_create(
                sport=sports[code], abbreviation=abbreviation, defaults=row
            )

    for row in load("stadiums.json"):
        home_team = teams[row.pop("sport"), row.pop("team")]
        Stadium.objects.update_or_create(home_team=home_team, name=row.pop("name"), defaults=row)

    for row in load("rivalries.json"):
        # Historical models skip Rivalry.save(), so normalize the pair order here.
        a, b = sorted((teams[row["sport"], abbr] for abbr in row["teams"]), key=lambda t: t.pk)
        Rivalry.objects.update_or_create(
            team_a=a, team_b=b, defaults={"intensity": row["intensity"], "name": row["name"]}
        )


def unseed(apps, schema_editor):
    Sport = apps.get_model("community_game_ranker", "Sport")
    Team = apps.get_model("community_game_ranker", "Team")
    Stadium = apps.get_model("community_game_ranker", "Stadium")

    for code, filename in TEAM_FILES.items():
        abbreviations = [row["abbreviation"] for row in load(filename)]
        seeded = Team.objects.filter(sport__code=code, abbreviation__in=abbreviations)
        # Rivalries cascade with their teams. Fails (PROTECT) if games still reference a team.
        Stadium.objects.filter(home_team__in=seeded).delete()
        seeded.delete()
    Sport.objects.filter(code__in=[row["code"] for row in load("sports.json")]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("community_game_ranker", "0002_single_vote_and_team_standing"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
