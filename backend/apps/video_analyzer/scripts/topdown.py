"""
Turn a game video into a top-down (bird's-eye) view.


"""

import sys
from pathlib import Path

import cv2
import numpy as np

# Output size in pixels for each court, keeping the real court's shape.
COURTS = {
    "futsal": (1200, 600),       # 40 m x 20 m, at 30 pixels per meter
    "basketball": (1128, 600),   # NCAA: 94 ft x 50 ft, at 12 pixels per foot
    "soccer": (1050, 680),       # 11-a-side: 105 m x 68 m, at 10 pixels per meter
}
CORNER_NAMES = ["top-left", "top-right", "bottom-right", "bottom-left"]
WINDOW = "Click the 4 court corners"

# Player detection works on a half-size copy of each frame
WORK_SCALE = 0.5
DIFF_THRESHOLD = 40      # how different from the empty court a pixel must be
MIN_PLAYER_HEIGHT = 25   # in half-size pixels; smaller blobs are noise or the ball


def pick_corners(frame):
    """Show the frame and let the user click 4 points. Returns [[x, y], ...]."""
    corners = []

    def redraw():
        shown = frame.copy()
        for i, (x, y) in enumerate(corners):
            cv2.circle(shown, (x, y), 8, (0, 0, 255), -1)
            cv2.putText(shown, str(i + 1), (x + 10, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        if len(corners) > 1:
            pts = np.array(corners, np.int32)
            cv2.polylines(shown, [pts], len(corners) == 4, (0, 255, 255), 2)
        if len(corners) < 4:
            message = f"Click the {CORNER_NAMES[len(corners)]} corner  (R = reset)"
        else:
            message = "Press Enter to continue  (R = reset)"
        cv2.putText(shown, message, (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.imshow(WINDOW, shown)

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(corners) < 4:
            corners.append([x, y])
            redraw()

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(WINDOW, on_click)
    redraw()

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key in (ord("r"), ord("R")):
            corners.clear()
            redraw()
        elif key in (13, 32) and len(corners) == 4:  # Enter or Space
            break
        elif key == 27:  # Esc
            sys.exit("Cancelled.")

    cv2.destroyWindow(WINDOW)
    return corners


def empty_court(video, samples=60):
    """
    Build a picture of the court with the players removed.

    Players keep moving, so for each pixel the most common ("median") color
    across many frames is the floor, not a player.
    """
    total = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for i in range(0, total, max(1, total // samples)):
        video.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = video.read()
        if ok:
            frames.append(frame)
    video.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def find_players(small_frame, small_empty, court_outline):
    """
    Find players by comparing the frame with the empty court.
    Returns a list of (feet_x, feet_y, jersey_color, box) in half-size pixels.
    """
    diff = cv2.absdiff(small_frame, small_empty).max(axis=2)
    _, mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # Join a player's head, body, and legs into one shape.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 5), np.uint8))

    players = []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < MIN_PLAYER_HEIGHT:
            continue
        feet = (x + w / 2, y + h)  # bottom-middle of the shape touches the floor
        if cv2.pointPolygonTest(court_outline, feet, True) < -10:
            continue  # outside the court: fans, benches, the mouse cursor
        # Jersey color = average color of the upper body.
        torso = small_frame[y + h // 5 : y + h // 2, x : x + w]
        torso_mask = mask[y + h // 5 : y + h // 2, x : x + w]
        color = cv2.mean(torso, torso_mask)[:3] if torso.size else (255, 255, 255)
        players.append((feet[0], feet[1], color, (x, y, w, h)))
    return players


def make_topdown_video(input_path, output_path, corners, court="futsal",
                       flat_path=None, show_preview=True):
    """Make the side-by-side top-down video. Returns the number of frames written."""
    out_w, out_h = COURTS[court]
    src = np.float32(corners)
    dst = np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]])
    matrix = cv2.getPerspectiveTransform(src, dst)

    # The same flip for the half-size frames used in player detection.
    small_matrix = cv2.getPerspectiveTransform(src * WORK_SCALE, dst)
    small_outline = (src * WORK_SCALE).reshape(-1, 1, 2)

    video = cv2.VideoCapture(str(input_path))
    fps = video.get(cv2.CAP_PROP_FPS) or 30
    frame_w = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print("Building an empty court (removing the players)...")
    empty = empty_court(video)
    small_empty = cv2.resize(empty, None, fx=WORK_SCALE, fy=WORK_SCALE)
    clean_court = cv2.warpPerspective(empty, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC)

    # Left panel: the original video, shrunk to the same height as the court.
    left_w = round(frame_w * out_h / frame_h)
    codec = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), codec, fps, (left_w + out_w, out_h))
    flat_writer = None
    if flat_path:
        flat_writer = cv2.VideoWriter(str(flat_path), codec, fps, (out_w, out_h))

    print("Making the top-down video...")
    count = 0
    while True:
        ok, frame = video.read()
        if not ok:
            break

        small = cv2.resize(frame, None, fx=WORK_SCALE, fy=WORK_SCALE)
        players = find_players(small, small_empty, small_outline)

        # Right panel: clean court + one dot per player, at their feet.
        court_view = clean_court.copy()
        for feet_x, feet_y, color, _ in players:
            point = np.float32([[[feet_x, feet_y]]])
            cx, cy = cv2.perspectiveTransform(point, small_matrix)[0][0]
            if -20 <= cx <= out_w + 20 and -20 <= cy <= out_h + 20:
                cv2.circle(court_view, (int(cx), int(cy)), 14, (30, 30, 30), -1)
                cv2.circle(court_view, (int(cx), int(cy)), 11, color, -1)

        # Left panel: original frame with the court outline and a box per player.
        original = frame.copy()
        cv2.polylines(original, [src.astype(np.int32)], True, (0, 255, 255), 4)
        for _, _, _, (x, y, w, h) in players:
            x, y, w, h = (int(v / WORK_SCALE) for v in (x, y, w, h))
            cv2.rectangle(original, (x, y), (x + w, y + h), (0, 255, 0), 3)
        original = cv2.resize(original, (left_w, out_h), interpolation=cv2.INTER_AREA)

        combined = np.hstack([original, court_view])
        writer.write(combined)
        if flat_writer:
            flat_writer.write(cv2.warpPerspective(frame, matrix, (out_w, out_h),
                                                  flags=cv2.INTER_CUBIC))
        count += 1

        if show_preview:
            cv2.imshow("Top-down view (Q to stop early)", combined)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                break

    video.release()
    writer.release()
    if flat_writer:
        flat_writer.release()
    cv2.destroyAllWindows()
    return count


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    input_path = Path(sys.argv[1])
    court = sys.argv[2] if len(sys.argv) > 2 else "futsal"
    if court not in COURTS:
        sys.exit(f"Unknown court '{court}'. Choose one of: {', '.join(COURTS)}")

    video = cv2.VideoCapture(str(input_path))
    ok, first_frame = video.read()
    video.release()
    if not ok:
        sys.exit(f"Couldn't read a video from {input_path}")

    corners = pick_corners(first_frame)
    output_path = input_path.with_name(f"{input_path.stem}_topdown.mp4")
    flat_path = input_path.with_name(f"{input_path.stem}_flat.mp4")
    frames = make_topdown_video(input_path, output_path, corners, court, flat_path)
    print(f"Done! Wrote {frames} frames to:")
    print(f"  {output_path}")
    print(f"  {flat_path}")


if __name__ == "__main__":
    main()
