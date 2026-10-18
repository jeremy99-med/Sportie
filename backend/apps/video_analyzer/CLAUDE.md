# Video Analyzer (owner: Alpha)

Tactical film review for amateur teams. Scope starts at 5v5 futsal, then 11v11, then basketball.

## Layout

- `models.py`: VideoUpload (user, file, status, created_at), AnalysisReport (upload, output
  paths, summary), TrainingSample (optional). See `.claude/docs/data-model.md`.
- `services/`: one module per pipeline stage: `detection.py`, `tracking.py`, `teams.py`,
  `homography.py`, `tactics.py`, `render.py`, plus `pipeline.py` to wire them together.
  The data contracts between stages are in `.claude/docs/video-pipeline.md`.
- `tests/`: per-stage tests that use tiny fixture frames in `tests/fixtures/`.

## Rules

- OpenCV and Ultralytics are **optional** dependencies (`requirements-video.txt`). Import
  them inside functions or behind `pytest.importorskip`, so `python manage.py check` and the
  ranker tests still run without them.
- Stages exchange plain dataclasses or numpy arrays, not ORM objects. Only `pipeline.py` talks
  to the database.
- `tactics.py` holds rule-based, pure geometry on court coordinates (meters). Keep it easy
  to test with hand-built positions, with no video involved.
- Never commit videos or model weights (`*.mp4`, `*.pt`). Fixtures should be a few small
  PNG/JPG frames.
- Uploaded videos can show people who never consented. Keep uploads private to the owner.

## Required tests (from the proposal)

Upload works · bird's-eye transform · correct player count on a sample frame · ball detected
when visible · players split into the correct teams · player keeps the same ID across frames ·
open space found when the court has space · YOLO integration (mocked in unit tests, real model
in an opt-in marked test).
