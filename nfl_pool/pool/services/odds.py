"""
The Odds API client — https://the-odds-api.com
Free tier: 500 requests/month. One daily morning pull uses ~1/day = ~30/month.
"""
import requests
from datetime import datetime, timedelta
from django.conf import settings

ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"


def fetch_odds() -> list:
    """
    Fetch current NFL moneyline and spread odds, averaged across US bookmakers.
    Returns the raw list of game objects from The Odds API.
    """
    response = requests.get(
        ODDS_API_URL,
        params={
            "apiKey": settings.ODDS_API_KEY,
            "regions": "us",
            "markets": "h2h,spreads",
            "oddsFormat": "american",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def parse_game_odds(game_data: dict) -> dict:
    """
    Average moneyline and spread across all available bookmakers for one game.

    Returns:
    {
        home_team (str),
        away_team (str),
        commence_time (str, ISO),
        home_moneyline (int | None),
        away_moneyline (int | None),
        home_spread (float | None),   # negative = home favored
    }
    """
    home_team = game_data["home_team"]
    away_team = game_data["away_team"]

    h2h_home, h2h_away, spreads_home = [], [], []

    for bookmaker in game_data.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market["key"] == "h2h":
                for outcome in market["outcomes"]:
                    if outcome["name"] == home_team:
                        h2h_home.append(outcome["price"])
                    elif outcome["name"] == away_team:
                        h2h_away.append(outcome["price"])
            elif market["key"] == "spreads":
                for outcome in market["outcomes"]:
                    if outcome["name"] == home_team:
                        spreads_home.append(outcome["point"])

    return {
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": game_data["commence_time"],
        "home_moneyline": round(sum(h2h_home) / len(h2h_home)) if h2h_home else None,
        "away_moneyline": round(sum(h2h_away) / len(h2h_away)) if h2h_away else None,
        "home_spread": round(sum(spreads_home) / len(spreads_home), 1) if spreads_home else None,
    }


def match_game_to_db(home_team: str, away_team: str, commence_time: str):
    """
    Find a Game in the DB matching team names and kickoff (±2 hours).
    The Odds API uses full team names matching ESPN's displayName.
    """
    from pool.models import Game

    kickoff = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    return Game.objects.filter(
        home_team__iexact=home_team,
        away_team__iexact=away_team,
        kickoff__range=(kickoff - timedelta(hours=2), kickoff + timedelta(hours=2)),
    ).first()
