"""Baseline corresponding to the original application's schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "USERS",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(128), unique=True),
        sa.Column("active", sa.Boolean()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_table(
        "WORKING_PUNCHES",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("USERS.id", ondelete="CASCADE"), nullable=False),
        sa.Column("should_punch_at", sa.DateTime()),
        sa.Column("done", sa.Boolean()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table("WORKING_PUNCHES")
    op.drop_table("USERS")
