# NFL Confidence Pool

A web app for running a weekly NFL confidence pool with friends — pick winners, rank your
confidence in each pick, and watch the standings update automatically as games are decided.

Live at: https://footballpool-production-6276.up.railway.app

## How the pool works

Each week, every player predicts the winner of every game and assigns each pick a
**confidence point** value from 1 up to the number of games that week — using every
number exactly once, with your most confident pick getting the highest number.

- **Scoring:** guess a winner correctly and you earn the confidence points you put on
  that pick. Guess wrong and you earn zero for that game. Your week's score is the sum
  across all games; your season score is the sum across all weeks.
- **Locking:** once a game kicks off, that pick locks and can no longer be changed.
  A countdown on the picks page always shows the time left before your next pick locks.
- **Missed picks:** if a game kicks off before you ever save a pick for it, that game
  is scored as a forfeit (zero points) rather than blocking you from the rest of the week.
- **Week gating:** you can't submit picks for a week until the previous week is fully
  decided (every game has a winner), so the board can't get too far ahead of results.
- **Results:** each week's results page is only visible once your own picks for that
  week are locked, to keep everyone picking blind.

## Features

- Season and weekly standings, with a per-season leaderboard and a cumulative-points
  trend chart across the season
- Head-to-head matrix — how many weeks each player has outscored each other player
- "Upset of the week" — the week's biggest underdog win and who correctly called it
  (via [The Odds API](https://the-odds-api.com))
- A highlights banner surfacing busted high-confidence picks and standings swaps
- Live team schedules and results synced from ESPN's public scoreboard API
- Per-game news headlines pulled from ESPN
- Player customization: a favorite-team icon and a short status phrase shown next to
  your name on the leaderboard
- Test seasons with simulated results, for trying the app out without waiting on a
  real NFL week

## Tech stack

Django 6, PostgreSQL (SQLite for local dev), gunicorn + WhiteNoise, deployed on Railway.

## Running it locally

```
cd nfl_pool
python -m venv ../.venv
../.venv/Scripts/activate    # or source ../.venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env         # fill in a SECRET_KEY; everything else has a local default
python manage.py migrate
python manage.py runserver
```

Then visit `http://127.0.0.1:8000` and `http://127.0.0.1:8000/admin` to set up a season,
weeks, and games.

## Credits

This entire project — every line of code, every template, every deploy fix — was built
by [Claude](https://claude.com) (Anthropic), via [Claude Code](https://claude.com/claude-code),
working directly with the project owner from a blank repo. No code was hand-written.
