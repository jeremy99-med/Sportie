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

| Function | Request | Status |
|---|---|---|
| `get_games(date)` / `get_games_between(start, end)` | `GET /v1/games?dates[]=YYYY-MM-DD&per_page=100` (or `start_date`, `end_date`) | Confirmed. Response `{data: [...], meta: {next_cursor, per_page}}`. Game fields: `id, date, datetime, season, status, period, time, postseason, postponed, home_team_score, visitor_team_score, home_team{id,abbreviation,...}, visitor_team{...}`. Value set of `status` is UNCONFIRMED (seen: `"Final"`, a tip-off time string, a period string). |
| `get_teams()` | `GET /v1/teams` | Confirmed. `data[]`: `id, conference, division, city, name, full_name, abbreviation`. |
| `get_players(team_id)` | `GET /v1/players?team_ids[]=<id>&per_page=100` | Confirmed. `data[]`: `id, first_name, last_name, position, team{...}`. |
| `get_standings(season)` | `GET /v1/standings?season=YYYY` | Endpoint confirmed, **GOAT tier only**. Not used by ingest. |
| `get_season_averages(season, player_ids)` | `GET /v1/season_averages/general?season=&season_type=regular&type=base&player_ids[]=` | Path/category UNCONFIRMED (docs show both `/v1/` and `/nba/v1/`; stat key names `pts/reb/ast/gp` assumed). **GOAT tier only**. Not used by ingest. |

Pagination is cursor based (`per_page` max 100, `?cursor=<next_cursor>`).

### SportsData.io (`integrations/sportsdata.py`)

Dates in paths use `YYYY-MON-DD` (e.g. `2026-OCT-27`). Season is the year, with an optional suffix
(`2026REG`, `2026POST`, `2026PRE`).

| Function | NFL | NBA | Status |
|---|---|---|---|
| `get_scores(league, date, final_only)` | `scores/json/ScoresByDate/{date}` (`ScoresByDateFinal`) | `scores/json/GamesByDate/{date}` (`GamesByDateFinal`) | Paths confirmed |
| `get_schedule(league, season)` | `scores/json/Schedules/{season}` | `scores/json/Games/{season}` | NFL confirmed; NBA path UNCONFIRMED |
| `get_injuries(league, season_code, week)` | `stats/json/Injuries/{season}/{week}` (e.g. `2026REG`, `5`) | `projections/json/InjuredPlayers` | Paths confirmed |
| `get_standings(league, season)` | `scores/json/Standings/{season}` | `scores/json/Standings/{season}` | Paths confirmed; field names (`Team`/`Key`, `Wins`, `Losses`, `Ties`, `ConferenceRank`, `GamesBack`) partly confirmed |
| `get_players(league)` | `scores/json/PlayersByAvailable` | `scores/json/PlayersActiveBasic` | Paths confirmed |
| `get_player_season_stats(league, season)` | `stats/json/PlayerSeasonStats/{season}` | `stats/json/PlayerSeasonStats/{season}` | Paths confirmed; NFL field `FantasyPoints` confirmed to exist; NBA fields `Games, Points, Rebounds, Assists` UNCONFIRMED |
| `get_teams(league)` | `scores/json/Teams` | `scores/json/teams` | UNCONFIRMED (standard SportsData path, not on the pages we could read) |

Game `Status` values (`Scheduled, InProgress, Final, F/OT, Suspended, Postponed, Canceled, Delayed,
Forfeit`) are UNCONFIRMED; the docs page does not list them. The mapping lives in
`sportsdata._STATUS_MAP`; unknown values fall back to `scheduled`.

**Season numbering (confirmed live 2026-10-27):** SportsData labels an NBA season by its ending year
(our 2026 -> 2027, see `_api_season`) and an NFL season by its start year. Our `GameLog.season` is
always the start year.

### WeatherAPI (`integrations/weatherapi.py`)

`GET /v1/forecast.json?key=<key>&q=<lat>,<lon>&days=3&aqi=no&alerts=no`. Response:
`forecast.forecastday[].hour[]` with `time_epoch, temp_c, precip_mm, snow_cm, wind_kph, condition.text`
(confirmed). We pick the hour closest to kickoff by `time_epoch`, so no timezone handling is needed.
Errors are HTTP 4xx with a JSON `error` object (body shape `{"error": {"code", "message"}}` is
UNCONFIRMED in the docs; the client falls back to raw text). Codes: 401/1002 no key, 401/2006 invalid
key, 400/1006 no location, 400/1003 missing `q`, 403/2007 quota exceeded, 403/2008 key disabled,
403/2009 plan lacks access.

## Free tiers and rate limits

| Provider | Finding | Status |
|---|---|---|
| balldontlie | Free: **5 requests/min**; ALL-STAR 60/min; GOAT 600/min. Free tier includes only **Teams, Players, Games**. Injuries and game player stats need ALL-STAR+; **Standings and Season Averages need GOAT**. So NBA standings, injuries and player stats come from SportsData.io. | Confirmed |
| SportsData.io | The free-trial page only advertises soccer (UEFA Champions League) coverage. NBA/NFL data needs a subscription or the Replay option, so test a real NBA/NFL key before the demo. Recommended call intervals per endpoint: standings 5 min, injuries 5 min, player season stats 15 min, live scores a few seconds. No hard quota published. | Confirmed (trial scope); hard limits UNCONFIRMED |
| SportsData.io trial data | Trial keys return **scrambled values in some fields**. From the data dictionary (`Scrambled` column): Injury `Status`, `BodyPart`, `Practice`, `DeclaredInactive` are scrambled; Score `HomeScore`/`AwayScore` are scrambled; `Status`, `DateTime`, `Week`, team abbreviations and Standing `Wins/Losses/Ties/ConferenceRank` are not. The extraction for `PlayerSeason.FantasyPoints` gave conflicting answers across tables, treat it as possibly scrambled. Consequence: with a trial key, injuries, scores and (probably) NFL fantasy points are not trustworthy. Use a paid key for real ranking. | **Confirmed live 2026-10-27 with our trial keys:** every injury row has `Status`/`InjuryStatus` = `"Scrambled"` (95 NBA, 447 NFL rows), so the client drops them all. NBA scores are scrambled (e.g. 29-31 where balldontlie shows 103-110). NFL scores look plausible but can't be trusted. Standings, schedules, rosters, and player season stats look real. |
| WeatherAPI | Free: 100K calls/month, 3 forecast days, 1 day of history, no per-minute limit published. Quota resets at 00:00 UTC on the 1st. Only outdoor games within 3 days of now get weather. | Confirmed |

Quota strategy: every call goes through `services/ingest.cached_call` (table `ExternalAPIMetadata`).
TTLs: live day data 5 min, finished backfill 12 h, rosters/stats 24 h, weather 3 h.
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
the scrambled body-part and notes text. Real statuses (`Out`, `Doubtful`, ...) are used as-is. Rows with
no team can't match a game and are skipped. With a paid key every row is real and nothing is estimated.
