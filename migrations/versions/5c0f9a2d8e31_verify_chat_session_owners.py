"""Track verified chat ownership and idempotent ticket submissions."""

from alembic import op
import sqlalchemy as sa

revision = "5c0f9a2d8e31"
down_revision = "a2801d519efc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("owner_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.add_column("tickets", sa.Column("request_key", sa.String(64), nullable=True))
    op.add_column("tickets", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_tickets_request_key", "tickets", ["request_key"])


def downgrade() -> None:
    op.drop_constraint("uq_tickets_request_key", "tickets", type_="unique")
    op.drop_column("tickets", "request_hash")
    op.drop_column("tickets", "request_key")
    op.drop_column("chat_sessions", "owner_verified")
