---
name: new-endpoint
description: Add a Django REST Framework API endpoint to a Sportie app and wire a matching frontend fetch helper. Use when exposing models or services to the React frontend (e.g. list today's games, cast a vote, upload a video, get an analysis report).
---

# New DRF endpoint

Arguments: `<app_label>` plus a description of the resource or action.

URL prefixes: `community_game_ranker` → `/api/ranker/`, `video_analyzer` → `/api/video/`.

1. **Serializer**: `backend/apps/<app>/serializers.py`. Use `ModelSerializer` with explicit
   `fields` (never `"__all__"`) and read-only computed fields.
2. **View**: `backend/apps/<app>/views.py`.
   - Use a `ModelViewSet`/`ReadOnlyModelViewSet` for CRUD and an `APIView` or `@action` for
     verbs like voting.
   - Always set `permission_classes` explicitly. Writes need `IsAuthenticated`.
   - User-owned data (uploads, votes) filters on `request.user` in `get_queryset`.
   - Use `select_related`/`prefetch_related` to avoid N+1 queries.
   - Keep logic thin by calling into `services/`.
3. **URLs**: put a `DefaultRouter` or paths in `backend/apps/<app>/urls.py`. Make sure
   `backend/config/urls.py` has `path("api/<prefix>/", include("apps.<app>.urls"))`.
4. **Tests**: `backend/apps/<app>/tests/test_api.py` uses `APIClient`. Cover the happy path,
   unauthenticated writes (401/403), and another user's data (404). Run `pytest apps/<app> -q`.
5. **Frontend helper**: add a function in `frontend/src/features/<feature>/api.js` (create
   the file if it's missing). It uses `fetch` with `credentials: "include"`, sends the CSRF header
   on writes, throws on non-2xx, and returns the JSON.
6. If DRF is missing from `INSTALLED_APPS` or `requirements.txt`, stop and tell the user.

Check the result against `.claude/docs/ethics-checklist.md` for vote and upload endpoints.
