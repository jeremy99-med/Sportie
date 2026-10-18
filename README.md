# Sportie

Sportie is organized as a React frontend and a Django backend, with each of the
two product features kept separate on both sides of the application.

## Project structure

```text
frontend/
  src/
    features/
      community-game-ranker/  # Daily games, importance scores, community votes
      video-analyzer/         # Uploads, video review, tactical visualizations
    App.jsx
    main.jsx
backend/
  config/                     # Django settings and project URLs
  apps/
    community_game_ranker/    # Game data, scoring, votes, external integrations
    video_analyzer/            # Video pipeline, tracking, tactical analysis
```

The React feature folders are intended for feature UI, API calls, and
feature-specific state. Django feature apps own their models, business logic,
API endpoints, and tests. Shared utilities belong in shared modules only when
both features need them.

## Stack

- Frontend: React and JavaScript, Vite, Bootstrap
- Backend: Python and Django (including Django authentication)
- Database: PostgreSQL via psycopg
- Tests: pytest and pytest-django
- Video analysis: OpenCV and Ultralytics YOLO (optional dependencies)

## Getting started

### Docker

Install Docker Desktop, then activate the `dev` profile to start the frontend,
backend, and PostgreSQL with Django debug mode enabled:

```bash
docker compose --profile dev up --build
```

Open the React app at <http://localhost:5173> and the Django admin at
<http://localhost:8000/admin/>. The database starts with development-only
credentials and keeps its data in a named Docker volume. To stop the services,
press Ctrl+C and run `docker compose --profile dev down`. To also remove the
local database volume, run `docker compose --profile dev down --volumes`. The
`--profile dev` flag is required because every service belongs to that profile.

The default backend image installs the core dependencies. To include OpenCV
and YOLO in the image, set the build argument while starting the dev profile:

```bash
INSTALL_VIDEO_DEPS=true docker compose --profile dev up --build
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py check
```

Configure the PostgreSQL connection in `backend/.env` before running database
migrations or starting the backend. Install the optional video dependencies
when working on the analyzer:

```bash
python -m pip install -r requirements-video.txt
```

Run backend tests with `pytest` from `backend/`.

### Frontend

Install Node.js (LTS), then run:

```bash
cd frontend
npm install
npm run dev
```

Node.js is required to install the frontend packages and run the Vite
development server.
