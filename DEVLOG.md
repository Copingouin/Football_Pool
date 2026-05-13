# NFL Confidence Pool — Dev Log

## Session: 2026-05-12

### What we built

#### 1. Scoring system
- `Pick.points_earned` was already defined on the model (confidence points if correct, 0 if wrong).
- Added `recalculate_week_scores(week)` function in `pool/models.py` — iterates every user with picks in a week, sums their earned points, and upserts a `Score` row.
- Added a `post_save` signal on `Game` that calls this automatically whenever a winner is set.
- **Result:** setting a game winner in the admin now immediately updates all player scores for that week.

#### 2. Season homepage
- New view at `/seasons/` — shows a card per season with:
  - Year and TEST badge (if applicable)
  - Player's current point total
  - Whether an open week exists
  - **Join** button (first time) or **Continue** button (returning player)
- Login and register now redirect to `/seasons/` instead of the old leaderboard.

#### 3. Per-season standings page
- New view at `/season/<id>/` with two columns:
  - **Standings** — leaderboard scoped to that season only, current user highlighted
  - **Weeks** — list of all weeks with status badges (Open / Locked / Completed), player's points per week, and links to Picks / Results

#### 4. Test / fake season
- Added `is_test` boolean field to the `Season` model (migration `0003_season_is_test`).
- Test seasons are labeled with a **TEST** badge everywhere in the UI.
- Added **"Simulate results"** admin action on the Week list:
  - Randomly assigns a winner (home or away) to every game in a week that doesn't have one yet.
  - Triggers score recalculation automatically via the existing signal.
  - Refuses to run on real (non-test) seasons — shows a warning instead.

---

### How to test locally

```
cd C:\Users\cedri\Documents\Football\nfl_pool
..\FootballPool\Scripts\python.exe manage.py runserver
```

- Site: http://127.0.0.1:8000
- Admin: http://127.0.0.1:8000/admin

To create a fake season for testing:
1. Admin → Seasons → Add season, check **Is test**
2. Admin → Weeks → Add weeks and games for that season
3. Select a week → Actions → **Simulate results**
4. Scores update immediately

---

### What's next

- [ ] **API integration** — auto-populate games/schedule from ESPN (sync_schedule command exists, wire it to run automatically)
- [ ] **Auto-simulate on a schedule** — for test seasons, run simulate_results on a cron/timer so a fake season plays out on its own without manual admin action
- [ ] **Results page link from season detail** — currently only accessible via the week list; could add a direct link once a week is completed
- [ ] **Week navigation in picks/results** — prev/next week arrows so players don't have to go back to the season page each time
- [ ] **Join confirmation** — optional: show a "you're now in this season" message on first pick submission
