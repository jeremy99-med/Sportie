import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.community_game_ranker.services import ingest

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300


class Command(BaseCommand):
    help = "Keep today's games current, plus last night's games that have not finished."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=DEFAULT_INTERVAL_SECONDS,
            help="Seconds to wait between passes",
        )
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")

    def handle(self, *args, interval=DEFAULT_INTERVAL_SECONDS, once=False, **options):
        if interval <= 0:
            raise CommandError("--interval must be positive")
        if once:
            self._run_pass()
            return
        try:
            while True:
                close_old_connections()  # survive a database restart in this long-lived process
                try:
                    self._run_pass()
                except Exception:
                    logger.exception("Ranker refresh pass failed; retrying next interval")
                # Wait after the pass, not on a fixed clock: a pass that starts slightly under
                # LIVE_TTL after the last fetch would hit the cache and skip a whole cycle.
                time.sleep(interval)
        except KeyboardInterrupt:
            pass

    def _run_pass(self):
        for day, by_sport in ingest.refresh_live().items():
            for sport, s in by_sport.items():
                self.stdout.write(f"refresh {day} {sport}: {s['created']} new, {s['updated']} updated")
                for error in s["errors"]:
                    self.stderr.write(self.style.WARNING(f"  {sport} {error}"))
