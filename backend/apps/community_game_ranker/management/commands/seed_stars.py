import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.community_game_ranker.services.stars import StarListError, sync_stars

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "seed" / "stars.json"


class Command(BaseCommand):
    help = (
        "Apply the always/never star overrides in seed/stars.json. Computed stars come from "
        "`sync_rosters`. Safe to re-run after editing the file."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", type=Path, default=DEFAULT_FILE)

    def handle(self, *args, file, **options):
        try:
            stars = json.loads(file.read_text())
            marked, cleared = sync_stars(None, overrides=stars)
        except (OSError, json.JSONDecodeError, StarListError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Marked {marked} stars, cleared {cleared}."))
