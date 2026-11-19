import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from apps.community_game_ranker.services import ai_assist, ingest
from apps.community_game_ranker.services.ranking import SCHEDULE_TZ

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300


class Command(BaseCommand):
    help = (
        "Keep today's games current, finish last night's, and load the rest of the site's window. "
        "About once an hour, Claude also re-ranks today's games (see services/ai_assist.py)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=DEFAULT_INTERVAL_SECONDS,
            help="Seconds to wait between passes",
        )
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")
        parser.add_argument("--no-ai", action="store_true", help="Skip the hourly Claude ranking")

    def handle(self, *args, interval=DEFAULT_INTERVAL_SECONDS, once=False, no_ai=False, **options):
        if interval <= 0:
            raise CommandError("--interval must be positive")
        self.use_ai = not no_ai
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
        if self.use_ai:
            # After ingest, so Claude sees this pass's injuries, weather and scores.
            today = timezone.now().astimezone(SCHEDULE_TZ).date()
            result = ai_assist.rank_day(today)
            if result["status"] == "disabled":
                self.use_ai = False  # say so once, not every 5 minutes
            report_ai(self, today, result)


def report_ai(command, day, result):
    """Print one line for an AI pass. Quiet when it wasn't due, so 5-minute logs stay short."""
    status = result["status"]
    if status == "fresh":
        return
    if status == "error":
        command.stderr.write(command.style.WARNING(f"ai {day}: failed: {result['error']}"))
    elif status == "disabled":
        command.stdout.write(f"ai {day}: skipped, ANTHROPIC_API_KEY is not set")
    else:
        command.stdout.write(f"ai {day}: {status} ({result['games']} games)")
