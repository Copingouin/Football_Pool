from django.contrib import admin
from django.utils import timezone
from .models import Season, Week, Game, Pick, Score


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('year',)


class GameInline(admin.TabularInline):
    model = Game
    extra = 1
    fields = ('away_team', 'home_team', 'kickoff', 'winner')


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status')
    list_filter = ('season', 'status')
    list_editable = ('status',)
    inlines = [GameInline]


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
