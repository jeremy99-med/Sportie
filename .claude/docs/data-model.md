# Data model

The source of truth for models in both apps and for the Nov 5 DB diagram. When a model
changes, update this file in the same change. Users come from `django.contrib.auth`
(`settings.AUTH_USER_MODEL`). Fields marked TODO are still undecided.

## community_game_ranker

Implemented in `backend/apps/community_game_ranker/models.py` (migrations `0001_initial_ranker_models`, `0002_single_vote_and_team_standing`; `0003_seed_reference_data` loads the sports, NBA/NFL teams, stadiums, and rivalries from `seed/`).
`?` = nullable. FKs to Sport/Team from GameLog are `PROTECT` so history can't be deleted by accident.

| Model | Key fields | Relations / constraints |
|---|---|---|
| Sport | `code` (TextChoices NFL/NBA/NHL/MLB, unique), `name`, `is_outdoor_default` (bool) | |
| Team | `name`, `abbreviation` (≤10), `city` (blank ok), `external_ids` (JSON per provider, e.g. `{"balldontlie": 8, "sportsdata": 4}`, filled by `sync_rosters`; default `{}`) | FK Sport (PROTECT, `teams`); unique (sport, abbreviation) |
| Stadium | `name`, `latitude` / `longitude` (Decimal 9,6), `is_indoor` | FK Team? home_team (SET_NULL, `stadiums`; null = neutral site); DB check lat ∈ [-90, 90], lon ∈ [-180, 180]; used for WeatherAPI lookups |
| Player | `name`, `position` (blank ok), `is_star` (bool), `external_ids` (JSON; SportsData id under `sportsdata_nba` / `sportsdata_nfl`) | FK Team? (SET_NULL, `players`; null = free agent) |
| TeamStanding | `season` (start year), `wins` / `losses` / `ties` (default 0), `conference_rank?`, `games_back?` (float), `updated_at` | FK Team (CASCADE, `standings`); unique (team, season); feeds the playoff and momentum factors |
| GameLog | `scheduled_at`, `status` (TextChoices scheduled/in_progress/final/delayed/postponed, default scheduled), `home_score?` / `away_score?` (PositiveSmallInt), `importance_score?` (float), `score_breakdown` (JSON, default `{}`), `season` (start year), `week?` (NFL only) | FK Sport (PROTECT, `games`), FK home_team (PROTECT, `home_games`), FK away_team (PROTECT, `away_games`), FK Stadium? (SET_NULL, `games`); index (sport, scheduled_at); DB check home ≠ away; `clean()` requires both teams in the game's sport |
| Injury | `status` (TextChoices out/doubtful/questionable), `status_estimated` (bool, true when trial data hid the real status), `description` (blank ok), `reported_at` | FK Player (CASCADE, `injuries`), FK GameLog (CASCADE, `injuries`); unique (player, game) |
| WeatherCondition | `temp_c`, `precip_mm` (≥0), `wind_kph` (≥0), `condition_text`, `fetched_at` | OneToOne GameLog (CASCADE, `weather`) |
| Rivalry | `intensity` (1-5, DB check), `name` (optional) | FK team_a, FK team_b (CASCADE); `save()` normalizes so team_a_id < team_b_id (also a DB check); unique (team_a, team_b); `Rivalry.between(t1, t2)` looks up either order |
| ExternalAPIMetadata | `provider` (TextChoices balldontlie/sportsdata/weatherapi), `endpoint`, `params_hash` (sha256 hex), `response?` (JSON), `fetched_at`, `status_code` | Response cache and audit log; unique (provider, endpoint, params_hash); `hash_params(dict)` gives a key-order-independent hash |
| CommunityVote | `value` (IntegerChoices +1 / -1, DB check), `created_at` | FK User (CASCADE, `game_votes`), FK GameLog (CASCADE, `votes`); unique (user, game). Same vote again removes it, opposite vote flips it (`services/votes.py`) |

## video_analyzer

| Model | Key fields | Relations / constraints |
|---|---|---|
| VideoUpload | `file` (FileField), `status` (uploaded/processing/done/failed), `sport` (futsal for now), `error` (text), `created_at` | FK User (owner) |
| AnalysisReport | `output_dir`, `topdown_video`, `summary` (JSON: possession, open-space events, suggestions), `created_at` | OneToOne VideoUpload |
| TrainingSample (TODO, optional) | `frame_index`, `positions` (JSON), `label` | FK VideoUpload |

## accounts (auth groups)

No models. `apps/accounts/services/groups.py` defines three `auth.Group`s and re-syncs them after
every `migrate` (post_migrate), so edit the code, not the admin site. New users join Normal, and
new superusers join Superadmin (post_save).

| Group | Permissions |
|---|---|
| Normal | `view_*` on ranker Sport/Team/Stadium/Player/TeamStanding/GameLog/Injury/WeatherCondition/Rivalry; add/change/delete/view CommunityVote |
| Admin | everything in `community_game_ranker` and `video_analyzer`; `auth.view_user`, `auth.view_group`, `admin.view_logentry` |
| Superadmin | every permission (`Permission.objects.all()`) |

## Conventions

- Use `TextChoices` for every status or enum field.
- Add `created_at = DateTimeField(auto_now_add=True)` wherever ordering matters.
- Register every model in the app's `admin.py`.
- Name migrations clearly: `makemigrations <app> --name <what_changed>`.
