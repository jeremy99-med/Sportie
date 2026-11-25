import os
import subprocess

import cv2
import imageio_ffmpeg
import numpy as np

SCALE = 30  # pixels per meter
WIDTH = 40 * SCALE
HEIGHT = 20 * SCALE

# OpenCV colors (blue, green, red)
GREEN = (60, 120, 60)
WHITE = (255, 255, 255)
YELLOW = (0, 255, 255)
TEAM_COLORS = {"A": (0, 0, 255), "B": (255, 0, 0)}


def draw_frame(players, ball):
    """Draws the court, the players, and the ball for one frame."""
    picture = np.full((HEIGHT, WIDTH, 3), GREEN, dtype=np.uint8)
    cv2.line(picture, (WIDTH // 2, 0), (WIDTH // 2, HEIGHT), WHITE, 2)

    for player in players:
        x = int(player["pos"][0] * SCALE)
        y = int(player["pos"][1] * SCALE)
        cv2.circle(picture, (x, y), 12, TEAM_COLORS[player["team"]], -1)
        cv2.putText(picture, str(player["id"]), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)

    if ball is not None:
        cv2.circle(picture, (int(ball[0] * SCALE), int(ball[1] * SCALE)), 6, YELLOW, -1)
    return picture


def save_video(all_frames, output_path, fps):
    """Draws every frame and saves them as an .mp4 video that browsers can play."""
    # OpenCV can't make H.264 (the format browsers need), so save a temporary video first,
    # then convert it with ffmpeg.
    temp_path = str(output_path) + ".tmp.mp4"
    video = cv2.VideoWriter(temp_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (WIDTH, HEIGHT))
    for frame in all_frames:
        video.write(draw_frame(frame["players"], frame["ball"]))
    video.release()

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", temp_path, "-vcodec", "libx264",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path)], check=True)
    os.remove(temp_path)
