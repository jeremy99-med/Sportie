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
- `services/`: `stars.py` (`pick_stars`, star sync with overrides), `scoring.py` (pure functions, one per factor plus a combiner), `ranking.py` (DB inputs, `score_day`, `ranked_games`),
  `ingest.py` (cached_call, ingest_day, backfill_finished, sync_rosters; the only module using both clients and the ORM; run with `python manage.py ingest_ranker --date YYYY-MM-DD [--sport NBA] [--backfill]`), `ai_assist.py` (Claude call for playoff
  implications). See `.claude/docs/importance-scoring.md`.
- `tests/`: mirrors the modules (`test_scoring.py`, `test_integrations.py`, `test_votes.py`, ...).

## API (`/api/ranker/`, auth at `/api/auth/`)

- `GET games/?date=YYYY-MM-DD&sport=NBA`: the day's games (US Eastern, default today), ranked by
  `services/ranking.ranked_games`, with breakdown, star injuries, weather, rivalry, `net_votes`, and
  `my_vote`. Public.
- `GET games/<id>/`: one game. Public.
- `POST games/<id>/vote/` with `{"value": 1 | -1}`: signed-in users only, CSRF-protected, throttled
  (`votes`, 30/min). Logic lives in `services/votes.cast_vote`, which re-scores the game.
- Auth (`apps/accounts`): `csrf/`, `me/`, `register/`, `login/`, `logout/`. These use Django
  sessions. Register and login are rate-limited per IP.
- Frontend helpers: `frontend/src/features/community-game-ranker/api.js` (games, votes) and
  `frontend/src/shared/auth/api.js`. Both go through `frontend/src/shared/http.js`, which handles
  CSRF. In dev, Vite proxies `/api` to Django (`VITE_API_TARGET`).

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
