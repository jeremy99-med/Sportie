import logging
import os
import threading
import uuid

from django.core.files.storage import default_storage
from django.db import connection

from .. import db

log = logging.getLogger(__name__)


def start(upload_id):
    """Runs the analysis in a background thread."""
    threading.Thread(target=_run_in_thread, args=(upload_id,), daemon=True).start()


def _run_in_thread(upload_id):
    try:
        run(upload_id)
    finally:
        connection.close()


def run(upload_id):
    """Analyzes one upload and marks it failed if anything goes wrong."""
    try:
        analyze(db.get_upload(upload_id))
    except Exception as exc:
        log.exception("Video analysis failed for upload %s", upload_id)
        db.mark_failed(upload_id, str(exc) or exc.__class__.__name__)


def analyze(upload):
    """Runs every stage on the video and saves the results."""
    # Imported here because they need OpenCV, which the normal server doesn't have.
    import cv2

    from . import homography, render, tactics, teams, tracking

    video_path = default_storage.path(upload["file_path"])

    # 1. Find the players and the ball in every frame (in pixels).
    tracked = tracking.track_video(video_path)

    # 2. Get each player's jersey color the first time they show up, then split the teams.
    video = cv2.VideoCapture(video_path)
    fps = (video.get(cv2.CAP_PROP_FPS) or 30) / tracking.FRAME_STEP  # tracked frames per second
    colors = {}
    frame_number = 0
    for frame_info in tracked:
        while frame_number < frame_info["frame"]:  # skip the frames that weren't tracked
            video.grab()
            frame_number += 1
        ok, frame = video.read()
        frame_number += 1
        if not ok:
            break
        for player in frame_info["players"]:
            if player["id"] not in colors:
                colors[player["id"]] = teams.jersey_color(frame, player["box"])
    video.release()
    team_of = teams.split_into_teams(colors)

    # 3. Move everyone from pixels to court meters.
    matrix = homography.make_matrix(upload["corners"])
    court_frames = []
    for frame_info in tracked:
        players = []
        for player in frame_info["players"]:
            players.append({
                "id": player["id"],
                "team": team_of[player["id"]],
                "pos": homography.to_court(matrix, player["feet"]),
            })
        ball = None
        if frame_info["ball"] is not None:
            ball = homography.to_court(matrix, frame_info["ball"])
        court_frames.append({"players": players, "ball": ball})

    # 4. Check for open teammates once per second, and skip repeated suggestions.
    suggestions = []
    for i in range(0, len(court_frames), int(fps)):
        for suggestion in tactics.suggest(court_frames[i]["players"], court_frames[i]["ball"]):
            if suggestion not in suggestions:
                suggestions.append(suggestion)

    # 5. Draw the top-down video and save the results.
    result_path = f"results/{upload['owner_id']}/{uuid.uuid4().hex}.mp4"
    os.makedirs(os.path.dirname(default_storage.path(result_path)), exist_ok=True)
    render.save_video(court_frames, default_storage.path(result_path), fps)
    db.save_results(upload["id"], result_path, {"suggestions": suggestions})
