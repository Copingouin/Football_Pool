from django.urls import path
from . import views

app_name = 'pool'

urlpatterns = [
    path('seasons/', views.home, name='home'),
    path('season/<int:season_id>/', views.season, name='season'),
    path('season/<int:season_id>/register/', views.register_season, name='register'),
    path('week/<int:week_id>/picks/', views.picks, name='picks'),
    path('week/<int:week_id>/results/', views.results, name='results'),
    path('game/<int:game_id>/news/', views.game_news, name='game_news'),
]
