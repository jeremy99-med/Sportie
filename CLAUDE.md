# Sportie

Capstone project (Jeremy Mednik + Alpha Diallo). Two independent features in one app:

- **Community Game Ranker** (owner: Jeremy). Ranks each day's NFL/NBA/NHL/MLB games by an
  importance score: playoff stakes, star injuries, weather, momentum, rivalry, game status,
  plus community up/down votes. Pulls data from balldontlie, SportsData.io, and WeatherAPI, and
  uses Claude (Opus 5.5) to interpret standings.
- **Video Analyzer** (owner: Alpha). Takes an uploaded amateur game video (5v5 futsal first),
  detects and tracks players and the ball with YOLO, assigns teams by jersey color, warps the
  view to bird's-eye with an OpenCV homography, and suggests open space and passing options
  with a rules engine.

## Repo map

```text
backend/                 Django 5.2 project (run commands from here)
  config/                settings.py, urls.py
  apps/community_game_ranker/   models, services/ (scoring), integrations/ (API clients), tests/
  apps/video_analyzer/          models, services/ (pipeline stages), tests/
  apps/accounts/                shared: auth groups (Normal/Admin/Superadmin), no models
frontend/src/features/   community-game-ranker/, video-analyzer/  (React 19 + Vite + Bootstrap 5)
frontend/src/theme.css   design tokens (--sp-*), dark navy palette
```

## Stack and conventions

- Backend: Django + **Django REST Framework**. Every API lives under `/api/<feature>/`
  (`/api/ranker/...`, `/api/video/...`). Each app owns its `serializers.py`, `views.py`, and
  `urls.py`, and `config/urls.py` only `include()`s them.
- Business logic goes in `services/`, not in views or models. API clients go in `integrations/`.
- Database: PostgreSQL only. Don't assume SQLite behavior.
- Tests: pytest + pytest-django, in `apps/<app>/tests/test_*.py`. Mock all external HTTP
  (`requests`) and YOLO/OpenCV inference in unit tests. Tests must never hit the network.
- Frontend: feature code stays in its feature folder, and each folder's API calls go in its `api.js`.
  Style with Bootstrap classes and the `--sp-*` tokens; don't hardcode colors.
- Keep the features isolated. Don't import across apps. Code both apps need goes in a shared module.
- Secrets live only in `backend/.env` (gitignored). Never read, print, or commit it. When you add a
  new key, also add a placeholder to `backend/.env.example`.
- For any Claude/Anthropic API code in the ranker, use the `claude-api` skill.

## Commands

```bash
docker compose --profile dev up --build             # db + backend :8000 + frontend :5173
INSTALL_VIDEO_DEPS=true docker compose --profile dev up --build   # include OpenCV + YOLO
cd backend && pytest                                # all backend tests
cd backend && pytest apps/community_game_ranker     # one app
cd backend && python manage.py makemigrations <app_label> && python manage.py migrate
cd backend && python manage.py check
cd frontend && npm run dev | npm run build
```

App labels: `community_game_ranker`, `video_analyzer`, `accounts`.

## Milestones (2026)

Nov 5 prototype + DB diagram · Nov 19 backend · Nov 26 frontend · Dec 3 unit tests ·
Dec 11 final demo + report.

## Read on demand (don't preload)

| When working on...                              | Read                                   |
|-------------------------------------------------|----------------------------------------|
| Models, migrations, the DB diagram              | `.claude/docs/data-model.md`           |
| Importance score, weights, sorting              | `.claude/docs/importance-scoring.md`   |
| balldontlie / SportsData.io / WeatherAPI        | `.claude/docs/external-apis.md`        |
| YOLO, tracking, homography, tactics rules       | `.claude/docs/video-pipeline.md`       |
| Reviews, auth, votes, uploads, disclaimers      | `.claude/docs/ethics-checklist.md`     |

Agents live in `.claude/agents/` (test-writer, api-integrator, cv-pipeline, reviewer,
status-reporter). Skills live in `.claude/skills/` (/new-model, /new-endpoint,
/react-feature-component, /scoring-factor, /status-report, /db-diagram).
