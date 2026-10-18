# Game importance score

Implementation: `backend/apps/community_game_ranker/services/scoring.py`.

## Shape

Each factor is a **pure function** that returns a value in `[0, 1]`. The final score is a
weighted sum per sport, scaled to `0-100`. The per-factor values go into
`GameLog.score_breakdown` so the UI can explain the ranking.

```text
importance = 100 * sum(weight[sport][f] * factor_f(game) for f in FACTORS) / sum(weight[sport].values())
```

## Factors

| Factor | Input | Notes |
|---|---|---|
| `playoff` | standings, games remaining, seeding race | Claude (`services/ai_assist.py`) can produce this from standings text. Cache the result per game per day. |
| `star_injury` | Injury rows for `is_star` players | Higher when a star on either team is out. TODO: decide whether a missing star makes a game more or less important. |
| `weather` | WeatherCondition | Only for outdoor games. **Always 0 for NBA and NHL.** Heavy rain, wind, or snow raises it (delay risk or drama). |
| `momentum` | last N results for both teams | Win streaks and hot teams score higher. |
| `rivalry` | Rivalry.intensity / 5 | 0 when no rivalry row exists. |
| `status` | GameLog.status | Delayed or postponed games get adjusted. |
| `community` | net votes, normalized | Breaks ties between games with equal objective scores. TODO: decide if it gets its own weight or only breaks ties. |

## Weights per sport (TODO: tune; placeholders only)

| Factor | NFL | NBA | NHL | MLB |
|---|---|---|---|---|
| playoff | TODO | TODO | TODO | TODO |
| star_injury | TODO | higher | TODO | TODO |
| weather | TODO | 0 | 0 | highest |
| momentum | TODO | TODO | TODO | TODO |
| rivalry | TODO | TODO | TODO | TODO |

Keep the weights in one dict, `WEIGHTS: dict[str, dict[str, float]]`, in `scoring.py`.
Don't scatter them across modules.

## Sorting

Sort by `importance_score` descending, then by net community votes descending. The required
tests check that the high-stakes game comes first, the low-stakes game comes last, and that
votes break ties.
