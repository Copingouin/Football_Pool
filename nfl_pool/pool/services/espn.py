"""
ESPN unofficial scoreboard API client.
No API key required. Returns schedule and game results for any NFL regular season week.
"""
import requests
from datetime import datetime

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
)
NFL_REGULAR_SEASON_WEEKS = 18


def fetch_week(year: int, week: int) -> dict:
    """
    Fetch raw ESPN scoreboard JSON for a specific regular-season week.
    seasontype=2 means regular season (1=preseason, 3=playoffs).
    """
    response = requests.get(
        ESPN_SCOREBOARD_URL,
        params={"dates": year, "seasontype": 2, "week": week},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def parse_games(data: dict) -> list:
    """
    Convert ESPN scoreboard JSON into a list of plain dicts:
    {
        espn_id (str),
        home_team (str),
        away_team (str),
        kickoff (timezone-aware datetime),
        winner (None | 'home' | 'away'),
    }
    """
    games = []

    for event in data.get("events", []):
        try:
            competition = event["competitions"][0]

            home = None
            away = None
            for competitor in competition["competitors"]:
                entry = {
                    "name": competitor["team"]["displayName"],
                    "winner": competitor.get("winner", False),
                }
                if competitor["homeAway"] == "home":
                    home = entry
                else:
                    away = entry

            if not home or not away:
                continue

            status = competition.get("status", {}).get("type", {})
            completed = status.get("completed", False)

            winner = None
            if completed:
                if home["winner"]:
                    winner = "home"
                elif away["winner"]:
                    winner = "away"

            # ESPN dates are UTC ISO strings ending in Z
            kickoff_str = event.get("date") or competition.get("date", "")
            kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))

            games.append({
                "espn_id": str(event["id"]),
                "home_team": home["name"],
                "away_team": away["name"],
                "kickoff": kickoff,
                "winner": winner,
            })
        except (KeyError, IndexError, TypeError, ValueError):
            # One malformed event (e.g. ESPN mid-update) shouldn't drop
            # the rest of the week's games.
            continue

    return games


def upsert_week_games(week, games: list) -> int:
    """Upsert already-fetched/parsed ESPN game dicts into DB Game rows for this week."""
    from pool.models import Game

    for g in games:
        Game.objects.update_or_create(
            espn_id=g["espn_id"],
            defaults={
                "week": week,
                "home_team": g["home_team"],
                "away_team": g["away_team"],
                "kickoff": g["kickoff"],
                "winner": g["winner"],
            },
        )

    return len(games)


def sync_week_games(week) -> int:
    """
    Fetch a single week's games from ESPN and upsert them into the DB.
    Picks up reschedules (weather delays, flex scheduling, etc.) for a week
    that already exists — used by the admin's "Resync from ESPN" action.
    """
    data = fetch_week(week.season.year, week.week_number)
    games = parse_games(data)
    return upsert_week_games(week, games)
