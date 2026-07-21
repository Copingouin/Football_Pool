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
    weeks = list(s.weeks.order_by('week_number'))
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

    chart = build_season_chart(s, players)
    head_to_head = build_head_to_head(s, players)

    latest_done_week = next((w for w in reversed(weeks) if w.is_done), None)
    highlights = find_highlights(latest_done_week) if latest_done_week else []

    context = {
        'season': s,
        'players': players,
        'week_data': week_data,
        'chart_labels': chart['labels'],
        'chart_datasets': chart['datasets'],
        'head_to_head': head_to_head,
        'highlights': highlights,
        'highlights_week': latest_done_week,
    }
    return render(request, 'pool/season.html', context)


def build_head_to_head(season, players):
    """
    For every pair of players, how many weeks (where both were scored) player A
    outscored player B. Returns None if fewer than 2 players — nothing to compare.
    """
    player_list = list(players)
    if len(player_list) < 2:
        return None

    scores_by_user = {}
    for row in Score.objects.filter(week__season=season).values('user_id', 'week_id', 'points'):
        scores_by_user.setdefault(row['user_id'], {})[row['week_id']] = row['points']

    rows = []
    for a in player_list:
        a_scores = scores_by_user.get(a.id, {})
        cells = []
        for b in player_list:
            if a.id == b.id:
                cells.append(None)
                continue
            b_scores = scores_by_user.get(b.id, {})
            common_weeks = set(a_scores) & set(b_scores)
            cells.append(sum(1 for w in common_weeks if a_scores[w] > b_scores[w]))
        rows.append({'player': a, 'cells': cells})

    return {'players': player_list, 'rows': rows}


# Fixed categorical order, validated (dataviz skill) against this app's dark navy
# surface — colorblind-safe adjacent separation. Assigned to players by a stable
# order (username), never by live standings rank, so a player's line color never
# changes as they move up/down the leaderboard.
CHART_PALETTE = [
    '#3987e5', '#008300', '#d55181', '#c98500',
    '#199e70', '#d95926', '#9085e9', '#e66767',
]


def build_season_chart(season, players):
    """Cumulative points per player by week, for the season trend chart."""
    week_numbers = list(season.weeks.order_by('week_number').values_list('week_number', flat=True))

    points_by_user = {}
    for row in Score.objects.filter(week__season=season).values('user_id', 'week__week_number', 'points'):
        points_by_user.setdefault(row['user_id'], {})[row['week__week_number']] = row['points']

    color_by_user = {
        user.id: CHART_PALETTE[i % len(CHART_PALETTE)]
        for i, user in enumerate(sorted(players, key=lambda u: u.username))
    }

    datasets = []
    for player in players:
        per_week = points_by_user.get(player.id)
        if not per_week:
            continue
        running = 0
        data = []
        for wn in week_numbers:
            running += per_week.get(wn, 0)
            data.append(running)
        datasets.append({
            'label': player.username,
            'data': data,
            'color': color_by_user[player.id],
        })

    return {
        'labels': [f'Wk {wn}' for wn in week_numbers],
        'datasets': datasets,
    }


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


def _user_week_is_locked(week, games, existing_picks, locked_game_ids):
    """
    True once a user is "done" with a week: the admin force-locked it, or every
    game is either picked (with that pick locked) or forfeited — kicked off with
    no pick ever saved, which scores 0 for that game but isn't otherwise a block.
    """
    all_games_accounted_for = all(
        g.id in locked_game_ids or g.id in existing_picks for g in games
    )
    return week.is_fully_locked or (
        all_games_accounted_for
        and all(p.locked for p in existing_picks.values())
    )


@login_required
def picks(request, week_id):
    """/week/<week_id>/picks/ — enter or view picks for a week."""
    week = get_object_or_404(Week, pk=week_id)
    games = list(week.games.order_by('kickoff'))
    now = timezone.now()

    locked_game_ids = {g.id for g in games if g.is_locked}
    next_kickoff = min(
        (g.kickoff for g in games if g.id not in locked_game_ids), default=None
    )

    existing_picks = {
        p.game_id: p
        for p in Pick.objects.filter(user=request.user, week=week).select_related('game')
    }

    user_week_locked = _user_week_is_locked(week, games, existing_picks, locked_game_ids)
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
            request.POST, week=week, locked_game_ids=locked_game_ids, user=request.user
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
                messages.success(request, 'Picks submitted and locked!', extra_tags='confetti')
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
        form = PicksForm(initial=initial, week=week, locked_game_ids=locked_game_ids, user=request.user)

    context = {
        'week': week,
        'games': games,
        'form': form,
        'existing_picks': existing_picks,
        'locked_game_ids': locked_game_ids,
        'user_week_locked': user_week_locked,
        'previous_week_pending': previous_week_pending,
        'next_kickoff': next_kickoff,
        'now': now,
        'confidence_range': range(1, len(games) + 1),
        'enable_game_news': settings.ENABLE_GAME_NEWS,
    }
    return render(request, 'pool/picks.html', context)


