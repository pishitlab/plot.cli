"""initial schema

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

import plot.db.models

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=253), nullable=False),
        sa.Column("suffix", sa.String(length=253), nullable=False),
        sa.Column("label", sa.String(length=63), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("auth_code", sa.String(length=64), nullable=False),
        sa.Column("created_at", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.Column("expires_at", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.Column("updated_at", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.Column("ns_ttl_override", sa.Integer(), nullable=True),
        sa.Column("delay_override", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("domain_name", sa.String(length=253), nullable=True),
        sa.Column("host_name", sa.String(length=253), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_events_domain_name"), ["domain_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_events_host_name"), ["host_name"], unique=False)

    op.create_table(
        "pending_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain_name", sa.String(length=253), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("scheduled_at", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.Column("apply_at", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.Column("applied_at", plot.db.models.UtcDateTime(length=27), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pending_changes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_pending_changes_domain_name"), ["domain_name"], unique=False
        )

    op.create_table(
        "published_state",
        sa.Column("domain_name", sa.String(length=253), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("published_at", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.PrimaryKeyConstraint("domain_name"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "domain_statuses",
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "status IN ('clientHold', 'serverHold', 'pendingDelete')", name="ck_status_value"
        ),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("domain_id", "status"),
    )
    op.create_table(
        "hosts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=253), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("parent_domain_id", sa.Integer(), nullable=True),
        sa.Column("created_at", plot.db.models.UtcDateTime(length=27), nullable=False),
        sa.CheckConstraint("kind IN ('subordinate', 'external')", name="ck_host_kind"),
        sa.ForeignKeyConstraint(["parent_domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "domain_ns",
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["hosts.id"],
        ),
        sa.PrimaryKeyConstraint("domain_id", "host_id"),
    )
    op.create_table(
        "host_addrs",
        sa.Column("host_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(length=45), nullable=False),
        sa.Column("family", sa.Integer(), nullable=False),
        sa.CheckConstraint("family IN (4, 6)", name="ck_addr_family"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("host_id", "address"),
    )


def downgrade() -> None:
    op.drop_table("host_addrs")
    op.drop_table("domain_ns")
    op.drop_table("hosts")
    op.drop_table("domain_statuses")
    op.drop_table("settings")
    op.drop_table("published_state")
    with op.batch_alter_table("pending_changes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pending_changes_domain_name"))

    op.drop_table("pending_changes")
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_events_host_name"))
        batch_op.drop_index(batch_op.f("ix_events_domain_name"))

    op.drop_table("events")
    op.drop_table("domains")
