from django.db import migrations

CREATE_TABLE = """
CREATE TABLE video_upload (
    id                 BIGSERIAL PRIMARY KEY,
    owner_id           INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    file_path          TEXT NOT NULL,
    first_frame_path   TEXT NOT NULL DEFAULT '',
    sport              TEXT NOT NULL DEFAULT 'futsal',
    status             TEXT NOT NULL DEFAULT 'uploaded',
    corners            TEXT,
    attack_direction   TEXT NOT NULL DEFAULT '',
    error              TEXT NOT NULL DEFAULT '',
    topdown_video_path TEXT NOT NULL DEFAULT '',
    summary            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunSQL(CREATE_TABLE, reverse_sql="DROP TABLE video_upload;")]
