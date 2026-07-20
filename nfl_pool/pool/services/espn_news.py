"""
ESPN unofficial "news" API client — powers the per-game news popup.
No API key required. Self-contained: safe to delete this file, its view,
its URL entry, and its template button as a unit if the feature doesn't
pan out (see ENABLE_GAME_NEWS in settings.py for a runtime kill switch).
"""
import requests

NFL_NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"


def fetch_game_news(home_team: str, away_team: str, limit: int = 5) -> list:
    """
    Fetch general NFL news and filter down to articles mentioning either team.
    Returns a list of dicts: {headline, description, link, image, published}.
    Returns [] on any request/parsing failure — this is a nice-to-have, never
    something a caller should have to handle as an error.
    """
    try:
        response = requests.get(NFL_NEWS_URL, params={"limit": 50}, timeout=6)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return []

    articles = []
    for item in data.get("articles", []):
        headline = item.get("headline") or ""
        description = item.get("description") or ""

        team_names = {
            c.get("description", "")
            for c in item.get("categories", [])
            if c.get("type") == "team"
        }
        haystack = f"{headline} {description}"

        mentions_home = home_team in team_names or home_team in haystack
        mentions_away = away_team in team_names or away_team in haystack
        if not (mentions_home or mentions_away):
            continue

        images = item.get("images") or [{}]
        articles.append({
            "headline": headline,
            "description": description,
            "link": (item.get("links") or {}).get("web", {}).get("href"),
            "image": images[0].get("url"),
            "published": item.get("published"),
        })

        if len(articles) >= limit:
            break

    return articles
