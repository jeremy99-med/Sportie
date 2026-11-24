import json

from django.db import connection


def query(sql, params=(), fetch=None):
    """Runs one SQL statement. fetch is None, "one", or "all"."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        if fetch == "one":
            return to_dict(cursor, cursor.fetchone())
        if fetch == "all":
            return [to_dict(cursor, row) for row in cursor.fetchall()]


def to_dict(cursor, row):
    """Turns a row into a dict and parses the JSON columns."""
    if row is None:
        return None
    upload = dict(zip([column.name for column in cursor.description], row))
    for field in ("corners", "summary"):
        if field in upload:
            upload[field] = json.loads(upload[field]) if upload[field] else None
    return upload


def list_my_uploads(owner_id):
    return query("SELECT * FROM video_upload WHERE owner_id = %s ORDER BY id DESC", [owner_id], "all")


def get_my_upload(upload_id, owner_id):
    return query("SELECT * FROM video_upload WHERE id = %s AND owner_id = %s",
                 [upload_id, owner_id], "one")


def get_upload(upload_id):
    return query("SELECT * FROM video_upload WHERE id = %s", [upload_id], "one")


def create_upload(owner_id, file_path):
    return query("INSERT INTO video_upload (owner_id, file_path) VALUES (%s, %s) RETURNING id",
                 [owner_id, file_path], "one")["id"]


def set_first_frame(upload_id, first_frame_path):
    query("UPDATE video_upload SET first_frame_path = %s WHERE id = %s", [first_frame_path, upload_id])


def start_analysis(upload_id, corners, attack_direction):
    query("UPDATE video_upload SET corners = %s, attack_direction = %s, status = 'processing', "
          "error = '' WHERE id = %s", [json.dumps(corners), attack_direction, upload_id])


def mark_failed(upload_id, error):
    query("UPDATE video_upload SET status = 'failed', error = %s WHERE id = %s", [error, upload_id])


def save_results(upload_id, topdown_video_path, summary):
    query("UPDATE video_upload SET status = 'done', topdown_video_path = %s, summary = %s "
          "WHERE id = %s", [topdown_video_path, json.dumps(summary), upload_id])


def delete_upload(upload_id):
    query("DELETE FROM video_upload WHERE id = %s", [upload_id])
