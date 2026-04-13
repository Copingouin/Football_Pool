from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone

from .models import Week, Game, Pick, Score, Season
from .forms import PicksForm


@login_required
def picks(request, week_id):
    """/week/<week_id>/picks/ — enter or view picks for a week."""
    week = get_object_or_404(Week, pk=week_id)
    games = list(week.games.order_by('kickoff'))
    now = timezone.now()

    # Games past kickoff are auto-locked regardless of pick status
    locked_game_ids = {g.id for g in games if g.is_locked}

    # Existing picks for this user/week
    existing_picks = {
        p.game_id: p
        for p in Pick.objects.filter(user=request.user, week=week).select_related('game')
    }

    # A user's week is considered "fully locked" if they hit Submit, or if the
    # admin has locked/completed the week, or if every pick they have is locked.
    user_week_locked = week.is_fully_locked or (
        len(existing_picks) == len(games)
        and all(p.locked for p in existing_picks.values())
    )

    if request.method == 'POST' and not user_week_locked:
        form = PicksForm(
            request.POST, week=week, locked_game_ids=locked_game_ids
        )
        if form.is_valid():
            submit_and_lock = '_submit_lock' in request.POST

            for game in games:
                if game.id in locked_game_ids:
                    # Auto-lock any existing pick for this game
                    if game.id in existing_picks and not existing_picks[game.id].locked:
                        existing_picks[game.id].locked = True
                        existing_picks[game.id].save(update_fields=['locked'])
                    continue

                winner = form.cleaned_data.get(f'winner_{game.id}')
                confidence = form.cleaned_data.get(f'confidence_{game.id}')
                if not winner or not confidence:
                    continue

                pick, _ = Pick.objects.get_or_create(
                    user=request.user,
                    week=week,
                    game=game,
                    defaults={
                        'predicted_winner': winner,
                        'confidence_points': int(confidence),
                    },
                )
                if not pick.locked:
                    pick.predicted_winner = winner
                    pick.confidence_points = int(confidence)
                    if submit_and_lock:
                        pick.locked = True
                    pick.save()

            if submit_and_lock:
                messages.success(request, 'Picks submitted and locked!')
            else:
                messages.success(request, 'Picks saved.')
            return redirect('pool:picks', week_id=week_id)
    else:
        # Pre-populate with existing picks
        initial = {}
        for game in games:
            pick = existing_picks.get(game.id)
            if pick:
                initial[f'winner_{game.id}'] = pick.predicted_winner
                initial[f'confidence_{game.id}'] = pick.confidence_points
        form = PicksForm(initial=initial, week=week, locked_game_ids=locked_game_ids)

    context = {
        'week': week,
        'games': games,
        'form': form,
        'existing_picks': existing_picks,
        'locked_game_ids': locked_game_ids,
        'user_week_locked': user_week_locked,
        'now': now,
        'confidence_range': range(1, 17),
    }
    return render(request, 'pool/picks.html', context)


@login_required
def leaderboard(request):
    """/leaderboard/ — all-time standings + current week rank."""
    players = (
        User.objects.filter(is_active=True, is_staff=False)
        .annotate(total_points=Sum('scores__points'))
        .order_by('-total_points')
    )

    # Find the most recent open or locked week to show current-week rank
    current_week = (
        Week.objects.filter(status__in=[Week.STATUS_OPEN, Week.STATUS_LOCKED])
        .order_by('-season__year', '-week_number')
        .first()
    )

    current_week_scores = {}
    if current_week:
        for score in Score.objects.filter(week=current_week).select_related('user'):
            current_week_scores[score.user_id] = score.points

    context = {
        'players': players,
        'current_week': current_week,
        'current_week_scores': current_week_scores,
    }
    return render(request, 'pool/leaderboard.html', context)


@login_required
def results(request, week_id):
    """/week/<week_id>/results/ — visible only after a player's picks are locked."""
    week = get_object_or_404(Week, pk=week_id)
    games = week.games.prefetch_related('picks__user').order_by('kickoff')

    user_picks = Pick.objects.filter(user=request.user, week=week)
    all_user_picks_locked = week.is_fully_locked or (
        user_picks.exists() and user_picks.filter(locked=False).count() == 0
    )

    if not all_user_picks_locked:
        messages.warning(
            request,
            'You must submit and lock your picks before viewing the results.'
        )
        return redirect('pool:picks', week_id=week_id)

    # Build a lookup: game_id -> {user_id -> pick}
    all_picks = Pick.objects.filter(week=week).select_related('user', 'game')
    picks_by_game = {}
    for pick in all_picks:
        picks_by_game.setdefault(pick.game_id, {})[pick.user_id] = pick

    players = User.objects.filter(
        picks__week=week
    ).distinct().order_by('username')

    week_scores = {
        s.user_id: s.points
        for s in Score.objects.filter(week=week)
    }

    context = {
        'week': week,
        'games': games,
        'players': players,
        'picks_by_game': picks_by_game,
        'week_scores': week_scores,
    }
    return render(request, 'pool/results.html', context)
