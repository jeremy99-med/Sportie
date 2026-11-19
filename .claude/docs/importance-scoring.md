# Game importance score

Implementation:
- `backend/apps/community_game_ranker/services/scoring.py`: pure factor functions, `WEIGHTS`, and the
  combiner. No DB access.
- `services/ranking.py`: gathers each game's inputs from the DB (`game_factors`), saves the score
  (`score_game`, `score_day`), and serves the ranked query (`ranked_games`). A "day" runs midnight to
  midnight US Eastern, the same calendar the providers use.
- `manage.py ingest_ranker` ingests a day and then scores it.
- `services/ai_assist.py`: the hourly Claude ranking that feeds the `ai` factor (see below).

## Shape

Each factor is a **pure function** that returns a value in `[0, 1]`. The final score is a
weighted sum per sport, scaled to `0-100`. The per-factor values go into
`GameLog.score_breakdown` so the UI can explain the ranking. Other keys in the breakdown are kept
when a game is re-scored.

```text
importance = 100 * sum(weight[sport][f] * factor_f(game) for f in used) / sum(weight[sport][f] for f in used)
```

`used` is every factor, except that `ai` is dropped (weight and all) while the game has no AI
rank. Other missing factors count as 0.

## Factors

| Factor | Input | Rule |
|---|---|---|
| `playoff` | TeamStanding for both teams | Each team's stakes are `1 - abs(conference_rank - cutoff) / race_width`, averaged over both teams. That is scaled by `0.4 + 0.6 * season_progress`, so the factor matters more late in the season. Cutoffs are NFL 7, NBA 8 (the middle of the 6-10 play-in), NHL 8, MLB 6. A team with no standing counts as 0.5. |
| `star_injury` | Injury rows for `is_star` players on either team | `1 - sum(severity) / stars_total`. Severity is out 1.0, doubtful 0.75, questionable 0.5. It's 1.0 when nobody is injured or neither team has stars. **Decided:** a missing star *lowers* the score. Trial-key injuries count as questionable (`status_estimated`). |
| `weather` | WeatherCondition | **Always 0 for NBA and NHL**, for indoor stadiums, and when there's no forecast. Snow or sleet gives 1 (any forecast `snow_cm` > 0, or the condition text mentions snow, sleet, blizzard or ice pellets). Otherwise it's the larger of `precip_mm / 5` and `(wind_kph - 15) / 35`. |
| `momentum` | Both teams' last 5 final GameLog rows | Average win rate (a tie counts 0.5). A team with no finished games counts as 0.5. |
| `rivalry` | `Rivalry.intensity / 5` | 0 when no rivalry row exists. |
| `status` | GameLog.status | in_progress 1.0, scheduled 0.8, delayed 0.6, final 0.3, postponed 0. |
| `ai` | AIRanking (rank among the day's games) | `1 - (rank - 1) / (ranked_count - 1)`: 1 for Claude's top game, 0 for its last, 1 when it's the only game. **None** (left out of the score) until the game is ranked. |
| `community` | Net votes | `0.5 + 0.5 * net / (abs(net) + 10)`: 0.5 with no votes, 0.75 at +10, 0.25 at -10. **Decided:** votes are a weighted factor *and* break ties (see Sorting). |

## Weights per sport (starting values, approved 2026-10-27; tune after the demo data is in)

| Factor | NFL | NBA | NHL | MLB |
|---|---|---|---|---|
| playoff | .30 | .30 | .30 | .25 |
| star_injury | .15 | .25 | .15 | .15 |
| weather | .10 | 0 | 0 | .15 |
| momentum | .15 | .15 | .20 | .15 |
| rivalry | .15 | .10 | .15 | .15 |
| status | .05 | .05 | .05 | .05 |
| community | .10 | .10 | .10 | .10 |
| ai | .15 | .15 | .15 | .15 |

`ai` was approved on 2026-11-19 as an addition on top of the original weights, so the other
factors keep their proportions. With an AI rank, it is .15 / 1.15 ≈ 13% of the score.

## AI ranking (`services/ai_assist.py`, `integrations/claude.py`)

- `refresh_ranker` calls `ai_assist.rank_day(today)` after every 5-minute ingest pass. It acts at
  most once per `AI_INTERVAL` (58 minutes, so about every 12th pass). `--no-ai` turns it off, and
  it's skipped when `ANTHROPIC_API_KEY` is empty. `manage.py rank_ai [--date]` runs it right away.
- Claude gets one JSON summary per game: the seven formula subscores, the formula score without
  `ai` (`scoring.base_importance`), and the facts behind them (records and conference ranks,
  injured stars by name and status, forecast, rivalry, last five results, live score, net votes).
  It ranks every game of the day (NFL and NBA together) and writes a one-to-three-sentence reason
  for each.
- **No feedback loop:** the summary never includes the `ai` factor or Claude's earlier rank or
  reason. Each hourly rank depends only on the other factors.
- **Only re-ranks on change:** the summaries are hashed. When the hash matches the last good
  run's, Claude isn't called and the ranks stay. A new injury (e.g. a star ruled out), a status
  or live-score change, a forecast update, or new votes all change the hash.
- A failed call keeps the previous ranks and tries again next interval. The last run per day is in
  ExternalAPIMetadata (`anthropic` / `rank_day`).
- Model: `claude-opus-5-5` (`integrations/claude.MODEL`), effort `medium`, JSON-schema output, and
  server-side refusal fallback (`fallbacks: "default"`). The answer is checked: every game exactly
  once and a reason for each, or the run fails.

Keep the weights in one dict, `WEIGHTS: dict[str, dict[str, float]]`, in `scoring.py`.
Don't scatter them across modules.

## Sorting

`ranked_games()` sorts by `importance_score` descending (unscored games last), then by net
community votes descending, then by start time. The required tests check that the high-stakes game
comes first, the low-stakes game comes last, and that votes break ties (`tests/test_ranking.py`).

## Known data limits

- Early in the season the playoff factor is small for every game, by design.
- `ingest_ranker --backfill` loads 14 days of finished games. That's about 2 NFL games per team, so
  NFL momentum rests on few results until more weeks are ingested.
- With a SportsData.io trial key, NFL score values may be scrambled. Checked live on 2026-10-27: the
  winners in the backfilled games matched each team's standings record.
