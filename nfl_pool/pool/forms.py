from django import forms
from django.core.exceptions import ValidationError
from .models import Pick, Game


class PicksForm(forms.Form):
    """
    Dynamically generated form: one winner + one confidence field per game in the week.
    Field names are winner_<game_id> and confidence_<game_id>.
    """

    def __init__(self, *args, week=None, locked_game_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.week = week
        self.locked_game_ids = set(locked_game_ids or [])

        if week:
            games = week.games.all().order_by('kickoff')
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
                    choices=[(i, str(i)) for i in range(1, 17)],
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

        games = self.week.games.all()
        confidence_values = []

        for game in games:
            if game.id in self.locked_game_ids:
                continue
            conf = cleaned_data.get(f'confidence_{game.id}')
            if conf is not None:
                try:
                    confidence_values.append(int(conf))
                except (ValueError, TypeError):
                    pass

        # Only validate the full 1-16 uniqueness when submitting all picks at once
        # (partial saves mid-week are allowed)
        if '_submit_lock' in self.data:
            all_confs = []
            for game in games:
                conf = cleaned_data.get(f'confidence_{game.id}')
                if conf is not None:
                    try:
                        all_confs.append(int(conf))
                    except (ValueError, TypeError):
                        pass
            if sorted(all_confs) != list(range(1, 17)):
                raise ValidationError(
                    'Each confidence value from 1 to 16 must be used exactly once '
                    'across all games before you can submit.'
                )

        # Always reject duplicate confidence values among unlocked picks
        if len(confidence_values) != len(set(confidence_values)):
            raise ValidationError(
                'You have duplicate confidence values. Each value must be unique.'
            )

        return cleaned_data
