"""domain seed flag

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("domains", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("seed", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("domains", schema=None) as batch_op:
        batch_op.drop_column("seed")
