from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Season(models.Model):
    year = models.IntegerField(unique=True)
    is_test = models.BooleanField(default=False)

    class Meta:
        ordering = ['-year']

    def __str__(self):
        label = ' [TEST]' if self.is_test else ''
        return f"NFL {self.year} Season{label}"


class SeasonParticipant(models.Model):
    """A user's registration in a season — independent of whether they've picked yet."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='season_participations')
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='participants')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'season')
        ordering = ['user__username']

    def __str__(self):
        return f"{self.user.username} — {self.season}"


class Week(models.Model):
    STATUS_OPEN = 'open'
    STATUS_LOCKED = 'locked'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_LOCKED, 'Locked'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='weeks')
    week_number = models.IntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)

    class Meta:
        unique_together = ('season', 'week_number')
        ordering = ['week_number']

    def __str__(self):
        return f"{self.season} — Week {self.week_number}"

    @property
    def is_fully_locked(self):
        return self.status in (self.STATUS_LOCKED, self.STATUS_COMPLETED)

    @property
    def is_done(self):
        """True once every game in the week has a recorded winner."""
        return self.games.exists() and not self.games.filter(winner__isnull=True).exists()

    @property
    def previous_week(self):
        return Week.objects.filter(
            season=self.season, week_number=self.week_number - 1
        ).first()

    @property
    def waiting_on_previous_week(self):
        """True if picks can't be entered yet because the prior week isn't done."""
        prev = self.previous_week
        return prev is not None and not prev.is_done


class Game(models.Model):
    WINNER_HOME = 'home'
    WINNER_AWAY = 'away'
    WINNER_CHOICES = [
        (WINNER_HOME, 'Home'),
        (WINNER_AWAY, 'Away'),
    ]

    week = models.ForeignKey(Week, on_delete=models.CASCADE, related_name='games')
    home_team = models.CharField(max_length=50)
    away_team = models.CharField(max_length=50)
    kickoff = models.DateTimeField()
    winner = models.CharField(
        max_length=10, choices=WINNER_CHOICES, null=True, blank=True
    )

    # ESPN identifier — used to match games when syncing schedule/scores
    espn_id = models.CharField(max_length=20, unique=True, null=True, blank=True)

    # Odds — populated by sync_odds, averaged across bookmakers
    home_moneyline = models.IntegerField(null=True, blank=True)
    away_moneyline = models.IntegerField(null=True, blank=True)
    # Negative = home team favored (e.g. -3.5 means home wins by 3.5+)
    home_spread = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    odds_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['kickoff']

    def __str__(self):
        return f"{self.away_team} @ {self.home_team}"

    @property
    def is_locked(self):
        return timezone.now() >= self.kickoff

    @property
    def has_odds(self):
        return self.home_moneyline is not None or self.home_spread is not None

    @property
    def home_moneyline_display(self):
        v = self.home_moneyline
        return (f'+{v}' if v > 0 else str(v)) if v is not None else '—'

    @property
    def away_moneyline_display(self):
        v = self.away_moneyline
        return (f'+{v}' if v > 0 else str(v)) if v is not None else '—'

    def spread_display(self):
        """'KC -3.5' style string for the favored team."""
        if self.home_spread is None:
            return '—'
        spread = self.home_spread
        if spread < 0:
            return f'{self.home_team} {spread:+.1f}'
        elif spread > 0:
            return f'{self.away_team} -{spread:.1f}'
        else:
            return 'Pick \'em'


class Pick(models.Model):
    WINNER_HOME = 'home'
    WINNER_AWAY = 'away'
    WINNER_CHOICES = [
        (WINNER_HOME, 'Home'),
        (WINNER_AWAY, 'Away'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='picks')
    week = models.ForeignKey(Week, on_delete=models.CASCADE, related_name='picks')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='picks')
    confidence_points = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(16)]
    )
    predicted_winner = models.CharField(max_length=10, choices=WINNER_CHOICES)
    locked = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'week', 'game')

    def __str__(self):
        return (
            f"{self.user.username} — {self.game} — "
            f"{self.confidence_points}pts — {self.predicted_winner}"
        )

    @property
    def is_correct(self):
        return (
            self.game.winner is not None
            and self.predicted_winner == self.game.winner
        )

    @property
    def points_earned(self):
        return self.confidence_points if self.is_correct else 0


class Score(models.Model):
    """Denormalized cache of a user's score per week. Recomputed when results are entered."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scores')
    week = models.ForeignKey(Week, on_delete=models.CASCADE, related_name='scores')
    points = models.IntegerField(default=0)

    class Meta:
        unique_together = ('user', 'week')

    def __str__(self):
        return f"{self.user.username} — {self.week} — {self.points}pts"


def recalculate_week_scores(week):
    """Recompute Score rows for every user who has picks in the given week."""
    users = User.objects.filter(picks__week=week).distinct()
    for user in users:
        points = sum(
            pick.points_earned
            for pick in Pick.objects.filter(user=user, week=week)
        )
        Score.objects.update_or_create(
            user=user,
            week=week,
            defaults={'points': points},
        )


@receiver(post_save, sender=Game)
def game_winner_saved(sender, instance, **kwargs):
    if instance.winner is not None:
        recalculate_week_scores(instance.week)
