---
name: scoring-factor
description: Add, change, or re-weight a factor in the Community Game Ranker importance score (playoff, star injury, weather, momentum, rivalry, status, community votes). Use for any change to how games are ranked.
---

# Importance-score factor

1. Read `.claude/docs/importance-scoring.md` and
   `backend/apps/community_game_ranker/services/scoring.py`.
2. Implement or adjust the factor as a **pure function**, `def <factor>_factor(...) -> float`.
   It takes plain values (not querysets) and returns a float in `[0, 1]`. Clamp the output.
3. Weights live only in the single `WEIGHTS[sport][factor]` dict. Weather is always 0 for NBA
   and NHL.
4. Make sure the combiner includes the factor and writes it into `score_breakdown`.
5. Tests in `tests/test_scoring.py`:
   - Boundary values (0, 1, missing data).
   - Per-sport behavior (for example, weather has no effect on NBA or NHL).
   - Ordering: the high-stakes game ranks above the low-stakes one, and votes break ties.
6. Update the factor and weight tables in `importance-scoring.md`. Replace TODOs only with
   values the user has chosen. Never make up weights. Ask if they're unspecified.
7. Run `cd backend && pytest apps/community_game_ranker -q`.
