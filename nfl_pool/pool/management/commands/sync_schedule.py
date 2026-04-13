"""
Pull the full NFL regular-season schedule from ESPN and populate
Season, Week, and Game records.

Run once before each season:
    python manage.py sync_schedule --year 2025
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from pool.models import Season, Week, Game
from pool.services.espn import fetch_week, parse_games, NFL_REGULAR_SEASON_WEEKS


class Command(BaseCommand):
    help = "Sync the full NFL season schedule from ESPN (run once per season)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=timezone.now().year,
            help="NFL season year (default: current year)",
        )

    def handle(self, *args, **options):
        year = options["year"]
        season, created = Season.objects.get_or_create(year=year)
        self.stdout.write(
            f"{'Created' if created else 'Using existing'} season: {season}"
        )

        total = 0
        for week_num in range(1, NFL_REGULAR_SEASON_WEEKS + 1):
            self.stdout.write(f"  Week {week_num:2d}... ", ending="")
            self.stdout.flush()

            try:
                data = fetch_week(year, week_num)
                games = parse_games(data)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"FAILED ({exc})"))
                continue

            if not games:
                self.stdout.write("no games returned, skipping.")
                continue

            week, _ = Week.objects.get_or_create(
                season=season,
                week_number=week_num,
            )

            for g in games:
                Game.objects.update_or_create(
                    espn_id=g["espn_id"],
                    defaults={
                        "week": week,
                        "home_team": g["home_team"],
                        "away_team": g["away_team"],
                        "kickoff": g["kickoff"],
                        "winner": g["winner"],
                    },
                )
                total += 1

            self.stdout.write(self.style.SUCCESS(f"{len(games)} games"))

        self.stdout.write(self.style.SUCCESS(f"\nSchedule sync complete — {total} games."))
