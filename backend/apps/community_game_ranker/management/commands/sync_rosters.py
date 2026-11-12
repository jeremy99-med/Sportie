import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.community_game_ranker.integrations.balldontlie import BalldontlieError
from apps.community_game_ranker.integrations.sportsdata import SportsDataError
from apps.community_game_ranker.services import ingest
from apps.community_game_ranker.services.stars import StarListError

DEFAULT_OVERRIDES = Path(__file__).resolve().parents[2] / "seed" / "stars.json"


class Command(BaseCommand):
    help = (
        "Sync team ids and rosters from SportsData.io (trades move players), then recompute "
        "stars from season stats and apply seed/stars.json overrides. Run weekly."
    )

    def add_arguments(self, parser):
        parser.add_argument("--sport", choices=ingest.SUPPORTED_SPORTS, help="Default: all sports")
        parser.add_argument("--skip-stars", action="store_true", help="Rosters only")
        parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)

    def handle(self, *args, sport=None, skip_stars=False, overrides=DEFAULT_OVERRIDES, **options):
        try:
            override_data = json.loads(overrides.read_text()) if not skip_stars else None
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(str(exc)) from exc
        for code in (sport,) if sport else ingest.SUPPORTED_SPORTS:
            try:
                s = ingest.sync_rosters(code)
                self.stdout.write(
                    f"{code} rosters: {s['teams_linked']} teams linked, {s['created']} new players, "
                    f"{s['updated']} updated, {s['moved']} traded, {s['released']} released"
                )
                for error in s["errors"]:
                    self.stderr.write(self.style.WARNING(f"  {code} {error}"))
                if not skip_stars:
                    marked, cleared = ingest.refresh_stars(code, date.today(), override_data)
                    self.stdout.write(f"{code} stars: marked {marked}, cleared {cleared}")
            except (SportsDataError, BalldontlieError, StarListError) as exc:
                raise CommandError(f"{code}: {exc}") from exc
