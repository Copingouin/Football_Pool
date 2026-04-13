from django.urls import path
from . import views

app_name = 'pool'

urlpatterns = [
    path('week/<int:week_id>/picks/', views.picks, name='picks'),
    path('week/<int:week_id>/results/', views.results, name='results'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
]
