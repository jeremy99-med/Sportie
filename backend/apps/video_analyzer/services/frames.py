def opencv_available():
    """True if OpenCV is installed."""
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def first_frame_jpeg(video_path):
    """Returns the first frame as JPEG bytes, or None if the video can't be read."""
    import cv2

    video = cv2.VideoCapture(str(video_path))
    ok, frame = video.read()
    video.release()
    return cv2.imencode(".jpg", frame)[1].tobytes() if ok else None
