"""Initial SingMatch data model.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "songs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("artists", JSON_DOCUMENT, nullable=False),
        sa.Column("genre", sa.String(80), nullable=False),
        sa.Column("tags", JSON_DOCUMENT, nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("bpm", sa.Float()),
        sa.Column("energy", sa.Integer()),
        sa.Column("mood", sa.String(100)),
        sa.Column("duet_possible", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.UniqueConstraint("source", "source_id", name="uq_song_source_id"),
    )
    op.create_index("ix_songs_genre", "songs", ["genre"])
    op.create_table(
        "karaoke_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("song_id", sa.String(64), sa.ForeignKey("songs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("youtube_video_id", sa.String(11), nullable=False),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.Date()),
        sa.Column("rights_reviewed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_karaoke_versions_song_id", "karaoke_versions", ["song_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(12), nullable=False),
        sa.Column("genre", sa.String(80), nullable=False),
        sa.Column("intention", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("host_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sessions_code", "sessions", ["code"], unique=True)
    op.create_table(
        "participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("profile_draft", JSON_DOCUMENT),
        sa.Column("profile_confirmed", JSON_DOCUMENT),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("session_id", "name", name="uq_participant_name_per_session"),
    )
    op.create_index("ix_participants_session_id", "participants", ["session_id"])
    op.create_table(
        "scripts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("items", JSON_DOCUMENT, nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "version", name="uq_script_session_version"),
    )
    op.create_index("ix_scripts_session_id", "scripts", ["session_id"])


def downgrade():
    op.drop_index("ix_scripts_session_id", table_name="scripts")
    op.drop_table("scripts")
    op.drop_index("ix_participants_session_id", table_name="participants")
    op.drop_table("participants")
    op.drop_index("ix_sessions_code", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_karaoke_versions_song_id", table_name="karaoke_versions")
    op.drop_table("karaoke_versions")
    op.drop_index("ix_songs_genre", table_name="songs")
    op.drop_table("songs")
