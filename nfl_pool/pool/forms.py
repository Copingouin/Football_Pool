from django import forms
from django.core.exceptions import ValidationError
from .models import Pick, Game


def forfeited_confidence_values(num_games, locked_values, forfeited_count):
    """
    A missed game (kicked off with no pick) burns the highest confidence value
    still unused, so a no-show can't keep their top numbers for later games.
    Miss one game in a 16-game week and 16 is gone; miss two and 15 goes too.
    """
    available = sorted(set(range(1, num_games + 1)) - set(locked_values), reverse=True)
    return set(available[:forfeited_count])


class PicksForm(forms.Form):
    """
    Dynamically generated form: one winner + one confidence field per game in the week.
    Field names are winner_<game_id> and confidence_<game_id>.
    """

    def __init__(self, *args, week=None, locked_game_ids=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.week = week
        self.locked_game_ids = set(locked_game_ids or [])
        self.user = user

        if week:
            games = week.games.all().order_by('kickoff')
            num_games = len(games)
            for game in games:
                is_locked = game.id in self.locked_game_ids

                self.fields[f'winner_{game.id}'] = forms.ChoiceField(
                    choices=[
                        (Game.WINNER_AWAY, game.away_team),
                        (Game.WINNER_HOME, game.home_team),
                    ],
                    widget=forms.RadioSelect(attrs={'disabled': 'disabled'} if is_locked else {}),
                    label=f"{game.away_team} @ {game.home_team}",
                    required=not is_locked,
                )

                self.fields[f'confidence_{game.id}'] = forms.ChoiceField(
                    choices=[(i, str(i)) for i in range(1, num_games + 1)],
                    widget=forms.Select(
                        attrs={
                            'class': 'form-select confidence-select',
                            **(({'disabled': 'disabled'}) if is_locked else {}),
                        }
                    ),
                    label='Confidence',
                    required=not is_locked,
                )

    def clean(self):
        cleaned_data = super().clean()
        if not self.week:
            return cleaned_data

        games = list(self.week.games.all())
        num_games = len(games)

        # A locked game's fields are rendered `disabled`, so browsers never submit
        # them — look up what was actually saved for it instead. A game that
        # kicked off with no pick ever saved forfeits its confidence number
        # entirely: there's no auto-pick, it just scores 0, and the number goes
        # unused rather than permanently blocking the rest of the week from
        # ever being submitted.
        locked_existing_confidence = {}
        if self.locked_game_ids and self.user:
            locked_existing_confidence = dict(
                Pick.objects.filter(
                    user=self.user, week=self.week, game_id__in=self.locked_game_ids
                ).values_list('game_id', 'confidence_points')
            )

        confidence_values = []
        forfeited_count = 0
        for game in games:
            if game.id in self.locked_game_ids:
                if game.id in locked_existing_confidence:
                    confidence_values.append(locked_existing_confidence[game.id])
                else:
                    forfeited_count += 1
                continue
            conf = cleaned_data.get(f'confidence_{game.id}')
            if conf is not None:
                confidence_values.append(int(conf))

        forfeited_values = forfeited_confidence_values(
            num_games, confidence_values, forfeited_count
        )
        if any(
            int(cleaned_data[f'confidence_{g.id}']) in forfeited_values
            for g in games
            if g.id not in self.locked_game_ids and cleaned_data.get(f'confidence_{g.id}')
        ):
            raise ValidationError(
                'You missed a game, so its confidence value is forfeited: '
                + ', '.join(str(v) for v in sorted(forfeited_values, reverse=True))
                + ' can no longer be used this week.'
            )

        # Only validate full coverage when submitting all picks at once (partial
        # saves mid-week are allowed). Forfeited games are exempt — every other
        # game must have a value, and none may repeat.
        if '_submit_lock' in self.data:
            expected_count = num_games - forfeited_count
            if len(confidence_values) != expected_count or len(set(confidence_values)) != expected_count:
                raise ValidationError(
                    'Every game you can still pick needs a unique confidence value '
                    'before you can submit.'
                )

        # Always reject duplicate confidence values, including against games that
        # already locked with a saved pick.
        if len(confidence_values) != len(set(confidence_values)):
            raise ValidationError(
                'You have duplicate confidence values. Each value must be unique.'
            )

        return cleaned_data
