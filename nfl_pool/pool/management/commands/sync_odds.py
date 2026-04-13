"""
Pull fresh NFL odds from The Odds API and update Game records.
Averages moneyline and spread across all available US bookmakers.

Recommended schedule (Windows Task Scheduler):
  - Every day 09:00

Usage:
    python manage.py sync_odds
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from pool.services.odds import fetch_odds, parse_game_odds, match_game_to_db


class Command(BaseCommand):
    help = "Sync NFL odds (moneyline + spread) from The Odds API."

    def handle(self, *args, **options):
        self.stdout.write("Fetching odds from The Odds API...")

        try:
            raw_games = fetch_odds()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Failed to fetch odds: {exc}"))
            return

        self.stdout.write(f"Received {len(raw_games)} games from API.")

        updated = 0
        skipped = 0
        now = timezone.now()

        for raw in raw_games:
            odds = parse_game_odds(raw)
            game = match_game_to_db(
                odds["home_team"],
                odds["away_team"],
                odds["commence_time"],
            )

            if not game:
                self.stdout.write(
                    f"  No match found: {odds['away_team']} @ {odds['home_team']}"
                )
                skipped += 1
                continue

            game.home_moneyline = odds["home_moneyline"]
            game.away_moneyline = odds["away_moneyline"]
            game.home_spread = odds["home_spread"]
            game.odds_updated_at = now
            game.save(update_fields=[
                "home_moneyline", "away_moneyline", "home_spread", "odds_updated_at"
            ])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Odds sync complete — {updated} updated, {skipped} unmatched."
            )
        )
