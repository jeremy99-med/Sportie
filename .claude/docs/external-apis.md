# External APIs (Community Game Ranker)

The clients live in `backend/apps/community_game_ranker/integrations/`, one module per provider.
Verified against the providers' official docs on 2026-10-27 (WebFetch). Items marked **UNCONFIRMED**
could not be read from the docs and must be checked with a real key before relying on them.
Scope: NBA and NFL only.

| Provider | Used for | Env var | Base URL | Auth |
|---|---|---|---|---|
| balldontlie | NBA games, teams, players | `BALLDONTLIE_API_KEY` | `https://api.balldontlie.io/v1` (some advanced endpoints use `/nba/v1`, `/nba/v2`) | Header `Authorization: <key>` (no `Bearer`) |
| SportsData.io | NFL games/injuries/standings/rosters/stats; NBA injuries/standings/rosters/stats | `SPORTSDATA_NFL_API_KEY`, `SPORTSDATA_NBA_API_KEY` (one key per sport; separate subscriptions per league) | `https://api.sportsdata.io/v3/{nfl\|nba}/{feed}/json/{Endpoint}` (feed = `scores`, `stats`, `projections`, `odds`) | Header `Ocp-Apim-Subscription-Key: <key>` (or `?key=`; we use the header so keys stay out of URLs/logs) |
| WeatherAPI.com | Stadium forecast by lat/lon | `WEATHERAPI_KEY` | `https://api.weatherapi.com/v1` | Query param `key` (the only documented method) |
| Anthropic | Playoff-implication reasoning | `ANTHROPIC_API_KEY` | Use the `claude-api` skill; never hardcode the model ID elsewhere | |

## Endpoints we use

### balldontlie (`integrations/balldontlie.py`)

