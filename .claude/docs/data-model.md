# Data model

The source of truth for models in both apps and for the Nov 5 DB diagram. When a model
changes, update this file in the same change. Users come from `django.contrib.auth`
(`settings.AUTH_USER_MODEL`). Fields marked TODO are still undecided.

## community_game_ranker

Implemented in `backend/apps/community_game_ranker/models.py` (migration `0001_initial_ranker_models`).
`?` = nullable. FKs to Sport/Team from GameLog are `PROTECT` so history can't be deleted by accident.

| Model | Key fields | Relations / constraints |
|---|---|---|
| Sport | `code` (TextChoices NFL/NBA/NHL/MLB, unique), `name`, `is_outdoor_default` (bool) | |
| Team | `name`, `abbreviation` (≤10), `city` (blank ok), `external_ids` (JSON, per provider, default `{}`) | FK Sport (PROTECT, `teams`); unique (sport, abbreviation) |
| Stadium | `name`, `latitude` / `longitude` (Decimal 9,6), `is_indoor` | FK Team? home_team (SET_NULL, `stadiums`; null = neutral site); DB check lat ∈ [-90, 90], lon ∈ [-180, 180]; used for WeatherAPI lookups |
| Player | `name`, `position` (blank ok), `is_star` (bool), `external_ids` (JSON) | FK Team? (SET_NULL, `players`; null = free agent) |
| GameLog | `scheduled_at`, `status` (TextChoices scheduled/in_progress/final/delayed/postponed, default scheduled), `home_score?` / `away_score?` (PositiveSmallInt), `importance_score?` (float), `score_breakdown` (JSON, default `{}`), `season` (start year), `week?` (NFL only) | FK Sport (PROTECT, `games`), FK home_team (PROTECT, `home_games`), FK away_team (PROTECT, `away_games`), FK Stadium? (SET_NULL, `games`); index (sport, scheduled_at); DB check home ≠ away; `clean()` requires both teams in the game's sport |
| Injury | `status` (TextChoices out/doubtful/questionable), `description` (blank ok), `reported_at` | FK Player (CASCADE, `injuries`), FK GameLog (CASCADE, `injuries`); unique (player, game) |
| WeatherCondition | `temp_c`, `precip_mm` (≥0), `wind_kph` (≥0), `condition_text`, `fetched_at` | OneToOne GameLog (CASCADE, `weather`) |
| Rivalry | `intensity` (1-5, DB check), `name` (optional) | FK team_a, FK team_b (CASCADE); `save()` normalizes so team_a_id < team_b_id (also a DB check); unique (team_a, team_b); `Rivalry.between(t1, t2)` looks up either order |
| ExternalAPIMetadata | `provider` (TextChoices balldontlie/sportsdata/weatherapi), `endpoint`, `params_hash` (sha256 hex), `response?` (JSON), `fetched_at`, `status_code` | Response cache and audit log; unique (provider, endpoint, params_hash); `hash_params(dict)` gives a key-order-independent hash |
| CommunityVote | `value` (IntegerChoices +1 / -1, DB check), `category` (TextChoices enjoyment/competitiveness/officiating), `created_at` | FK User (CASCADE, `game_votes`), FK GameLog (CASCADE, `votes`); unique (user, game, category) |

## video_analyzer

| Model | Key fields | Relations / constraints |
|---|---|---|
| VideoUpload | `file` (FileField), `status` (uploaded/processing/done/failed), `sport` (futsal for now), `error` (text), `created_at` | FK User (owner) |
| AnalysisReport | `output_dir`, `topdown_video`, `summary` (JSON: possession, open-space events, suggestions), `created_at` | OneToOne VideoUpload |
| TrainingSample (TODO, optional) | `frame_index`, `positions` (JSON), `label` | FK VideoUpload |

## Conventions

- Use `TextChoices` for every status or enum field.
- Add `created_at = DateTimeField(auto_now_add=True)` wherever ordering matters.
- Register every model in the app's `admin.py`.
- Name migrations clearly: `makemigrations <app> --name <what_changed>`.
