# Find the players in one frame of a video with YOLO, and save a picture of it.
# Run: .venv/bin/python backend/apps/video_analyzer/scripts/detect_demo.py ~/Downloads/test3.mp4.mov

import sys
import cv2
from ultralytics import YOLO

# 1. Load the YOLO model (downloads it the first time).
model = YOLO("yolo11n.pt")

# 2. Open the video and grab one frame (a single picture).
video = cv2.VideoCapture(sys.argv[1])
ok, frame = video.read()

# 3. Ask YOLO to find people (class 0) and balls (class 32) in the picture.
#    conf=0.4 means "only if you're at least 40% sure".
results = model(frame, classes=[0, 32], conf=0.4, imgsz=1920)

# 4. Print how many things it found.
print("Found", len(results[0].boxes), "things")

# 5. Draw the boxes on the picture and save it.
cv2.imwrite("detections.jpg", results[0].plot())
print("Saved detections.jpg")
