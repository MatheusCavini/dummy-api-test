"""add stripe billing fields and webhook event log

Revision ID: 20260222_01
Revises: 
Create Date: 2026-02-22 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260222_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("stripe_metered_subscription_item_id", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("subscription_status", sa.String(length=50), nullable=True))
    op.add_column("clients", sa.Column("subscription_current_period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clients", sa.Column("billing_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("clients", sa.Column("usage_synced_until", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_clients_stripe_customer_id", "clients", ["stripe_customer_id"], unique=True)
    op.create_index("ix_clients_stripe_subscription_id", "clients", ["stripe_subscription_id"], unique=True)

    op.create_table(
        "stripe_event_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stripe_event_log_id", "stripe_event_log", ["id"], unique=False)
    op.create_index("ix_stripe_event_log_event_id", "stripe_event_log", ["event_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_stripe_event_log_event_id", table_name="stripe_event_log")
    op.drop_index("ix_stripe_event_log_id", table_name="stripe_event_log")
    op.drop_table("stripe_event_log")

    op.drop_index("ix_clients_stripe_subscription_id", table_name="clients")
    op.drop_index("ix_clients_stripe_customer_id", table_name="clients")

    op.drop_column("clients", "usage_synced_until")
    op.drop_column("clients", "billing_enabled")
    op.drop_column("clients", "subscription_current_period_end")
    op.drop_column("clients", "subscription_status")
    op.drop_column("clients", "stripe_metered_subscription_item_id")
    op.drop_column("clients", "stripe_subscription_id")
    op.drop_column("clients", "stripe_customer_id")
