# Video analysis pipeline

Code: `backend/apps/video_analyzer/services/`. Dependencies: `requirements-video.txt`
(opencv-python-headless, ultralytics). Both are optional, so import them lazily.

## Stages and contracts

```text
video file
  -> frames.py      iter_frames(path, stride) -> Iterator[(frame_idx, np.ndarray BGR)]
  -> detection.py   detect(frame) -> list[Detection(bbox_xyxy, cls: "player"|"ball", conf)]
  -> tracking.py    track(frames) -> list[FrameTracks(frame_idx, tracks: list[Track(id, bbox, cls)])]
                    (Ultralytics' built-in tracker, e.g. ByteTrack, keeps IDs stable)
  -> teams.py       assign_teams(frame, tracks) -> dict[track_id, "A"|"B"|"ref"]
                    (dominant jersey color from the upper half of the bbox, then k-means with k=2)
  -> homography.py  compute_H(src_corners_px[4], court_dims_m) -> 3x3
                    to_court(H, foot_point_px) -> (x_m, y_m)   # use the bottom-center of the bbox
  -> tactics.py     analyze(snapshot: CourtSnapshot) -> list[Suggestion]
  -> render.py      draw_topdown(snapshots, suggestions) -> output video/PNGs
pipeline.py         run(upload_id): runs every stage and writes AnalysisReport, setting status
```

`CourtSnapshot` = `{frame_idx, players: [{id, team, x, y}], ball: (x, y) | None}` in meters.

## Court

- Futsal court: TODO (pick and record the exact dimensions used, about 40x20 m).
- Corner points: the user picks the 4 court corners in the frontend for the MVP, so there's
  no automatic court-line detection yet.

## Tactics rules (MVP, rule-based)

- **Open space:** grid the court, and mark a cell open when its distance to the nearest opponent
  is above a threshold (TODO: pick the value). A Voronoi diagram is a good alternative.
- **Passing option:** a teammate of the ball carrier is open when no opponent is within X m of the
  pass line and the receiver is unmarked.
- **Crowding:** two teammates closer than Y m to each other.
- Later: replace these thresholds with a model learned from tracked games.

## Testing

- Unit-test `tactics.py` and `homography.py` with hand-built coordinates. No video needed.
- Detection and tracking tests mock the YOLO model. An opt-in real-model test goes behind
  `@pytest.mark.yolo` with `pytest.importorskip("ultralytics")`.
- Fixtures: 2-5 small frames in `tests/fixtures/`. Never commit videos or `.pt` weights.
- Bias check (ethics): spot-check detection quality across skin tones and jersey colors.
