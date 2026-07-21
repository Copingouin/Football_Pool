import random
from django.contrib import admin
from .models import Season, Week, Game, Pick, Score, ScoreHistory, SeasonParticipant
from .services.espn import sync_week_games


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('year', 'is_test')
    list_editable = ('is_test',)


@admin.register(SeasonParticipant)
class SeasonParticipantAdmin(admin.ModelAdmin):
    list_display = ('user', 'season', 'joined_at')
    list_filter = ('season',)
    raw_id_fields = ('user',)


class GameInline(admin.TabularInline):
    model = Game
    extra = 1
    fields = ('away_team', 'home_team', 'kickoff', 'winner')


@admin.action(description='Simulate results (test seasons only)')
def simulate_results(modeladmin, request, queryset):
    for week in queryset:
        if not week.season.is_test:
            modeladmin.message_user(
                request,
                f'{week}: skipped — not a test season.',
                level='warning',
            )
            continue
        count = 0
        for game in week.games.filter(winner__isnull=True):
            game.winner = random.choice([Game.WINNER_HOME, Game.WINNER_AWAY])
            game.save()
            count += 1
        modeladmin.message_user(request, f'{week}: simulated {count} game(s).')


@admin.action(description='Resync schedule from ESPN (picks up reschedules/cancellations)')
def resync_from_espn(modeladmin, request, queryset):
    for week in queryset:
        try:
            count = sync_week_games(week)
        except Exception as exc:
            modeladmin.message_user(
                request, f'{week}: FAILED to resync ({exc})', level='error'
            )
            continue
        modeladmin.message_user(
            request, f'{week}: resynced {count} game(s) from ESPN.'
        )


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status', 'computed_status')
    list_filter = ('season', 'status')
    list_editable = ('status',)
    inlines = [GameInline]
    actions = [simulate_results, resync_from_espn]

    @admin.display(description='Computed status (what players see)')
    def computed_status(self, obj):
        return obj.display_status.capitalize()


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'week', 'kickoff', 'winner', 'is_locked')
    list_filter = ('week__season', 'week')
    list_editable = ('winner',)

    @admin.display(boolean=True, description='Locked')
    def is_locked(self, obj):
        return obj.is_locked


@admin.register(Pick)
class PickAdmin(admin.ModelAdmin):
    list_display = ('user', 'week', 'game', 'predicted_winner', 'confidence_points', 'locked')
    list_filter = ('week', 'locked')
    raw_id_fields = ('user', 'game')


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ('user', 'week', 'points')
    list_filter = ('week',)


@admin.register(ScoreHistory)
class ScoreHistoryAdmin(admin.ModelAdmin):
    """Read-only audit log — one row per score recalculation, never overwritten."""
    list_display = ('user', 'week', 'points', 'recorded_at')
    list_filter = ('week__season', 'week', 'user')
    date_hierarchy = 'recorded_at'
    raw_id_fields = ('user',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
