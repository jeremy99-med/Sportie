"""
Simple top-down view of a basketball game.
Run: .venv/bin/python backend/apps/video_analyzer/scripts/topdown_simple.py ~/Downloads/test3.mp4.mov
"""

import sys
import cv2
import numpy as np

COURT_W, COURT_H = 940, 500    # NCAA court is 94 x 50 ft, so 10 pixels per foot


def click_corners(frame):
    """Let the user click the 4 court corners: top-left, top-right, bottom-right, bottom-left."""
    corners = []

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(corners) < 4:
            corners.append([x, y])
            cv2.circle(frame, (x, y), 10, (0, 0, 255), -1)
            cv2.imshow("Click 4 corners, then press any key", frame)

    cv2.namedWindow("Click 4 corners, then press any key", cv2.WINDOW_NORMAL)
    cv2.imshow("Click 4 corners, then press any key", frame)
    cv2.setMouseCallback("Click 4 corners, then press any key", on_click)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return corners


def make_topdown(video_path, corners):
    # 1. The flip: map the 4 clicked corners onto a flat rectangle.
    flat = np.float32([[0, 0], [COURT_W, 0], [COURT_W, COURT_H], [0, COURT_H]])
    matrix = cv2.getPerspectiveTransform(np.float32(corners), flat)

    # 2. Grab every 10th frame of the video.
    video = cv2.VideoCapture(video_path)
    samples = []
    count = 0
    while True:
        ok, frame = video.read()
        if not ok:
            break
        if count % 10 == 0:
            samples.append(frame)
        count += 1

    # 3. Empty court: players move, so the median of many frames is just the floor.
    empty = np.median(np.stack(samples), axis=0).astype(np.uint8)
    empty_flat = cv2.warpPerspective(empty, matrix, (COURT_W, COURT_H))

    fps = video.get(cv2.CAP_PROP_FPS)    # play back at the same speed as the original
    out = cv2.VideoWriter("topdown_simple.mp4", cv2.VideoWriter_fourcc(*"mp4v"),
                          fps, (COURT_W, COURT_H))

    # Go through the video again, this time every frame.
    video = cv2.VideoCapture(video_path)
    while True:
        ok, frame = video.read()
        if not ok:
            break
        # 4. Players = whatever looks different from the empty court.
        diff = cv2.absdiff(frame, empty).max(axis=2)
        _, mask = cv2.threshold(diff, 40, 255, cv2.THRESH_BINARY)
        mask = cv2.dilate(mask, np.ones((25, 9), np.uint8))   # join head, body, legs
        shapes, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 5. Draw a dot where each player's feet land on the flat court.
        court = empty_flat.copy()
        for shape in shapes:
            x, y, w, h = cv2.boundingRect(shape)
            if h < 60:
                continue                                       # too small to be a player
            feet = np.float32([[[x + w / 2, y + h]]])          # bottom-middle of the player
            fx, fy = cv2.perspectiveTransform(feet, matrix)[0][0]
            if 0 <= fx <= COURT_W and 0 <= fy <= COURT_H:      # only players on the court
                cv2.circle(court, (int(fx), int(fy)), 12, (0, 0, 255), -1)
        out.write(court)

    out.release()
    print("Saved topdown_simple.mp4")


if __name__ == "__main__":
    video_path = sys.argv[1]
    _, first_frame = cv2.VideoCapture(video_path).read()
    corners = click_corners(first_frame.copy())
    make_topdown(video_path, corners)