@login_required
def results(request, week_id):
    """/week/<week_id>/results/ — visible only after a player's picks are locked."""
    week = get_object_or_404(Week, pk=week_id)
    games = list(week.games.prefetch_related('picks__user').order_by('kickoff'))
    locked_game_ids = {g.id for g in games if g.is_locked}

    user_picks = Pick.objects.filter(user=request.user, week=week)
    existing_picks = {p.game_id: p for p in user_picks}
    all_user_picks_locked = _user_week_is_locked(week, games, existing_picks, locked_game_ids)

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

    perfect_week = (
        week.is_done
        and user_picks.exists()
        and all(p.is_correct for p in user_picks)
    )

    biggest_upset = find_biggest_upset(games, picks_by_game)
    highlights = find_highlights(week)

    context = {
        'week': week,
        'games': games,
        'players': players,
        'picks_by_game': picks_by_game,
        'week_scores': week_scores,
        'perfect_week': perfect_week,
        'biggest_upset': biggest_upset,
        'highlights': highlights,
    }
    return render(request, 'pool/results.html', context)


def find_biggest_upset(games, picks_by_game):
    """
    The decided game where the winner had the largest positive moneyline (i.e.
    was the biggest underdog), plus whoever correctly called it. None if no
    decided game this week has odds on record.
    """
    candidates = []
    for game in games:
        if not game.winner or not game.has_odds:
            continue
        winner_moneyline = game.home_moneyline if game.winner == 'home' else game.away_moneyline
        if winner_moneyline is not None and winner_moneyline > 0:
            candidates.append((winner_moneyline, game))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    moneyline, game = candidates[0]

    callers = sorted(
        (p for p in picks_by_game.get(game.id, {}).values() if p.is_correct),
        key=lambda p: p.confidence_points,
        reverse=True,
    )

    return {'game': game, 'moneyline': moneyline, 'callers': callers}


# --- "News" highlights banner — self-contained, computed on read (no new storage,
#     see ENABLE_HIGHLIGHTS in settings.py). Busted big-confidence picks and season
#     standings shakeups, derived from Pick/Score/ScoreHistory already on hand. ---

def _season_standings(weeks):
    """[(user_id, total_points), ...] sorted by points desc, over the given weeks."""
    totals = (
        Score.objects.filter(week__in=weeks)
        .values('user_id')
        .annotate(total=Sum('points'))
    )
    return sorted(
        ((row['user_id'], row['total']) for row in totals),
        key=lambda pair: pair[1], reverse=True,
    )


def find_highlights(week):
    """
    Notable moments from a decided week: big confidence picks that busted, and
    movement at the top of the season standings. Empty list if the week isn't
    fully decided yet or the feature is disabled.
    """
    if not settings.ENABLE_HIGHLIGHTS or not week.is_done:
        return []

    highlights = []

    max_confidence = week.games.count()
    week_picks = Pick.objects.filter(week=week).select_related('user', 'game')
    for pick in week_picks:
        if not pick.is_correct and pick.confidence_points >= max_confidence - 2:
            highlights.append(
                f"{pick.user.username} just lost {pick.confidence_points} points on "
                f"{pick.game.away_team} @ {pick.game.home_team}"
            )

    season = week.season
    prior_weeks = season.weeks.filter(week_number__lt=week.week_number)
    if prior_weeks.exists():
        weeks_through_now = season.weeks.filter(week_number__lte=week.week_number)
        before_rank = {
            user_id: i + 1 for i, (user_id, _) in enumerate(_season_standings(prior_weeks))
        }
        after_rank = {
            user_id: i + 1 for i, (user_id, _) in enumerate(_season_standings(weeks_through_now))
        }
        usernames = {
            u.id: u.username for u in User.objects.filter(id__in=after_rank)
        }

        for user_id, new_rank in after_rank.items():
            old_rank = before_rank.get(user_id)
            if old_rank is None or old_rank == new_rank:
                continue
            if old_rank == 1 and new_rank != 1:
                highlights.append(f"{usernames[user_id]} just dropped out of 1st place!")
            elif new_rank == 1 and old_rank != 1:
                highlights.append(f"{usernames[user_id]} just took over 1st place!")

    return highlights


# --- Per-game news (self-contained feature — see ENABLE_GAME_NEWS in settings.py) ---

@login_required
def game_news(request, game_id):
    """GET /game/<game_id>/news/ — HTML fragment of ESPN news for a game's two teams."""
    if not settings.ENABLE_GAME_NEWS:
        raise Http404

    game = get_object_or_404(Game, pk=game_id)
    articles = fetch_game_news(game.home_team, game.away_team)
    return render(request, 'pool/_game_news.html', {'game': game, 'articles': articles})
