"""
Email every season participant a Tuesday-morning reminder to submit picks for
the next open week, plus a shoutout for whoever scored the most points in the
week that just finished.

Self-contained: safe to delete this file (and the Railway cron service running
it) as a unit if it doesn't work out — no models, no other code paths touch it.

Recommended schedule (Railway Cron Schedule, UTC): Tuesday mornings, e.g.
"0 13 * * 2" (~9am ET). Adjust for DST same as the other cron jobs.

Usage:
    python manage.py send_pick_reminders              # current year
    python manage.py send_pick_reminders --year 2025
    python manage.py send_pick_reminders --dry-run     # print instead of send
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage, get_connection
from django.urls import reverse
from django.utils import timezone

from pool.models import Season, Week, Score, SeasonParticipant


class Command(BaseCommand):
    help = "Email season participants a reminder to submit next week's picks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=timezone.now().year,
            help="NFL season year (default: current year)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print emails instead of sending them.",
        )

    def handle(self, *args, **options):
        year = options["year"]
        dry_run = options["dry_run"]

        try:
            season = Season.objects.get(year=year, is_test=False)
        except Season.DoesNotExist:
            self.stdout.write(f"No live season for {year} — nothing to send.")
            return

        weeks = list(season.weeks.order_by("week_number"))
        open_week = next((w for w in weeks if w.display_status == Week.STATUS_OPEN), None)
        if open_week is None:
            self.stdout.write("No open week to pick right now — nothing to send.")
            return

        last_done_week = next((w for w in reversed(weeks) if w.is_done), None)
        top_scorers, top_points = self._top_scorers(last_done_week)

        participants = (
            SeasonParticipant.objects.filter(season=season)
            .select_related("user")
            .exclude(user__email="")
        )
        if not participants.exists():
            self.stdout.write("No participants with an email on file — nothing to send.")
            return

        connection = get_connection() if not dry_run else None
        sent = 0
        for participant in participants:
            user = participant.user
            message = self._build_message(
                user, open_week, last_done_week, top_scorers, top_points
            )
            if dry_run:
                self.stdout.write(f"--- {user.email} ---\n{message.subject}\n{message.body}\n")
            else:
                message.connection = connection
                message.send()
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Reminder sent to {sent} participant(s)."))

    def _top_scorers(self, week):
        """Users tied for the most points in `week`. Returns ([usernames], points)."""
        if week is None:
            return [], 0
        scores = list(Score.objects.filter(week=week).select_related("user"))
        if not scores:
            return [], 0
        top_points = max(s.points for s in scores)
        if top_points == 0:
            return [], 0
        top_scorers = [s.user.username for s in scores if s.points == top_points]
        return top_scorers, top_points

    def _build_message(self, user, open_week, last_done_week, top_scorers, top_points):
        first_kickoff = open_week.games.order_by("kickoff").values_list("kickoff", flat=True).first()

        domain = settings.RAILWAY_PUBLIC_DOMAIN or "localhost:8000"
        pick_link = f"https://{domain}{reverse('pool:picks', args=[open_week.id])}"

        lines = [
            f"Hi {user.username},",
            "",
            f"Week {open_week.week_number} picks are open — get them in before kickoff!",
            pick_link,
        ]
        if first_kickoff:
            local_kickoff = timezone.localtime(first_kickoff)
            day = local_kickoff.strftime("%A, %B") + f" {local_kickoff.day}"
            hour_12 = local_kickoff.hour % 12 or 12
            time_str = f"{hour_12}:{local_kickoff:%M %p %Z}"
            lines.append(f"First game locks: {day} at {time_str}.")

        if top_scorers:
            names = " & ".join(top_scorers)
            lines += [
                "",
                f"Top score for Week {last_done_week.week_number}: "
                f"{names} with {top_points} point{'s' if top_points != 1 else ''}!",
            ]

        lines += ["", "Good luck!"]
        body = "\n".join(lines)

        return EmailMessage(
            subject=f"Week {open_week.week_number} picks are open",
            body=body,
            to=[user.email],
        )
