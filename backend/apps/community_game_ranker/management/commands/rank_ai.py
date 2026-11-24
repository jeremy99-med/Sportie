from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.community_game_ranker.management.commands.refresh_ranker import report_ai
from apps.community_game_ranker.services import ai_assist
from apps.community_game_ranker.services.ranking import SCHEDULE_TZ


class Command(BaseCommand):
    help = (
        "Have Claude rank one day's games now (default today, US Eastern). Skips the hourly wait, "
        "but still skips the API call when nothing the ranking depends on has changed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--date", help="YYYY-MM-DD (default: today, US Eastern)")

    def handle(self, *args, date=None, **options):
        try:
            day = date_from_iso(date) if date else timezone.now().astimezone(SCHEDULE_TZ).date()
        except ValueError as exc:
            raise CommandError(f"--date must be YYYY-MM-DD: {exc}") from exc
        report_ai(self, day, ai_assist.rank_day(day, force=True))


def date_from_iso(value):
    return date.fromisoformat(value)
