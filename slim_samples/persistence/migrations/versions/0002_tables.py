"""slim-samples' tables (S-07), append-only by trigger.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from slim_samples.persistence import append_only, types

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen here, not read from the models: this migration must keep meaning what it meant.
TABLES = ("samples_rules", "samples_containers", "samples_events")


def upgrade() -> None:
    op.create_table(
        "samples_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("published_by_id", sa.String(100), nullable=False),
        sa.Column("published_by", sa.JSON(), nullable=False),
        sa.Column("created_at", types.UtcDateTime(), nullable=False, server_default=types.db_now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_samples_rules")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_samples_rules_content_hash")),
    )
    op.create_table(
        "samples_containers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sample", sa.String(40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("container_type", sa.String(40), nullable=False),
        sa.Column("type_label", sa.String(100), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("rules_id", sa.Integer(), nullable=False),
        sa.Column("customer", sa.String(100), nullable=False, server_default=""),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("retention_due", sa.Date(), nullable=False),
        sa.Column("location", sa.String(40), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("analyses", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("received_by_id", sa.String(100), nullable=False),
        sa.Column("received_by", sa.JSON(), nullable=False),
        sa.Column("created_at", types.UtcDateTime(), nullable=False, server_default=types.db_now()),
        sa.ForeignKeyConstraint(
            ["rules_id"], ["samples_rules.id"], name=op.f("fk_samples_containers_rules_id_samples_rules")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_samples_containers")),
        sa.UniqueConstraint("sample", "position", name=op.f("uq_samples_containers_sample")),
    )
    op.create_index(op.f("ix_samples_containers_retention_due"), "samples_containers", ["retention_due"])
    op.create_table(
        "samples_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("container_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(40), nullable=True),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("by_id", sa.String(100), nullable=False),
        sa.Column("by", sa.JSON(), nullable=False),
        sa.Column("created_at", types.UtcDateTime(), nullable=False, server_default=types.db_now()),
        sa.ForeignKeyConstraint(
            ["container_id"],
            ["samples_containers.id"],
            name=op.f("fk_samples_events_container_id_samples_containers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_samples_events")),
    )
    op.create_index(op.f("ix_samples_events_container_id"), "samples_events", ["container_id"])
    append_only.install(op.get_bind(), TABLES)


def downgrade() -> None:
    append_only.uninstall(op.get_bind())
    op.drop_index(op.f("ix_samples_events_container_id"), table_name="samples_events")
    op.drop_table("samples_events")
    op.drop_index(op.f("ix_samples_containers_retention_due"), table_name="samples_containers")
    op.drop_table("samples_containers")
    op.drop_table("samples_rules")
