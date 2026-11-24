MODEL_FILE = "yolo11n.pt"
IMAGE_SIZE = 1920  # the default 640 misses players in wide shots
COCO_PERSON = 0
COCO_SPORTS_BALL = 32


def load_model():
    """Loads the YOLO model."""
    from ultralytics import YOLO

    return YOLO(MODEL_FILE)


def detect(model, picture, min_confidence=0.4):
    """Finds the players and the ball in one frame."""
    results = model(picture, classes=[COCO_PERSON, COCO_SPORTS_BALL], conf=min_confidence,
                    imgsz=IMAGE_SIZE, verbose=False)
    found = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
        found.append({
            "kind": "player" if int(box.cls) == COCO_PERSON else "ball",
            "box": (x1, y1, x2, y2),
            "feet": ((x1 + x2) / 2, y2),
            "confidence": float(box.conf),
        })
    return found
