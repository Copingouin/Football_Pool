from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from pool.team_data import TEAM_ABBR

FAVORITE_TEAM_CHOICES = [('', 'No favorite team')] + [
    (name, name) for name in sorted(TEAM_ABBR)
]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=100, blank=True)
    favorite_team = models.CharField(
        max_length=100, blank=True, default='', choices=FAVORITE_TEAM_CHOICES,
        help_text="Shown as your player icon next to your name.",
    )

    def __str__(self):
        return self.display_name or self.user.username


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