Docs: [NBA API](https://docs.balldontlie.io/#nba-api), [NFL API](https://docs.balldontlie.io/#nfl-api).

| Function | Request | Status |
|---|---|---|
| `get_games(date)` / `get_games_between(start, end)` | `GET /v1/games?dates[]=YYYY-MM-DD&per_page=100` (or `start_date`, `end_date`) | Confirmed. Response `{data: [...], meta: {next_cursor, per_page}}`. Game fields: `id, date, datetime, season, status, period, time, postseason, postponed, home_team_score, visitor_team_score, home_team{id,abbreviation,...}, visitor_team{...}`. Docs (2026-10-28): before tip-off `status` is the start time (e.g. `"7:00 pm ET"`); finished games show `"Final"`. Samples also carry a `status_state` field; `"final"` there takes precedence over `status`. The in-progress value is still UNCONFIRMED (seen: a period string). |
| `get_teams()` | `GET /v1/teams` | Confirmed. `data[]`: `id, conference, division, city, name, full_name, abbreviation`. |
| `get_players(team_id)` | `GET /v1/players?team_ids[]=<id>&per_page=100` | Confirmed. `data[]`: `id, first_name, last_name, position, team{...}`. |
| `get_standings(season)` | `GET /v1/standings?season=YYYY` | Endpoint confirmed, **GOAT tier only**. Not used by ingest. |
| `get_season_averages(season, player_ids)` | `GET /v1/season_averages/general?season=&season_type=regular&type=base&player_ids[]=` | Route `/v1/season_averages/{category}` with a `type` query param is confirmed (the docs' text example uses `/nba/v1/` instead). Player stat keys `pts/reb/ast/gp` are UNCONFIRMED: they appear only in the team season-averages example. **GOAT tier only**. Not used by ingest. |

Pagination is cursor based (`per_page` max 100, `?cursor=<next_cursor>`). On HTTP 429 the client waits
`Retry-After` seconds (default 12, max 60) and retries once. A second 429 raises
`BalldontlieRateLimitError`, a `BalldontlieError` subclass, so ingest records it like any other
provider error.

### SportsData.io (`integrations/sportsdata.py`)

Docs: <https://sportsdata.io/developers/api-documentation/nfl> and
<https://sportsdata.io/developers/api-documentation/nba>. Check these first when resolving the
UNCONFIRMED items below. Field names, status values and the trial `Scrambled` flag are in the data
dictionaries: <https://sportsdata.io/developers/data-dictionary/nfl> and
<https://sportsdata.io/developers/data-dictionary/nba>. Rechecked against all four pages on 2026-10-28.

Dates in paths use `YYYY-MON-DD` (e.g. `2026-OCT-27`). Season is the year, with an optional suffix
(`2026REG`, `2026POST`, `2026PRE`).

| Function | NFL | NBA | Status |
|---|---|---|---|
| `get_scores(league, date, final_only)` | `scores/json/ScoresByDate/{date}` (`ScoresByDateFinal`) | `scores/json/GamesByDate/{date}` (`GamesByDateFinal`) | Paths confirmed |
| `get_schedule(league, season)` | `scores/json/Schedules/{season}` | `scores/json/Games/{season}` | Paths confirmed |
| `get_injuries(league, season_code, week)` | `stats/json/Injuries/{season}/{week}` (e.g. `2026REG`, `5`) | `projections/json/InjuredPlayers` | Paths confirmed |
| `get_standings(league, season)` | `scores/json/Standings/{season}` | `scores/json/Standings/{season}` | Paths confirmed. Fields confirmed: NFL `Team, Wins, Losses, Ties, ConferenceRank`; NBA `Key, Wins, Losses, ConferenceRank, GamesBack` |
| `get_players(league)` | `scores/json/PlayersByAvailable` | `scores/json/PlayersActiveBasic` | Paths confirmed |
| `get_player_season_stats(league, season)` | `stats/json/PlayerSeasonStats/{season}` | `stats/json/PlayerSeasonStats/{season}` | Paths confirmed. Fields confirmed: NFL `FantasyPoints`; NBA `Games, Points, Rebounds, Assists` |
| `get_teams(league)` | `scores/json/Teams` (active; `AllTeams` includes inactive) | `scores/json/teams` (active; `AllTeams` includes inactive) | Paths confirmed |

Game `Status` values for NBA are confirmed from the data dictionary: `Scheduled, InProgress, Final,
F/OT, Suspended, Postponed, Delayed, Canceled, Forfeit, NotNecessary`. The NFL dictionary links to a
separate game-status guide instead of listing them, so assume the same set. The mapping lives in
`sportsdata._STATUS_MAP`, and unknown values fall back to `scheduled`. `NotNecessary` (an unneeded
playoff game) is **not mapped yet**, so it currently shows as scheduled.

**Season numbering (confirmed live 2026-10-27):** SportsData labels an NBA season by its ending year
(our 2026 -> 2027, see `_api_season`) and an NFL season by its start year. Our `GameLog.season` is
always the start year.

### WeatherAPI (`integrations/weatherapi.py`)

Docs: [Request](https://www.weatherapi.com/docs/request/),
[Request parameters](https://www.weatherapi.com/docs/request-parameters/),
[Location object](https://www.weatherapi.com/docs/location-object/).

`GET /v1/forecast.json?key=<key>&q=<lat>,<lon>&days=3&aqi=no&alerts=no`. Response:
`forecast.forecastday[].hour[]` with `time_epoch, temp_c, precip_mm, snow_cm, wind_kph, condition.text`
(confirmed). All but `time_epoch` are returned and stored on `WeatherCondition`; hours without a numeric
`time_epoch` are skipped. We pick the hour closest to kickoff by `time_epoch`, so no timezone handling is needed.
Errors are HTTP 4xx, and the body "contains error message including error code"
([error codes](https://www.weatherapi.com/docs/error-codes/)). The docs give no JSON example, so the
body shape `{"error": {"code", "message"}}` is still UNCONFIRMED and the client falls back to raw text.
Codes we can hit (confirmed): 401/1002 no key, 400/1003 missing `q`, 400/1005 invalid request URL,
400/1006 no location found, 401/2006 invalid key, 403/2007 monthly quota exceeded, 403/2008 key
disabled, 403/2009 plan lacks access, 400/9999 internal error. Codes 1010-1013 (solar/agriculture) and
9000-9001 (bulk) don't apply to us.

## Free tiers and rate limits

| Provider | Finding | Status |
|---|---|---|
| balldontlie | Free: **5 requests/min**; ALL-STAR 60/min; GOAT 600/min. Free tier includes only **Teams, Players, Games**. Injuries and game player stats need ALL-STAR+; **Standings and Season Averages need GOAT**. So NBA standings, injuries and player stats come from SportsData.io. | Confirmed |
| SportsData.io | The free-trial page only advertises soccer (UEFA Champions League) coverage. NBA/NFL data needs a subscription or the Replay option, so test a real NBA/NFL key before the demo. Recommended call intervals per endpoint: standings 5 min, injuries 5 min, player season stats 15 min, live scores a few seconds. No hard quota published. | Confirmed (trial scope); hard limits UNCONFIRMED |
| SportsData.io trial data | Trial keys return **scrambled values in some fields**. From the data dictionary (`Scrambled` column): Injury `Status`, `BodyPart`, `Practice`, `DeclaredInactive` are scrambled; Score `HomeScore`/`AwayScore` are scrambled; `Status`, `DateTime`, `Week` and team abbreviations are not. Standings: `Wins/Losses/GamesBack` are real, but **NBA `ConferenceRank` is scrambled**. Player season stats (rechecked 2026-10-28): **NFL `FantasyPoints` and NBA `Points/Rebounds/Assists` are scrambled**; NBA `Games` is not. Consequence: with a trial key, injuries, scores, NBA conference rank and the star-picking stats are not trustworthy. Use a paid key for real ranking. | **Confirmed live 2026-10-27 with our trial keys:** every injury row has `Status`/`InjuryStatus` = `"Scrambled"` (95 NBA, 447 NFL rows); see "Trial-key injuries" below for how the client handles them. NBA scores are scrambled (e.g. 29-31 where balldontlie shows 103-110). NFL scores look plausible but can't be trusted. Schedules and rosters are real. Standings and player season stats looked plausible live, but the dictionary marks the fields above as scrambled, so don't trust them on a trial key. |
| WeatherAPI | Free: 100K calls/month, 3 forecast days, 1 day of history, no per-minute limit published. Quota resets at 00:00 UTC on the 1st. Only outdoor games within 3 days of now get weather. | Confirmed |

Quota strategy: every call goes through `services/ingest.cached_call` (table `ExternalAPIMetadata`).
TTLs: live day data 5 min (today and yesterday by US Eastern date), standings 30 min, finished
backfill 12 h, rosters/stats 24 h, weather 3 h.
balldontlie at 5/min: `ingest_day` makes 1 NBA games call per day, `backfill` makes 1 ranged call.
Do not loop `get_players(team_id)` over all 30 teams on a free key (6 min of quota); rosters use
SportsData instead.

## Client pattern

```python
# integrations/weatherapi.py
import os
import requests

TIMEOUT = 10

class WeatherAPIError(Exception): ...

def get_forecast(lat: float, lon: float, when) -> dict:
    """Return a normalized dict: {temp_c, precip_mm, wind_kph, condition_text}."""
    resp = requests.get(..., params={"key": os.environ["WEATHERAPI_KEY"], ...}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise WeatherAPIError(resp.status_code, resp.text[:200])
    return _normalize(resp.json())
```

- Always set a `timeout`. Raise a provider-specific exception on non-200 responses and on network
  errors (`requests.RequestException`) and a missing key.
- Return **normalized, JSON-serializable** dicts (datetimes as ISO strings) so `cached_call` can store
  them in `ExternalAPIMetadata.response`. Code outside the client never sees raw provider JSON.
- Team references are `{"id": <provider team id or None>, "abbreviation": "<provider abbr>"}`.
  Provider abbreviations differ from ours; `services/ingest.TEAM_ALIASES` maps them.
- The client does no ORM work. Caching and upserts go in `services/ingest.py`.
- Read keys from `os.environ`, and add each key to `backend/.env.example`.

## Testing

- Patch `requests.get` with recorded, sanitized sample payloads saved in
  `tests/fixtures/<provider>/*.json` (no keys, no real user data).
- Each provider needs one success test (normalized output) and one invalid-request test
  (raises the provider exception).
- The fixtures were written from the documented response shapes, not recorded from live calls (no keys
  yet). Re-record them once real keys exist.

## Player names across feeds

The SportsData stats feed abbreviates NFL names (`J.Allen`), while the roster feed has full names
(`Josh Allen`), and NBA names keep their accents (`Luka Dončić`). Always match players by
provider id (`Player.external_ids["sportsdata_<league>"]`), never by name. `refresh_stars` maps stat
rows to roster names by id, so `sync_rosters` has to run first. Use the provider's spelling
in `seed/stars.json`.

## Trial-key injuries

On a trial key, `get_injuries` keeps rows whose status is `"Scrambled"` (the player, team and
`InjuryStartDate` are real). It records them as `questionable` with `status_estimated=True` and drops
the scrambled body-part and notes text. Body-part and notes text is dropped whenever the status is estimated, even if it isn't the
literal word `Scrambled`. Real statuses (`Out`, `Doubtful`, ...) are used as-is. Rows with
no team can't match a game and are skipped. With a paid key every row is real and nothing is estimated.
