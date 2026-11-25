from .detection import COCO_PERSON, COCO_SPORTS_BALL, IMAGE_SIZE, load_model

PLAYER_MIN_CONFIDENCE = 0.3
BALL_MIN_CONFIDENCE = 0.15
MAX_BALL_GAP = 5
FRAME_STEP = 3  # only track every 3rd frame, to be faster


def track_frame(model, frame, frame_number):
    """Finds the players (with tracking IDs) and the ball in one frame."""
    results = model.track(frame, persist=True, tracker="bytetrack.yaml",
                          classes=[COCO_PERSON, COCO_SPORTS_BALL], conf=BALL_MIN_CONFIDENCE,
                          imgsz=IMAGE_SIZE, verbose=False)
    players, ball, ball_confidence = [], None, 0
    for box in results[0].boxes:
        kind, confidence = int(box.cls), float(box.conf)
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
        if kind == COCO_PERSON and box.id is not None and confidence >= PLAYER_MIN_CONFIDENCE:
            players.append({"id": int(box.id), "box": (x1, y1, x2, y2), "feet": ((x1 + x2) / 2, y2)})
        if kind == COCO_SPORTS_BALL and confidence > ball_confidence:
            ball, ball_confidence = ((x1 + x2) / 2, (y1 + y2) / 2), confidence
    return {"frame": frame_number, "players": players, "ball": ball}


def track_video(video_path):
    """Tracks every FRAME_STEP-th frame of a video."""
    import cv2

    model = load_model()
    video = cv2.VideoCapture(str(video_path))
    total = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    all_frames = []
    frame_number = 0
    while video.grab():
        if frame_number % FRAME_STEP == 0:
            ok, frame = video.retrieve()
            all_frames.append(track_frame(model, frame, frame_number))
            if len(all_frames) % 20 == 0:
                print(f"Tracking frame {frame_number} of {total}", flush=True)
        frame_number += 1
    video.release()
    fill_ball_gaps(all_frames)
    return all_frames


def fill_ball_gaps(all_frames):
    """Fills short gaps in the ball position with a straight line."""
    seen = [i for i, f in enumerate(all_frames) if f["ball"] is not None]
    for before, after in zip(seen, seen[1:]):
        missing = after - before - 1
        if missing == 0 or missing > MAX_BALL_GAP:
            continue
        (x1, y1), (x2, y2) = all_frames[before]["ball"], all_frames[after]["ball"]
        for step in range(1, missing + 1):
            t = step / (missing + 1)
            all_frames[before + step]["ball"] = (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
