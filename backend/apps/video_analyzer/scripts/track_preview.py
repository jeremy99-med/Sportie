"""Usage: python -m apps.video_analyzer.scripts.track_preview path/to/game.mp4"""

import sys

import cv2

from apps.video_analyzer.services.detection import load_model
from apps.video_analyzer.services.tracking import track_frame

SECONDS = 10
GREEN = (0, 255, 0)
YELLOW = (0, 255, 255)

if len(sys.argv) < 2:
    sys.exit(__doc__)

video_path = sys.argv[1]
output_path = video_path.rsplit(".", 1)[0] + "_tracked.mp4"
video = cv2.VideoCapture(video_path)
fps = video.get(cv2.CAP_PROP_FPS) or 30
size = (int(video.get(cv2.CAP_PROP_FRAME_WIDTH)), int(video.get(cv2.CAP_PROP_FRAME_HEIGHT)))
output = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
model = load_model()
ids_seen, frames_with_ball, frame_number = set(), 0, 0

while frame_number < fps * SECONDS:
    ok, frame = video.read()
    if not ok:
        break
    result = track_frame(model, frame, frame_number)
    for player in result["players"]:
        x1, y1, x2, y2 = [int(v) for v in player["box"]]
        cv2.rectangle(frame, (x1, y1), (x2, y2), GREEN, 2)
        cv2.putText(frame, f"#{player['id']}", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, GREEN, 2)
        ids_seen.add(player["id"])
    if result["ball"] is not None:
        cv2.circle(frame, tuple(int(v) for v in result["ball"]), 10, YELLOW, -1)
        frames_with_ball += 1
    output.write(frame)
    frame_number += 1

video.release()
output.release()
print(f"Saved {output_path}: {len(ids_seen)} player IDs, ball in {frames_with_ball}/{frame_number} frames")
