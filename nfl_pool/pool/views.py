from django.conf import settings
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Season, Week, Game, Pick, Score, SeasonParticipant
from .forms import PicksForm
from .services.espn_news import fetch_game_news


@login_required
def home(request):
    """/seasons/ — list all seasons with the player's status in each."""
    seasons = Season.objects.prefetch_related('weeks').order_by('-year')

    # User's total points per season
    user_points_by_season = {
        row['week__season_id']: row['total']
        for row in Score.objects.filter(user=request.user)
            .values('week__season_id')
            .annotate(total=Sum('points'))
    }

    joined_seasons = set(
        SeasonParticipant.objects.filter(user=request.user)
            .values_list('season_id', flat=True)
    )

    season_data = []
    for season in seasons:
        open_week = next(
            (w for w in season.weeks.all() if w.display_status == Week.STATUS_OPEN), None
        )
        season_data.append({
            'season': season,
            'user_points': user_points_by_season.get(season.id),
            'joined': season.id in joined_seasons,
            'open_week': open_week,
        })

    return render(request, 'pool/home.html', {'season_data': season_data})


@login_required
def season(request, season_id):
    """/season/<id>/ — per-season leaderboard and week list."""
    s = get_object_or_404(Season, pk=season_id)

    # Leaderboard: everyone registered for this season, ranked by season total
    # (registered-but-not-yet-scored players show up with 0 points).
    players = (
        User.objects.filter(season_participations__season=s)
        .distinct()
        .annotate(
            season_points=Coalesce(
                Sum('scores__points', filter=Q(scores__week__season=s)), 0
            )
        )
        .order_by('-season_points', 'username')
    )

    # Weeks with the user's score and open-week flag
    weeks = s.weeks.order_by('week_number')
    user_scores = {
        row['week_id']: row['points']
        for row in Score.objects.filter(user=request.user, week__season=s)
            .values('week_id', 'points')
    }

    week_data = []
    for week in weeks:
        week_data.append({
            'week': week,
            'user_points': user_scores.get(week.id),
        })

    context = {
        'season': s,
        'players': players,
        'week_data': week_data,
    }
    return render(request, 'pool/season.html', context)


@login_required
@require_POST
def register_season(request, season_id):
    """POST /season/<id>/register/ — join a season's roster (no picks required)."""
    season = get_object_or_404(Season, pk=season_id)
    _, created = SeasonParticipant.objects.get_or_create(user=request.user, season=season)
    if created:
        messages.success(request, f"You're registered for the {season.year} season!")

    open_week = next(
        (w for w in season.weeks.all() if w.display_status == Week.STATUS_OPEN), None
    )
    if open_week:
        return redirect('pool:picks', week_id=open_week.id)
    return redirect('pool:season', season_id=season.id)


@login_required
def picks(request, week_id):
    """/week/<week_id>/picks/ — enter or view picks for a week."""
    week = get_object_or_404(Week, pk=week_id)
    games = list(week.games.order_by('kickoff'))
    now = timezone.now()

    locked_game_ids = {g.id for g in games if g.is_locked}

    existing_picks = {
        p.game_id: p
        for p in Pick.objects.filter(user=request.user, week=week).select_related('game')
    }

    user_week_locked = week.is_fully_locked or (
        len(existing_picks) == len(games)
        and all(p.locked for p in existing_picks.values())
    )
    previous_week_pending = (not user_week_locked) and week.waiting_on_previous_week

    if request.method == 'POST' and previous_week_pending:
        messages.error(
            request,
            f'You cannot enter picks for this week until Week '
            f'{week.previous_week.week_number} is done.'
        )
        return redirect('pool:picks', week_id=week_id)

    if request.method == 'POST' and not user_week_locked:
        form = PicksForm(
            request.POST, week=week, locked_game_ids=locked_game_ids
        )
        if form.is_valid():
            submit_and_lock = '_submit_lock' in request.POST

            for game in games:
                if game.id in locked_game_ids:
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
        'previous_week_pending': previous_week_pending,
        'now': now,
        'confidence_range': range(1, len(games) + 1),
        'enable_game_news': settings.ENABLE_GAME_NEWS,
    }
    return render(request, 'pool/picks.html', context)


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


# --- Per-game news (self-contained feature — see ENABLE_GAME_NEWS in settings.py) ---

@login_required
def game_news(request, game_id):
    """GET /game/<game_id>/news/ — HTML fragment of ESPN news for a game's two teams."""
    if not settings.ENABLE_GAME_NEWS:
        raise Http404

    game = get_object_or_404(Game, pk=game_id)
    articles = fetch_game_news(game.home_team, game.away_team)
    return render(request, 'pool/_game_news.html', {'game': game, 'articles': articles})
