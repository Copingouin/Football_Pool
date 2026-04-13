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

    return games
