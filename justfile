# Sportie commands. Run `just` to list them.

dc := "docker compose --profile dev"

# Show all commands
default:
    @just --list

# ---- Run the app ----

# Start everything: database, backend (:8000), frontend (:5173), ranker refresh
up:
    {{dc}} up --build

# Start everything with YOLO + OpenCV installed (needed for the Video Analyzer)
up-video:
    INSTALL_VIDEO_DEPS=true {{dc}} up --build

# Start only the database + backend (:8000)
server:
    {{dc}} up --build db backend

# Start the backend with YOLO + OpenCV installed
server-video:
    INSTALL_VIDEO_DEPS=true {{dc}} up --build db backend

# Start only the frontend (:5173). Run `just server` in another terminal first.
client:
    {{dc}} up --no-deps frontend

# Stop everything
down:
    {{dc}} down

# Show the backend's logs
logs:
    {{dc}} logs -f backend

# ---- Tests ----

# Run all backend tests (e.g. `just test apps/video_analyzer -k upload`)
test *args:
    {{dc}} run --rm backend pytest -q {{args}}

# Run the YOLO / OpenCV tests on your Mac (Docker doesn't have OpenCV by default)
test-cv:
    cd backend && ../.venv/bin/pytest -q -p no:cacheprovider apps/video_analyzer/tests/test_detection.py apps/video_analyzer/tests/test_tracking.py apps/video_analyzer/tests/test_homography.py apps/video_analyzer/tests/test_teams.py

# Check the frontend builds without errors
build:
    {{dc}} run --rm --no-deps frontend npm run build

# ---- Database ----

# Create the tables (run new migrations)
migrate:
    {{dc}} run --rm backend python manage.py migrate

# Make a migration after changing models (e.g. `just makemigrations community_game_ranker`)
makemigrations app:
    {{dc}} run --rm backend python manage.py makemigrations {{app}}

# Open a SQL prompt on the database
psql:
    {{dc}} exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

# Make a login for yourself (asks for a username and password)
superuser:
    {{dc}} run --rm backend python manage.py createsuperuser

# ---- Video Analyzer ----

# See YOLO tracking on your own video (e.g. `just track ~/Downloads/game.mp4`)
track video:
    cd backend && ../.venv/bin/python -m apps.video_analyzer.scripts.track_preview "{{absolute_path(video)}}"
