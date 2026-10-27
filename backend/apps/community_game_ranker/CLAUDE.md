# Community Game Ranker (owner: Jeremy)

Ranks the day's NFL, NBA, NHL, and MLB games so fans know which ones to watch.

## Layout

- `models.py`: Sport, Team, Player, Stadium, TeamStanding, GameLog, Injury, WeatherCondition, Rivalry,
  ExternalAPIMetadata, CommunityVote. Full field list: `.claude/docs/data-model.md`.
- `seed/`: reference data. Sports, NBA/NFL teams, stadiums (coordinates for weather lookups),
  and rivalries load in migration `0003_seed_reference_data`, so edit the JSON and add a new
  data migration for changes. `stars.json` holds per-sport `always` / `never` star overrides (at most 5
  stars per team in total) and loads with `python manage.py seed_stars`. Computed stars come from
  `python manage.py sync_rosters` (rosters, trades, and `pick_stars` from season stats).
- `integrations/`: one module per provider (`balldontlie.py`, `sportsdata.py`, `weatherapi.py`).
  These are thin HTTP clients that return normalized dicts and never touch the ORM.
  See `.claude/docs/external-apis.md`.
- `services/`: `stars.py` (`pick_stars`, star sync with overrides), `scoring.py` (pure functions, one per factor plus a combiner),
  `ingest.py` (cached_call, ingest_day, backfill_finished, sync_rosters; the only module using both clients and the ORM; run with `python manage.py ingest_ranker --date YYYY-MM-DD [--sport NBA] [--backfill]`), `ai_assist.py` (Claude call for playoff
  implications). See `.claude/docs/importance-scoring.md`.
- `tests/`: mirrors the modules (`test_scoring.py`, `test_integrations.py`, `test_votes.py`, ...).

## Rules

- Scoring functions are pure: plain values in, a float out, no DB access. That keeps them cheap
  to unit test.
- Weather weight is 0 for NBA and NHL, which play indoors.
- Votes: one per (user, game), and the user must be logged in. Sending the same vote again
  removes it. Sending the opposite vote flips it.
- Any page that shows injuries or importance needs the gambling disclaimer
  (`.claude/docs/ethics-checklist.md`).

## Required tests (from the proposal)

Score factors: playoff, star injury, weather (NBA/NHL excluded), rivalry, momentum ·
API clients: one success and one invalid request each, for balldontlie, SportsData.io, and WeatherAPI ·
Sorting: high-stakes game first, low-stakes game last, and fan votes break ties ·
Votes: upvote, downvote, remove.
