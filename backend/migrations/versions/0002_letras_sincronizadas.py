"""Versões com letra sincronizada (vídeo original + LRC exibido pelo player).

Revision ID: 0002_letras_sincronizadas
Revises: 0001_initial
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_letras_sincronizadas"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("karaoke_versions") as batch:
        batch.add_column(sa.Column("kind", sa.String(24), nullable=False, server_default="karaoke"))
        batch.add_column(sa.Column("lyrics_lrc", sa.Text(), nullable=True))
        batch.add_column(sa.Column("lyrics_source", sa.String(200), nullable=True))


def downgrade():
    with op.batch_alter_table("karaoke_versions") as batch:
        batch.drop_column("lyrics_source")
        batch.drop_column("lyrics_lrc")
        batch.drop_column("kind")
