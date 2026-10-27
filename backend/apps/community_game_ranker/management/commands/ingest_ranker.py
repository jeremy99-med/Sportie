from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.community_game_ranker.services import ingest


class Command(BaseCommand):
    help = "Fetch games, standings, injuries and weather for one day (NBA and NFL)."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, help="YYYY-MM-DD")
        parser.add_argument("--sport", choices=ingest.SUPPORTED_SPORTS, help="Default: all sports")
        parser.add_argument(
            "--backfill",
            action="store_true",
            help=f"Also load finished games from the previous {ingest.BACKFILL_DAYS} days",
        )

    def handle(self, *args, date: str, sport=None, backfill=False, **options):
        try:
            day = date_from_iso(date)
        except ValueError as exc:
            raise CommandError(f"--date must be YYYY-MM-DD: {exc}") from exc
        sports = (sport,) if sport else ingest.SUPPORTED_SPORTS

        if backfill:
            self._report("backfill", ingest.backfill_finished(day, sports=sports))
        self._report("ingest", ingest.ingest_day(day, sports=sports))

        # Phase 3 hook: score the day here once services/ranking.py exists, e.g.
        #   from apps.community_game_ranker.services.ranking import score_day
        #   score_day(day)

    def _report(self, label, results):
        for sport, s in results.items():
            self.stdout.write(
                f"{label} {sport}: {s['created']} new, {s['updated']} updated, {s['skipped']} skipped, "
                f"{s['standings']} standings, {s['injuries']} injuries, {s['weather']} weather"
            )
            for error in s["errors"]:
                self.stderr.write(self.style.WARNING(f"  {sport} {error}"))


def date_from_iso(value):
    return date.fromisoformat(value)
