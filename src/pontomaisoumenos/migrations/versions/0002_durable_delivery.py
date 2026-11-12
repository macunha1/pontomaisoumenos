"""Durable delivery status and unambiguous timestamps for async processing."""

from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import context, op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    timezone = context.config.attributes.get("legacy_timezone", "America/Sao_Paulo")
    ZoneInfo(timezone)
    op.add_column("WORKING_PUNCHES", sa.Column("status", sa.String(16), nullable=False, server_default="pending"))
    op.add_column("WORKING_PUNCHES", sa.Column("queued_at", sa.DateTime(timezone=True)))
    op.execute(sa.text("UPDATE \"WORKING_PUNCHES\" SET status = 'done' WHERE done = true"))
    if op.get_bind().dialect.name == "postgresql":
        for table, columns in (
            ("USERS", ("updated_at", "created_at")),
            ("WORKING_PUNCHES", ("should_punch_at", "updated_at", "created_at")),
        ):
            for column in columns:
                op.alter_column(
                    table,
                    column,
                    type_=sa.DateTime(timezone=True),
                    postgresql_using=f"\"{column}\" AT TIME ZONE '{timezone}'",
                )
    with op.batch_alter_table("WORKING_PUNCHES") as batch:
        batch.create_unique_constraint("uq_punch_user_time", ["user_id", "should_punch_at"])
        batch.create_index("ix_punch_dispatch", ["status", "should_punch_at", "queued_at"])


def downgrade() -> None:
    # Reverting timestamp interpretation is not safe without the operator's
    # original timezone and a verified backup. Restore that backup instead.
    raise RuntimeError("Restore the pre-migration database backup to roll back revision 0002")
