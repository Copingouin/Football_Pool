"""
Sync game results from ESPN and recalculate user scores for affected weeks.

Recommended schedule (Windows Task Scheduler):
  - Every Monday    08:00  (after Monday Night Football)
  - Every Thursday  23:00  (after Thursday Night Football)
  - Every Sunday    16:30  (after early games ~1pm ET)
  - Every Sunday    20:00  (after late games ~4pm ET)
  - Every Sunday    23:30  (after Sunday Night Football)

Usage:
    python manage.py sync_scores              # all incomplete weeks
    python manage.py sync_scores --week 3     # specific week
    python manage.py sync_scores --year 2025  # specific season
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from pool.models import Season, Week, Game, Pick, Score
from pool.services.espn import fetch_week, parse_games


def recalculate_scores(week):
    """
    Recompute the Score record for every user who has picks for this week.
    Only counts picks for games that have a result.
    """
    picks = (
        Pick.objects
        .filter(week=week)
        .select_related("game", "user")
    )

    by_user = {}
    for pick in picks:
        by_user.setdefault(pick.user_id, []).append(pick)

    for user_id, user_picks in by_user.items():
        total = sum(p.points_earned for p in user_picks)
        Score.objects.update_or_create(
            user_id=user_id,
            week=week,
            defaults={"points": total},
        )


class Command(BaseCommand):
    help = "Sync NFL game results from ESPN and recalculate user scores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=timezone.now().year,
            help="NFL season year (default: current year)",
        )
        parser.add_argument(
            "--week",
            type=int,
            default=None,
            help="Specific week number to sync (default: all incomplete weeks)",
        )

    def handle(self, *args, **options):
        year = options["year"]
        week_filter = options["week"]

        try:
            season = Season.objects.get(year=year)
        except Season.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"Season {year} not found — run sync_schedule --year {year} first."
                )
            )
            return

        weeks_qs = season.weeks.exclude(status=Week.STATUS_COMPLETED)
        if week_filter:
            weeks_qs = weeks_qs.filter(week_number=week_filter)

        if not weeks_qs.exists():
            self.stdout.write("No incomplete weeks to sync.")
            return

        for week in weeks_qs.order_by("week_number"):
            self.stdout.write(f"Syncing {week}... ", ending="")
            self.stdout.flush()

            try:
                data = fetch_week(year, week.week_number)
                games = parse_games(data)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"FAILED ({exc})"))
                continue

            updated = 0
            for g in games:
                if g["winner"] is None:
                    continue
                rows = Game.objects.filter(
                    espn_id=g["espn_id"],
                    week=week,
                ).update(winner=g["winner"])
                updated += rows

            if updated:
                recalculate_scores(week)
                # Auto-complete week when every game has a result
                if not week.games.filter(winner__isnull=True).exists():
                    week.status = Week.STATUS_COMPLETED
                    week.save(update_fields=["status"])
                    self.stdout.write(
                        self.style.SUCCESS(f"{updated} results — week marked COMPLETED")
                    )
                else:
                    self.stdout.write(self.style.SUCCESS(f"{updated} results updated"))
            else:
                self.stdout.write("no new results yet")

        self.stdout.write(self.style.SUCCESS("Score sync done."))
