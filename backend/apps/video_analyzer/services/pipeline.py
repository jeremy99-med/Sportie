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


COURT_MARGIN = 1     # meters; people further outside the lines are ignored (bench, crowd)
SMOOTH_FRAMES = 5    # average each player's last 5 positions so the dots don't jump
COLOR_SAMPLES = 10   # jersey color = average of up to 10 frames
MAX_SUGGESTIONS = 30


def on_court(pos):
    """True if a position (in meters) is on the court, or just outside it."""
    x, y = pos
    return -COURT_MARGIN <= x <= 40 + COURT_MARGIN and -COURT_MARGIN <= y <= 20 + COURT_MARGIN


def analyze(upload):
    """Runs every stage on the video and saves the results."""
    # Imported here because they need OpenCV, which the normal server doesn't have.
    import cv2

    from . import homography, render, tactics, teams, tracking

    video_path = default_storage.path(upload["file_path"])

    # 1. Find the players and the ball in every frame (in pixels).
    tracked = tracking.track_video(video_path)

    # 2. Move everyone to court meters, and drop anyone who isn't on the court.
    matrix = homography.make_matrix(upload["corners"])
    for frame_info in tracked:
        players = []
        for player in frame_info["players"]:
            player["pos"] = homography.to_court(matrix, player["feet"])
            if on_court(player["pos"]):
                players.append(player)
        frame_info["players"] = players
        if frame_info["ball"] is not None:
            frame_info["ball"] = homography.to_court(matrix, frame_info["ball"])

    # 3. Average each player's jersey color over several frames, then split the teams.
    video = cv2.VideoCapture(video_path)
    fps = (video.get(cv2.CAP_PROP_FPS) or 30) / tracking.FRAME_STEP  # tracked frames per second
    samples = {}
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
            player_samples = samples.setdefault(player["id"], [])
            if len(player_samples) < COLOR_SAMPLES:
                player_samples.append(teams.jersey_color(frame, player["box"]))
    video.release()
    colors = {}
    for player_id, player_samples in samples.items():
        colors[player_id] = teams.average(player_samples)
    team_of = teams.split_into_teams(colors)

    # 4. Smooth each player's position over their last few frames.
    history = {}
    court_frames = []
    for frame_info in tracked:
        players = []
        for player in frame_info["players"]:
            recent = history.setdefault(player["id"], [])
            recent.append(player["pos"])
            del recent[:-SMOOTH_FRAMES]
            players.append({"id": player["id"], "team": team_of[player["id"]], "pos": teams.average(recent)})
        court_frames.append({"players": players, "ball": frame_info["ball"]})

    # 5. Check once per second and keep one new suggestion each time, with the time.
    suggestions = []
    seen = set()
    for i in range(0, len(court_frames), max(1, int(fps))):
        seconds = round(i / fps)
        for suggestion in tactics.suggest(court_frames[i]["players"], court_frames[i]["ball"]):
            if suggestion["text"] not in seen and len(suggestions) < MAX_SUGGESTIONS:
                seen.add(suggestion["text"])
                suggestions.append({"time": seconds, "text": f"{seconds // 60}:{seconds % 60:02d} — {suggestion['text']}"})
                break

    # 6. Draw the top-down video and save the results.
    result_path = f"results/{upload['owner_id']}/{uuid.uuid4().hex}.mp4"
    os.makedirs(os.path.dirname(default_storage.path(result_path)), exist_ok=True)
    render.save_video(court_frames, default_storage.path(result_path), fps)
    db.save_results(upload["id"], result_path, {"suggestions": suggestions})
