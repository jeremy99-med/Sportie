# Community Game Ranker (owner: Jeremy)

Ranks the day's NFL, NBA, NHL, and MLB games so fans know which ones to watch.

## Layout

- `models.py`: Sport, Team, Player, Stadium, GameLog, Injury, WeatherCondition, Rivalry,
  ExternalAPIMetadata, CommunityVote. Full field list: `.claude/docs/data-model.md`.
- `integrations/`: one module per provider (`balldontlie.py`, `sportsdata.py`, `weatherapi.py`).
  These are thin HTTP clients that return normalized dicts and never touch the ORM.
  See `.claude/docs/external-apis.md`.
- `services/`: `scoring.py` (pure functions, one per factor plus a combiner),
  `ingest.py` (calls the clients and upserts models), `ai_assist.py` (Claude call for playoff
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
