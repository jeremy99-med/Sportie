import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import db
from .serializers import upload_to_json
from .services import frames, pipeline

VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
MAX_UPLOAD_MB = 500
DIRECTIONS = ["left_to_right", "right_to_left"]


def error(message, status=400):
    return Response({"error": message}, status=status)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def uploads(request):
    """GET lists the user's uploads. POST uploads a new video."""
    if request.method == "GET":
        return Response([upload_to_json(u) for u in db.list_my_uploads(request.user.id)])

    file = request.FILES.get("file")
    if file is None:
        return error("Send the video in a field called 'file'.")
    extension = Path(file.name).suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        return error("That isn't a video file.")
    if file.size > MAX_UPLOAD_MB * 1024 * 1024:
        return error(f"Videos can be at most {MAX_UPLOAD_MB} MB.")

    user_id = request.user.id
    file_path = default_storage.save(f"videos/{user_id}/{uuid.uuid4().hex}{extension}", file)
    upload_id = db.create_upload(user_id, file_path)

    if frames.opencv_available():
        jpeg = frames.first_frame_jpeg(default_storage.path(file_path))
        if jpeg is None:
            delete_upload_and_files(db.get_upload(upload_id))
            return error("Couldn't read this video. Try an .mp4 file.")
        frame_path = default_storage.save(f"frames/{user_id}/{uuid.uuid4().hex}.jpg", ContentFile(jpeg))
        db.set_first_frame(upload_id, frame_path)

    return Response(upload_to_json(db.get_upload(upload_id)), status=201)


@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def upload_detail(request, upload_id):
    """GET returns one upload. DELETE removes it and its files."""
    upload = db.get_my_upload(upload_id, request.user.id)
    if upload is None:
        return error("Video not found.", 404)
    if request.method == "GET":
        return Response(upload_to_json(upload))
    delete_upload_and_files(upload)
    return Response(status=204)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze(request, upload_id):
    """Saves the court corners and attack direction, then starts the analysis."""
    upload = db.get_my_upload(upload_id, request.user.id)
    if upload is None:
        return error("Video not found.", 404)
    if upload["status"] == "processing":
        return error("This video is already being analyzed.", 409)

    corners = request.data.get("corners")
    direction = request.data.get("attack_direction")
    if not is_four_points(corners):
        return error("Send 4 corners, each as [x, y].")
    if direction not in DIRECTIONS:
        return error("attack_direction must be left_to_right or right_to_left.")

    db.start_analysis(upload_id, corners, direction)
    pipeline.start(upload_id)
    return Response(upload_to_json(db.get_upload(upload_id)), status=202)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def first_frame(request, upload_id):
    """Returns the first frame of the video as a JPEG."""
    return send_file(request, upload_id, "first_frame_path", "image/jpeg")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def result(request, upload_id):
    """Returns the finished top-down video."""
    return send_file(request, upload_id, "topdown_video_path", "video/mp4")


def send_file(request, upload_id, field, content_type):
    upload = db.get_my_upload(upload_id, request.user.id)
    if upload is None or not upload[field]:
        return error("Video not found.", 404)
    return FileResponse(default_storage.open(upload[field], "rb"), content_type=content_type)


def is_four_points(corners):
    """True if corners is 4 [x, y] pairs of non-negative numbers."""
    def is_number(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0

    return (isinstance(corners, list) and len(corners) == 4 and all(
        isinstance(p, list) and len(p) == 2 and all(is_number(v) for v in p) for p in corners))


def delete_upload_and_files(upload):
    for path in (upload["file_path"], upload["first_frame_path"], upload["topdown_video_path"]):
        if path:
            default_storage.delete(path)
    db.delete_upload(upload["id"])
