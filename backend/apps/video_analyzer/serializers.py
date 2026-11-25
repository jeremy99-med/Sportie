def upload_to_json(upload):
    """Turns an upload row into the JSON sent to the frontend."""
    url = f"/api/video/uploads/{upload['id']}"
    return {
        "id": upload["id"],
        "sport": upload["sport"],
        "status": upload["status"],
        "error": upload["error"],
        "corners": upload["corners"],
        "attack_direction": upload["attack_direction"],
        "first_frame_url": f"{url}/first-frame/" if upload["first_frame_path"] else None,
        "topdown_video_url": f"{url}/result/" if upload["topdown_video_path"] else None,
        "summary": upload["summary"],
        "created_at": upload["created_at"],
    }
